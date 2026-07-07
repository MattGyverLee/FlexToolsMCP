#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #54: Pydantic response envelope models for FlexToolsMCP.

Provides:
- BaseEnvelope: common _contract / status / op_id fields
- Per-tool *Success models (extra="ignore" for forward-compat)
- RejectionEnvelope with a discriminated union keyed on error_code
- 16 per-code detail models (12 existing + 4 folded in)

All field aliases reference KEY_* constants from response_keys so renames
propagate automatically.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

try:
    from .response_keys import (
        KEY_STATUS, KEY_CONTRACT, KEY_OP_ID, KEY_ERROR_CODE, KEY_MESSAGE, KEY_HINT,
        KEY_ERROR,
    )
except ImportError:
    from server.response_keys import (
        KEY_STATUS, KEY_CONTRACT, KEY_OP_ID, KEY_ERROR_CODE, KEY_MESSAGE, KEY_HINT,
        KEY_ERROR,
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


class InvalidApiChainDetail(BaseModel):
    """Detail payload for invalid_api_chain rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["invalid_api_chain"] = "invalid_api_chain"
    issues: List[Any] = Field(default_factory=list)
    guidance: Optional[str] = None


class ProjectLockedDetail(BaseModel):
    """Detail payload for project_locked rejections."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    error_code: Literal["project_locked"] = "project_locked"
    guidance: str = ""
    lock_file_path: Optional[str] = None


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


# ---------------------------------------------------------------------------
# Discriminated union over all 16 per-code detail models
# ---------------------------------------------------------------------------

AnyDetail = Union[
    SyntaxErrorDetail,
    ServerStateErrorDetail,
    PartialModuleStructureDetail,
    UnprotectedWritesDetail,
    CastingIssuesDetectedDetail,
    ApiDiscoveryRequiredDetail,
    UndiscoveredEntityDetail,
    UndefinedVariablesDetail,
    MissingImportsDetail,
    WrongLibraryImportsDetail,
    InvalidApiChainDetail,
    ProjectLockedDetail,
    ProjectDriveUnavailableDetail,
    ProjectPathMismatchDetail,
    ProjectNotFoundDetail,
    RuntimeErrorDetail,
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
              16 known codes, plus any per-code detail fields.

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
