---
description: "Task list for parser-check CP2a-bridge + CP2b"
---

# Tasks: parser-check CP2a-bridge + CP2b -- the assistant reaches the parser

**Input**: design documents from `specs/parser-check-cp2b/`

**Prerequisites**: [`plan.md`](./plan.md), [`spec.md`](./spec.md) (scoping; authoritative
requirement text is [`../parser-check-cp2/spec.md`](../parser-check-cp2/spec.md)),
[`research.md`](./research.md), [`data-model.md`](./data-model.md),
[`contracts/tools.md`](./contracts/tools.md), [`contracts/bridge.md`](./contracts/bridge.md),
[`quickstart.md`](./quickstart.md)

**Tests**: test tasks are included and are **not optional here**. The parent
specification's success criteria are stated as measurements, the registered `after_plan`
gate blocks on coverage that is asserted but not scheduled, and CP2a's own history is the
argument: a green offline suite and four green structural ratchets coexisted with a silent
wrong answer for an entire checkpoint.

**Organization**: by user story, per the parent spec's US2 (P2), US3 (P3), US4 (P4).
US1 is CP2a and is complete; it appears here only as the three read gaps its execution
left untested (R-08), which are a precondition of US3.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US2, US3, US4. Setup, Foundational and Polish tasks carry no story label.

## Path conventions

Repository root is `D:\Github\_Projects\_LEX\FlexToolsMCP`. Paths below are relative to it
unless prefixed `flexicon:`, which means the sibling repository at
`D:\Github\_Projects\_LEX\flexicon`.

---

## Phase 1: Setup

**Purpose**: the one decision and the two files everything else assumes.

- [x] T001 Resolve the open maintainer branch decision recorded in `specs/parser-check-cp2b/spec.md` ("Open maintainer decision"): this repository is on `feat/parser-check-cp1` and CP2b writes production code here. Cut or confirm `feat/parser-check-cp2` before T004 and record the decision in `specs/parser-check-cp2b/evidence/cp2b-evidence.md`. **Blocks every implementation task below.**
- [x] T002 [P] Create the run-machinery package at `src/flextoolsmcp/server/parse/__init__.py`, exporting nothing yet; the package boundary is what makes process-lifetime ownership expressible (plan.md Structure Decision)
- [x] T003 [P] Create `specs/parser-check-cp2b/evidence/cp2b-evidence.md` with CP2a's recording discipline as headings: exact invocation per measurement, full counts including failures, pre-existing failures named as pre-existing, and anything not run recorded as **not run** rather than omitted

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the bridge, the untested accessors underneath the resolver, and the run
machinery the parent spec forces all three stories to share.

**CRITICAL**: no user story work begins until this phase completes. FR-026 means there is
no second, simpler execution path to fall back on, so this phase is not deferrable.

### CP2a-bridge -- FR-011 (plan Phase A)

- [x] T004 Regenerate the bundled index by running `python -m flextoolsmcp.refresh`, producing `src/flextoolsmcp/index/python/flexicon_api_v4.9.0.json`, `src/flextoolsmcp/index/python/flexicon_lcm_bridge_v4.9.0.json` and `src/flextoolsmcp/index/common_patterns_flexicon-v4.9.0.json` (the third artifact the Verbatim Constraints do not name -- research.md R-04)
- [x] T005 Write the floor/index equality test in `tests/test_flexicon_index_floor.py` asserting declared floor == the version `src/flextoolsmcp/server/versioning.py` resolves == the suffix of **every flexicon-version-locked artifact discovered by pattern**, never a hardcoded pair; the failure message names which of the three disagrees; a LibLCM regeneration skip must not fail it
- [x] T006 **Observe T005 failing** against the pre-bridge tree (floor still `>=4.8.0,<5`) and paste the red output into `specs/parser-check-cp2b/evidence/cp2b-evidence.md`. A test that has never been red has not been shown to detect anything -- this step is acceptance, not ceremony (contracts/bridge.md, ordering step 3)
- [x] T007 Raise the declared minimum to `pyflexicon>=4.9.0,<5` in `pyproject.toml` and mirror it in `requirements.txt`, then re-run `tests/test_flexicon_index_floor.py` green
- [x] T008 Run `python -m pytest -q` at repository root -- the floor change touches dependency tests -- and record the exact invocation and full counts in `specs/parser-check-cp2b/evidence/cp2b-evidence.md`
- [x] T009 [P] In a clean environment run `pip install "pyflexicon>=4.9.0,<5"`, then `python -c "import flexicon; print(flexicon.version)"` (expect `4.9.0`) and `python -m pytest -q`; record under **its own evidence line** in `specs/parser-check-cp2b/evidence/cp2b-evidence.md`. This session cannot perform it; if it does not run it is recorded as **not run** and must never be rounded into T005's green (research.md R-01)

### Close R-08 -- the three read gaps, in flexicon (plan Phase B)

Before the resolver: FR-019's refusal is only as trustworthy as the accessor underneath it.

- [x] T010 [P] Write `flexicon:tests/operations/test_text_genres.py` covering `Texts.GetGenres` (FR-007), pinning the empty-collection contract
- [x] T011 [P] Write `flexicon:tests/operations/test_allomorph_owner.py` covering `Allomorphs.GetOwningEntry` (FR-008), pinning the null-owner branch
- [x] T012 [P] Write `flexicon:tests/operations/test_msa_read.py` covering `MSA.GetAll` (FR-009) -- the resolver's terminal accessor
- [x] T013 In the flexicon repository run `python -m pytest -m "not requires_live_project" -q`, that repository's required invocation per its Constitution Principle II; `pytest --ignore=tests/contract` is prohibited there and appears nowhere in this list. Record counts in `specs/parser-check-cp2b/evidence/cp2b-evidence.md`

### The run machinery, bottom-up (plan Phase C)

Built and proven against a **stub** parse before it is pointed at the real facade, so a
queue defect and a parser defect cannot be mistaken for one another.

- [x] T014 [P] Implement the closed stage enum and its transition table in `src/flextoolsmcp/server/parse/stages.py` -- exactly `starting | loading_grammar | parsing | filing | completed | failed | cancelled`
- [x] T015 [P] Implement the five priority levels in `src/flextoolsmcp/server/parse/priority.py` -- `ReloadGrammarAndLexicon = 0, TryAWord = 1, High = 2, Medium = 3, Low = 4`, lowest wins
- [x] T016 Write `tests/test_parse_stages.py`: the seven names verbatim, the transition graph, terminal stages absorbing, and an assertion that **no CP2b code path can produce `filing`** (FR-027)
- [x] T017 Implement the single sorted queue with **per-wordform** enqueue granularity in `src/flextoolsmcp/server/parse/queue.py`; FIFO within a level; built now to accept CP3's `Medium`/`Low` enqueues so CP3 adds no second runner
- [x] T018 Write `tests/test_parse_priority_queue.py`: priority ordering, FIFO within a level, per-wordform granularity (FR-030). The ordering guarantee is this feature's own -- the local FieldWorks tree's uncommitted parallel-drain change to `ParserScheduler` must not be cited as rationale or copied
- [x] T019 Implement the append-only JSONL run record in `src/flextoolsmcp/server/parse/record.py` following `src/flextoolsmcp/server/skeleton_storage.py`: `meta.json` rewritten on stage change, `results.jsonl` appended **and flushed per word**, traces written out of line to `traces/<n>.xml`, a **size cap from day one**, and a server-issued opaque `run_id` that is never a caller-controlled path component
- [x] T020 Write `tests/test_parse_record.py`: per-word flush rather than buffered write, kill-survival leaving every prior result readable (FR-029, SC-008), the size cap, and that no caller string reaches a path component
- [x] T021 Implement the long-lived worker in `src/flextoolsmcp/server/parse/worker_main.py` -- line-delimited JSON on stdin/stdout, one worker per project, project opened `writeEnabled=False`, one held-grammar slot, cancellation observed **at a word boundary**, idle timeout releasing the project. Addressed by dotted module path exactly as `run_scan_module` addresses `scan/grammar_scan_module.py`; **the server process must never import it** (research.md R-02)
- [x] T022 Implement the server side of the channel in `src/flextoolsmcp/server/parse/worker_client.py`, launched through the existing `subprocess_helpers.run_script_async` family -- not a second execution mechanism -- with shutdown teardown via the existing `_kill_process_tree` path (issue #57)
- [x] T023 Implement the run lifecycle in `src/flextoolsmcp/server/parse/runner.py`: stage transitions, the 5-second configurable grace window, `cancel_requested`, and the single execution path all three stories use (FR-026)
- [x] T024 Write `tests/test_parse_runner.py` against the stub worker: the grace window **reports, it does not execute** -- assert the run keeps advancing after the handle is returned, and that closing the window cancels 0 runs and slows 0 runs (FR-028, SC-010)
- [x] T025 Write the worker-lifetime tests in `tests/test_parse_worker_lifetime.py`: idle release, shutdown teardown, and the orphaned-worker case. A *long-lived* pythonnet holder of a `.fwdata` lock makes issue #57's known failure worse, so this is scheduled rather than left to review
- [x] T026 Point the worker in `src/flextoolsmcp/server/parse/worker_main.py` at the real `flexicon.ParserOperations` facade, with `check_active_parser(project, supported_engines=("HC",))` as the **first statement** of the request handler and `GetAvailability()` called rather than inferred from the `CAPABILITIES` token (research.md R-03, spec.md Delta 4)

**Checkpoint**: bridge landed, accessors tested, one execution path exists. Stories begin.

---

## Phase 3: User Story 2 -- "Does this word parse, and why not?" (Priority: P2) -- MVP

**Goal**: a linguist asks whether a word parses and gets a complete answer in one call;
a failure explains itself in the parser's own terms.

**Independent test**: on a project with a working grammar, ask for a word known to parse
and a word known to fail; both return complete answers in one call and the failure
explains itself. Then point the same call at an `XAmple` project and confirm it is refused
up front with no parser constructed.

- [ ] T027 [P] [US2] Add `TryWordInput` to `src/flextoolsmcp/server/models.py` -- `word`, `level` (`restricted` | `plain` | `explain`), `morphs`, `project_name`; `morphs` on a non-restricted level is a usage error, not a silent ignore
- [ ] T028 [US2] Implement the `flextools_try_word` handler in `src/flextoolsmcp/server/handlers/parse.py`, mapping the three levels to `TraceWordXml(word, analyses)` / `ParseWord(word)` / `TraceWordXml(word, None)`. Bind **positionally** -- the interface says `word` where the implementation says `form` for both XML-producing operations, so anything bound by name to either breaks (FR-012)
- [ ] T029 [US2] In the same handler make the plain level report only that nothing parsed and point at the explaining levels; it must never present itself as an explanation (FR-013). Add the guidance defaults: restricted when the caller has a hypothesis, explain only when they do not (FR-014)
- [ ] T030 [US2] Register the tool in `src/flextoolsmcp/server/tool_definitions.py` with the `READ_ONLY_SAFE` annotation and add its route in `src/flextoolsmcp/server/dispatch.py`
- [ ] T031 [US2] Write `tests/test_try_word_handler.py`: the three levels reach the three calls (FR-012); plain does not explain (FR-013); guidance defaults (FR-014); the engine gate is first, asserted as **zero recorded calls into the parser area** for an `XAmple` project and with `ActiveParser` re-read live rather than memoized (FR-015); and a missing HC recording agent does **not** mark reading unavailable (FR-016)
- [ ] T032 [P] [US2] Write `tests/test_parser_no_xcore.py` -- the standing test named `HCParser_DoesNotLoadXCore`, a name pinned by the Verbatim Constraints. After a real `Update()` + `ParseWord()` **in the worker process**, no `XCore` and no `System.Windows.Forms` assembly is loaded, asserted against the **worker's** loaded-assembly list. Include the positive vacuity guard: `ParserCore` *is* loaded and the parse produced a result (FR-017, SC-003)
- [ ] T033 [US2] Add quickstart scenarios 1, 2 and 3 to `tests/test_parse_live.py` against `IndonesianHC-Complete`, read-only: a word parses inline against a held grammar and a second call does not re-enter `loading_grammar`; `Sena 3` is refused with `parser_engine_mismatch` naming `XAmple` and `HC`; a failing word at plain offers no reason and at explain carries the parser's trace
- [ ] T034 [US2] Measure SC-004 as a **rate, not a boolean**: repeat the single-word call across a set of words against the held grammar, record the attempt count and the observed inline rate (>=95% required), and put **both numbers** in `specs/parser-check-cp2b/evidence/cp2b-evidence.md`. One fast call does not discharge this criterion

**Checkpoint**: US2 is independently demonstrable. This is the MVP.

---

## Phase 4: User Story 3 -- "Test my hypothesis about this word" (Priority: P3)

**Goal**: a caller's proposed decomposition, given in headwords, is traced exactly as
given -- or refused outright naming the piece that could not be resolved.

**Independent test**: supply a decomposition by headword for a word with a known analysis
and confirm the trace is restricted to it; supply one with an unresolvable piece and
confirm refusal with the piece named and no parse run.

**Depends on**: Phase 2 (T012 in particular -- the resolver terminates in `MSA.GetAll`)
and Phase 3's handler.

- [ ] T035 [US3] Implement the morph resolver in `src/flextoolsmcp/server/parse/resolver.py`: `MorphSpec` (`headword` / `sense` / `msa_hvo` / `position`, exactly one of headword or msa_hvo required, **no free-text form**) to MSA identifiers, with the lookup index built **exactly once per run** (FR-018, FR-020, SC-007)
- [ ] T036 [US3] Keep the three failure outcomes distinct in `src/flextoolsmcp/server/parse/resolver.py` -- `none`, `ambiguous`, `no_msa`. Collapsing them into a bare refusal reproduces the silent-narrowing failure the requirement exists to prevent: the caller cannot tell whether to fix a spelling, pick a homograph, or conclude the entry has no analysis
- [ ] T037 [P] [US3] Add the `parse_morph_unresolved` detail model to `src/flextoolsmcp/server/response_models.py` with `ConfigDict(extra="forbid", populate_by_name=True)` and a `Literal` discriminator, matching the four CP1 parser models at `:361-416`. Five fields **in this exact order**: `morph`, `position`, `resolved_to`, `candidates`, `hint`. Do not reorder, rename, recase or pluralize -- this order was the subject of a three-way agreement check during CP2's cycle 3
- [ ] T038 [US3] Wire the `restricted` level in `src/flextoolsmcp/server/handlers/parse.py` so resolution completes **before the worker is asked for anything**, and an empty resolved selection is a **refusal, never a widening**: never a call with an empty sequence, never a fallback to `explain`. `flexicon` raises `FP_ParameterError` on an empty iterable and the setting outlives the call; that exception reaching a caller as an internal error is a defect in this tool, not a safety net (spec.md Delta 2)
- [ ] T039 [US3] Write `tests/test_parse_resolver.py`: headword / headword+sense / identifier input (FR-018); the three outcomes stay distinct; the index is built once per run (SC-007); and FR-019's **negative assertion** -- when a piece is unresolvable, **0 parses run** (SC-005), asserted by recorded calls rather than inferred
- [ ] T040 [US3] Implement the bounded proposal assist in `src/flextoolsmcp/server/handlers/parse.py`: where every piece has exactly one unambiguous candidate, pre-fill a proposed `morphs` labelled **proposed, unverified** -- a lexicon string match is not a parse and knows nothing about phonological rules (FR-021). `next_step` names the decomposition as the missing input and, for any "look it up" rung, emits a `flextools_run_module` snippet, because no lexicon-query tool exists to point at (FR-022, SC-011)
- [ ] T041 [US3] Write `tests/test_parse_proposal.py`: traced exactly as given with no substitution, widening, reordering, scoring or demotion; commentary limited to an adjacent candidate or a conflict with recorded analyses, worded as an observation and carrying **no confidence figure**; and **silence on agreement** (FR-023, FR-024, FR-025, SC-006). Include the case most likely to be implemented wrong -- a decomposition disagreeing with every recorded analysis must be traced as given and not refused, so that **a ranking-by-agreement implementation fails this test**
- [ ] T042 [US3] **Run the sweep-pattern audit** for the CLR collection-parameter binding and write its result into `specs/parser-check-cp2b/evidence/cp2b-evidence.md`. CP2a's null-vs-empty sweep found no siblings but recorded a by-construction claim that *any future binding of a CLR method taking a collection parameter re-opens the obligation*; `src/flextoolsmcp/server/parse/resolver.py` feeds `TraceWordXml`'s `IEnumerable<int>`, so it is re-opened. **CP2a's QC gate blocked on a missing pattern audit; a repeat is not acceptable** (CLAUDE.md)
- [ ] T043 [US3] Add quickstart scenario 4 to `tests/test_parse_live.py` against `IndonesianHC-Complete`: a resolvable decomposition restricted to exactly the analyses given; an unresolvable piece refused with the five fields in order and `resolved_to: none`; then the `ambiguous` and `no_msa` variants kept distinct; then the divergent-decomposition case traced exactly as given

**Checkpoint**: US3 independently demonstrable on top of US2.

---

## Phase 5: User Story 4 -- long parses are visible, interruptible and never lose work (Priority: P4)

**Goal**: a run outliving the grace window returns a handle, keeps going, can be polled
and cancelled, survives death with its partial results readable, and yields to an urgent
single word at a word boundary.

**Independent test**: start a parse long enough to exceed the grace window against
`Malay Parsing-20230810withHC`; confirm a handle returns and the work continues; poll it;
cancel it; confirm partial results survive. Separately submit an urgent single word during
a running batch.

**Depends on**: Phase 2's runner, queue and record.

- [ ] T044 [P] [US4] Add `ParseStatusInput` to `src/flextoolsmcp/server/models.py` -- a single `run_id`
- [ ] T045 [P] [US4] Add the `parse_run_not_found` (`run_id`, `available_runs`) and `parse_job_cancelled` (`run_id`, `words_completed`, `state_at_cancel`) detail models to `src/flextoolsmcp/server/response_models.py`, same `extra="forbid"` + `Literal` discriminator convention
- [ ] T046 [US4] Implement the `flextools_parse_status` handler in `src/flextoolsmcp/server/handlers/parse.py`: stage, `words_completed` / `words_total`, `interleaved_by`, `result_summary` on `completed`, `failure` on `failed`. A terminal `failed` or `cancelled` run is reported as a **SUCCESSFUL response** -- asking about a dead run is a successful query, not a failed request (FR-033)
- [ ] T047 [US4] Make `parse_run_not_found` the **only** refusal that tool issues, naming the handle and listing the handles that do exist (FR-035); register the tool in `src/flextoolsmcp/server/tool_definitions.py` with `READ_ONLY_SAFE` and add its route in `src/flextoolsmcp/server/dispatch.py`
- [ ] T048 [US4] Attach diagnostic guidance to a failed run's `RunFailure.next_step` in `src/flextoolsmcp/server/parse/runner.py`, pointing at `flextools_health` and `flextools_grammar_health` -- memory exhaustion during `loading_grammar` is the case where a diagnosis beats a retry (FR-034)
- [ ] T049 [US4] Implement the word-boundary interleave in `src/flextoolsmcp/server/parse/queue.py` and `src/flextoolsmcp/server/parse/worker_main.py` as a **queue-jump, not preemption**: the urgent word runs at the running batch's next word boundary, the batch does not restart or lose position, the grammar is **not** reloaded, and the batch's status carries `interleaved_by` so a caller polling mid-interleave does not see a stalled run (FR-031, SC-009)
- [ ] T050 [US4] Implement cooperative cancellation in `src/flextoolsmcp/server/parse/runner.py` and `src/flextoolsmcp/server/parse/worker_main.py`: the server sets `cancel_requested`, the worker observes it at the next word boundary and ends `cancelled` over the partial results; a second cancel against a terminal run is `parse_job_cancelled` (FR-032, FR-036)
- [ ] T051 [US4] Write `tests/test_parse_status_handler.py` covering **both directions** of the asymmetry: a cancelled run reports success with `words_completed` and the stage at cancel, while a second cancellation raises `parse_job_cancelled`; and an unknown handle refuses naming the available ones (FR-033, FR-035, FR-036)
- [ ] T052 [US4] Extend `tests/test_parse_priority_queue.py` with the interleave assertions: the urgent word begins within one word boundary, **0 words repeated**, the grammar loaded **exactly once** for both, and reported batch progress accounts for the interleave (SC-009)
- [ ] T053 [US4] Add quickstart scenarios 5 and 6 to `tests/test_parse_live.py` against `Malay Parsing-20230810withHC`, read-only: grace-window overflow with the work continuing across two polls; `loading_grammar` distinguished from `parsing` on a cold run; live interleave; cooperative cancel; and worker-kill survival with 0 results lost. **41 entries cannot exercise these -- the project split is not interchangeable** (SC-017)

**Checkpoint**: all three stories demonstrable.

---

## Phase 6: Polish and cross-cutting concerns

- [ ] T054 [P] Add three rows to `docs/TOOL-CONTRACT.md` for `parse_morph_unresolved`, `parse_run_not_found` and `parse_job_cancelled`, and raise the documented count **22 -> 25** at `docs/TOOL-CONTRACT.md:69`. Additive throughout -- the contract stays at `tool-responses/1.0`
- [ ] T055 [P] Add one entry under "Tool contract" in `CHANGELOG.md`
- [ ] T056 Extend `tests/test_response_contract.py` with the three codes, asserting `parse_morph_unresolved`'s **field order** and the raised count (FR-037)
- [ ] T057 Repoint every CP1 `next_step` row that degraded to `tool: null` in `src/flextoolsmcp/server/handlers/diagnostic_health.py` so it names `flextools_try_word`, and revert the `write: unavailable` / `read: ready` row's replacement action text to wording that names the tool (FR-038)
- [ ] T058 Amend `tests/test_flextools_health.py` for the repointed rows and add a registry sweep asserting **0 `next_step` references to tools that do not exist** across the emitted guidance (FR-038, SC-011)
- [x] T059 Amend `tests/test_cp1_boundary.py` -- **amended, never weakened**: narrow its scope in writing to the CP1 surface, add the `server/parse/` worker-module allowlist entry, and **pin that allowlist with a test** so widening it later means editing a test (research.md R-06). The guarantee that the diagnostic path still never parses is exactly the one CP2b makes easiest to break
- [x] T060 Add to `tests/test_cp1_boundary.py` the AST check asserting no handler reaches the parser facade outside `src/flextoolsmcp/server/parse/` -- the structural half of FR-026's "one mechanism"
- [ ] T061 Implement the SPEC 16 test groups CP1 deferred -- the no-user-interface-code guarantee, the no-oracle case, the conditional-proposal case and the script-library facade group -- and enumerate them by name in `specs/parser-check-cp2b/evidence/cp2b-evidence.md` (FR-039)
- [ ] T062 [P] Record Decision D5's grammar-lint deferral to CP3 in `specs/parser-check-cp2b/evidence/cp2b-evidence.md`, stating that the engine-version-specific absence must be **re-probed** in CP3 rather than inherited from CP2's verdict (FR-040)
- [ ] T063 [P] Correct `specs/parser-check/CP2-SPEC.md` section 3.1 (`:91-95`) in place: it tabulates `TryWord` / `TryWordXml` / `TraceWord`, none of which exists. Replace it with the shipped six-member surface so the next reader is not misled (spec.md Delta 1)
- [ ] T064 Record `git diff --stat -- src/flextoolsmcp/server/parser_probe.py` showing **0 lines changed** in `specs/parser-check-cp2b/evidence/cp2b-evidence.md`, and confirm each of the two capability checks states what the other carries that it lacks (FR-041, SC-016)
- [ ] T065 Verify FR-042 and FR-043's **current** half live in `tests/test_parse_live.py`: at most one held grammar, released when another project's grammar is needed, currency confirmed before every reuse, and an explicit reload performed as **reset then update**, two steps (SC-014, and the dischargeable half of SC-015)
- [x] T066 **E-D -- the one live write. STOP HERE IF NOBODY IS WATCHING.** Quickstart scenario 7 in `specs/parser-check-cp2b/quickstart.md`: parse a word, make a model change so the held grammar's currency reads stale, parse again, and confirm the facade reloads **before** the second word is parsed. Requires a present human's authorisation and a **backed-up or copied** project, never an installed project relied on for anything else. An unattended run must not perform it and must report status `needs_human`. If it is not run, record it in the evidence artifact as **not run**, with what stays unproven: the automatic path firing when the model genuinely changes underneath a held grammar
- [ ] T067 Run the full suite `python -m pytest -q` at repository root and record the exact invocation and full counts, failures included, in `specs/parser-check-cp2b/evidence/cp2b-evidence.md` (SC-013)
- [ ] T068 Finalize `specs/parser-check-cp2b/evidence/cp2b-evidence.md`: per-scenario observations, the SC-004 rate **with its attempt count**, the pattern-audit result from T042, FR-043 shown as **half discharged** with E-D named, and T009 and T066 each recorded as run or not run. Then dispatch the registered `after_implement` crew gates

---

## Dependencies

```
Phase 1 (Setup)
   |
Phase 2 (Foundational)
   |-- bridge      T004 -> T005 -> T006 -> T007 -> T008 ;  T009 may lag, does not gate
   |-- R-08        T010 | T011 | T012  ->  T013
   |-- machinery   T014 | T015  ->  T016
   |               T015 -> T017 -> T018
   |               T019 -> T020
   |               T021 -> T022 -> T023 -> T024 ;  T025
   |               T013 + T023 -> T026
   |
   +-- Phase 3 (US2, P2)   <- MVP
   |        |
   +-- Phase 4 (US3, P3)   needs T012 (MSA.GetAll tested) and T028 (the handler)
   |        |
   +-- Phase 5 (US4, P4)   needs T017, T019, T023
            |
        Phase 6 (Polish)
```

**Story independence.** US3 and US4 are independently *testable* but not independently
*deliverable*: the parent spec states US2 and US3 run on US4's machinery and that no
second execution path exists. That coupling is why the machinery sits in Foundational
rather than inside US4 -- US4's own phase carries the behaviours a user observes, not the
plumbing all three stories share.

**The bridge gates everything.** Per `contracts/bridge.md`, CP2b's first parser task may
not start until T007 has landed.

---

## Parallel execution

- **T002, T003** -- different files, no ordering between them
- **T010, T011, T012** -- three independent flexicon test files
- **T014, T015** -- `stages.py` and `priority.py` share nothing
- **T027, T032** -- an input model and a standing assembly test
- **T044, T045** -- an input model and two detail models
- **T054, T055, T062, T063** -- four different documents

**Not parallel, though it looks it.** T005 and T007 must run in that order with T006
between them. The whole point of T006 is watching the test fail *before* the floor moves;
doing them together loses the only evidence that the test detects anything.

---

## Implementation strategy

**MVP is Phase 1 + Phase 2 + Phase 3.** That delivers the answer of record the checkpoint
exists to produce: a user asks whether a word parses and the parser answers. It is the
first point at which the feature is visible to a user at all.

**Increment 2 is Phase 4** -- the hypothesis mode: the highest-value mode for the expert
user and the checkpoint's main correctness risk.

**Increment 3 is Phase 5** -- visibility and interruptibility, which is scope risk rather
than user-facing novelty.

**Then Phase 6**, of which T066 may end the run with `needs_human` rather than completion.
That is a correct outcome, not a failure.

---

## Requirement coverage cross-check

Mirrors `plan.md`'s coverage table with task IDs, so coverage the plan asserts is coverage
this list schedules.

| Requirement | Task(s) |
|---|---|
| FR-011, SC-013 | T004, T005, T006, T007, T008, T067 |
| FR-011 (published dist installs) | T009 -- separate evidence line |
| FR-012 | T028, T031 |
| FR-013 | T029, T031 |
| FR-014 | T029, T031 |
| FR-015 | T026, T031, T033 |
| FR-016 | T031 |
| FR-017, SC-003 | T032 |
| FR-018 | T035, T039 |
| FR-019, SC-005 | T036, T038, T039 |
| FR-020, SC-007 | T035, T039 |
| FR-021, FR-022 | T040, T041 |
| FR-023, FR-024, FR-025, SC-006 | T041, T043 |
| FR-026 | T023, T060 |
| FR-027 | T014, T016 |
| FR-028, SC-010 | T023, T024 |
| SC-004 | T034 -- a measured rate with its attempt count |
| FR-029, SC-008 | T019, T020, T053 |
| FR-030 | T017, T018 |
| FR-031, SC-009 | T049, T052, T053 |
| FR-032 | T050, T051 |
| FR-033, FR-036 | T046, T051 |
| FR-034 | T048 |
| FR-035 | T047, T051 |
| FR-037 | T037, T045, T054, T056 |
| FR-038, SC-011 | T040, T057, T058 |
| FR-039 | T061 |
| FR-040 | T062 |
| SC-012 | T033, T043 |
| SC-017 | T053 |
| FR-041, SC-016 | T064 |
| FR-042, SC-014 | T065 |
| FR-043, SC-015 | T065 (current half) + **T066 / E-D** (stale half) |
| R-06 | T059 |
| R-08 | T010, T011, T012, T013 |
| pattern-audit obligation | T042 |
