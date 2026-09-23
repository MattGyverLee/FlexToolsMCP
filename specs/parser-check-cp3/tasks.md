# Tasks: parser-check CP3 -- the corpus, the artifact, and the diagnosis

**Input**: Design documents from `specs/parser-check-cp3/`

**Prerequisites**: [`plan.md`](./plan.md), [`spec.md`](./spec.md), [`research.md`](./research.md), [`data-model.md`](./data-model.md), [`contracts/tools.md`](./contracts/tools.md), [`contracts/artifact.md`](./contracts/artifact.md), [`quickstart.md`](./quickstart.md)

**Authoritative requirement text**: [`../parser-check/SPEC.md`](../parser-check/SPEC.md) section 15. `spec.md` here is the scoping document.

**Tests**: **Included, and not optional for this feature.** The spec's Success Criteria are written as assertions ("asserted by a regression test", "a count-equality implementation fails this assertion"), and `plan.md`'s Test strategy table schedules each one. Five tests are written so the *wrong* implementation fails rather than merely disagrees: SC-008, SC-014, SC-015, FR-018 and FR-022's retention.

**Organization**: Tasks are grouped by user story (US1..US6) so each story is independently implementable and testable. The plan's own implementation phases map onto these story phases; where they differ, the deviation is noted in the phase header.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel -- different files, no dependency on an incomplete task
- **[Story]**: US1..US6, mapping to the user stories in `spec.md`
- Every task names its exact file path

## Path conventions

Single Python package. Server code under `src/flextoolsmcp/`, tests at `tests/`, documentation at `docs/`, campaign specs under `specs/`.

## Transcription rule (applies to every task below)

> Verbatim strings -- the five refusal codes and their **field order**, the six oracle sentences, the eight host counter names, the four job-failure reasons, the bucket names, the section names, the staleness markers -- are transcribed from [`contracts/tools.md`](./contracts/tools.md) and **not** re-derived from prose. CP2's own field-order divergence cost two crew cycles and happened during transcription, not because the source was wrong.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: confirm the entry gate is still closed and create the empty seams the later phases fill.

- [X] T001 Confirm the entry gate before any CP3 change: run `pytest tests/ -k "floor or index_equality" -q` and `pytest tests/test_parser_no_xcore.py -q` from the repository root and record both green in `specs/parser-check-cp3/quickstart.md`'s run log. Neither may be weakened or skipped to land a CP3 change.
- [X] T002 Capture a full-suite baseline with `pytest tests/ -q` so any later red is attributable to CP3 rather than inherited.
- [X] T003 [P] Confirm the dependency floor `pyflexicon >= 4.9.0, < 5` is declared in `requirements.txt` and `pyproject.toml`, and that the bundled index agrees, per `plan.md` Technical Context.
- [X] T004 [P] Create the new package `src/flextoolsmcp/server/signals/__init__.py` with a module docstring stating that it holds CP3's *interpretation* surface, deliberately separate from `server/parse/` which CP4 and CP5 read.
- [X] T005 [P] Create the live-marked test module `tests/test_parse_live_cp3.py` with the pytest marker used by the existing `tests/test_parse_live.py`, and a module docstring naming the two designated projects `IndonesianHC-Complete` and `Malay Parsing-20230810withHC` and excluding `Sena 3` by name (it reports engine `XAmple`).
- [X] T006 Record the status of the open maintainer decision D-1 (the destructive annotation on `flextools_parse_text`) at the top of `specs/parser-check-cp3/plan.md`'s "Open maintainer decision" section. It blocks T050, not this phase.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the plan's Phase 1 -- the two live questions and the one shared probe -- plus the five refusal detail models, which US1 and US4 both refuse through.

**⚠️ CRITICAL**: no user story work may begin until T007 and T012 are complete. T008-T011 gate *wording*, not build (R-08), and may run alongside Phase 3.

- [X] T007 Implement the single read-only project-state probe in `src/flextoolsmcp/server/parse/project_state.py` (FR-004), with its three consumers named in the module docstring: the never-parsed warning (FR-041), the oracle precondition (FR-041), and CP4's deletion-projection precondition (FR-050). It MUST be built exactly once; a second probe at CP4 is a review finding.
- [X] T008 [P] *(run; FR-001 NOT settled -- the designated project holds no never-tokenized text. See `live-note-fr001-fr003.md`. FR-002's conservative wording is unaffected.)* Answer FR-001 on a live project: establish whether a text never opened for interlinear work is distinguishable through the data model alone from a text that genuinely contains no words. Capture the evidence under `specs/parser-check-cp3/` as a live-run note.
- [X] T009 [P] Answer FR-003 on a live project: establish whether an analysis can be recorded against a text segment without any human act. Capture the evidence alongside T008's.
- [X] T010 Write both answers back into the open-question register of `specs/parser-check/SPEC.md` (FR-001, FR-003). Until T009's answer is recorded, the description of what the indeterminate population *contains* MUST NOT ship (it gates one sentence in T090, not the split itself).
- [X] T011 [P] Add the offline unit test for the probe in `tests/test_parse_project_state.py`, asserting it performs no project write and that all three consumers resolve through the one implementation.
- [X] T012 Add the five refusal detail models to `src/flextoolsmcp/server/response_models.py`, transcribed field-for-field and **in the exact field order** from `specs/parser-check-cp3/contracts/tools.md` section 2: `parse_scope_empty` (`scope`, `matched_texts`, `hint`), `parse_scope_ambiguous` (`scope`, `requested`, `candidates`), `parse_scope_mismatch` (`baseline_fingerprint`, `current_fingerprint`, `differing_fields`, `hint`), `parser_timeout` (`timeout_seconds`, `words_completed`, `run_id`, `hint`), `parser_job_failed` (`state_at_failure`, `failure`, `words_completed`, `words_total`, `run_id`, `log_path`). Each uses `model_config = ConfigDict(extra="forbid", populate_by_name=True)` and a `Literal` `error_code`, copying `ParseRunNotFoundDetail` (`response_models.py:476`) as the template (FR-059, FR-060, R-04).
- [X] T013 Extend `tests/test_parser_error_models.py` to assert, for all five new codes, that extra fields are forbidden and that the declared field order matches `contracts/tools.md` byte-for-byte. A reordered model must fail.
- [X] T014 Assert in `tests/test_parser_error_models.py` that the response contract version is still `tool-responses/1.0` and that the five additions are purely additive -- no existing code changed shape (FR-059).

**Checkpoint**: the shared probe exists once, the five codes exist and are pinned, and the two live answers are recorded. User stories may begin.

---

## Phase 3: User Story 1 - "Which words am I actually asking about?" (Priority: P1) 🎯 MVP

**Goal**: resolve a scope to a definite, ordered, de-duplicated word list, and record a fingerprint that decides whether two runs are comparable -- without starting a parse.

**Independent Test**: resolve a scope by genre, by text, and across all texts on a live project; confirm the word list, its ordering, its count and its recorded fingerprint, with no parse started.

**Plan mapping**: plan Phase 2's first half. The artifact half of plan Phase 2 moves to US2 (Phase 4), where the run that writes it lives.

### Tests for User Story 1 ⚠️

> Write these first and confirm they fail.

- [x] T015 [P] [US1] Write the two-genre regression in `tests/test_parse_scope.py`: a text tagged with two genres is found by the **second** of them. A first-genre-only read must fail this test (FR-006, SC-001).
- [x] T016 [P] [US1] Write the order-then-truncate test in `tests/test_parse_scope.py`: the same corpus in two source orderings yields an identical list and an identical fingerprint; truncation applied before ordering must fail (FR-009, SC-002).
- [x] T017 [P] [US1] Write the never-tokenized test in `tests/test_parse_scope.py`: a text with structure but no unique wordforms produces **0** responses asserting the text has no words, and does not reuse `parse_scope_empty`'s wording (FR-002, SC-003).
- [x] T018 [P] [US1] Write the genre empty-collection contract test in `tests/test_parse_scope.py`, pinning that a text with no genres returns an empty collection and raises nothing. This read shipped untested and CP3 is its first consumer (FR-013).
- [x] T019 [P] [US1] Write the ambiguity test in `tests/test_parse_scope.py`: a genre string matching two genres refuses with `parse_scope_ambiguous` carrying **every** candidate (FR-007).
- [x] T020 [P] [US1] Write the fingerprint tests in `tests/test_parse_fingerprint.py`: exactly the eight fields of `data-model.md` section 3 are present, **nothing describing the grammar is present** (FR-011, D-3), and two runs differing only in `engine` are not comparable (FR-010).

### Implementation for User Story 1

- [x] T021 [US1] Implement scope resolution in `src/flextoolsmcp/server/parse/scope.py`: take the target word list from the data model's own unique-wordform enumeration, unioned across the selected texts exactly as the host application does. Do **not** build a corpus walk (FR-005).
- [x] T022 [US1] Implement genre matching in `src/flextoolsmcp/server/parse/scope.py`: case-insensitive against **both** genre name and abbreviation, reading the **full** genre collection on each text (FR-006, FR-007).
- [x] T023 [US1] Implement the ambiguity refusal in `src/flextoolsmcp/server/parse/scope.py`, emitting `parse_scope_ambiguous` with every candidate named (FR-007).
- [x] T024 [US1] Implement the no-match disclosure in `src/flextoolsmcp/server/parse/scope.py`: record in the response that matching ran against the **default analysis writing system**, so a localized-interface user sees a plausible reason rather than a bare assertion that no such genre exists (FR-008). This is a disclosed limitation, not a fix; a writing-system fallback is out of scope.
- [x] T025 [US1] Implement NFC de-duplication and ordering in `src/flextoolsmcp/server/parse/scope.py` -- descending occurrence count, then alphabetically -- and apply any caller limit **after** ordering, recording `truncated` on the response (FR-009).
- [x] T026 [US1] Implement the empty-vs-never-tokenized distinguishing read in `src/flextoolsmcp/server/parse/scope.py`: a structural count that is non-zero while the unique-word count is empty. Word the refusal conservatively and do **not** reuse `parse_scope_empty` for it (FR-002). Wording is finalized against T010's recorded FR-001 answer.
- [x] T027 [US1] Implement `ScopeFingerprint` in `src/flextoolsmcp/server/parse/fingerprint.py` with exactly the eight fields of `data-model.md` section 3: `scope_kind`, `scope_value`, `text_ids`, `word_count`, `limit`, `truncated`, `engine`, `vernacular_ws`. Grammar state is deliberately absent (FR-010, FR-011, D-3).
- [x] T028 [US1] Implement fingerprint comparison in `src/flextoolsmcp/server/parse/fingerprint.py`: differing fingerprints refuse with `parse_scope_mismatch` naming `differing_fields`, unless forced; a forced comparison runs on the **intersection only** and says so in its output (FR-012).
- [x] T029 [US1] Add the `Scope` / `ResolvedScope` input models to `src/flextoolsmcp/server/models.py` per `data-model.md` sections 1 and 2.
- [x] T030 [US1] Run the pattern-audit sweep for **first-element-only reads of a multi-valued LCM collection** (the FR-006 shape) across `src/flextoolsmcp/`, and record the sibling list (file:line + confidence) in this feature's review notes. A point fix on the genre read alone does not discharge the `lex-qc` gate.

**Checkpoint**: SC-001, SC-002, SC-003 green. A linguist can ask "how many distinct words are in this genre, and in what order" with no parse started.

---

## Phase 4: User Story 2 - "Parse my corpus, and don't lose the work if it dies" (Priority: P2)

**Goal**: run a batch over the resolved scope on the existing runner, and leave behind a durable artifact that other tools read without reopening the project.

**Independent Test**: run a batch to completion on a live project, then one killed mid-flight; confirm both leave a readable artifact, each stating its own terminal state.

**Plan mapping**: plan Phase 2's artifact half plus plan Phase 3's batch half. **The artifact is a forward commitment -- it is frozen at the end of this phase, before Phase 6 or Phase 7 consumes it.**

### Tests for User Story 2 ⚠️

- [x] T031 [P] [US2] Write the partial-stream test in `tests/test_parse_batch_artifact.py`: a run killed after its first completed word leaves 100% of completed words readable, and `iter_results` tolerates a malformed trailing line (FR-020, SC-004).
- [x] T032 [P] [US2] Write the retention test in `tests/test_parse_retention.py`: newest 20 runs per project by `created_at`; an implementation that sorts run-directory **names** must fail, and one that reuses `list_run_ids()`'s `st_mtime` order must fail (FR-022, R-03).
- [x] T033 [P] [US2] Write the counter tests in `tests/test_parse_counters.py`: the eight host names byte-exact from `contracts/tools.md` section 4; `counter_divergences` present **in the artifact**, not only in the spec (FR-017).
- [x] T034 [P] [US2] Extend `tests/test_parse_counters.py` so `TotalUserApprovedAnalysesMissing` computed over **all** human analyses **fails**, and only a fully-linked-only computation passes (FR-018).
- [x] T035 [P] [US2] Extend `tests/test_parse_counters.py` to assert `TotalUserNoOpinionAnalyses` is never presented, named or documented as a count of unreviewed analyses, and that the affirmed/indeterminate split rides beside it (FR-019).
- [x] T036 [US2] Extend `tests/test_parse_runner.py` (exists, CP2b) with the one-grammar-load assertion: a batch plus one interleaved single-word request loads the grammar exactly once (FR-027, SC-006), and the batch resumes at its next word with its position intact (SC-005).
- [x] T037 [P] [US2] Write the artifact-shape test in `tests/test_parse_batch_artifact.py` asserting sandbox-spine files are **not written and not created empty** (FR-015), and that no live data-model object reference is serialized anywhere in the artifact (FR-021).

### Implementation for User Story 2

- [x] T038 [US2] Add `words.txt` writing to `src/flextoolsmcp/server/parse/record.py` -- UTF-8, NFC, one word per line, in resolved order -- per `contracts/artifact.md` section 5. It is the only genuinely net-new file at CP3.
- [x] T039 [US2] Add the CP3 fields to `RunMeta` in `src/flextoolsmcp/server/parse/record.py`: `scope_fingerprint`, `engine_at_submission`, `engine_changed_midjob`, `load_error_baseline`, `counters`, `counter_divergences`, `words_path`. Keep every CP2b field unchanged and keep `run_id` as 32 lowercase hex -- **not re-minted** into a timestamped form (FR-016, FR-022, `contracts/artifact.md` sections 2-3).
- [x] T040 [US2] Implement `HostCounters` in `src/flextoolsmcp/server/parse/record.py` with the eight names verbatim, and emit `counter_divergences` into `meta.json` stating both deliberate divergences **in the artifact itself** (FR-017, FR-018, FR-019, R-09).
- [x] T041 [US2] Implement retention in `src/flextoolsmcp/server/parse/retention.py`: keep the newest 20 runs per project ordered by `meta.json`'s `created_at`. Adopt `server/backup.py`'s keep-newest-N **policy** and reject its name-sorting **mechanism**, which is sound only for timestamp-named directories (FR-022, R-03).
- [x] T042 [US2] Capture the grammar load-error baseline at CP3's own grammar load in `src/flextoolsmcp/server/parse/worker_main.py`, persist it in the run record, and key it to the scope fingerprint -- beside the fingerprint, never inside it (FR-023).
- [x] T043 [US2] Add batch submission to `src/flextoolsmcp/server/parse/runner.py` via `ParseQueue.enqueue_run(run_id, words, Priority.LOW)` -- the existing runner's lower-priority path at per-wordform granularity. **No second execution model** (FR-014, R-01).
- [x] T044 [US2] Place the parser-engine capability check as the **first statement** of the batch handler in `src/flextoolsmcp/server/handlers/parse.py`, before any parser is constructed, firing **once at submission**. An engine change mid-job sets `engine_changed_midjob` and surfaces as a **warning on the summary, not a refusal** (FR-024).
- [x] T045 [US2] Add the batch parse loop and structured-result extraction to `src/flextoolsmcp/server/parse/worker_main.py`, reading from the parser's **typed structured output, never its document form** (FR-035, R-11).
- [x] T046 [US2] Append per-word results as each word completes in `src/flextoolsmcp/server/parse/record.py`, keeping the existing per-line flush and `fsync` so the stream is valid up to its last complete record (FR-020).
- [x] T047 [US2] Make reported progress account for single-word requests interleaving ahead of the batch, in `src/flextoolsmcp/server/parse/runner.py`, so a batch does not appear to stall (FR-026).
- [x] T048 [US2] Hold at most one loaded grammar in `src/flextoolsmcp/server/parse/worker_main.py`, so an interleaving single-word request uses that same grammar and triggers no reload (FR-027).
- [x] T049 [US2] Add the `flextools_parse_text` input model to `src/flextoolsmcp/server/models.py` -- scope kind and value, optional word limit, optional project name. **The filing argument is absent from the schema** (FR-025, D-1).
- [x] T050 [US2] Register `flextools_parse_text` in `src/flextoolsmcp/server/tool_definitions.py` annotated `readOnlyHint=False, destructiveHint=True` -- at its designed maximum capability from its first release, **unchanged at CP4** -- with a description whose **first line** states the spine and that filing is not yet reachable (FR-025, D-1). Blocked on T006's maintainer decision.
- [x] T051 [US2] Route `flextools_parse_text` in `src/flextoolsmcp/server/dispatch.py`.
- [x] T052 [US2] Run the pattern-audit sweep for **name-sorted directory retention** (the R-03 shape) across `src/flextoolsmcp/`, asking where else the tree sorts opaque directory names as if they were chronological, and record the sibling list in this feature's review notes.
- [x] T053 [US2] Reconcile `specs/parser-check-cp3/contracts/artifact.md` against the shipped `record.py` and **freeze** the artifact contract. Nothing in Phase 6 or Phase 7 may consume it before this task closes.

**Checkpoint**: SC-004, SC-005, SC-006 green, including a live kill-mid-batch leaving every completed word readable. The artifact is frozen.

---

## Phase 5: User Story 3 - "Show me what happened" (Priority: P3)

**Goal**: read a finished or failed run back, with sandbox-spine sections explicitly not-applicable rather than silently empty.

**Independent Test**: read every section of a completed in-process run and confirm each returns either real content or an explicit not-applicable naming its spine.

### Tests for User Story 3 ⚠️

- [x] T054 [P] [US3] Write `tests/test_parse_log_sections.py` asserting the seven section names exactly -- `summary | config_generation | hc_stdout | hc_output | trace | words | results` -- and that **0 sections return empty content** (FR-028, SC-007).
- [x] T055 [P] [US3] Extend `tests/test_parse_log_sections.py` so each of `config_generation`, `hc_stdout`, `hc_output` returns a typed not-applicable response **naming the spine and the checkpoint that will fill it** (FR-028).
- [x] T056 [P] [US3] Extend `tests/test_parse_log_sections.py` so an unparseable trace returns the **raw slice explicitly labelled raw**, with no invented explanation (FR-029).
- [x] T057 [P] [US3] Assert in `tests/test_parse_log_sections.py` that the log tool never calls the parser-engine capability check -- it reads prior artifacts and never touches the engine (FR-024).

### Implementation for User Story 3

- [x] T058 [US3] Implement the `flextools_parse_log` handler in `src/flextoolsmcp/server/handlers/parse.py`, serving `summary`, `words`, `results` and `trace` with real, paged content for in-process runs (FR-028).
- [x] T059 [US3] Implement the typed not-applicable-for-this-spine response for `config_generation`, `hc_stdout` and `hc_output` in `src/flextoolsmcp/server/handlers/parse.py`, naming the spine and the checkpoint that will fill it. Never return an empty section -- an empty section reads as "nothing happened" (FR-028).
- [x] T060 [US3] Implement one-line blocking rule/stage naming for a parseable trace, and the raw-and-labelled fallback for one that is not, in `src/flextoolsmcp/server/handlers/parse.py` (FR-029).
- [x] T061 [US3] Add the `flextools_parse_log` input model to `src/flextoolsmcp/server/models.py`, register it in `src/flextoolsmcp/server/tool_definitions.py`, and route it in `src/flextoolsmcp/server/dispatch.py`.

**Checkpoint**: SC-007 green. Every section of a run is readable or explicitly inapplicable.

---

## Phase 6: User Story 4 - "Did my grammar edit help?" (Priority: P4)

**Goal**: compare two runs and say which words newly parse, which stopped, which parse differently, and which are unchanged.

**Independent Test**: baseline parse, deliberate grammar break, diff, revert, diff again, on a live project; confirm the two diffs name the right words in the right buckets.

**Depends on**: US2's frozen artifact (T053) and US1's fingerprint (T027).

### Tests for User Story 4 ⚠️

- [ ] T062 [P] [US4] Write the changed-not-unchanged test in `tests/test_parse_diff.py`: a word going from one analysis to seven is classified `changed`. **A count-equality implementation must fail this assertion** (FR-030, SC-008).
- [ ] T063 [P] [US4] Write the identity-change test in `tests/test_parse_signature.py`: identical rendered forms under differing identifiers is an identity change -- reported as behavioural change **0 times**, and never collapsed to unchanged (FR-032, SC-010).
- [ ] T064 [P] [US4] Write the signature-fallback test in `tests/test_parse_signature.py`, exercising the rendered-form-plus-category fallback **by fixture**, whatever live verification finds, and asserting the resulting ambiguity is stated in the report (FR-033).
- [ ] T065 [P] [US4] Write the shared-mode test in `tests/test_parse_diff.py`: `probe_project_access` reporting `open_shared` or `open_exclusive` yields `staleness: "shared_mode_unverifiable"`, the save-or-close note, and `no_change` downgraded to `no_change_unverifiable`. Assert **no safe read-back interval is promised anywhere** (FR-034, R-06).
- [ ] T066 [P] [US4] Write the provisional-match test in `tests/test_parse_signature.py`: an analysis carrying `has_guessed_form` compares as **provisional**, never as asserted behavioural identity (FR-031a).

### Implementation for User Story 4

- [ ] T067 [US4] Implement `DurableAnalysisSignature` in `src/flextoolsmcp/server/parse/signature.py` as the ordered sequence of (morph-form id, morph-syntax-analysis id, **inflection-type id**) triples, with `rendered_morphs` and `category_labels` carried alongside so a report renders without reopening the project (FR-031, D-2). The inflection-type component is not optional: a two-component signature collapses analyses that genuinely differ.
- [ ] T068 [US4] Record `has_guessed_form` per analysis in `src/flextoolsmcp/server/parse/signature.py` and surface it as a **provisional** comparison result. The host predicate's fourth component -- a writing-system-alternative match on a guessed surface form -- has no serialized equivalent, and dropping it silently would claim an alignment the signature does not reproduce (FR-031a).
- [ ] T069 [US4] Implement the FR-033 fallback in `src/flextoolsmcp/server/parse/signature.py`, wired behind the live identifier-stability verification, stating the resulting ambiguity in the report.
- [ ] T070 [US4] Implement the comparison in `src/flextoolsmcp/server/parse/diff.py` with buckets exactly `fixed | broken | changed | unchanged`, classified on **signature sets**, never on counts (FR-030).
- [ ] T071 [US4] Implement identity-change labelling in `src/flextoolsmcp/server/parse/diff.py` -- identical rendered forms, differing identifiers -- as neither behavioural change nor unchanged (FR-032).
- [ ] T072 [US4] Implement the shared-mode downgrade in `src/flextoolsmcp/server/parse/diff.py` over `project_access.probe_project_access`, carrying the staleness marker verbatim and promising no read-back interval (FR-034, R-06).
- [ ] T073 [US4] Wire the fingerprint-mismatch refusal and the forced-intersection path into `src/flextoolsmcp/server/parse/diff.py`, emitting `parse_scope_mismatch` with `differing_fields` and stating in the output when a forced comparison ran on the intersection (FR-012).
- [ ] T074 [US4] Add the `flextools_parse_diff` input model to `src/flextoolsmcp/server/models.py`, register it in `src/flextoolsmcp/server/tool_definitions.py`, and route it in `src/flextoolsmcp/server/dispatch.py`. Assert it never calls the engine check (FR-024).

**Checkpoint**: SC-008, SC-009, SC-010 green, including a live break-then-revert cycle.

---

## Phase 7: User Story 5 - "Which of these analyses are wrong, and why?" (Priority: P5)

**Goal**: show where the grammar is producing too much, each signal printed beside the legitimate reason it might be a false alarm, with human analyses used as an oracle only where they are actually comparable.

**Independent Test**: run the batch report against fixtures covering every completeness tier and every stated false-positive case, and assert the exact wording of every mandated sentence.

**Ordered by risk, not by requirement number** (plan Phase 5). T075 is this phase's gate, not one of its assertions. The net-new attribution piece is scheduled last so it is not on the critical path of the other seven.

### Tests for User Story 5 ⚠️

- [ ] T075 [US5] **Write SC-014's ranking fixture in `tests/test_signals_ranking.py` FIRST, and confirm it is RED before `ranking.py` exists.** A non-compositional word whose correct analysis disagrees with the human gloss must rank above a compositional-but-wrong competitor, and **a sort-by-gloss-distance implementation must fail** (FR-045, SC-014, R-10). This is the single most important regression test in CP3.
- [ ] T076 [P] [US5] Write `tests/test_signals_oracle_wording.py` asserting all six mandated sentences from `contracts/tools.md` section 3 render **byte-exact**, never paraphrased (FR-040, SC-011).
- [ ] T077 [P] [US5] Extend `tests/test_signals_oracle_wording.py` with a forbidden-word scan over **every emitted response**: "invalid", "incorrect", "rejected", "flagged" appear 0 times in connection with an analysis carrying no stored opinion (FR-040, SC-011).
- [ ] T078 [P] [US5] Extend `tests/test_signals_oracle_wording.py` to assert 0 individual analyses are labelled `tacit`, `unreviewed` or `auto_approved` across all outputs, and that the split is exactly `{affirmed, indeterminate}` and never `{affirmed, tacit}` (FR-042, SC-012).
- [ ] T079 [P] [US5] Extend `tests/test_signals_oracle_wording.py` with an **offline fixture** -- not live-only -- for a project the parser has never run against: the oracle is reported **absent** with its own sentence, and degenerate all-unreviewed reports are emitted 0 times (FR-041, SC-013).
- [ ] T080 [P] [US5] Write `tests/test_signals_tiers.py` covering all four tiers (`none`, `meaning_only`, `sketched`, `fully_linked`), asserting tiers derive from the public per-bundle completeness flag plus the bundle count and that the host's internal fully-formed predicate is **not** reimplemented (FR-038).
- [ ] T081 [P] [US5] Write `tests/test_signals_batch_signals.py` asserting all five signals ship and each prints its false-positive explanation **in the output**, not in documentation (FR-036).
- [ ] T082 [P] [US5] Extend `tests/test_signals_batch_signals.py` to assert the count distribution is presented as a comparison instrument -- **0 severity values, 0 verdict wording, 0 scalar scores** (FR-037).
- [ ] T083 [P] [US5] Write `tests/test_signals_pairing.py` asserting a candidate pairing is ranked first, names its confidence basis, is worded as a suggestion, and is **never filed** (FR-044).
- [ ] T084 [P] [US5] Extend `tests/test_signals_pairing.py` asserting a derivable word whose parts do not add up to its recorded meaning is reported as a **candidate lexicalized form** using the mandated wording, not as a parse error (FR-046).
- [ ] T085 [P] [US5] Write `tests/test_signals_clustering.py` asserting clustering by shared root entry first and category pair otherwise, representatives capped at three, the drill-down cap honoured within 10-20, and **0 bulk auto-traces** regardless of how many words look suspect (FR-047, FR-048, SC-016, D-5).
- [ ] T086 [P] [US5] Write `tests/test_signals_projections.py`: the deletion projection over a fixture holding one segment-referenced and one unreferenced candidate returns **exactly one**; **a bare no-opinion projection returns two and must fail** (FR-050, SC-015).
- [ ] T087 [P] [US5] Extend `tests/test_signals_projections.py` for the duplicate projection, and assert **no part of the write ladder ships** -- no confirmation, no filing path (FR-050).
- [ ] T088 [P] [US5] Write `tests/test_signals_attribution.py` asserting attribution is a side-by-side comparison of competing rule chains, and that the engine's pre-parse morph filter is **not** used as an attribution mechanism -- only to narrow a candidate set by subtraction (FR-049).

### Implementation for User Story 5

- [ ] T089 [US5] Implement completeness tiering in `src/flextoolsmcp/server/signals/tiers.py` from the public per-bundle completeness flag plus the bundle count (FR-038).
- [ ] T090 [US5] Implement the oracle in `src/flextoolsmcp/server/signals/oracle.py`: the six verbatim sentences transcribed from `contracts/tools.md` section 3, the absent case (FR-041), and the affirmed/indeterminate split. Only **fully linked** human analyses enter the approval comparison; meaning-only and partially linked analyses are reported separately **and by name**, never folded into a count, never dropped, never rendered as disagreement with the parser (FR-039, FR-040, FR-042).
- [ ] T091 [US5] Implement the segment-occurrence join in `src/flextoolsmcp/server/signals/oracle.py`, **built once and structured for reuse** -- CP4's deletion projection is the same join for the opposite purpose, and a CP4 that rebuilds it is a review finding (FR-043). Add the one-line unguarded-`.Owner`-on-base-`ICmObject` check here, where the traversal actually exists.
- [ ] T092 [US5] Implement the one-sided approval-provenance join in `src/flextoolsmcp/server/signals/oracle.py`: approved and not occurring in any segment is reliably affirmed; approved and occurring in a segment is unknowable (FR-042).
- [ ] T093 [US5] Implement promotion-only ranking in `src/flextoolsmcp/server/signals/ranking.py` against T075's now-red fixture: gloss agreement **raises** an analysis, disagreement **never lowers** one, and everything not promoted keeps its original order. An implementation that sorts by gloss distance is wrong (FR-045).
- [ ] T094 [US5] Implement candidate pairing in `src/flextoolsmcp/server/signals/pairing.py` -- one parser analysis meeting one human meaning-only record -- surfaced, ranked first, confidence basis named, worded as a suggestion, and **never filed automatically** (FR-044).
- [ ] T095 [US5] Implement the lexicalization finding in `src/flextoolsmcp/server/signals/pairing.py` using the mandated wording (FR-046).
- [ ] T096 [US5] Implement the five batch signals in `src/flextoolsmcp/server/signals/batch_signals.py` -- analyses per word; disagreement over which root entry a word belongs to; a root analysed as a stack of affixes; the same surface form in incompatible categories; the distribution of analysis counts -- each carrying its `false_positive_note` **printed in the output**. Computed from the parser's typed structured output, never from its document form (FR-035, FR-036, FR-037, R-11).
- [ ] T097 [US5] Implement clustering in `src/flextoolsmcp/server/signals/clustering.py`: key on shared root entry first, category pair otherwise; representatives by highest analysis count, ties broken by the word list's existing order, **capped at three**; state the heuristic in the output (FR-048, D-5).
- [ ] T098 [US5] Implement the drill-down cap in `src/flextoolsmcp/server/handlers/parse.py`: a user-chosen figure in the range 10-20 per session, **never auto-traced in bulk** (FR-047).
- [ ] T099 [US5] Implement side-by-side rule-chain attribution in `src/flextoolsmcp/server/signals/attribution.py` -- the net-new piece. The engine's pre-parse morph filter is **not** an attribution mechanism; its only legitimate use here is narrowing a candidate set by subtraction (FR-049).
- [ ] T100 [US5] Implement both projections in `src/flextoolsmcp/server/signals/projections.py`: deletion (parser-created **and** carrying no user opinion **and** not referenced by any segment -- all three conjuncts) and duplicate. Computed, reported as information, **acted on by nothing**; no confirmation and no part of the write ladder (FR-050).

**Checkpoint**: SC-011..SC-016 green. SC-014 is this phase's gate.

---

## Phase 8: User Story 6 - "This is taking forever -- is my grammar broken?" (Priority: P6)

**Goal**: spend one word finding out whether the grammar is the problem, and route the user to the cheap static scan.

**Independent Test**: run the bounded measurement against a known-slow grammar and a known-fast one; confirm one produces a terminal measured result and the other triggers no proposal.

### Tests for User Story 6 ⚠️

- [ ] T101 [P] [US6] Write `tests/test_parse_measure.py` asserting a measurement terminated at its bound is reported as a terminal **result** carrying a wall-clock measurement, not an error, and reports **0 invented engine step or node counts** (FR-053, FR-054, SC-017).
- [ ] T102 [P] [US6] Extend `tests/test_parse_measure.py` asserting the measurement runs in its own worker and never shares one with a batch -- terminating it must not take a running batch with it (FR-051, R-05).
- [ ] T103 [P] [US6] Extend `tests/test_parse_proposal.py` (exists, CP2b): a request answered inside the fast-path window carries **0** grammar-scan proposals; one that misses it carries **exactly one** (FR-056, SC-018).
- [ ] T104 [P] [US6] Extend `tests/test_parse_proposal.py` asserting that across every response the feature can emit, proposals name a nonexistent tool **0 times** and omit a cost estimate **0 times**, and that no proposal names a filing step -- unreachable at CP3 in every session (FR-057, SC-019).
- [ ] T105 [P] [US6] Extend `tests/test_parse_proposal.py` asserting the static scan is proposed **before** the trace where both are candidates (FR-057).

### Implementation for User Story 6

- [ ] T106 [US6] Add a second `ParseWorkerPool` key for the bounded measurement in `src/flextoolsmcp/server/parse/worker_client.py`, so a measurement on a project with a running batch does not land in the batch's worker (FR-051, R-05). The pool is keyed by project name today; this is a real, small change, not a call-site choice.
- [ ] T107 [US6] Implement the bounded measurement in `src/flextoolsmcp/server/parse/measure.py`, running as its own job at the runner's highest word priority, with the fields of `data-model.md` section 15 (FR-051).
- [ ] T108 [US6] Enforce the bound at **process level** in `src/flextoolsmcp/server/parse/measure.py` via `subprocess_helpers._kill_process_tree`. Claim no in-parse enforcement: the engine offers no cancellation token, timeout or step budget, and cooperative cancellation lands at the next word boundary, which for a one-word parse is after the parse being bounded (FR-052, D-4, R-05).
- [ ] T109 [US6] Report wall-clock elapsed time plus whether the fast-path window was missed and by how much, in `src/flextoolsmcp/server/parse/measure.py`. Report no engine step or node count -- no such number exists (FR-053).
- [ ] T110 [US6] Report a bound-terminated measurement as `outcome: "terminated_at_bound"` -- a terminal **result**, not an error (FR-054).
- [ ] T111 [US6] Read and report the stored parser parameters as context for a slow parse in `src/flextoolsmcp/server/parse/measure.py`. **Never write them** -- that is a project-data write and this checkpoint has none (FR-055).
- [ ] T112 [US6] Implement the four proposal trigger conditions in `src/flextoolsmcp/server/handlers/parse.py` -- a single-word request that misses the fast-path window; a batch that enters grammar loading and stays there; a terminal failure; a bounded measurement that exceeds its bound. Never on a request answered inline, and never attached to every response (FR-056).
- [ ] T113 [US6] Give every proposal a mandatory `cost_estimate` (where `"unbounded"` is legitimate) and directly usable `arguments` needing no reconstruction, in `src/flextoolsmcp/server/handlers/parse.py`. Propose the static scan before the trace where both are candidates; never propose a step the project cannot reach, including any filing step (FR-057).
- [ ] T114 [US6] Revisit every next-step row left pointing at a null tool because the tool did not yet exist, for the three tools CP3 ships: `runner.py`'s `_FAILURE_NEXT_STEP` and `handlers/parse.py`'s `_status_next_step` are the two revisit sites. None may still be null for a shipped tool (FR-058, R-07).

**Checkpoint**: SC-017, SC-018, SC-019 green.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: plan Phase 7 -- the contract, the standing guarantees, the pattern audit the `lex-qc` gate blocks on, the corrections CP3 owes the parent spec, and live verification.

- [ ] T115 Add five rows to the table in `docs/TOOL-CONTRACT.md` for the new codes, raising the documented code count **25 -> 30**, with the field lists transcribed from `contracts/tools.md` section 2 (FR-059, FR-060).
- [ ] T116 Add one changelog entry under the tool-contract heading in `docs/CHANGELOG.md`, stating the additive change and that `tool-responses/1.0` is unchanged (FR-059).
- [ ] T117 Write the standing no-write test `tests/test_parse_no_project_writes.py`: no code path shipped by CP3 writes to a FieldWorks project -- 0 occurrences, asserted by test rather than by inspection (FR-063, SC-021). This is the gate the checkpoint cannot ship without.
- [ ] T118 Write the standing no-blocking regression `tests/test_parse_no_edit_blocking.py`: a running parse job blocks a concurrent lexicon edit or human-analysis write **0 times**, and no project-wide claim is introduced (FR-061, SC-020).
- [ ] T119 Run the pattern-audit sweep for **multistring / `ITsString` field access** (the standing #36/#39/#40 class) across the sites CP3 adds: genre name and abbreviation reads and `vernacular_ws` in `src/flextoolsmcp/server/parse/scope.py`, and `rendered_morphs` / `category_labels` in `src/flextoolsmcp/server/parse/signature.py`. Record the sibling list in this feature's review notes.
- [ ] T120 Re-probe the three grammar lints deferred at CP1 and again at CP2: fold them into `src/flextoolsmcp/server/scan/grammar_scan_module.py` if the host library exposes its checker publicly, **or** record the continued deferral with a reason in `specs/parser-check/SPEC.md`. A third silent move is drift (FR-062).
- [ ] T121 Correct the file listing in `specs/parser-check/SPEC.md` section 5.5 to match the shipped artifact layout -- `meta.json`, `results.jsonl`, `words.txt`, `traces/<n>.xml` -- rather than `run.json`, a flat `trace.txt` and four sandbox files. The listing is the thing that is wrong; CP3 corrects it rather than renaming shipped files an artifact two checkpoints read (D-6).
- [ ] T122 [P] Run live Scenario 1-3 from `specs/parser-check-cp3/quickstart.md` on `IndonesianHC-Complete`, capturing pre/post evidence with the same discipline a write path would get -- the identifier-stability and shared-mode facts this plan rests on are live-only.
- [ ] T123 [P] Run live Scenario 4-6 from `specs/parser-check-cp3/quickstart.md` on `IndonesianHC-Complete`, including the break-then-revert cycle (SC-009) and the kill-mid-batch (SC-004).
- [ ] T124 Run the scale scenarios from `specs/parser-check-cp3/quickstart.md` on `Malay Parsing-20230810withHC`. Do not substitute `Sena 3` -- it reports engine `XAmple` and this feature's own gate refuses it (SC-022).
- [ ] T125 Confirm identifier stability across sessions from T122's evidence and record the verdict in `specs/parser-check-cp3/research.md`'s open-items table. If disproved, activate the FR-033 fallback in `src/flextoolsmcp/server/parse/signature.py` wired at T069 and state the resulting ambiguity in the report.
- [ ] T126 Run the full suite `pytest tests/ -q` and confirm green including CP1's and CP2's standing groups, `HCParser_DoesNotLoadXCore`, and the floor/index equality test unweakened (SC-022).

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies.
- **Phase 2 (Foundational)**: depends on Phase 1. T007 and T012 **block every user story**. T008-T011 gate wording only and may run alongside Phase 3 (R-08).
- **Phase 3 (US1)**: depends on Phase 2.
- **Phase 4 (US2)**: depends on US1's fingerprint (T027) and scope resolution (T021-T026).
- **Phase 5 (US3)**: depends on US2's artifact existing (T038-T046). Independently testable once a run record exists.
- **Phase 6 (US4)**: depends on the **frozen** artifact (T053) and the fingerprint (T027-T028).
- **Phase 7 (US5)**: depends on the frozen artifact (T053) and US2's structured-result extraction (T045).
- **Phase 8 (US6)**: depends only on the runner (T043) and the worker pool. Independent of US4 and US5.
- **Phase 9 (Polish)**: depends on all stories.

### Story dependencies

- **US1 (P1)**: the only story with standalone value before any parse exists. MVP.
- **US2 (P2)**: needs US1's resolved scope and fingerprint.
- **US3 (P3)**: needs US2's artifact. Smallest story.
- **US4 (P4)**: needs US2's artifact and US1's fingerprint.
- **US5 (P5)**: needs US2's artifact. Largest story -- larger than everything else combined.
- **US6 (P6)**: needs the runner only. Can proceed in parallel with US4 and US5.

### Hard ordering constraints

1. **T053 freezes the artifact.** Neither Phase 6 nor Phase 7 may consume it before T053 closes. CP4 and CP5 both read it, so a shape chosen loosely is migrated twice later.
2. **T075 is written red before T093 exists.** This is not a general test-first preference; the wrong ranking implementation is shorter than the correct one and confidently wrong about exactly the words a linguist cares most about.
3. **T006 (D-1 maintainer decision) blocks T050.** Overturning it before implementation costs nothing; after CP3 ships it costs the caller-visible contract event D-1 exists to avoid.
4. **T010 finalizes the wording in T026 and one sentence in T090.** Neither blocks the surrounding build.
5. **T099 (attribution) is scheduled last within US5** so the net-new piece is not on the critical path of the other seven.

### Parallel opportunities

- T003, T004, T005 in Setup.
- T008, T009, T011 in Foundational (T012 touches `response_models.py` alone and is not parallel with T013/T014).
- All of T015-T020 (US1 tests) -- two files, no implementation yet.
- T031-T035 and T037 (US2 tests) -- distinct test files.
- T054-T057 (US3 tests) share one file and must be sequenced; they are marked [P] only against other phases' work.
- T062-T066 (US4 tests) across two files.
- T076-T088 (US5 tests) across seven files, after T075.
- T101-T105 (US6 tests) across two files.
- US6 (Phase 8) may run fully in parallel with US4 and US5.

---

## Parallel Example: User Story 1

```bash
# Launch the US1 test tasks together (all red before implementation):
Task: "Two-genre regression in tests/test_parse_scope.py"           # T015
Task: "Order-then-truncate test in tests/test_parse_scope.py"       # T016
Task: "Never-tokenized test in tests/test_parse_scope.py"           # T017
Task: "Genre empty-collection contract in tests/test_parse_scope.py"# T018
Task: "Ambiguity refusal test in tests/test_parse_scope.py"         # T019
Task: "Seven-field fingerprint tests in tests/test_parse_fingerprint.py" # T020
```

---

## Implementation Strategy

### MVP first (User Story 1 only)

1. Phase 1 Setup -- confirm the entry gate is closed.
2. Phase 2 Foundational -- the one probe, the five codes.
3. Phase 3 US1 -- scope, genres, ordering, fingerprint.
4. **Stop and validate**: SC-001, SC-002, SC-003 green. A linguist can ask "how many distinct words are in this genre, and in what order of frequency" with no parse started -- useful on its own.

### Incremental delivery

1. Setup + Foundational -> the probe exists once and the codes are pinned.
2. + US1 -> scope answers a real question. **MVP.**
3. + US2 -> the batch runs and the artifact is frozen. This is the forward commitment CP4 and CP5 read.
4. + US3 -> the artifact is readable.
5. + US4 -> the edit-then-compare loop the feature exists to enable.
6. + US5 -> the diagnosis. Largest and most correctness-sensitive.
7. + US6 -> the bounded measurement and routing.
8. + Polish -> contract rows, standing tests, sweeps, the parent-spec corrections, live verification.

### Parallel team strategy

After Phase 2, and after T053 freezes the artifact:

- Developer A: US4 (comparison) -- `parse/signature.py`, `parse/diff.py`
- Developer B: US5 (signals) -- the whole `server/signals/` package, starting with T075 red
- Developer C: US6 (measurement) -- `parse/measure.py`, `parse/worker_client.py`, proposals

US5 is larger than A and C combined; staff it accordingly or sequence it after US4.

---

## Notes

- **CP3 is entirely read-only.** T117's standing test is the gate the checkpoint cannot ship without, and "no write path" is a claim asserted by test rather than discharged by skipping a gate.
- `tests/test_parse_runner.py` and `tests/test_parse_proposal.py` already exist (CP2b). T036, T103, T104 and T105 **extend** them; they are not created.
- `src/flextoolsmcp/server/parse/queue.py`, `priority.py` and `stages.py` are **unchanged**. The `filing` stage stays inbound-edgeless. A structural runner need is an **escalation**, not an absorbable task (FR-014).
- `parser_probe.py` stays at zero lines changed, as CP2a and CP2b both held.
- Five tests are written so the *wrong* implementation fails rather than merely disagreeing: T032 (name-sorted retention), T034 (all-analyses counter), T062 (count-equality diff), T075 (sort-by-gloss-distance ranking), T086 (bare no-opinion projection). That property is what makes them worth the lines.
- Commit after each task or logical group. Stop at any checkpoint to validate a story independently.
