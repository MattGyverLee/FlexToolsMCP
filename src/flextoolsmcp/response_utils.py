#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Response Utilities: Centralized error handling and response formatting for MCP server.

Provides:
- Structured error envelopes for all tool returns
- Decorator for catching unhandled exceptions and formatting as structured errors
- Safe JSON serialization with sensible defaults
"""

import json
import functools
import traceback
from typing import Any, Callable, Dict, List

# Issue #54: contract version for the tool-response envelope.
# Increment to 2.0 when the deprecated nested-error shape is removed.
CONTRACT_VERSION = "tool-responses/1.0"

# Import MCP types for type hints
try:
    from mcp.types import TextContent
except ImportError:
    TextContent = None  # Fallback if MCP not available


def make_error(code: str, message: str, **extra) -> Dict[str, Any]:
    """
    Create a standard error envelope for tool returns.

    Args:
        code: Error code (e.g., 'INVALID_ARGUMENT', 'FILE_NOT_FOUND', 'INTERNAL_ERROR')
        message: Human-readable error message
        **extra: Additional fields to include (e.g., details, traceback, file_path)

    Returns:
        A dict with 'error' key containing code, message, and any extra fields

    Example:
        >>> err = make_error('FILE_NOT_FOUND', 'Config file not found', path='~/.config')
        >>> err['error']['code']
        'FILE_NOT_FOUND'
        >>> err['error']['message']
        'Config file not found'
        >>> err['error']['path']
        '~/.config'
    """
    error_dict = {
        'code': code,
        'message': message,
    }
    if extra:
        error_dict.update(extra)

    return {'error': error_dict}


def format_result(data: Dict[str, Any], **kwargs) -> str:
    """
    Format data as JSON string with safe serialization.

    Handles non-serializable types (datetime, Path, etc.) by converting to string.
    Ensures output is valid JSON with no encoding issues.

    Args:
        data: The dict to serialize
        **kwargs: Additional arguments passed to json.dumps (indent, sort_keys, etc.)

    Returns:
        JSON string with default formatting applied

    Example:
        >>> result = {'status': 'ok', 'count': 42}
        >>> json_str = format_result(result)
        >>> json.loads(json_str)
        {'status': 'ok', 'count': 42}
    """
    # Set sensible defaults
    kwargs.setdefault('indent', 2)
    kwargs.setdefault('default', str)
    kwargs.setdefault('ensure_ascii', False)

    return json.dumps(data, **kwargs)


def tool_handler(func: Callable) -> Callable:
    """
    Decorator that catches unhandled exceptions and returns structured errors.

    Wraps MCP tool functions to ensure all exceptions are caught and returned
    as properly formatted error objects instead of raising to the server.

    The decorated function should return a dict (result or error dict).
    If an unhandled exception occurs, it is caught and returned as an error dict.

    Args:
        func: The tool function to wrap

    Returns:
        Wrapped function that catches exceptions and returns error dicts

    Example:
        @tool_handler
        def my_tool(arg1: str) -> Dict:
            return {'status': 'ok', 'result': arg1}

        # If my_tool raises an exception, it returns:
        # {'error': {'code': 'INTERNAL_ERROR', 'message': '...', 'type': 'ValueError', 'traceback': '...'}}
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Dict[str, Any]:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            # Capture exception details
            error_dict = make_error(
                code='INTERNAL_ERROR',
                message=str(exc),
                type=type(exc).__name__,
                traceback=traceback.format_exc()
            )
            return error_dict

    return wrapper


def build_response_with_context(data: Dict[str, Any], include_session: bool = True) -> Dict[str, Any]:
    """Add session context and contract version stamp to tool response.

    If session is initialized, adds api_mode, write_enabled, and project to the response.
    Always stamps _contract=CONTRACT_VERSION on the response (issue #54).

    Args:
        data: The response data dict
        include_session: Whether to include session context (if available)

    Returns:
        The data dict, optionally with session_context added
    """
    # Issue #54: stamp every success response with the contract version.
    data.setdefault("_contract", CONTRACT_VERSION)

    # Issue #79: attach a proactive update notice (at most once per process)
    # when a newer flextools-mcp release is known from the cached PyPI check.
    # Fully self-contained and fail-open -- it never hits the network on this
    # path and never raises, so it can't break a tool response.
    if "update_notice" not in data:
        try:
            if __package__:
                from .update_check import get_update_notice
            else:
                from update_check import get_update_notice
            notice = get_update_notice()
            if notice:
                data["update_notice"] = notice
        except Exception:
            pass

    # Import here to avoid circular imports. Package-relative when installed,
    # absolute for script runs (dual-mode guard, per repo convention).
    if __package__:
        from .server.kernel import session_state
    else:
        from server.kernel import session_state

    if include_session and hasattr(session_state, 'initialized') and session_state.initialized:
        data["session_context"] = {
            "api_mode": session_state.api_mode,
            "write_enabled": session_state.write_enabled,
            "project": session_state.project_name or "(not set)"
        }

    return data


def json_response(data: Dict[str, Any], indent: int = 2, sort_keys: bool = False,
                   ensure_ascii: bool = False) -> List[Any]:
    """
    Format data as JSON response wrapped in MCP TextContent.

    Consolidates the repeated pattern across all handler modules of:
    1. Converting dict to JSON string
    2. Wrapping in TextContent
    3. Returning as list

    This is the preferred way to return successful JSON responses from tool handlers.

    Args:
        data: The dict to serialize as JSON
        indent: JSON indentation level (default: 2)
        sort_keys: Sort dictionary keys in output (default: False)
        ensure_ascii: Escape non-ASCII characters (default: False)

    Returns:
        List with single TextContent object suitable for MCP tool return

    Example:
        >>> result = {'status': 'ok', 'items': [1, 2, 3]}
        >>> return json_response(result)
        [TextContent(type='text', text='{"status": "ok", "items": [1, 2, 3]}')]
    """
    json_str = format_result(data, indent=indent, sort_keys=sort_keys,
                            ensure_ascii=ensure_ascii)

    if TextContent is None:
        # Fallback if MCP not available (e.g., unit tests)
        return [{"type": "text", "text": json_str}]

    return [TextContent(type="text", text=json_str)]


def error_response(error_code: str, message: str, **extra) -> List[Any]:
    """
    Format error as MCP TextContent response.

    Issue #54: emits BOTH the canonical flat envelope (status/error_code at top
    level) and the deprecated nested-error shape in the same payload for the
    transition window.  Both shapes carry identical content so existing callers
    reading ``data["error"]`` still work while new callers can read
    ``data["error_code"]`` without a compatibility shim.

    Canonical (new) top-level keys:
        _contract, status="error", error_code, message, hint (if provided),
        op_id (if provided), plus per-code detail keys spread at top level.

    Deprecated (retained) nested key:
        error: {code, message, ...same extras}

    Args:
        error_code: Machine-readable error code (e.g., 'syntax_error')
        message: Human-readable error message
        **extra: Additional fields included in both canonical and deprecated shapes

    Returns:
        List with single TextContent object suitable for MCP tool return
    """
    # Build canonical flat envelope.
    data: Dict[str, Any] = {
        "_contract": CONTRACT_VERSION,
        "status": "error",
        "error_code": error_code,
        "message": message,
    }
    # Spread detail keys at top level for canonical consumers.
    # Guard against clobbering canonical envelope keys.
    _canonical_keys = {"_contract", "status", "error_code", "message", "error"}
    collisions = _canonical_keys & extra.keys()
    if collisions:
        raise ValueError(
            f"error_response() extra keys collide with canonical envelope keys: {collisions}"
        )
    data.update(extra)

    # Deprecated nested shape -- retained for backward compat.
    # Contains identical content so round-tripping is lossless.
    nested: Dict[str, Any] = {"code": error_code, "message": message}
    nested.update(extra)
    # Avoid clobbering canonical "error_code" key with the nested object when
    # extra happens to contain keys that overlap.  The nested key is always
    # the plain string "error".
    data["error"] = nested

    if TextContent is None:
        # Fallback if MCP not available (e.g., unit tests)
        return [{"type": "text", "text": format_result(data)}]

    return [TextContent(type="text", text=format_result(data))]
