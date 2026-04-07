#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pydantic input/output models for FlexToolsMCP.

These models define type-safe, validated request/response schemas for all MCP tools.
They replace raw JSON Schema dicts and provide automatic validation, type coercion,
and IDE autocomplete support.
"""

from typing import Optional, Literal, Any
from pydantic import BaseModel, Field
from .constants import API_MODES, API_MODES_DEFAULT

# Ensure API mode constants match Literal types
assert API_MODES == ("flexlibs2", "flexlibs_stable", "liblcm"), \
    "API_MODES constant must match Literal types in models"
assert API_MODES_DEFAULT == "flexlibs2", \
    "API_MODES_DEFAULT must match FlexToolsStartInput.api_mode default"


# ============================================================
# Admin Tools
# ============================================================

class FlexToolsStartInput(BaseModel):
    """Initialize a FlexTools MCP session."""
    api_mode: Literal["flexlibs2", "flexlibs_stable", "liblcm"] = Field(
        default=API_MODES_DEFAULT,
        description="API mode - REQUIRED: 'flexlibs2' (recommended, ~1400 methods), "
                    "'flexlibs_stable' (legacy ~71 methods), 'liblcm' (raw C# API)."
    )
    task: Optional[str] = Field(
        default=None,
        description="Optional: Task/goal description in natural language. "
                    "Can be provided now or discovered organically later."
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Optional: FLEx project name for run_operation()/run_module(). "
                    "Can be set now or provided when executing."
    )
    output_type: Literal["auto", "operation", "module"] = Field(
        default="auto",
        description="Optional: Output type - 'auto' (default), 'operation' (quick one-off), "
                    "'module' (reusable script)"
    )
    write_enabled: bool = Field(
        default=False,
        description="Enable write access. Default False (dry-run/read-only). "
                    "Set True only after testing!"
    )


class ManageConfigInput(BaseModel):
    """Get, set, delete, or list persistent configuration."""
    action: Literal["get", "set", "delete", "list"] = Field(
        description="Configuration action to perform"
    )
    key: Optional[str] = Field(
        default=None,
        description="Dotted key (e.g., 'paths.flexlibs2') for get/set/delete actions"
    )
    value: Optional[Any] = Field(
        default=None,
        description="Value to set (required for 'set' action)"
    )


class GetSessionHistoryInput(BaseModel):
    """View session operation history and undo/redo availability."""
    include_operations: bool = Field(
        default=False,
        description="Include full list of operations in response"
    )


class UndoLastOperationInput(BaseModel):
    """Undo the most recent database write operation."""
    pass


class GetModuleTemplateInput(BaseModel):
    """Get the official FlexTools module template."""
    module_name: Optional[str] = Field(
        default=None,
        description="Name for the new module (e.g., 'Export Custom Data')"
    )
    synopsis: Optional[str] = Field(
        default=None,
        description="Short description of what the module does"
    )
    modifies_db: bool = Field(
        default=False,
        description="Whether the module modifies the database"
    )


# ============================================================
# Discovery Tools
# ============================================================

class SearchCapabilityInput(BaseModel):
    """Search for methods/functions by capability."""
    query: str = Field(
        description="Natural language description of what you want to do"
    )
    max_results: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results to return"
    )
    api_mode: Literal["flexlibs2", "flexlibs_stable", "liblcm", "all"] = Field(
        default="flexlibs2",
        description="API mode: 'flexlibs2' (recommended), 'flexlibs_stable', 'liblcm', 'all'"
    )


class GetObjectApiInput(BaseModel):
    """Get detailed API documentation for an object."""
    object_type: str = Field(
        description="The object type to look up (e.g., 'ILexEntry', 'LexEntryOperations')"
    )
    include_flexlibs2: bool = Field(
        default=True,
        description="Include FlexLibs 2.0 wrapper methods"
    )
    include_liblcm: bool = Field(
        default=True,
        description="Include raw LibLCM interface info"
    )
    summary_only: bool = Field(
        default=False,
        description="Return only method/property names without full details. Use for large objects."
    )
    method_filter: Optional[str] = Field(
        default=None,
        description="Filter to methods containing this substring (case-insensitive)"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of methods to return"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of methods to skip for pagination"
    )


class GetNavigationPathInput(BaseModel):
    """Find navigation paths between object types."""
    from_object: str = Field(
        description="Starting object type (e.g., 'ILexEntry')"
    )
    to_object: str = Field(
        description="Target object type (e.g., 'ILexExampleSentence')"
    )


class FindExamplesInput(BaseModel):
    """Find code examples for a method or operation type."""
    method_name: Optional[str] = Field(
        default=None,
        description="Specific method name to find examples for"
    )
    operation_type: Optional[Literal["create", "read", "update", "delete", "iterate", "search"]] = Field(
        default=None,
        description="Type of operation to find examples for"
    )
    object_type: Optional[str] = Field(
        default=None,
        description="Object type to filter examples (e.g., 'LexEntry', 'Sense')"
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum number of examples to return"
    )


class ListCategoriesInput(BaseModel):
    """List all available API categories."""
    pass


class ListEntitiesInCategoryInput(BaseModel):
    """List all entities in a specific category."""
    category: str = Field(
        description="Category name (e.g., 'lexicon', 'grammar', 'texts')"
    )


class ResolvePropertyInput(BaseModel):
    """Resolve property names and check casting requirements."""
    property_name: str = Field(
        description="Property name to resolve (e.g., 'Senses', 'PartOfSpeechRA')"
    )
    context_entity: Optional[str] = Field(
        default=None,
        description="Optional entity context for disambiguation (e.g., 'ILexEntry')"
    )
    include_casting_info: bool = Field(
        default=True,
        description="Include pythonnet casting requirements"
    )


# ============================================================
# Module Management Tools
# ============================================================

class StartModuleInput(BaseModel):
    """Interactive wizard to start creating a new FlexTools module."""
    module_name: Optional[str] = Field(
        default=None,
        description="Name for the new module"
    )
    synopsis: Optional[str] = Field(
        default=None,
        description="Short description of what the module does"
    )
    api_target: Optional[Literal["flexlibs2", "flexlibs_stable", "liblcm"]] = Field(
        default=None,
        description="Target API: 'flexlibs2' (recommended), 'flexlibs_stable', 'liblcm'"
    )
    modifies_db: Optional[bool] = Field(
        default=None,
        description="Whether the module modifies the database"
    )
    domain: Optional[Literal["lexicon", "grammar", "texts", "media", "general"]] = Field(
        default=None,
        description="Primary domain the module works with"
    )
    include_dry_run: Optional[bool] = Field(
        default=None,
        description="Include DRY_RUN safety mode for write operations"
    )


class GetOperationLogsInput(BaseModel):
    """View operation logs and pattern recommendations."""
    log_lines: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Number of recent log lines to return"
    )
    include_patterns: bool = Field(
        default=True,
        description="Include pattern analysis and recommendations"
    )
    errors_only: bool = Field(
        default=False,
        description="Only show error entries in logs"
    )


# ============================================================
# Execution Tools
# ============================================================

class RunModuleInput(BaseModel):
    """Execute code (snippet or full module) against a FieldWorks project.

    Accepts:
    - Minimal snippets: entries = project.LexEntry.GetAll()
    - Full modules: def Main(project, report, modifyAllowed): ...
    - Anything in between

    If code defines Main(), it will be called. Otherwise, code runs as-is.
    """
    code: str = Field(
        description="Python code to execute. Can be a snippet or full module with Main() function. "
                    "Has access to: project (FLExProject), report (SimpleReporter), write_enabled (bool). "
                    "All flexlibs2 Operations classes are pre-imported."
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Name of the FieldWorks project. Uses session value if set by start()."
    )
    write_enabled: Optional[bool] = Field(
        default=None,
        description="Enable write access. Uses session value if set by start(). Default: False (dry-run)."
    )
    timeout_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Maximum execution time in seconds"
    )
    show_code: bool = Field(
        default=True,
        description="Include executed code in response for learning"
    )
    confirmed: bool = Field(
        default=False,
        description="Required for CUD operations. Confirm understanding of risks."
    )


class GetStatisticsInput(BaseModel):
    """Get server statistics including loaded APIs and entity counts.

    Provides metrics about the FlexToolsMCP server state without requiring
    project access, making it useful as a diagnostic tool after initialization.
    """
    pass  # No parameters required for statistics retrieval
