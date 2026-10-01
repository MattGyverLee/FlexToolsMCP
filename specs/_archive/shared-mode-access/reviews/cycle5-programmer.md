# Cycle 5 -- Programmer report: CP3 T3.1-T3.4 (issue #93)

## Files changed
- `src/flextoolsmcp/server/project_access.py`
  - docstring update (lines ~24-32)
  - new `build_lock_diagnosis(access)` (inserted before `_is_fieldworks_process_name`, ~lines 240-284)
- `src/flextoolsmcp/server/handlers/execution.py`
  - `_diagnose_project_open_error`, locked-marker branch rewritten, lines ~1204-1265
- `tests/test_cp3_lock_diagnosis.py` (new, 6 tests)

Commit: `6677fd8` ("fix(#93): CP3 T3.1-T3.4 -- wire probe_project_access into project-locked diagnosis")

## Stale-lock wording-ownership decision
Added a sibling, `build_lock_diagnosis()`, in `project_access.py` rather than widening `build_access_remedy()`. Evidence: CP4's write gate (`execution.py:4180`) dispatches refusal on `access.verdict in ("open_exclusive", "held_by_other")`, not on `remedy is not None` -- so widening would not have changed CP4's *control flow*. But `tests/test_shared_mode_write_gate.py::TestBuildAccessRemedy::test_non_blocking_verdicts_have_no_remedy` (line 77-80) directly asserts `build_access_remedy(...) is None` for `["free", "open_shared", "stale_lock"]`; widening would break that existing, passing test outright. `build_lock_diagnosis()` delegates to `build_access_remedy()` for the two blocking verdicts (wording can never drift between CP3/CP4) and supplies new text only for `stale_lock`.

## Fallback table (verdict -> emitted keys on `diag`)
| verdict | hint | verdict/sharing_enabled/holder_pid/holder_process | remedy |
|---|---|---|---|
| `open_exclusive` | enable-sharing recipe (or unreadable-holder text) | set | `build_access_remedy()` text (== hint) |
| `held_by_other` | collision message naming PID/process | set | `build_access_remedy()` text (== hint) |
| `stale_lock` | names dead PID, says lock is stale, retry | set | `None` (nothing to DO) |
| `free` / `open_shared` / unrecognized | generic "Close FieldWorks" (unchanged) | **not set** | **not set** |
| probe import/call raises | generic "Close FieldWorks" (unchanged) | **not set** | **not set** |

Whole probe+diagnosis block wrapped in one `try/except Exception: pass`, so any failure degrades silently to the pre-existing generic dict (constraint 1).

## Tests added
`tests/test_cp3_lock_diagnosis.py` (new file, not CP2's `test_shared_mode_access.py`, to keep it alongside `test_shared_mode_write_gate.py`'s CP4 convention): `test_open_exclusive_gives_enable_sharing_remedy`, `test_stale_lock_names_the_dead_pid`, `test_held_by_other_is_a_real_collision`, `test_probe_raising_falls_back_to_generic_hint`, `test_non_blocking_verdicts_fall_back_to_generic_hint` (subtests: free, open_shared), `test_unrelated_error_still_returns_none`. All monkeypatch `server.project_access.probe_project_access` via `unittest.mock.patch`; none touch a real projects directory.

## Verification
- `pytest -q`: **1144 passed, 4 skipped** (requires_flex, expected), 14 subtests passed.
- Targeted (`test_shared_mode_access.py test_rejection_payloads.py test_shared_mode_write_gate.py test_nested_uow_gate.py test_cp3_lock_diagnosis.py`): **95 passed, 2 subtests passed**.
- `tests/test_rejection_payloads.py:471` (`Close FieldWorks` in hint) still passes unmodified -- untouched project "Foo" resolves to `free` via the real probe (no monkeypatch in that test), which is a non-blocking verdict and falls back to the generic hint.
- Golden fixture `tests/golden/responses/project_locked.json` / `tests/make_golden.py`: unchanged, no regeneration needed -- CP4's `error_response()` payload shape (the thing the golden covers) was not touched, only the CP3 diagnosis dict.
- Pre-commit hooks (AST syntax, ruff, dual-mode import check, Flexicon Operations load) all passed on commit.

## Deliberately not done
- `response_models.ProjectLockedDetail` (T3.5) untouched, per instructions (already done).
- CP5/CP6 untouched.
- Did not widen `build_access_remedy()` (see decision above).
- Did not add a `hint`/hint-parity field to `ProjectLockedDetail` -- this diagnosis path returns a plain dict merged into `execution_result`, never validated against that pydantic model, consistent with how `project_path_mismatch`/`project_drive_unavailable` diagnoses already work in the same function.
