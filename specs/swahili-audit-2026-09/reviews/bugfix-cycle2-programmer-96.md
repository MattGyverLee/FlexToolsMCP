# Programmer -- #96 MCP-side fix (A-7, A-8), bugfix cycle 2

Commit: `0c9a59b777bc7eaedb3db329357544947ff8bd7b` on `feat/shared-mode-access`.

## Files + lines changed

- `src/flextoolsmcp/server/handlers/execution.py` -- inside the generated
  runner-script template (`run_module()`):
  - Moved `report = SimpleReporter()` up before the `flexicon` imports so
    setup-time warnings (the `ui=` fallback) and the `OpenProject` failure
    path both have somewhere to report to.
  - New guarded import block (`try: from flexicon.code.headless_ui import
    HeadlessLcmUI ... except ImportError: _lcm_ui = None`) and
    `OpenProject(..., ui=_lcm_ui)` (was: no `ui=` arg at all).
  - `finally:` block: replaced the bare `except: pass` after
    `project.CloseProject()` with `except Exception as e:` that demotes
    `result["success"]` to `False`, sets `error_type = "TeardownError"`,
    appends (not clobbers) `result["error"]`, and stores the full
    type/message/traceback under `result["teardown_error"]`.
- `src/flextoolsmcp/server/handlers/admin.py` -- added a
  `shared_mode_read_back` entry to `RUNTIME_PRIMER`, same shape as the
  existing `hvo_stability` entry (description/why/note).
- `tests/test_issue96_teardown_visibility.py` (new, 8 tests, all pass, none
  need live FieldWorks).

## Version-gating mechanism (A-8)

Matched this repo's existing convention (dozens of sites, e.g.
`admin.py`, `catalog.py`, `api.py`) of `try: from X import Y / except
ImportError:`. On success, `_lcm_ui = HeadlessLcmUI()` is passed to
`OpenProject`. On `ImportError` (older flexicon build without
`flexicon.code.headless_ui`), `_lcm_ui = None` -- identical to
historical behavior -- and `report.Warning(...)` emits a visible message
naming the hazard (a `ConflictingSave()` can hang) rather than degrading
silently. This warning flows through the existing `messages`/`summary`
machinery, so it reaches the caller with no new response-envelope key.

## Primer wording (Deliverable 3)

`shared_mode_read_back.description`: *"In FLEx's shared-mode setup, a
fresh read-only session under a live FLEx master shows the last master
save, not your write."* The `why` field explains the commit-log/master
mechanism and states explicitly: *"there is NO reliable interval and NO
retry count that guarantees the write has become visible -- the window
is unbounded."* No seconds, no interval, no retry count anywhere in the
entry (locked by a test).

## Verification

Manually executed the actual generated runner script (extracted via a
monkeypatched `run_script_async`) as a real subprocess against a tiny
fake `flexicon` package for all three paths: normal close (`ui=
HeadlessLcmUI()` passed, success), `CloseProject()` raising (success ->
False, `error_type=TeardownError`, exception text present, not
swallowed), and `headless_ui` absent (falls back to `ui=None`, emits a
WARNING message, still succeeds). All three are now locked by
`tests/test_issue96_teardown_visibility.py`.

`python -m pytest -q`: **1049 passed, 4 skipped** (baseline 1041 + 8 new
tests, exact match). Did not hit the known
`test_flextools_health.py` mtime flake this run.

## Could not touch / out of scope

Nothing needed a flexicon edit -- `HeadlessLcmUI` and `OpenProject(...,
ui=None)` already ship there. Did not touch validators.py, the casting
gate, or the #103 hvo gate per the lock set. The staleness root cause
itself (unbounded read-after-write window) is unfixed -- that requires
the authorized live repro, which is still blocked on the user flipping
`Target`'s `projectSharing` and parking FLEx on a non-editing view.
