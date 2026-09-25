#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pydantic input/output models for FlexToolsMCP.

These models define type-safe, validated request/response schemas for all MCP tools.
They replace raw JSON Schema dicts and provide automatic validation, type coercion,
and IDE autocomplete support.
"""

from typing import Optional, Literal, Any, List, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
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
        description="Documentation and preflight context: 'flexicon' (recommended, "
                    "~1400 indexed methods), 'flexlibs_stable' (legacy ~71 methods), "
                    "'liblcm' (raw C# API). flextools_run_module always executes with "
                    "flexicon imports regardless of this value (issue #164). The deprecated "
                    "value 'flexlibs2' is accepted as an alias for 'flexicon'."
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
    user_request: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="Optional: the VERBATIM text of the human's request for this "
                    "turn (not a paraphrase). Diagnostic-report feature (spec section 4): "
                    "captured at the source because the MCP process never sees the raw "
                    "conversation otherwise. Primary/turn-level placement -- "
                    "flextools_run_module accepts an optional per-op override of the "
                    "same field when intent drifts mid-turn. Absent user_request falls "
                    "back to the user_intent paraphrase wherever it is logged."
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
    """View session operation history."""
    include_operations: bool = Field(
        default=False,
        description="Include full list of operations in response"
    )


class GetModuleTemplateInput(BaseModel):
    """Get the official FlexTools module template."""
    # Declared as a plain str (not Literal) on purpose: an unknown flavor must
    # reach the handler so it can return the structured `invalid_flavor` error
    # (available_flavors + recommended) instead of a generic Pydantic 422. If
    # this field is omitted, model_dump() drops the caller's `flavor` as an
    # unknown extra and the handler silently falls back to 'flexicon' (issue #78).
    flavor: str = Field(
        default="flexicon",
        description="Template flavor: 'flexicon' (recommended), 'flexlibs_stable', or "
                    "'liblcm'. Aliases 'stable', 'advanced', and 'flexlibs2' are accepted."
    )
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
        description="Issue #55 (Rung 3): ENFORCED for mutating writes. When the "
                    "script is certified mutating (see `writeability`) AND "
                    "write_enabled=True, a call with confirmed=False is refused "
                    "with error_code='confirmation_required' plus the mutation "
                    "plan (mutations_detected[], affected entities, backup intent) "
                    "-- nothing executes. Resubmit the SAME call with "
                    "confirmed=True to actually run it. Ignored entirely on "
                    "read-only runs (no mutating calls detected): confirmed has no "
                    "effect there. Config key 'require_write_confirmation' (default "
                    "True) can disable this gate server-wide for power users who "
                    "accept the risk."
    )
    validate_only: bool = Field(
        default=False,
        description="Issue #49: run the full 11-gate preflight (syntax, server "
                    "state, partial-module structure, unprotected writes, casting, "
                    "API discovery x2, undefined vars, imports x2, invalid API "
                    "chains) plus a READ-ONLY project-lock probe, then STOP -- the "
                    "project is never opened and no subprocess is spawned. ALL "
                    "gates are evaluated and reported in one response (no "
                    "short-circuit, except that a syntax error blocks the "
                    "AST-dependent gates after it). Returns status "
                    "'validated'|'validation_failed', a `checks[]` array (one "
                    "entry per gate), and a `writeability` block describing any "
                    "mutations the script would make. Discovery gates REPORT but "
                    "do NOT mark entities as discovered -- validation is "
                    "side-effect-free. Use this to ask \"would this go green?\" "
                    "before actually running, especially before a write."
    )
    backup_before_write: Optional[bool] = Field(
        default=None,
        description="Issue #55 (Rung 2): opt-out of the automatic pre-write "
                    "backup. None (default) defers to the server-side config key "
                    "'backup_before_write' (default True). Only relevant on the "
                    "FIRST mutating run per (session, project) -- subsequent "
                    "mutating runs in the same session/project reuse that backup "
                    "and never re-copy. The backup is skipped (with a WARNING) "
                    "when free disk space is under 2x the project's .fwdata size. "
                    "Restore is manual -- see docs/RECOVERY.md."
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
    user_request: Optional[str] = Field(
        default=None,
        max_length=4000,
        description="Optional: the VERBATIM text of the human's request, as an override "
                    "of the turn-level user_request supplied to flextools_start when intent "
                    "drifts mid-turn. Diagnostic-report feature (spec section 4). Logged on "
                    "the operation start line next to user_intent; absent user_request "
                    "falls back to the user_intent paraphrase."
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
    auto_fix: Optional[bool] = Field(
        default=None,
        description="Issue #46: opt-in to safe auto-apply of CASTING rewrites and TYPO "
                    "corrections before execution. None (default) defers to the server-side "
                    "config key 'auto_fix_enabled' (default: True for read-only runs). "
                    "Overrides the config when explicitly set. Write runs ALWAYS skip "
                    "auto-fix regardless of this flag."
    )
    source: Literal["authored", "existing"] = Field(
        default="authored",
        description="Issue #80: provenance of this code, a COST lever (never a safety lever). "
                    "'authored' (default): you wrote this code this session -- full API "
                    "discovery verification applies (call get_object_api/search_by_capability "
                    "first, or accept the graceful read-only auto-discovery). "
                    "'existing': the code came from disk or the human pasted it -- the "
                    "API-discovery gates (api_discovery_required, undiscovered_entity) are "
                    "SKIPPED to avoid expensive re-verification of code you did not author. "
                    "Write-safety (CUD detection, unprotected-write guard) and casting "
                    "injection ALWAYS run regardless of this flag -- provenance can never "
                    "relax a safety gate. CUD still requires confirmed=True."
    )


# ============================================================
# Diagnostic-report tools (CP3)
# ============================================================

class PrepareReportInput(BaseModel):
    """Explicitly prepare a diagnostic report bundle (spec sections 5, 10).

    Lets a user/Claude ask "report the last error" even when the auto-offer
    was suppressed/deduped, and lets Claude size the slice with steps_back /
    include_from_op_id / op_ids instead of accepting the default whole-turn
    boundary. This tool NEVER sends anything -- it writes ONE local report
    file under ~/.flextoolsmcp/reports/ and returns prepared transport
    strings (gh argv, GitHub issue URL, mailto: URI) for a human to act on.
    """
    op_id: Optional[str] = Field(
        default=None,
        description="Anchor op_id for the default whole-turn slice (spec section 5). "
                    "Defaults to the most recent operation in operations.jsonl when omitted."
    )
    op_ids: Optional[List[str]] = Field(
        default=None,
        description="Explicit list of op_ids to include verbatim, bypassing turn-boundary "
                    "logic entirely. Takes precedence over op_id/steps_back/include_from_op_id."
    )
    steps_back: Optional[int] = Field(
        default=None,
        ge=0,
        description="Include this many ops before the anchor (op_id), through turn end. "
                    "Use when the root cause was set up earlier in the turn than the "
                    "immediately-failing op."
    )
    include_from_op_id: Optional[str] = Field(
        default=None,
        description="Include from this op_id (inclusive) through turn end. Alternative to "
                    "steps_back when you know the exact starting op_id."
    )


# ============================================================
# Diagnostics tool (issue #56)
# ============================================================

class FlexToolsHealthInput(BaseModel):
    """Composed diagnostic snapshot: versions, index match state, session, logs.

    Read-only. Composes existing detectors (installed-library detection,
    versioned-index file discovery, session state, stale-lock sweep) into a
    single answer for "why is this API missing?" / "which versions am I
    actually running?" -- previously answerable only by reading server logs.
    """
    verbose: bool = Field(
        default=False,
        description="When true, adds project lock status, FLExInit/pythonnet "
                    "importability, and the last 5 operation outcomes from the "
                    "telemetry JSONL. Slower (probes imports and reads a log file); "
                    "leave false for a quick check."
    )


# ============================================================
# Grammar health tool (parser-check CP1)
# ============================================================

class GrammarHealthInput(BaseModel):
    """Pure-LCM static scan for path-multiplying grammar properties (SPEC 9.5.5).

    Read-only. No parse, no export, no subprocess to `hc`, no `HCParser`.
    See contracts/flextools_grammar_health.md.
    """
    project_name: Optional[str] = Field(
        default=None,
        description="Name of the FieldWorks project. Uses session value if set by start()."
    )
    checks: Optional[List[str]] = Field(
        default=None,
        description="Restrict to named check_ids. None (default) runs all implemented checks."
    )
    limit: int = Field(
        default=20,
        description="Per-check cap on objects[]. SPEC S7: responses summarise, "
                    "never inline the full set."
    )


class FoundObject(BaseModel):
    """One object surfaced by a grammar health check (data-model.md `FoundObject`).

    Closed model (extra="forbid") -- see data-model.md's "Validation rules":
    error/finding detail models use extra="forbid" so a typo'd field fails
    loudly rather than silently vanishing. Here it also closes the objects[]
    nesting level against a smuggled severity proxy (score/grade/rank/etc.),
    which is the whole reason this type exists as its own model rather than
    an open dict.
    """
    model_config = ConfigDict(extra="forbid")
    hvo: int
    class_name: str
    label: str
    goto_url: Optional[str] = None


class GrammarHealthFinding(BaseModel):
    """One suspect from the static grammar scan (data-model.md `GrammarFinding`).

    Closed model (extra="forbid"), exactly six fields. Deliberately has no
    `severity`, `score`, `grade`, `rank`, or `priority` (D7, SPEC 9.5.3):
    findings are grouped by check_id and never ordered by count. `count` is
    evidence -- how many objects tripped the check -- never a total to sum
    across findings.
    """
    model_config = ConfigDict(extra="forbid")
    check_id: str
    spec_row: Optional[int] = None
    count: int
    measured: str
    evidence_basis: Optional[str] = None
    objects: List[FoundObject] = Field(default_factory=list)


# ============================================================
# Parse tools (parser-check CP2b)
# ============================================================

class MorphSpec(BaseModel):
    """One piece of a caller's proposed decomposition (data-model.md section 4).

    Declared HERE rather than in `server/parse/resolver.py` because this is
    the shape a *caller* writes: it arrives over the tool boundary inside
    `TryWordInput.morphs` and has to be validated before any resolver is
    reached. The resolver imports it from this module and turns it into MSA
    identifiers; that direction keeps `models.py` free of any dependency on
    the parse package, which is the one import edge that would drag run
    machinery into every tool's schema generation.

    Closed model (`extra="forbid"`) for the same reason the grammar-health
    detail models are: a typo'd field in a decomposition must fail loudly.
    Silently dropping `msa_hov=123` would leave the piece looking like a bare
    headword and resolve it to something the caller did not ask for -- exactly
    the silent narrowing FR-019 exists to prevent.

    THERE IS DELIBERATELY NO FREE-TEXT `form` FIELD. A bare surface string is
    a search, and this feature ships no segmenter; accepting one would promise
    a segmentation the tool cannot perform (data-model.md section 4).
    """
    model_config = ConfigDict(extra="forbid")

    headword: Optional[str] = Field(
        default=None,
        description="Entry headword for this piece, as it appears in the lexicon. "
                    "Exactly one of headword / msa_hvo is required."
    )
    sense: Optional[Any] = Field(
        default=None,
        description="Optional sense, as a gloss string or a 1-based sense number. "
                    "Disambiguates homographs; ignored when msa_hvo is given."
    )
    msa_hvo: Optional[int] = Field(
        default=None,
        description="The identifier form, for a caller that already resolved this "
                    "piece. Exactly one of headword / msa_hvo is required."
    )
    position: Optional[int] = Field(
        default=None,
        description="0-based index of this piece in the decomposition. Optional on "
                    "input -- filled from list order when omitted -- and always "
                    "present downstream, because it is echoed in the refusal."
    )

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "MorphSpec":
        """Exactly one of `headword` / `msa_hvo`, never both and never neither.

        Both is not a harmless redundancy: the two can disagree, and there is
        no defensible rule for which one wins. Neither leaves nothing to
        resolve, which reaches the resolver as an empty selection -- the one
        input the underlying component reads as "admit nothing" rather than
        "no restriction" (contracts/tools.md, "Never widen").
        """
        has_headword = self.headword is not None and str(self.headword).strip() != ""
        has_hvo = self.msa_hvo is not None
        if has_headword and has_hvo:
            raise ValueError(
                "A morph gives either a headword or an msa_hvo, not both -- the "
                "two can disagree and there is no rule for which wins. Drop one."
            )
        if not has_headword and not has_hvo:
            raise ValueError(
                "Each morph needs a headword or an msa_hvo. There is no free-text "
                "form field: a bare surface string is a search, and this tool "
                "ships no segmenter."
            )
        return self


class TryWordInput(BaseModel):
    """Parse one word at one of three levels (parser-check CP2b, FR-012).

    Read-only. The three levels are exposed as three because they answer
    different questions at different costs, and each reaches its own
    underlying operation (contracts/tools.md, "Levels"):

        restricted -> TraceWordXml(word, analyses)   fastest; needs `morphs`
        plain      -> ParseWord(word)                a cheap yes/no
        explain    -> TraceWordXml(word, None)       slowest; no hypothesis

    `morphs` ON A NON-RESTRICTED LEVEL IS A USAGE ERROR. Accepting and
    ignoring it would silently discard the caller's hypothesis and hand back
    an unrestricted answer that looks like a restricted one -- the caller
    would read a full-search result as confirmation of their decomposition.
    Refusing costs one round trip and names the level they wanted.

    `project_name` is optional here and falls back to the session, matching
    every other project-touching tool (`GrammarHealthInput`, `RunModuleInput`).
    The contract calls it required in the sense that the call cannot proceed
    without one: the handler refuses with `project_name_required` when neither
    the argument nor the session supplies it.
    """
    word: str = Field(
        description="The surface form to parse. One wordform, not a phrase."
    )
    level: Literal["restricted", "plain", "explain"] = Field(
        description="restricted: trace only the decomposition in `morphs` (fastest; "
                    "use when you have a hypothesis). plain: yes/no, no reason "
                    "(cheapest). explain: full trace with no hypothesis (slowest, "
                    "and the one under a budget cap -- use it only when you have no "
                    "decomposition to propose)."
    )
    morphs: Optional[List[MorphSpec]] = Field(
        default=None,
        description="The proposed decomposition, in order. REQUIRED and non-empty "
                    "for level='restricted'; a usage error on any other level."
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Name of the FieldWorks project whose worker parses this word. "
                    "Uses the session value if set by start()."
    )
    bound_seconds: Optional[float] = Field(
        default=None, ge=1.0, le=600.0,
        description="Measure this word instead of just parsing it: run it to "
                    "completion in a worker of its own, stopped at this many "
                    "seconds. Reports wall-clock time, and a word stopped at the "
                    "bound is a result, not an error. level='plain' only."
    )

    @model_validator(mode="after")
    def _bound_only_on_plain(self) -> "TryWordInput":
        """The measurement asks "how long does ONE word take", nothing else.

        A trace level would measure the tracer as well as the grammar, and a
        restricted one a narrowed search -- neither is the cost of the
        grammar on this word. Refused rather than ignored, for the reason
        `morphs` is.
        """
        if self.bound_seconds is not None and self.level != "plain":
            raise ValueError(
                "bound_seconds measures one word at level='plain'; you passed "
                "level=" + repr(self.level) + ". A trace would time the tracer "
                "as well as the grammar. Use level='plain' to measure."
            )
        return self

    @model_validator(mode="after")
    def _morphs_match_level(self) -> "TryWordInput":
        """Tie `morphs` to `level`, in both directions, and fill `position`.

        The empty list is refused for `restricted` rather than read as "no
        restriction". `TraceWordXml` reads an empty selection as "admit
        nothing" -- the opposite -- and the setting outlives the call, so a
        widening here would not even stay inside this request
        (contracts/tools.md, "Never widen"; spec.md Delta 2).
        """
        if self.level == "restricted":
            if not self.morphs:
                raise ValueError(
                    "level='restricted' traces a decomposition, so `morphs` is "
                    "required and must be non-empty. An empty selection is not "
                    "'no restriction' -- the parser reads it as 'admit nothing'. "
                    "Use level='explain' to trace without a hypothesis."
                )
            for index, morph in enumerate(self.morphs):
                if morph.position is None:
                    morph.position = index
        elif self.morphs is not None:
            raise ValueError(
                "`morphs` is only meaningful at level='restricted'; you passed "
                "level=" + repr(self.level) + ". Accepting it here would discard "
                "your decomposition and return an unrestricted answer that looks "
                "like a restricted one. Use level='restricted' to trace it, or "
                "drop `morphs`."
            )
        return self


class ParseStatusInput(BaseModel):
    """Ask after a parse run by its handle (parser-check CP2b, FR-033).

    Read-only, and one field by design. Asking about a run that has already
    failed or been cancelled is a SUCCESSFUL query, not a failed request --
    the only refusal this tool issues is `parse_run_not_found`, for a handle
    that corresponds to no run at all (contracts/tools.md).
    """
    run_id: str = Field(
        description="The handle returned when a parse outlived the grace window."
    )


class ParseCancelInput(BaseModel):
    """Cancel a parse run by its handle (parser-check CP4, FR-034; M-3).

    A new tool rather than an action on `flextools_parse_status`, whose
    read-only annotation callers can see and rely on. Cancelling writes
    nothing to the project: the run stops at its next word boundary, and
    anything a FILING run already filed stays filed.
    """
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(
        description="The run's handle, as flextools_parse_text or flextools_try_word "
                    "returned it."
    )


class ParseReleaseInput(BaseModel):
    """Release this server's own idle parse worker(s) for a project (#223).

    `flextools_try_word` / `flextools_parse_text` leave a shared read
    worker running until its idle timeout, holding `<project>.fwdata.lock`
    until then. `flextools_run_module`'s write gate already releases it
    automatically when a write needs the lock -- this tool exists for the
    case nothing else prompts that release: dropping the lock on purpose,
    without also submitting a write. Refuses rather than killing a live
    run; a no-op success if no worker is running at all.
    """
    model_config = ConfigDict(extra="forbid")

    project_name: Optional[str] = Field(
        default=None,
        description="Name of the FieldWorks project. Uses session value if set by start()."
    )


# ============================================================
# Parse scope (parser-check CP3, US1; data-model.md sections 1-2)
# ============================================================

class ParseScope(BaseModel):
    """What the caller asked to parse, before resolution (data-model.md s.1).

    Declared here rather than in `server/parse/scope.py` for the same reason
    `MorphSpec` is: it is the shape a caller writes, validated at the tool
    boundary before any resolver runs, and `models.py` must not import the
    parse package.

    `limit` truncates AFTER ordering (FR-009). A limit applied first would
    make two runs over the same corpus in a different source order resolve
    to different words -- and therefore not be comparable.

    `vernacular_ws` names the writing system the words are read in. It is
    optional and defaults to the project's default vernacular writing system,
    but it is always resolved to an EXPLICIT one and recorded: on
    IndonesianHC-Complete every wordform of one text reads back as "" at the
    default vernacular WS while being perfectly present in another
    (specs/parser-check-cp3/live-note-fr001-fr003.md). The field is how a
    caller reaches that text at all.
    """
    model_config = ConfigDict(extra="forbid")

    kind: Literal["all_texts", "genre", "text", "words"] = Field(
        description="all_texts: every text in the project. genre: texts tagged "
                    "with a genre (by name or abbreviation, any of a text's "
                    "genres). text: one text, by name or id. words: an explicit "
                    "word list."
    )
    value: Optional[Any] = Field(
        default=None,
        description="The genre string, the text name or id, or the list of words. "
                    "Omit for all_texts."
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Keep at most this many words. Applied after ordering by "
                    "descending occurrence then alphabetically."
    )
    vernacular_ws: Optional[str] = Field(
        default=None,
        description="Language tag of the vernacular writing system to read words "
                    "in. Defaults to the project's default vernacular writing system."
    )

    @model_validator(mode="after")
    def _value_matches_kind(self) -> "ParseScope":
        if self.kind == "all_texts":
            if self.value is not None:
                raise ValueError("kind='all_texts' takes no value.")
        elif self.kind in ("genre", "text"):
            if self.value is None or str(self.value).strip() == "":
                raise ValueError(f"kind={self.kind!r} needs a non-empty value.")
            self.value = str(self.value).strip()
        else:  # words
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("kind='words' needs a non-empty list of words.")
            if not all(isinstance(w, str) for w in self.value):
                raise ValueError("kind='words' takes a list of strings.")
        return self


class ParseTextInput(BaseModel):
    """Submit a batch parse over a resolved scope (parser-check CP3, US2),
    and -- from CP4 -- file its results into the project (FR-001).

    Scope kind and value, an optional word limit, an optional writing system,
    an optional project name, and CP4's three filing arguments: `apply`,
    `confirmed`, `plan_id`. NOTHING ELSE. In particular there is no argument
    that skips or pre-answers the confirmation, lowers the backup rung, or
    overrides the session's write permission (FR-004, SC-008, R-15);
    `tests/test_filing_bypass_surface.py` enumerates this schema and fails
    if a bypass-shaped name ever appears. `extra="forbid"` is what makes
    "absent" enforceable -- a caller who guesses at a `force` or `write`
    flag is refused, not silently ignored.

    `apply` absent or false is CP3's read-only batch, exactly (FR-001).
    `confirmed` and `plan_id` mean something only with `apply=true`; a
    read-only request cannot carry a confirmation, so they are refused
    without it.
    """
    model_config = ConfigDict(extra="forbid")

    scope_kind: Literal["all_texts", "genre", "text", "words"] = Field(
        description="all_texts: every text. genre: texts carrying a genre (name or "
                    "abbreviation, any of a text's genres). text: one text, by name "
                    "or id. words: an explicit word list."
    )
    scope_value: Optional[Any] = Field(
        default=None,
        description="The genre string, the text name or id, or the list of words. "
                    "Omit for all_texts."
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Parse at most this many words, keeping the most frequent "
                    "(applied after ordering)."
    )
    vernacular_ws: Optional[str] = Field(
        default=None,
        description="Language tag of the vernacular writing system to read words "
                    "in. Defaults to the project's default vernacular writing system."
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Name of the FieldWorks project. Uses the session value if set "
                    "by start()."
    )
    apply: bool = Field(
        default=False,
        description="File the parser's results into the project, as FLEx's Parse Words "
                    "in Text does. The first call returns confirmation_required with a "
                    "mutation plan and a plan_id, and writes nothing. Requires a session "
                    "started with write_enabled=true. Filing cannot be undone."
    )
    confirmed: bool = Field(
        default=False,
        description="Resubmit flag, meaningful only with apply=true and the plan_id the "
                    "preview returned. A confirmation for a plan that has since changed "
                    "gets a new preview instead of filing."
    )
    plan_id: Optional[str] = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
        description="The plan_id from the preview this call confirms (64 lowercase hex). "
                    "Only with apply=true."
    )

    @model_validator(mode="after")
    def _scope_is_valid(self) -> "ParseTextInput":
        """Validate kind/value together at the tool boundary, via ParseScope."""
        self.to_scope()
        return self

    @model_validator(mode="after")
    def _confirmation_needs_apply(self) -> "ParseTextInput":
        """A read-only request cannot carry a confirmation (contracts row 0)."""
        if not self.apply and (self.confirmed or self.plan_id is not None):
            raise ValueError(
                "confirmed and plan_id are meaningful only with apply=true: they "
                "confirm a filing preview, and a read-only parse files nothing."
            )
        return self

    def to_scope(self) -> ParseScope:
        return ParseScope(
            kind=self.scope_kind,
            value=self.scope_value,
            limit=self.limit,
            vernacular_ws=self.vernacular_ws,
        )


#: The log sections, verbatim from contracts/tools.md section 1: CP3's seven,
#: plus CP4's additive `deletions` (a filing run's pre-deletion captures).
PARSE_LOG_SECTIONS = (
    "summary", "config_generation", "hc_stdout", "hc_output", "trace", "words", "results",
    "deletions",
)


class ParseLogInput(BaseModel):
    """Read a parse run back from its artifact (parser-check CP3, US3; FR-028).

    Read-only, and it never touches the engine (FR-024): every section is
    served from the run directory on disk, so a run from an earlier server
    process is as readable as one from this one.
    """
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="The run's handle, as flextools_parse_text or "
                                    "flextools_try_word returned it.")
    section: Literal[
        "summary", "config_generation", "hc_stdout", "hc_output", "trace", "words", "results",
        "deletions",
    ] = Field(
        default="summary",
        description="summary: stage, progress, fingerprint, counters, and for a batch run "
                    "the report (signals, oracle, pairings, clusters, projections); for a "
                    "filing run also its filing block (counts, projected beside actual "
                    "deletions, backup, overwritten disapprovals). words: the resolved "
                    "word list. results: one line per completed word. trace: a drill-down "
                    "trace (pass trace_index). deletions: a filing run's pre-deletion "
                    "captures (not applicable to read-only runs). config_generation / "
                    "hc_stdout / hc_output belong to the sandbox spine and are reported as "
                    "not applicable to in-process runs."
    )
    offset: int = Field(default=0, ge=0, description="First item to return (words, results).")
    limit: int = Field(default=50, ge=1, le=500, description="Items per page (words, results).")
    trace_index: Optional[int] = Field(
        default=None, ge=0,
        description="Which word's trace to read (its index in the run). Defaults to the "
                    "first trace the run holds."
    )
    max_trace_chars: int = Field(
        default=20000, ge=1000, le=200000,
        description="Cap on how much of a raw trace is returned inline."
    )
    drill_down_cap: Optional[int] = Field(
        default=None, ge=10, le=20,
        description="Your drill-down cap for this session: how many words, from 10 to "
                    "20, the batch report may recommend tracing in total. Chosen once "
                    "per session; nothing is ever traced automatically (summary of a "
                    "batch run only)."
    )


class ParseDiffInput(BaseModel):
    """Compare two batch runs (parser-check CP3, US4; FR-012, FR-030).

    Read-only, and it never touches the engine (FR-024): both runs are read
    from their records on disk.
    """
    model_config = ConfigDict(extra="forbid")

    baseline_run_id: str = Field(description="The earlier run -- usually the one "
                                             "before your grammar edit.")
    current_run_id: str = Field(description="The later run -- usually the one after it.")
    force: bool = Field(
        default=False,
        description="Compare even though the two runs' scopes differ. The comparison "
                    "then covers only the words both runs share, and says so."
    )


# ============================================================
# Sandbox spine (parser-check CP5; contracts/tools.md section 2)
# ============================================================

class ParseSandboxInput(BaseModel):
    """Parse against an exported or copied grammar with the stand-alone `hc`
    tool (parser-check CP5, FR-034). The live project is never opened for
    writing.

    One tool, five actions. `words` / `word_file` belong to `parse` alone,
    and exactly one of them is required there; on any other action they are
    refused rather than ignored, so a caller who thinks they are parsing
    while creating a sandbox finds out. `extra="forbid"` refuses guessed
    arguments the same way. Name, existence, corpus and disk-space checks are
    NOT done here -- they are `parse_sandbox_refused` refusals from the
    handler (contracts/tools.md section 3), because they depend on the disk.
    """
    model_config = ConfigDict(extra="forbid")

    action: Literal["parse", "create_sandbox", "seed_corpus", "run_corpus", "list"] = Field(
        default="parse",
        description="parse: parse words against a sandbox or the project's cached config. "
                    "create_sandbox: export the project's grammar into a new named sandbox. "
                    "seed_corpus: save a completed sandbox parse run's words as a named "
                    "corpus. run_corpus: parse a saved corpus. list: list sandboxes and "
                    "corpora."
    )
    project_name: Optional[str] = Field(
        default=None,
        description="Name of the FieldWorks project. Uses the session value if set "
                    "by start()."
    )
    words: Optional[Union[List[str], str]] = Field(
        default=None,
        description="The words to parse (action='parse' only). A string is split on "
                    "commas and whitespace; a list is taken item by item. Give this or "
                    "word_file, not both."
    )
    word_file: Optional[str] = Field(
        default=None,
        description="Path to a UTF-8 file, one word per line (action='parse' only). "
                    "Refused if it is inside a project folder. Give this or words, not both."
    )
    sandbox: Optional[str] = Field(
        default=None,
        description="The sandbox to parse against (parse, run_corpus). Omit to use the "
                    "project's cached config. For create_sandbox, the NEW sandbox's name."
    )
    corpus: Optional[str] = Field(
        default=None,
        description="The corpus name: the new one for seed_corpus, the one to parse for "
                    "run_corpus."
    )
    from_run_id: Optional[str] = Field(
        default=None,
        pattern=r"^[0-9a-f]{32}$",
        description="seed_corpus only: the completed sandbox parse run (32 lowercase hex) "
                    "whose words become the corpus."
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        description="Parse at most this many words (action='parse'), applied after "
                    "ordering."
    )
    timeout_seconds: int = Field(
        default=600,
        ge=10,
        le=86400,
        description="Wall-clock bound on the hc run, in seconds (parse, run_corpus). "
                    "10 to 86400."
    )

    @model_validator(mode="after")
    def _words_match_action(self) -> "ParseSandboxInput":
        """`parse` takes exactly one of words / word_file; nothing else takes either."""
        given = [n for n in ("words", "word_file") if getattr(self, n) is not None]
        if self.action == "parse":
            if len(given) != 1:
                raise ValueError(
                    "action='parse' needs exactly one of `words` or `word_file`; you "
                    "passed " + ("both" if given else "neither") + "."
                )
        elif given:
            raise ValueError(
                "`" + "` and `".join(given) + "` " + ("is" if len(given) == 1 else "are")
                + " meaningful only with action='parse'; you passed action="
                + repr(self.action) + ". Accepting it here would discard your words "
                "without parsing them."
            )
        return self


class ResolvedScope(BaseModel):
    """A scope after resolution: a definite, ordered word list (data-model.md s.2).

    `count_before_limit` is the de-duplicated count BEFORE truncation, and is
    what the fingerprint records as `word_count` -- a truncated run and a full
    one over the same corpus must be recognisably the same corpus.

    `never_tokenized_text_ids` carries the FR-002 distinguishing read: texts
    with structure but no unique wordforms. Not an assertion that those texts
    contain no words -- that has not been shown (FR-001 is open).

    `unreadable_wordform_count` counts wordforms present in a selected text
    whose form is empty at `vernacular_ws`. They are skipped, never emitted as
    "" -- after NFC de-duplication a text of such wordforms would otherwise
    become one empty "word", indistinguishable from a real one-word text.

    Carries no live data-model object (FR-021): identifiers and text only.
    """
    model_config = ConfigDict(extra="forbid")

    scope_kind: str
    scope_value: Optional[Any] = None
    #: Session-scoped handles (hvos), for addressing a text in THIS session
    #: -- e.g. `kind="text", value="<id>"`. Not durable: liblcm renumbers
    #: hvos on every cache load (issue #103).
    text_ids: List[int] = Field(default_factory=list)
    #: The same texts' GUIDs, in the same order. Durable, and what the scope
    #: fingerprint records, so a comparison across two sessions does not
    #: refuse merely because the cache was reloaded in between.
    text_guids: List[str] = Field(default_factory=list)
    words: List[str] = Field(default_factory=list)
    count_before_limit: int = 0
    limit: Optional[int] = None
    truncated: bool = False
    vernacular_ws: str
    never_tokenized_text_ids: List[int] = Field(default_factory=list)
    unreadable_wordform_count: int = 0
    notes: List[str] = Field(default_factory=list)
