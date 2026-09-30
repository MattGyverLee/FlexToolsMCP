# Contract: `flextools_try_word` and `flextools_parse_status`

The two tools this slice adds. Identifiers pinned by the parent spec's Verbatim
Constraints are reproduced **exactly**; they are the contract, not a description
of it.

Both carry the annotation `READ_ONLY_SAFE`.

---

## What backs the `READ_ONLY_SAFE` annotation

The annotation is a claim about a **call path, not a class** (SPEC 12.1). Three
things hold it true, and all three are controls rather than promises:

1. **The facade cannot reach a write path.** `flexicon.ParserOperations` exposes
   exactly six members, frozen by a set-equality test in that repository. None
   records, files or writes a parse result. Adding one later would silently
   invalidate this annotation, which is why the absence is stated in that class's
   docstring.
2. **`HCParser_DoesNotLoadXCore`** -- after a real `Update()` + `ParseWord()` in the
   worker process, no `XCore` and no `System.Windows.Forms` assembly is loaded.
   Asserted against the **worker's** loaded-assembly list, because the server process
   never loads `ParserCore` at all and asserting there would prove nothing.
   `ParserWorker` and `ParserScheduler` pull xCore in through their own constructor
   parameters, so "reuse `ParserWorker` for consistency" is exactly the refactor this
   test exists to catch.
3. **The project is opened `writeEnabled=False`** in the worker, matching
   `handlers/grammar_health.py:196`.

A missing HC recording agent must **not** mark reading unavailable (FR-016): reading
neither records nor needs one. CP1 shipped the agent probe and its refusal logic with
tests and no caller; CP2b is the caller, and this is the boundary it must not blur.

---

## `flextools_try_word`

Parses one word. Three levels of answer, exposed as three -- they answer different
questions at different costs.

### Levels

| Level | Reaches | When to use |
|---|---|---|
| **restricted** | `TraceWordXml(word, analyses)` with a non-empty selection | the caller has a hypothesis. **Fastest**, not narrowest -- the selection is a pre-parse filter that collapses the search space before any tracing cost is paid |
| **plain** | `ParseWord(word)` | a cheap yes/no |
| **explain** | `TraceWordXml(word, None)` | the caller has no hypothesis. **Slowest**, and the one under a budget cap |

**Guidance defaults (FR-014): restricted when the caller has a hypothesis, explain
only when they do not.** Spending an explain-level budget on a word the caller could
have segmented by hand is the most common way this feature will feel slow.

**The plain level never answers "why" (FR-013).** It reports only that nothing
parsed, and its response points at the explaining levels. It must not present itself
as an explanation.

### Input

| Field | Type | Notes |
|---|---|---|
| `word` | str, required | the surface form |
| `level` | `restricted` \| `plain` \| `explain`, required | |
| `morphs` | list[`MorphSpec`], required for `restricted` | see `data-model.md` section 4 |
| `project_name` | str, required | which project's worker |

`morphs` on a non-`restricted` level is a usage error, not a silent ignore.

### Ordering guarantees

1. **The engine gate is first.** `check_active_parser(project, supported_engines=("HC",))`
   runs as the first statement of the worker's request handler, **before any parser
   area is touched**, and refuses a project configured for an unsupported engine with
   `parser_engine_mismatch`. `ActiveParser` is re-read live on every call, never
   memoized -- a user can flip it mid-session. Asserted by a test that records **zero**
   calls into the parser area for an `XAmple` project.
2. **Resolution before execution.** For `restricted`, every `MorphSpec` resolves
   before the worker is asked for anything. Any piece resolving to no usable analysis
   refuses with `parse_morph_unresolved` and **no parse runs** (FR-019, SC-005),
   asserted as a negative.
3. **Never widen.** An empty resolved selection is a refusal, never a call with an
   empty sequence and never a fallback to `explain`. The underlying component reads
   an empty restriction as "admit nothing" -- the opposite of "no restriction" -- and
   the setting outlives the call. `flexicon` refuses the empty sequence with
   `FP_ParameterError`; that exception reaching a caller as an internal error is a
   defect in this tool, not a safety net.

### The caller's hypothesis is never overruled (FR-023, FR-024, FR-025, SC-006)

- Traced **exactly as given**. No substitution, no widening, no reordering, no
  scoring, no demotion, no refusal on the grounds that it disagrees with recorded
  analyses.
- Where there is something to say, it is limited to an **adjacent candidate** (a
  different allomorph of the same entry, a homograph, a boundary shifted by one) or a
  **conflict with recorded analyses**; it is worded as an observation, carries **no
  confidence figure**, and rides alongside the result rather than replacing it.
- **Agreement produces no commentary.** A tool that congratulates every correct guess
  teaches the caller to skim the field where real warnings live.

A proposal diverging from every recorded analysis may be the correct analysis of an
irregular word -- which is exactly when a linguist reaches for this tool. A
ranking-by-agreement implementation must fail the test for this.

### The proposal assist (FR-021, FR-022, SC-011)

Where every piece has exactly one unambiguous candidate, the response **may** pre-fill
a proposed `morphs` and must label it **proposed, unverified**. A lexicon string match
is not a parse and knows nothing about phonological rules or environments.

`next_step` names the decomposition as the **missing input** and says what a usable
one looks like. It **cannot** point at a lexicon-query tool, because none exists --
every other tool is API discovery, codegen or admin, and the only path to lexicon data
is `flextools_run_module` executing Python. Any "look it up" rung is therefore a
`run_module` snippet, not a tool call. This constrains every `next_step` this slice
emits.

### Output

Inside the grace window, a complete result. Outside it, a bare `run_id`. See the
run contract below.

**Per-level result fields (spec.md Delta 6).** All three levels derive their
result fields from the single call already made -- never a second facade
call:

| Level | Success fields | Notes |
|---|---|---|
| `plain` | `parsed` (bool), `analysis_count` (int) | unchanged, already shipped |
| `explain` | `parsed` (bool), `analysis_count` (int), `trace_available`, `trace_path`, `trace_bytes` | the count is derived from the trace document's `<Analysis>` children, which is provably identical to `ParseWord`'s own count, not an approximation of it |
| `restricted` | `hypothesis_held` (bool), `restricted_analysis_count` (int), `trace_available`, `trace_path`, `trace_bytes`, `restricted_to` | **never** `parsed`/`analysis_count` -- these names are reserved for "does this word parse at all," and a restricted trace answers a narrower question ("does my restriction still admit an analysis") -- the keys are absent from the object entirely, never present and set to false |

**The `<Error>` case, for `explain` and `restricted` only.** If the trace
document carries `<Error>` instead of any `<Analysis>` (HermitCrab caught an
exception while tracing), or if the trace document has no `Root` at all and
so cannot be inspected for either, the response reports `parse_error` (a
message string) and emits **neither** `parsed`/`analysis_count` nor
`hypothesis_held`/`restricted_analysis_count` -- a zero-`<Analysis>` document
is ambiguous between "no analysis" and "the parse itself errored," and
neither field is honest to report in that state. `parse_error` **replaces**
both pairs rather than joining them: the object carries `parse_error` alone,
never `parse_error` alongside an absent-but-implied `parsed` or
`hypothesis_held`. The trace file, if written before the error, is still
reported via `trace_available`/`trace_path`. This is a deliberate asymmetry
with `plain`, where the underlying exception propagates and the request
fails outright rather than succeeding with a `parse_error` field -- the
diagnostic levels' trace is already on disk and useful by the time tracing
errors, so the request succeeded even though the parse did not.

**`explains_failure` and `next_step`, per level.** `plain` always reports
`explains_failure: False` -- it never explains, so the flag cannot honestly
claim otherwise regardless of whether the word parsed. `explain` reports
`explains_failure: False` with no rungs when `parsed` is true,
`explains_failure: True` with rungs toward `restricted` and a lexicon lookup
when it is false, and omits the key entirely on `parse_error` -- the trace
threw, so this response answers no question about the word either way.
`restricted` follows the same split for its own question, closed in cycle 4
rather than left as the unconditional `explains_failure: True` it shipped
with: `explains_failure: False` with no rungs when `hypothesis_held` is
true, unchanged `explains_failure: True` with no rungs when it is false
(the caller already committed to a level matched to their hypothesis, so
there is nothing new to suggest either way), and the key omitted on
`parse_error`, the same "presence of the key is the fact" discipline as
`explain`.

### Refusals

| Code | When |
|---|---|
| `parser_engine_mismatch` | the project is configured for an unsupported engine (CP1 code, first emitted here) |
| `parser_core_missing` | `GetAvailability()` reports unavailable; `reason` is carried through |
| `parse_morph_unresolved` | any piece of a decomposition did not resolve |
| `parse_job_cancelled` | the request attaches to a run already in a terminal state |

**`GetAvailability()` is called, never inferred.** `flexicon.CAPABILITIES` containing
`"parser"` means the build implements the surface, not that the parser is reachable
on this machine.

---

## `flextools_parse_status`

Read-only. Takes a `run_id`, reports stage, progress, and -- on a terminal stage --
the result summary or the failure with its `next_step`.

### The one asymmetry that is easy to implement wrong

**A terminal `failed` or `cancelled` run is reported as a SUCCESSFUL response.**
Asking about a dead run is a successful query, not a failed request (FR-033).

The **only** refusal this tool issues is `parse_run_not_found`, for a handle that
corresponds to no run -- naming the handle and listing the handles that do exist
(FR-035).

A cancelled run reports `words_completed` and the stage it was in when cancelled
(FR-036). `parse_job_cancelled` does **not** fire here. Both directions get a test.

### Output

| Field | Notes |
|---|---|
| `run_id` | |
| `stage` | one of the seven |
| `words_completed` / `words_total` | |
| `interleaved_by` | the run currently occupying the worker, or null -- what makes SC-009's "progress accounts for the interleave" observable rather than asserted |
| `result_summary` | on `completed` -- see the table below |
| `failure` | on `failed` -- message, stage at failure, and `next_step` |

**`result_summary` (spec.md Delta 6).** `parsed` and `hypotheses_held` count
two different questions and neither substitutes for the other:

| Field | Counts |
|---|---|
| `words` | every word in the run, regardless of level or outcome |
| `parsed` | entries carrying a `parsed` key (`plain` and `explain` results) where it is `true` -- **never** incremented for a `restricted` entry, which does not carry this key at all |
| `hypotheses_held` | `restricted` entries whose `hypothesis_held` is `true` -- the count `parsed` cannot honestly report for a restricted run, because a restricted trace never answers "does this word parse at all" |
| `traces_written` | entries with a `trace_path` (`explain`/`restricted`, never `plain`) |
| `record_dir` | unchanged |

Before this delta, `_result_summary` tested `parse.get("parsed")` against a
key `explain`/`restricted` results never wrote, so every completed
`explain`/`restricted` run reported `parsed: 0` unconditionally --
indistinguishable from "every word failed," even when the traces on disk
showed successful analyses.

An entry carrying `parse_error` counts toward `words` (and toward
`traces_written` if a trace file was written before the error) but toward
**neither** `parsed` nor `hypotheses_held` -- it answers neither question,
the same replaces-rather-than-joins reading `parse_error` gets at the
single-word level above.

---

## The run contract (FR-026 .. FR-032)

**One mechanism.** All parser execution goes through it. There is **no** separate
synchronous path, and there must not be one added later: CP3 consumes this runner
rather than growing a second execution model.

| Guarantee | Contract |
|---|---|
| **grace window** | default **5 seconds**, configurable. A run reaching a terminal stage inside it returns results inline and no handle is issued. |
| **the window is reporting, not execution** | it is **not** a timeout. Closing it cancels 0 runs, slows 0 runs and throttles nothing (FR-028, SC-010). A test asserts the run keeps going after the handle is returned. |
| **incremental persistence** | results are written to the run record as they are produced, so a run that dies at word 4,000 leaves 4,000 readable (FR-029, SC-008). |
| **priority** | `ReloadGrammarAndLexicon = 0, TryAWord = 1, High = 2, Medium = 3, Low = 4`. Lower wins, FIFO within a level, **per-wordform** enqueue granularity -- that granularity is what makes interleaving possible at all. |
| **interleave** | queue-jump, **not preemption**. A higher-priority word runs at the running batch's **next word boundary**; the batch does not restart or lose position, the grammar is **not** reloaded, and reported progress accounts for the interleave (FR-031, SC-009). |
| **cancellation** | cooperative. Stops at the next word boundary, leaves `cancelled` over the partial results (FR-032). |
| **held grammar** | one slot, for the project in use, released when another project's grammar is needed; currency confirmed before every reuse; an explicit reload is **reset then update**, two steps (FR-042, FR-043, SC-014, SC-015). |

**The ordering guarantee is ours.** The local FieldWorks tree carries an uncommitted
change draining its queue into a parallel batch and losing priority ordering within
it. We do not use `ParserScheduler`. It does not bind us, it must never be cited as
our rationale, and our runner must not copy it.

---

## Contract-document obligations (FR-037)

| Artifact | Change |
|---|---|
| `docs/TOOL-CONTRACT.md` | one row per new code; the documented count **22 -> 25** (`:69`) |
| `CHANGELOG.md` | one entry under **"Tool contract"** |
| `server/response_models.py` | three detail models, `extra="forbid"`, `Literal` discriminator |
| `server/tool_definitions.py` | two `ToolDef` entries with their input models and `READ_ONLY_SAFE` annotation |

Additive throughout -- the contract stays at `tool-responses/1.0`.

### Which of the four rows Delta 6 touches

Delta 6 (the diagnostic levels reporting their result -- `hypothesis_held`,
`restricted_analysis_count`, `parse_error`, `hypotheses_held`) adds
**success-payload fields only**. It raises no new error code and removes or
renames nothing, so the contract stays at `tool-responses/1.0` -- this is the
same additive-optional posture the base contract already uses for
`update_notice`, `workspace_notice`, `diagnostic_report`, and
`inherited_from`.

| Artifact | Delta 6 touches it? | Why |
|---|---|---|
| `docs/TOOL-CONTRACT.md` | **yes** | new subsection documenting the per-level fields and the `parse_error` case; the error-code count at `:69` does **not** move -- no new code |
| `CHANGELOG.md` | **yes** | one entry under **"Tool contract"**, the convention already used for additive codes |
| `server/response_models.py` | **yes** | the `explain`/`restricted` result models and the `result_summary` model gain fields; still `extra="forbid"` throughout |
| `server/tool_definitions.py` | **no** | no new input argument on either tool -- only response fields change. Touch only if a `ToolDef` description string becomes inaccurate (SPEC 10 truthfulness), not as a required change |

(Delta 7's narrow analysis signature is spec-only this spurt and touches
none of the four rows yet -- when it is built, it follows the same pattern:
a `response_models.py` addition, a `CHANGELOG.md` entry, a `TOOL-CONTRACT.md`
subsection, and no `tool_definitions.py` change, because it adds no input
either.)
