#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Tool Handlers for FlexToolsMCP

This package organizes tool handler functions by category.
Handlers are gradually being extracted from server.py during v1.3.0 modularization.

Planned structure:
  - api.py: Read-only operations (get_object_api, search, find_examples, resolve_property)
  - execution.py: Write operations (run_operation, run_module, undo_last_operation)
  - admin.py: Admin tools (start, manage_config, get_session_history, get_module_template)
  - discovery.py: Navigation (get_navigation_path)
  - catalog.py: Listing (list_categories, list_entities_in_category)

During Phase 5 modularization, handlers will be moved here from src/server.py.
The re-export facade in src/server/__init__.py ensures backward compatibility.

BACKWARD COMPATIBILITY NOTE:
All handler functions remain importable from the main server module:
  OLD STYLE (v1.2.0): from server import handle_run_operation
  NEW STYLE (v1.3.0): from server.handlers.execution import handle_run_operation

Both work thanks to the re-export facade.
"""

# Placeholder for future handler module imports
# These will be gradually populated as handlers are extracted from server.py

__all__ = [
    # api.py - Read-only operations
    'handle_get_object_api',
    'handle_search_by_capability',
    'handle_find_examples',
    'handle_resolve_property',

    # execution.py - Write operations
    'handle_run_operation',
    'handle_run_module',
    'handle_undo_last_operation',

    # admin.py - Admin operations
    'handle_start',
    'handle_manage_config',
    'handle_get_session_history',
    'handle_get_module_template',

    # discovery.py - Navigation
    'handle_get_navigation_path',

    # catalog.py - Listing
    'handle_list_categories',
    'handle_list_entities_in_category',
]
