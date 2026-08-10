# Should we support mcp 1.x AND 2.x simultaneously?

Investigation for issue #83. Evidence gathered against real installs:
mcp 1.27.0 (project env) and mcp 2.0.0 (scratch venv), driven over a real
stdio JSON-RPC handshake -- not from changelogs.

**Answer: yes. The compat seam is ~25 lines in one place, and no handler
body changes.** Dual support also lets the `<2` cap drop entirely, which is
the actual cure for the incident that started this (an uncapped-then-capped
dependency breaking fresh installs for 11 releases).

## Why it's cheap

Confirmed by `inspect.signature(Server.__init__)` under 2.0.0: the ONLY
divergence this repo touches is handler registration. `stdio_server`,
`server.run(...)`, `create_initialization_options()`, and every `mcp.types`
camelCase kwarg (`inputSchema=`, `readOnlyHint=`) are unchanged and work
identically on both.

So the seam is exactly one function:

```python
MCP2 = not hasattr(Server, "call_tool")

def build_server(name, list_tools_fn, call_tool_fn):
    """list_tools_fn: async () -> list[Tool]
       call_tool_fn:  async (name, arguments) -> list[TextContent]"""
    if not MCP2:
        srv = Server(name)
        srv.list_tools()(list_tools_fn)   # decorators are just callables
        srv.call_tool()(call_tool_fn)
        return srv

    from mcp.types import CallToolResult, ListToolsResult

    async def _on_list_tools(ctx, params):
        return ListToolsResult(tools=await list_tools_fn())

    async def _on_call_tool(ctx, params):
        try:
            content = await call_tool_fn(params.name, params.arguments or {})
        except Exception as exc:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {exc}")],
                isError=True,
            )
        return CallToolResult(content=list(content))

    return Server(name, on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)
```

`list_tools()` and `call_tool(name, arguments)` in `server.py` keep their
current signatures and bodies verbatim. They stop being decorated and get
passed to `build_server` instead. `dispatch.py` and all `handlers/*.py`
keep returning bare `list[TextContent]` -- **the "audit all ~15+ dispatch
return paths" scope item in issue #83 evaporates**, because the shim does
the `CallToolResult` wrap at the single seam.

## PoC results (real stdio handshake, same source file both runs)

| Check | mcp 1.27.0 | mcp 2.0.0 |
|---|---|---|
| `initialize` | OK, proto 2025-06-18 | OK, proto 2025-06-18 |
| `tools/list` | OK, `inputSchema` + `readOnlyHint` present | OK, identical |
| `tools/call` happy path | `isError: False` | `isError: False` |
| handler raises | `isError: True` result | `isError: True` result (via shim try/except) |
| `serverInfo.version` | `"1.27.0"` | `""` |
| bad-type arg (`text: 123`) | `isError: True`, "Input validation error" | **passed through to handler** |

## The two deltas, and why neither blocks

**1. `serverInfo.version` is empty under 2.0.** 1.x defaulted it to the mcp
library version; 2.0's ctor defaults `version: str = ""`. Fix: pass
`version=<flextools-mcp version>` explicitly. Strictly an improvement --
reporting our own version is more useful than reporting mcp's.

**2. 2.0's raw `on_call_tool` skips mcp's jsonschema pre-validation.** In
1.x the decorator validated `arguments` against `inputSchema` before
calling. A raw 2.0 handler does not -- the PoC's `text: 123` reached the
handler untouched.

For *this* repo that is nearly a no-op: `tool_definitions.get_schema()`
generates `inputSchema` from the very same Pydantic model that `server.py`
re-validates against at line 966 (`input_model(**arguments)`). The
constraint set is identical; only the error *shape* differs -- the repo's
own `{"error": "Input validation failed"}` JSON instead of mcp's isError
text. If exact parity is wanted, add a `jsonschema.validate` call in the
2.x branch of the shim.

## Costs of dual support

- **CI matrix required.** Two live code paths means the test suite must run
  under both pins, or the untested branch rots. This is the real ongoing
  cost -- roughly one extra CI job.
- **Ceiling on 2.x-only features.** Resources, prompts, completion,
  `cache_hints`, `lifespan` typing, `InputRequiredResult` are all 2.0-shaped.
  The repo uses none of them today; adopting any would end dual support.
- **structuredContent would grow the shim.** 1.x's decorator auto-normalizes
  a `dict` or `(content, dict)` return into `structuredContent`; 2.0 does
  not. Currently moot -- `outputSchema` advertisement is deliberately
  disabled (server.py:825-835, issue #54 follow-up) and handlers return
  text-only. If that follow-up lands, the shim needs a matching branch.

## Recommended shape

1. Add the shim (new `src/flextoolsmcp/mcp_compat.py`, or inline in
   `server.py` next to the `Server(...)` construction at line 689).
2. Pass `version=` explicitly for `serverInfo` parity.
3. Relax the pin from `mcp>=1.27.0,<2` to `mcp>=1.27.0,<3` -- capped at the
   next unknown major, uncapped across the break we've actually verified.
4. CI matrix: run `pytest` under both `mcp==1.27.0` (floor) and `mcp>=2`.
5. Extend the publish smoke job to run against both (this overlaps issue 4
   in `deferred-issues.md` -- the raw-JSON-RPC harness written for this PoC
   is directly reusable there, and needs no mcp client library, which is
   exactly what makes it work against both majors).

`kernel.py:761`'s bare `Server("flextools-mcp")` health-check instantiation
needs no change; confirmed the bare ctor still works under 2.0.
