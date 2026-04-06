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
    ResolvePropertyInput,
    StartModuleInput,
    GetOperationLogsInput,
    RunModuleInput,
)

# Import all handler functions
try:
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
    # Fallback imports for non-package mode
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


# Type alias for tool handlers
ToolHandler = Callable[[BaseModel], list[TextContent]]

# ============================================================
# Dispatch Router
# ============================================================

DISPATCH_ROUTES: Dict[str, Tuple[Callable, Type[BaseModel]]] = {
    # Admin tools
    "flextools_start": (handle_start, FlexToolsStartInput),
    "flextools_manage_config": (handle_manage_config, ManageConfigInput),
    "flextools_get_session_history": (handle_get_session_history, GetSessionHistoryInput),
    "flextools_undo_last_operation": (handle_undo_last_operation, UndoLastOperationInput),
    "flextools_get_module_template": (handle_get_module_template, GetModuleTemplateInput),

    # Discovery tools
    "flextools_search_by_capability": (handle_search_by_capability, SearchCapabilityInput),
    "flextools_get_object_api": (handle_get_object_api, GetObjectApiInput),
    "flextools_get_navigation_path": (handle_get_navigation_path, GetNavigationPathInput),
    "flextools_find_examples": (handle_find_examples, FindExamplesInput),

    # Catalog tools
    "flextools_list_categories": (handle_list_categories, ListCategoriesInput),
    "flextools_list_entities_in_category": (handle_list_entities_in_category, ListEntitiesInCategoryInput),

    # Module management tools
    "flextools_start_module": (handle_start_module, StartModuleInput),
    "flextools_get_operation_logs": (handle_get_operation_logs, GetOperationLogsInput),

    # Execution tools
    "flextools_run_module": (handle_run_module, RunModuleInput),

    # Property resolution tool
    "flextools_resolve_property": (handle_resolve_property, ResolvePropertyInput),
}


def get_tool_handler(tool_name: str) -> Tuple[Callable, Type[BaseModel]] | None:
    """Get handler and input model for a tool.

    Args:
        tool_name: Name of the tool (e.g., 'flextools_search_by_capability')

    Returns:
        Tuple of (handler_func, input_model_class) or None if not found
    """
    return DISPATCH_ROUTES.get(tool_name)


def get_all_tool_names() -> list[str]:
    """Get list of all registered tool names."""
    return list(DISPATCH_ROUTES.keys())
