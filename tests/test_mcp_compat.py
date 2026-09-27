#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp 1.x/2.x dual support -- compat shim tests (issue #83).

`src/flextoolsmcp/mcp_compat.py::build_server` registers tool handlers via
decorators on mcp 1.x and via constructor-injected `on_list_tools=` /
`on_call_tool=` on mcp 2.x. These tests lock the major-agnostic surface:

- `MCP2` flag agrees with the live `Server` class probe.
- `resolve_server_version()` never returns empty.
- `build_server()` returns a `Server` whose initialization options carry the
  explicitly passed version (the `serverInfo.version` parity fix -- mcp 2.x
  defaults it to `""`). The options shape differs per major (flat
  `server_version` on 2.x, `server_info.version` on 1.x), so the test reads
  both spellings.
- The 2.x adapters wrap bare `list[TextContent]` in `CallToolResult` and map
  a raising handler to an `isError` result, mirroring the 1.x decorator
  behavior. Driven directly (stub params object), so they run identically
  under both majors with no version-specific client.

Async work is driven via `asyncio.run` (not bare `async def` tests) so this
file passes with or without `pytest-asyncio` installed.

Run with:
    python -m pytest tests/test_mcp_compat.py -q
"""

import asyncio
from types import SimpleNamespace

from mcp.server import Server
from mcp.types import TextContent, Tool

from flextoolsmcp.mcp_compat import (
    MCP2,
    build_server,
    make_call_tool_handler,
    make_list_tools_handler,
    resolve_server_version,
)


async def _fake_list_tools():
    return [Tool(name="probe", description="probe", inputSchema={"type": "object"})]


async def _fake_call_tool(name, arguments):
    if name == "boom":
        raise RuntimeError("kaboom")
    return [TextContent(type="text", text=f"ok:{name}")]


def _options_version(opts):
    """serverInfo version across both majors' InitializationOptions shapes."""
    flat = getattr(opts, "server_version", None)
    if flat is not None:
        return flat
    return opts.server_info.version


def _is_error(result):
    """isError flag across both majors' CallToolResult shapes.

    Construction accepts both spellings on both majors (pydantic aliases),
    but attribute *reads* require the canonical spelling: `isError` on 1.x,
    `is_error` on 2.x.
    """
    if hasattr(result, "is_error"):
        return result.is_error
    return result.isError


def test_mcp2_flag_matches_live_server_class():
    """MCP2 must agree with the hasattr probe against the installed major."""
    assert MCP2 == (not hasattr(Server, "call_tool"))


def test_resolve_server_version_is_never_empty():
    assert isinstance(resolve_server_version(), str)
    assert resolve_server_version() != ""


def test_build_server_returns_server_with_explicit_version():
    """serverInfo.version carries OUR version, not mcp's (or empty)."""
    srv = build_server("test-srv", _fake_list_tools, _fake_call_tool, version="9.9.9")
    assert isinstance(srv, Server)
    opts = srv.create_initialization_options()
    assert _options_version(opts) == "9.9.9"


def test_list_tools_adapter_wraps_tool_list():
    handler = make_list_tools_handler(_fake_list_tools)
    result = asyncio.run(handler(None, None))
    assert [t.name for t in result.tools] == ["probe"]


def test_call_tool_adapter_wraps_bare_content():
    handler = make_call_tool_handler(_fake_call_tool)
    params = SimpleNamespace(name="probe", arguments={})
    result = asyncio.run(handler(None, params))
    assert not _is_error(result)
    assert [c.text for c in result.content] == ["ok:probe"]


def test_call_tool_adapter_maps_exception_to_is_error():
    """A raising handler becomes an isError result (1.x decorator parity)."""
    handler = make_call_tool_handler(_fake_call_tool)
    params = SimpleNamespace(name="boom", arguments={})
    result = asyncio.run(handler(None, params))
    assert _is_error(result)
    assert "kaboom" in result.content[0].text


def test_call_tool_adapter_tolerates_null_arguments():
    """`params.arguments or {}` -- a null arguments payload reaches the handler."""
    seen = {}

    async def _recording(name, arguments):
        seen.update(arguments)
        return [TextContent(type="text", text="ok")]

    handler = make_call_tool_handler(_recording)
    result = asyncio.run(handler(None, SimpleNamespace(name="x", arguments=None)))
    assert not _is_error(result)
    assert seen == {}
