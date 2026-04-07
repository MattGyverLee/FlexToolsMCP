#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool dispatch router for FlexToolsMCP.

Maps tool names to handler functions and their Pydantic input models.
Replaces the 16-way if/elif chain in call_tool() with a clean, dict-based lookup.
"""

from typing import Callable, Type, Dict, Tuple
from pydantic import BaseModel
from mcp.types import TextContent

# Import all Pydantic input models
from .models import (
    FlexToolsStartInput,
    ManageConfigInput,
    GetSessionHistoryInput,
    UndoLastOperationInput,
    GetModuleTemplateInput,
    GetStatisticsInput,
    SearchCapabilityInput,
    GetObjectApiInput,
    GetNavigationPathInput,
    FindExamplesInput,
    ListCategoriesInput,
    ListEntitiesInCategoryInput,
    ResolvePropertyInput,
    StartModuleInput,
    GetOperationLogsInput,
    RunModuleInput,
)

# ============================================================
# Tool name constants (replace stringly-typed code)
# ============================================================
# Admin tools
TOOL_FLEXTOOLS_START = "flextools_start"
TOOL_MANAGE_CONFIG = "flextools_manage_config"
TOOL_GET_SESSION_HISTORY = "flextools_get_session_history"
TOOL_UNDO_LAST_OPERATION = "flextools_undo_last_operation"
TOOL_GET_MODULE_TEMPLATE = "flextools_get_module_template"
TOOL_GET_STATISTICS = "flextools_get_statistics"

# Discovery tools
TOOL_SEARCH_BY_CAPABILITY = "flextools_search_by_capability"
TOOL_GET_OBJECT_API = "flextools_get_object_api"
TOOL_GET_NAVIGATION_PATH = "flextools_get_navigation_path"
TOOL_FIND_EXAMPLES = "flextools_find_examples"

# Catalog tools
TOOL_LIST_CATEGORIES = "flextools_list_categories"
TOOL_LIST_ENTITIES_IN_CATEGORY = "flextools_list_entities_in_category"

# Module management tools
TOOL_START_MODULE = "flextools_start_module"
TOOL_GET_OPERATION_LOGS = "flextools_get_operation_logs"

# Execution tools
TOOL_RUN_MODULE = "flextools_run_module"

# Property resolution tool
TOOL_RESOLVE_PROPERTY = "flextools_resolve_property"

# All tool names for validation
ALL_TOOL_NAMES = frozenset([
    TOOL_FLEXTOOLS_START,
    TOOL_MANAGE_CONFIG,
    TOOL_GET_SESSION_HISTORY,
    TOOL_UNDO_LAST_OPERATION,
    TOOL_GET_MODULE_TEMPLATE,
    TOOL_GET_STATISTICS,
    TOOL_SEARCH_BY_CAPABILITY,
    TOOL_GET_OBJECT_API,
    TOOL_GET_NAVIGATION_PATH,
    TOOL_FIND_EXAMPLES,
    TOOL_LIST_CATEGORIES,
    TOOL_LIST_ENTITIES_IN_CATEGORY,
    TOOL_START_MODULE,
    TOOL_GET_OPERATION_LOGS,
    TOOL_RUN_MODULE,
    TOOL_RESOLVE_PROPERTY,
])

# Import all handler functions
def _import_handlers():
    """Import all handlers with fallback to non-package mode."""
    try:
        # Try package imports first (relative imports)
        from .handlers.admin import (
            handle_start,
            handle_manage_config,
            handle_get_session_history,
            handle_undo_last_operation,
            handle_get_module_template,
            handle_get_statistics,
        )
        from .handlers.api import (
            handle_get_object_api,
            handle_search_by_capability,
            handle_find_examples,
            handle_resolve_property,
        )
        from .handlers.catalog import (
            handle_list_categories,
            handle_list_entities_in_category,
        )
        from .handlers.discovery import (
            handle_get_navigation_path,
        )
        from .handlers.execution import (
            handle_start_module,
            handle_run_module,
            handle_get_operation_logs,
        )
    except ImportError:
        # Fallback to non-package mode (absolute imports)
        from server.handlers.admin import (
            handle_start,
            handle_manage_config,
            handle_get_session_history,
            handle_undo_last_operation,
            handle_get_module_template,
            handle_get_statistics,
        )
        from server.handlers.api import (
            handle_get_object_api,
            handle_search_by_capability,
            handle_find_examples,
            handle_resolve_property,
        )
        from server.handlers.catalog import (
            handle_list_categories,
            handle_list_entities_in_category,
        )
        from server.handlers.discovery import (
            handle_get_navigation_path,
        )
        from server.handlers.execution import (
            handle_start_module,
            handle_run_module,
            handle_get_operation_logs,
        )

    return {
        "handle_start": handle_start,
        "handle_manage_config": handle_manage_config,
        "handle_get_session_history": handle_get_session_history,
        "handle_undo_last_operation": handle_undo_last_operation,
        "handle_get_module_template": handle_get_module_template,
        "handle_get_statistics": handle_get_statistics,
        "handle_get_object_api": handle_get_object_api,
        "handle_search_by_capability": handle_search_by_capability,
        "handle_find_examples": handle_find_examples,
        "handle_resolve_property": handle_resolve_property,
        "handle_list_categories": handle_list_categories,
        "handle_list_entities_in_category": handle_list_entities_in_category,
        "handle_get_navigation_path": handle_get_navigation_path,
        "handle_start_module": handle_start_module,
        "handle_run_module": handle_run_module,
        "handle_get_operation_logs": handle_get_operation_logs,
    }


_handlers = _import_handlers()
handle_start = _handlers["handle_start"]
handle_manage_config = _handlers["handle_manage_config"]
handle_get_session_history = _handlers["handle_get_session_history"]
handle_undo_last_operation = _handlers["handle_undo_last_operation"]
handle_get_module_template = _handlers["handle_get_module_template"]
handle_get_statistics = _handlers["handle_get_statistics"]
handle_get_object_api = _handlers["handle_get_object_api"]
handle_search_by_capability = _handlers["handle_search_by_capability"]
handle_find_examples = _handlers["handle_find_examples"]
handle_resolve_property = _handlers["handle_resolve_property"]
handle_list_categories = _handlers["handle_list_categories"]
handle_list_entities_in_category = _handlers["handle_list_entities_in_category"]
handle_get_navigation_path = _handlers["handle_get_navigation_path"]
handle_start_module = _handlers["handle_start_module"]
handle_run_module = _handlers["handle_run_module"]
handle_get_operation_logs = _handlers["handle_get_operation_logs"]


# Type alias for tool handlers
ToolHandler = Callable[[BaseModel], list[TextContent]]

# ============================================================
# Dispatch Router
# ============================================================

DISPATCH_ROUTES: Dict[str, Tuple[Callable, Type[BaseModel]]] = {
    # Admin tools
    TOOL_FLEXTOOLS_START: (handle_start, FlexToolsStartInput),
    TOOL_MANAGE_CONFIG: (handle_manage_config, ManageConfigInput),
    TOOL_GET_SESSION_HISTORY: (handle_get_session_history, GetSessionHistoryInput),
    TOOL_UNDO_LAST_OPERATION: (handle_undo_last_operation, UndoLastOperationInput),
    TOOL_GET_MODULE_TEMPLATE: (handle_get_module_template, GetModuleTemplateInput),
    TOOL_GET_STATISTICS: (handle_get_statistics, GetStatisticsInput),

    # Discovery tools
    TOOL_SEARCH_BY_CAPABILITY: (handle_search_by_capability, SearchCapabilityInput),
    TOOL_GET_OBJECT_API: (handle_get_object_api, GetObjectApiInput),
    TOOL_GET_NAVIGATION_PATH: (handle_get_navigation_path, GetNavigationPathInput),
    TOOL_FIND_EXAMPLES: (handle_find_examples, FindExamplesInput),

    # Catalog tools
    TOOL_LIST_CATEGORIES: (handle_list_categories, ListCategoriesInput),
    TOOL_LIST_ENTITIES_IN_CATEGORY: (handle_list_entities_in_category, ListEntitiesInCategoryInput),

    # Module management tools
    TOOL_START_MODULE: (handle_start_module, StartModuleInput),
    TOOL_GET_OPERATION_LOGS: (handle_get_operation_logs, GetOperationLogsInput),

    # Execution tools
    TOOL_RUN_MODULE: (handle_run_module, RunModuleInput),

    # Property resolution tool
    TOOL_RESOLVE_PROPERTY: (handle_resolve_property, ResolvePropertyInput),
}

# Cache tool names (avoid O(n) list rebuild on every call)
_CACHED_TOOL_NAMES: list[str] = sorted(DISPATCH_ROUTES.keys())


def get_tool_handler(tool_name: str) -> Tuple[Callable, Type[BaseModel]] | None:
    """Get handler and input model for a tool.

    Args:
        tool_name: Name of the tool (e.g., TOOL_SEARCH_BY_CAPABILITY or 'flextools_search_by_capability')

    Returns:
        Tuple of (handler_func, input_model_class) or None if not found
    """
    return DISPATCH_ROUTES.get(tool_name)


def get_all_tool_names() -> list[str]:
    """Get list of all registered tool names (cached)."""
    return _CACHED_TOOL_NAMES
