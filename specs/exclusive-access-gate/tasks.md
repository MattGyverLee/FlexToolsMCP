# Tasks: Exclusive-access gate and shared-mode follow-ups

**Input**: `specs/exclusive-access-gate/` -- plan.md, spec.md, research.md, data-model.md,
contracts/requires_exclusive_access.md, quickstart.md
**Worktree**: `C:\Github\FlexToolsMCP-exclusive-access` (branch `feat/exclusive-access-gate`).
Run every command from there.

**Tests**: REQUIRED. The plan gate (constitution, `reviews/plan-qc.md`) maps
every requirement and scenario to a test. Write tests first and see them fail.

**Line numbers** come from origin/main `db66f11` and drift. Grep for the symbol
before editing.

**Test command** (never bare `python`):
`.venv\Scripts\python -m pytest -q -m "not requires_flex" <paths> | tail -20`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on unfinished tasks)
- **[Story]**: US1-US6 from spec.md

---

## Phase 1: Setup

- [ ] T001 Record the baseline. Run `.venv\Scripts\python -m pytest -q -m "not requires_flex" tests/test_response_contract.py tests/test_parser_error_models.py tests/test_shared_mode_write_gate.py tests/test_shared_mode_lock_diagnosis.py tests/test_script_certification.py | tail -20` and note the pass count in `specs/exclusive-access-gate/evidence/baseline.md`. All must pass before any change.
- [ ] T002 [P] Create `specs/exclusive-access-gate/evidence/` and `specs/exclusive-access-gate/issues/`, each with a one-line `README.md` describing what will go there (live evidence; the filing ledger).

---

## Phase 2: Foundational (blocks US1, US2, US4)

**Purpose**: the single table that the detector, the refusal message and the
docs check all read (constitution VI).

- [ ] T003 Write `tests/test_exclusive_access_detect.py::TestTable`, which must fail first:
  - every `wrapper` method in `EXCLUSIVE_ONLY_OPERATIONS` exists in the shipped flexicon index (`src/flextoolsmcp/index/python/flexicon_api_v*.json`; load it the way `tests/test_issue130_facade_receiver_write_gate.py` does) with `is_mutating: true`;
  - no row names `SetValue`, `AddListValue`, `RemoveListValue`, `SetListFieldSingle`, `SetListFieldMultiple`, `ClearValue` or `Duplicate`;
  - every row has a non-empty `reason` and `evidence`, and a `failure_class` in {`crashes_holder`, `silently_lost`}.
- [ ] T004 Create `src/flextoolsmcp/server/exclusive_access.py` with:
  - Frozen dataclasses `ExclusiveOnlyOperation` and `ExclusiveOnlyMatch`, fields exactly as in data-model.md.
  - The tuple `EXCLUSIVE_ONLY_OPERATIONS` with these rows (names from research.md R2/R3):
    - `ws.wrapper`: `WritingSystemOperations` {Create, Ensure, Delete, SetFontName, SetFontSize, SetRightToLeft, SetDefaultVernacular, SetDefaultAnalysis}, `crashes_holder`, evidence `specs/_archive/shared-mode-access/evidence/live-cp4.md Item 5`.
    - `cf.wrapper`: `CustomFieldOperations` {CreateField, DeleteField, SetFieldName}, `silently_lost`, evidence `SharedXMLBackendProvider.cs:429,479; CommitLogRecord.cs:23-48`.
    - `cf.raw`: raw_names {AddCustomField, UpdateCustomField, DeleteCustomField}; raw_assignments {MarkForDeletion}.
    - `ws.raw.manager`: raw_receiver_methods ({WritingSystemManager}, {Set, GetOrSet, Replace, Save}).
    - `ws.raw.container`: raw_names {AddToCurrentVernacularWritingSystems, AddToCurrentAnalysisWritingSystems}.
    - `ws.raw.lists`: raw_receiver_methods ({VernacularWritingSystems, AnalysisWritingSystems, CurrentVernacularWritingSystems, CurrentAnalysisWritingSystems}, {Add, Remove, Insert, Clear}).
    - `ws.raw.services`: raw_receiver_methods ({WritingSystemServices}, {FindOrCreateWritingSystem, FindOrCreateSomeWritingSystem, UpdateWritingSystemFields, DeleteWritingSystem, MergeWritingSystems, UpdateWritingSystemId}).
    - `ws.raw.props`: raw_assignments {DefaultVernacularWritingSystem, DefaultAnalysisWritingSystem, DefaultFontName, DefaultFont, DefaultFontSize, RightToLeftScript}.
    - `FieldDescription.UpdateCustomField` is covered by `cf.raw`'s `UpdateCustomField` name.
  - A module docstring that cites spec FR-001/FR-002 and research R3.
  - Plain ASCII only. Run T003 until it passes.

**Checkpoint**: the table exists and is index-consistent.

---

## Phase 3: User Story 1 - Refuse WS/CF changes while FLEx is open (Priority: P1) MVP

**Goal**: a write-enabled `run_module` containing an exclusive-only call is
refused with `requires_exclusive_access` when the probe says `open_shared` or
`unknown`, before the confirmation gate, the backup or any subprocess.

**Independent test**: `tests/test_exclusive_access_gate.py` passes with the
probe mocked, and live V1-V3 pass on Sena 3.

### Tests for US1 (write first, see them fail)

- [ ] T005 [P] [US1] In `tests/test_exclusive_access_detect.py::TestDetect`, cover, each as its own test:
  - (a) `project.WritingSystems.Create(...)`
  - (b) the alias `ws = project.WritingSystems; ws.Ensure(...)`
  - (c) the facade `fx = FLExProject.FromOpenProject(project); fx.CustomFields.CreateField(...)`
  - (d) `WritingSystemOperations(project).Delete(...)`
  - (e) the raw `cache.MetaDataCacheAccessor.AddCustomField(...)`
  - (f) the raw receiver `mgr = cache.ServiceLocator.WritingSystemManager; mgr.Set(ws)`
  - (g) `lp.CurrentVernacularWritingSystems.Add(ws)`
  - (h) the assignment `fd.MarkForDeletion = True` and `ws.DefaultFontSize = 12`
  - (i) a call guarded by `if modifyAllowed:` still matches (it comes from `protected_calls`)
  - (j) a match taken from `unknown_calls`, and one from a Step 2b `unresolved_receiver` row (copy the receiver shapes from `tests/test_issue130_facade_receiver_write_gate.py`)
  - (k) a call inside `if False:` still matches

  Negatives:
  - (l) `project.CustomFields.SetValue(...)` and the other value setters
  - (m) `project.WritingSystems.GetAll()`, `Exists(...)`, `GetDisplayName(...)`
  - (n) `some_dict.Set(...)`, `items.Add(...)` and `other.Save()` on unrelated receivers
  - (o) calls only inside a comment or a string literal
  - (p) the detector run over every `.py` under `src/flextoolsmcp/server/filing/` returns zero matches (research R8)
- [ ] T006 [P] [US1] Write `tests/test_exclusive_access_gate.py`. Drive `handle_run_module` with `write_ladder.probe_write_access` mocked to return each verdict; model it on `tests/test_shared_mode_write_gate.py`. Assert that the subprocess spawn mock is never called on refusal. Cases:
  - scenario 1.1/1.2: `open_shared` plus a WS script, a CF script and a raw script each give the code `requires_exclusive_access`;
  - 1.3: `free` and `stale_lock` with matches are not refused by this gate;
  - 1.4: `open_exclusive` and `held_by_other` with matches give `project_locked`;
  - 1.5: `write_enabled=True` plus a script that certifies read-only but contains a match. The probe mock is called, and the run is refused;
  - FR-006: `unknown` with matches is refused, and the remedy says FLEx could not be confirmed closed; `unknown` with an ordinary write is unchanged (not refused);
  - 1.8: `write_enabled=False` plus a guarded match is not gated;
  - refusal happens before the confirmation gate: `confirmed=False` on an `open_shared` match gives `requires_exclusive_access`, not `confirmation_required`;
  - the gate uses the first probe decision, unaffected by the `_release_own_worker_or_refuse` re-probe;
  - the detail fields match data-model.md `RequiresExclusiveAccessDetail` exactly (FR-008).
- [ ] T007 [P] [US1] Add a test to `tests/test_exclusive_access_gate.py` for the `validate_only=True` path (scenario 1.7): `project_lock.exclusive_access` = {required: true, operations: [...], blocking: true} on `open_shared`; `blocking: false` on `free`; `blocking is None` when the probe is unavailable (mirror the existing `probed`/#118 branch).

### Implementation for US1

- [ ] T008 [US1] In `src/flextoolsmcp/server/exclusive_access.py`, implement `detect_exclusive_only_operations(code: str, tree: ast.AST, cert: dict) -> list[ExclusiveOnlyMatch]`:
  - Layer 1 filters the cert rows in `mutating_calls`, `protected_calls`, `unknown_calls` and those with `source == "unresolved_receiver"` on `(class, method)` against the wrapper rows. For `unresolved_receiver` rows, match on method name only when the class is unknown.
  - Layer 2 is an `ast.walk`, modelled on `detect_raw_addcustomfield_risk` (`src/flextoolsmcp/server/validators.py` ~:5789):
    - `Call` nodes whose `func.attr` is in a row's `raw_names`;
    - `Call` nodes whose `func.attr` is in a row's generic method set **and** whose receiver chain (via `ast.unparse` on `func.value`) contains a receiver name, or is a local `Name` previously assigned from an expression containing one (a single-pass alias map per function scope, like `_resolve_alias_maps` ~:4835);
    - `Assign`/`AugAssign` targets that are an `Attribute` whose `attr` is in `raw_assignments`.
  - Fill `line` from the AST, and fall back to the cert row's line if present. De-duplicate on `(key, line)` and sort by line.
  - Run T005 until it passes.
- [ ] T009 [US1] Add `RequiresExclusiveAccessDetail` (`extra="forbid"`, fields in data-model.md order) next to `ProjectLockedDetail` in `src/flextoolsmcp/server/response_models.py` (~:396). Add it to the `AnyDetail` union (~:979-1026), and add the code to the module-docstring count history (~:25), changing 46 to 47.
- [ ] T010 [US1] Wire the gate into `handle_run_module` in `src/flextoolsmcp/server/handlers/execution.py`:
  - right after `cert` / `is_mutating_script` (~:5239), compute `_exclusive_matches = detect_exclusive_only_operations(code, code_tree, cert) if write_enabled else []`;
  - change `_probe_access = needs_lock or (not write_enabled)` (~:5257) to `needs_lock or (not write_enabled) or bool(_exclusive_matches)`;
  - immediately after the probe and read-back block (~:5278), before the confirmation gate (~:5285), refuse when `_exclusive_matches` is non-empty **and** `_access.verdict in ("open_shared", "unknown")`;
  - build the refusal with `error_response("requires_exclusive_access", message, detail=...)` (`src/flextoolsmcp/response_utils.py:249`), wrapped in `_attach_assistance_if_loop(..., error_code="requires_exclusive_access", ...)` like the `project_locked` refusal (~:5400-5423). Use the message and guidance text from `contracts/requires_exclusive_access.md`, with the project name;
  - log the refusal on the existing `[SHARED]` prose and structured paths with the op id;
  - leave `open_exclusive` / `held_by_other` alone.

  Run T006 until it passes.
- [ ] T011 [US1] In the `validate_only` block of `src/flextoolsmcp/server/handlers/execution.py` (~:2466-2531), run the detector, then add `project_lock["exclusive_access"]` per data-model.md (`blocking: None` on the probe-unavailable branch ~:2507/:2516). Update `lock_note` when blocking. Run T007 until it passes.
- [ ] T012 [US1] Contract chores for the new code:
  - add a `requires_exclusive_access` entry to `GOLDEN_FIXTURES` in `tests/make_golden.py` (~:105, next to `project_locked` ~:179), then run `python tests/make_golden.py --regen`. The only new file should be `tests/golden/responses/requires_exclusive_access.json`;
  - in `tests/test_response_contract.py`, add the per-code key set (~:169), the `ALL_ERROR_CODES` entry (~:243), the detail-model map (~:367), the count history comment (~:515-521) and `assert union_size == 47` (~:522);
  - in `tests/test_parser_error_models.py` (~:503), change 46 to 47;
  - in `docs/TOOL-CONTRACT.md`, update ":82 one of the 47 codes below", add a code-table row next to `project_locked` (~:136), and fix the stale "44 codes" at ~:721;
  - finish with `grep -rn "== 46" tests/` and `grep -rn "46 codes" docs/ src/ tests/`, which must return nothing;
  - leave `tests/evals/test_corpus.py` and `tests/evals/preflight_runner.py` unchanged: not applicable (plan.md);
  - run `tests/test_response_contract.py` and `tests/test_parser_error_models.py`.

**Checkpoint**: run T005-T007 plus the contract tests. All green means US1 works offline.

---

## Phase 4: User Story 2 - Recovery without looping (Priority: P1)

**Goal**: the refusal teaches the right next step, and no message tells users
to close FLEx for an ordinary failure on a shared project.

**Independent test**: scenario 2.1 and 2.2 tests pass.

### Tests for US2

- [ ] T013 [P] [US2] In `tests/test_exclusive_access_gate.py`, test that `_ASSISTANCE_HINTS_BY_ERROR_CODE["requires_exclusive_access"]` exists (`src/flextoolsmcp/server/session.py` ~:33) and contains "re-submit" and "do not rewrite". Also test that a repeated refusal in one session gets that hint attached, not the generic fallback (scenario 2.1).
- [ ] T014 [P] [US2] Extend `tests/test_shared_mode_lock_diagnosis.py`: for an open failure carrying a lock marker while the probe says `open_shared`, `_diagnose_project_open_error` returns no "Close FieldWorks" text and says sharing is on (scenario 2.2, FR-011).
- [ ] T015 [P] [US2] Extend `tests/test_shared_mode_write_gate.py`: the `open_shared` advisory from `probe_write_access` no longer contains "Custom-field and writing-system changes are NOT safe", and it names `requires_exclusive_access` (FR-013).

### Implementation for US2

- [ ] T016 [US2] Add the hint text from `contracts/requires_exclusive_access.md` to `_ASSISTANCE_HINTS_BY_ERROR_CODE` in `src/flextoolsmcp/server/session.py`. Run T013.
- [ ] T017 [US2] In `src/flextoolsmcp/server/handlers/execution.py` `_diagnose_project_open_error` (~:1223, generic hint ~:1265-1271): when the probe verdict is `open_shared`, replace the generic hint with: "FieldWorks has this project open with sharing on, so the lock file is not the cause. Report the underlying error below; closing FieldWorks is not required." Keep the other verdicts unchanged. Run T014.
- [ ] T018 [US2] In `src/flextoolsmcp/server/write_ladder.py`:
  - reword the fallback guidance (~:157-158) so it doesn't contradict shared mode;
  - replace the last sentence of the `open_shared` advisory (~:172-179) with "Writing-system and custom-field changes are refused while FieldWorks has the project open (requires_exclusive_access).".

  Run T015 and the existing `tests/test_shared_mode_write_gate.py`.
- [ ] T019 [US2] Pattern audit, sweeping for siblings of the "close FieldWorks" message:
  - check each candidate: `src/flextoolsmcp/server/project_discovery.py` ~:398 and ~:419, `src/flextoolsmcp/server/handlers/teardown_recovery.py` ~:180, plus `grep -rni "close fieldworks\|close flex" src/`;
  - fix any that fire on an `open_shared` project, and record each one kept with its reason (stale-lock or dead-PID text may legitimately stay);
  - put the findings in the Phase 4 commit body under "Pattern audit".

**Checkpoint**: US1 and US2 both pass offline. This is the MVP.

---

## Phase 5: User Story 4 - Docs tell the truth (Priority: P2)

(Scheduled before US3 because it is offline. US3 needs a human.)

**Goal**: no doc claims an undo the system doesn't have, and SHARED-MODE.md
describes the gate as shipped.

**Independent test**: `tests/test_docs_no_undo_claims.py` passes.

- [ ] T020 [P] [US4] Write `tests/test_docs_no_undo_claims.py`:
  - (a) no file under `docs/`, nor `USAGE.md`, `README.md` or `src/flextoolsmcp/server/tool_definitions.py`, contains `undo_last_operation`;
  - (b) none contains "can reverse a write";
  - (c) `docs/SHARED-MODE.md` contains "requires_exclusive_access", "navigate away", "F5", "non-undoable" and "empty undo history" (or the exact phrases chosen in T023, kept in sync);
  - (d) every `category` in `EXCLUSIVE_ONLY_OPERATIONS` has a row in SHARED-MODE.md's "Close FLEx for these" table.
- [ ] T021 [P] [US4] In `docs/workflow-summary.md`:
  - remove Stage 6 "Inspect & Undo" (~:16 table row, ~:137 "undo entry recorded", ~:170-211);
  - keep `flextools_get_operation_logs` and `flextools_get_session_history` in an "Inspect" stage, described without undo;
  - fix the numbering of any stages after it.
- [ ] T022 [P] [US4] In `docs/FLEXTOOLS-STYLE-GUIDE.md` (~:688-693), replace the "`flextools_undo_last_operation` can reverse a write" passage with: there is no undo; your safety nets are the automatic pre-write backup and, for Send/Receive projects, the repository. Link `docs/RECOVERY.md`.
- [ ] T023 [US4] In `docs/SHARED-MODE.md`:
  - "Close FLEx for these" (~:72-97): say the server refuses these with `requires_exclusive_access` and give the recovery steps; generate the table rows from the categories in `EXCLUSIVE_ONLY_OPERATIONS`;
  - add a "Seeing an MCP change in FLEx" paragraph: navigate away and back; F5 alone is not enough (#96);
  - extend "Undo" (~:143-149) with the four facts from spec Section 2: no MCP undo; FLEx starts with an empty undo history on open; FLEx records peer writes as non-undoable, citing research R4; programmatic LCM undo is not built;
  - leave the "upstream issue not yet filed" line (~:141) for T037.

  Run T020.
- [ ] T024 [US4] Review the undo wording in `src/flextoolsmcp/server/tool_definitions.py` (~:133-142, ~:661, ~:718). Rewrite anything that suggests the MCP can undo a write. FLEx-side `undoable` mode text may stay if it is accurate. Then run `python scripts/validate_integrity.py server`.

**Checkpoint**: T020 passes, and the integrity check is clean.

---

## Phase 6: User Story 5 - Write-enabled sessions see peer writes (Priority: P3)

**Goal**: settle FR-030 live, then ship the sync-at-open step only if it helps.

**Independent test**: quickstart V5 recorded, plus T027 if the step ships.

- [ ] T025 [US5] Live V5 (`requires_flex`, Sena 3, FLEx open, sharing on, `FLEXLIBS_REQUIRE_LIVE=1`), following quickstart.md:
  - call A creates a `zzExclTest` entry and sets its gloss;
  - call B (write-enabled, confirmed, a script that only reads that gloss) runs once as-is, and once with `project.SaveChanges()` added as its first statement (`SyncForeignChanges()` if `_undoable` is false);
  - record both read values, `run_mode: live`, the exact commands, and the cleanup (delete `zzExclTest`, confirmed by a read-only listing) in `specs/exclusive-access-gate/evidence/live-gate.md` under "V5";
  - decide SHIP or NO-SHIP.
- [ ] T026 [US5] Only if T025 says SHIP:
  - in the generated runner template in `src/flextoolsmcp/server/handlers/execution.py` (after the open-failure `except` ~:4880-4889, before `FLEX_EMPTY_PLACEHOLDER` ~:4892), add a step guarded by `if WRITE_ENABLED and SHARED_PEER:` that calls `project.SaveChanges()` (or `SyncForeignChanges()` when not `_undoable`);
  - wrap it in try/except. On failure, log it and record `shared_mode.sync_at_open = {attempted, ok, error}`; never fail the run;
  - inject `SHARED_PEER` from `_live_fw_peer`.

  If NO-SHIP, write "not shipped" plus the reason in `evidence/live-gate.md` and skip T027.
- [ ] T027 [P] [US5] Only if T026 shipped: add a test in `tests/test_exclusive_access_gate.py` that the generated runner source contains the guarded sync call when write-enabled on `open_shared`, and does not contain it otherwise.
- [ ] T028 [US5] Update the `shared_mode_read_back` note in `src/flextoolsmcp/server/handlers/admin.py` (~:277-313) and its source in `execution.py` (~:5263-5278). Replace "this path is untested" with the result: read-only sessions cannot pull in a peer's recent writes (`FP_ReadOnlyError`); write-enabled sessions do / do not (per T025). Add a text assertion to `tests/test_shared_mode_write_gate.py`.

---

## Phase 7: User Story 3 - Valid live test for the custom-field hazard (Priority: P2, needs-human)

**Goal**: replace the withdrawn CP5-a with a procedure that can actually
observe Class B.

**Independent test**: quickstart V7 recorded with an outcome.

- [ ] T029 [US3] Write the harness `specs/exclusive-access-gate/evidence/live_cf_peer.py`, modelled on `specs/_archive/shared-mode-access/evidence/live_shared_peer.py` and `run_live_peer.py`:
  - assert the project name is `Sena 3`;
  - open as a peer with `writeEnabled=True`;
  - build `FieldDescription(cache)` for class `LexEntry`, name `zzExclTest`, type MultiUnicode, analysis WS;
  - inside `NonUndoableUnitOfWorkHelper.Do(cache.ActionHandlerAccessor, ...)`, call `fd.UpdateCustomField()` then `FieldDescription.ClearDataAbout()`;
  - commit, close, and print plain-ASCII results;
  - write no data to the field.
- [ ] T030 [US3] **needs-human**. Ask the maintainer to open Sena 3 in FLEx (sharing on), then run the harness with `FLEXLIBS_REQUIRE_LIVE=1`. Record whether `zzExclTest` shows in FLEx's Custom Fields dialog. Ask them to close and reopen FLEx and check again. Record everything in `evidence/live-gate.md` under "V7". If the definition survived, have them delete it in the dialog and confirm.
- [ ] T031 [US3] Update the custom-field row's evidence in `docs/SHARED-MODE.md` (~:81) and `EXCLUSIVE_ONLY_OPERATIONS` `cf.*` evidence to the V7 outcome ("seen live" or what was observed). If V7 could not run, file the gap upstream per FR-014. This needs maintainer authorization, so record it in `issues/filing-ledger.md`.

---

## Phase 8: User Story 6 - Close out unfiled findings (Priority: P3, needs-human)

**Independent test**: every item in `issues/filing-ledger.md` has an outcome.

- [ ] T032 [P] [US6] Create `specs/exclusive-access-gate/issues/filing-ledger.md` with one row per item: Item | Target repo | Check result | Outcome (filed #N / duplicate of #N / already fixed in <sha> / not filing: reason) | Authorized by.
- [ ] T033 [US6] Check each upstream hazard against the flexicon working tree (`C:\Github\flexicon`, `git log --oneline -5` for the version) and record the result:
  - the `ConflictingSave` modal: is `FwLcmUI` still passed in `flexicon/code/FLExLCM.py`, or does `headless_ui.py` replace it?
  - `BeginUndoTask` arity;
  - the `_transaction_depth` leak;
  - the nonexistent `RollbackToMark` call in `Transaction()`;
  - the inaccurate `CheckNotProcessingDataChanges` comment in `CustomFieldOperations.CreateField` (research R3).
- [ ] T034 [US6] Triage each draft in `specs/_archive/shared-mode-access/issues/DRAFT-issues.md` against open and closed issues on MattGyverLee/FlexToolsMCP and MattGyverLee/flexicon (`gh issue list --search`). Record duplicate, already fixed, or still new for each.
- [ ] T035 [US6] **needs-human**. Present the "still new" items from T033-T034 to the maintainer and file only those they approve, one `gh issue create` per item, each with an authorization note. Record the issue numbers in the ledger.

---

## Phase 9: Polish & cross-cutting

- [ ] T036 Live US1/US2 verification (`requires_flex`, Sena 3, `FLEXLIBS_REQUIRE_LIVE=1`): quickstart V1, V2, V3, V4 and V6, recorded in `evidence/live-gate.md`. Each step needs:
  - `run_mode: live`, cross-checked against `tests/live_status.json`;
  - the exact call;
  - pre/post values re-queried from LCM (V1: `.ldml` mtimes; V3: the WS list before and after; V4: the gloss before and after; V6: whether Undo offers the change);
  - cleanup of every `zzExclTest` object, confirmed by a read-only listing.

  V3 and V6 need the maintainer to close and reopen FLEx (**needs-human**).
- [ ] T037 Once T035 is done, replace "upstream issue not yet filed" in `docs/SHARED-MODE.md` (~:141) with the filed issue links, or with "already fixed in flexicon <version>".
- [ ] T038 Add a CHANGELOG.md `[Unreleased]` entry. There is no issue for this feature, so it goes under Other, appended at the bottom, plus a Tool contract line appended at the section end:
  - the new `requires_exclusive_access` code, moving the count from 46 to 47;
  - the `validate_only` `project_lock.exclusive_access` key;
  - the advisory and diagnose text changes;
  - the doc corrections;
  - sync-at-open, if shipped.

  Model it on the `recipe_not_found` entry (~:69-72).
- [ ] T039 Run the `sweep-pattern` skill on the detector's own shape (receiver/name matching, role disambiguation; plan.md Phase 3). Record the result in `specs/exclusive-access-gate/reviews/sweep-detector.md`, and fix any confirmed sibling.
- [ ] T040 Run the full offline gate:
  - `.venv\Scripts\python -m pytest -q -m "not requires_flex" | tail -20`
  - `python tests/make_golden.py --regen` (no diff beyond T012)
  - `python scripts/validate_integrity.py server`
  - `pre-commit run --all-files`

  All must be clean.
- [ ] T041 Update `specs/exclusive-access-gate/.spec-context.json` (currentStep implement, status per progress). Commit and push each phase on the branch with `git push origin HEAD:refs/heads/feat/exclusive-access-gate`, and only after that phase's tests are green.

**Constitution gate obligations**:

- Pattern audit: T019 (message class) and T039 (detector shape).
- Live-LCM verification: T025, T030 and T036, with pre/post values on Sena 3 and `zzExclTest` objects.
- CHANGELOG: T038. Golden regeneration: T012. No extractor change, so no index diff.

---

## Dependencies & execution order

- **Setup (T001-T002)** comes first.
- **Foundational (T003-T004)** blocks US1, US2 and US4 (the table).
- **US1 (T005-T012)**: the tests (T005-T007) can run in parallel. T008 comes before T010 and T011. T009 comes before T010 and T012.
- **US2 (T013-T019)** depends on T010 (the gate exists) for T013 and T016. T014/T017 and T015/T018 depend only on Phase 2.
- **US4 (T020-T024)** depends on T004 (table categories) and T010 (the code name). Otherwise it is independent.
- **US5 (T025-T028)**: T025 needs FieldWorks. T026 and T027 depend on T025's decision. T028 depends on T025.
- **US3 (T029-T031)** is independent of code. T030 needs a human.
- **US6 (T032-T035)** is independent. T035 needs a human.
- **Polish**: T036 after US1 and US2; T037 after T035; T038-T040 last.

### Parallel examples

```text
# After T004:
T005 test_exclusive_access_detect.py  ||  T006 test_exclusive_access_gate.py  ||  T007 validate_only test
# After T010:
T013 || T014 || T015   then   T016 || T017 || T018
# US4 docs, all different files:
T020 || T021 || T022
# Independent of code at any time:
T029 (harness)  ||  T032-T034 (ledger + triage)
```

## Implementation strategy

1. **MVP = Phases 1-4** (US1 and US2), all offline. Commit and push after each phase with its tests green.
2. Then Phase 5 (US4 docs). That completes everything that doesn't need FieldWorks or a human.
3. Then live: T036 and T025 (US5 decision).
4. **needs-human items**: T030, T035, and the V3/V6 parts of T036. An unattended round stops at each with a `needs-human` handoff; it never skips them silently.
