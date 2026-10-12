> **SUPERSEDED (2026-10-11):** the mcp 2.0 port described below has landed
> under issue #369 -- see `specs/mcp-modernization/`. The server is now
> `mcp` 2.x-only (`mcp>=2,<3`), the `mcp_compat` dual-support shim is
> deleted, and the port took a different shape than this directory assumed:
> the low-level `mcp.server.Server` with constructor-injected handlers,
> NOT the `MCPServer` (FastMCP) framework. The `>=1.27.0,<2` cap and the
> un-done port stated below are historical, not current fact. Everything
> below this banner is the pre-#369 record, kept unchanged.

# mcp2-compat

Dual support for mcp 1.x and 2.x (#83, closed; guard #285). Review history and the
dual-support analysis are in `specs/_archive/mcp2-compat/` (do not read by default).

Live: `deferred-issues.md` -- drafts 2-4 (dep upper bounds, exception chaining,
stdio handshake smoke test) are not yet filed. Draft 1 is superseded by #83.
