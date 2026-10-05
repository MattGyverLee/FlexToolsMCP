# Research: mcp2-only

**Date**: 2026-10-05. Probes ran in a throwaway Python 3.12 venv with
`mcp==2.3.0` (pydantic 2.13.5, anyio 4.15.1) in the session scratchpad, not in
the repo venv, which still carries mcp 1.30. Resolution checks used
`uv pip compile --resolution lowest-direct` against `requirements.txt` with the
CP1 floors applied.

## R1. Registration target: the low-level `Server`

- **Decision**: register through `mcp.server.Server(name, *, version=,
  instructions=, on_list_tools=, on_call_tool=)`.
- **Evidence**: the 2.3.0 signature is
  `on_list_tools(ctx, PaginatedRequestParams | None) -> ListToolsResult` and
  `on_call_tool(ctx, CallToolRequestParams) -> CallToolResult | InputRequiredResult`.
  `version` defaults to `''`, so `resolve_server_version()` is still needed.
- **Alternatives rejected**: `MCPServer` (the FastMCP decorator framework):
  about 31 tool rewrites, loses the Pydantic-generated schemas, and conflicts
  with `docs/TODO.md:39-44` and the project memory note on mixed text/code
  output.

## R2. The SDK still does no input validation

- **Decision**: CP1 keeps the jsonschema pre-check in the adapter (FR-005).
- **Evidence**: a tool with `additionalProperties: false` and `a: integer`
  received `{'a': 'notint', 'extra': 1}` in its handler, with `is_error=False`,
  in both `mode='legacy'` and `mode='auto'`.

## R3. Escaped exceptions become protocol errors, with era-dependent text

- **Decision**: CP1 keeps the adapter's `except Exception` -> `is_error=True`
  with `Error: {exc}` (FR-006). CP2 swaps the body for `internal_error`
  (FR-022).
- **Evidence**: a handler raising `RuntimeError("kaboom")` surfaced to the
  client as `MCPError`. The message was `kaboom` on legacy connections and
  `Internal server error` on 2026-07-28 connections. Without the adapter the
  wire would change in both eras, and differently in each.

## R4. Dual-era negotiation needs no server code

- **Decision**: CP1 adds tests, not protocol code (FR-009).
- **Evidence**: `Client(server, mode='legacy')` negotiated `2025-11-25`;
  `mode='auto'` negotiated `2026-07-28`. Both listed tools, and
  `Tool.annotations.read_only_hint` and `Tool.input_schema` are readable as
  snake_case attributes. The in-process client goes through `DirectDispatcher`,
  so the real modern stdio branch is only exercised by the subprocess test
  (umbrella section 0, item 3).
- **Client API used by tests**: `Client(server_or_StdioServerParameters, mode=,
  read_timeout_seconds=)`, then `.protocol_version`, `.server_info`,
  `.instructions`, `.list_tools()`, `.call_tool(name, args)`.

## R5. Dependency floors

- **Decision**: `mcp>=2.3.0,<3`; `pydantic>=2.12`; `anyio>=4.9` (with
  `anyio>=4.10; python_version>='3.14'`); `jsonschema>=4.20` declared
  explicitly (Q16).
- **Evidence**: mcp 2.3.0's own requirements are
  `anyio>=4.9; python_version<'3.14'`, `anyio>=4.10; python_version>='3.14'`,
  `pydantic>=2.12.0`, `jsonschema>=4.20.0`, `httpx2>=2.10.0`, `mcp-types==2.3.0`,
  `opentelemetry-api>=1.28.0`, `pywin32>=311` on win32. So `jsonschema` still
  arrives transitively. We declare it anyway because the adapter imports it
  directly, and matching mcp's floor costs nothing.
- **Python floor**: mcp 2.3.0 declares `Requires-Python >=3.10` (PyPI,
  2026-10-04). `requires-python = ">=3.10"` and the py3.10 CI cells stay.
- `httpx>=0.27.1` stays, because `update_check.py` imports it directly and mcp
  2.x no longer brings it.

## R6. The lower-bound CI cell needs one non-mcp floor raised

- **Decision**: raise `sentence-transformers>=2.2.0` to `>=2.3.0` in CP1, in
  `pyproject.toml` and `requirements.txt` together. The constitution allows
  ratcheting a floor upward. The CHANGELOG notes it.
- **Evidence**: lowest-direct resolves on py3.10 and py3.12 (mcp 2.3.0,
  pydantic 2.12.0, anyio 4.10.0, jsonschema 4.20.0, httpx 0.27.1,
  pythonnet 3.0.3, faiss-cpu 1.7.4 / 1.8.0). But it also resolves
  `sentence-transformers==2.2.0` against `huggingface-hub==0.36.2`, and
  2.2.x imports `cached_download` (`SentenceTransformer.py`, `util.py`), which
  the hub removed in 0.26. The floor cell would fail at import. The 2.3.0 wheel
  has no `cached_download` reference.
- **Note**: anyio resolves to 4.10.0 even at lowest-direct, because a transitive
  dependency asks for it. The declared floor stays at mcp's 4.9 so we never
  claim more than mcp does; the cell tests what actually resolves.
- **Alternatives rejected**: pinning only the mcp set to floors and leaving
  everything else at latest. That does not test the floors the package
  declares, which is what Q2 chose.
- **Follow-up for implement**: if the floor cell surfaces another stale floor
  (for example `faiss-cpu 1.7.4` on py3.10, or `pythonnet` wheels), ratchet it
  in the same change and record it in research and the CHANGELOG. Do not drop
  the cell.

## R7. CI shape

- **Decision**:
  - The fast tier (push/PR) runs the `py3.12 x latest` cell, as today.
  - The full tier (schedule and `full_matrix`) replaces the mcp axis
    `["1.27.0","latest"]` with a `deps` axis `["lowest","latest"]`. The
    `lowest` cell runs `uv pip compile --resolution lowest-direct pyproject.toml
    --extra dev -o lowest.txt`, installs it, then `pip install -e . --no-deps`.
  - The "Downgrade mcp to floor" step (`test.yml:94-96`) is deleted.
  - The stdio subprocess test runs in every Windows cell. It is not deselected
    by `-m "not requires_flex"`, so it is part of the required `test` check
    automatically. Linux runs it too, without being required (spec
    assumption).
  - `publish.yml` `smoke`: the 1.27.0 re-smoke (`:104-108`) becomes a stdio
    handshake in both eras through the installed `flextools-mcp` console script
    in the fresh smoke venv.
- **Alternative rejected**: a separate `stdio` job. It would duplicate setup,
  and the `test` job is already the required check.

## R8. Stdio test isolation

- **Decision**: launch `[sys.executable, "-m", "flextoolsmcp"]` with
  `FLEXTOOLSMCP_NO_UPDATE_CHECK=1`, `FLEXTOOLSMCP_NO_WORKSPACE_CHECK=1`, a temp
  `FLEXTOOLSMCP_LOG_DIR`, and `FLEXTOOLSMCP_INDEX_DIR` pinned to the shipped
  indexes. Use a 60 s read timeout and a new `requires_subprocess` marker
  registered in `pytest.ini`.
- **Verify during implement**: the env var names above are the ones
  `update_check.py`, the workspace check and `get_index_dir()` actually read.
  Grep before writing the fixture, and fix this file if a name differs.

## R9. Where the gate and the classifier sit today (CP2 anchors)

- The cold-session gate is at `server.py:943-1019`. Route lookup,
  `unknown_tool` and `invalid_input` follow at `:1021-1045`. `internal_error`
  is emitted at `:1058-1070` with fields `error_type`, `traceback`, `tool`,
  matching TOOL-CONTRACT.md:114 and `InternalErrorDetail`. The error-code
  extraction to reuse is at `:1090-1102`.
- `FlexToolsStartInput` is `extra="allow"` (`models.py:47`).
- `CONTRACT_VERSION` lives at `response_utils.py:19`.
- Today only the shim's own paths set `isError`. `unknown_tool`,
  `invalid_input` and `session_not_initialized` go out with `isError=false`, so
  setting it is the CP2 wire change (FR-021), as the spec says.
- Line numbers are as of `f48695c`. Re-anchor by symbol after the PR-0 rebase.
