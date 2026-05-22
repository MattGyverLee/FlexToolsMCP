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
from datetime import datetime
from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps, safe_import_session_state, safe_import_logging_helpers
from ..response_keys import (
    KEY_MESSAGE, KEY_STATUS, KEY_SESSION, KEY_ERROR, KEY_SOURCE,
    KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED, KEY_HISTORY,
    KEY_TEMPLATE, KEY_WARNINGS, KEY_ENTITIES, KEY_CATEGORIES, KEY_CATEGORY
)

# Import kernel dependencies with fallback support
json_response, session_state, get_log_dir, get_api_index = safe_import_kernel_deps()
rotate_logging_to_session, _ = safe_import_logging_helpers()
SessionState = safe_import_session_state()

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

# Runtime invariants - true for both lightweight ops (bare snippets) and full
# FlexTools modules. Emitted in start()'s response so the assistant sees these
# BEFORE writing any code. Saves a Dennis-style debugging arc where the AI
# reinvents reporters, write guards, or '***' placeholder handling because it
# never learned the runtime contract.
RUNTIME_PRIMER = {
    "output": {
        "description": "Use report.* for all user-facing output. Both lightweight ops and modules use the same API.",
        "methods": [
            "report.Info(msg, ref=None)",
            "report.Warning(msg, ref=None)",
            "report.Error(msg, ref=None)",
            "report.Blank()",
        ],
        "example": 'report.Info(f"Updated {entry_hw}", project.BuildGotoURL(sense))',
        "note": "Plain print() also works but bypasses message counts and ref links. Prefer report.*",
        "do_not_rebind": (
            "Do NOT redefine `report` or `project` (e.g. `report = SafeReporter(report)`). "
            "The runner already handles unicode-safe stdout; wrappers are unnecessary and "
            "obscure the contract. The injected `report` and `project` are the canonical "
            "objects - use them directly."
        ),
    },
    "clickable_refs": {
        "description": "Pass a goto URL as the second argument to make a message clickable in FlexTools UI.",
        "pattern": "project.BuildGotoURL(obj) -> str",
        "example": 'report.Info("Found match", project.BuildGotoURL(sense))',
        "note": "obj must be a concrete LCM object (entry, sense, example, ...) - not an HVO or string.",
    },
    "write_protection": {
        "description": "Every database mutation MUST be guarded by `if modifyAllowed:`. Unguarded mutations are refused at validation time before execution.",
        "lightweight_op_form": (
            "modifyAllowed is exposed as a top-level namespace variable. "
            "Use:  if modifyAllowed:  sense.Gloss.set_String(ws, 'new gloss')"
        ),
        "module_form": (
            "modifyAllowed is the third positional parameter of Main. "
            "Use:  def Main(project, report, modifyAllowed):  if modifyAllowed:  sense.Gloss.set_String(ws, 'new gloss')"
        ),
        "note": "modifyAllowed reflects the write_enabled flag set in start(). False by default (dry-run safe).",
    },
    "multistring_placeholder": {
        "description": "FLEx stores '***' as the placeholder for unset multilingual string fields (Gloss, Definition, Form, ...).",
        "wrapper_behavior": (
            "FlexLibs2 wrapper getters normalize '***' to '' so `if not gloss:` works. "
            "Use:  gloss = LexSenseOperations(project).GetGloss(sense)  # '' if empty"
        ),
        "raw_csharp_behavior": (
            "Direct C# property access still returns '***'. Check explicitly: "
            "raw = sense.Gloss.BestAnalysisAlternative.Text; "
            "if raw == '***': raw = ''"
        ),
        "note": "Prefer wrapper getters. Mixing the two styles in one script is the most common source of empty-string bugs.",
    },
    "namespace_helpers": {
        "description": "These helpers are pre-injected into the execution namespace. No import required.",
        "available": [
            "is_empty_multistring(text) -> bool  # True for None, '', or '***'",
            "FLEX_EMPTY_PLACEHOLDER  # the literal '***' constant",
            "find_writing_system(project, query) -> ws_handle | None  # substring search by name/tag",
            "list_writing_systems(project) -> [{'name', 'tag'}, ...]",
        ],
        "note": "Always available; do NOT redefine these at the top of your script.",
        "scope_warning": "MCP-runner only. If this code is saved as a FlexTools module file, the helpers will NOT exist when FlexTools loads it - inline copies or do not use them.",
    },
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


def _resolve_inherited_flag(
    field: str,
    args: dict,
    user_provided: set,
    same_project: bool,
    default: bool = False,
):
    """Resolve a boolean session flag with explicit/inherit/default precedence.

    Used for write_enabled and undoable (and any future flag that should
    persist across same-project re-inits). Returns
    (value, inherited, downgraded) where:
        inherited  = prior session value was kept because no explicit value given
        downgraded = explicit value flipped a previously-True flag to False
                     (worth surfacing as a warning so the LLM can confirm intent)
    """
    explicit = field in user_provided
    prior = bool(getattr(session_state, field, default))
    if explicit or not same_project:
        value = args.get(field, default)
    else:
        value = prior
    inherited = same_project and not explicit and prior
    downgraded = explicit and prior and not value
    return value, inherited, downgraded


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

    user_provided = args.get("_user_provided_keys", set())
    same_project = (
        bool(session_state.initialized)
        and getattr(session_state, "project_name", "") == project_name
        and project_name != ""
    )

    # #9 fix: write_enabled persists across re-init on the same project.
    write_enabled, write_enabled_inherited, write_enabled_downgraded = (
        _resolve_inherited_flag("write_enabled", args, user_provided, same_project)
    )

    # #14 Phase 1: undoable opt-in. Coerced off when write is off because
    # flexlibs2 silently ignores undoable in that case -- coercing it here
    # makes the effective value visible so the LLM can react.
    undoable, _, _ = _resolve_inherited_flag(
        "undoable", args, user_provided, same_project
    )
    undoable = undoable and write_enabled

    # Generate session ID (format: YYYYMMDD-HHMMSS)
    session_id = datetime.now().strftime("%Y%m%d-%H%M%S")

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

    # Set session-wide settings (including session_id)
    session_state.session_id = session_id
    session_state.configure(
        api_mode=api_mode,
        output_type="auto",
        project_name=project_name,
        write_enabled=write_enabled,
        undoable=undoable,
        api_versions=api_versions
    )

    # Diagnostic for #10: record identity of the configured session_state so
    # the next "Session not initialized" log line can be compared against this.
    try:
        from ..kernel import get_operations_logger
    except ImportError:
        from server.kernel import get_operations_logger
    _op_logger = get_operations_logger()
    if _op_logger:
        _op_logger.info(
            f"[SESSION-CONFIGURED] session_state_id={id(session_state)} "
            f"session_id={session_id} project={project_name!r} "
            f"api_mode={api_mode} write_enabled={write_enabled} "
            f"undoable={undoable} initialized={session_state.initialized}"
        )

    # Rotate logging to session-specific log file
    rotate_logging_to_session(session_id)

    # Note: Project metadata query removed from start handler
    # The FieldWorks registry access causes issues in start context but works fine
    # during execution. Users can discover project metadata by running:
    #   for ws_info in list_writing_systems(project):
    #       report.Info(f"{ws_info['name']} ({ws_info['tag']})")

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
            "5. Use run_module() to execute (accepts bare snippets and full Main-shaped modules)"
        ]
    }

    result[KEY_MODE_INFO] = MODE_GUIDANCE.get(api_mode, MODE_GUIDANCE["flexlibs2"])
    result["runtime_primer"] = RUNTIME_PRIMER

    # Warnings
    warnings = []
    if not project_name:
        warnings.append("No project_name set - will need to specify when running operations")
    if write_enabled:
        warnings.append("WRITE MODE ENABLED - operations will modify the database")
    if write_enabled_inherited:
        warnings.append(
            "write_enabled=True inherited from prior session on this project "
            "(no value was explicitly provided in this call)."
        )
    if write_enabled_downgraded:
        warnings.append(
            "write_enabled was downgraded True -> False on re-init. "
            "Was this intentional?"
        )
    if undoable:
        warnings.append(
            "undoable=True (EXPERIMENTAL): writes go through LCM's persistent "
            "undo stack. flextools_undo_last_operation can reverse them across "
            "MCP sessions (matches FLEx UI Ctrl+Z)."
        )
    if "undoable" in user_provided and args.get("undoable") and not write_enabled:
        warnings.append(
            "undoable=True was requested but coerced to False because "
            "write_enabled=False (flexlibs2 ignores undoable in read-only mode)."
        )

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
    """Undo the last database write operation (#14 Phase 2).

    Executes project.Undo() in a subprocess against the configured project,
    which reverses the most recent LCM UndoableOperation. Requires the
    session to have been started with undoable=True; otherwise the LCM
    project was opened without an undo stack and Undo() will raise.

    Returns a structured result including how many Undo() calls succeeded
    and (best-effort) the undo stack depth before and after.
    """
    # Local session-side bookkeeping: peek the last checkpoint if any. This
    # is informational -- the actual undo always runs against the LCM cache.
    last_checkpoint = (
        session_state.undo_checkpoints[-1] if session_state.undo_checkpoints else None
    )

    project_name = session_state.project_name or ""
    if not project_name:
        return json_response({
            KEY_SUCCESS: False,
            KEY_MESSAGE: "No project_name set in session. Call flextools_start(project_name=...) first.",
        })

    if not session_state.write_enabled:
        return json_response({
            KEY_SUCCESS: False,
            KEY_MESSAGE: (
                "Write mode is not enabled in this session. Re-init with "
                "flextools_start(write_enabled=True, undoable=True) to enable undo."
            ),
        })

    if not session_state.is_undoable():
        return json_response({
            KEY_SUCCESS: False,
            KEY_MESSAGE: (
                "Session was started with undoable=False, so the project was "
                "opened without LCM's persistent undo stack. project.Undo() "
                "would raise. Re-init with flextools_start(undoable=True) "
                "BEFORE making changes you want to be reversible."
            ),
            KEY_NOTE: (
                "Per #14 design: undoable is opt-in while experimental. "
                "Existing writes from this session that were made under "
                "undoable=False cannot be reversed by this tool."
            ),
        })

    # Pydantic already validated count: int = Field(ge=1, default=1) on the
    # input model, so no defensive re-coercion needed here.
    undo_count = args.get("count", 1)

    try:
        from ..undo_subprocess import execute_undo
    except ImportError:
        from server.undo_subprocess import execute_undo

    sub_result = await execute_undo(
        project_name=project_name,
        undo_count=undo_count,
        timeout_seconds=60,
    )

    success = bool(sub_result.get("success"))
    undid = int(sub_result.get("undid", 0))
    result = {
        KEY_SUCCESS: success and undid > 0,
        KEY_MESSAGE: (
            f"Undid {undid} operation(s) via project.Undo()."
            if success and undid > 0
            else "Undo did not reverse anything -- see error fields."
        ),
        "undid": undid,
        "stack_depth_before": sub_result.get("stack_depth_before"),
        "stack_depth_after": sub_result.get("stack_depth_after"),
        "requested_count": undo_count,
    }
    if not success or undid == 0:
        result[KEY_ERROR] = sub_result.get("error", "unknown")
        if sub_result.get("error_message"):
            result["error_message"] = sub_result["error_message"]
        if sub_result.get("subprocess_stderr"):
            result["subprocess_stderr"] = sub_result["subprocess_stderr"]
        if sub_result.get("traceback"):
            result["traceback"] = sub_result["traceback"]

    # Pop matching checkpoints from our local log -- one per successful undo.
    # If we undid more than we tracked, that's fine (we may have reached into
    # a prior session's stack); the checkpoint log is informational only.
    popped = []
    for _ in range(undid):
        if session_state.undo_checkpoints:
            popped.append(session_state.undo_checkpoints.pop())
    if popped:
        result["local_checkpoints_popped"] = popped

    if last_checkpoint is not None:
        result["last_session_checkpoint"] = last_checkpoint
    result["remaining_session_checkpoints"] = len(session_state.undo_checkpoints)

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


