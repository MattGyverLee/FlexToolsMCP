# Tasks: parser-check CP4 -- ParseFiler, the write ladder, and the first mutation

**Input**: [`plan.md`](./plan.md), [`spec.md`](./spec.md) (authoritative, clarified 2026-09-23), [`research.md`](./research.md), [`data-model.md`](./data-model.md), [`contracts/tools.md`](./contracts/tools.md), [`quickstart.md`](./quickstart.md)

**Worktree**: `C:\Github\FlexToolsMCP-cp4`, branch `feat/parser-check-cp4`. All paths below are relative to it.

**Size**: `oversized` -- full phased list.

**Tests**: required. The constitution (Principle I, write path) and the plan's test strategy name a test for every FR. Where the plan marks a test as a *tripwire* or says "red first", the test task comes before its implementation task and MUST be observed failing before the implementation lands.

**Line format**: `- [ ] **T###** [P?] [US#] Description · file`

**Story order note.** The spec's priority order is US1, US2, US3 (all P1), then US4, US5 (P2), then US6 (P3). US2 (filing) cannot run without US3's gate (FR-024: the gate re-runs on every reload inside the filing worker), so US3 comes before US2 here. The claim *registry* that US2's ladder needs (contracts section 1, rows 2 and 14) is Foundational. US4 keeps the concurrency behaviour built on it. US5 (live proof) is last, because it exercises everything.

**Six wrong-implementation tripwires** (plan, Test strategy). Each is a named task below and must survive review unchanged: R-01 trap (T030), FR-039 silent drop (T040), FR-019 declined-then-next-word (T055), FR-006 foreign `plan_id` (T032), FR-002 locked-and-unconfirmed (T050), SC-008 `require_write_confirmation=false` (T014).

---

## Phase 1: Setup -- the live questions that can move the design (plan Phase 1)

**Purpose**: answer R-10 (L-0) and R-13 (Q2, Q3, Q5) on disposable copies before the ladder walk (Phase 5 / US2) merges. Every run is on a `CP4-Scratch-` copy (FR-037) with evidence under `evidence/`. Unattended live writes stop as `needs_human` (constitution I).

**Wave 1 -- independent (different files):**

- [x] **T001** [P] Create the disposable-copy helper: copy a named project to `CP4-Scratch-<name>-<stamp>`, tear it down afterwards, and refuse any target without the `CP4-Scratch-` prefix (FR-037). Nothing is ever written inside a real project folder (FR-042) · `tests/live_support/make_disposable.py`
- [x] **T002** [P] Create the `evidence/` directory with a README naming the expected artifacts (`l0-coexistence.json`, `q2-agent.json`, `q3-staleness.json`, `q5-checksum.json`, the five FR-036 cases, and Q1/Q4), following the CP2/CP3 naming precedent · `specs/parser-check-cp4/evidence/README.md`

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 -- live probes (one evidence file each; a human must be present):**

- [x] **T003** [P] Run L-0 (quickstart "L-0"): two processes on one **non-shared** disposable project, a writable open alongside a read-only open, including the root cause of the read worker's save (memory `parse-worker-saves-xample-project`). Record the verdict and the root cause · `specs/parser-check-cp4/evidence/l0-coexistence.json`
- [x] **T004** [P] Run Q2 (the HermitCrab agent is present and resolvable by GUID), Q3 (does a filed word mark the grammar stale, R-05), and Q5 (checksum parity across processes). Record each · `specs/parser-check-cp4/evidence/q2-agent.json`, `q3-staleness.json`, `q5-checksum.json`

**⟶ Wait for Wave 2 to finish, then:**

- [x] **T005** Settle M-1 from T003. If L-0 passes, drop R-10's interim read refusal and record that FR-027 holds everywhere. If L-0 fails, **stop as `needs_human`** (plan, M-1); do not downgrade. Write Q2's finding into parent section 17.10 · `specs/parser-check-cp4/research.md` (R-10 outcome), `specs/parser-check/SPEC.md` (17.10)

**Checkpoint**: `evidence/l0-coexistence.json` exists, M-1 is settled or escalated, and Q2, Q3 and Q5 are recorded.

---

## Phase 2: Foundational -- ladder extraction, contract, surface, package skeleton (plan Phases 2 and 3)

**Purpose**: the shared infrastructure every story needs. No story work starts until this phase is done.

### 2a. Extract the write ladder (FR-002, R-07). No behaviour change.

- [x] **T006** Write the extraction test: the ladder leaves (`probe_write_access`, `backup_intent`, `take_backup`) are patched and each is called exactly once from `handle_run_module`; an AST check finds no `probe_project_access` call outside `write_ladder.py` and its own module. Red until T007 · `tests/test_write_ladder_extraction.py`

**⟶ Wait, then:**

- [x] **T007** Extract the inline rungs from `handle_run_module` (`execution.py:~4480-4710` at `2aedb1d`) into `probe_write_access`, `backup_intent` and `take_backup`, moved, not copied · `src/flextoolsmcp/server/write_ladder.py`

**⟶ Wait, then:**

- [x] **T008** Rewrite `handle_run_module` to call the extracted rungs. Exit gate: `test_issue55_write_safety_ladder.py`, `test_shared_mode_*.py`, `test_issue92_write_path_e2e.py` and `test_async_locking.py` pass **with no modification**, and the `confirmation_required` and `project_locked` golden responses are byte-identical · `src/flextoolsmcp/server/handlers/execution.py`

### 2b. Contract and surface (FR-001, FR-004, FR-035). This can start alongside 2a.

**Wave 1 -- independent (different files):**

- [x] **T009** [P] Add `ParserFilingInProgressDetail` and `GrammarLoadUncleanDetail`, with fields in the exact order of contracts section 2. The four appended `grammar_load_unclean` fields come after the parent's five, and `eligible_forms_dropped` is added to `signal`. Use `ConfigDict(extra="forbid", populate_by_name=True)` and a `Literal` `error_code`, append both to `AnyDetail`, and give `baseline_source` the pattern `^(this_run|absent|prior_run:[0-9a-f]{32})$` · `src/flextoolsmcp/server/response_models.py`
- [x] **T010** [P] Add `apply`, `confirmed` and `plan_id` (64 lowercase hex) to `ParseTextInput`, with `confirmed`/`plan_id` rejected without `apply` (contracts row 0). Add `ParseCancelInput(run_id)` · `src/flextoolsmcp/server/models.py`
- [x] **T011** [P] Add two code rows and raise the documented count by exactly 2, taking the count from the live file (it was 32) · `docs/TOOL-CONTRACT.md`
- [x] **T012** [P] Add golden fixtures for the two new codes · `tests/golden/responses/parser_filing_in_progress.json`, `tests/golden/responses/grammar_load_unclean.json`
- [x] **T013** [P] Add one entry under "Tool contract": the two codes, the enum value, the four appended fields, the three arguments, `flextools_parse_cancel` and the `deletions` parse_log section · `CHANGELOG.md`
- [x] **T014** [P] **Tripwire (SC-008).** Write the bypass-surface test **before the handler exists**. It enumerates the `parse_text` input schema and every config key, and fails on any name matching `write|backup|force|override|skip|bypass|unattended|auto_confirm` other than `apply`, `confirmed` and `plan_id`. It also asserts that with `require_write_confirmation=false` set through `flextools_manage_config`, a filing request **still** returns `confirmation_required` (FR-004; that assertion stays red until T037) · `tests/test_filing_bypass_surface.py`

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 -- independent (different files):**

- [x] **T015** [P] Change the first line of the `parse_text` description to the contracts section 1 text, leaving the annotations unchanged. Add the `flextools_parse_cancel` ToolDef (`readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False`) (M-3 default: a new tool) · `src/flextoolsmcp/server/tool_definitions.py`
- [x] **T016** [P] Add the `flextools_parse_cancel` route · `src/flextoolsmcp/server/dispatch.py`
- [x] **T017** [P] Update the contract tests: the count +2, and field-order rows for both detail models equal to contracts section 2 (FR-035) · `tests/test_response_contract.py`, `tests/test_parser_error_models.py`
- [x] **T018** [P] Make the R-16 updates to the existing handler test: the schema has the three fields; the new first line; `apply=false` responses are diffed against the CP3 golden and equal apart from `filing: "not_requested"`; annotations are pinned (FR-001) · `tests/test_parse_text_handler.py`

**⟶ Wait for Wave 2 to finish, then:**

- [x] **T019** Implement `handle_flextools_parse_cancel` over `ParseRunner.cancel_run` (`runner.py:810`): an unknown run gives `parse_run_not_found`; a terminal run gives `parse_job_cancelled`; otherwise `{run_id, cancel_requested: true}`. It works on read-only runs too. Make the `apply=false` path emit `filing: "not_requested"` · `src/flextoolsmcp/server/handlers/parse.py`

### 2c. The filing package skeleton, claims, session state and worker role

**Wave 1 -- independent (different files):**

- [x] **T020** [P] Create the `filing` package with a docstring stating that it is the **only** write spine (FR-029) · `src/flextoolsmcp/server/filing/__init__.py`
- [x] **T021** [P] Build the in-process per-project claim registry (acquire, release, lookup returning `run_id`/`started_at`/`words_completed`) and a startup sweep (data-model section 6, R-11). It takes no project-wide lock (FR-027) · `src/flextoolsmcp/server/filing/claims.py`
- [x] **T022** [P] Add `filing_plans` (`plan_id` -> plan) and `filing_backed_up_projects`, a separate key from `run_module`'s (FR-008) · `src/flextoolsmcp/server/session.py`
- [x] **T023** [P] Add `FILING_ROLE` beside `SHARED_ROLE`/`MEASUREMENT_ROLE` · `src/flextoolsmcp/server/parse/worker_client.py`
- [x] **T024** [P] Build `assert_outside_project` (refuse a record dir or backup path inside any project folder, FR-042) and Send/Receive detection (`<projects>/<P>/.hg` is a directory; `unknown` is treated as S/R, FR-043, R-14) · `src/flextoolsmcp/server/filing/paths.py`
- [x] **T025** [P] Add the one-line docstring note "not the filing bound" (R-01) · `src/flextoolsmcp/server/signals/projections.py`

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T026** Wire the filing-claim sweep in beside the existing `sweep_stale_locks()` call (FR-028 server-crash case) · `src/flextoolsmcp/server.py` (~line 1083)

**Checkpoint**: `run_module` is unchanged on the extracted ladder, the contract tests are green at the new count, the surface test is green (except the FR-004 assertion, which goes green at T037), and `apply=false` is unchanged apart from `filing: "not_requested"`.

---

## Phase 3: User Story 1 -- See what filing would do before anything is written (P1) 🎯 MVP

**Goal**: `apply=true` without confirmation returns `confirmation_required` with a concrete, project-computed mutation plan and a `plan_id`, and writes nothing.

**Independent Test**: on a fixture project, an unconfirmed `apply=true` gives a plan whose deletion upper bound is a concrete number (0 for a never-parsed project). The `.fwdata` sha256 is identical before and after, no backup dir exists, and the filing worker was never spawned (SC-001, SC-003).

### Tests (write first, observe red)

**Wave 1 -- independent (different files):**

- [x] **T030** [P] [US1] **Tripwire (R-01), red first.** Projection tests:
  - a human-made, never-evaluated, unused analysis **is counted**;
  - an analysis in use through a gloss is shielded;
  - a disapproved analysis is excluded, and shown as its own count (FR-011, FR-012, FR-040);
  - a never-parsed project gives `upper_bound == 0` and `by_wordform == {}` (FR-013, SC-003);
  - an import assertion that `projection.py` uses `oracle.segment_occurrence` and `project_state.probe_project_state`, with no second traversal (FR-015).

  CP3's predicate MUST fail this fixture · `tests/test_filing_projection.py`
- [x] **T031** [P] [US1] Plan tests: every data-model section 2 key is present (FR-010); CP3 `duplicate_projection` is carried through (FR-016); canonical JSON gives a stable `plan_id` · `tests/test_filing_plan_binding.py` (plan-shape half)

**⟶ Wait, then:**

- [x] **T032** [US1] **Tripwire (FR-006).** Binding tests:
  - `confirmed=True` with no `plan_id` re-previews;
  - `confirmed=True` with a **foreign** `plan_id` re-previews;
  - a recompute mismatch in scope or in any count re-previews with a new `plan_id`.

  A bare `confirmed` flag MUST fail · `tests/test_filing_plan_binding.py` (binding half; same file as T031, so sequential)

### Implementation

**Wave 1 -- independent (different files):**

- [x] **T033** [P] [US1] Build `deletion_upper_bound` on FR-011's two conjuncts, per wordform, with disapproval overwrites counted separately (data-model section 3, R-01). It reuses CP3's join and probe · `src/flextoolsmcp/server/filing/projection.py`
- [x] **T034** [P] [US1] Add the read-only `filing_preview` worker message: a **fresh** segment join (not the worker-lifetime cache, R-02), the eligibility inputs, and the stored analyses per wordform. It opens nothing for writing · `src/flextoolsmcp/server/parse/worker_main.py`
- [x] **T035** [P] [US1] Have every batch run write the additive `eligible_entries` key into its baseline (it feeds US3's eligibility diff) · `src/flextoolsmcp/server/parse/record.py`

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T036** [US1] Build `build_plan`, canonical JSON and `plan_id` (sha256, 64 lowercase hex), with the fields of data-model section 2: words in scope, gate standing (a slot filled by US3), the projection, the duplicate disclosure, backup intent, `access`, and the hypothesis note (R-08) · `src/flextoolsmcp/server/filing/plan.py`

**⟶ Wait, then:**

- [x] **T037** [US1] Add the preview path to the handler for contracts rows 1-10, with row 9 (the gate) stubbed as pass until US3:
  - store the plan in `session.filing_plans`;
  - return `confirmation_required` with `plan`, `plan_id`, `backup{intent,note}` and `next_step`;
  - the message states the upper bound as a number, including 0.

  Confirmation is **unconditional**: `require_write_confirmation` is not consulted (R-08) · `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: T030-T032 are green, SC-001 holds offline (sha256 identical, no backup dir, filing worker not spawned), and SC-003 is green.

---

## Phase 4: User Story 3 -- Refuse to file against a grammar that did not load cleanly (P1)

**Goal**: `grammar_load_unclean` is returned for `morpher_null`, `new_load_errors` or `eligible_forms_dropped`: at preview, at confirm, and on any reload during the job. There is no override.

**Independent Test**: fixtures for each signal are refused before any word is filed, the message names the read-only re-baseline, and a first run treats every error as pre-existing, with `baseline_source="absent"` (SC-005).

### Tests (write first, observe red)

**Wave 1 -- independent (different files):**

- [x] **T040** [P] [US3] **Tripwire (FR-039).** Gate tests:
  - a `None` parse gives `morpher_null`, with no override (FR-020);
  - 3 then 5 errors give `new_error_count=2`, and the message names the re-baseline (FR-021);
  - a first run gives every error pre-existing and `baseline_source="absent"` (FR-022);
  - a stale `HCLoadErrors.xml` with a foreign mtime plays no part (FR-023);
  - an emptied lexeme form gives `eligible_forms_dropped` and names the entry.

  A load-error-only gate MUST fail the last case · `tests/test_filing_gate.py`
- [x] **T041** [P] [US3] Eligibility port tests, one fixture per branch of `IsValidLexEntryForm` / `HasValidRuleForm` (R-12) · `tests/test_filing_eligibility.py`

### Implementation

**Wave 1 -- independent (different files):**

- [x] **T042** [P] [US3] Port the two private `HCLoader` predicates (the Principle VI justified violation; see Complexity Tracking), with a module docstring pointing at the live parity test (T081) · `src/flextoolsmcp/server/filing/eligibility.py`

**⟶ Wait, then:**

- [x] **T043** [US3] Build `find_baseline` (by `created_at`, R-12), the load-error diff and the eligibility diff, returning `GateStanding` (data-model section 4). The message wording is transcribed from data-model section 8 · `src/flextoolsmcp/server/filing/gate.py`

**⟶ Wait, then:**

- [x] **T044** [US3] Wire the gate into contracts row 9 (preview), replacing T037's stub, and fill the plan's gate-standing slot · `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: the preview variants of SC-005 are green offline. The confirm-time check (row 12) and the mid-run check land in US2.

---

## Phase 5: User Story 2 -- File confirmed results, backed up first whenever possible (P1)

**Goal**: a confirmed request with a matching `plan_id` walks the ladder (confirmation, then access gate, then gate again, then best-effort backup, then claim). It then starts a `FILING_ROLE` run that files each word through a fresh `ParseFiler` with a paused, hand-pumped `IdleQueue`. No word is filed whose live would-delete set exceeds the projection.

**Independent Test**: against a fake CLR surface, a confirmed request files every in-projection word, skips `outside_projection` / `invalid_object` / `filer_declined` with counts, and the captures are written before each pump. The backup intent equals the outcome, or the verbatim no-recovery warning is present.

### Tests (write first, observe red)

**Wave 1 -- independent (different files):**

- [x] **T050** [P] [US2] **Tripwire (FR-002).** Ladder-order tests, with boom-stubs on everything after each refusal (the `_boom_lock` pattern) for contracts rows 0-14:
  - unconfirmed + `open_exclusive` gives `confirmation_required`, and plan `access` names the remedy;
  - confirmed + `open_exclusive` gives `project_locked`;
  - `unknown` gives `project_drive_unavailable`;
  - `open_shared` proceeds, with the verbatim advisory;
  - `write_enabled=false` gives `server_state_error` naming `flextools_start(write_enabled=true)`;
  - a missing agent gives `parser_agent_missing` before the preview, and `KeyNotFoundException` is mapped (FR-025);
  - `start_run` is boom-stubbed until row 14, and no refusal carries a `run_id` (FR-003).

  It also covers the offline half of FR-005/SC-001 · `tests/test_filing_ladder_order.py`
- [x] **T051** [P] [US2] Backup tests:
  - disk-full and opt-out fixtures: the run proceeds, intent equals outcome, and the warning is in both the response and meta (FR-007, SC-004);
  - a `run_module` backup does not satisfy filing, and the backup timestamp is earlier than the filing worker's spawn (FR-008);
  - a path or the verbatim warning is always present (FR-009);
  - a record dir inside a project folder is refused (FR-042);
  - a `.hg` fixture gives the S/R route, and `unknown` is treated as S/R (FR-043).

  File: `tests/test_filing_backup.py`
- [x] **T052** [P] [US2] Inverse confinement test: `writeEnabled=True` (and any writable-open call) appears **only** in `filing/worker_filing.py` (FR-029) · `tests/test_filing_write_confinement.py`
- [x] **T053** [P] [US2] Make the R-16 update to the no-writes test: the scan set is **unchanged**, and the FILING stage is narrowed per run. Try-word never files (structural, FR-017) · `tests/test_parse_no_project_writes.py`
- [x] **T054** [P] [US2] Classify tests: counts; the R-02 guard (a live would-delete set larger than the projection gives `outside_projection`, **nothing filed**, FR-014); errored results are filed, with `errored_words` and `errored_word_deletions` counted separately (FR-017); the capture line is written **before** the pump, with the order asserted on the fake (FR-031) · `tests/test_filing_classify.py`
- [x] **T055** [P] [US2] **Tripwire (FR-019).** Filer-pump tests: a fake `IdleQueue` asserts it is non-null and `IsPaused=True`; the agent comes from the HermitCrab GUID; the handler is non-null (FR-018); an invalid result gives `invalid_object`; `Delegate` returning False gives `filer_declined`, and **the next word does not file it**. A single long-lived filer MUST fail · `tests/test_filing_filer_pump.py`
- [x] **T056** [P] [US2] Cancel tests: the run stops at a word boundary; `filed_words` matches; the not-undoable wording is verbatim (FR-034) · `tests/test_filing_cancel.py`

### Implementation

**Wave 1 -- independent (different files):**

- [x] **T057** [P] [US2] Build a per-word `ParseFiler` factory and the paused-`IdleQueue` pump. `FwUtils` is loaded for `IdleQueue`, and every bound member is capability-probed (R-03, contracts row 6) · `src/flextoolsmcp/server/filing/filer.py`
- [x] **T058** [P] [US2] Build the per-word sequence: the R-02 guard against the confirmed projection, then the captures (PreDeletionCapture and DisapprovalOverwrite, data-model section 9), then the pump, then the before/after classification. Counts follow data-model section 7 · `src/flextoolsmcp/server/filing/classify.py`
- [x] **T059** [P] [US2] Add per-run FILING edges, present only for filing runs (data-model section 10) · `src/flextoolsmcp/server/parse/stages.py`
- [x] **T060** [P] [US2] Add the `meta.json` `filing` section writer and the `filing/deletions.jsonl` appender, both through `paths.assert_outside_project` · `src/flextoolsmcp/server/parse/record.py`

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T061** [US2] Build the `FILING_ROLE` entry:
  - a writable open (the one and only one);
  - the agent resolved by GUID;
  - the gate re-run on **every** reload (R-05), giving `refused_midrun` with nothing asked (FR-024);
  - cancellation at a word boundary;
  - at teardown, reuse #147's `RefreshFromDisk`-before-`CloseProject` step (`106a2ff`), gated on the same flexicon capability.

  Apply T005's M-1 outcome here · `src/flextoolsmcp/server/filing/worker_filing.py`

**⟶ Wait, then:**

- [x] **T062** [US2] Add `filing=True` submission to the `FILING_ROLE` worker; release the claim on **every** terminal state (success, refusal, cancel, worker crash); recycle the read worker according to M-1 · `src/flextoolsmcp/server/parse/runner.py`

**⟶ Wait, then:**

- [x] **T063** [US2] Complete the confirmed path in the handler, contracts rows 10-14:
  - verify `plan_id` against a recomputed plan;
  - the access gate;
  - the gate again (row 12);
  - `perform_pre_write_backup` via `write_ladder.take_backup` under the separate session key, best-effort and never refusing;
  - acquire the claim, start the run, and return `run_id`, `filing: "started"`, `backup{path}` or `no_recovery_warning`, `shared_mode_advisory` and `stale_lock_advisory`.

  File: `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: T050-T056 are green, SC-004 and SC-008 hold offline, and every `test_filing_*` offline test so far is green against the fake CLR surface.

---

## Phase 6: User Story 4 -- Only one filing job per project, without freezing the lexicon (P2)

**Goal**: a second filing request against a busy project is refused in under 1 s with the four fields, and read-only tools keep answering.

**Independent Test**: with a claim held, a second `apply=true` gets `parser_filing_in_progress` (4 fields) in under 1 s, before the engine check. `flextools_try_word`, `parse_status`, `parse_log` and `parse_diff` all proceed (SC-006, SC-007).

### Tests

**Wave 1 -- independent (different files):**

- [x] **T070** [P] [US4] Claim tests:
  - refusal in under 1 s, before the engine check (boom-stub, row 2);
  - `hint` names `flextools_parse_status(run_id=...)`;
  - the claim clears on success, refusal, cancel, worker crash and the server-crash sweep (FR-026, FR-028);
  - try-word proceeds while the claim is held, both shared and, if L-0 passed, non-shared (FR-027);
  - no project-wide lock name appears.

  File: `tests/test_filing_claims.py`
- [x] **T071** [P] [US4] Add `filing/claims.py` to the no-edit-blocking scan · `tests/test_parse_no_edit_blocking.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T072** [US4] Wire contracts row 2: a claim lookup before the engine, scope, preview, backup or parse, returning `ParserFilingInProgressDetail`. Confirm that `parse_status`, `parse_log` and `parse_diff` never consult the claim · `src/flextoolsmcp/server/handlers/parse.py`

**Checkpoint**: SC-006 is green offline. SC-007 is green on shared projects (and on non-shared ones if M-1 cleared).

---

## Phase 7: User Story 6 -- Know exactly what a filing run did, afterwards (P3)

**Goal**: the run record shows what the run did: projected beside actual, the captures, the overwritten disapprovals and the wording. The parent spec is corrected.

**Independent Test**: after a fake filing run, `parse_log` `summary` carries the `filing` block with every count key; the `deletions` section serves the captures (and a typed not-applicable response on read-only runs); and no output contains a forbidden word.

### Tests

- [x] **T075** [US6] Record tests:
  - every count key of data-model section 7 is present, with projected beside actual (FR-032);
  - the verbatim sentence (FR-033);
  - a forbidden-word scan (`tacit`, `unreviewed`, `auto_approved`, `auto-approved`) over every emitted response and `meta.json`;
  - the D-2 overwrite list captures the prior evaluation (FR-041);
  - `deletions` on a read-only run is typed not-applicable, never empty.

  File: `tests/test_filing_record.py`

### Implementation

**⟶ Wait, then:**

**Wave 1 -- independent (different files):**

- [x] **T076** [P] [US6] Add a `filing` block to `parse_log` `summary`, and a new `deletions` section (the additive section list in contracts section 1) · `src/flextoolsmcp/server/handlers/parse.py`
- [x] **T077** [P] [US6] Parent-spec corrections: 12.2 D-2 ("filing *does* overwrite an in-use human disapproval"); 12.4 "best-effort" (M-2's spec half); the section 14 row extension (the four appended fields and `eligible_forms_dropped`) · `specs/parser-check/SPEC.md`
- [x] **T078** [P] [US6] Amend CP3's artifact contract additively: `eligible_entries`, the `filing` meta section, `deletions.jsonl` · `specs/parser-check-cp3/contracts/artifact.md`

**Checkpoint**: SC-011's offline half is green, and the corrections are committed.

---

## Phase 8: User Story 5 -- Prove the write against a real project (P2)

**Goal**: the five FR-036 live cases, plus Q1 and Q4, on disposable copies of `IndonesianHC-Complete` (correctness) and `Malay Parsing-20230810withHC` (scale), under `FLEXLIBS_REQUIRE_LIVE=1`.

**Independent Test**: one evidence file per FR-036 case exists under `evidence/` (SC-009), every analysis actually deleted appears in its plan's projection (SC-002), and every overwritten disapproval was projected (SC-011).

**If no human is present, this phase stops as `needs_human` and performs no writes** (constitution I; the `lex-verification` hook).

- [x] **T080** [US5] Write the live test module: `requires_flex`, a fixture that uses T001 and refuses any project without the `CP4-Scratch-` prefix (FR-037), and `FLEXLIBS_REQUIRE_LIVE=1` turning a missing prerequisite into a failure · `tests/test_parse_live_cp4.py`

**⟶ Wait, then:**

**Wave 1 -- independent (different files):**

- [x] **T081** [P] [US5] Add the eligibility port parity test: the port's count equals the loaded grammar's entry count (the Principle VI mitigation) · `tests/test_parse_live_cp4.py` (parity group)
- [x] **T082** [P] [US5] Run quickstart scenarios 1-3 (preview writes nothing; the conjunction is an upper bound; a disapproval is overwritten) and record evidence (SC-001, SC-002, SC-003, SC-011) · `specs/parser-check-cp4/evidence/`
- [x] **T083** [P] [US5] Run quickstart scenarios 4-6 (the gate refuses, including the S4d mid-run reload; backup outcomes; concurrency) and record evidence (SC-004, SC-005, SC-006, SC-007) · `specs/parser-check-cp4/evidence/`
- [x] **T084** [P] [US5] Run quickstart scenarios 7-8 (Q1 and Q4, the FR-038 re-probe including `MoveConcAnnotationsToWordform`; cancel) and record evidence · `specs/parser-check-cp4/evidence/`

T082-T084 share one live FieldWorks host. They are independent in the files they write, but a host may run them sequentially.

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T085** [US5] Write the FR-038 finding into parent 9.5.3 · `specs/parser-check/SPEC.md`

**Checkpoint**: SC-002, SC-009 and SC-011 are observed live.

---

## Phase 9: Polish and cross-cutting

**Wave 1 -- independent (different files):**

- [x] **T090** [P] Pattern-audit sweep #1 (a proxy predicate under-counting a C# predicate, R-01) and sweep #2 (worker or session caches read by a gate, R-02), via the `sweep-pattern` skill. Record the sibling lists for the PR body · `specs/parser-check-cp4/reviews/pattern-audit-1-2.md`
- [x] **T091** [P] Pattern-audit sweep #3: re-grep `config_get(` in `src/`, not trusting the plan's list, and record for each call whether lowering the key is intended. Sweep #4: fail-open probes, siblings of #118 · `specs/parser-check-cp4/reviews/pattern-audit-3-4.md`
- [x] **T092** [P] Run the golden fixture refresh check and the integrity validator (the plan's merge requirements) · `tests/golden/responses/`

**⟶ Wait for Wave 1 to finish, then:**

- [x] **T093** Validate against the Success Criteria:
  - run the full offline suite (`pytest`) and lint (`ruff`, as in CI);
  - confirm SC-010, that the existing suite and the read-only boundary tests are green, and that `test_issue55_write_safety_ladder.py` is still unmodified since `2aedb1d`;
  - map each of SC-001..SC-011 to its passing test or evidence file.
- [x] **T094** Surface M-2 to the maintainer: issue #165's definition of done still says "Mandatory pre-write backup". The edit is outward-facing, so report it and do **not** make it without authorisation · (no file; report in the PR body)

---

## Dependencies & Execution Order

**Phases:** Setup (1) → Foundational (2) → US1 (3) → US3 (4) → US2 (5) → US4 (6) → US6 (7) → US5 (8) → Polish (9).
- Phase 1's M-1 outcome (T005) must land before T061/T062 **merge**. Phases 2-4 can proceed while Phase 1's live probes are pending.
- US6 (Phase 7) needs US2's record writers (T060).
- US5 (Phase 8) needs every offline phase.

**Waves per phase:**
- **Phase 1**: W1 {T001, T002} → W2 {T003, T004} → T005.
- **Phase 2**: 2a runs T006 → T007 → T008. 2b runs W1 {T009-T014} → W2 {T015-T018} → T019. 2c runs W1 {T020-T025} → T026. The three sub-tracks touch different files and can interleave; T019 and T008 both precede Phase 3's handler work.
- **Phase 3 (US1)**: tests {T030, T031} → T032. Implementation W1 {T033, T034, T035} → T036 → T037.
- **Phase 4 (US3)**: tests {T040, T041}. Implementation T042 → T043 → T044.
- **Phase 5 (US2)**: tests W1 {T050-T056}. Implementation W1 {T057-T060} → T061 → T062 → T063.
- **Phase 6 (US4)**: W1 {T070, T071} → T072.
- **Phase 7 (US6)**: T075 → W1 {T076, T077, T078}.
- **Phase 8 (US5)**: T080 → W1 {T081-T084} → T085.
- **Phase 9**: W1 {T090, T091, T092} → T093 → T094.

**Handler serialization.** `handlers/parse.py` is edited by T019, T037, T044, T063, T072 and T076, strictly in that order. None of them shares a wave.
