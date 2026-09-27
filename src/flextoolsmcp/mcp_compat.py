#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp 1.x / 2.x compatibility shim (issue #83).

mcp 2.0.0 removed the low-level ``Server.list_tools()`` / ``Server.call_tool()``
decorator API in favor of constructor-injected ``on_list_tools=`` /
``on_call_tool=`` handlers. Everything else this repo touches
(``stdio_server``, ``server.run()``, ``create_initialization_options()``,
camelCase ``mcp.types`` kwargs) is identical across both majors, so the entire
compat surface is the single :func:`build_server` function below.

``list_tools()`` and ``call_tool(name, arguments)`` in ``server.py`` keep their
signatures and bodies verbatim -- they stop being decorated and are passed to
``build_server()`` instead. ``dispatch.py`` and ``handlers/*.py`` keep
returning bare ``list[TextContent]``; the 2.x branch wraps them in
``CallToolResult`` at this single seam.

Deliberately NOT in the 2.x branch: ``jsonschema`` pre-validation of
``arguments`` against ``inputSchema``. mcp 1.x's decorator validated before
calling; a raw 2.x ``on_call_tool`` handler does not. That is nearly a no-op
here because ``tool_definitions.get_schema()`` generates ``inputSchema`` from
the same Pydantic model ``server.py`` re-validates against -- the constraint
set is identical, only the error *shape* differs (the repo's own
``invalid_input`` JSON instead of mcp's ``isError`` text).
"""

from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from mcp.server import Server

# mcp 2.0 removed the decorator API entirely -- no ``list_tools``/``call_tool``
# attribute exists on Server at all (verified against 2.0.0 and 2.2.0: raises
# ``AttributeError``). On 1.x these are instance methods, so a class-level
# probe distinguishes both majors with no version parsing.
MCP2 = not hasattr(Server, "call_tool")


def resolve_server_version() -> str:
    """Best-effort flextools-mcp version string for ``serverInfo.version``.

    Prefers installed package metadata, falls back to a ``VERSION`` file found
    by walking up from this module (covers source checkouts), then to the dev
    placeholder. Mirrors the logic in ``server/kernel.py``'s session header.
    """
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("flextools-mcp")
    except Exception:
        pass
    try:
        here = Path(__file__).resolve()
        for parent in here.parents:
            version_file = parent / "VERSION"
            if version_file.exists():
                text = version_file.read_text(encoding="utf-8").strip()
                if text:
                    return text
                break
    except Exception:
        pass
    return "0.0.0.dev0"


def _construct(name: str, version: str, **kwargs: Any) -> Server:
    """``Server(name, version=..., **kwargs)`` with a bare-name fallback.

    The ``version`` kwarg exists on every verified 1.x/2.x constructor; the
    fallback covers only hypothetical older 1.x constructors without it.
    """
    try:
        return Server(name, version=version, **kwargs)
    except TypeError:
        return Server(name, **kwargs)


def make_list_tools_handler(
    list_tools_fn: Callable[[], Awaitable[list]],
) -> Callable[[Any, Any], Awaitable[Any]]:
    """Adapt ``async () -> list[Tool]`` to mcp 2.x's ``on_list_tools`` handler.

    Only used on the 2.x branch of :func:`build_server`; factored to module
    level so tests can drive it directly with a stub ``params`` object.
    """
    from mcp.types import ListToolsResult

    async def _on_list_tools(ctx: Any, params: Any) -> Any:
        return ListToolsResult(tools=await list_tools_fn())

    return _on_list_tools


def make_call_tool_handler(
    call_tool_fn: Callable[[str, dict], Awaitable[list]],
) -> Callable[[Any, Any], Awaitable[Any]]:
    """Adapt ``async (name, arguments) -> list[TextContent]`` to ``on_call_tool``.

    Wraps the bare content list in ``CallToolResult`` and maps a raising
    handler to an ``isError`` result (mirroring mcp 1.x's decorator behavior).
    Only used on the 2.x branch; factored out for direct testing.
    """
    from mcp.types import CallToolResult, TextContent

    async def _on_call_tool(ctx: Any, params: Any) -> Any:
        try:
            content = await call_tool_fn(params.name, params.arguments or {})
        except Exception as exc:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {exc}")],
                isError=True,
            )
        return CallToolResult(content=list(content))

    return _on_call_tool


def build_server(
    name: str,
    list_tools_fn: Callable[[], Awaitable[list]],
    call_tool_fn: Callable[[str, dict], Awaitable[list]],
    version: Optional[str] = None,
) -> Server:
    """Build an ``mcp.server.Server`` with tool handlers registered.

    Args:
        name: Server name advertised in ``serverInfo``.
        list_tools_fn: ``async () -> list[Tool]`` -- server.py's body, verbatim.
        call_tool_fn: ``async (name, arguments) -> list[TextContent]`` --
            server.py's body, verbatim.
        version: Version string for ``serverInfo.version``. Defaults to
            :func:`resolve_server_version`. Passed explicitly because mcp 2.x
            defaults it to ``""`` while 1.x defaulted to the mcp library
            version -- explicit is parity on both, and more useful.

    Returns:
        A ``Server`` with both handlers registered, on either major.
    """
    server_version = version if version is not None else resolve_server_version()

    if not MCP2:
        srv = _construct(name, server_version)
        # On 1.x the decorators are just registration callables -- applying
        # them explicitly is equivalent to the old ``@``-syntax.
        srv.list_tools()(list_tools_fn)
        srv.call_tool()(call_tool_fn)
        return srv

    return _construct(
        name,
        server_version,
        on_list_tools=make_list_tools_handler(list_tools_fn),
        on_call_tool=make_call_tool_handler(call_tool_fn),
    )
