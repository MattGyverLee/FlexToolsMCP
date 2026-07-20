#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool definitions for FlexToolsMCP MCP server.

Centralized definition of all MCP tools with their Pydantic models,
descriptions, and annotations. This replaces the massive list_tools()
function with a data-driven approach.
"""

from typing import Optional, Type
from pydantic import BaseModel
from mcp.types import ToolAnnotations

# Import response models for outputSchema wiring
from .response_models import (
    RunModuleSuccess,
    GetObjectApiSuccess,
    SearchByCapabilitySuccess,
)

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
        output_model: Optional[Type[BaseModel]] = None,
    ):
        self.name = name
        self.description = description
        self.input_model = input_model
        self.annotations = annotations
        self.output_model = output_model
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
# All Tools (21 total -- this count drifts; see dispatch.ALL_TOOL_NAMES
# for the authoritative registered set)
# ============================================================

TOOLS: dict[str, ToolDef] = {
    "flextools_start": ToolDef(
        name="flextools_start",
        description="""[WORKFLOW - BEGIN HERE] Initialize the FlexTools MCP session.

REQUIRED: Sets api_mode to determine which API (flexicon, flexlibs_stable, or liblcm) to use.
OPTIONAL: task description for initial API discovery, project_name for operations, etc.

After calling flextools_start():
- Use flextools_search_by_capability(query='...') for API discovery
- Use flextools_get_object_api(object_type='...') for detailed API info
- Use flextools_run_module() to execute code (accepts bare snippets and full Main-shaped modules)

Task and project_name can be set now or updated/provided later as needed.

OPTIONAL: fill `user_request` with the VERBATIM text of what the human just asked
(not a paraphrase) -- this is the turn-level slot for the diagnostic-report
feature; it is carried through to any run_module ops this turn unless a given
op overrides it with its own user_request.

Undoable mode: undoable now DEFAULTS to True whenever write_enabled=True (issue #55)
-- the project opens with LCM's persistent undo stack enabled (matches FLEx UI
Ctrl+Z), so flextools_undo_last_operation can reverse a prior session's writes
without any extra opt-in. Pass undoable=False explicitly to disable it.
Both write_enabled and undoable are inherited from the prior session on re-init when
not explicitly provided (per #9 fix). The session-local checkpoint log is capped at
500 entries (deque maxlen); past that the oldest local checkpoint record is silently
evicted (the real LCM undo stack itself is unaffected -- see docs/RECOVERY.md).""",
        input_model=FlexToolsStartInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_get_object_api": ToolDef(
        name="flextools_get_object_api",
        description="""[WORKFLOW STEP 3] Get detailed API documentation for an object. Use AFTER flextools_search_by_capability to validate and understand the APIs you want to use.

WARNING: Calling flextools_get_object_api is required BEFORE using an API in flextools_run_module. This ensures you have full context of the signature and behavior, reducing debugging.

IMPORTANT: Each API result includes 'import_statement' showing exactly what to add at the top of your code. When you use LexEntryOperations, LexSenseOperations, or any Operations class in your code, you MUST include the import statement shown in the API response.

CASTING: Properties that require a pythonnet cast are annotated inline (requires_cast, cast_to, cast_example) and polymorphic collections are flagged (polymorphic, iteration_note); a top-level casting_notes counter summarizes them. Write the cast_example as-is -- preflight rejects uncast access. You no longer need flextools_resolve_property on the happy path (keep it only for chained/ambiguous receivers).

Tip: Use summary_only=true first to explore large objects, then drill down into specific methods.""",
        input_model=GetObjectApiInput,
        annotations=READ_ONLY_SAFE,
        output_model=GetObjectApiSuccess,
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
- Flexicon wrapper classes (recommended, ~1400 methods with examples)
- Direct LibLCM interfaces for advanced use
- Navigation methods to move between related objects""",
        input_model=SearchCapabilityInput,
        annotations=READ_ONLY_SAFE,
        output_model=SearchByCapabilitySuccess,
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
2. Target API mode (flexicon, flexlibs_stable, liblcm)
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
You must include `from flexicon import ...` in your code, or use the project
accessors (project.POS, project.LexEntry, project.Senses, ...) which create the
instances lazily. Every Operations class you reference must be discovered first
via flextools_get_object_api -- the runner rejects code that uses an undiscovered
entity (see api_discovery_required / undiscovered_entity errors).

When you call this, fill `user_intent` with a one-sentence summary of what the
user asked you to do (under 200 chars). It is logged on the operation Start
block so post-mortem readers can see the goal without scrolling back through
the conversation. Skipping it is allowed but discouraged.

OPTIONAL `user_request`: the VERBATIM human request text, only needed here if
intent drifted since flextools_start (which already captures it per-turn).

VALIDATE WITHOUT EXECUTING (issue #49): pass validate_only=True to run the full
11-gate preflight (plus a read-only project-lock probe) WITHOUT opening the
project or spawning a subprocess. Returns status 'validated'|'validation_failed',
a per-gate `checks[]` array (ALL gates reported, not just the first failure),
and a `writeability` block describing any mutations the script would make.
Use this to ask "would this go green?" before committing to a real (especially
write) run.

WRITE-PATH SAFETY LADDER (issue #55): a mutating run (write_enabled=True AND the
script is not certified read-only) additionally requires `confirmed=True`.
Submitting without it returns error_code='confirmation_required' plus the
mutation plan (mutations_detected[], backup intent) and executes NOTHING --
review the plan, then resubmit the same call with confirmed=True. Before the
FIRST such confirmed mutating run per (session, project), an automatic backup
of the project's .fwdata is taken (see the `backup` field in the response);
opt out with backup_before_write=False. Read-only runs are unaffected by both
`confirmed` and the backup step.""",
        input_model=RunModuleInput,
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
        output_model=RunModuleSuccess,
    ),

    "flextools_prepare_report": ToolDef(
        name="flextools_prepare_report",
        description="""Prepare a diagnostic report for the maintainer -- "send this to the maintainer" flow.

Reconstructs the failing slice (request -> interpretation -> what-was-tried
-> error -> resolution) from the session log + operations.jsonl, writes ONE
local report file to ~/.flextoolsmcp/reports/report_<ts>.md, and returns
prepared (but NOT sent) transport strings for three outcomes: a `gh issue
create` command, a prefilled GitHub issue URL, and a `mailto:` link.

This tool NEVER sends anything itself -- present the three outcomes to the
user (GitHub default, email if `likely_contains_lexical_data` flags a
confidentiality concern, or don't-send) and let them choose. Report is
always full-fidelity/unscrubbed (no anonymization exists); privacy is
protected by channel choice, never by content masking.

Defaults to the WHOLE TURN (the contiguous run of ops sharing one
user_intent) containing the most recent operation. Use op_id to anchor on a
different op, steps_back/include_from_op_id to widen the slice backward, or
op_ids for an explicit list (bypasses turn-boundary logic entirely). Useful
even when the auto-offer on a run_module response was suppressed/deduped --
this tool always produces a report on request.""",
        input_model=PrepareReportInput,
        annotations=ToolAnnotations(
            readOnlyHint=False,   # writes one local report_<ts>.md file per call
            destructiveHint=False,
            idempotentHint=False,  # each call writes a NEW timestamped file
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

When to use: Off the happy path. flextools_get_object_api now inlines casting
requirements at discovery time (requires_cast / cast_to / cast_example), and the
casting_issues_detected rejection inlines the rewrite and imports_needed in each
casting_issues[*] entry. Reach for this tool only for chained/ambiguous receivers
where those paths emit no rewrite (rewrite: null), or as the debugging entry
point for "has no attribute" errors on code you didn't discover through the gate.""",
        input_model=ResolvePropertyInput,
        annotations=READ_ONLY_SAFE,
    ),

    "flextools_manage_config": ToolDef(
        name="flextools_manage_config",
        description="""Get, set, delete, or list persistent configuration values.

Actions:
- 'get': Retrieve a config value by dotted key (e.g., 'paths.flexicon')
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
        description="""Look up the LibLCM internals (factories, repositories, properties, methods, mapping_type) that a flexlibs/flexicon wrapper method uses.

Use this when you need to understand what a wrapper method does under the hood, or whether
switching to api_mode='liblcm' would let you reach internals the wrapper doesn't expose.

Input:
- method: 'ClassName.MethodName' (e.g. 'LexEntryOperations.GetHeadword')
- library: 'flexicon' (default) or 'flexlibs_stable'

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
case for raw LCM types), then flexicon / flexlibs_stable.

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
'ICmObjectRepository') and want to know whether flexicon or flexlibs_stable wraps it -
or whether you need to drop to api_mode='liblcm' because no wrapper exists.

Input:
- lcm_name: e.g. 'ILexEntry', 'ILexEntry.HeadWord', 'ICmAgentEvaluationFactory'
- kind: 'entity' | 'factory' | 'repository' | 'method' | 'property' | 'auto' (default)
- include: list of libraries to check (default ['flexicon', 'flexlibs_stable'])

Returns coverage per library and an explicit `gaps` list naming libraries with no coverage,
so missing wrappers are surfaced rather than silently absent.""",
        input_model=FindWrappersForLcmInput,
        annotations=READ_ONLY_SAFE,
    ),
}
