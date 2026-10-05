# Issue #145 -- flextools_health lock freshness fix (cycle 1, programmer)

## Files changed

- `src/flextoolsmcp/server/handlers/diagnostic_health.py`
  - Added `sweep_stale_locks` import (try/except relative-then-package pattern,
    matching the file's existing style).
  - `_build_warnings()`: replaced `getattr(api_index, "startup_lock_warnings", [])`
    with a direct `sweep_stale_locks()` call on every invocation, with a comment
    mirroring `get_workspace_notice()`'s "not once-per-process gated ... health is
    explicitly diagnostic" wording immediately below it.
  - Updated the module docstring's bullet describing `sweep_stale_locks()` to
    reflect the re-scan (was: "already collected at startup").
- `src/flextoolsmcp/server/validators.py` (`validate_server_state()`, ~line 213)
  - Removed the block that appended `api_index.startup_lock_warnings` as
    `("warning", ...)` tuples. Replaced with a comment explaining the removal.
- `src/flextoolsmcp/server.py`
  - Removed the `startup_lock_warnings: list = field(default_factory=list)`
    field from `APIIndex` (line ~511) -- grepped the whole repo first; after
    the two edits above, nothing reads it anymore (only remaining hits were the
    definition/assignment and a spec review doc).
  - `main()` (~line 1048): kept the `sweep_stale_locks()` call for its
    boot-time WARNING log lines (issue #57 (C) intent), removed the
    `api_index.startup_lock_warnings = ...` assignment, and rewrote the stale
    "so flextools_health can surface them without re-scanning" comment to say
    the opposite: health now re-scans itself.
- `tests/test_flextools_health.py`
  - New `TestLockWarningFreshness` class, 3 tests (see below).

## validators.py decision: drop the block

Chose **drop** over **re-sweep**. `validate_server_state()` is a preflight
check of the server's *own* module-import/init state, invoked by
`execution.py` before running user code (I did not touch `execution.py` per
the task boundary -- only the function body in `validators.py`). Lock
warnings are non-fatal (`severity="warning"`, never affects `is_healthy`) and
orthogonal to "is the server's own state ready" -- a stale FLEx lock doesn't
block code execution. Re-sweeping here would add a filesystem directory scan
to every code-execution preflight for a value that's already available,
fresher, from `flextools_health`. Dropping it leaves exactly one caller of
`sweep_stale_locks()` in any response path (`diagnostic_health.py`), which
structurally guarantees the two paths can no longer disagree -- rather than
relying on two call sites staying manually in sync.

## Tests added (`tests/test_flextools_health.py::TestLockWarningFreshness`)

1. `test_lock_appearing_after_startup_is_reported` -- no lock at simulated
   startup, lock created afterward, `handle_flextools_health()` still reports it.
2. `test_lock_removed_after_startup_is_not_reported` -- lock present at
   simulated startup, released before the health check, `handle_flextools_health()`
   does NOT report it (proves no frozen-snapshot replay).
3. `test_validate_server_state_does_not_duplicate_lock_warnings` -- confirms
   `validate_server_state()` no longer emits its own lock-warning copy.

Both used `FW_PROJECTS_DIR` env var + real `.fwdata.lock` files on disk,
following the existing convention in `tests/test_startup_lock_sweep.py`.

## Suite results

`uv run python -m pytest -q`: **1150 passed, 1 failed, 4 skipped**.

The 1 failure (`test_issue100_access_path.py::TestKnownOperationsImportInvariant::
test_known_operations_disjoint_from_full_facade_only_set`) is pre-existing and
unrelated: an environment-dependent tripwire comparing `KNOWN_OPERATIONS`
against the locally installed flexicon package's live class set (fails because
this environment's installed flexicon version lacks `MSAOperations`). None of
issue #145's touched files (`diagnostic_health.py`, `validators.py`,
`server.py`, `project_discovery.py`) are involved. Targeted re-run of
`test_flextools_health.py`, `test_startup_lock_sweep.py`,
`test_shared_mode_access.py`, `test_mcp_tools.py`: **81 passed**.

`execution.py` was not opened or modified.
