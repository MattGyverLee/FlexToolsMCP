# Cycle 2 verification — MCP modernization (#369), close-out gate

Verifier: lex-verification (independent; implementer reports not relied on).
Branch: `feat/369-mcp-modernization` · HEAD `b4adb61` · base `origin/main c1c751f`
(6 commits ahead, working tree clean at audit start.)
Env: `/tmp/ftmcp-venv` (mcp 2.3.0, confirmed via `pip show mcp`),
absolute `PYTHONPATH=/home/hatch/workspace/ftmcp-369/src`.

## Method / limitation

I personally ran: the nine phase test files named in the task plus
`tests/test_structured_output.py` (Phase 2's core evidence file, in the
branch's diff), `scripts/validate_integrity.py all`, `ruff check src tests`,
a `git apply --check` of the held workflows patch, a jsonschema validation
of `server.json` against the live pinned 2025-12-11 registry schema, and
two independent raw JSON-RPC stdio smokes of my own (see Acceptance 2).
**The full test suite was NOT run** (per task instruction; 12+ min), so
any verdict resting on "full suite green" is marked PARTIAL — phase-file
runs are necessary but not sufficient evidence for it.

Phase-file run (single invocation, `-m "not requires_flex"`):
**132 passed, 3 xfailed in 9.77s.** The 3 xfails are all in
`test_tool_poisoning_regression.py`, each carrying an explicit follow-up
reason: `test_t3a…` and `test_t3b…` (S-P1-1: index-served text has no
data/provenance labelling; import statements not validated), and
`test_t5_local_capture_is_scrubbed_before_reserve` (S-P1-4).

`validate_integrity.py all`: all 6 sections OK (31 files syntax/imports;
server.py 31 tools registered and documented; flexicon contract passed;
tool output models golden + minimal OK). Exit clean.
`ruff check src tests`: **All checks passed!** (ruff 0.17.0).

## Acceptance verdicts (spec.md, 7 items)

| # | Acceptance item | Verdict | Evidence I checked |
|---|---|---|---|
| 1 | `mcp>=2,<3` in pyproject + requirements; `mcp_compat.py` deleted; no 1.x path; CI matrix floor cell becomes 2.0.0 | **PARTIAL** | pyproject.toml:36 `"mcp>=2,<3"` and requirements.txt:5 `mcp>=2,<3` (grep). `src/flextoolsmcp/mcp_compat.py` absent; no `mcp_compat` references remain in `src/` (only test-file docstrings mention the retirement). server.py imports `from mcp.server import Server` (line 68) with constructor-injected `on_list_tools=`/`on_call_tool=` adapters (lines 1280–1359) and `resolve_server_version` moved into server.py:1234. kernel.py untouched by the diff (not in `git diff --stat`). `test_dependency_bounds.py` passed (asserts the ≥2 floor). **Gap: the CI floor cell is NOT on the branch** — `git diff origin/main..HEAD -- .github/` is empty. It is exactly the content of `~/workspace/ftmcp-369-workflows.patch`: `git apply --check` passes cleanly, and I read the whole patch — it contains only (a) test.yml: matrix `1.27.0`→`2.0.0` + comment updates, and (b) publish.yml: comment `1.27.0`→`2.0.0` and removal of the `mcp==1.27.0` smoke block. Nothing else. |
| 2 | New-era (`server/discover`) and legacy-era (`initialize`) clients both connect and list/call tools — stdio smoke evidence | **DONE** | Suite smoke run verbosely by me: `pytest tests/test_mcp_compat.py -k stdio -v` → 2 passed (raw JSON-RPC, no client lib). Plus my own independent smoke (`/tmp/ftmcp_raw_smoke.py`, launches the real `flextoolsmcp.server:run` entry over stdio): LEGACY `initialize` → protocolVersion `2025-11-25`, serverInfo `flextools-mcp/2.15.0`, instructions present; `tools/list` → 31 tools; `tools/call flextools_get_object_api {object_type:"ILexEntry"}` → isError=False, success text, structuredContent attached. MODERN `server/discover` → supportedVersions `['2026-07-28']`, capabilities `['tools']`, serverInfo `flextools-mcp/2.15.0`; `tools/list` → 31 tools; same `tools/call` → isError=False, structuredContent keys `['_contract','_session_note','api_mode','found','liblcm','object_type','session_context','status']`. Both processes exited 0. Note: against the bare server construction (the suite smoke's pattern, no index preload) the same call returns an `internal_error` payload (`'NoneType' object has no attribute 'ensure_casting_index_loaded'`) — the suite smoke only lists tools; the call path is evidenced via the real `run()` entry, as above. |
| 3 | Structured output advertised on batch-1 tools; text payloads byte-identical; error payloads carry no structuredContent | **DONE** | `tests/test_structured_output.py` passed (inside the 132): only-batch-1-advertises test, golden byte-identical text + structured attached on success, byte-identical + nothing attached on error, session-note-in-final-text case, `status=="error"` without error_code attaches nothing, structuredContent validates against the advertised outputSchema (client-side jsonschema check), advertised schema requires traced keys. Precondition verified directly: the shadowing local `build_response_with_context` is gone from `handlers/api.py` — the only definition in the tree is the canonical stamping one at `src/flextoolsmcp/response_utils.py:146`; real wire payload above carries `status` + `_contract`. Wire check: all three batch-1 tools (`flextools_run_module`, `flextools_search_by_capability`, `flextools_get_object_api`) show `outputSchema` in `tools/list`; my deliberate bad-argument call returned the pre-validation error with isError=True and **no** structuredContent. |
| 4 | Progress notifications for C/B/E/H ops when a client supplies a progressToken; byte-identical behavior without one | **DONE** (scoped per R3) | `tests/test_progress_notifications.py` passed (inside the 132): reporter seam tests (token ⇒ notifications recorded with that token; no token / ctx=None ⇒ nothing emitted, identical results; raising sink never propagates); C milestone-sequence test (`test_semantic_search_model_load_milestone_sequence`); B heartbeat tests (15s interval constant in `src/flextoolsmcp/server/progress.py:41`, `progress_heartbeat` cancelled in `finally`); E grammar scan via the same wrapper (`test_run_scan_module_heartbeats_while_subprocess`
...[truncated 6749 chars]