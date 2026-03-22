#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool definitions for FlexToolsMCP MCP server.

Centralized definition of all 16 MCP tools with their Pydantic models,
descriptions, and annotations. This replaces the massive list_tools()
function with a data-driven approach.
"""

from typing import Type
from pydantic import BaseModel
from mcp.types import ToolAnnotations

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
    RunOperationInput,
    RunModuleInput,
)


# ============================================================
# Tool Metadata
# ============================================================

class ToolDef:
    """Metadata for a single MCP tool."""

    def __init__(
        self,
        name: str,
        description: str,
        input_model: Type[BaseModel],
        annotations: ToolAnnotations,
    ):
        self.name = name
        self.description = description
        self.input_model = input_model
        self.annotations = annotations


# ============================================================
# All 16 Tools
# ============================================================

TOOLS: dict[str, ToolDef] = {
    "flextools_start": ToolDef(
        name="flextools_start",
        description="""[WORKFLOW - BEGIN HERE] Initialize the FlexTools MCP session.

REQUIRED: Sets api_mode to determine which API (flexlibs2, flexlibs_stable, or liblcm) to use.
OPTIONAL: task description for initial API discovery, project_name for operations, etc.

After calling flextools_start():
- Use flextools_search_by_capability(query='...') for API discovery
- Use flextools_get_object_api(object_type='...') for detailed API info
- Use flextools_run_operation() or flextools_run_module() to execute code against a FieldWorks project

Task and project_name can be set now or updated/provided later as needed.""",
        input_model=FlexToolsStartInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_get_object_api": ToolDef(
        name="flextools_get_object_api",
        description="""[WORKFLOW STEP 3] Get detailed API documentation for an object. Use AFTER flextools_search_by_capability to validate and understand the APIs you want to use.

WARNING: Calling flextools_get_object_api is required BEFORE using an API in flextools_run_operation/flextools_run_module. This ensures you have full context of the signature and behavior, reducing debugging.

IMPORTANT: Each API result includes 'import_statement' showing exactly what to add at the top of your code. When you use LexEntryOperations, LexSenseOperations, or any Operations class in your code, you MUST include the import statement shown in the API response.

Tip: Use summary_only=true first to explore large objects, then drill down into specific methods.""",
        input_model=GetObjectApiInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_search_by_capability": ToolDef(
        name="flextools_search_by_capability",
        description="""[WORKFLOW STEP 2] Search for methods/functions by natural language capability.

Example queries:
- "How do I add a gloss to a sense?"
- "Find methods to delete senses"
- "Count entries matching a condition"
- "Iterate over all wordforms in a text"

The search engine uses semantic understanding to find relevant APIs, including:
- FlexLibs 2.0 wrapper classes (recommended, ~1400 methods with examples)
- Direct LibLCM interfaces for advanced use
- Navigation methods to move between related objects""",
        input_model=SearchCapabilityInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_get_navigation_path": ToolDef(
        name="flextools_get_navigation_path",
        description="""Find navigation paths between object types.

Example:
- from_object='ILexEntry' to_object='ILexExampleSentence'
- Result: ILexEntry -> ILexSense -> ILexExample -> ILexExampleSentence

Useful for understanding object relationships and writing traversal code.""",
        input_model=GetNavigationPathInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_find_examples": ToolDef(
        name="flextools_find_examples",
        description="""Find code examples for operations.

Search by:
- method_name: Find examples using a specific method
- operation_type: Find examples for 'create', 'read', 'update', 'delete', 'iterate', 'search'
- object_type: Filter examples by entity type ('Entry', 'Sense', 'Example', etc.)""",
        input_model=FindExamplesInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_list_categories": ToolDef(
        name="flextools_list_categories",
        description="""List all available API categories.

Returns: Category names like 'lexicon', 'grammar', 'texts', 'media', 'notebook', 'lists', 'system'
with entity counts for each.""",
        input_model=ListCategoriesInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_list_entities_in_category": ToolDef(
        name="flextools_list_entities_in_category",
        description="""List all entities/classes in a specific category.

Example categories: 'lexicon', 'grammar', 'texts', 'media'""",
        input_model=ListEntitiesInCategoryInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_get_module_template": ToolDef(
        name="flextools_get_module_template",
        description="""Get the official FlexTools module template.

Call this before running flextools_run_module() to get the proper boilerplate.""",
        input_model=GetModuleTemplateInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_start_module": ToolDef(
        name="flextools_start_module",
        description="""Interactive wizard to start creating a new FlexTools module.

Guides you through:
1. Module name and synopsis
2. Target API mode (flexlibs2, flexlibs_stable, liblcm)
3. Whether it modifies the database
4. Primary domain (lexicon, grammar, texts, etc.)
5. Optional dry-run mode setup""",
        input_model=StartModuleInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_run_module": ToolDef(
        name="flextools_run_module",
        description="""Execute a FlexTools module against a FieldWorks project.

SAFETY: write_enabled defaults to False (dry-run mode). Set to True only after testing!

Module must be in valid FlexTools format (call get_module_template first).""",
        input_model=RunModuleInput,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    ),

    "flextools_get_operation_logs": ToolDef(
        name="flextools_get_operation_logs",
        description="""View operation execution logs and pattern recommendations.

Returns: Recent log entries, errors, and AI-generated recommendations for fixing patterns.""",
        input_model=GetOperationLogsInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_run_operation": ToolDef(
        name="flextools_run_operation",
        description="""Execute FlexLibs2 operations directly against a FieldWorks project.

For quick one-off operations. For complex multi-step workflows, use flextools_run_module instead.

SAFETY: write_enabled defaults to False (dry-run mode). Set to True only after testing!

The 'operations' parameter contains Python code with access to:
- project: FLExProject instance
- report: Output mechanism for results
- write_enabled: Boolean from session
All flexlibs2 Operations classes are pre-imported.""",
        input_model=RunOperationInput,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    ),

    "flextools_resolve_property": ToolDef(
        name="flextools_resolve_property",
        description="""Resolve property names and check pythonnet casting requirements.

When you encounter "has no attribute" errors or need to know if a property requires casting,
use this tool to get the full resolution path and casting instructions.""",
        input_model=ResolvePropertyInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_manage_config": ToolDef(
        name="flextools_manage_config",
        description="""Get, set, delete, or list persistent configuration values.

Actions:
- 'get': Retrieve a config value by dotted key (e.g., 'paths.flexlibs2')
- 'set': Set a config value
- 'delete': Remove a config value
- 'list': Show all configuration""",
        input_model=ManageConfigInput,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_get_session_history": ToolDef(
        name="flextools_get_session_history",
        description="""View session operation history and undo/redo availability.

Returns: List of operations performed, current undo stack, and next operation to undo.""",
        input_model=GetSessionHistoryInput,
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    ),

    "flextools_undo_last_operation": ToolDef(
        name="flextools_undo_last_operation",
        description="""Undo the most recent database write operation.

Calls ActionHandler.Undo() to roll back changes.""",
        input_model=UndoLastOperationInput,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    ),
}
