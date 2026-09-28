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

Deliberately NOT in the 2.x branch: anything beyond input pre-validation.
mcp 1.x's decorator validated ``arguments`` against ``inputSchema`` before
calling; a raw 2.x ``on_call_tool`` handler does not. The adapter below
closes that gap with ``jsonschema`` (a hard mcp 2.x dependency) because the
divergence is behavioral, not cosmetic: server.py's cold-session gate
configures session state *before* its own Pydantic re-validation, so without
pre-validation a rejected first call would initialize the session on 2.x
while leaving it cold on 1.x.
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


def annotation_is_read_only(annotations: Any) -> bool:
    """True when a tool annotations object marks the tool read-only-safe.

    mcp 1.x spells the field ``readOnlyHint``, mcp 2.x spells it
    ``read_only_hint`` -- and each major exposes ONLY its own spelling on
    attribute read (construction accepts both via pydantic aliases). Reading
    just one spelling silently resolves to False on the other major, which
    disabled cold-session auto-initialization for every read-only tool under
    2.x. Read both, plus mapping-style fallbacks for dict-shaped annotations.
    """
    if annotations is None:
        return False
    for attr in ("read_only_hint", "readOnlyHint"):
        try:
            if getattr(annotations, attr, False):
                return True
        except Exception:
            continue
    if isinstance(annotations, dict):
        return bool(
            annotations.get("read_only_hint", annotations.get("readOnlyHint", False))
        )
    return False


_CAMEL_TO_SNAKE = {
    "readOnlyHint": "read_only_hint",
    "destructiveHint": "destructive_hint",
    "idempotentHint": "idempotent_hint",
    "openWorldHint": "open_world_hint",
    "inputSchema": "input_schema",
    "outputSchema": "output_schema",
    "isError": "is_error",
}
_SNAKE_TO_CAMEL = {v: k for k, v in _CAMEL_TO_SNAKE.items()}


def annotation_value(annotations: Any, camel_name: str) -> Any:
    """Read one annotations field across both majors' spellings.

    Test helper (and future production use): mcp 1.x exposes camelCase
    (``readOnlyHint``), mcp 2.x exposes snake_case (``read_only_hint``);
    each major exposes ONLY its own on attribute read. Reads snake first,
    then camel, then dict-style lookups under both keys. Returns None when
    absent on both spellings (mirrors the old ``getattr(ann,
    "readOnlyHint", None)`` default).
    """
    if annotations is None:
        return None
    snake = _CAMEL_TO_SNAKE.get(camel_name, camel_name)
    for attr in (snake, camel_name):
        try:
            value = getattr(annotations, attr, None)
        except Exception:
            continue
        # getattr(obj, name, None) with pydantic v2 can still raise
        # AttributeError for the foreign spelling instead of returning the
        # default -- the try/except above covers that; an explicit None
        # means "field exists but unset", so keep probing the other spelling.
        if value is not None:
            return value
    if isinstance(annotations, dict):
        if snake in annotations:
            return annotations[snake]
        return annotations.get(camel_name)
    # vars() fallback for objects whose __getattr__ is hostile: pydantic
    # v2 stores field values in __dict__ under the canonical name.
    try:
        d = vars(annotations)
        if snake in d:
            return d[snake]
        if camel_name in d:
            return d[camel_name]
    except Exception:
        pass
    return None


def normalized_annotation_keys(annotations: Any) -> set:
    """Annotation key set normalized to camelCase across both majors.

    ``vars(ToolAnnotations)`` yields snake_case on mcp 2.x and camelCase on
    1.x; normalizing lets one assertion cover both (see
    test_annotations_have_required_keys).
    """
    if annotations is None:
        return set()
    if isinstance(annotations, dict):
        keys = set(annotations.keys())
    else:
        try:
            keys = set(vars(annotations).keys())
        except Exception:
            keys = set()
    return {_SNAKE_TO_CAMEL.get(k, k) for k in keys}


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


def _tool_input_schema(tool: Any) -> Any:
    """A Tool's input schema across both majors' field spellings.

    Same mirror-image layout as the annotations (``input_schema`` on 2.x,
    ``inputSchema`` on 1.x); each major exposes only its own on read.
    """
    for attr in ("input_schema", "inputSchema"):
        try:
            schema = getattr(tool, attr, None)
        except Exception:
            continue
        if schema:
            return schema
    return None


def tool_input_schema(tool: Any) -> Any:
    """Public alias for :func:`_tool_input_schema` (test seam).

    Kept as a thin wrapper so tests import a non-underscore name while the
    internal schema-provider path keeps its existing reference.
    """
    return _tool_input_schema(tool)


def make_schema_provider(
    list_tools_fn: Callable[[], Awaitable[list]],
) -> Callable[[], Awaitable[dict]]:
    """Build the ``{tool_name: inputSchema}`` provider for pre-validation.

    Factored out of :func:`build_server` so tests can wire the real tool list
    to the real adapter and prove rejected calls never reach the dispatcher.
    Tools without a readable schema are skipped (fail-open per tool).
    """

    async def _provider() -> dict:
        schemas: dict = {}
        for tool in await list_tools_fn():
            schema = _tool_input_schema(tool)
            if schema:
                schemas[tool.name] = schema
        return schemas

    return _provider


def make_call_tool_handler(
    call_tool_fn: Callable[[str, dict], Awaitable[list]],
    schema_provider: Optional[Callable[[], Awaitable[dict]]] = None,
) -> Callable[[Any, Any], Awaitable[Any]]:
    """Adapt ``async (name, arguments) -> list[TextContent]`` to ``on_call_tool``.

    Wraps the bare content list in ``CallToolResult`` and maps a raising
    handler to an ``isError`` result (mirroring mcp 1.x's decorator behavior).
    Only used on the 2.x branch; factored out for direct testing.

    When ``schema_provider`` is given (``async () -> {tool_name: inputSchema}``,
    wired by :func:`build_server` from the same tool list), arguments are
    pre-validated with ``jsonschema`` before delegating -- the 1.x decorator
    validated before calling, and without this a rejected first call would
    initialize the cold session on 2.x while leaving it cold on 1.x. A
    validation failure returns the same ``isError`` shape 1.x produced
    (``Input validation error: ...``). Unknown tools (no schema), a failing
    provider, or a missing ``jsonschema`` all fail open to plain delegation.
    """
    from mcp.types import CallToolResult, TextContent

    try:
        from jsonschema import ValidationError as _ValidationError
        from jsonschema import validate as _validate_jsonschema
    except Exception:  # jsonschema absent -- pre-validation skipped (fail-open)
        _ValidationError = None  # type: ignore[assignment]
        _validate_jsonschema = None  # type: ignore[assignment]

    _schema_cache: Optional[dict] = None

    async def _schemas() -> dict:
        nonlocal _schema_cache
        if _schema_cache is None and schema_provider is not None:
            try:
                _schema_cache = await schema_provider()
            except Exception:
                _schema_cache = {}
        return _schema_cache or {}

    async def _on_call_tool(ctx: Any, params: Any) -> Any:
        name = params.name
        arguments = params.arguments or {}
        if _validate_jsonschema is not None and schema_provider is not None:
            schema = (await _schemas()).get(name)
            if schema:
                try:
                    _validate_jsonschema(instance=arguments, schema=schema)
                except _ValidationError as exc:
                    return CallToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text=f"Input validation error: {exc.message}",
                            )
                        ],
                        isError=True,
                    )
        try:
            content = await call_tool_fn(name, arguments)
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
    instructions: Optional[str] = None,
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
        instructions: Optional server instructions string (unified-recipes
            FR-027). Forwarded to ``Server(..., instructions=...)`` on both
            majors through the compat shim.

    Returns:
        A ``Server`` with both handlers registered, on either major.
    """
    server_version = version if version is not None else resolve_server_version()

    if not MCP2:
        srv = _construct(name, server_version, instructions=instructions)
        # On 1.x the decorators are just registration callables -- applying
        # them explicitly is equivalent to the old ``@``-syntax. The 1.x
        # decorator pre-validates arguments itself, so no schema wiring here.
        srv.list_tools()(list_tools_fn)
        srv.call_tool()(call_tool_fn)
        return srv

    kwargs: dict = {}
    if instructions is not None:
        kwargs["instructions"] = instructions
    return _construct(
        name,
        server_version,
        on_list_tools=make_list_tools_handler(list_tools_fn),
        on_call_tool=make_call_tool_handler(
            call_tool_fn, make_schema_provider(list_tools_fn)
        ),
        **kwargs,
    )
