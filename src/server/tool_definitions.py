#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool definitions for FlexToolsMCP MCP server.

Centralized definition of all MCP tools with their Pydantic models,
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
    ListProjectsInput,
    ResolvePropertyInput,
    StartModuleInput,
    GetOperationLogsInput,
    RunModuleInput,
    GetWrapperDependenciesInput,
    FindWrappersForLcmInput,
    ResolveTypeInput,
    ListSkeletonsInput,
)


# ============================================================
# Tool Metadata & Shared Annotations
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
        self._cached_schema = None  # Cache for pre-generated schema

    def get_schema(self):
        """Get cached schema, or generate and cache it on first call."""
        if self._cached_schema is None:
            # Defer import to avoid circular dependencies
            from .utils import model_to_tool_schema
            self._cached_schema = model_to_tool_schema(self.input_model)
        return self._cached_schema


# Default annotations for read-only, safe operations (most tools use this)
READ_ONLY_SAFE = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# ============================================================
# All Tools (15 total)
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
- Use flextools_run_module() to execute code (accepts bare snippets and full Main-shaped modules)

Task and project_name can be set now or updated/provided later as needed.

OPT-IN undoable mode (EXPERIMENTAL): pass undoable=True alongside write_enabled=True
to open the project with LCM's persistent undo stack enabled (matches FLEx UI Ctrl+Z).
Required if you want flextools_undo_last_operation to reverse a prior session's writes.
Both write_enabled and undoable are inherited from the prior session on re-init when
not explicitly provided (per #9 fix).""",
        input_model=FlexToolsStartInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_get_object_api": ToolDef(
        name="flextools_get_object_api",
        description="""[WORKFLOW STEP 3] Get detailed API documentation for an object. Use AFTER flextools_search_by_capability to validate and understand the APIs you want to use.

WARNING: Calling flextools_get_object_api is required BEFORE using an API in flextools_run_module. This ensures you have full context of the signature and behavior, reducing debugging.

IMPORTANT: Each API result includes 'import_statement' showing exactly what to add at the top of your code. When you use LexEntryOperations, LexSenseOperations, or any Operations class in your code, you MUST include the import statement shown in the API response.

Tip: Use summary_only=true first to explore large objects, then drill down into specific methods.""",
        input_model=GetObjectApiInput,
        annotations=READ_ONLY_SAFE,
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
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_get_navigation_path": ToolDef(
        name="flextools_get_navigation_path",
        description="""Find navigation paths between object types.

Example:
- from_object='ILexEntry' to_object='ILexExampleSentence'
- Result: ILexEntry -> ILexSense -> ILexExample -> ILexExampleSentence

Useful for understanding object relationships and writing traversal code.""",
        input_model=GetNavigationPathInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_find_examples": ToolDef(
        name="flextools_find_examples",
        description="""Find code examples for operations.

Search by:
- method_name: Find examples using a specific method
- operation_type: Find examples for 'create', 'read', 'update', 'delete', 'iterate', 'search'
- object_type: Filter examples by entity type ('Entry', 'Sense', 'Example', etc.)""",
        input_model=FindExamplesInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_list_categories": ToolDef(
        name="flextools_list_categories",
        description="""List all available API categories.

Returns: Category names like 'lexicon', 'grammar', 'texts', 'media', 'notebook', 'lists', 'system'
with entity counts for each.""",
        input_model=ListCategoriesInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_list_entities_in_category": ToolDef(
        name="flextools_list_entities_in_category",
        description="""List all entities/classes in a specific category.

Example categories: 'lexicon', 'grammar', 'texts', 'media'""",
        input_model=ListEntitiesInCategoryInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_list_projects": ToolDef(
        name="flextools_list_projects",
        description="""List FieldWorks projects available on this machine.

SAFE: This tool never opens any project. It only enumerates the projects
directory and checks for <name>/<name>.fwdata sibling files -- no LCM cache
load, no .fwdata modification-time change. Free to call at any time.

When to use:
- The user asked for a project but you don't have it set yet, or the name
  they gave doesn't match (run_module/start will autocorrect minor case or
  whitespace differences and return suggestions for bigger mismatches).
- The user explicitly asks "what projects do I have?" or "list FLEx projects".

Optional name_contains filter applies a case-insensitive substring match
against project names.""",
        input_model=ListProjectsInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_get_module_template": ToolDef(
        name="flextools_get_module_template",
        description="""Get the official FlexTools module template (Main/docs/FlexToolsModule scaffold).

Fetch this when you are graduating a working snippet into a named, reusable
module the user wants to keep (saved as a .py file in their FlexTools Modules
folder). For exploratory snippets executed via flextools_run_module(), the
bare-snippet form is first-class -- no template required.""",
        input_model=GetModuleTemplateInput,
        annotations=READ_ONLY_SAFE,
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
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_run_module": ToolDef(
        name="flextools_run_module",
        description="""Execute code against a FieldWorks project.

Accepts:
- Full modules: def Main(project, report, modifyAllowed): ...
- Code snippets: entries = project.LexEntry.GetAll()
- Anything in between

If code defines Main(), it will be called. Otherwise, code runs as-is.

SAFETY: write_enabled defaults to False (dry-run mode). Set to True only after testing!

All code has access to:
- project: FLExProject instance
- report: Output mechanism (report.Info/Warning/Error)
- write_enabled / modifyAllowed: Boolean flag for write operations
- Helpers: is_empty_multistring, FLEX_EMPTY_PLACEHOLDER, find_writing_system, list_writing_systems

Operations classes (POSOperations, LexEntryOperations, etc.) are NOT auto-imported.
You must include `from flexlibs2 import ...` in your code, or use the project
accessors (project.POS, project.LexEntry, project.Senses, ...) which create the
instances lazily. Every Operations class you reference must be discovered first
via flextools_get_object_api -- the runner rejects code that uses an undiscovered
entity (see api_discovery_required / undiscovered_entity errors).

When you call this, fill `user_intent` with a one-sentence summary of what the
user asked you to do (under 200 chars). It is logged on the operation Start
block so post-mortem readers can see the goal without scrolling back through
the conversation. Skipping it is allowed but discouraged.""",
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
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_resolve_property": ToolDef(
        name="flextools_resolve_property",
        description="""Resolve property names and check pythonnet casting requirements.

When you encounter "has no attribute" errors or need to know if a property requires casting,
use this tool to get the full resolution path and casting instructions.

When to use: Mostly redundant when the polymorphic-casting validator fires --
the casting_issues_detected rejection now inlines the rewrite (the cast-wrapped
expression) and imports_needed (the SIL.LCModel imports to add) directly in
each casting_issues[*] entry. Use this tool for ad-hoc lookups when writing
new code from scratch, or as a fallback when the preflight didn't catch the
issue (e.g. chained or call-rooted receivers the inline rewriter skips).""",
        input_model=ResolvePropertyInput,
        annotations=READ_ONLY_SAFE,
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
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_undo_last_operation": ToolDef(
        name="flextools_undo_last_operation",
        description="""Undo the most recent database write operation via LCM's persistent undo stack.

Executes project.Undo() in a subprocess, which reverses the most recent
UndoableOperation -- the SAME stack FLEx UI Ctrl+Z uses. Survives MCP
session boundaries: writes made by a prior session are reachable if
they were made with undoable=True.

REQUIRES the session to have been started with undoable=True (opt-in
during the experimental phase -- pass to flextools_start). Will refuse
with a clear error if the session is not undoable-mode, since
project.Undo() would raise FP_TransactionError otherwise.

Pass count=N to undo multiple steps in one call (useful for rolling
back a single run_module that wrapped multiple UndoableOperations).""",
        input_model=UndoLastOperationInput,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    ),

    "flextools_get_wrapper_dependencies": ToolDef(
        name="flextools_get_wrapper_dependencies",
        description="""Look up the LibLCM internals (factories, repositories, properties, methods, mapping_type) that a flexlibs/flexlibs2 wrapper method uses.

Use this when you need to understand what a wrapper method does under the hood, or whether
switching to api_mode='liblcm' would let you reach internals the wrapper doesn't expose.

Input:
- method: 'ClassName.MethodName' (e.g. 'LexEntryOperations.GetHeadword')
- library: 'flexlibs2' (default) or 'flexlibs_stable'

Returns the bridge entry: lcm_deps, properties_accessed, methods_called, repositories_used,
factories_used, mapping_type, plus an advisory about which surface is callable in the active session.""",
        input_model=GetWrapperDependenciesInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_resolve_type": ToolDef(
        name="flextools_resolve_type",
        description="""Resolve a type name to its canonical namespace, assembly, and import statement.

Single-purpose lookup -- much cheaper than flextools_get_object_api when you only need
to know which `from <namespace> import <Type>` line to use.

Use this when you have a bare type name (from search results, an error message, or context)
and need the import path before you can use it in code. Searches liblcm first (most common
case for raw LCM types), then flexlibs2 / flexlibs_stable.

Example:
  flextools_resolve_type(type_name='SandboxGenericMSA')
  -> { namespace: 'SIL.LCModel.DomainServices',
       import_statement: 'from SIL.LCModel.DomainServices import SandboxGenericMSA',
       assembly: 'SIL.LCModel.dll', ... }

Returns substring suggestions on a miss to help recover from typos.""",
        input_model=ResolveTypeInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_list_skeletons": ToolDef(
        name="flextools_list_skeletons",
        description="""List captured "skeleton" helpers that survived prior sessions (issue #24).

Each successful flextools_run_module() call auto-captures top-level `def` functions to a
JSONL "closet" on disk. This tool surfaces them so prior helpers (pos_abbr, get_words,
seg_interlinear, affix-iteration patterns) can be reused instead of rewritten from scratch.

Returns: name, source, entities the helper walked, the original user_intent (if known),
captured_at timestamp, and op_id. Most-recent-first; capped by `limit` (default 100).

Tip: flextools_find_examples also surfaces these (under `skeletons_from_your_sessions`)
when filtered by object_type.""",
        input_model=ListSkeletonsInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_find_wrappers_for_lcm": ToolDef(
        name="flextools_find_wrappers_for_lcm",
        description="""Find which wrapper methods cover a given LibLCM symbol (entity, factory, repository, method, or property).

Use this when you have an LCM name (e.g. 'ILexEntry', 'ICmAgentEvaluationFactory',
'ICmObjectRepository') and want to know whether flexlibs2 or flexlibs_stable wraps it -
or whether you need to drop to api_mode='liblcm' because no wrapper exists.

Input:
- lcm_name: e.g. 'ILexEntry', 'ILexEntry.HeadWord', 'ICmAgentEvaluationFactory'
- kind: 'entity' | 'factory' | 'repository' | 'method' | 'property' | 'auto' (default)
- include: list of libraries to check (default ['flexlibs2', 'flexlibs_stable'])

Returns coverage per library and an explicit `gaps` list naming libraries with no coverage,
so missing wrappers are surfaced rather than silently absent.""",
        input_model=FindWrappersForLcmInput,
        annotations=READ_ONLY_SAFE,
    ),
}
