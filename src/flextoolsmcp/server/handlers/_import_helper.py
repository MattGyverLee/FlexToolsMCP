#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified import helper for handler modules.

Consolidates the dual-mode import pattern (package mode vs. script mode)
that was previously duplicated in every handler (try/except ImportError).

This eliminates ~120 LOC of boilerplate across 5 handler modules and 6
separate try/except blocks in execution.py.
"""

from typing import Any, Callable, TypeVar

_T = TypeVar("_T")


def _import_with_fallback(primary: Callable[[], _T], fallback: Callable[[], _T]) -> _T:
    """Run ``primary`` import; on ImportError only, run ``fallback``.

    If the fallback also raises ImportError, re-raise it chained from the
    first so diagnostics show both the package-mode and script-mode failures
    (mcp2-compat QC P2, specs/mcp2-compat/deferred-issues.md §3).
    """
    try:
        return primary()
    except ImportError as first_exc:
        try:
            return fallback()
        except ImportError as second_exc:
            raise second_exc from first_exc


def safe_import(package_import_path: str, fallback_import_path: str) -> Any:
    """Generic safe import with package/script mode fallback.

    Args:
        package_import_path: Import path for package mode (relative, e.g., '..kernel')
        fallback_import_path: Import path for script mode (absolute, e.g., 'server.kernel')

    Returns:
        The imported module or object

    Example:
        kernel = safe_import('..kernel', 'server.kernel')
    """
    return _import_with_fallback(
        lambda: __import__(package_import_path, fromlist=[""]),
        lambda: __import__(fallback_import_path, fromlist=[""]),
    )


def safe_import_kernel_deps() -> tuple[Any, Any, Any, Any]:
    """Import kernel dependencies with fallback for both package and script modes.

    Returns:
        Tuple of (json_response, session_state, get_log_dir, get_api_index)

    Raises:
        ImportError: If neither import path succeeds
    """

    def _package():
        from ...response_utils import json_response
        from ..kernel import (
            session_state,
            get_log_dir,
            get_api_index,
        )
        return json_response, session_state, get_log_dir, get_api_index
    def _script():
        from response_utils import json_response
        from server.kernel import (
            session_state,
            get_log_dir,
            get_api_index,
        )
        return json_response, session_state, get_log_dir, get_api_index

    def _script_server():
        # Third tier (P2, server.*-only script launches): same kernel deps,
        # but response_utils only exposed under server.*.
        from server.response_utils import json_response
        from server.kernel import (
            session_state,
            get_log_dir,
            get_api_index,
        )
        return json_response, session_state, get_log_dir, get_api_index

    return _import_with_fallback(
        _package, lambda: _import_with_fallback(_script, _script_server)
    )


def safe_import_logging_helpers() -> tuple[Any, Any]:
    """Import logging-related functions with fallback for both modes.

    Returns:
        Tuple of (rotate_logging_to_session, get_operations_logger)
    """

    def _package():
        from ..kernel import rotate_logging_to_session, get_operations_logger
        return rotate_logging_to_session, get_operations_logger

    def _script():
        from server.kernel import rotate_logging_to_session, get_operations_logger
        return rotate_logging_to_session, get_operations_logger

    return _import_with_fallback(_package, _script)


def safe_import_session_state() -> Any:
    """Import SessionState class with fallback for both modes.

    Returns:
        SessionState class
    """

    def _package():
        from ..session import SessionState
        return SessionState

    def _script():
        from server.session import SessionState
        return SessionState

    return _import_with_fallback(_package, _script)


def safe_import_api_index() -> Any:
    """Import get_api_index function with fallback for both modes.

    Returns:
        get_api_index function
    """

    def _package():
        from ..kernel import get_api_index
        return get_api_index

    def _script():
        from server.kernel import get_api_index
        return get_api_index

    return _import_with_fallback(_package, _script)
