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
    SearchCapabilityInput,
    GetObjectApiInput,
    GetNavigationPathInput,
    FindExamplesInput,
    ListCategoriesInput,
    ListEntitiesInCategoryInput,
    ListProjectsInput,
    ResolvePropertyInput,
    StartModuleInput,
    GetOperationLogsInput,
    RunModuleInput,
    GetWrapperDependenciesInput,
    FindWrappersForLcmInput,
    ResolveTypeInput,
    ListSkeletonsInput,
    PrepareReportInput,
    FlexToolsHealthInput,
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

# Discovery tools
TOOL_SEARCH_BY_CAPABILITY = "flextools_search_by_capability"
TOOL_GET_OBJECT_API = "flextools_get_object_api"
TOOL_GET_NAVIGATION_PATH = "flextools_get_navigation_path"
TOOL_FIND_EXAMPLES = "flextools_find_examples"

# Catalog tools
TOOL_LIST_CATEGORIES = "flextools_list_categories"
TOOL_LIST_ENTITIES_IN_CATEGORY = "flextools_list_entities_in_category"
TOOL_LIST_PROJECTS = "flextools_list_projects"

# Module management tools
TOOL_START_MODULE = "flextools_start_module"
TOOL_GET_OPERATION_LOGS = "flextools_get_operation_logs"

# Execution tools
TOOL_RUN_MODULE = "flextools_run_module"

# Diagnostic-report tools (CP3)
TOOL_PREPARE_REPORT = "flextools_prepare_report"

# Property resolution tool
TOOL_RESOLVE_PROPERTY = "flextools_resolve_property"

# Equivalence / cross-flavor mapping tools
TOOL_GET_WRAPPER_DEPENDENCIES = "flextools_get_wrapper_dependencies"
TOOL_FIND_WRAPPERS_FOR_LCM = "flextools_find_wrappers_for_lcm"
TOOL_RESOLVE_TYPE = "flextools_resolve_type"

# Skeleton storage closet (issue #24)
TOOL_LIST_SKELETONS = "flextools_list_skeletons"

# Diagnostics tool (issue #56)
TOOL_FLEXTOOLS_HEALTH = "flextools_health"

# All tool names for validation
ALL_TOOL_NAMES = frozenset([
    TOOL_FLEXTOOLS_START,
    TOOL_MANAGE_CONFIG,
    TOOL_GET_SESSION_HISTORY,
    TOOL_UNDO_LAST_OPERATION,
    TOOL_GET_MODULE_TEMPLATE,
    TOOL_SEARCH_BY_CAPABILITY,
    TOOL_GET_OBJECT_API,
    TOOL_GET_NAVIGATION_PATH,
    TOOL_FIND_EXAMPLES,
    TOOL_LIST_CATEGORIES,
    TOOL_LIST_ENTITIES_IN_CATEGORY,
    TOOL_LIST_PROJECTS,
    TOOL_START_MODULE,
    TOOL_GET_OPERATION_LOGS,
    TOOL_RUN_MODULE,
    TOOL_RESOLVE_PROPERTY,
    TOOL_GET_WRAPPER_DEPENDENCIES,
    TOOL_FIND_WRAPPERS_FOR_LCM,
    TOOL_RESOLVE_TYPE,
    TOOL_LIST_SKELETONS,
    TOOL_PREPARE_REPORT,
    TOOL_FLEXTOOLS_HEALTH,
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
        )
        from .handlers.api import (
            handle_get_object_api,
            handle_search_by_capability,
            handle_find_examples,
            handle_resolve_property,
            handle_resolve_type,
        )
        from .handlers.catalog import (
            handle_list_categories,
            handle_list_entities_in_category,
            handle_list_projects,
            handle_list_skeletons,
        )
        from .handlers.discovery import (
            handle_get_navigation_path,
        )
        from .handlers.execution import (
            handle_start_module,
            handle_run_module,
            handle_get_operation_logs,
        )
        from .handlers.equivalence import (
            handle_get_wrapper_dependencies,
            handle_find_wrappers_for_lcm,
        )
        from .handlers.diagnostic_report import (
            handle_prepare_report,
        )
        from .handlers.diagnostic_health import (
            handle_flextools_health,
        )
    except ImportError:
        # Fallback to non-package mode (absolute imports)
        from server.handlers.admin import (
            handle_start,
            handle_manage_config,
            handle_get_session_history,
            handle_undo_last_operation,
            handle_get_module_template,
        )
        from server.handlers.api import (
            handle_get_object_api,
            handle_search_by_capability,
            handle_find_examples,
            handle_resolve_property,
            handle_resolve_type,
        )
        from server.handlers.catalog import (
            handle_list_categories,
            handle_list_entities_in_category,
            handle_list_projects,
            handle_list_skeletons,
        )
        from server.handlers.discovery import (
            handle_get_navigation_path,
        )
        from server.handlers.execution import (
            handle_start_module,
            handle_run_module,
            handle_get_operation_logs,
        )
        from server.handlers.equivalence import (
            handle_get_wrapper_dependencies,
            handle_find_wrappers_for_lcm,
        )
        from server.handlers.diagnostic_report import (
            handle_prepare_report,
        )
        from server.handlers.diagnostic_health import (
            handle_flextools_health,
        )

    return {
        "handle_start": handle_start,
        "handle_manage_config": handle_manage_config,
        "handle_get_session_history": handle_get_session_history,
        "handle_undo_last_operation": handle_undo_last_operation,
        "handle_get_module_template": handle_get_module_template,
        "handle_get_object_api": handle_get_object_api,
        "handle_search_by_capability": handle_search_by_capability,
        "handle_find_examples": handle_find_examples,
        "handle_resolve_property": handle_resolve_property,
        "handle_list_categories": handle_list_categories,
        "handle_list_entities_in_category": handle_list_entities_in_category,
        "handle_list_projects": handle_list_projects,
        "handle_list_skeletons": handle_list_skeletons,
        "handle_get_navigation_path": handle_get_navigation_path,
        "handle_start_module": handle_start_module,
        "handle_run_module": handle_run_module,
        "handle_get_operation_logs": handle_get_operation_logs,
        "handle_get_wrapper_dependencies": handle_get_wrapper_dependencies,
        "handle_find_wrappers_for_lcm": handle_find_wrappers_for_lcm,
        "handle_resolve_type": handle_resolve_type,
        "handle_prepare_report": handle_prepare_report,
        "handle_flextools_health": handle_flextools_health,
    }


_handlers = _import_handlers()
handle_start = _handlers["handle_start"]
handle_manage_config = _handlers["handle_manage_config"]
handle_get_session_history = _handlers["handle_get_session_history"]
handle_undo_last_operation = _handlers["handle_undo_last_operation"]
handle_get_module_template = _handlers["handle_get_module_template"]
handle_get_object_api = _handlers["handle_get_object_api"]
handle_search_by_capability = _handlers["handle_search_by_capability"]
handle_find_examples = _handlers["handle_find_examples"]
handle_resolve_property = _handlers["handle_resolve_property"]
handle_list_categories = _handlers["handle_list_categories"]
handle_list_entities_in_category = _handlers["handle_list_entities_in_category"]
handle_list_projects = _handlers["handle_list_projects"]
handle_list_skeletons = _handlers["handle_list_skeletons"]
handle_get_navigation_path = _handlers["handle_get_navigation_path"]
handle_start_module = _handlers["handle_start_module"]
handle_run_module = _handlers["handle_run_module"]
handle_get_operation_logs = _handlers["handle_get_operation_logs"]
handle_get_wrapper_dependencies = _handlers["handle_get_wrapper_dependencies"]
handle_find_wrappers_for_lcm = _handlers["handle_find_wrappers_for_lcm"]
handle_resolve_type = _handlers["handle_resolve_type"]
handle_prepare_report = _handlers["handle_prepare_report"]
handle_flextools_health = _handlers["handle_flextools_health"]


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

    # Discovery tools
    TOOL_SEARCH_BY_CAPABILITY: (handle_search_by_capability, SearchCapabilityInput),
    TOOL_GET_OBJECT_API: (handle_get_object_api, GetObjectApiInput),
    TOOL_GET_NAVIGATION_PATH: (handle_get_navigation_path, GetNavigationPathInput),
    TOOL_FIND_EXAMPLES: (handle_find_examples, FindExamplesInput),

    # Catalog tools
    TOOL_LIST_CATEGORIES: (handle_list_categories, ListCategoriesInput),
    TOOL_LIST_ENTITIES_IN_CATEGORY: (handle_list_entities_in_category, ListEntitiesInCategoryInput),
    TOOL_LIST_PROJECTS: (handle_list_projects, ListProjectsInput),

    # Module management tools
    TOOL_START_MODULE: (handle_start_module, StartModuleInput),
    TOOL_GET_OPERATION_LOGS: (handle_get_operation_logs, GetOperationLogsInput),

    # Execution tools
    TOOL_RUN_MODULE: (handle_run_module, RunModuleInput),

    # Property resolution tool
    TOOL_RESOLVE_PROPERTY: (handle_resolve_property, ResolvePropertyInput),

    # Equivalence / cross-flavor mapping tools
    TOOL_GET_WRAPPER_DEPENDENCIES: (handle_get_wrapper_dependencies, GetWrapperDependenciesInput),
    TOOL_FIND_WRAPPERS_FOR_LCM: (handle_find_wrappers_for_lcm, FindWrappersForLcmInput),
    TOOL_RESOLVE_TYPE: (handle_resolve_type, ResolveTypeInput),

    # Skeleton storage closet (issue #24)
    TOOL_LIST_SKELETONS: (handle_list_skeletons, ListSkeletonsInput),

    # Diagnostic-report tools (CP3)
    TOOL_PREPARE_REPORT: (handle_prepare_report, PrepareReportInput),

    # Diagnostics tool (issue #56)
    TOOL_FLEXTOOLS_HEALTH: (handle_flextools_health, FlexToolsHealthInput),
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
