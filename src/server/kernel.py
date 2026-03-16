#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared kernel state for FlexToolsMCP.

Manages:
- APIIndex (loaded API documentation)
- SessionState (session configuration and history)
- PatternTracker (API usage patterns)
- Logging configuration
- Lazy module loading for optional dependencies (Feature 4)
"""

import sys
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass, field

# Import local modules
from .session import SessionState

# Import PatternTracker (will be defined in patterns.py later, for now import from server.py)
# This is imported at module level after everything is set up

# ===== Feature 4: Lazy Module Loading =====

# Track MCP import errors
_mcp_error: Optional[str] = None
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, CallToolResult
except ImportError as exc:
    _mcp_error = str(exc)
    Server = None  # type: ignore
    stdio_server = None  # type: ignore
    Tool = None  # type: ignore
    TextContent = None  # type: ignore
    CallToolResult = None  # type: ignore


def check_mcp_available() -> Tuple[bool, Optional[str]]:
    """Check if MCP library is available.

    Returns:
        Tuple of (is_available, error_message)
    """
    if _mcp_error:
        return False, _mcp_error
    return True, None


def _ensure_flexlibs2() -> Tuple[Optional[object], Optional[str]]:
    """Ensure FlexLibs 2.0 is available and can be imported.

    Follows the pattern from liblcm_extractor.init_pythonnet().

    Returns:
        Tuple of (module, error_message) where module is None if import failed
    """
    try:
        # This will be called when FlexLibs 2.0 operations are attempted
        # For now, just verify it can be imported
        if __package__:
            import flexlibs2
        else:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent / "flexlibs2" / "src"))
            import flexlibs2
        return flexlibs2, None
    except ImportError as e:
        error_msg = f"FlexLibs 2.0 not available: {e}"
        return None, error_msg
    except Exception as e:
        error_msg = f"Error loading FlexLibs 2.0: {e}"
        return None, error_msg


# ===== Logging Setup =====

def get_log_dir() -> Path:
    """Get the log directory path (~/.flextoolsmcp/logs/).

    Respects config if available (will be integrated in Feature 2).
    """
    log_dir = Path.home() / ".flextoolsmcp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging():
    """Configure file logging for operations."""
    log_dir = get_log_dir()
    log_file = log_dir / "operations.log"

    # Create a logger for operations
    logger = logging.getLogger("flextoolsmcp.operations")
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers
    if not logger.handlers:
        # File handler with rotation (max 5MB, keep 3 backups)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        # Format: timestamp | level | message
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-7s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Initialize the operations logger
operations_logger = setup_logging()


# ===== Shared Kernel State =====

# Global session state (shared across all tool handlers)
session_state: SessionState = SessionState()

# Global API index (loaded during server startup)
api_index: Optional[object] = None  # Will be APIIndex type, avoid circular import

# Global pattern tracker (imported from patterns.py after it's defined)
pattern_tracker: Optional[object] = None

# MCP Server instance (lazy loaded in main())
mcp_server: Optional[object] = None


def get_index_dir() -> Path:
    """Get the index directory path.

    Respects config if available (will be integrated in Feature 2).
    Currently returns hardcoded path, updated by config fallback in Feature 2.
    """
    return Path(__file__).parent.parent.parent / "index"


def initialize_kernel() -> Tuple[bool, Optional[str]]:
    """Initialize the kernel state for server startup.

    Checks for required dependencies and sets up shared state.

    Returns:
        Tuple of (success, error_message)
    """
    global api_index, mcp_server

    # Check MCP availability
    mcp_available, mcp_error = check_mcp_available()
    if not mcp_available:
        return False, f"MCP library not available: {mcp_error}\nInstall with: pip install mcp"

    # Initialize MCP server
    try:
        mcp_server = Server("flextools-mcp")
        operations_logger.info("MCP server initialized")
    except Exception as e:
        return False, f"Failed to initialize MCP server: {e}"

    # Load API indexes (non-blocking - will load what's available)
    try:
        from src.server import APIIndex  # Temporary import, will be resolved during modularization
        api_index = APIIndex.load(get_index_dir())
        operations_logger.info("API indexes loaded successfully")
    except Exception as e:
        operations_logger.warning(f"Warning: Could not load API indexes: {e}")
        # Non-fatal error - server can still run with limited functionality

    operations_logger.info("Kernel initialization complete")
    return True, None


def reset_session() -> None:
    """Reset session state for a new session.

    Called by the 'start' tool to begin a new session.
    """
    global session_state
    session_state = SessionState()
    operations_logger.info("Session state reset")


def get_session_state() -> SessionState:
    """Get the current session state."""
    global session_state
    if session_state is None:
        session_state = SessionState()
    return session_state
