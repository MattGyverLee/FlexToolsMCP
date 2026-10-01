# CP2 implementation report (issue #93)

## Task status
- T2.1 New `src/flextoolsmcp/server/project_access.py` -- done. Pure stdlib
  (json, ctypes, xml.etree, os, pathlib, dataclasses). Reuses
  `get_projects_directory()` / `_FWDATA_EXT` from `project_discovery.py`.
- T2.2 `read_lock_holder()` -- done. Returns `None` only when no lock file
  exists; empty/non-JSON/non-object/missing-key/wrong-type lock content
  returns `LockHolder(None, None, None)` rather than raising.
- T2.3 `_pid_is_alive()` -- done, stdlib only. Windows:
  `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`; treats `GetLastError() ==
  ERROR_ACCESS_DENIED` as alive (higher-privilege process), closes the
  handle on success. POSIX: `os.kill(pid, 0)`. No psutil.
- T2.4 `is_project_sharing_enabled()` -- done. Missing file -> `False`;
  parse error -> `None`; parses but attribute absent -> `False`; value
  compared as lowercase string, not truthiness.
- T2.5 `probe_project_access()` -- done, see decision table below.
- T2.6 `sweep_stale_locks()` rewritten on `read_lock_holder` +
  `_pid_is_alive` -- done, detection-only, no deletion.
- T2.7 `flextools_health(verbose=True)` -- done: `_build_project_lock_block`
  replaced by `_build_project_access_block`; verbose key renamed
  `project_lock` -> `project_access`.

## Shapes
`LockHolder(pid, process_name, timestamp_ticks)` -- all `Optional`.
`ProjectAccess(project_name, verdict, sharing_enabled, holder, lock_age_seconds)`.

## Verdict decision table (as implemented)
| pid_alive | ProcessName=="FieldWorks" | sharing_enabled | verdict |
|---|---|---|---|
| no lock file | -- | -- | `free` |
| False (dead) | either | either | `stale_lock` |
| True | yes | True | `open_shared` |
| True | yes | False/None | `open_exclusive` |
| True | no | either | `held_by_other` |
| unknown (no parseable PID) | -- | -- | `open_exclusive` |

Dead always wins over identity (matches the live Target example: PID
54480/"python", dead -> `stale_lock`, not `held_by_other`). Unknown-holder
falls back to `open_exclusive` -- deliberately conservative, matching
pre-CP2 blunt behavior (any existing lock == treat as held) rather than
risk declaring free.

## Ticks and `__type`
`_ticks_to_age_seconds()` uses `datetime(1,1,1) + timedelta(microseconds=
ticks/10)` vs `datetime.now()`; returns `None` on missing/garbage ticks
(caught via `OverflowError/ValueError/TypeError/OSError`). Verified against
the live value `639222387834226079` -> 2026-08-13, not an epoch-scale
absurdity. `read_lock_holder` ignores unknown keys (`__type`) by construction
(only reads `PID`/`ProcessName`/`Timestamp`).

## Deviations from SPEC
- None substantive. One judgment call not spelled out in SPEC: the
  "unknown holder" fallback verdict (`open_exclusive`) and treating
  `sharing_enabled is None` as falsy for verdict purposes only (the raw
  tri-state is preserved in the returned field). Documented in the module
  docstring.
- Renamed the `flextools_health` verbose key `project_lock` ->
  `project_access` per T2.7's "replace ... with a project_access block";
  updated the one assertion in `tests/test_flextools_health.py` that
  referenced the old key (not on the forbidden list; directly tests code I
  changed).

## `sweep_stale_locks()` warning-string changes
Only for lock files with a parseable PID: new format `"Lock detected: {path}
({age} old), held by {ProcessName} (PID {pid}), process {still
running|no longer running (stale)}. Close FieldWorks..."`. The
empty/unparseable-holder path is untouched byte-for-byte (`"Stale lock
detected: {path} ({age} old). Close FieldWorks..."`), so
`tests/test_startup_lock_sweep.py` (which writes empty lock files) needed
no changes and passes unmodified.

## Tests
New `tests/test_shared_mode_access.py` (30 tests): `read_lock_holder`
(real-shaped JSON incl. `__type`, empty, non-JSON, missing keys, array-not-
object), `_ticks_to_age_seconds` (known tick value, missing, garbage/
overflow), `is_project_sharing_enabled` (true/false/missing/malformed/
missing-attribute), `probe_project_access` (all 5 verdicts incl. the dead-
python-process Target case and unresolvable-projects-dir), `_pid_is_alive`
smoke test (own PID / non-positive), and `sweep_stale_locks` holder-aware
messages (live/dead/non-FieldWorks + empty-lock regression guard).

`pytest -q`: **1008 passed, 4 skipped** (clean). One transient failure was
observed on an earlier run in `test_response_contract.py::TestMakeGolden::
test_make_golden_dry_run_passes` -- traced to a parallel, uncommitted
workstream already present in this tree (adding a 17th `nested_unit_of_work`
error code to `response_models.py`/`validators.py`/`execution.py`/
`make_golden.py`/`test_response_contract.py`, all files I'm forbidden to
touch); it resolved on rerun once that concurrent edit settled and is
unrelated to CP2. I did not touch any of those files.

## Proposed CHANGELOG text (not applied -- file is off-limits this cycle)
```
### Added
- Shared-mode access probe (`server/project_access.py`): detects whether a
  FieldWorks project is free, shared, exclusively held, stale-locked, or
  held by a non-FieldWorks process, by reading `.fwdata.lock` JSON and
  `LexiconSettings.plsx` -- no LCM/pythonnet involved. Detection only this
  cycle; no gate behavior changes yet. (#93)
- `sweep_stale_locks()` now names the lock holder's process and whether it
  is still running. `flextools_health(verbose=True)`'s `project_access`
  block exposes the full verdict.
```
