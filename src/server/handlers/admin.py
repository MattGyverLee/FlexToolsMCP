#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin handler functions for FlexToolsMCP.

These handlers manage session configuration and provide admin tools:
- start: Initialize session with mode and project settings
- manage_config: Get/set/delete/list persistent configuration (Feature 2)
- get_session_history: View operation history and undo availability (Feature 3)
- undo_last_operation: Undo the most recent database write (Feature 3)
- get_module_template: Return the official FlexTools module template
"""

import json
from pathlib import Path
from mcp.types import TextContent

# Import response utilities and shared state (with fallback for both modes)
try:
    from ...response_utils import json_response
    from ..kernel import session_state, get_log_dir, get_api_index
    from ..session import SessionState
    from ..response_keys import (
        KEY_MESSAGE, KEY_STATUS, KEY_SESSION, KEY_ERROR, KEY_SOURCE,
        KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED, KEY_HISTORY,
        KEY_TEMPLATE, KEY_WARNINGS
    )
except ImportError:
    # Fallback for when module isn't fully modularized yet
    from response_utils import json_response
    from server.kernel import session_state, get_log_dir, get_api_index
    from server.session import SessionState
    from server.response_keys import (
        KEY_MESSAGE, KEY_STATUS, KEY_SESSION, KEY_ERROR, KEY_SOURCE,
        KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED, KEY_HISTORY,
        KEY_TEMPLATE, KEY_WARNINGS
    )

if not isinstance(session_state, SessionState):
    session_state = SessionState()


# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
# Shared constants imported from response_keys:
# - KEY_MESSAGE, KEY_STATUS, KEY_SESSION, KEY_ERROR, KEY_SOURCE
# - KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED, KEY_HISTORY
# - KEY_TEMPLATE, KEY_WARNINGS (above)

# Admin-specific constants
KEY_ACTION = "action"
KEY_KEY = "key"
KEY_VALUE = "value"
KEY_CONFIG = "config"
KEY_INITIALIZED = "session_initialized"
KEY_API_MODE = "api_mode"
KEY_OPERATIONS = "operations"
KEY_INCLUDE_OPERATIONS = "include_operations"
KEY_UNDO_AVAILABLE = "undo_available"
KEY_REDO_AVAILABLE = "redo_available"
KEY_NEXT_STEPS = "next_steps"
KEY_CAN_UNDO = "can_undo"
KEY_MODE_INFO = "mode_info"
KEY_FLAVOR = "flavor"
KEY_GUIDANCE = "guidance"
KEY_STYLE_GUIDE = "style_guide"
KEY_UNDONE_OPERATION = "undone_operation"
KEY_TIMESTAMP = "timestamp"
KEY_TOOL = "tool"
KEY_ARGS_SUMMARY = "args_summary"
KEY_UNDO_STATUS = "undo_status"
KEY_NOTE = "note"
KEY_REMAINING_UNDOABLE = "remaining_undoable"

# Template flavors mapping
TEMPLATE_MAP = {
    "flexlibs2": "2-flexlibs2-template.py",
    "flexlibs_stable": "1-flexlibs-stable-template.py",
    "liblcm": "3-liblcm-template.py",
    "stable": "1-flexlibs-stable-template.py",  # Alias
    "advanced": "3-liblcm-template.py",  # Alias
}

# Template guidance (static data, not rebuilt per request)
FLAVOR_GUIDANCE = {
    "flexlibs2": {
        "description": "Recommended - Best documented, 90% API coverage",
        "use_when": "For most projects with FieldWorks 9.0+",
        "advantages": [
            "Automatic '***' multistring normalization",
            "Better error messages",
            "Comprehensive coverage (~200 functions)",
            "Well documented with many examples"
        ]
    },
    "flexlibs_stable": {
        "description": "Legacy - Limited but stable",
        "use_when": "For FieldWorks < 9.0 or when flexlibs2 not available",
        "advantages": [
            "Works with older FieldWorks versions",
            "Limited API (~40 functions) but stable",
            "Good for simple read-only operations"
        ]
    },
    "liblcm": {
        "description": "Advanced - Full API access",
        "use_when": "For edge cases not covered by flexlibs2",
        "advantages": [
            "100% API coverage",
            "Direct C# access for complex operations",
            "Performance-critical code"
        ],
        "warning": "Complex code, hard to maintain. Use flexlibs2 first."
    }
}

# Mode guidance for API initialization
MODE_GUIDANCE = {
    "flexlibs2": {
        "description": "FlexLibs 2.0 - Pythonic wrapper with Operations classes",
        "example": "project.LexEntries.GetAll(), project.Wordforms.GetForm(wf)",
        "note": "Recommended mode - best documentation and examples"
    },
    "flexlibs_stable": {
        "description": "FlexLibs Stable - Original wrapper with LibLCM fallback",
        "example": "project.LexiconAllEntries(), entry.SensesOS",
        "note": "Use when compatibility with existing scripts needed"
    },
    "liblcm": {
        "description": "Pure LibLCM - Direct C# API access via pythonnet",
        "example": "entry.SensesOS, sense.Gloss.get_String(wsHandle)",
        "note": "Low-level access - requires understanding of LCM suffixes (OS/OC/OA/RS/RC/RA)"
    }
}

# Project root for template path resolution
PROJECT_ROOT = Path(__file__).parents[3]

# Template cache (loaded once at module init, not per request)
_TEMPLATE_CACHE: dict[str, str] = {}


# ============================================================
# Helpers
# ============================================================
def _get_flavor_guidance(flavor: str) -> dict:
    """Get guidance for a flavor, handling aliases."""
    # Handle aliases
    if flavor in ["flexlibs_stable", "stable"]:
        flavor = "flexlibs_stable"
    elif flavor in ["liblcm", "advanced"]:
        flavor = "liblcm"
    return FLAVOR_GUIDANCE.get(flavor, FLAVOR_GUIDANCE["flexlibs2"])


def _get_template(flavor: str) -> str | None:
    """Load and cache template file content (O(1) lookup after first call).

    Args:
        flavor: Template flavor (e.g., 'flexlibs2')

    Returns:
        Template file content, or None if not found

    Impact:
        Eliminates 50-100ms disk I/O on repeated requests by caching
        template files at module initialization instead of per-request read.
    """
    # Return cached result if available (O(1) lookup)
    if flavor in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[flavor]

    # Not cached yet - load from disk and cache
    if flavor not in TEMPLATE_MAP:
        return None

    templates_dir = PROJECT_ROOT / "templates"
    template_file = templates_dir / TEMPLATE_MAP[flavor]

    if not template_file.exists():
        return None

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()
        _TEMPLATE_CACHE[flavor] = content
        return content
    except Exception:
        return None


async def handle_start(args: dict) -> list[TextContent]:
    """Initialize a FlexTools MCP session with mode and project settings.

    This sets up the session for subsequent API discovery and operations.
    After calling start(), discuss the goal with the user, then use
    search_by_capability() or get_object_api() to discover the correct APIs.

    If project_name is provided, queries the project to list:
    - Available writing systems and their language tags
    - Number of entries in the project
    """
    api_mode = args.get(KEY_API_MODE, "flexlibs2")
    # Note: Pydantic model uses 'project_name', not 'project'
    project_name = args.get("project_name") or args.get(KEY_PROJECT) or ""
    write_enabled = args.get(KEY_WRITE_ENABLED, False)

    # Clear any previously discovered APIs for fresh session
    session_state.clear_discovered_apis()

    # Build API versions dict from current APIIndex (more Pythonic)
    api_versions = {}
    if get_api_index():
        if get_api_index().liblcm_version:
            api_versions["liblcm"] = get_api_index().liblcm_version
        if get_api_index().flexlibs2_version:
            api_versions["flexlibs2"] = get_api_index().flexlibs2_version
        if get_api_index().flexlibs_stable_version:
            api_versions["flexlibs_stable"] = get_api_index().flexlibs_stable_version

    # Set session-wide settings
    session_state.configure(
        api_mode=api_mode,
        output_type="auto",
        project_name=project_name,
        write_enabled=write_enabled,
        api_versions=api_versions
    )

    # Query project metadata if project_name provided
    project_metadata = {}
    project_metadata_error = None
    if project_name:
        import time
        project = None

        # Retry opening project - LibLCM may need a moment to fully initialize
        for attempt in range(3):
            try:
                from flexlibs2 import FLExProject

                project = FLExProject()
                project.OpenProject(project_name, writeEnabled=False)
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < 2:
                    # Not the last attempt, wait a moment and retry
                    time.sleep(0.5)
                else:
                    # Last attempt failed, raise the exception
                    raise

        try:

            # Classify writing systems by type
            vernacular_ws = []
            analysis_ws = []
            default_vernacular = None
            default_analysis = None

            try:
                # Get default writing systems
                try:
                    default_vernacular = project.WritingSystems.GetDefaultVernacular()
                except:
                    pass

                try:
                    default_analysis = project.WritingSystems.GetDefaultAnalysis()
                except:
                    pass

                # Get vernacular writing systems
                try:
                    for ws in project.WritingSystems.GetVernacular():
                        try:
                            display_name = project.WritingSystems.GetDisplayName(ws)
                            language_tag = project.WritingSystems.GetLanguageTag(ws)
                            ws_info = {
                                "name": display_name,
                                "tag": language_tag
                            }
                            if ws == default_vernacular:
                                ws_info["default"] = True
                            vernacular_ws.append(ws_info)
                        except:
                            pass
                except:
                    pass

                # Get analysis writing systems
                try:
                    for ws in project.WritingSystems.GetAnalysis():
                        try:
                            display_name = project.WritingSystems.GetDisplayName(ws)
                            language_tag = project.WritingSystems.GetLanguageTag(ws)
                            ws_info = {
                                "name": display_name,
                                "tag": language_tag
                            }
                            if ws == default_analysis:
                                ws_info["default"] = True
                            analysis_ws.append(ws_info)
                        except:
                            pass
                except:
                    pass
            except:
                pass

            # Get entry count
            entry_count = 0
            try:
                entry_count = len(list(project.LexEntry.GetAll()))
            except Exception as e:
                pass

            # Close project
            try:
                project.CloseProject()
            except:
                pass

            project_metadata = {
                "writing_systems": {
                    "vernacular": vernacular_ws,
                    "analysis": analysis_ws
                },
                "entry_count": entry_count
            }
        except Exception as e:
            # Project couldn't be queried, store error for response
            import traceback
            project_metadata_error = {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc()
            }

    # Build response
    result = {
        KEY_STATUS: "session_initialized",
        KEY_SESSION: session_state.summary(),
        KEY_MESSAGE: "Session configured. Now discuss the goal with the user.",
        KEY_NEXT_STEPS: [
            "1. Discuss the task/goal with the user to understand requirements",
            "2. Use search_by_capability(query='...') to find relevant APIs",
            "3. Use get_object_api(object_type='...') to get detailed API info",
            "4. Write code using ONLY the discovered APIs",
            "5. Use run_operation() or run_module() to execute"
        ]
    }

    result[KEY_MODE_INFO] = MODE_GUIDANCE.get(api_mode, MODE_GUIDANCE["flexlibs2"])

    # Add project metadata or error to response
    if project_metadata_error:
        result["project_metadata_error"] = project_metadata_error
    elif project_metadata:
        result["project_metadata"] = project_metadata
    elif project_name:
        # project_name was set but no metadata and no error - return empty metadata
        result["project_metadata"] = {
            "writing_systems": {"vernacular": [], "analysis": []},
            "entry_count": 0,
            "note": "Failed to retrieve metadata but no error was captured"
        }

    # Warnings
    warnings = []
    if not project_name:
        warnings.append("No project_name set - will need to specify when running operations")
    if write_enabled:
        warnings.append("WRITE MODE ENABLED - operations will modify the database")

    if warnings:
        result[KEY_WARNINGS] = warnings

    return json_response(result)


async def handle_manage_config(args: dict) -> list[TextContent]:
    """Manage persistent configuration (Feature 2).

    Actions:
    - get: Retrieve a config value by dotted key
    - set: Set a config value
    - delete: Delete a config key
    - list: List entire configuration
    """
    try:
        from ..config import config_get, config_set, config_delete, config_list
    except ImportError:
        from config import config_get, config_set, config_delete, config_list

    action = args.get(KEY_ACTION, "list")
    key = args.get(KEY_KEY, "")
    value = args.get(KEY_VALUE, None)

    result = {
        KEY_ACTION: action,
        KEY_SUCCESS: False,
        KEY_MESSAGE: ""
    }

    try:
        if action == "get":
            if not key:
                result[KEY_MESSAGE] = "key parameter required for 'get' action"
                return json_response(result)

            value = config_get(key)
            result[KEY_SUCCESS] = True
            result[KEY_KEY] = key
            result[KEY_VALUE] = value
            result[KEY_MESSAGE] = f"Retrieved config: {key}"

        elif action == "set":
            if not key:
                result[KEY_MESSAGE] = "key parameter required for 'set' action"
                return json_response(result)

            config_set(key, value)
            result[KEY_SUCCESS] = True
            result[KEY_KEY] = key
            result[KEY_VALUE] = value
            result[KEY_MESSAGE] = f"Set config: {key} = {value}"

        elif action == "delete":
            if not key:
                result[KEY_MESSAGE] = "key parameter required for 'delete' action"
                return json_response(result)

            deleted = config_delete(key)
            result[KEY_SUCCESS] = deleted
            result[KEY_KEY] = key
            result[KEY_MESSAGE] = f"Deleted config key: {key}" if deleted else f"Config key not found: {key}"

        elif action == "list":
            cfg = config_list()
            result[KEY_SUCCESS] = True
            result[KEY_CONFIG] = cfg
            result[KEY_MESSAGE] = f"Config contains {len(cfg)} root keys"

        else:
            result[KEY_MESSAGE] = f"Unknown action: {action}. Use 'get', 'set', 'delete', or 'list'"

    except Exception as e:
        result[KEY_SUCCESS] = False
        result[KEY_MESSAGE] = f"Error: {str(e)}"

    return json_response(result)


async def handle_get_session_history(args: dict) -> list[TextContent]:
    """Get session history and undo/redo availability (Feature 3)."""
    # Cache undo/redo status to avoid redundant computation
    can_undo = session_state.can_undo()
    can_redo = session_state.can_redo()

    result = {
        KEY_INITIALIZED: session_state.initialized,
        KEY_API_MODE: session_state.api_mode,
        KEY_PROJECT: session_state.project_name or "(not set)",
        KEY_WRITE_ENABLED: session_state.write_enabled,
    }

    # Add history summary
    history_summary = session_state.get_history_summary()
    result[KEY_HISTORY] = history_summary

    # Add operation list if requested
    if args.get(KEY_INCLUDE_OPERATIONS, False):
        result[KEY_OPERATIONS] = session_state.export_history()

    # Add undo/redo status
    result[KEY_UNDO_AVAILABLE] = can_undo
    result[KEY_REDO_AVAILABLE] = can_redo

    # Add helpful next steps
    if not session_state.initialized:
        result[KEY_NEXT_STEPS] = ["Call start() to initialize session"]
    elif can_undo:
        result[KEY_NEXT_STEPS] = ["Call undo_last_operation() to undo recent changes"]
    else:
        result[KEY_NEXT_STEPS] = ["Run operations to build history"]

    return json_response(result)


async def handle_undo_last_operation(args: dict) -> list[TextContent]:
    """Undo the last database write operation (Feature 3).

    Uses FLEx ActionHandler.Undo() to reverse the last transaction.
    Requires write access and an undoable operation to be available.
    """
    can_undo = session_state.can_undo()
    result = {
        KEY_SUCCESS: False,
        KEY_CAN_UNDO: can_undo,
        KEY_MESSAGE: ""
    }

    # Check if undo is available
    if not can_undo:
        result[KEY_MESSAGE] = "No undoable operations available in this session"
        return json_response(result)

    # Check if write was enabled (only makes sense for write operations)
    if not session_state.write_enabled:
        result[KEY_MESSAGE] = "Write mode was not enabled - no database modifications to undo"
        return json_response(result)

    # Get the operation to undo
    operation = session_state.pop_undo()
    if not operation:
        result[KEY_MESSAGE] = "Error retrieving operation from undo stack"
        return json_response(result)

    result[KEY_SUCCESS] = True
    result[KEY_MESSAGE] = "Undo operation queued"
    result[KEY_UNDONE_OPERATION] = {
        KEY_TIMESTAMP: operation.timestamp.isoformat(),
        KEY_TOOL: operation.tool,
        KEY_ARGS_SUMMARY: operation.args_summary,
        KEY_PROJECT: operation.project,
    }
    result[KEY_NOTE] = (
        "To execute the undo, you would call FLEx ActionHandler.Undo() via run_operation. "
        "Undo is available but not automatically executed to allow review first."
    )
    result[KEY_UNDO_STATUS] = {
        KEY_REMAINING_UNDOABLE: session_state.can_undo(),
        KEY_REDO_AVAILABLE: session_state.can_redo(),
    }

    return json_response(result)


async def handle_get_module_template(args: dict) -> list[TextContent]:
    """Return the official FlexTools module template from templates/ directory.

    This reads from the authoritative template files so they stay in sync with
    the style guide and documentation. Users get the recommended best practices
    directly, not a generic fallback.

    Uses module-level template cache to avoid repeated disk I/O (50-100ms savings).
    """
    flavor = args.get(KEY_FLAVOR, "flexlibs2")

    if flavor not in TEMPLATE_MAP:
        return json_response({
            KEY_ERROR: "invalid_flavor",
            KEY_MESSAGE: f"Unknown flavor '{flavor}'",
            "available_flavors": list(TEMPLATE_MAP.keys()),
            "recommended": "flexlibs2"
        })

    # Use cached template (O(1) lookup after first request)
    template_content = _get_template(flavor)

    if template_content is None:
        templates_dir = PROJECT_ROOT / "templates"
        template_file = templates_dir / TEMPLATE_MAP[flavor]
        return json_response({
            KEY_ERROR: "template_not_found",
            KEY_MESSAGE: f"Template file not found: {template_file}",
            "hint": "Templates should be in the root/templates/ directory"
        })

    # Get guidance using helper (handles aliases cleanly)
    guidance = _get_flavor_guidance(flavor)

    result = {
        KEY_STATUS: "success",
        KEY_FLAVOR: flavor,
        KEY_TEMPLATE: template_content,
        KEY_SOURCE: f"templates/{TEMPLATE_MAP[flavor]} (authoritative)",
        KEY_GUIDANCE: guidance,
        KEY_STYLE_GUIDE: {
            "reference": "docs/FLEXTOOLS-STYLE-GUIDE.md",
            "key_sections": [
                "Section 1: Choose the Right Flavor",
                "Section 7: Write Permission Checking - CRITICAL (if modifyAllowed:)",
                "Section 8: Helper Functions",
                "Pattern: Always check modifyAllowed before ANY write"
            ]
        },
        KEY_NEXT_STEPS: [
            "1. Copy the template code above",
            "2. Replace [Placeholders] with your logic",
            "3. Pay special attention to 'if modifyAllowed:' guards",
            "4. Test in read-only mode first (modifyAllowed=False)",
            "5. Run flextools_run_module() when ready"
        ]
    }

    return json_response(result)
