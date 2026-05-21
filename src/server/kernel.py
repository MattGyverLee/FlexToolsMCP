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
import json
import logging
import logging.handlers
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field

# Import local modules
from .session import SessionState

if TYPE_CHECKING:
    from server import APIIndex

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
            import flexlibs2  # type: ignore
        else:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent.parent / "flexlibs2" / "src"))
            import flexlibs2  # type: ignore
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


def setup_logging(session_id: str = ""):
    """Configure file and console logging for operations.

    Args:
        session_id: Optional session ID (format: YYYYMMDD-HHMMSS) for organizing logs by date/session
                   If provided, logs are stored in logs/YYYY-MM-DD/session_ID.log
                   If not provided, logs go to logs/operations.log for backward compatibility
    """
    log_dir = get_log_dir()

    # Determine log file path based on session_id
    if session_id:
        # Extract date from session_id (format: YYYYMMDD-HHMMSS)
        date_part = session_id[:8]  # YYYYMMDD
        year = date_part[:4]
        month = date_part[4:6]
        day = date_part[6:8]
        dated_dir = log_dir / f"{year}-{month}-{day}"
        dated_dir.mkdir(parents=True, exist_ok=True)
        log_file = dated_dir / f"session_{session_id}.log"
    else:
        # Fallback to monolithic log for backward compatibility
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


def rotate_logging_to_session(session_id: str) -> None:
    """Rotate the logging handler to a new session-specific log file.

    Called by the start handler to switch from the default operations.log
    to a per-session log file organized by date.

    Args:
        session_id: Session ID (format: YYYYMMDD-HHMMSS)
    """
    global operations_logger

    if not operations_logger:
        return

    # Remove existing file handlers
    for handler in operations_logger.handlers[:]:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            operations_logger.removeHandler(handler)
            handler.close()

    # Create dated directory structure
    log_dir = get_log_dir()
    date_part = session_id[:8]  # YYYYMMDD
    year = date_part[:4]
    month = date_part[4:6]
    day = date_part[6:8]
    dated_dir = log_dir / f"{year}-{month}-{day}"
    dated_dir.mkdir(parents=True, exist_ok=True)
    log_file = dated_dir / f"session_{session_id}.log"

    # Add new file handler for the session
    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-7s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    operations_logger.addHandler(file_handler)
    operations_logger.info(f"Switched to session log: session_{session_id}.log")
    _emit_session_header(session_id)


def _emit_session_header(session_id: str) -> None:
    """Write a one-time environment block to the session log.

    Captures versions / OS / python so a .log pasted into a bug report
    is enough to identify the build that produced it -- without requiring
    the user to dig up an MCP startup banner.
    """
    if not operations_logger:
        return

    import platform
    try:
        from .versioning import detect_installed_library_version
    except ImportError:
        from server.versioning import detect_installed_library_version  # type: ignore

    def _safe(label: str, fn) -> str:
        try:
            return fn() or "(unknown)"
        except Exception as exc:
            return f"(error: {exc})"

    flexlibs2_ver = _safe("flexlibs2", lambda: detect_installed_library_version(
        "FlexLibs 2.0", import_path="flexlibs2", package_name="flexlibs2"
    ))
    liblcm_ver = _safe("liblcm", lambda: detect_installed_library_version(
        "LibLCM", assembly_name="SIL.LCModel"
    ))

    server_ver = "(unknown)"
    try:
        from importlib.metadata import version as _pkg_version
        server_ver = _pkg_version("flextoolsmcp")
    except Exception:
        pass

    log = operations_logger
    log.info("=== Session Environment ===")
    log.info(f"Session ID:      {session_id}")
    log.info(f"FlexToolsMCP:    {server_ver}")
    log.info(f"FlexLibs 2.0:    {flexlibs2_ver}")
    log.info(f"LibLCM:          {liblcm_ver}")
    log.info(f"Python:          {platform.python_implementation()} {platform.python_version()}")
    log.info(f"OS:              {platform.system()} {platform.release()} ({platform.machine()})")
    log.info("=== End Session Environment ===")


# Lazy-initialized: operations logger is set up in initialize_kernel()
operations_logger: Optional[logging.Logger] = None


# ===== Pattern Tracking =====

# Pattern dict schema constants (avoid stringly-typed keys)
_PATTERN_KEY_API = "api_patterns"
_PATTERN_KEY_ERROR = "error_patterns"
_PATTERN_KEY_SUCCESS = "success_count"
_PATTERN_KEY_FAILURE = "failure_count"

@dataclass
class PatternTracker:
    """Tracks API patterns with success/failure counts for learning.

    Maintains bounded cache (max 1000 API patterns, max 500 error patterns)
    to prevent unbounded memory growth in long-running sessions.
    """
    patterns_file: Optional[Path] = None
    patterns: Dict = field(default_factory=dict)
    _MAX_API_PATTERNS = 1000
    _MAX_ERROR_PATTERNS = 500

    def __post_init__(self):
        if self.patterns_file is None:
            self.patterns_file = get_log_dir() / "patterns.json"
        # Only load if patterns dict is empty (avoid reinitializing)
        if not self.patterns:
            self.load()

    def load(self):
        """Load patterns from disk."""
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, 'r', encoding='utf-8') as f:
                    self.patterns = json.load(f)
            except Exception as e:
                if operations_logger:
                    operations_logger.warning(f"Failed to load patterns: {e}")
                self.patterns = {_PATTERN_KEY_API: {}, _PATTERN_KEY_ERROR: {}}
        else:
            self.patterns = {_PATTERN_KEY_API: {}, _PATTERN_KEY_ERROR: {}}

    def _evict_stale_patterns(self):
        """Enforce bounded cache size by evicting least recently used patterns."""
        api_patterns = self.patterns.get(_PATTERN_KEY_API, {})
        if len(api_patterns) > self._MAX_API_PATTERNS:
            # Sort by last_used, evict oldest 20%
            sorted_patterns = sorted(
                api_patterns.items(),
                key=lambda x: x[1].get("last_used") or ""
            )
            num_to_remove = len(api_patterns) // 5
            for api_call, _ in sorted_patterns[:num_to_remove]:
                del api_patterns[api_call]

        error_patterns = self.patterns.get(_PATTERN_KEY_ERROR, {})
        if len(error_patterns) > self._MAX_ERROR_PATTERNS:
            sorted_errors = sorted(
                error_patterns.items(),
                key=lambda x: x[1].get("first_seen") or ""
            )
            num_to_remove = len(error_patterns) // 5
            for error_key, _ in sorted_errors[:num_to_remove]:
                del error_patterns[error_key]

    def save(self):
        """Save patterns to disk."""
        try:
            self._evict_stale_patterns()
            # Import here to avoid circular dependency
            from ..json_utils import sort_json_arrays
            patterns_to_save = sort_json_arrays(self.patterns)
            with open(self.patterns_file, 'w', encoding='utf-8') as f:
                json.dump(patterns_to_save, f, indent=2, ensure_ascii=False, sort_keys=True)
        except Exception as e:
            operations_logger.warning(f"Failed to save patterns: {e}")

    def extract_api_calls(self, code: str) -> List[str]:
        """Extract API method calls from code."""
        patterns = []
        # Match patterns like: ClassName(project).Method() or ops.Method()
        method_pattern = r'(\w+Operations)\s*\(\s*\w+\s*\)\s*\.\s*(\w+)'
        for match in re.finditer(method_pattern, code):
            patterns.append(f"{match.group(1)}.{match.group(2)}")

        # Match patterns like: project.MethodName()
        project_pattern = r'project\s*\.\s*(\w+)\s*\('
        for match in re.finditer(project_pattern, code):
            patterns.append(f"project.{match.group(1)}")

        # Match attribute access like: entry.SensesOS, sense.Gloss
        attr_pattern = r'(\w+)\s*\.\s*((?:[A-Z]\w*OS|[A-Z]\w*OC|[A-Z]\w*RS|[A-Z]\w*RC|Gloss\w*|Definition\w*|Headword|Form\w*))'
        for match in re.finditer(attr_pattern, code):
            patterns.append(f"*.{match.group(2)}")

        return list(set(patterns))  # Deduplicate

    def record_operation(self, code: str, success: bool, error_msg: str | None = None, error_type: str | None = None):
        """Record an operation's success or failure for pattern learning."""
        api_calls = self.extract_api_calls(code)

        for api_call in api_calls:
            if api_call not in self.patterns[_PATTERN_KEY_API]:
                self.patterns[_PATTERN_KEY_API][api_call] = {
                    _PATTERN_KEY_SUCCESS: 0,
                    _PATTERN_KEY_FAILURE: 0,
                    "last_used": None,
                    "common_errors": {}
                }

            pattern_data = self.patterns[_PATTERN_KEY_API][api_call]
            pattern_data["last_used"] = datetime.now().isoformat()

            if success:
                pattern_data[_PATTERN_KEY_SUCCESS] += 1
            else:
                pattern_data[_PATTERN_KEY_FAILURE] += 1
                if error_type:
                    if error_type not in pattern_data["common_errors"]:
                        pattern_data["common_errors"][error_type] = {"count": 0, "example": ""}
                    pattern_data["common_errors"][error_type]["count"] += 1
                    if error_msg:
                        pattern_data["common_errors"][error_type]["example"] = error_msg[:200]

        # Track error patterns for FlexLibs bug identification
        if not success and error_msg:
            error_key = self._normalize_error(error_msg)
            if error_key not in self.patterns[_PATTERN_KEY_ERROR]:
                self.patterns[_PATTERN_KEY_ERROR][error_key] = {
                    "count": 0,
                    "examples": [],
                    "api_calls": [],
                    "first_seen": datetime.now().isoformat(),
                    "potential_fix": None
                }

            err_pattern = self.patterns[_PATTERN_KEY_ERROR][error_key]
            err_pattern["count"] += 1
            if len(err_pattern["examples"]) < 3:
                err_pattern["examples"].append({
                    "code": code[:500],
                    "error": error_msg[:500],
                    "timestamp": datetime.now().isoformat()
                })
            for api_call in api_calls:
                if api_call not in err_pattern["api_calls"]:
                    err_pattern["api_calls"].append(api_call)

        self.save()

    def _normalize_error(self, error_msg: str) -> str:
        """Normalize error message to group similar errors."""
        # Remove specific values, keep the pattern
        normalized = error_msg
        # Remove hex addresses
        normalized = re.sub(r'0x[0-9a-fA-F]+', '0x...', normalized)
        # Remove line numbers
        normalized = re.sub(r'line \d+', 'line N', normalized)
        # Remove specific object names in quotes
        normalized = re.sub(r"'[^']{20,}'", "'...'", normalized)
        # Take first 100 chars as key
        return normalized[:100]

    def get_recommendations(self) -> Dict:
        """Get pattern-based recommendations for API usage."""
        recommendations = {
            "preferred_patterns": [],
            "patterns_to_avoid": [],
            "common_errors_needing_fix": []
        }

        # Find high-success patterns
        for api_call, data in self.patterns.get("api_patterns", {}).items():
            total = data["success_count"] + data["failure_count"]
            if total >= 3:  # Need at least 3 uses to make a recommendation
                success_rate = data["success_count"] / total
                if success_rate >= 0.8:
                    recommendations["preferred_patterns"].append({
                        "pattern": api_call,
                        "success_rate": round(success_rate * 100, 1),
                        "uses": total
                    })
                elif success_rate <= 0.3:
                    recommendations["patterns_to_avoid"].append({
                        "pattern": api_call,
                        "success_rate": round(success_rate * 100, 1),
                        "uses": total,
                        "common_errors": list(data.get("common_errors", {}).keys())[:3]
                    })

        # Find recurring errors that need FlexLibs fixes
        for error_key, data in self.patterns.get("error_patterns", {}).items():
            if data["count"] >= 2:  # Recurring error
                recommendations["common_errors_needing_fix"].append({
                    "error_pattern": error_key,
                    "count": data["count"],
                    "affected_apis": data["api_calls"][:5],
                    "potential_fix": data.get("potential_fix")
                })

        # Sort by relevance
        recommendations["preferred_patterns"].sort(key=lambda x: -x["uses"])
        recommendations["patterns_to_avoid"].sort(key=lambda x: x["success_rate"])
        recommendations["common_errors_needing_fix"].sort(key=lambda x: -x["count"])

        return recommendations


# ===== Shared Kernel State =====

# Global session state (shared across all tool handlers)
session_state: SessionState = SessionState()

# Global API index (loaded during server startup)
api_index: Optional["APIIndex"] = None

# Global pattern tracker (lazy-initialized in initialize_kernel() to avoid disk I/O on import)
pattern_tracker: Optional[PatternTracker] = None

# MCP Server instance (lazy loaded in main())
mcp_server: Optional[object] = None

# ===== Write Operation Serialization =====
# Per-project write locks to prevent concurrent CUD operations on same database
# Key: project_name, Value: asyncio.Lock
# Only locked when: write_enabled=True AND is_cud=True
project_write_locks: Dict[str, asyncio.Lock] = {}


def get_project_write_lock(project_name: str) -> asyncio.Lock:
    """Get or create the write lock for a project.

    Write locks serialize CUD (Create/Update/Delete) operations on the same
    FieldWorks project to prevent database corruption from concurrent writes.

    Args:
        project_name: Name of the FieldWorks project

    Returns:
        asyncio.Lock for this project (creates if doesn't exist)
    """
    if project_name not in project_write_locks:
        project_write_locks[project_name] = asyncio.Lock()
    return project_write_locks[project_name]


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
    global api_index, mcp_server, operations_logger, pattern_tracker

    # Initialize logging (moved from module-level to avoid blocking I/O on import)
    operations_logger = setup_logging()

    # Lazy-initialize pattern tracker (moved from module-level to avoid disk I/O on import)
    pattern_tracker = PatternTracker()

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
        from server import APIIndex  # Temporary import, will be resolved during modularization
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
    if operations_logger:
        operations_logger.info("Session state reset")


def get_session_state() -> SessionState:
    """Get the current session state."""
    global session_state
    if session_state is None:
        session_state = SessionState()
    return session_state


def set_api_index(index: "APIIndex") -> None:
    """Set the global API index (called by server.py after loading).

    Args:
        index: The APIIndex instance loaded by server.py
    """
    global api_index
    api_index = index


def get_api_index() -> Optional["APIIndex"]:
    """Get the current API index.

    Returns the APIIndex instance, or None if not yet loaded.
    Use this function instead of importing api_index directly to ensure
    you always get the most recent version (especially important after
    set_api_index() is called during server startup).

    Returns:
        The current APIIndex instance, or None
    """
    global api_index
    return api_index


def init_operations_logger() -> logging.Logger:
    """Initialize and return the operations logger.

    Called by server.py at startup to set up logging before handlers are used.

    Returns:
        The initialized logger instance
    """
    global operations_logger
    operations_logger = setup_logging()
    return operations_logger


def get_operations_logger() -> Optional[logging.Logger]:
    """Get the current operations logger.

    Returns the logger instance, or None if not yet initialized.
    Use this function instead of importing operations_logger directly.

    Returns:
        The operations logger instance, or None
    """
    global operations_logger
    return operations_logger


def get_pattern_tracker() -> Optional[PatternTracker]:
    """Get the current pattern tracker.

    Returns the pattern tracker instance, or None if not yet initialized.
    Use this function instead of importing pattern_tracker directly to ensure
    you always get the most recent version (especially important after
    initialize_kernel() is called during server startup).

    Returns:
        The current PatternTracker instance, or None
    """
    global pattern_tracker
    return pattern_tracker
