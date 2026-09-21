# Cycle 1 -- Explore: adoption call-site + test inventory

Feature: project-adoption (issues #168 / #169 / #170)
Mode: read-only recon. No source files were edited.
Note: authored by the Explore agent, which has no write tool; persisted
verbatim by the main session.

## Call sites

`resolve_or_explain` is defined at
`src\flextoolsmcp\server\project_discovery.py:449` (wrapping
`resolve_project_name` at `:228`). There are exactly **5** call sites in
`src\`, of which **3** write session state and **1** is a hidden 4th
adoption path:

1. `src\flextoolsmcp\server\handlers\execution.py:2837` -- guard at
   `:2851` `if resolved and resolved != project_name:` -> writes
   `session_state.project_name = resolved` at `:2853`. **Session write-back.**
2. `src\flextoolsmcp\server\handlers\grammar_health.py:248` -- guard at
   `:258` -> writes at `:259`. **Session write-back.**
3. `src\flextoolsmcp\server\handlers\parse.py:316` (inside
   `_resolve_project`, defined `:289`) -- guard at `:326`
   `if resolved and resolved != name:` -> writes at `:327`.
   **Session write-back.**
4. `src\flextoolsmcp\server\handlers\admin.py:497` (`flextools_start`) --
   **the 4th site.** Same `if resolved and resolved != project_name:`
   guard at `:507`, but it does NOT assign `session_state.project_name`;
   it rebinds the local at `:518` and the name reaches the session
   indirectly via `session_state.configure(project_name=project_name, ...)`
   at `:547-550`. Because `configure()` always assigns
   (`session.py:286-287`), admin.py is already effectively unconditional --
   the guard there only controls the `[SESSION-START] project_name
   autocorrected` log line at `:514-517`. Making the other three
   unconditional brings them in line with admin.py.
5. `src\flextoolsmcp\server\handlers\execution.py:1425` -- error-shaping
   only (`_resolved` discarded, payload reused for suggestions). No
   session write; not an adoption site.

`resolve_project_name` has no callers outside `project_discovery.py:459`.

## Other `session_state.project_name` writers

- `src\flextoolsmcp\server\session.py:287` -- `configure()` assigns from
  the `project_name` kwarg whenever the key is present (incl. `""`); this
  is the canonical writer and is unconditional.
- `src\flextoolsmcp\server.py:906-910` -- cold-start auto-init calls
  `configure(..., project_name=cold_project_name or "")`, i.e. writes
  `""` for read-only tools and the caller-supplied name for cold
  `flextools_run_module`; then `record_auto_init()` at `:911`.
- `src\flextoolsmcp\server\handlers\admin.py:547-550` -- see call site 4.
- Non-session (unrelated, same attribute name on other objects):
  `src\flextoolsmcp\server\parse\worker_client.py:135`,
  `src\flextoolsmcp\server\parse\worker_main.py:938`.

## Affected tests

Direct resolver/adoption contract:

- `tests\test_project_discovery.py:132-223` -- `resolve_project_name`
  reason table (`exact`/`normalized`/miss/empty) and the four
  `test_resolve_or_explain_*` cases at `:200,206,212,222`. Most likely to
  need a new "exact match still adopted" companion.
- `tests\test_issue47_auto_discovery.py:326-343` -- asserts
  `s.project_name == "ProjectB"` after a project change; also
  same-project-restart continuity at `:310-324`.
- `tests\test_mcp_tools.py:288-300` -- asserts
  `srv.session_state.project_name == ""` after cold read-only auto-init;
  `:302-341` auto_init_count; `:404-416` `project_name_required` +
  inlined `available_projects`.

Cold-start / hint strings:

- `tests\test_issue53_cold_start.py` -- `TestAutoInitCounter` (`:34-84`),
  `TestAssistanceHintsPointToAvailableProjects` (`:86-105`, reads
  `_ASSISTANCE_HINTS_BY_ERROR_CODE["project_name_required"]` and
  `["project_not_open"]`), `TestAvailableProjectsPayload` (`:111-165`).
- `tests\test_retry_loop_detection.py:141-155` -- `project_not_open` hint
  must mention `available_projects`.
- `tests\test_issue10_session_persistence.py:119-206` -- asserts
  `session_state.initialized` survives failures; autouse fixture at
  `:124-130` patches `resolve_or_explain` as a module attribute on
  `exec_mod`/`admin_mod` with `raising=False`. **Latent trap:**
  `execution.py` imports `resolve_or_explain` *inside* the function
  (`:2834`), so that patch is a no-op there; only the `admin_mod` half
  binds (admin imports at module level, `:52`). Any rewrite of the
  execution.py block must not assume this fixture is neutralising the
  resolver.
- `tests\evals\preflight_runner.py:219,253-256` and
  `tests\evals\test_corpus.py:41` +
  `tests\evals\corpus\13_reject_project_name_required.yaml` -- mirror the
  `project_name_required` gate ordering.
- `tests\test_parse_live.py:308` -- treats
  `project_name_required`/`project_not_found` as skip codes.

Tests that monkeypatch `project_discovery.resolve_or_explain` to
`lambda name: (name, None)` (i.e. force the "exact, unchanged" branch --
these are exactly the tests whose behaviour flips from "no write" to
"write" under an unconditional change):
`tests\test_diagnostic_report_reconstruction.py:660`,
`tests\test_diagnostic_report_transport.py:643`,
`tests\test_issue103_hvo_stability.py:182`,
`tests\test_issue40_casting_severity.py:52`,
`tests\test_issue49_validate_only.py:501,619`,
`tests\test_issue55_write_safety_ladder.py:49-52,184,228`,
`tests\test_issue96_teardown_visibility.py:72`,
`tests\test_nested_uow_gate.py:173`,
`tests\test_shared_mode_write_gate.py:145`,
`tests\test_issue92_write_path_e2e.py:108,215`.

Parse-path tests that stub `_resolve_project` wholesale (bypass the guard
entirely, so they are insulated from the change but will mask
regressions): `tests\test_try_word_handler.py:274-278,818,858,1023,1083,1259,1295`,
`tests\test_parse_status_handler.py:73,125,162,256`,
`tests\test_parse_proposal.py:103`,
`tests\test_spec16_deferred_groups.py:190,215,269`.

## Uncommitted-file overlap

`git status --short` shows in-flight parser-check-CP2b work. Overlap with
the above:

- **Source, modified:** `src\flextoolsmcp\server\handlers\parse.py`
  (contains adoption site 3 at `:316-328`) and
  `src\flextoolsmcp\server.py` (cold-start auto-init at `:906-911`).
  Edit these two with care / coordinate.
- **Source, clean:** `execution.py`, `grammar_health.py`, `admin.py`,
  `session.py`, `project_discovery.py` -- safe to edit.
- **Tests, modified (avoid disturbing):** `tests\test_mcp_tools.py`,
  `tests\test_try_word_handler.py`, `tests\test_parse_status_handler.py`,
  `tests\test_parse_proposal.py`, `tests\test_parse_worker_lifetime.py`,
  `tests\test_grammar_scan_checks.py`,
  `tests\test_cross_session_logging.py`. Plus untracked
  `tests\test_summarize_trace.py`.
- **Tests, clean (safe to extend):** `test_project_discovery.py`,
  `test_issue53_cold_start.py`, `test_issue47_auto_discovery.py`,
  `test_issue10_session_persistence.py`, `test_retry_loop_detection.py`,
  `test_issue55_write_safety_ladder.py`, `test_issue49_validate_only.py`,
  `test_spec16_deferred_groups.py`, and the `tests\evals\*` set.

Recommended landing order: put new coverage in `test_project_discovery.py`
+ `test_issue53_cold_start.py` (both clean), change `execution.py` and
`grammar_health.py` first (clean), and defer the `parse.py:326` guard
until CP2b's parse.py changes settle.
