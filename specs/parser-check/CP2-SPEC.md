# CP2 -- parser-check: the read spine goes live

**Parent spec:** [`SPEC.md`](./SPEC.md) (2252 lines) -- this document does not
restate it. Section references like "5.1.1" point there unless marked local.
**Scope:** SPEC 15, CP2 row.
**Status:** draft, not reviewed by the crew, not started.
**Predecessor:** CP1 (`tasks.md`, T001-T035; 28/35 done at time of writing).
**Writes:** none. CP2 is entirely `READ_ONLY_SAFE`; filing arrives at CP4.

---

## 1. What CP2 is

CP1 established that the parser *could* be driven -- located, capability-probed,
engine-gated -- without ever constructing one. CP2 constructs one.

Three deliverables, in a build order that is not negotiable (section 2):

| # | Deliverable | Repo | Why it is here |
|---|---|---|---|
| **A** | The read-only `project.Parser` facade plus three companion read gaps | **flexicon** | S9. Generated FLExTools modules import from flexicon and cannot reach MCP-internal code |
| **B** | `flextools_try_word` -- all three trace modes of 5.1.1, plus mode A's MSA-HVO resolver | FlexToolsMCP | The first tool that actually parses |
| **C** | The job runner of 5.6 and `flextools_parse_status` | FlexToolsMCP | New infrastructure; the MCP has no async job model today |

Plus the `HCParser_DoesNotLoadXCore` standing test, which SPEC 15 calls out
separately because **that test is the safety story** -- `flextools_try_word`'s
`READ_ONLY_SAFE` annotation is a claim about a call path (12.1), and this is the
only thing that holds the claim true under later refactoring.

### 1.1 What CP2 is not

- **Not a write.** No `ParseFiler`, no filing, no ladder. CP4.
- **Not batch scoping.** `UniqueWordforms()`, `parse_diff`, `parse_log` and the
  G3 batch layer are CP3, and they *consume* CP2's runner rather than adding a
  second execution model.
- **Not the sandbox.** `hcparse.ps1` hardening and `flextools_parse_sandbox` are
  CP5.
- **Not a general segmenter.** 5.1.2's anti-requirement stands: the decomposition
  assist is opportunistic and bounded, never a search.

---

## 2. Build order, and why it binds

SPEC 5.4 settles this and section 15 sequences it: **the flexicon facade lands
first and the MCP consumes it.** The MCP does not grow a temporary parser path of
its own to be retired later.

That makes CP2 a **cross-repo checkpoint**, which nothing in CP1's tracking
prepared for. The real sequence:

```
A1  flexicon: facade + 3 read gaps, behind a lazy import + capability probe
A2  flexicon: release  (4.8.0 -> 4.9.0)
A3  MCP: bump the floor in pyproject.toml/requirements.txt to >=4.9.0,<5
A4  MCP: regenerate the index -> index/python/flexicon_api_v4.9.0.json
     (`python -m flextoolsmcp.refresh`; the floor and the indexed version must
      match -- see CLAUDE.md's note on the 2.10.0 mismatch that shipped an index
      built at 4.5.2 against a >=4.3.0 floor)
B   MCP: flextools_try_word consuming project.Parser
C   MCP: the job runner + flextools_parse_status
```

**A2 is a real gate, not a formality.** The MCP pins `pyflexicon>=4.8.0,<5`, so
until a release exists, `project.Parser` is not installable and B cannot be
tested against anything but a working tree. Whoever schedules CP2 should treat
A1-A4 as its first phase rather than as a prerequisite that happens elsewhere.

**Mitigating fact:** flexicon is the same maintainer's repo, currently on `main`
at `598f41e` with a clean tree and no advisory lock. The "cross-repo negotiation"
SPEC 17.5 flags is a scheduling question, not a political one. It is still a
release.

---

## 3. Part A -- the flexicon change

### 3.1 The facade

A thin read-only `project.Parser`, naming to flexicon's own verb conventions
(`code/` is organised `Grammar/`, `Lexicon/`, `TextsWords/`, ... with an
`Operations` class per area and `FLExProject` exposing accessors -- `Parser`
joins that list).

It wraps exactly the surface 5.4's capability probe already enumerates, and
nothing more:

| Facade call | Wraps | Mode (5.1.1) |
|---|---|---|
| `TryWord(form)` | `ParseWord(string) -> ParseResult` | B |
| `TryWordXml(form)` | `ParseWordXml(string) -> XDocument` | B |
| `TraceWord(form, msa_hvos=None)` | `TraceWordXml(string, IEnumerable<int>)` | A when `msa_hvos` given, C when `None` |
| `Reload()` | `Update()` | -- |
| `IsUpToDate()` | `IsUpToDate()` | -- |

`ParseFiler` is **not** wrapped. Per S9 the write path stays in the MCP, and per
12.1 a facade that cannot reach a write type is what makes the read spine's
safety claim structural rather than conventional. Adding a filing method to this
facade later would silently invalidate `flextools_try_word`'s annotation -- say so
in the module docstring, where a future contributor will actually read it.

**Result marshalling is a real design question, not a passthrough.** `ParseResult`
and `XDocument` are .NET objects. Returning them raw makes every consumer do
pythonnet interop; converting them fully duplicates work the MCP also does.
Recommendation: return typed Python structures for `ParseResult` (analyses ->
morphs -> `form`, `gloss`, plus the `IMoForm`/`IMoMorphSynAnalysis`/`ILexEntryInflType`
**objects**, not just their strings -- 9.3.1 and 11 both need object identity, and
a string-only marshal would quietly break the diff's `MatchesIWfiAnalysis`
alignment), and return the trace as an `XDocument` or its XML string unchanged,
since no consumer's needs are known well enough yet to fix a schema. Flag for
crew review: this is the one place CP2 could make CP3 and CP4 harder.

### 3.2 The three companion read gaps

All currently raw-LCM-only, all named in 5.4 as part of the same change:

1. **`Texts.GetGenres()`** -- `IText.GenresRC`, the full reference collection.
   `GetGenre()` returns only the first genre, so genre selection (6.1) misses a
   text tagged `[Narrative, Folklore]` when scoped by `"Folklore"`. Needed by
   CP3, specified here because it ships in the same release.
2. **Allomorph -> owning entry.** `GetOwningEntry` exists for Etymology, Sense,
   Pronunciation and Variant, but not allomorphs.
3. **An MSA read surface.** `MSAOperations` exposes **none at all** -- its own
   stub says so (`MSAOperations.pyi:14-20`) -- yet 5.1.1's resolver must terminate
   in MSA HVOs. **This one is on mode A's critical path**, not adjacent to it.

Items 2 and 3 are what make 5.1.2's resolver writable in flexicon rather than
forcing the MCP to reach past the facade into raw LCM -- which would defeat the
point of the facade.

### 3.3 The two acceptance conditions

SPEC 5.4 is explicit that these are **the terms on which the facade was
accepted**, not risks to monitor: *"failing either is grounds to keep the facade
out of flexicon rather than to ship it degraded."*

**Condition 1 -- the import must be lazy.** A future FieldWorks that renames or
relocates `ParserCore.dll` must degrade to "parser unavailable", never break
`import flexicon` for users of unrelated features. So no module-level
`clr.AddReference("ParserCore")`; the load is call-triggered.

**Condition 2 -- a capability probe, never a version floor.** Two checks, neither
of which reads a version:

1. **Same install.** `ParserCore.dll` must come from the same FieldWorks
   directory that supplied the resolved `SIL.LCModel.dll`. Mixing two installs
   across an in-process boundary is the failure a floor would not have caught.
2. **The bound surface exists.** Reflect over exactly the members called, and
   **bind positionally** -- `IParser` names the parameter `word`, `HCParser`
   implements it as `form` (`IParser.cs:23,25`), so keyword binding breaks on the
   interface/impl mismatch.

The detected version is **reported**, never decisive. No code path may compare
`detected_version` against a floor; CP1's T007 already ships a standing
regression test for that on the MCP side, and flexicon needs its own.

### 3.4 The duplicate-probe problem (local finding -- needs a decision)

CP1 shipped exactly this capability probe in `src/flextoolsmcp/server/parser_probe.py`
(978 lines). Condition 2 now requires the same probe on flexicon's side, in a
separate repo with no shared code.

**Two implementations of one safety-critical check will drift.** Options, none
free:

- **(a) Duplicate deliberately**, with the member list as the single point of
  truth in both, plus a cross-repo test asserting both enumerate the same set.
  Simple; drift is detectable but only if someone runs both suites.
- **(b) Move the probe into flexicon and have the MCP consume it.** No drift, but
  `flextools_health`'s parser block (CP1, shipped) then depends on flexicon for
  detection it currently does itself — and health must keep working when the
  facade is unavailable, which is precisely when the probe matters most.
- **(c) Flexicon probes only what the facade binds; the MCP keeps its own
  superset** (which includes `ParseFiler.ProcessParse` for the write spine, a
  member flexicon deliberately does not wrap). The two probes are then *different
  by design*, and divergence stops being a bug.

**Recommendation: (c).** It matches the split S9 already drew — flexicon probes
the read surface it wraps, the MCP probes the full surface it gates — and it is
the only option where the two probes having different member lists is correct
rather than a smell. Flag for crew review; this decides whether CP2 touches
`parser_probe.py` at all.

### 3.5 Release mechanics

- Version: **4.9.0** (additive surface, no breaking change).
- MCP floor: `pyflexicon>=4.9.0,<5` in `pyproject.toml` **and**
  `requirements.txt` -- CLAUDE.md notes these mirror each other.
- Index: regenerate so `index/python/flexicon_api_v4.9.0.json` exists and the
  floor matches the indexed version. The 2.10.0 incident (index built at 4.5.2
  against a `>=4.3.0` floor, resolving to 4.4.1 in practice) is the failure mode
  to avoid.
- `__init__.pyi` must declare the new public surface -- flexicon has an existing
  ratchet test on the declared surface (`3fbc922`, "declare the full public
  surface in `__init__.pyi`").

---

## 4. Part B -- `flextools_try_word`

### 4.1 Three modes, exposed as three

Per 5.1.1, the modes answer different questions at different costs and the tool
exposes all three. **Mode A is the fastest, not the narrowest** -- `selectTraceMorphs`
is a pre-parse filter that collapses the search space before any tracing cost is
paid. Mode C is the slowest and is the G2 answer of record.

Defaults matter more than the parameterisation: **A when the caller has a
hypothesis, C only when they do not.** 9.4's cap is a cap on **C**. Spending a
mode-C budget on a word the caller could have segmented by hand is the most
common way this feature will feel slow.

Mode B never answers "why" -- it reports only that nothing parsed. Wherever the
spec says "trace the word to find out why," it means A or C.

### 4.2 Mode A's resolver -- the net-new work

`selectTraceMorphs` is `IEnumerable<int>` matched against
`Morpheme.Properties["ID"]` -- MSA HVOs. FLEx harvests them from the Try A Word
sandbox where the user has already picked real entries. **Over MCP there is no
sandbox**, so the tool accepts what a caller can actually write -- entry
headwords, entry+sense, or MSA HVOs directly -- and resolves it.

`HCParser` does not do this for us. A caller guessing HVOs is not a design.

**A morph that resolves to no MSA is not a usable selection.** FLEx refuses
outright when any selected HVO is `0` (`TryAWordDlg.cs:519-524`). Mirror it
exactly: `parse_morph_unresolved`, naming the offending morph and its candidates.
A silently-degraded mode A is worse than a failure — its empty result reads as
"your grammar rejects this analysis" when the truth is "we never tested the
analysis you asked for," which is the fabricated verdict 8.4 forbids.

**Performance requirement, from 5.1.2:** every existing flexicon lookup is an
unindexed linear scan, and `LexEntryOperations.Find` is exact, case-sensitive,
lexeme-form-only and returns only the **first** match — unusable for a candidate
generator that needs all homographs. Build the form -> morph index **once per
run** and reuse it. A project-wide allomorph pass per word is the obvious way to
make this feature feel slow.

### 4.3 The proposal assist, and its ceiling

5.1.2: **the caller proposes, the MCP resolves.** A calling model has the
glosses, the surrounding text and the user's hypothesis; the MCP does not.

The assist exists so the hand-off is not a dead end:

- `next_step` names the decomposition as the **missing input** and says what a
  usable one looks like. It **cannot** point at a lexicon-query tool, because
  none exists — all 21 existing tools are API-discovery, codegen or admin, and
  the only path to lexicon data is `run_module` executing Python. Any "look it
  up" step is a `run_module` snippet, not a tool call. This constrains every
  `next_step` CP2 emits.
- Where the MCP holds an unambiguous candidate (single entry per morph, no
  competing allomorph), **pre-fill `args.morphs`** — bounded, always labelled a
  guess.
- Label it **"proposed, unverified"**. A lexicon string match is not a parse and
  knows nothing about phonological rules or environments.

### 4.4 When the proposal looks wrong (5.1.3)

**Always trace what was asked.** Substituting a different restriction under a
restricted label is the same violation as handing back an unrestricted search.
The flag rides alongside the result, never in place of it.

Surface only two things: an **adjacent candidate** (different allomorph of the
same entry, a homograph, a boundary shifted by one), and a **conflict with
standing evidence** (contradicts the tier-3 analyses already recorded). **Silence
on agreement** — a tool that congratulates every correct guess teaches the caller
to skim the field where real warnings live.

**The 9.3.2 asymmetry governs here, and this is the part most likely to be
implemented wrong.** A proposal diverging from every recorded analysis may be the
correct analysis of an irregular word — which is exactly when a linguist reaches
for Try A Word. Flag divergence as an **observation**, never a verdict. Never
demote, refuse, reorder or score. No confidence number on a user's hypothesis.

---

## 5. Part C -- the job runner

**New infrastructure.** `start_module` is an interactive wizard, not an async
runner; `subprocess_helpers` is blocking-with-timeout. Per 5.6 the runner lands
with the first tool that needs it, which is `flextools_try_word`.

### 5.1 States and the fast path

States: `starting | loading_grammar | parsing | filing | completed | failed |
cancelled`. (`filing` is defined here but unreachable until CP4.)

**The fast path is part of the contract, not an optimisation.** A job reaching a
terminal state inside a grace window (default 5s, configurable) returns results
**inline** and the caller never polls. Only a job still running when the window
closes returns a bare `run_id`. One set of job machinery, no second synchronous
path to drift.

The window governs **reporting, never execution**: it is not a timeout, and
closing it neither cancels nor throttles the job.

`loading_grammar` is its own state for two reasons: it is the step that most
often exhausts memory, so attributing a death to it is diagnostic; and on a large
project it dominates the run before a single word is parsed, so a caller shown
only "running" concludes the tool is hung.

A terminal `failed` carries a `next_step` pointing at 9.5.2's G4 instruments — a
run that died of memory exhaustion is the case where the user most needs a
diagnosis rather than a retry.

### 5.2 Priority and interleave

Mirror FLEx's names and ordering exactly (`ParserScheduler.cs:25-32`):

```
ReloadGrammarAndLexicon = 0, TryAWord = 1, High = 2, Medium = 3, Low = 4
```

**Lower value wins.** One sorted queue, FIFO within a level, **per-wordform**
enqueue granularity — that granularity is what makes interleaving possible at all.

**Queue-jump, not preemption.** A high-priority single word interleaves at the
running batch's **next word boundary**; the batch does not restart or lose
position, and the grammar stays loaded once for both. The batch's reported
progress must account for the interleave rather than appearing to stall.

> Our guarantee is our own. The local FieldWorks tree carries an **uncommitted**
> change (`ParserScheduler.cs:265-296`) draining the whole queue into a
> `Parallel.ForEach` batch, losing priority ordering within it. We do not use
> `ParserScheduler`, so it does not bind us — but we must never argue "FLEx
> guarantees this ordering" as our rationale, and our runner must not copy it.

### 5.3 Cancellation

An hours-long operation that can consume all available memory and cannot be
stopped is not an acceptable surface. Cancellation is **cooperative**: it stops
at the next word boundary and leaves a `cancelled` terminal state over the
partial results, exactly as a failure would.

### 5.4 `flextools_parse_status`

`READ_ONLY_SAFE`. Takes `run_id`, reports state, progress, and — on a terminal
state — the result summary or the failure with its `next_step`.

Results accumulate in the run artifact (5.5) **as they are produced**, so a job
that dies at word 4,000 leaves 4,000 usable results beside a terminal state
naming the failure. This is the same commitment `parser_timeout`'s
`words_completed` field makes from the failure side: partial work is preserved
and reportable, never discarded.

---

## 6. Inherited from CP1

CP1 shipped several things with no live caller. CP2 is that caller, and these are
easy to miss because they are already `[x]`:

| From | Obligation at CP2 |
|---|---|
| T024 | `check_active_parser()` must be **the first statement** of every spine-executing handler, before any `HCParser` construction |
| T025 / 12.7 | The HC-agent probe gets its first live caller. **The read spine is unaffected** — `try_word` neither files nor resolves an agent, so a missing HC agent must never mark `read` unavailable |
| T027 | Agent-probe refusal logic shipped with tests but no caller; CP2 supplies it |
| T013 | `next_step` rows that degraded to `tool: null` because `flextools_try_word` did not exist can now name it. **Revisit every one** |
| T031 | The three PanGloss lints, if `GrammarHealthChecker` is public — fold in or record the CP2 deferral |
| T028 | Deferred SPEC 16 groups now in scope: `HCParser_DoesNotLoadXCore`, the oracle-absent bullet, the conditional-proposal bullet, and the flexicon-facade group |

---

## 7. Error codes added at CP2

Additive to `tool-responses/1.0`; CHANGELOG entry under "Tool contract", count
bumped from 22.

| Code | Detail fields |
|---|---|
| `parse_morph_unresolved` | `morph`, `candidates`, `position`, `hint` |
| `parse_run_not_found` | `run_id`, `available_runs` *(already specced in SPEC 14; first emitted here)* |
| `parse_job_cancelled` | `run_id`, `words_completed`, `state_at_cancel` |

`parser_engine_mismatch`, `parser_core_missing`, `parser_agent_missing` and
`parser_tool_missing` ship at CP1 and are merely *emitted* here.

---

## 8. Test plan

**Standing guarantee — the one that matters most**

- `HCParser_DoesNotLoadXCore`: isolated process; after a real `Update()` +
  `ParseWord()`, assert no `XCore` / `System.Windows.Forms` assembly is loaded.
  This is the safety story behind `try_word`'s `READ_ONLY_SAFE` annotation, and
  the guarantee is about a **call path, not a class** (12.1) — `ParserWorker` and
  `ParserScheduler` pull xCore in through their own constructor parameters, so
  "reuse ParserWorker for consistency" is exactly the refactor this test exists
  to catch.

**Mode and resolver**

- Each of A/B/C reaches the correct underlying call, with mode A passing a
  non-empty `IEnumerable<int>` and mode C passing `null`.
- A morph resolving to no MSA produces `parse_morph_unresolved` and **no parse
  runs** — assert the negative, since a silently-degraded mode A is the failure
  8.4 forbids.
- Positional binding: a fixture whose parameter is named `word` rather than
  `form` still binds.
- The form -> morph index is built once per run, not per word.

**Proposal handling (5.1.3)**

- A proposal diverging from every recorded analysis is traced **as given**, is
  never reordered or scored, and its divergence is worded as an observation. A
  ranking-by-agreement implementation must fail this test — same shape as 9.3.2's
  promotion-only test.
- Agreement produces **no** commentary.

**Job runner**

- A job completing inside the window returns inline; one exceeding it returns a
  bare `run_id` and the job keeps running (assert the window is not a timeout).
- A `TryAWord` submitted during a running batch interleaves at the next word
  boundary; the batch neither restarts nor loses position; the grammar loads once.
- Cancellation leaves `cancelled` over preserved partial results.
- A job killed mid-run leaves its completed results readable in the artifact.

**flexicon side**

- `import flexicon` succeeds with `ParserCore.dll` absent or relocated, and
  `project.Parser` reports unavailable rather than raising (condition 1).
- The capability probe refuses a ParserCore from a different install directory,
  and **passes an unexpected-but-complete version** — the standing regression
  against reintroducing a floor.

---

## 9. Exit criteria

1. `pyflexicon` 4.9.0 released; MCP floor and bundled index both at 4.9.0.
2. `flextools_try_word` answers all three modes against a live HC-configured
   project, with mode A driven by a caller-supplied decomposition.
3. `HCParser_DoesNotLoadXCore` passes and is wired into the default suite.
4. The runner demonstrates: inline fast path, poll path, word-boundary
   interleave, cooperative cancel, and partial-result survival across a killed
   job.
5. Every CP1 `next_step` row that degraded to `tool: null` for `try_word` is
   revisited.
6. Full suite green — CP1's T028 groups plus this document's section 8.
7. Live verification (`lex-verification`) on a project with a working HermitCrab
   grammar. **Not Sena 3** unless confirmed to have one.

---

## 10. Open questions

1. **The duplicate-probe decision** (3.4) — (a), (b) or (c). Decides whether CP2
   touches `parser_probe.py`.
2. **Result marshalling** (3.1) — how much of `ParseResult` crosses into Python,
   and in what shape. The one place CP2 can make CP3/CP4 harder; note 9.3.1 and
   11 both need LCM **object identity**, not just strings.
3. **Trace payload shape.** `TraceWordXml` returns an `XDocument` that can be
   large. Does the facade return it raw, and does the MCP persist it to the run
   artifact rather than the response? 5.5 implies the artifact; confirm.
4. **Grammar load lifetime.** `Update()` is expensive and `loading_grammar`
   dominates a cold run. Is a loaded `HCParser` cached per project for the
   session, and if so what invalidates it? `IsUpToDate()` /
   `ParserModelChangeListener` exist for this — but a cached parser is
   process-lifetime state the MCP does not currently keep.
5. **12.7's live question** (SPEC 17.10) — whether a migration or lazy path
   materialises the HC agent. CP2 is the first checkpoint that could answer it
   from a real project, though the read spine does not depend on it.

---

## 11. Risks

- **The cross-repo release is the schedule risk**, not the code. A1-A4 gate
  everything else, and B is untestable against a released dependency until A2.
- **The runner is the scope risk.** It is new infrastructure specified in
  considerable detail (priority queue, interleave, cancellation, fast path,
  incremental artifacts) and it arrives attached to a tool that, for a single
  word against a loaded grammar, would otherwise be a synchronous call. Resist
  the temptation to ship `try_word` synchronously and add the runner at CP3 —
  5.6 is explicit that there must not be a second execution model, and CP3
  assumes the runner exists.
- **Mode A's resolver is the correctness risk.** It is net-new, on the critical
  path, and its failure mode (a silently-degraded selection) produces a confident
  wrong answer about someone's grammar.
