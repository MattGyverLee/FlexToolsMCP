# mcp SDK 2.0.0 Compatibility Audit

Investigated read-only in two scratch venvs (`mcp==2.0.0` vs `mcp==1.29.0`,
newest 1.x). flextools package was NOT installed; only `mcp` itself was
introspected via `dir()`/`inspect.signature()`.

## (a) Per-symbol table

| # | Symbol | mcp 1.x (1.29.0) status | mcp 2.0.0 status | What a port requires |
|---|---|---|---|---|
| 1 | `from mcp.server import Server` | Present, `mcp.server.lowlevel.server.Server` | Present, same import path/class name, but **totally different API shape** (constructor-injection, not decorators) | Rewrite every call site that builds a `Server` |
| 2 | `from mcp.server.stdio import stdio_server` | Present, async CM factory | Present, unchanged signature/behavior | No change |
| 3 | `@server.list_tools()` | Instance method decorator, `sig=()` | **Removed.** No `list_tools` attribute on `Server` instance at all | Must pass `on_list_tools=<handler>` to `Server(...)` constructor instead |
| 4 | `@server.call_tool()` | Instance method decorator, `sig=(*, validate_input=True)` | **Removed.** No `call_tool` attribute | Must pass `on_call_tool=<handler>` to constructor |
| 5 | `server.run(read, write, init_opts)` | `run(read_stream, write_stream, initialization_options, raise_exceptions=False, stateless=False)` | `run(read_stream, write_stream, initialization_options, raise_exceptions=False)` -- `stateless` kwarg dropped | No change needed (repo calls positionally, doesn't pass `stateless`) |
| 6 | `server.create_initialization_options()` | `(notification_options=None, experimental_capabilities=None)` | Same plus new optional `extensions=None` | No change (additive, backward compatible) |
| 7 | `async with stdio_server() as (...)` | Works | Works, unchanged | No change |
| 8 | `mcp.types.{TextContent,Tool,CallToolResult,ToolAnnotations}` | Fields are camelCase (`inputSchema`, `readOnlyHint`, `isError`, `structuredContent`) | Canonical fields renamed to snake_case (`input_schema`, `read_only_hint`, `is_error`, `structured_content`) but **pydantic alias_generator + `populate_by_name`/`validate_by_alias` preserve old camelCase kwargs** -- confirmed `Tool(inputSchema=...)`, `ToolAnnotations(readOnlyHint=...)`, `CallToolResult(content=[...])` all construct successfully under 2.0 | No change required; back-compat is real, not accidental |
| 9 | `from mcp.types import ToolAnnotations` | Present | Present, same back-compat aliasing as #8 | No change |

## (b) Newest 1.x / cap viability

Newest available 1.x is **1.29.0** (`pip index versions mcp`: 2.0.0, then
1.29.0, 1.28.1, ... down to 0.9.1). `pip install --dry-run "mcp>=1.27.0,<2"`
resolves cleanly to 1.29.0 with zero conflicting sub-dependencies (jsonschema,
pydantic, uvicorn, pyjwt, cryptography all satisfied). **The cap works.**

## (c) Port effort estimate

The break is **structural, not mechanical**, and confined almost entirely to
the low-level `Server` object's request-handler wiring. `mcp.types` (#8/#9)
needs zero changes thanks to alias back-compat -- that eliminates the ~9
files (`response_utils.py`, `dispatch.py`, `tool_definitions.py`, and six
`handlers/*.py`) that only import `TextContent`/`ToolAnnotations`. The real
work is confined to **2 files**: `src/flextoolsmcp/server.py` (decorator
definitions at lines 808/854 plus the `Server("flextools-mcp")`
instantiation at line 689 -- handlers must move into the constructor call,
and `call_tool`'s signature changes from `(name, arguments) -> list[TextContent]`
to `on_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult` with
`params.name`/`params.arguments` and an explicit `CallToolResult(content=[...])`
wrap) and `src/flextoolsmcp/server/kernel.py` (the redundant health-check
`Server("flextools-mcp")` instantiation at line 761 -- works unchanged, no
handlers attached there). No `list()`/dict signature-breakage was found in
the four `mcp.types` classes beyond the field renames, which are absorbed.
Rough size: ~2 files, ~2 call sites, plus rewriting `list_tools`/`call_tool`
handler bodies (name mangling for `params.name` vs `name` is trivial; the
`CallToolResult` wrap touches every one of the ~15+ tool dispatch return
paths in `dispatch.py`/`handlers/*.py` if those currently return bare
`list[TextContent]` up through `call_tool` -- worth re-checking at port time).

## (d) Recommendation

**Cap now** (`mcp>=1.27.0,<2`), do not port today. The cap is a one-line,
zero-risk change that immediately un-breaks installs; the newest 1.x
(1.29.0) resolves cleanly with no dependency fallout. The 2.0 port is real
work (constructor-injection rewrite of `server.py`'s two decorators plus a
signature change for `call_tool`) but is well-scoped to one file's core and
should be tracked as a proper ticket, not rushed under fire-drill pressure.
Track for the eventual port: (1) rewrite `list_tools`/`call_tool` as
`on_list_tools`/`on_call_tool` callables passed to `Server(...)`; (2) update
`call_tool` handler to accept `(ctx, params: CallToolRequestParams)` and
return `CallToolResult`, not bare `list[TextContent]`; (3) verify whether
`dispatch.py`'s handler-return contract needs a wrapping shim at the
`call_tool` boundary; (4) note MCP 2.0 deprecates logging/roots/progress
capabilities (SEP-2577, 2026-07-28) -- irrelevant to this repo (none used)
but worth a mention in the port ticket. No evidence contradicts capping;
2.0 is one week old (released 2026-07-28) and the low-level `Server` API
was replaced outright with no shim, which is exactly the situation an
unbounded `>=` should never have been exposed to.
