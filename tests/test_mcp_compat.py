#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp 2.x server wiring tests (issue #369; formerly the #83 compat-shim tests).

The 1.x/2.x compat shim (`mcp_compat.py`) is retired: its 2.x branch now
lives inlined in `src/flextoolsmcp/server.py`, next to the `Server`
construction it feeds. These tests lock that wiring:

- `resolve_server_version()` never returns empty.
- A `Server` built with the inlined adapters carries the explicitly passed
  version in its initialization options (the `serverInfo.version` parity
  fix -- mcp 2.x defaults it to `""`; 2.x options are flat: `server_version`).
- The adapters wrap bare `list[TextContent]` in `CallToolResult` and map a
  raising handler to an `isError` result. Driven directly (stub params
  object), with no version-specific client.
- The REAL module-level server construction advertises our version.
- Raw JSON-RPC stdio smoke: a modern-era client (`server/discover` with
  the 2026-07-28 per-request `_meta` envelope) and a legacy-era client
  (`initialize` handshake + `tools/list`) both connect to the real server
  construction and list tools. No client library is used.

The old shim's `MCP2`-flag test died with the shim (the probe it encoded is
meaningless once 1.x is unsupported); every other portable test from the
shim suite is carried over here against the inlined adapters.

Async work is driven via `asyncio.run` (not bare `async def` tests) so this
file passes with or without `pytest-asyncio` installed.

Run with:
    python -m pytest tests/test_mcp_compat.py -q
"""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.server import Server
from mcp.types import TextContent, Tool, ToolAnnotations

REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"


@lru_cache(maxsize=1)
def _get_srv():
    """Load src/flextoolsmcp/server.py directly via importlib (as in
    test_mcp_tools.py) so the adapters under test are server.py's own."""
    import importlib.util

    server_py = SRC_DIR / "flextoolsmcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_server_module", str(server_py))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec from {server_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _fake_list_tools():
    return [Tool(name="probe", description="probe", inputSchema={"type": "object"})]


async def _fake_call_tool(name, arguments):
    if name == "boom":
        raise RuntimeError("kaboom")
    return [TextContent(type="text", text=f"ok:{name}")]


def _make_server(version=None):
    """A Server built exactly as server.py builds its own, with fakes."""
    srv = _get_srv()
    kwargs = {}
    if version is not None:
        kwargs["version"] = version
    return Server(
        "test-srv",
        on_list_tools=srv.make_list_tools_handler(_fake_list_tools),
        on_call_tool=srv.make_call_tool_handler(
            _fake_call_tool, srv.make_schema_provider(_fake_list_tools)
        ),
        **kwargs,
    )


def test_resolve_server_version_is_never_empty():
    srv = _get_srv()
    assert isinstance(srv.resolve_server_version(), str)
    assert srv.resolve_server_version() != ""


def test_server_construction_carries_explicit_version():
    """serverInfo.version carries OUR version, not mcp's (or empty)."""
    srv = _make_server(version="9.9.9")
    assert isinstance(srv, Server)
    opts = srv.create_initialization_options()
    assert opts.server_version == "9.9.9"


def test_list_tools_adapter_wraps_tool_list():
    handler = _get_srv().make_list_tools_handler(_fake_list_tools)
    result = asyncio.run(handler(None, None))
    assert [t.name for t in result.tools] == ["probe"]


def test_call_tool_adapter_wraps_bare_content():
    handler = _get_srv().make_call_tool_handler(_fake_call_tool)
    params = SimpleNamespace(name="probe", arguments={})
    result = asyncio.run(handler(None, params))
    assert not result.is_error
    assert [c.text for c in result.content] == ["ok:probe"]


def test_call_tool_adapter_maps_exception_to_is_error():
    """A raising handler becomes an isError result."""
    handler = _get_srv().make_call_tool_handler(_fake_call_tool)
    params = SimpleNamespace(name="boom", arguments={})
    result = asyncio.run(handler(None, params))
    assert result.is_error
    assert "kaboom" in result.content[0].text


def test_call_tool_adapter_tolerates_null_arguments():
    """`params.arguments or {}` -- a null arguments payload reaches the handler."""
    seen = {}

    async def _recording(name, arguments):
        seen.update(arguments)
        return [TextContent(type="text", text="ok")]

    handler = _get_srv().make_call_tool_handler(_recording)
    result = asyncio.run(handler(None, SimpleNamespace(name="x", arguments=None)))
    assert not result.is_error
    assert seen == {}


# ---------------------------------------------------------------------------
# annotation_is_read_only: the mcp 2.x ToolAnnotations spelling (issue #369;
# the cold-session gate reads read_only_hint -- reading only the old 1.x
# camelCase spelling silently disabled auto-init for read-only tools).
# ---------------------------------------------------------------------------


def test_annotation_helper_reads_read_only_hint():
    srv = _get_srv()
    assert srv.annotation_is_read_only(ToolAnnotations(read_only_hint=True))
    assert not srv.annotation_is_read_only(ToolAnnotations(read_only_hint=False))
    assert not srv.annotation_is_read_only(None)


def test_real_tool_annotations_resolve():
    """The shipped TOOL_DEFINITIONS must read correctly under mcp 2.x --
    this is the exact lookup server.py's cold-session gate performs."""
    srv = _get_srv()
    from flextoolsmcp.server.tool_definitions import TOOLS

    assert srv.annotation_is_read_only(
        TOOLS["flextools_search_by_capability"].annotations
    )
    assert not srv.annotation_is_read_only(TOOLS["flextools_run_module"].annotations)


# ---------------------------------------------------------------------------
# Adapter input pre-validation (issue #83 review, preserved by #369 --
# without it, a rejected first call initializes the cold session, because
# a raw 2.x on_call_tool handler does not pre-validate).
# ---------------------------------------------------------------------------

_STRICT_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


async def _strict_schema_provider():
    return {"probe": _STRICT_SCHEMA}


def test_call_tool_adapter_prevalidates_before_delegating():
    """Invalid arguments are rejected WITHOUT invoking the handler -- so the
    cold-session gate inside never runs and the session stays untouched."""
    called = []

    async def _recording(name, arguments):
        called.append(name)
        return [TextContent(type="text", text="ok")]

    handler = _get_srv().make_call_tool_handler(_recording, _strict_schema_provider)
    params = SimpleNamespace(name="probe", arguments={"text": 123})
    result = asyncio.run(handler(None, params))
    assert result.is_error
    assert "Input validation error" in result.content[0].text
    assert called == []


def test_call_tool_adapter_valid_arguments_delegate():
    handler = _get_srv().make_call_tool_handler(_fake_call_tool, _strict_schema_provider)
    params = SimpleNamespace(name="probe", arguments={"text": "hi"})
    result = asyncio.run(handler(None, params))
    assert not result.is_error
    assert [c.text for c in result.content] == ["ok:probe"]


def test_call_tool_adapter_unknown_tool_delegates_without_schema():
    """No schema for the name (e.g. unknown tool) -- fail open to the handler,
    which owns the unknown_tool envelope."""
    handler = _get_srv().make_call_tool_handler(_fake_call_tool, _strict_schema_provider)
    params = SimpleNamespace(name="other", arguments={"anything": 1})
    result = asyncio.run(handler(None, params))
    assert not result.is_error
    assert [c.text for c in result.content] == ["ok:other"]


def test_call_tool_adapter_failing_provider_fails_open():
    """A schema provider that raises must never break valid calls."""

    async def _boom_provider():
        raise RuntimeError("schemas unavailable")

    handler = _get_srv().make_call_tool_handler(_fake_call_tool, _boom_provider)
    params = SimpleNamespace(name="probe", arguments={"text": "hi"})
    result = asyncio.run(handler(None, params))
    assert not result.is_error


# ---------------------------------------------------------------------------
# Real construction: the module-level `server` object in server.py.
# ---------------------------------------------------------------------------


def test_real_server_construction_advertises_our_version():
    """The real server construction's serverInfo.version is
    resolve_server_version() -- never the mcp 2.x default of ""."""
    srv = _get_srv()
    assert isinstance(srv.server, Server)
    opts = srv.server.create_initialization_options()
    assert opts.server_version == srv.resolve_server_version()
    assert opts.server_version != ""


# ---------------------------------------------------------------------------
# Raw JSON-RPC stdio smoke tests (no client library): both protocol eras
# against the REAL server construction (the module-level `server` object,
# served over stdio_server exactly as main() serves it, minus main()'s
# index preload, which tools/list does not need).
# ---------------------------------------------------------------------------

_CHILD_CODE = (
    "import asyncio\n"
    "from mcp.server.stdio import stdio_server\n"
    "from flextoolsmcp.server import server\n"
    "async def main():\n"
    "    async with stdio_server() as (read_stream, write_stream):\n"
    "        await server.run(read_stream, write_stream,\n"
    "                         server.create_initialization_options())\n"
    "asyncio.run(main())\n"
)

_MODERN_META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {},
    "io.modelcontextprotocol/clientInfo": {"name": "smoke", "version": "0"},
}


class _StdioServerProcess:
    def __init__(self, tmp_path):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC_DIR)
        env["FLEXTOOLSMCP_LOG_DIR"] = str(tmp_path / "logs")
        self.proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD_CODE],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(tmp_path),
        )
        self._lines: queue.Queue = queue.Queue()

        def _reader():
            for line in self.proc.stdout:
                self._lines.put(line)

        threading.Thread(target=_reader, daemon=True).start()

    def send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def recv(self, timeout=90):
        try:
            line = self._lines.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise AssertionError(
                "timed out waiting for a JSON-RPC response from the server"
            ) from None
        return json.loads(line)

    def close(self):
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
            self.proc.wait(timeout=30)
        except Exception:
            self.proc.kill()


def test_stdio_smoke_modern_discover_and_tools_list(tmp_path):
    """Modern era: server/discover (2026-07-28 envelope) + tools/list."""
    proc = _StdioServerProcess(tmp_path)
    try:
        proc.send({
            "jsonrpc": "2.0", "id": 1, "method": "server/discover",
            "params": {"_meta": _MODERN_META},
        })
        discover = proc.recv()
        assert "error" not in discover, discover
        result = discover["result"]
        assert "2026-07-28" in result["supportedVersions"]
        assert "tools" in result["capabilities"]
        assert result["instructions"]
        server_info = result["_meta"]["io.modelcontextprotocol/serverInfo"]
        assert server_info["name"] == "flextools-mcp"
        assert server_info["version"] == _get_srv().resolve_server_version()

        proc.send({
            "jsonrpc": "2.0", "id": 2, "method": "tools/list",
            "params": {"_meta": _MODERN_META},
        })
        listed = proc.recv()
        assert "error" not in listed, listed
        names = [t["name"] for t in listed["result"]["tools"]]
        assert "flextools_start" in names
        assert len(names) >= 10
    finally:
        proc.close()
    assert proc.proc.returncode == 0


def test_stdio_smoke_legacy_initialize_and_tools_list(tmp_path):
    """Legacy era: initialize handshake + notifications/initialized +
    tools/list on the same real server construction."""
    proc = _StdioServerProcess(tmp_path)
    try:
        proc.send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "0"},
            },
        })
        init = proc.recv()
        assert "error" not in init, init
        result = init["result"]
        assert result["protocolVersion"] == "2025-11-25"
        assert result["serverInfo"]["name"] == "flextools-mcp"
        assert result["serverInfo"]["version"] == _get_srv().resolve_server_version()

        proc.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        proc.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = proc.recv()
        assert "error" not in listed, listed
        names = [t["name"] for t in listed["result"]["tools"]]
        assert "flextools_start" in names
        assert len(names) >= 10
    finally:
        proc.close()
    assert proc.proc.returncode == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
