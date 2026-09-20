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
| `result_summary` | on `completed` |
| `failure` | on `failed` -- message, stage at failure, and `next_step` |

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
