#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #54: Pydantic response envelope models for FlexToolsMCP.

Provides:
- BaseEnvelope: common _contract / status / op_id fields
- Per-tool *Success models (extra="ignore" for forward-compat)
- RejectionEnvelope with a discriminated union keyed on error_code
- 36 per-code detail models (12 existing + 4 folded in + nested_unit_of_work
  + hvo_literal_write_risk + invalid_api_mode + 4 parser-check CP1 codes
  + 3 parser-check CP2b codes: parse_morph_unresolved, parse_run_not_found,
  parse_job_cancelled
  + 5 parser-check CP3 codes: parse_scope_empty, parse_scope_ambiguous,
  parse_scope_mismatch, parser_timeout, parser_job_failed
  + internal_error (#89)
  + 2 parser-check CP4 codes: parser_filing_in_progress, grammar_load_unclean
  + 2 parser-check CP5 codes: parser_config_failed, parse_sandbox_refused)

All field aliases reference KEY_* constants from response_keys so renames
propagate automatically.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

try:
    from .response_keys import (
        KEY_STATUS, KEY_CONTRACT, KEY_OP_ID, KEY_ERROR_CODE, KEY_MESSAGE, KEY_HINT,
        KEY_ERROR, KEY_AUTO_FIXES_APPLIED, KEY_AUTO_FIX_NOTE,
        KEY_AUTO_DISCOVERED, KEY_INLINE_DISCOVERY, KEY_DISCOVERY_NOTE,
        KEY_DIAGNOSTIC_REPORT,
        KEY_DISCOVERY_REDIRECT, KEY_CAPABILITY_SUGGESTIONS, KEY_EXECUTED,
    )
except ImportError:
    from server.response_keys import (
        KEY_STATUS, KEY_CONTRACT, KEY_OP_ID, KEY_ERROR_CODE, KEY_MESSAGE, KEY_HINT,
        KEY_ERROR, KEY_AUTO_FIXES_APPLIED, KEY_AUTO_FIX_NOTE,
        KEY_AUTO_DISCOVERED, KEY_INLINE_DISCOVERY, KEY_DISCOVERY_NOTE,
        KEY_DIAGNOSTIC_REPORT,
        KEY_DISCOVERY_REDIRECT, KEY_CAPABILITY_SUGGESTIONS, KEY_EXECUTED,
    )

try:
    from ..response_utils import CONTRACT_VERSION
except (ImportError, ValueError):
    from response_utils import CONTRACT_VERSION


# ---------------------------------------------------------------------------
# Base envelope
# ---------------------------------------------------------------------------

class BaseEnvelope(BaseModel):
    """Common fields present on every tool response (success and error)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    status: Literal["ok", "error"] = Field(alias=KEY_STATUS)
    contract: str = Field(alias=KEY_CONTRACT, default=CONTRACT_VERSION)
    op_id: Optional[str] = Field(alias=KEY_OP_ID, default=None)


# ---------------------------------------------------------------------------
# Success envelopes (per-tool, extra="ignore" for forward-compat)
# ---------------------------------------------------------------------------

class RunModuleSuccess(BaseEnvelope):
    """Successful run_module response envelope."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    status: Literal["ok", "error"] = Field(alias=KEY_STATUS, default="ok")
    # Issue #46: auto-fix fields (None when no auto-fix was applied)
    auto_fixes_applied: Optional[list] = Field(
        alias=KEY_AUTO_FIXES_APPLIED, default=None,
        description="List of auto-fix records applied before execution (issue #46). "
                    "None when no auto-fix was attempted."
    )
    auto_fix_note: Optional[str] = Field(
        alias=KEY_AUTO_FIX_NOTE, default=None,
        description="Actionable note about applied auto-fixes including source file:line "
                    "references and a reminder to update the source file (issue #46)."
    )
    # Issue #47: auto-discovery fields (None when no auto-discovery occurred)
    auto_discovered: Optional[List[str]] = Field(
        alias=KEY_AUTO_DISCOVERED, default=None,
        description="Entity names auto-discovered on this READ-ONLY run (issue #47). "
                    "These will re-trigger the undiscovered_entity gate on the first WRITE run."
    )
    inline_discovery: Optional[Dict[str, Any]] = Field(
        alias=KEY_INLINE_DISCOVERY, default=None,
        description="Inline API docs for auto-discovered entities (issue #47). "
                    "Same compact shape as _inline_discovery from rejection payloads."
    )
    discovery_note: Optional[str] = Field(
        alias=KEY_DISCOVERY_NOTE, default=None,
        description="Advisory note about auto-discovered entities (issue #47). "
                    "Explains write-gate re-trigger semantics."
    )
    # Diagnostic-report feature (CP3, spec section 10): additive advisory
    # block attached when this success close resolves a same-turn reportable
    # failure (spec section 6.2 workaround-taken signal) and the underlying
    # inconsistency signature has not been dedupe-suppressed (section 6.3-6.4).
    # None when no offer fires this close. Same additive-optional pattern as
    # the #46/#47 fields above -- no contract version bump (resolved Q5).
    diagnostic_report: Optional[Dict[str, Any]] = Field(
        alias=KEY_DIAGNOSTIC_REPORT, default=None,
        description="Diagnostic-report offer (CP3): {signature, title, summary, "
                    "report_path, transports, likely_contains_lexical_data, error_code}. "
                    "The MCP never sends this itself -- transports are prepared strings "
                    "only; a human must take the send action."
    )
    # Issue #80: graceful discovery-redirect fields. Present on a status:"ok"
    # response that did NOT execute -- a gentle nudge to apply the inlined
    # discovery and resubmit, so a turn-1/turn-2 run attempt is not an error.
    executed: Optional[bool] = Field(
        alias=KEY_EXECUTED, default=None,
        description="Issue #80: False when the response is a graceful discovery "
                    "redirect (code was NOT run). Absent/None on normal executed runs."
    )
    discovery_redirect: Optional[Dict[str, Any]] = Field(
        alias=KEY_DISCOVERY_REDIRECT, default=None,
        description="Issue #80: structured advisory block on a non-executed redirect: "
                    "{needs_resubmit, reason, undiscovered, prefer_tools}. The model should "
                    "apply the inlined discovery/capability suggestions and resubmit."
    )
    capability_suggestions: Optional[List[Dict[str, Any]]] = Field(
        alias=KEY_CAPABILITY_SUGGESTIONS, default=None,
        description="Issue #80: search_by_capability-backed method hits for guessed "
                    "methods/capabilities, when the entity-shaped inline docs alone "
                    "aren't the right lookup."
    )


class GetObjectApiSuccess(BaseEnvelope):
    """Successful get_object_api response envelope."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    status: Literal["ok", "error"] = Field(alias=KEY_STATUS, default="ok")


class SearchByCapabilitySuccess(BaseEnvelope):
    """Successful search_by_capability response envelope."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    status: Literal["ok", "error"] = Field(alias=KEY_STATUS, default="ok")


# ---------------------------------------------------------------------------
# Per-code detail models (extra="forbid" -- tightest coupling for rejection)
# ---------------------------------------------------------------------------

class SyntaxErrorDetail(BaseModel):
    """Detail payload for syntax_error rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["syntax_error"] = "syntax_error"
    line: Optional[int] = None
    col: Optional[int] = None
    offending_token: Optional[str] = None
    parser_message: Optional[str] = None


class ServerStateErrorDetail(BaseModel):
    """Detail payload for server_state_error rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["server_state_error"] = "server_state_error"
    server_state: Any = None
    component: Optional[str] = None
    state_description: Optional[str] = None


class InternalErrorDetail(BaseModel):
    """Detail payload for internal_error (unhandled handler exceptions, issue #89)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["internal_error"] = "internal_error"
    error_type: Optional[str] = None
    traceback: Optional[str] = None
    tool: Optional[str] = None


class PartialModuleStructureDetail(BaseModel):
    """Detail payload for partial_module_structure rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["partial_module_structure"] = "partial_module_structure"
    missing_elements: List[str] = Field(default_factory=list)
    has_main: Optional[bool] = None
    has_docs_dict: Optional[bool] = None
    has_flextools_binding: Optional[bool] = None


class UnprotectedWritesDetail(BaseModel):
    """Detail payload for unprotected_writes rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["unprotected_writes"] = "unprotected_writes"
    mutating_calls: Optional[List[Any]] = None
    write_certification_required: Optional[bool] = None


class CastingIssueItem(BaseModel):
    """Single item in the casting_issues list."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    line: int
    base_type: Optional[str] = None
    concrete_type: Optional[str] = None
    correct_cast_expression: Optional[str] = None
    # Existing keys preserved for compat
    property: Optional[str] = None
    pattern: Optional[str] = None
    rewrite: Optional[str] = None
    imports_needed: Optional[List[str]] = None
    cast_interface: Optional[str] = None
    fix: Optional[str] = None
    severity: Optional[str] = None


class CastingIssuesDetectedDetail(BaseModel):
    """Detail payload for casting_issues_detected rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["casting_issues_detected"] = "casting_issues_detected"
    casting_issues: List[Any] = Field(default_factory=list)
    polymorphic_collections: Optional[Any] = None
    general_guidance: Optional[Any] = None


class ApiDiscoveryRequiredDetail(BaseModel):
    """Detail payload for api_discovery_required rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["api_discovery_required"] = "api_discovery_required"
    detected_candidates: List[str] = Field(default_factory=list)
    session: Optional[Any] = None
    missing_entity: Optional[str] = None
    suggested_tool_call: Optional[str] = None


class UndiscoveredEntityDetail(BaseModel):
    """Detail payload for undiscovered_entity rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["undiscovered_entity"] = "undiscovered_entity"
    undiscovered: Optional[Any] = None
    imported_undiscovered: Optional[List[str]] = None
    session: Optional[Any] = None
    closest_matches: Optional[List[str]] = None


class UndefinedVariablesDetail(BaseModel):
    """Detail payload for undefined_variables rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["undefined_variables"] = "undefined_variables"
    undefined_vars: List[str] = Field(default_factory=list)
    guidance: Optional[str] = None


class MissingImportsDetail(BaseModel):
    """Detail payload for missing_imports rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["missing_imports"] = "missing_imports"
    missing_imports: List[str] = Field(default_factory=list)
    api_mode: str = ""
    guidance: Optional[str] = None


class WrongLibraryImportsDetail(BaseModel):
    """Detail payload for wrong_library_imports rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["wrong_library_imports"] = "wrong_library_imports"
    wrong_imports: List[str] = Field(default_factory=list)
    api_mode: str = ""
    affected_symbols: Optional[List[str]] = None
    guidance: Optional[str] = None


class InvalidApiModeDetail(BaseModel):
    """Detail payload for invalid_api_mode rejections (issue #164)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["invalid_api_mode"] = "invalid_api_mode"
    allowed_modes: List[str] = Field(default_factory=list)
    received: Optional[Any] = None
    hint: Optional[str] = None


class InvalidApiChainDetail(BaseModel):
    """Detail payload for invalid_api_chain rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["invalid_api_chain"] = "invalid_api_chain"
    issues: List[Any] = Field(default_factory=list)
    guidance: Optional[str] = None


class NestedUnitOfWorkDetail(BaseModel):
    """Detail payload for nested_unit_of_work rejections (issue #92 follow-up,
    re-derived for issue #144).

    Fires when write-enabled code opens its own raw liblcm UnitOfWork
    (UndoableUnitOfWorkHelper/NonUndoableUnitOfWorkHelper, or a bare
    IActionHandler.BeginUndoTask()/BeginNonUndoableTask() call), which would
    nest inside whichever unit of work is already open at that point --
    the runner's session-long non-undoable task on flexicon builds without
    the "per-operation-uow" capability (defence-in-depth for unsupported
    installs under the declared pyflexicon floor; surfaced via
    run_module's `undoable` / `timestamps_updated` flags -- issue #153),
    or flexicon's own per-operation task on builds that have it -- and
    discard the writes it was holding (the whole run's, or just that one
    operation's, respectively). See validators.detect_nested_unit_of_work().
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["nested_unit_of_work"] = "nested_unit_of_work"
    constructs: List[Any] = Field(default_factory=list)
    guidance: Optional[str] = None


class ProjectLockedDetail(BaseModel):
    """Detail payload for project_locked rejections.

    Issue #93 CP3 (T3.5) / CP4 (T4.1): the mere existence of a .fwdata.lock
    file is no longer the reason for this rejection -- it is now raised only
    for the two verdicts a write genuinely cannot survive
    (``open_exclusive`` and ``held_by_other``). The probe facts that produced
    the verdict travel with the payload so the caller can tell "FLEx has it
    and sharing is off" (fixable by the user in 20 seconds) apart from
    "another python process has it" (not fixable by toggling a checkbox).

    The model is ``extra="forbid"``, so these fields had to exist before
    the handler could send them.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["project_locked"] = "project_locked"
    guidance: str = ""
    lock_file_path: Optional[str] = None
    # project_access.probe_project_access() facts behind the refusal.
    verdict: Optional[str] = None
    sharing_enabled: Optional[bool] = None
    holder_pid: Optional[int] = None
    holder_process: Optional[str] = None
    remedy: Optional[str] = None


class ProjectDriveUnavailableDetail(BaseModel):
    """Detail payload for project_drive_unavailable rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["project_drive_unavailable"] = "project_drive_unavailable"
    attempted_path: Optional[str] = None
    hint: Optional[str] = None


class ProjectPathMismatchDetail(BaseModel):
    """Detail payload for project_path_mismatch rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["project_path_mismatch"] = "project_path_mismatch"
    attempted_path: Optional[str] = None
    discovered_at: Optional[str] = None
    hint: Optional[str] = None


class ProjectNotFoundDetail(BaseModel):
    """Detail payload for project_not_found rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["project_not_found"] = "project_not_found"
    attempted_path: Optional[str] = None
    hint: Optional[str] = None
    # recovery action: always "list_projects"
    recovery: Optional[str] = "list_projects"


class RuntimeErrorDetail(BaseModel):
    """Detail payload for runtime_error rejections (post-exec failures)."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["runtime_error"] = "runtime_error"
    stderr: Optional[str] = None
    traceback: Optional[str] = None
    exit_code: Optional[int] = None
    error_type: Optional[str] = None




class HvoLiteralWriteRiskDetail(BaseModel):
    """Detail payload for hvo_literal_write_risk rejections (issue #103).

    Fires when write-enabled code passes a bare integer literal to an
    `*_or_hvo` parameter. An hvo is a session-scoped handle that liblcm
    renumbers on every cache load, so a literal carried across run_module
    calls silently resolves to a real but DIFFERENT object -- the write
    lands on the wrong target with no exception. Only GUIDs are stable;
    re-resolve with project.Object(guid_str). See
    validators.detect_hvo_literal_args().
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["hvo_literal_write_risk"] = "hvo_literal_write_risk"
    findings: List[Any] = Field(default_factory=list)
    next_steps: List[Any] = Field(default_factory=list)


class ParserEngineMismatchDetail(BaseModel):
    """Detail payload for parser_engine_mismatch rejections (parser-check CP1).

    Raised by check_active_parser(project, supported_engines=("HC",)), called
    as the first statement of each spine-executing handler, before any
    HCParser or config-export construction. See contracts/error-codes.md.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_engine_mismatch"] = "parser_engine_mismatch"
    configured_engine: str
    supported_engines: List[str]
    hint: str


class ParserCoreMissingDetail(BaseModel):
    """Detail payload for parser_core_missing rejections (parser-check CP1).

    ``signal`` is a closed enum shared with the health block's
    ``read.reason`` / ``write.reason`` -- do not rename, recase or extend.
    ``detected_version`` is reported and never compared against a floor.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_core_missing"] = "parser_core_missing"
    signal: Literal["absent", "foreign_install", "incompatible_surface", "load_failed"]
    expected_path: str
    detected_version: Optional[str] = None
    missing_members: List[str]
    lcmodel_install_path: Optional[str] = None
    install_hint: str
    load_error: Optional[str] = None


class ParserAgentMissingDetail(BaseModel):
    """Detail payload for parser_agent_missing rejections (parser-check CP1).

    Raised instead of propagating KeyNotFoundException when a handler would
    resolve the HermitCrab agent via LangProject.DefaultParserAgent. The read
    spine is unaffected -- flextools_try_word never resolves an agent.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_agent_missing"] = "parser_agent_missing"
    agent_guid: str
    agent_name: Literal["HermitCrab"]
    active_engine: str
    probe_source: Literal["bootstrap_absent", "lookup_failed"]
    hint: str


class ParserToolMissingDetail(BaseModel):
    """Detail payload for parser_tool_missing rejections (parser-check CP1).

    ``component`` is a closed enum shared with flextools_health's
    ``sandbox.components[].component`` -- the two components fail
    independently, which is why health reports an array while this names one.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_tool_missing"] = "parser_tool_missing"
    component: Literal["hc", "GenerateHCConfig.exe"]
    expected_path: str
    install_hint: str


class ParseMorphCandidate(BaseModel):
    """One entry a piece of a decomposition might have meant (CP2b).

    `msa_hvo` being null IS the `no_msa` signal -- data-model.md section 4
    says so explicitly rather than leaving it to be inferred. The field is
    not omitted in that case and not filled with a sentinel: null is the
    fact, and echoing it lets the caller see WHICH candidate carried no
    analysis rather than only that something did.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    headword: str
    sense: Optional[str] = None
    msa_hvo: Optional[int] = None
    entry_hvo: int


class ParseMorphUnresolvedDetail(BaseModel):
    """Detail payload for parse_morph_unresolved rejections (parser-check CP2b).

    Raised when any piece of a caller's proposed decomposition does not
    resolve to a usable analysis. **No parse runs** for such a request
    (FR-019, SC-005, asserted as a negative).

    FIVE FIELDS, IN THIS EXACT ORDER: ``morph``, ``position``,
    ``resolved_to``, ``candidates``, ``hint``. The order was the subject of
    a three-way agreement check during CP2's cycle 3; do not reorder,
    rename, recase or pluralize. ``tests/test_response_contract.py`` asserts
    the order, not merely the membership.

    ``resolved_to`` is a CLOSED enum and its three members are kept distinct
    on purpose: ``none`` means fix the spelling, ``ambiguous`` means pick
    the homograph, ``no_msa`` means the entry carries no analysis and needs
    work. Collapsing them reproduces the silent-narrowing failure the
    requirement exists to prevent.

    ``candidates`` carries the REJECTED options too. A refusal naming no
    candidates can only be retried; one that names them can be acted on.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parse_morph_unresolved"] = "parse_morph_unresolved"
    morph: Optional[Any] = None
    position: Optional[int] = None
    resolved_to: Literal["none", "ambiguous", "no_msa"]
    candidates: List[ParseMorphCandidate] = Field(default_factory=list)
    hint: str


class ParseRunNotFoundDetail(BaseModel):
    """Detail payload for parse_run_not_found rejections (parser-check CP2b).

    The ONLY refusal ``flextools_parse_status`` issues (FR-035). Asking
    about a run that has already failed or been cancelled is a SUCCESSFUL
    query -- a dead run is a fact about the run, not a fault in the request
    -- so neither of those reaches this model.

    ``available_runs`` is what makes the refusal actionable. A handle is an
    opaque 32-character string; told only "no such run", a caller has
    nothing to compare theirs against and no way to tell a typo from a run
    the server has forgotten.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parse_run_not_found"] = "parse_run_not_found"
    run_id: str
    available_runs: List[str] = Field(default_factory=list)
    hint: str


class ParseJobCancelledDetail(BaseModel):
    """Detail payload for parse_job_cancelled rejections (parser-check CP2b).

    Raised when a request attaches to a run that is already in a terminal
    state -- a second cancel, or a word submitted against a run that has
    stopped (FR-036).

    NOT RAISED BY ``flextools_parse_status``. Asking after a cancelled run
    is a successful query reporting ``words_completed`` and the stage it was
    in when it stopped; this code fires when something tries to ACT on a run
    that has already ended. Both directions get a test
    (``tests/test_parse_status_handler.py``), because the asymmetry is the
    part of FR-033/FR-036 that is easy to implement backwards.

    ``words_completed`` and ``state_at_cancel`` ride on the refusal because
    the partial results survive the cancellation (FR-029) and the caller
    needs to know how much of the work is readable.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parse_job_cancelled"] = "parse_job_cancelled"
    run_id: str
    words_completed: int
    state_at_cancel: str
    hint: str


# ---------------------------------------------------------------------------
# parser-check CP3 -- five additive refusal codes
#
# Field ORDER below is transcribed from specs/parser-check-cp3/contracts/
# tools.md section 2 and is asserted byte-for-byte by
# tests/test_parser_error_models.py. A reordered model must fail that test:
# the order is what a caller reads a refusal in, and reordering it is a
# silent presentation change to a contract that claims to be additive.
#
# All five are ADDITIVE. No existing code changed shape and the contract
# version stays tool-responses/1.0 (FR-059).
# ---------------------------------------------------------------------------

class ParseScopeEmptyDetail(BaseModel):
    """Detail payload for parse_scope_empty rejections (parser-check CP3).

    Raised when a scope resolves to no texts at all -- a genre nothing is
    tagged with, or a named text that is not there.

    NOT RAISED FOR A NEVER-TOKENIZED TEXT (FR-002). A text with structure but
    no unique wordforms is a different situation with a different remedy, and
    it gets its own conservative wording rather than this code. The
    distinction matters because this code's wording asserts that nothing
    matched, and a text that matched but has not been through interlinear
    work did match. Collapsing the two would tell a linguist their text is
    empty when it is merely untokenized.

    ``matched_texts`` is what makes the refusal actionable: told only that
    the scope is empty, a caller cannot tell a misspelled genre from a genre
    that exists and is simply unused.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parse_scope_empty"] = "parse_scope_empty"
    scope: Dict[str, Any]
    matched_texts: List[str] = Field(default_factory=list)
    hint: str


class ParseScopeAmbiguousDetail(BaseModel):
    """Detail payload for parse_scope_ambiguous rejections (parser-check CP3).

    Raised when a genre string matches more than one genre (FR-007).

    ``candidates`` carries EVERY candidate, not the first two or a truncated
    sample. Matching runs case-insensitively against both the genre name and
    its abbreviation, so the collisions that reach here are usually ones the
    caller cannot predict from what they typed -- naming only some of them
    leaves the caller guessing at the rest.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parse_scope_ambiguous"] = "parse_scope_ambiguous"
    scope: Dict[str, Any]
    requested: str
    candidates: List[str] = Field(default_factory=list)


class ParseScopeMismatchDetail(BaseModel):
    """Detail payload for parse_scope_mismatch rejections (parser-check CP3).

    Raised when two runs being compared do not describe the same scope
    (FR-012). Comparing them anyway would report grammar changes that are
    really corpus changes.

    ``differing_fields`` names which of the fingerprint's eight fields
    disagree. Without it the refusal is unactionable -- a caller cannot tell
    "you added a text to that genre" from "you ran these against different
    engines", and those have opposite remedies.

    The refusal is overridable. A forced comparison runs on the INTERSECTION
    only and says so in its own output; that is a property of the forced
    path, not of this model.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parse_scope_mismatch"] = "parse_scope_mismatch"
    baseline_fingerprint: Dict[str, Any]
    current_fingerprint: Dict[str, Any]
    differing_fields: List[str] = Field(default_factory=list)
    hint: str


class ParserTimeoutDetail(BaseModel):
    """Detail payload for parser_timeout rejections (parser-check CP3).

    ``words_completed`` rides on the refusal for the same reason it rides on
    ParseJobCancelledDetail: the partial results survive (FR-020), and a
    caller told only "timed out" has no way to know that 400 of their 500
    words are sitting readable on disk. ``run_id`` is how they reach them.

    A BOUNDED MEASUREMENT DOES NOT USE THIS CODE. A measurement that hits its
    bound is a terminal *result* carrying a wall-clock number
    (``outcome: "terminated_at_bound"``, FR-054) -- finding out that the
    grammar is slow is the measurement succeeding, not failing.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_timeout"] = "parser_timeout"
    timeout_seconds: float
    words_completed: int
    run_id: str
    hint: str


class ParserJobFailedDetail(BaseModel):
    """Detail payload for parser_job_failed rejections (parser-check CP3).

    ``failure`` is a CLOSED enum -- ``out_of_memory | crashed | cancelled`` --
    and its members are kept distinct because the remedies differ: out of
    memory means cut the scope, crashed means look at the log, cancelled
    means it was asked to stop and nothing is wrong.

    ``words_completed`` against ``words_total`` is the pair that says how much
    of the work survived; either number alone is not interpretable.
    ``log_path`` is carried so the caller does not have to reconstruct where
    the run wrote -- a run directory is named by an opaque 32-hex handle.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_job_failed"] = "parser_job_failed"
    state_at_failure: str
    failure: Literal["out_of_memory", "crashed", "cancelled"]
    words_completed: int
    words_total: int
    run_id: str
    log_path: str


# ---------------------------------------------------------------------------
# parser-check CP4 -- two additive refusal codes
#
# Field ORDER below is transcribed from specs/parser-check-cp4/contracts/
# tools.md section 2 and asserted by tests/test_parser_error_models.py and
# tests/test_response_contract.py. The contract stays tool-responses/1.0
# (FR-035): both codes are new, and grammar_load_unclean's four trailing
# fields are APPENDED after the parent spec's five, which stay a strict
# prefix in the parent's order.
# ---------------------------------------------------------------------------

class ParserFilingInProgressDetail(BaseModel):
    """Detail payload for parser_filing_in_progress rejections (CP4, FR-026).

    Raised when a filing request arrives for a project that already has a
    filing job running. Checked FIRST, before the engine check, the scope,
    the preview, the backup or any parse, which is what keeps the refusal
    under a second (SC-006).

    The claim is not a project lock (FR-027): read-only parses, single-word
    tries and the run-reading tools are not refused on its account.

    ``hint`` names ``flextools_parse_status(run_id=...)``: the useful thing
    to do with a running job is to watch it, not to start a second one.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_filing_in_progress"] = "parser_filing_in_progress"
    run_id: str
    started_at: str
    words_completed: int
    hint: str


class GrammarLoadUncleanDetail(BaseModel):
    """Detail payload for grammar_load_unclean rejections (CP4, FR-020..FR-024, FR-039).

    Filing is refused when the grammar did not load cleanly, because filing
    against a grammar that silently lost entries deletes every analysis
    those entries used to license, with no error anywhere in the chain.

    ``signal`` is a CLOSED enum:
      * ``morpher_null`` -- the parser could not be built at all (FR-020);
      * ``new_load_errors`` -- this load logged errors the baseline did not
        (FR-021);
      * ``eligible_forms_dropped`` -- fewer lexical forms are eligible to
        reach the grammar than in the baseline, which the loader does
        WITHOUT logging anything (FR-039, D-1). Additive to the parent's two.

    There is no override. The only way past ``new_load_errors`` or
    ``eligible_forms_dropped`` is a read-only ``flextools_parse_text`` of the
    same scope, which re-baselines; the message says so.

    ``baseline_source`` is ``this_run``, ``absent`` or ``prior_run:<run_id>``.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["grammar_load_unclean"] = "grammar_load_unclean"
    signal: Literal["morpher_null", "new_load_errors", "eligible_forms_dropped"]
    new_error_count: int
    baseline_error_count: int
    baseline_source: str = Field(pattern=r"^(this_run|absent|prior_run:[0-9a-f]{32})$")
    log_path: Optional[str] = None
    # -- appended after the parent spec's five (contracts/tools.md s.2) --
    new_errors: List[Any] = Field(default_factory=list)
    dropped_entries: List[Dict[str, Any]] = Field(default_factory=list)
    baseline_eligible_count: Optional[int] = None
    eligible_count: Optional[int] = None


# ---------------------------------------------------------------------------
# parser-check CP5 -- two additive refusal codes (the second per M-2)
#
# Field ORDER below is transcribed from specs/parser-check-cp5/contracts/
# tools.md section 4, which tests/test_parser_error_models.py parses. The
# contract stays tool-responses/1.0: both codes are new, and the existing
# parser_tool_missing / parser_timeout / parser_engine_mismatch shapes the
# sandbox spine also emits are unchanged.
# ---------------------------------------------------------------------------

class ParserConfigFailedDetail(BaseModel):
    """Detail payload for parser_config_failed (parser-check CP5, FR-009).

    Generation is judged from its OUTPUT, not its exit code: a run that
    exits 0 without the generator's ``Writing completed.`` line (a help
    screen, a locked project, a migration prompt, a crash, an empty config)
    is a failure, and lands here.

    ``exit_code`` is null when the generator never returned one -- it timed
    out or could not be started. ``stderr_tail`` is the last 20 lines of the
    combined generator output, ASCII with non-ASCII escaped (FR-021), capped
    at 4 KiB; the whole log is at ``log_path`` (the run's
    ``sandbox/generate-config.log``). ``run_id`` is null only when the
    failure came before a run existed.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parser_config_failed"] = "parser_config_failed"
    exit_code: Optional[int] = None
    stderr_tail: str
    log_path: str
    run_id: Optional[str] = None


class ParseSandboxRefusedDetail(BaseModel):
    """Detail payload for parse_sandbox_refused (parser-check CP5, M-2).

    One code for the sandbox tool's own pre-run refusals -- names, existence,
    corpora, seeding and disk space -- rather than one code per kind, or
    ``runtime_error`` (which would misreport a request fault as a server
    fault). Every one of these fires before a file is created (contracts/
    tools.md section 3).

    ``reason`` is a CLOSED enum; its members stay distinct because each has a
    different remedy (rename, pick an existing name, fix the file, free
    space). ``name`` and ``path`` identify what was refused where that
    applies; ``needed_bytes`` / ``free_bytes`` are set only for
    ``insufficient_disk_space``.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["parse_sandbox_refused"] = "parse_sandbox_refused"
    reason: Literal[
        "name_invalid",
        "sandbox_exists",
        "sandbox_not_found",
        "corpus_exists",
        "corpus_not_found",
        "corpus_invalid",
        "run_not_seedable",
        "insufficient_disk_space",
        "word_file_invalid",
    ]
    name: Optional[str] = None
    path: Optional[str] = None
    hint: str
    needed_bytes: Optional[int] = None
    free_bytes: Optional[int] = None


# ---------------------------------------------------------------------------
# Discriminated union over all 36 per-code detail models
# ---------------------------------------------------------------------------

AnyDetail = Union[
    SyntaxErrorDetail,
    ServerStateErrorDetail,
    InternalErrorDetail,
    PartialModuleStructureDetail,
    UnprotectedWritesDetail,
    CastingIssuesDetectedDetail,
    ApiDiscoveryRequiredDetail,
    UndiscoveredEntityDetail,
    UndefinedVariablesDetail,
    MissingImportsDetail,
    WrongLibraryImportsDetail,
    InvalidApiModeDetail,
    InvalidApiChainDetail,
    NestedUnitOfWorkDetail,
    ProjectLockedDetail,
    ProjectDriveUnavailableDetail,
    ProjectPathMismatchDetail,
    ProjectNotFoundDetail,
    RuntimeErrorDetail,
    HvoLiteralWriteRiskDetail,
    ParserEngineMismatchDetail,
    ParserCoreMissingDetail,
    ParserAgentMissingDetail,
    ParserToolMissingDetail,
    ParseMorphUnresolvedDetail,
    ParseRunNotFoundDetail,
    ParseJobCancelledDetail,
    ParseScopeEmptyDetail,
    ParseScopeAmbiguousDetail,
    ParseScopeMismatchDetail,
    ParserTimeoutDetail,
    ParserJobFailedDetail,
    ParserFilingInProgressDetail,
    GrammarLoadUncleanDetail,
    ParserConfigFailedDetail,
    ParseSandboxRefusedDetail,
]


# ---------------------------------------------------------------------------
# Rejection envelope
# ---------------------------------------------------------------------------

class RejectionEnvelope(BaseModel):
    """Full rejection response envelope.

    extra="ignore" so forward-compat extra keys from future error codes are
    silently tolerated at the envelope level (intentional -- do not change).
    The discriminated union is on error_code -- only used inside detail
    validation, not at the envelope level.
    """
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    status: Literal["error"] = Field(alias=KEY_STATUS, default="error")
    contract: str = Field(alias=KEY_CONTRACT, default=CONTRACT_VERSION)
    op_id: Optional[str] = Field(alias=KEY_OP_ID, default=None)
    error_code: str = Field(alias=KEY_ERROR_CODE)
    message: str = Field(alias=KEY_MESSAGE)
    hint: Optional[str] = Field(alias=KEY_HINT, default=None)
    # Deprecated nested error object (transition window; drop at 2.0)
    error: Optional[Dict[str, Any]] = Field(alias=KEY_ERROR, default=None)
    # All other per-code detail keys land in the model as extra fields.
    # RejectionEnvelope validates the envelope shape; detail validation
    # is done separately via AnyDetail discriminated union.


# ---------------------------------------------------------------------------
# AnyDetail discriminated-union validator
# ---------------------------------------------------------------------------

def validate_detail(data: Dict[str, Any]) -> AnyDetail:
    """Validate a detail payload dict against the AnyDetail discriminated union.

    Selects the correct per-code detail model using the ``error_code`` field
    as the discriminator and returns a validated model instance.

    Args:
        data: Dict containing at minimum ``error_code`` matching one of the
              36 known codes, plus any per-code detail fields.

    Returns:
        A validated instance of the appropriate detail model (e.g.
        ``SyntaxErrorDetail``, ``RuntimeErrorDetail``, etc.).

    Raises:
        pydantic.ValidationError: If ``error_code`` is unknown or required
            fields for the matched model are missing/invalid.

    Example:
        >>> detail = validate_detail({"error_code": "syntax_error", "line": 3})
        >>> isinstance(detail, SyntaxErrorDetail)
        True
    """
    from pydantic import TypeAdapter
    _adapter: TypeAdapter[AnyDetail] = TypeAdapter(
        Annotated[AnyDetail, Field(discriminator="error_code")]
    )
    return _adapter.validate_python(data)
