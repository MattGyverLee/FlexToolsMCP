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
    """Return the official FlexTools module template."""
    module_name = args.get("module_name", "<Module name>")
    synopsis = args.get("synopsis", "<description>")
    modifies_db = args.get("modifies_db", False)

    template = '''#
#   {module_name}
#    - A FlexTools Module -
#
#   {synopsis}
#
#   Platforms: Python .NET and IronPython
#

from flextoolslib import *

#----------------------------------------------------------------
# Documentation that the user sees:

docs = {{FTM_Name        : "{module_name}",
        FTM_Version     : 1,
        FTM_ModifiesDB  : {modifies_db},
        FTM_Synopsis    : "{synopsis}",
        FTM_Description :
"""
<detailed description here>
""" }}

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    """
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    """
    report.Info("Starting...")

    # Example: iterate all entries
    # for entry in project.LexiconAllEntries():
    #     headword = project.LexiconGetHeadword(entry)
    #     report.Info("Entry: {{}}".format(headword))

    report.Info("Done.")

#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
'''.format(
        module_name=module_name,
        synopsis=synopsis,
        modifies_db=modifies_db
    )

    result = {
        "template": template,
        "notes": [
            "FTM_Version should be an integer (1, 2, 3...), not a string",
            "Main function must be named 'Main' (not 'MainFunction')",
            "Use .format() for string formatting (IronPython compatible), not f-strings",
            "Do not use type hints (IronPython does not support them)",
            "Do not use pathlib (use os.path instead for IronPython compatibility)",
            "FlexToolsModule = FlexToolsModuleClass(Main, docs) uses positional args"
        ],
        "report_methods": [
            "report.Info(message) - Informational message",
            "report.Warning(message) - Warning message",
            "report.Error(message) - Error message",
            "report.Blank() - Blank line",
            "report.FileURL(path) - Create clickable file link"
        ]
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]
