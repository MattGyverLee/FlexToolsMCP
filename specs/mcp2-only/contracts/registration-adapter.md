# Contract: registration adapter (`src/flextoolsmcp/server/registration.py`)

The adapter is the only code that touches the mcp SDK's server types. Neither
`server.py` nor the handlers import from `mcp.server`.

## Public functions

```text
resolve_server_version() -> str
    Package version from importlib.metadata; falls back the same way
    mcp_compat.resolve_server_version does today. Never ''.

build_server(list_tools_fn, call_tool_fn) -> mcp.server.Server
    list_tools_fn: async () -> list[Tool]
    call_tool_fn:  async (name: str, arguments: dict) -> list[ContentBlock] | InputRequiredResult
    Returns Server("flextools-mcp", version=resolve_server_version(),
                   instructions=SERVER_INSTRUCTIONS,
                   on_list_tools=..., on_call_tool=...)
```

## `on_list_tools(ctx, params)`

- Returns `ListToolsResult(tools=await list_tools_fn())`.
- Ignores pagination (the tool list is small and fixed).

## `on_call_tool(ctx, params)`: CP1 order

1. **Schema pre-check** (moved verbatim from `mcp_compat.py:256-295`):
   - Look up the tool's `input_schema` via the cached schema provider.
   - No schema, or `jsonschema` unavailable: skip (fail-open, as today).
   - Violation: return `CallToolResult(is_error=True,
     content=[TextContent(type="text", text=f"Input validation error: {exc.message}")])`.
     The handler is not called and session state is not touched.
2. **Dispatch**: `result = await call_tool_fn(params.name, params.arguments or {})`.
   - `InputRequiredResult`: return it unchanged.
   - Otherwise: return `CallToolResult(content=list(result))`.
3. **Escape hatch**: `except Exception as exc`:
   - log the traceback to the operations log;
   - return `CallToolResult(is_error=True, content=[TextContent(type="text", text=f"Error: {exc}")])`.
   - It must never re-raise. A re-raise becomes `MCPError` with era-dependent
     text (research R3).

## `on_call_tool`: CP2 changes

- Step 1 is deleted. Validation happens in the dispatcher (`server.py`
  `call_tool`), before the cold-session gate, through the tool's input model.
- Step 2 additionally sets `is_error=classify_is_error(payload)` (see
  data-model.md, error-flag classifier) when the content is a JSON envelope.
- Step 3 returns an `internal_error` envelope built by `error_response`, with
  `error_type=type(exc).__name__`, `tool=params.name`, and `traceback`, the
  same fields and order as `server.py`'s in-handler path. `is_error=True`.

## Invariants (tested)

- Same behavior in `mode='legacy'` and `mode='auto'`, in process and over stdio.
- `server_info.version != ''`, and `instructions == SERVER_INSTRUCTIONS`.
- No camelCase attribute reads of mcp types anywhere in `src/` or `tests/`.
  Constructor keyword arguments are exempt. The guard regex is in plan.md.
- Nothing is written to stdout before the stdio stream opens.
