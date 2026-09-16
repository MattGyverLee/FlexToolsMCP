# T030 -- programmer report

**Seam added** (both new, additive-only) in
`src/flextoolsmcp/server/handlers/execution.py`, placed between
`handle_run_module` and `handle_get_operation_logs` -- not inside either:

- `_build_scan_script(module_import_path, function_name, project_name, write_enabled) -> str`
  -- builds the subprocess script text. Header (4 `repr()`'d globals) via
  `.format()`; the harness body is a STATIC triple-quoted string (no further
  interpolation, no brace-escaping needed).
- `async def run_scan_module(module_import_path, function_name, project_name, write_enabled=False, timeout_seconds=300) -> Dict[str, Any]`
  -- the callable seam T020 will use.

**Reuse, not a second mechanism.** Launch is the literal same
`run_script_async` (`subprocess_helpers.py`) `handle_run_module` calls --
same `sys.executable`, same `env=None`. The generated script's "module
code" is the fixed one-liner D11 specifies: `importlib.import_module(...)`
+ `getattr(scan_mod, function_name)(project)` + `report.Result(findings)`,
never caller-supplied text -- so none of the AST/casting/CUD preflight
chain is needed or invoked. Findings ride the SAME
`===FLEXTOOLS_USER_RESULT===` sentinel; the run envelope rides the SAME
`===FLEXTOOLS_RESULT_JSON===` sentinel, parsed with logic mirroring
`execution.py`'s existing block (search "Issue #35"). No second result
channel was invented.

**"Never ran" vs "ran, zero findings":** the return dict always carries
`ran` and `success` separately. `ran=False` (`error_type` one of
`Timeout`, `NoResultMarker`, `JSONDecodeError`) means no parseable envelope
came back at all. `ran=True, success=True, findings=[]` is a legitimate
empty result. `ran=True, success=True` requires the scan to have actually
called `report.Result(...)`; if it didn't, that's `MissingFindingsPayload`
(a scan-module bug), never silently treated as "no findings". Project-open
/ import / attribute failures get their own `error_type`s
(`ProjectOpenError`, `ScanModuleImportError`, `ScanFunctionNotFound`).

**`handle_run_module` untouched** -- confirmed by diff: only insertions
after its closing `finally:` block; no line inside the function body was
touched.

**Verified:**
- `ruff check` on the file: clean.
- Generated script parses (`ast.parse`) for representative inputs.
- Real end-to-end run (real `sys.executable` subprocess, real
  `flexicon.FLExProject.OpenProject`, no live project available in this
  environment) against a nonexistent project name: returned
  `ran=True, success=False, error_type="ProjectOpenError"`, confirming the
  subprocess launch, flexicon import, and sentinel round-trip all work for
  real, not just as a code-read.
- All six branch cases (`success` w/ empty findings, `MissingFindingsPayload`,
  `NoResultMarker`, `Timeout`, `JSONDecodeError`, scan-reported-failure)
  exercised by monkeypatching `run_script_async` to return canned
  stdout/timeout combinations and calling `run_scan_module` -- all matched
  the designed contract.
- **Not verified:** the success path against a real `grammar_scan_module`
  returning real findings from a live FieldWorks project -- no such
  project/module exists in this dev environment (module lands at
  T019/T034/T035). That remains T020/integration's job.

**Full-suite delta:** `python -m pytest tests/ -q` -- 104 failed / 1515
passed (same run before my change, isolated via `git stash push -- .../execution.py`,
also fails identically) except this file's diff is additive-only. Failures
decompose as: `test_parser_health_block.py`, `test_grammar_scan_checks.py`,
`test_parser_engine_gate.py`, `test_parser_agent_probe.py`, and part of
`test_grammar_health.py` (all explicitly pre-declared RED, pending
T012/T013/T019/T020/T024/T025/T034/T035). One extra failure,
`test_mcp_tools.py::TestToolRegistration::test_tool_count`, is caused by a
concurrent T018 tool-registration change already in the working tree
(`tool_definitions.py`, +22 lines uncommitted) registering
`flextools_grammar_health` ahead of `EXPECTED_TOOL_COUNT` being bumped --
confirmed unrelated to this task by stashing only `execution.py` and
re-running: the failure persists identically. All pre-existing execution.py
tests (`test_auto_fix`, `test_issue47_auto_discovery`,
`test_issue49_validate_only`, `test_issue80_graceful_redirect`,
`test_issue82_writeability_reject_logging`,
`test_issue84_project_lexsense_accessor`, `test_rejection_payloads`,
`test_shared_mode_lock_diagnosis`, `test_info_message_cap`,
`test_issue103_hvo_stability`, `test_nested_uow_gate`,
`test_issue10_session_persistence`, `test_v1_3_0_upgrade`) pass unchanged.
