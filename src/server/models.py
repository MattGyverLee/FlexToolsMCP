#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pydantic input/output models for FlexToolsMCP.

These models define type-safe, validated request/response schemas for all MCP tools.
They replace raw JSON Schema dicts and provide automatic validation, type coercion,
and IDE autocomplete support.
"""

from typing import Optional, Literal, Any
from pydantic import BaseModel, Field, field_validator
from .constants import API_MODES, API_MODES_DEFAULT, normalize_api_mode

# Ensure API mode constants match Literal types
assert API_MODES == ("flexicon", "flexlibs_stable", "liblcm"), \
    "API_MODES constant must match Literal types in models"
assert API_MODES_DEFAULT == "flexicon", \
    "API_MODES_DEFAULT must match FlexToolsStartInput.api_mode default"


def _normalize_mode(value):
    """Field-validator helper: map deprecated api_mode aliases (e.g. 'flexlibs2')
    to their canonical value BEFORE Literal validation runs, so old callers keep
    working without widening the Literal types."""
    return normalize_api_mode(value)


def _normalize_mode_list(value):
    """Normalize each element of a library-list field (e.g. FindWrappersForLcm.include)."""
    if isinstance(value, list):
        return [normalize_api_mode(v) for v in value]
    return value


# ============================================================
# Admin Tools
# ============================================================

class FlexToolsStartInput(BaseModel):
    """Initialize a FlexTools MCP session."""
    api_mode: Literal["flexicon", "flexlibs_stable", "liblcm"] = Field(
        default=API_MODES_DEFAULT,
        description="API mode - REQUIRED: 'flexicon' (recommended, ~1400 methods), "
                    "'flexlibs_stable' (legacy ~71 methods), 'liblcm' (raw C# API). "
                    "The deprecated value 'flexlibs2' is accepted as an alias for 'flexicon'."
    )
    _normalize_api_mode = field_validator("api_mode", mode="before")(_normalize_mode)
    task: Optional[str] = Field(
        default=None,
        description="Optional: Task/goal description in natural language. "
                    "Can be provided now or discovered organically later."
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Optional: FLEx project name for run_module(). "
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
    undoable: bool = Field(
        default=False,
        description="EXPERIMENTAL (opt-in): open project with undoable=True so "
                    "writes go through LCM's persistent undo stack (matches "
                    "FLEx UI Ctrl+Z behavior). Required for "
                    "flextools_undo_last_operation to actually reverse a "
                    "prior session's writes. Only meaningful when write_enabled=True."
    )


class ManageConfigInput(BaseModel):
    """Get, set, delete, or list persistent configuration."""
    action: Literal["get", "set", "delete", "list"] = Field(
        description="Configuration action to perform"
    )
    key: Optional[str] = Field(
        default=None,
        description="Dotted key (e.g., 'paths.flexicon') for get/set/delete actions"
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
    count: int = Field(
        default=1,
        ge=1,
        description="How many undo steps to perform in one call (default 1). "
                    "Useful when a single flextools_run_module call wrapped "
                    "multiple UndoableOperations and you want to roll all of "
                    "them back together."
    )


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
    api_mode: Literal["flexicon", "flexlibs_stable", "liblcm", "all"] = Field(
        default="flexicon",
        description="API mode: 'flexicon' (recommended), 'flexlibs_stable', 'liblcm', 'all'. "
                    "The deprecated value 'flexlibs2' is accepted as an alias for 'flexicon'."
    )
    _normalize_api_mode = field_validator("api_mode", mode="before")(_normalize_mode)


class GetObjectApiInput(BaseModel):
    """Get detailed API documentation for an object."""
    object_type: str = Field(
        description="The object type to look up (e.g., 'ILexEntry', 'LexEntryOperations')"
    )
    include_flexicon: bool = Field(
        default=True,
        description="Include Flexicon wrapper methods"
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


class ListProjectsInput(BaseModel):
    """List available FieldWorks projects on this machine."""
    name_contains: Optional[str] = Field(
        default=None,
        description="Optional case-insensitive substring filter applied to project names."
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


class GetWrapperDependenciesInput(BaseModel):
    """Look up the LibLCM internals a flexlibs/flexicon wrapper method uses."""
    method: str = Field(
        description="Fully-qualified wrapper method (e.g. 'LexEntryOperations.GetHeadword' or 'FLExProject.LexiconAllEntries')"
    )
    library: Literal["flexicon", "flexlibs_stable"] = Field(
        default="flexicon",
        description="Which wrapper library: 'flexicon' or 'flexlibs_stable' "
                    "('flexlibs2' accepted as a deprecated alias for 'flexicon')"
    )
    _normalize_library = field_validator("library", mode="before")(_normalize_mode)


class ResolveTypeInput(BaseModel):
    """Resolve a type name to its canonical namespace and import statement."""
    type_name: str = Field(
        description="Type name to resolve (e.g. 'SandboxGenericMSA', 'IMultiAccessorBase', 'ILexEntry'). "
                    "Single-purpose lookup -- cheaper than get_object_api when you only need the import path."
    )
    library: Literal["liblcm", "flexicon", "flexlibs_stable", "auto"] = Field(
        default="auto",
        description="Which index to search. 'auto' (default) searches liblcm first, then flexlibs."
    )
    _normalize_library = field_validator("library", mode="before")(_normalize_mode)


class FindWrappersForLcmInput(BaseModel):
    """Find which wrapper methods cover a given LibLCM symbol."""
    lcm_name: str = Field(
        description="LCM name to look up (e.g. 'ILexEntry', 'ILexEntry.HeadWord', 'ILexEntryRefFactory', 'ICmObjectRepository')"
    )
    kind: Literal["entity", "factory", "repository", "method", "property", "auto"] = Field(
        default="auto",
        description="What kind of LCM thing this is: 'entity' | 'factory' | 'repository' | 'method' | 'property' | 'auto'"
    )
    include: list[str] = Field(
        default_factory=lambda: ["flexicon", "flexlibs_stable"],
        description="Which wrapper libraries to check ('flexlibs2' accepted as a "
                    "deprecated alias for 'flexicon')"
    )
    _normalize_include = field_validator("include", mode="before")(_normalize_mode_list)


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
    api_target: Optional[Literal["flexicon", "flexlibs_stable", "liblcm"]] = Field(
        default=None,
        description="Target API: 'flexicon' (recommended), 'flexlibs_stable', 'liblcm'"
    )
    _normalize_api_target = field_validator("api_target", mode="before")(_normalize_mode)
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
    user_intent: Optional[str] = Field(
        default=None,
        max_length=200,
        description="One-sentence paraphrase of what the human user asked you to do, "
                    "under 200 chars. Logged on session start for post-mortem clarity. "
                    "Example: 'Add a Pinyin gloss to senses whose English gloss starts with to.'"
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

class ListSkeletonsInput(BaseModel):
    """List captured skeletons from the storage closet (issue #24)."""
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of skeletons to return, most-recent-first."
    )


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
                    "All flexicon Operations classes are pre-imported."
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
    skip_module_check: bool = Field(
        default=False,
        description="If True, skip the partial-module structural check. "
                    "Use when intentionally running module-shaped code (with `def Main`) "
                    "that lacks docs/FlexToolsModule scaffolding -- e.g. quick tests of a "
                    "Main-shaped function without bothering to fetch the full template."
    )
    user_intent: Optional[str] = Field(
        default=None,
        max_length=200,
        description="One-sentence paraphrase of what the human asked you to do, under 200 chars. "
                    "Logged on the operation start line so post-mortem readers can see the goal "
                    "without scrolling back through the conversation. "
                    "Example: 'List entries whose lexeme form starts with a vowel.'"
    )
    max_info_messages: int = Field(
        default=100,
        ge=0,
        le=10000,
        description="Max report.Info messages to return verbatim. If exceeded, keep the "
                    "first cap//2 and last cap//2 with a truncation marker in between. "
                    "Pass 0 to disable the cap (return all info messages, no truncation). "
                    "Errors and warnings are NEVER capped -- they always survive intact."
    )
