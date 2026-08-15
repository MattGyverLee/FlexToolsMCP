# Cycle 1 — Programmer report (CP1)

**Commit:** `d17105f7f4dad11c60b44ab9527ba224bdb4bdc4` on `feat/shared-mode-access` (not merged to main).

## Changes per file

- **`execution.py`**: `OpenProject(...)` hardcodes `undoable=False`; removed the
  `undoable` local var, the `UNDOABLE`/`undoable=repr(undoable)` template
  slots, and the `undo_checkpoints` rollover block (guarded on `write_enabled
  and undoable`). Kept `lcm_undoable_action_count` (read-only diagnostic) and
  the `BeginNonUndoableTask` regex in `validators.py` per the plan.
- **`models.py`**: deleted `undoable` field from `FlexToolsStartInput` and the
  whole `UndoLastOperationInput` class; edited `GetSessionHistoryInput` docstring.
- **`tool_definitions.py`**: removed the "Undoable mode" paragraph from
  `flextools_start`'s description, the `flextools_undo_last_operation` ToolDef,
  and its import; edited `flextools_get_session_history`'s description.
- **`dispatch.py`**: removed all undo wiring (import, constant, `ALL_TOOL_NAMES`
  entry, handler import/binding, `DISPATCH_ROUTES` entry).
- **`handlers/admin.py`**: deleted `handle_undo_last_operation`, the
  undoable-default computation block, the false "reverse across MCP sessions"
  warning, `undo_available`/`redo_available` from `get_session_history`, and 10
  now-dead `KEY_*` constants.
- **`session.py`**: removed `undoable` field/`is_undoable()`/`summary()` key,
  `_UNDO_CHECKPOINT_CAP`, `undo_stack`/`redo_stack`/`undo_checkpoints` fields,
  `record_operation`/`can_undo`/`can_redo`/`pop_undo`/`pop_redo`, and the
  `undoable_count`/`can_undo`/`can_redo`/stack-depth keys from
  `get_history_summary()`. Kept `OperationRecord`/`operations_history`/
  `export_history`/`_extract_operation_details` (general history, not undo).
- **`server/__init__.py`, `handlers/__init__.py`**: dropped the
  `UndoLastOperationInput` re-export and docstring mentions.
- **`undo_subprocess.py`**: deleted.
- **`server.py`** (top-level entry point): fixed a cold-start `undoable`
  call site into `session_state.configure()` that **Explore's map missed**
  (it lives outside `handlers/`); flagging this per the "report, don't
  silently widen scope" instinct even though it wasn't in the D-exception
  category (that exception is specifically for undo-stack call sites, and
  none were found).
- **Tests**: deleted `test_undo_wiring.py`; edited `test_mcp_tools.py`
  (tool-count list, destructive-tools list), `test_issue55_write_safety_ladder.py`
  (deleted `TestRung1UndoableDefault`), `test_issue10_session_persistence.py`
  (dropped `undoable` from start args), `test_v1_3_0_upgrade.py` (replaced the
  undo-tracking assertion with an `operations_history` existence check).
- **New**: `tests/test_issue92_write_path_e2e.py` — `requires_flex`, drives the
  real `handle_run_module` (not stubbed) through `SetGloss` → `CloseProject` →
  reopen → assert persisted. Skips unless `FLEXTOOLSMCP_E2E_SCRATCH_PROJECT` is
  set (verified: collects and reports `1 skipped` with no env var).
- **`CHANGELOG.md`**: `[Unreleased]` entry referencing #92.

## Command results

- `pytest`: **961 passed, 3 skipped** (0 failures).
- `python scripts/validate_integrity.py all`: **all 5 checks passed** (21 tools
  registered, down from 22).
- `python scripts/verify_python.py`: **passed** (same 5 checks).

## Contract change (step E)

New failure shape from the generated-script runner: if `report.messageCounts[ERROR] > 0`,
`result["success"]` is now `False` (previously always `True` when no exception
was raised), plus `result["error_type"] = "ReportedError"` and
`result["error"] = "Operation reported N error(s) via report.Error(); see messages for details."`
This flows through the existing failure path (`_log_operation_failure`,
`error_code = "ReportedError"` in the response) unchanged — no new envelope
keys. `get_session_history` also lost `undo_available`/`redo_available`, and
`flextools_start`'s `session` summary lost the `undoable` key.

## Golden fixtures

None regenerated. `python tests/make_golden.py` (dry run) reported all 19
fixtures up to date — they're built via `error_response()` for 16 static
error codes, none of which touch the run_module success/error dict or
session-history shape.

## Deferred / not done

- **CP6 docs** (`README.md:151`, `USAGE.md:18`, `docs/FLEXTOOLS-STYLE-GUIDE.md:505-510`,
  `docs/workflow-detail.md`, `docs/workflow-summary.md`) still describe
  `flextools_undo_last_operation`/`undoable`. Out of scope for CP1 per
  SPEC.md's checkpoint split; no test depends on them.
- Did **not** run the live CP1 verification (`SetGloss`/`ApplySyncableProperties`
  against a real project) — that requires human authorization per the task
  and the plan's Verification step 1.
