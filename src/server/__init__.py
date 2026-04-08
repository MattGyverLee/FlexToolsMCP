#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlexToolsMCP Server Package

This package provides a modularized server structure while maintaining
backward compatibility with existing code that imports from the server module.

All handler functions, classes, and utilities are re-exported here to ensure
that both old and new import styles work seamlessly:

OLD STYLE (still works via re-exports):
  from server import handle_run_operation, SessionState, APIIndex

NEW STYLE (direct from modules):
  from server.handlers.execution import handle_run_operation
  from server.session import SessionState
  from server.kernel import api_index
"""

# Re-export Pydantic input models
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

# Re-export session management (Feature 3)
from .session import SessionState, OperationRecord

# Re-export validation functions (Feature 5)
from .validators import (
    detect_cud_operations,
    detect_module_structure,
    check_output_mechanism,
    detect_polymorphic_error,
    detect_missing_operations_imports,
    detect_wrong_library_imports,
    detect_undefined_variables,
    validate_project_context,
)

# Re-export kernel state and utilities (Feature 4)
from .kernel import (
    check_mcp_available,
    _ensure_flexlibs2,
    get_log_dir,
    setup_logging,
    rotate_logging_to_session,
    operations_logger,
    session_state,
    get_index_dir,
    initialize_kernel,
    reset_session,
    get_session_state,
    PatternTracker,
)

# Lazy import of server.py handlers (Feature 5 - modularization)
# These will be available but only loaded when actually accessed
# This allows backward compatibility while we gradually modularize the codebase

# Cache the loaded server.py module to avoid reloading on every __getattr__ call (efficiency fix)
_server_module_cache = None

def __getattr__(name: str):
    """Lazy load handler functions and classes from the main server.py module.

    This enables backward compatibility by allowing imports like:
      from server import handle_run_operation, APIIndex, main

    To still work even after modularization.

    The server.py module is loaded once and cached to avoid reload overhead.
    """
    global _server_module_cache
    import sys
    from pathlib import Path
    import importlib.util

    # List of all handler functions and classes that should be lazy-loaded from server.py
    # NOTE: Handler functions have been refactored into modularized handlers/
    # Only keep items that actually exist in server.py for backward compatibility
    LAZY_IMPORTS = {
        # Classes
        'APIIndex',
        'SemanticSearch',
        'Server',

        # Helper functions
        'build_response_with_context',
        'rank_object_matches',
        'main',
    }

    if name in LAZY_IMPORTS:
        # Load server.py as a module once and cache it
        if _server_module_cache is None:
            src_path = str(Path(__file__).parent.parent)
            server_path = str(Path(__file__).parent.parent / "server.py")

            # Ensure src/ is in sys.path for imports to work
            if src_path not in sys.path:
                sys.path.insert(0, src_path)

            spec = importlib.util.spec_from_file_location("_server_module", server_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load server module from {server_path}")

            _server_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_server_module)
            _server_module_cache = _server_module

        # Get the attribute from the cached module
        if hasattr(_server_module_cache, name):
            return getattr(_server_module_cache, name)

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# For direct re-exports of commonly used items
# Note: Lazy-loaded items (APIIndex, etc.) are not in __all__ because
# they're dynamically loaded via __getattr__ and don't exist at import time.
# They can still be imported and used at runtime, but Pylance won't see them here.
__all__ = [
    # Session management
    'SessionState',
    'OperationRecord',

    # Validators
    'detect_cud_operations',
    'detect_module_structure',
    'check_output_mechanism',
    'detect_polymorphic_error',
    'detect_missing_operations_imports',
    'detect_wrong_library_imports',
    'detect_undefined_variables',
    'validate_project_context',

    # Kernel utilities
    'check_mcp_available',
    'get_log_dir',
    'setup_logging',
    'rotate_logging_to_session',
    'operations_logger',
    'session_state',
    'get_index_dir',
    'initialize_kernel',
    'reset_session',
    'get_session_state',
    'PatternTracker',
]
