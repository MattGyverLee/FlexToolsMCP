#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified import helper for handler modules.

Consolidates the dual-mode import pattern (package mode vs. script mode)
that was previously duplicated in every handler (try/except ImportError).

This eliminates ~120 LOC of boilerplate across 5 handler modules and 6
separate try/except blocks in execution.py.
"""

from typing import Any


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
    try:
        # Import as package
        return __import__(package_import_path, fromlist=[''])
    except ImportError:
        # Fall back to absolute import
        return __import__(fallback_import_path, fromlist=[''])


def safe_import_kernel_deps() -> tuple[Any, Any, Any, Any]:
    """Import kernel dependencies with fallback for both package and script modes.

    Returns:
        Tuple of (json_response, session_state, get_log_dir, get_api_index)

    Raises:
        ImportError: If neither import path succeeds
    """
    try:
        from ...response_utils import json_response
        from ..kernel import (
            session_state,
            get_log_dir,
            get_api_index,
        )
        return json_response, session_state, get_log_dir, get_api_index
    except ImportError:
        from response_utils import json_response
        from server.kernel import (
            session_state,
            get_log_dir,
            get_api_index,
        )
        return json_response, session_state, get_log_dir, get_api_index


def safe_import_logging_helpers() -> tuple[Any, Any]:
    """Import logging-related functions with fallback for both modes.

    Returns:
        Tuple of (rotate_logging_to_session, get_operations_logger)
    """
    try:
        from ..kernel import rotate_logging_to_session, get_operations_logger
        return rotate_logging_to_session, get_operations_logger
    except ImportError:
        from server.kernel import rotate_logging_to_session, get_operations_logger
        return rotate_logging_to_session, get_operations_logger


def safe_import_session_state() -> Any:
    """Import SessionState class with fallback for both modes.

    Returns:
        SessionState class
    """
    try:
        from ..session import SessionState
        return SessionState
    except ImportError:
        from server.session import SessionState
        return SessionState


def safe_import_api_index() -> Any:
    """Import get_api_index function with fallback for both modes.

    Returns:
        get_api_index function
    """
    try:
        from ..kernel import get_api_index
        return get_api_index
    except ImportError:
        from server.kernel import get_api_index
        return get_api_index
