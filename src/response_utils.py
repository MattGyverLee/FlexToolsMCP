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
from typing import Any, Callable, Dict, Optional


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
