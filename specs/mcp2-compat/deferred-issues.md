# Deferred issues -- mcp 2.0 compatibility follow-up

These are DRAFTS ready to paste into `gh issue create --title ... --body ...`.
They are intentionally NOT filed -- only the user authorizes filing GitHub
issues. Each section below is one issue: title as the heading, body as the
fenced block underneath.

---

## 1. Port to mcp 2.0

```
Title: Port server.py to the mcp 2.0 low-level Server API

mcp 2.0.0 (released 2026-07-28) removed the decorator-based
`@server.list_tools()` / `@server.call_tool()` API in favor of
constructor-injected handlers. flextools-mcp currently caps `mcp` at
`>=1.27.0,<2` (see specs/mcp2-compat/) to stay on the working decorator API;
this issue tracks the eventual forward port.

### Per-symbol audit (from specs/mcp2-compat/reviews/cycle1-programmer.md)

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

### Scope

Confined almost entirely to `src/flextoolsmcp/server.py`:
- The `Server("flextools-mcp")` instantiation (line 689) must move to
  constructor-injection: handlers passed as `on_list_tools=...`,
  `on_call_tool=...` kwargs instead of decorators.
- `list_tools()` (line 809) keeps its body but drops the `@server.list_tools()`
  decorator.
- `call_tool(name, arguments) -> list[TextContent]` (line 855) must become
  `on_call_tool(ctx, params: CallToolRequestParams) -> CallToolResult`:
  read `params.name` / `params.arguments` instead of the old positional args,
  and wrap the return value in `CallToolResult(content=[...])` instead of
  returning a bare `list[TextContent]`. This wrap likely needs to happen at
  the `dispatch.py`/`handlers/*.py` boundary, since those currently return
  bare `list[TextContent]` up through `call_tool` -- audit all ~15+ tool
  dispatch return paths.
- `src/flextoolsmcp/server/kernel.py`'s redundant health-check
  `Server("flextools-mcp")` instantiation (around line 761) has no handlers
  attached and needs no change beyond confirming the bare constructor call
  still works under 2.0 (it does, per audit).
- `mcp.types` field renames (#8/#9 above) need ZERO code changes anywhere in
  the repo -- pydantic alias back-compat is real and verified. Do not
  "helpfully" convert camelCase kwargs to snake_case as part of this port;
  it's unnecessary churn.

### Acceptance criteria
- `mcp>=2.0.0` resolves and `pytest -q` passes with no cap.
- `scripts/validate_integrity.py all` reports a runtime (not AST) tool count.
- The publish-workflow smoke job (added in the mcp2-compat cap fix) passes
  against a wheel built with the ported code.
```

---

## 2. Add upper bounds to remaining uncapped runtime deps

```
Title: Add upper bounds to remaining uncapped runtime deps + adopt a lockfile

The mcp 2.0.0 break (specs/mcp2-compat/) exposed that `mcp` was the only
dependency without an upper bound, and that an uncapped `>=` on a fast-moving
dependency can silently break every fresh install for as long as the
maintainers take to notice (11 releases, 2.3.1-2.9.0, shipped broken).

Other runtime dependencies in pyproject.toml/requirements.txt are ALSO
uncapped today and carry the same latent risk:
- sentence-transformers>=2.2.0
- faiss-cpu>=1.7.4
- pythonnet>=3.0.0
- pydantic>=2.0.0
- httpx>=0.27.1
- anyio>=4.5

### Proposed work
1. For each dependency above, determine the actual compatibility ceiling
   (either by reading changelogs for known breaking-change majors, or by
   testing against the current major+1 in a scratch venv the way the mcp
   audit did).
2. Add appropriate upper bounds (probably `<majorNext` for each, mirroring
   the `mcp>=1.27.0,<2` pattern).
3. Adopt a lockfile or constraints file (`pip-compile` / `uv pip compile` /
   similar) for CI so that "what does `pip install .` actually resolve to
   today" is reproducible and reviewable in PRs, rather than only being
   discovered when it breaks.
4. Consider whether `tests/test_dependency_bounds.py`'s
   `KNOWN_UNCAPPED_DEPS` allowlist should shrink as each dependency gets
   capped, eventually becoming empty (at which point a general "all deps
   have upper bounds" assertion becomes viable, without immediately failing
   on day one).

Not urgent -- no evidence any of these six has a 2.0-style API removal
imminent -- but the mcp incident is a strong argument for treating "no
upper bound" as a standing risk across the whole dependency list, not just
whichever one happened to break last.
```

---

## 3. Chain exceptions in dual-mode import fallback blocks

```
Title: Chain exceptions (raise ... from exc) in dual-mode import fallbacks

QC P2 finding from specs/mcp2-compat/reviews/cycle1-qc.md, sibling sweep:

`src/flextoolsmcp/server/handlers/_import_helper.py:29-104` and roughly 15
duplicated inline blocks across `execution.py`, `admin.py`, `catalog.py`,
`dispatch.py`, etc. follow the pattern:

    try:
        from ..X import Y   # relative (package mode)
    except ImportError:
        from X import Y     # absolute (script mode)

This dual-mode import is the accepted architecture (see the `__package__`
discussion in src/flextoolsmcp/server/__init__.py) and only one branch is
ever live per deployment, so this is lower severity than the P0/P1 lazy
loader bug fixed in the mcp2-compat cycle. But if the fallback (absolute)
import ALSO fails for a reason other than the expected mode mismatch (e.g.
a genuine missing symbol, a syntax error in the target module), the
original ImportError's message/traceback is silently discarded because
there's no `from exc` chaining on the fallback's own failure path.

### Proposed fix
For each of the ~15 sites, chain the fallback failure to the original:

    try:
        from ..X import Y
    except ImportError as first_exc:
        try:
            from X import Y
        except ImportError as second_exc:
            raise second_exc from first_exc

Diagnostic-preservation only; no behavior change when both branches work as
designed. Low priority -- batch with other lint/hygiene cleanup.
```

---

## 4. Extend the publish smoke job to a full stdio MCP handshake

```
Title: Extend publish.yml smoke job to a full stdio MCP initialize handshake

The mcp2-compat fix added a `smoke` job to `.github/workflows/publish.yml`
that installs the built wheel into a fresh venv and calls
`asyncio.run(list_tools())` directly against the imported module. This
catches import-time and decorator-registration breaks (exactly the mcp 2.0
class of bug) but does NOT exercise the actual stdio transport, the
`initialize` handshake, or the console-script entry points
(`flextoolsmcp`/`flextools-mcp` in pyproject.toml).

### Proposed work
Extend (or add alongside) the smoke job to:
1. Launch the installed console script as a subprocess
   (`flextools-mcp` or `python -m flextoolsmcp.server`).
2. Speak the MCP stdio JSON-RPC protocol far enough to send an
   `initialize` request and receive a valid `InitializeResult`, then send
   `tools/list` and assert a non-empty tool list over the wire (not just
   in-process).
3. Requires no FieldWorks install (same constraint as the existing smoke
   job) -- read-only server startup only.

This closes the remaining gap between "the Python object imports and
`list_tools()` returns tools" and "a real MCP client can actually talk to
this server end-to-end."
```
