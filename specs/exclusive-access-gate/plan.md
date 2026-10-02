# Implementation Plan: Exclusive-access gate and shared-mode follow-ups

**Branch**: `feat/exclusive-access-gate` (worktree `C:\Github\FlexToolsMCP-exclusive-access`) | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/exclusive-access-gate/spec.md`

## Summary

The server already lets writes go ahead while FLEx has a project open in shared
mode. This plan adds the one refusal shared mode still needs.

A write-enabled `run_module` whose script changes writing systems or custom
fields is refused with a new error code, `requires_exclusive_access`, whenever
the access probe says FLEx holds the project (`open_shared`) or can't tell
(`unknown`). The refusal happens before the confirmation gate, the backup and
the subprocess.

Detection reuses the read-only certifier's resolved call rows (wrapper calls)
and adds an AST pass for raw LCM names (research R2-R3). Around the gate, the
plan:
- fixes the messages that still tell users to close FLEx on a shared project;
- corrects the remaining undo documentation, now that LCM source shows FLEx
  records peer writes as non-undoable (R4);
- adds an optional sync-at-open step for write-enabled runs, which ships only
  if live check V5 shows it helps (R5);
- replaces the predecessor's invalid custom-field live test (R9);
- carries out the upstream filing, with the maintainer's sign-off.

## Technical Context

**Language/Version**: Python 3.10+ (pyproject floor). The generated runner runs under the pythonnet subprocess.

**Primary Dependencies**: flexicon (`pyflexicon`) 4.11.x, pythonnet, mcp>=1.27,<3, pydantic (response models)

**Storage**: N/A. The gate is stateless. The table is a module constant.

**Testing**: pytest via `.venv\Scripts\python -m pytest -q -m "not requires_flex"`; golden fixtures (`tests/make_golden.py`); live checks per [quickstart.md](quickstart.md)

**Target Platform**: Windows with FieldWorks 9.3.x for the live steps. The offline suite runs anywhere.

**Project Type**: MCP server (stdio tool)

**Performance Goals**: The detector adds one AST walk over the handler's already-parsed `code_tree`. It adds no noticeable latency.

**Constraints**: Additive contract only. Console output is plain ASCII. No writes to `LexiconSettings.plsx`.

**Scale/Scope**: about 1 new module (~250 lines), edits to `execution.py`, `write_ladder.py`, `session.py`, `response_models.py` and `handlers/admin.py`, 5 doc files and 3 to 4 test files

## Constitution Check

*Source: `.specify/memory/constitution.md` v1.1.0.*

- [x] **I. Safety-First Write Path**: Yes, this touches a write path, but only to
      refuse more. Read-only stays the default. It relaxes no guard,
      confirmation or backup. The new refusal comes before confirmation, so
      nothing is taken or spawned. Live verification uses Sena 3 with
      `zzExclTest` objects, cleaned up in the same session. V7 needs a human
      to close and reopen FLEx, so it is `needs-human`, not unattended.
- [x] **II. Discovery Over Memory**: The wrapper rows are checked against the
      shipped flexicon index by a test. Raw LCM names are cited to LCM source
      (research R3).
- [x] **III. Self-Contained, Regenerable Extraction**: No extractor or index
      change.
- [x] **IV. Append-Only Versioned Contracts**: One new code, one new detail
      model and one new `validate_only` sub-key. No removal or rename. The
      text changes keep their keys. A CHANGELOG entry is planned.
- [x] **V. Errors That Teach**: A stable code, guidance with the exact next
      steps, and a specific assistance hint. Each refusal is logged on the
      existing prose and structured paths with its op id.
- [x] **VI. One Module, One Source of Truth**: Detection reads the certifier's
      rows and does not re-implement resolution. One table feeds the
      detector, the message and the docs check.
- [x] **VII. Windows-First, No Cross-Platform Shims**: Live tests are marked
      `requires_flex`. The offline suite needs no FieldWorks.
- [x] **Gate obligations scheduled**: Tests per requirement are below. A
      pattern audit is scheduled for the "close FieldWorks" message class
      (R7). Live-LCM verification is V1-V7.

Re-checked after Phase 1 design: all still pass. R10 flags a stale undo
sentence in the constitution itself. It is out of scope, because changing it
is a governance amendment.

## Requirement-to-test map

| Requirement | Test |
|---|---|
| FR-001, FR-002, FR-002a | `tests/test_exclusive_access_detect.py`:<br>- one positive case per row (wrapper via `project.X`, alias, facade, `XOperations(project)`; raw by name; raw by receiver; assignment)<br>- negatives: value setters, WS `Get*`/`Exists*`, bare `.Set(`/`.Add(` on other receivers, comments and strings<br>- index-consistency test (every wrapper method exists and `is_mutating`) |
| FR-003 | the same file: alias, facade and Step 2b cases mirrored from `test_issue130_facade_receiver_write_gate.py` |
| FR-004, FR-005, FR-006, FR-007 | `tests/test_exclusive_access_gate.py` (probe mocked): each row of the data-model gate table, including write-enabled plus certified read-only (the probe is forced), `unknown` refusal, `project_locked` precedence, and read-only runs not gated |
| FR-008, FR-010 | the same file: detail content, and the hint present for the code |
| FR-009 | the same file: `validate_only` reports `exclusive_access.blocking` |
| FR-011 | `tests/test_shared_mode_lock_diagnosis.py`, extended: `open_shared` gets no "Close FieldWorks" text |
| FR-012 | `tests/test_response_contract.py` (code count 47, maps), the golden fixture, the doc-count regex |
| FR-013 | `tests/test_shared_mode_write_gate.py`, extended: the advisory text no longer carries the CF/WS warning |
| FR-014, FR-015 | live evidence V1-V3 and V7 in `evidence/live-gate.md` |
| FR-020, FR-021, FR-026 | `tests/test_docs_no_undo_claims.py`: no `undo_last_operation` and no "can reverse a write" in `docs/`, `USAGE.md`, `README.md` or `tool_definitions.py` |
| FR-022 to FR-024 | `tests/test_docs_no_undo_claims.py`: SHARED-MODE.md has the required phrases, and the table categories match `EXCLUSIVE_ONLY_OPERATIONS` |
| FR-025 | CHANGELOG review (merge requirement) |
| FR-030, FR-031 | live V5. If the step ships, a unit test that the generated runner contains the guarded sync call only when write-enabled and `open_shared`; and an `admin.py` note-text test |
| FR-040, FR-041 | filing ledger in `issues/filing-ledger.md` (each item has an outcome). **Not an automated test**; this is `needs-human` work |
| R8 (filing path) | `tests/test_exclusive_access_detect.py`: the detector over the `filing/` sources gives zero matches |

## Scenario-to-test map

| Scenario | Test |
|---|---|
| 1.1, 1.2 | `test_exclusive_access_gate.py`: `open_shared` + WS wrapper / CF wrapper / raw name gives a refusal before any subprocess (the spawn mock is not called) |
| 1.3 | same file: `free` and `stale_lock` with matches are **not refused** by the gate |
| 1.4 | same file: `open_exclusive` / `held_by_other` with matches give `project_locked`, not the new code |
| 1.5 | same file: write-enabled plus certified read-only plus a match forces the probe and gives a refusal |
| 1.6 | `test_exclusive_access_detect.py`: calls inside comments and strings give no match; a call inside `if False:` still matches |
| 1.7 | `test_exclusive_access_gate.py`: `validate_only` gives `exclusive_access.blocking == true`; when the probe is unavailable, `blocking is None` |
| 1.8 | same file: read-only run plus a call **guarded** by `if modifyAllowed:` is not gated |
| 2.1 | same file: the `_ASSISTANCE_HINTS_BY_ERROR_CODE` entry exists, and a retry loop gets it |
| 2.2 | `test_shared_mode_lock_diagnosis.py`: an `open_shared` open failure gives no "Close FieldWorks" text |
| FR-006 | `test_exclusive_access_gate.py`: `unknown` refuses only when there are matches; an ordinary write on `unknown` is unchanged |
| R2 inputs | `test_exclusive_access_detect.py`: matches drawn from each of `mutating_calls`, `protected_calls`, `unknown_calls` and the Step 2b `unresolved_receiver` rows |

## Phases (checkpoints for `/speckit-tasks`)

1. **Detector** (US1). `server/exclusive_access.py` holds the table, the
   match type and `detect_exclusive_only_operations`. Tests:
   `test_exclusive_access_detect.py`.
2. **Gate and contract** (US1, US2):
   - Wire into `handle_run_module`: detect first, force the probe, refuse
     before confirmation.
   - Add the `validate_only` key.
   - Add the detail model, the union entry, the golden fixture and the
     `session.py` hint.
   - Update the count from 46 to 47 at every site (as built: 47 -> 48,
     because main's `unknown_method` (#306) took the base to 47 first):
     - `tests/test_response_contract.py:522` and its history comment
       `:515-521`;
     - `tests/test_parser_error_models.py:503`;
     - `docs/TOOL-CONTRACT.md:82`, which the regex at
       `test_response_contract.py:529` reads;
     - the `response_models.py:25` header;
     - the stale "44" at `TOOL-CONTRACT.md:721`.
     Finish with `grep -rn "== 46"` and `grep -rn "46 codes"` both returning
     nothing (as built: `== 47` / `47 codes`).
   - `tests/evals/test_corpus.py:40` (`ALL_PREFLIGHT_CODES`) and
     `tests/evals/preflight_runner.py:238`: **not applicable**. The gate is
     probe-based, not a preflight validator, so the new code is deliberately
     left out of those lists.
   - Change `_probe_access = needs_lock or (not write_enabled)`
     (`execution.py:5258`) to also probe when `write_enabled` and the
     detector matched. The test asserts the probe was called.
   - **Ordering**: the detector runs before the confirmation gate (`:5285`),
     and the refusal fires there **only** for `open_shared` / `unknown`.
     `open_exclusive` / `held_by_other` fall through untouched to the
     existing `project_locked` refusal (`:5376-5423`), so scenario 1.4 and
     FR-007 hold. The `_release_own_worker_or_refuse` re-probe (`:5384`) can
     only change a `held_by_other` verdict, which this gate does not act on.
     A test pins that the gate uses the first decision.
   - `validate_only`: the new sub-key handles the probe-unavailable branch
     (`:2507`, `:2516`) by reporting `blocking: null`, like `project_lock`.
   - Tests: `test_exclusive_access_gate.py`, `test_response_contract.py`.
3. **Message alignment** (US2, FR-011, FR-013). Fix the `open_shared`
   diagnose fallback, the `write_ladder` fallback text and the advisory text.
   - **Pattern audit**, recorded in the commit body. Candidates:
     `execution.py:1267`, `write_ladder.py:157`, the advisory at
     `write_ladder.py:172-179`, `project_discovery.py:398`,
     `project_discovery.py:419` and `handlers/teardown_recovery.py:180`.
     Stale-lock and dead-PID text may legitimately stay. Say why for each one
     kept.
   - Run the `sweep-pattern` skill on the detector's own shape (matching on
     receiver and name, telling roles apart), since that bug class has come
     back before.
4. **Docs** (US4):
   - `workflow-summary.md`: remove Stage 6 undo.
   - Style guide `:688-693`.
   - SHARED-MODE.md: the gate is shipped; four undo facts; navigate away and
     back; fix the "upstream not yet filed" line after Phase 7.
   - Review `tool_definitions.py` undo wording.
   - CHANGELOG.
   - `test_docs_no_undo_claims.py`.
5. **Live verification** (US1, US2; `requires_flex`): V1-V4 and V6 on Sena 3.
   `evidence/live-gate.md` MUST record, for each step:
   - `run_mode: live`, cross-checked against `tests/live_status.json`;
   - the exact command, with `FLEXLIBS_REQUIRE_LIVE=1`;
   - pre/post field values re-queried from LCM (the V4 gloss before and
     after, the V3 WS list before and after, the V1 `.ldml` mtimes);
   - cleanup confirmation by a read-only listing.
6. **Sync-at-open** (US5, conditional): run V5 first. If it is positive, add
   the runner step and its test. Either way, update the `admin.py` read-back
   note.
7. **Custom-field live test and filing** (US3, US6; `needs-human`):
   - V7 harness and evidence.
   - Check the four upstream hazards plus the R3 comment note against
     flexicon.
   - Triage the archived drafts into `issues/filing-ledger.md`.
   - File only with the maintainer's OK.

Phases 1-4 are the MVP. Phases 5-7 need FieldWorks or a human.

## Project Structure

### Documentation (this feature)

```text
specs/exclusive-access-gate/
├── spec.md
├── plan.md              # this file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/requires_exclusive_access.md
├── checklists/requirements.md
├── reviews/             # domain gate, plan gate, later QC
├── evidence/            # live-gate.md (phase 5-7)
├── issues/              # filing-ledger.md (phase 7)
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/flextoolsmcp/server/
├── exclusive_access.py          # NEW: table + detector
├── validators.py                # read-only: certifier rows reused
├── write_ladder.py              # advisory + fallback text
├── session.py                   # assistance hint
├── response_models.py           # RequiresExclusiveAccessDetail, AnyDetail
└── handlers/
    ├── execution.py             # gate seam (~:5257), validate_only (~:2466), diagnose (~:1265), runner sync (~:4889)
    └── admin.py                 # shared_mode_read_back note

tests/
├── test_exclusive_access_detect.py   # NEW
├── test_exclusive_access_gate.py     # NEW
├── test_docs_no_undo_claims.py       # NEW
├── test_response_contract.py         # count + maps
├── test_shared_mode_lock_diagnosis.py
├── test_shared_mode_write_gate.py
├── make_golden.py + golden/responses/requires_exclusive_access.json

docs/  SHARED-MODE.md, TOOL-CONTRACT.md, workflow-summary.md, FLEXTOOLS-STYLE-GUIDE.md
CHANGELOG.md
```

**Structure Decision**: Single project, existing layout. The only new source
file is `server/exclusive_access.py`. It keeps the table and the detector out
of the 8.5k-line `validators.py`, while reusing that file's certifier output.

## Open items for the maintainer

- **No tracking issue exists for this feature.** Regression tests are named
  for the feature until one is filed.
- **The constitution I undo sentence (R10).** Amend it separately.

## Complexity Tracking

No violations.

## Review trail

- after_specify domain gate: `reviews/specify-domain.md`.
- after_plan QC gate (2026-09-30): one BLOCKING finding (the missed count site
  `test_parser_error_models.py:503`) and non-blocking gaps N1-N5. All were
  folded into this plan: the count sites, the scenario map, the probe-forcing
  change, the ordering note, the live evidence shape and the audit
  candidates. See `reviews/plan-qc.md`.
