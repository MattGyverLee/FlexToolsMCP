#!/usr/bin/env python3
"""Publish smoke: full stdio MCP initialize + tools/list over the wire.

The publish workflow already imports ``list_tools()`` in-process after wheel
install (specs/mcp2-compat/deferred-issues.md section 4). That catches import
and handler registration breaks but not stdio transport or JSON-RPC framing.
This script launches the installed console entry (``flextools-mcp`` by
default), completes ``initialize``, and asserts ``tools/list`` returns a
non-empty tool list.

Usage::

    python scripts/smoke_stdio_handshake.py flextools-mcp
    python scripts/smoke_stdio_handshake.py python3 -c "from flextoolsmcp.server import run; run()"

Exit 0 on success, 1 on failure. Intended for CI only; requires ``mcp`` 2.x
(already a dependency of the installed wheel).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


async def _handshake(server_command: str, server_args: list[str]) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=server_command,
        args=server_args,
        env=os.environ.copy(),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            count = len(tools.tools)
            print(f"stdio handshake OK: {count} tools over MCP wire")
            if count < 10:
                print(
                    f"expected at least 10 tools, got {count}",
                    file=sys.stderr,
                )
                return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "server_argv",
        nargs=argparse.REMAINDER,
        help="Server command (default: flextools-mcp)",
    )
    parsed = parser.parse_args(argv)
    server_argv = parsed.server_argv or ["flextools-mcp"]
    if server_argv[0] == "--":
        server_argv = server_argv[1:]
    if not server_argv:
        server_argv = ["flextools-mcp"]
    command = server_argv[0]
    args = server_argv[1:]
    try:
        return asyncio.run(_handshake(command, args))
    except Exception as exc:
        print(f"stdio MCP handshake failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
