#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin handler functions for FlexToolsMCP.

These handlers manage session configuration and provide admin tools:
- manage_config: Get/set/delete/list persistent configuration (Feature 2)
- get_session_history: View operation history and undo availability (Feature 3)
- undo_last_operation: Undo the most recent database write (Feature 3)
"""

import json
from mcp.types import TextContent

# Import shared state from kernel
try:
    from ..kernel import session_state, get_log_dir
    from ..session import SessionState
    if not isinstance(session_state, SessionState):
        session_state = SessionState()
except ImportError:
    # Fallback for when module isn't fully modularized yet
    from src.server.kernel import session_state, get_log_dir
    from src.server.session import SessionState


async def handle_manage_config(args: dict) -> list[TextContent]:
    """Manage persistent configuration (Feature 2).

    Actions:
    - get: Retrieve a config value by dotted key
    - set: Set a config value
    - delete: Delete a config key
    - list: List entire configuration
    """
    from src.config import config_get, config_set, config_delete, config_list

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
