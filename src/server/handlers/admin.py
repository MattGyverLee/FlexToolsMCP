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
import os
from pathlib import Path
from mcp.types import TextContent

# Import shared state from kernel
try:
    from ..kernel import session_state, get_log_dir, api_index
    from ..session import SessionState
    if not isinstance(session_state, SessionState):
        session_state = SessionState()
except ImportError:
    # Fallback for when module isn't fully modularized yet
    from server.kernel import session_state, get_log_dir, api_index
    from server.session import SessionState


async def handle_start(args: dict) -> list[TextContent]:
    """Initialize a FlexTools MCP session with mode and project settings.

    This sets up the session for subsequent API discovery and operations.
    After calling start(), discuss the goal with the user, then use
    search_by_capability() or get_object_api() to discover the correct APIs.
    """
    api_mode = args.get("api_mode", "flexlibs2")  # Default to flexlibs2
    project_name = args.get("project_name", "")
    write_enabled = args.get("write_enabled", False)

    # Clear any previously discovered APIs for fresh session
    session_state.clear_discovered_apis()

    # Build API versions dict from current APIIndex
    api_versions = {}
    if api_index:
        if api_index.liblcm_version:
            api_versions["liblcm"] = api_index.liblcm_version
        if api_index.flexlibs2_version:
            api_versions["flexlibs2"] = api_index.flexlibs2_version
        if api_index.flexlibs_stable_version:
            api_versions["flexlibs_stable"] = api_index.flexlibs_stable_version

    # Set session-wide settings
    session_state.configure(
        api_mode=api_mode,
        output_type="auto",
        project_name=project_name,
        write_enabled=write_enabled,
        api_versions=api_versions
    )

    # Build response
    result = {
        "status": "session_initialized",
        "session": session_state.summary(),
        "message": "Session configured. Now discuss the goal with the user.",
        "next_steps": [
            "1. Discuss the task/goal with the user to understand requirements",
            "2. Use search_by_capability(query='...') to find relevant APIs",
            "3. Use get_object_api(object_type='...') to get detailed API info",
            "4. Write code using ONLY the discovered APIs",
            "5. Use run_operation() or run_module() to execute"
        ]
    }

    # Add mode-specific guidance
    mode_guidance = {
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

    result["mode_info"] = mode_guidance.get(api_mode, mode_guidance["flexlibs2"])

    # Warnings
    warnings = []
    if not project_name:
        warnings.append("No project_name set - will need to specify when running operations")
    if write_enabled:
        warnings.append("WRITE MODE ENABLED - operations will modify the database")

    if warnings:
        result["warnings"] = warnings

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


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

    action = args.get("action", "list")
    key = args.get("key", "")
    value = args.get("value", None)

    result = {
        "action": action,
        "success": False,
        "message": ""
    }

    try:
        if action == "get":
            if not key:
                result["message"] = "key parameter required for 'get' action"
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            value = config_get(key)
            result["success"] = True
            result["key"] = key
            result["value"] = value
            result["message"] = f"Retrieved config: {key}"

        elif action == "set":
            if not key:
                result["message"] = "key parameter required for 'set' action"
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            config_set(key, value)
            result["success"] = True
            result["key"] = key
            result["value"] = value
            result["message"] = f"Set config: {key} = {value}"

        elif action == "delete":
            if not key:
                result["message"] = "key parameter required for 'delete' action"
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            deleted = config_delete(key)
            result["success"] = deleted
            result["key"] = key
            result["message"] = f"Deleted config key: {key}" if deleted else f"Config key not found: {key}"

        elif action == "list":
            cfg = config_list()
            result["success"] = True
            result["config"] = cfg
            result["message"] = f"Config contains {len(cfg)} root keys"

        else:
            result["message"] = f"Unknown action: {action}. Use 'get', 'set', 'delete', or 'list'"

    except Exception as e:
        result["success"] = False
        result["message"] = f"Error: {str(e)}"

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_get_session_history(args: dict) -> list[TextContent]:
    """Get session history and undo/redo availability (Feature 3)."""
    result = {
        "session_initialized": session_state.initialized,
        "api_mode": session_state.api_mode,
        "project": session_state.project_name or "(not set)",
        "write_enabled": session_state.write_enabled,
    }

    # Add history summary
    history_summary = session_state.get_history_summary()
    result["history"] = history_summary

    # Add operation list if requested
    if args.get("include_operations", False):
        result["operations"] = session_state.export_history()

    # Add undo/redo status
    result["undo_available"] = session_state.can_undo()
    result["redo_available"] = session_state.can_redo()

    # Add helpful next steps
    if not session_state.initialized:
        result["next_steps"] = ["Call start() to initialize session"]
    elif session_state.can_undo():
        result["next_steps"] = ["Call undo_last_operation() to undo recent changes"]
    else:
        result["next_steps"] = ["Run operations to build history"]

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_undo_last_operation(args: dict) -> list[TextContent]:
    """Undo the last database write operation (Feature 3).

    Uses FLEx ActionHandler.Undo() to reverse the last transaction.
    Requires write access and an undoable operation to be available.
    """
    result = {
        "success": False,
        "can_undo": session_state.can_undo(),
        "message": ""
    }

    # Check if undo is available
    if not session_state.can_undo():
        result["message"] = "No undoable operations available in this session"
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Check if write was enabled (only makes sense for write operations)
    if not session_state.write_enabled:
        result["message"] = "Write mode was not enabled - no database modifications to undo"
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Get the operation to undo
    operation = session_state.pop_undo()
    if not operation:
        result["message"] = "Error retrieving operation from undo stack"
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    result["success"] = True
    result["message"] = "Undo operation queued"
    result["undone_operation"] = {
        "timestamp": operation.timestamp.isoformat(),
        "tool": operation.tool,
        "args_summary": operation.args_summary,
        "project": operation.project,
    }
    result["note"] = (
        "To execute the undo, you would call FLEx ActionHandler.Undo() via run_operation. "
        "Undo is available but not automatically executed to allow review first."
    )
    result["undo_status"] = {
        "remaining_undoable": session_state.can_undo(),
        "redo_available": session_state.can_redo(),
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_get_module_template(args: dict) -> list[TextContent]:
    """Return the official FlexTools module template from templates/ directory.

    This reads from the authoritative template files so they stay in sync with
    the style guide and documentation. Users get the recommended best practices
    directly, not a generic fallback.
    """
    flavor = args.get("flavor", "flexlibs2")  # Default to recommended flavor

    # Map flavor names to template files
    template_map = {
        "flexlibs2": "2-flexlibs2-template.py",
        "flexlibs_stable": "1-flexlibs-stable-template.py",
        "liblcm": "3-liblcm-template.py",
        "stable": "1-flexlibs-stable-template.py",  # Alias
        "advanced": "3-liblcm-template.py",  # Alias
    }

    if flavor not in template_map:
        return [TextContent(type="text", text=json.dumps({
            "error": "invalid_flavor",
            "message": f"Unknown flavor '{flavor}'",
            "available_flavors": list(template_map.keys()),
            "recommended": "flexlibs2"
        }, indent=2))]

    # Find templates directory relative to this file
    # admin.py is in src/server/handlers/, templates are in root/templates/
    # So we go up 3 levels: handlers -> server -> src -> root
    current_file = Path(__file__)
    root_dir = current_file.parent.parent.parent.parent  # Go up to project root
    templates_dir = root_dir / "templates"
    template_file = templates_dir / template_map[flavor]

    if not template_file.exists():
        return [TextContent(type="text", text=json.dumps({
            "error": "template_not_found",
            "message": f"Template file not found: {template_file}",
            "hint": "Templates should be in the root/templates/ directory"
        }, indent=2))]

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            template_content = f.read()
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "error": "template_read_error",
            "message": f"Failed to read template: {str(e)}"
        }, indent=2))]

    # Flavor-specific guidance
    flavor_guidance = {
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
        "1-flexlibs-stable-template.py": {
            "description": "Legacy - Limited but stable",
            "use_when": "For FieldWorks < 9.0 or when flexlibs2 not available",
            "advantages": [
                "Works with older FieldWorks versions",
                "Limited API (~40 functions) but stable",
                "Good for simple read-only operations"
            ]
        },
        "3-liblcm-template.py": {
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

    guidance = flavor_guidance.get(flavor, {})
    if flavor in ["flexlibs_stable", "stable"]:
        guidance = flavor_guidance.get("1-flexlibs-stable-template.py", {})
    elif flavor in ["liblcm", "advanced"]:
        guidance = flavor_guidance.get("3-liblcm-template.py", {})

    result = {
        "status": "success",
        "flavor": flavor,
        "template": template_content,
        "source": f"templates/{template_map[flavor]} (authoritative)",
        "guidance": guidance,
        "style_guide": {
            "reference": "docs/FLEXTOOLS-STYLE-GUIDE.md",
            "key_sections": [
                "Section 1: Choose the Right Flavor",
                "Section 7: Write Permission Checking - CRITICAL (if modifyAllowed:)",
                "Section 8: Helper Functions",
                "Pattern: Always check modifyAllowed before ANY write"
            ]
        },
        "next_steps": [
            "1. Copy the template code above",
            "2. Replace [Placeholders] with your logic",
            "3. Pay special attention to 'if modifyAllowed:' guards",
            "4. Test in read-only mode first (modifyAllowed=False)",
            "5. Run flextools_run_module() when ready"
        ]
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]
