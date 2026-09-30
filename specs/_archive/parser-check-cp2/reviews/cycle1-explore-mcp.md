# cycle1-explore-mcp -- recon for parser-check CP2

Read-only recon of the MCP side. Nothing changed.

## 1. Tool registration path (end to end)

**Declare** -- `src/flextoolsmcp/server/tool_definitions.py`:
- `class ToolDef` at :53 (`name`, `description`, `input_model`, `annotations`,
  optional `output_model`; `get_schema()` at :71 caches `utils.model_to_tool_schema`).
- `READ_ONLY_SAFE = ToolAnnotations(...)` at :81-86.
- `TOOLS: dict[str, ToolDef]` at :93. Nearest precedent = `flextools_grammar_health`
  (CP1) at :498 / :517 region.
- Input model imported from `.models` (:23-46).

**Input model** -- `src/flextoolsmcp/server/models.py`: `class GrammarHealthInput(BaseModel)`
at :564-582 is the pattern (optional `project_name` falling back to session, plain
`Field(default=..., description=...)`). Closed detail models use
`ConfigDict(extra="forbid")` -- e.g. `FoundObject` at :585.

**Route** -- `src/flextoolsmcp/server/dispatch.py`:
- Name constant, e.g. `TOOL_GRAMMAR_HEALTH = "flextools_grammar_health"` at :85.
- Add to `ALL_TOOL_NAMES` frozenset :88-111.
- Import handler in `_import_handlers()` **twice** -- relative branch :155-157 and
  absolute fallback :197-199 -- then add to the returned dict :223 and the
  module-level rebind :249.
- Add `DISPATCH_ROUTES[TOOL_X] = (handler, InputModel)` at :259-303.
- `get_tool_handler()` :309; `_CACHED_TOOL_NAMES` :306.

**Implement** -- `src/flextoolsmcp/server/handlers/<name>.py`. Signature is
`async def handle_<tool>(args: dict) -> List[TextContent]` (`grammar_health.py:193`).
Kernel deps via `safe_import_kernel_deps()` (`grammar_health.py:57`) giving
`json_response, session_state, _get_log_dir, _get_api_index`. Errors via
`error_response(code, message, **extra)` from `response_utils` (:229); success via
`build_response_with_context` (:128) / `json_response` (:193).
`handlers/__init__.py` exports nothing (`__all__ = []`) -- import from submodules directly.

**Server glue** -- `src/flextoolsmcp/server.py`: `list_tools()` :808-837 iterates
`TOOL_DEFINITIONS.values()`; note `outputSchema` advertisement is **deliberately
disabled** (:822-834) -- do not wire `output_model` expecting it to ship.
`call_tool()` :853; dispatch at :952-981 (`model_dump()` -> handler). Session gate
:888-896 keys off `annotations.readOnlyHint`.

**Response keys** -- `response_keys.py` (KEY_* constants, :92-168).
**Error models** -- `response_models.py`: per-code `*Detail` model with
`Literal["code"]` discriminator, added to `AnyDetail` union (:420+) and validated by
`validate_detail()` (:483). CP2's three new codes go here;
`docs/TOOL-CONTRACT.md:69` hand-carries the count "22" -> must become 25.

## 2. What CP1 shipped, and what is uncalled

All in `src/flextoolsmcp/server/parser_probe.py` (44.9 KB, **do not modify** -- D1):
- `ProbeResult` :122; `probe_parser_core()` :240; `discover_hc_tool()` :454;
  `discover_generate_hc_config()` :524; `SandboxProbe` :572; `ParserVersions` :675;
  `ParserDetector` :909.
- **Engine gate**: `ParserEngineMismatchError` :698,
  `check_active_parser(project, *, supported_engines=("HC",))` :714. Module comment
  :690-697 states plainly "Not wired into any handler at CP1". **UNCALLED** -- grep
  shows zero callers (`grammar_health.py:32` documents why it deliberately does not
  call it).
- **Recording-agent probe**: `AgentProbeResult` :641, `probe_hc_agent(project, active_engine)`
  :773. Docstring :663-665: "shipped for CP2 callers but not wired into
  `ParserDetector`/any handler at CP1". **UNCALLED**.
- **Called today**: only `ParserDetector` -- `handlers/diagnostic_health.py:77-79, :233`,
  which reports `agent_probe` unconditionally `"skipped"` (:223) because health never
  opens a project.
- **Four error codes**, `response_models.py`: `ParserEngineMismatchDetail` :360,
  `ParserCoreMissingDetail` :374, `ParserAgentMissingDetail` :392,
  `ParserToolMissingDetail` :408. Contracts in `specs/parser-check/contracts/error-codes.md`.

## 3. READ_ONLY_SAFE

Exact identifier: **`READ_ONLY_SAFE`**, declared
`src/flextoolsmcp/server/tool_definitions.py:81` as
`ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)`.
Consumed at runtime in `server.py:891-892` via
`getattr(tool_def.annotations, "readOnlyHint", False)`.

Tested in `tests/test_mcp_tools.py`: `READ_ONLY_TOOLS` list :96-116,
`EXPECTED_TOOL_NAMES` :~60-91 (count derived, :93), `TestToolAnnotations` :188,
`test_readonly_tools_annotated_correctly` :207.
**Adding a tool requires editing both lists** or the count test fails.

## 4. Long-running / job infrastructure -- THERE IS NONE

Material planning fact: **no job runner, no queue, no background worker, no durable
run record exists.**

- `session.py:126` `SessionState` is the only process-lifetime state: `session_id`,
  `api_mode`, `project_name`, `write_enabled`, `user_request`,
  `discovered_apis`/`validated_apis`/`auto_discovered_apis` sets,
  `operations_history: List[OperationRecord]` (:113), `backed_up_projects` (:156),
  `auto_init_count` (:169), `recent_op_signals` deque(maxlen=5) (:192). All
  in-memory, wiped by `kernel.reset_session()` (:779).
- `kernel.py` module globals: `api_index` :691, `pattern_tracker` :694,
  `mcp_server` :697, `project_write_locks: Dict[str, asyncio.Lock]` :703 with
  `get_project_write_lock()` :707. That per-project asyncio lock is the **only**
  concurrency primitive on the request path.
- `subprocess_helpers.py:56` `run_script_async()` -- a single
  `asyncio.create_subprocess_exec` + `wait_for(timeout)`, fire-and-await, no handle,
  no cancellation token; `_kill_process_tree()` :20. Tree kill covers Windows via `taskkill`.
- `handlers/execution.py:5060` `run_scan_module(module_import_path, function_name,
  project_name, write_enabled=False, timeout_seconds=300)` -- the CP1 subprocess seam,
  and the closest thing to a runner. Still synchronous-await, one shot, result over a
  `===FLEXTOOLS_USER_RESULT===` sentinel.
- Threads exist only off the request path: `server.py:521-527` startup
  `ThreadPoolExecutor`, `update_check.py:231`, `workspace_check.py:42`.
- `scan/` holds one file, `grammar_scan_module.py` (child-process only). `diagnostic/`
  is pure file+in-memory (`offered_store.py:50` `get_reports_dir()`).

**Durable artifact locations that already exist** (all under `Path.home()/".flextoolsmcp"`):
`backup.py:47` `BACKUP_ROOT = ~/.flextoolsmcp/backups`; `~/.flextoolsmcp/reports/`
(`offered_store.py:52`, `diagnostic_report.py:25`); `skeleton_storage.py:43-50` --
JSONL append with a `threading.Lock` (`_WRITE_LOCK`), env override
`FLEXTOOLSMCP_SKELETON_DIR`, the best structural precedent for a run-record store;
`kernel.get_log_dir()` :85 + per-session log paths :134. `config.py:19` `CONFIG_DIR`.

Conclusion: US4's run machinery (stages, priority queue, interleave, cooperative
cancel, partial-result durability) is **100% net-new**. Nothing to extend.

## 5. Dependency + index facts -- DISCREPANCY CONFIRMED

- Current floors: `pyproject.toml:54` `"pyflexicon>=4.8.0,<5"`; `requirements.txt:21`
  `pyflexicon>=4.8.0,<5`. Stale build artifact `src/flextools_mcp.egg-info/requires.txt:10`.
  Both must become `pyflexicon>=4.9.0,<5`.
- Bound test file: `tests/test_dependency_bounds.py` (83 lines) -- currently asserts
  only `mcp`'s upper bound; the regex pattern at :64 and :77 is the template for a
  pyflexicon-floor test.
- **Actual on-disk index root is `src/flextoolsmcp/index/python/`**, containing
  `flexicon_api_v4.8.0.json` (plus `flexicon_lcm_bridge_v4.8.0.json`,
  `flexlibs_api_v1.2.8.json`, `archive/`).
- **DISCREPANCY**: the spec's Verbatim Constraints say
  `index/python/flexicon_api_v4.9.0.json`. That is repo-root-relative and wrong on
  disk. Real 4.9.0 path: `src/flextoolsmcp/index/python/flexicon_api_v4.9.0.json`.
  Also note the sibling bridge file is version-locked in the same directory -- a
  4.9.0 bump plausibly needs `flexicon_lcm_bridge_v4.9.0.json` too, which the spec
  does not mention. Flag both to planning.
- Resolution is by glob, not by literal: `versioning.py:386`
  `find_latest_versioned_api_file(index_dir, prefix)`, prefix `"flexicon_api"`
  registered in `handlers/diagnostic_health.py:92-97`. Overlay for installed wheels:
  `file_utils.py:61` `~/.flextoolsmcp/index` -- a 4.9.0 index must reach the overlay too.

## 6. Test layout

Flat `tests/`, no subpackages beyond `evals/`, `fixtures/`, `golden/`.
`tests/conftest.py`. Mixed `unittest.TestCase` and bare pytest; both styles coexist
in one file.

Naming: `test_<feature>.py` (`test_parser_probe.py`, `test_parser_engine_gate.py` 396L,
`test_parser_agent_probe.py` 477L, `test_parser_error_models.py` 278L,
`test_parser_health_block.py` 658L, `test_grammar_health.py`, `test_cp1_boundary.py`
1241L) or `test_issue<N>_<slug>.py`. CP2 should follow the feature form:
`test_parser_try_word.py`, `test_parser_run_lifecycle.py`.

**Isolated-process precedent** for `HCParser_DoesNotLoadXCore`:
`tests/test_cp1_boundary.py` is the model, but note it uses *in-process monkeypatched
spies*, not a child process -- `class BoundarySpy` :694, fixture
`boundary_spy(monkeypatch)` :1047-1048, dynamic suites :1119, :1167, falsifiability
suite :1191 (a spy that cannot catch a planted violation is itself tested).
`subprocess.run` appears there only as planted violation text (:684, :1230). Also
present: static AST scanners over the whole `server/` tree (:503, :526, :595) with
explicit allowlist/denylist non-overlap assertion (:591).

For a genuine loaded-assembly assertion, the parse must run where the parse runs --
the `run_scan_module` child (`execution.py:5060`) via `run_script_async`
(`subprocess_helpers.py:56`, `sys.executable`). Pattern: child returns its
loaded-assembly list over the `===FLEXTOOLS_USER_RESULT===` sentinel; the test asserts
zero XCore entries. Keep CP1's falsifiability discipline -- assert the probe *would*
have seen a planted XCore load.
