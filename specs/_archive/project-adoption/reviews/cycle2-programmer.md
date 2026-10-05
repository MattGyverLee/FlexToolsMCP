# Cycle 2 -- Programmer report (project-adoption, issues #168/#169/#170)

## Files changed (path:line)

- `src\flextoolsmcp\server\handlers\execution.py:2851-2864` -- guard changed
  `if resolved and resolved != project_name:` -> `if resolved:`; added
  `[PROJECT-ADOPTED]` log (module-scope `get_operations_logger`, already
  imported at line 44).
- `src\flextoolsmcp\server\handlers\grammar_health.py:258-274` -- same guard
  change; added `[PROJECT-ADOPTED]` log via function-local
  `from ..kernel import get_operations_logger` (module had no prior logging
  import).
- `src\flextoolsmcp\server\handlers\parse.py:326-341` (`_resolve_project`,
  local var `name`) -- same guard change + log, function-local kernel
  import. Nothing else in parse.py touched (dirty CP2b work at 465+ left
  alone).
- `src\flextoolsmcp\server\session.py:48-64` -- reworded
  `project_not_open` and `project_name_required` hints per spec text.
  Both keep `available_projects`/`project_name` substrings; neither
  contains `call flextools_list_projects`.
- `admin.py:507` -- untouched, confirmed out of scope.
- `tests\test_issue53_cold_start.py` -- 3 assertions added to existing
  `TestAssistanceHintsPointToAvailableProjects`.
- `tests\test_project_discovery.py` -- new fixtures + 5 test classes
  appended (see below).

## Diff summary

Each of the three sites: capture `_prev_project_name` from
`session_state.project_name` BEFORE overwriting; if non-empty and different
from `resolved`, log
`[PROJECT-ADOPTED] {name}: session project changed '{old}' -> '{new}'`,
guarded for a `None` logger. No new flag anywhere; `configure()`,
`session.py`'s inheritance logic, and `server.py:891-917` untouched.

## Test files + test names added

`tests\test_project_discovery.py` (new, appended after existing unittest
suite):
- `TestExactNameAdoptionPerHandler`: `test_run_module_adopts_and_a_bare_followup_reuses_it`,
  `test_grammar_health_adopts_and_a_bare_followup_reuses_it`,
  `test_try_word_resolver_adopts_and_a_bare_followup_reuses_it`
- `TestIssue169ColdStartThenAdopt::test_empty_start_then_run_module_with_project_then_bare_run_module`
- `TestNoStompRegression::test_adopted_project_does_not_reset_api_mode_or_write_enabled`
- `TestProjectAdoptedLogging`: `test_fires_on_a_genuine_change`,
  `test_does_not_fire_on_first_adopt_from_empty_session`

`tests\test_issue53_cold_start.py` (existing class, 3 new methods):
`test_project_not_open_hint_no_longer_mentions_run_module_parenthetical`,
`test_project_name_required_hint_now_mentions_flextools_start`,
`test_project_not_open_hint_mentions_flextools_start_before_per_op_phrasing`.

The try_word test exercises `parse.py`'s `_resolve_project` directly rather
than round-tripping through `handle_flextools_try_word`'s full
ParseRunner/worker stack, to avoid duplicating the RecordingWorker/Pool
doubles already committed in the dirty `test_try_word_handler.py`.

## Test run results (verbatim)

`test_project_discovery.py test_issue53_cold_start.py`: **40 passed**

Required verification command:
```
tests\test_project_discovery.py tests\test_issue53_cold_start.py
tests\test_issue47_auto_discovery.py tests\test_issue10_session_persistence.py
tests\test_retry_loop_detection.py tests\test_issue55_write_safety_ladder.py
```
-> **84 passed**

The ~12 identity-stub files (`test_try_word_handler.py`,
`test_shared_mode_write_gate.py`, `test_nested_uow_gate.py`,
`test_issue92_write_path_e2e.py`, `test_issue55_write_safety_ladder.py`,
`test_issue49_validate_only.py`, `test_issue96_teardown_visibility.py`,
`test_issue40_casting_severity.py`, `test_issue103_hvo_stability.py`,
`test_issue10_session_persistence.py`, `test_diagnostic_report_transport.py`,
`test_diagnostic_report_reconstruction.py`, plus `test_project_discovery.py`):
-> **294 passed, 2 skipped**. No fallout; no changes needed in any of them.

## Objections

None -- the locked design (unconditional adoption at the three sites, no
new flag, log-only guardrail, reworded hints) was implemented as specified.

## Anything I could not do

Nothing outstanding for the five tasks. One deviation from a literal
reading of Task 5.1 is noted above (try_word tested via `_resolve_project`
directly, not the full handler) -- functionally equivalent since that
function is the entire Task-1 site inside `parse.py`, and flagged rather
than silently substituted.

Did not run the full repo-wide `pytest -q` to completion (kicked off in
background, still running at report time) -- the task's own explicit
verification command, plus the 12 identity-stub files, all ran to
completion and passed.
