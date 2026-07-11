#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #54: Tests for the tool-response envelope contract.

Tests:
- Required keys present (containment, not equality) per golden fixtures
- Dual-emit: both canonical top-level error_code AND deprecated nested error.code present
- Round-trip: each of the 16 error codes validates against RejectionEnvelope
- Success shapes validated against *Success models with extra keys tolerated
- CONTRACT_VERSION stamp on all responses

Run with:
    python -m pytest tests/test_response_contract.py -q -m "not requires_flex"
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure src is on path for both installed and dev runs
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.response_utils import CONTRACT_VERSION, error_response, build_response_with_context
from flextoolsmcp.server.response_models import (
    RejectionEnvelope,
    RunModuleSuccess,
    GetObjectApiSuccess,
    SearchByCapabilitySuccess,
    validate_detail,
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
)

GOLDEN_DIR = Path(__file__).parent / "golden" / "responses"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_error_response(resp_list):
    """Extract parsed JSON dict from an error_response() list."""
    item = resp_list[0]
    if isinstance(item, dict):
        return json.loads(item["text"])
    # TextContent-like object
    return json.loads(item.text)


# ---------------------------------------------------------------------------
# CONTRACT_VERSION constant
# ---------------------------------------------------------------------------

class TestContractVersion:
    def test_contract_version_string(self):
        assert CONTRACT_VERSION == "tool-responses/1.0"


# ---------------------------------------------------------------------------
# error_response: dual-emit shape
# ---------------------------------------------------------------------------

class TestErrorResponseShape:
    """Verify every error_response() call emits both canonical and deprecated keys."""

    def test_canonical_keys_present(self):
        resp = _parse_error_response(error_response("syntax_error", "Bad syntax"))
        assert resp["_contract"] == CONTRACT_VERSION
        assert resp["status"] == "error"
        assert resp["error_code"] == "syntax_error"
        assert resp["message"] == "Bad syntax"

    def test_deprecated_nested_error_present(self):
        resp = _parse_error_response(error_response("syntax_error", "Bad syntax"))
        # Deprecated nested shape must co-exist
        assert "error" in resp
        assert isinstance(resp["error"], dict)
        assert resp["error"]["code"] == "syntax_error"
        assert resp["error"]["message"] == "Bad syntax"

    def test_transition_both_canonical_and_deprecated(self):
        """Explicit transition test: BOTH shapes in the same response."""
        resp = _parse_error_response(error_response("project_locked", "Project locked", guidance="Close FW"))
        # Canonical
        assert resp["error_code"] == "project_locked"
        # Deprecated nested
        assert resp["error"]["code"] == "project_locked"
        # Detail key spread at top level AND inside nested
        assert resp["guidance"] == "Close FW"
        assert resp["error"]["guidance"] == "Close FW"

    def test_extra_keys_spread_at_top_level(self):
        resp = _parse_error_response(
            error_response("undefined_variables", "Undefined", undefined_vars=["FOO"], guidance="Fix it")
        )
        assert resp["undefined_vars"] == ["FOO"]
        assert resp["guidance"] == "Fix it"

    def test_hint_propagated(self):
        resp = _parse_error_response(
            error_response("syntax_error", "Bad", hint="Check line 1")
        )
        assert resp["hint"] == "Check line 1"
        assert resp["error"]["hint"] == "Check line 1"

    def test_op_id_propagated(self):
        resp = _parse_error_response(
            error_response("missing_imports", "Missing", op_id="op-123")
        )
        assert resp["op_id"] == "op-123"


# ---------------------------------------------------------------------------
# build_response_with_context: _contract stamp on success responses
# ---------------------------------------------------------------------------

class TestBuildResponseWithContext:
    def test_contract_stamped_on_success(self):
        data = build_response_with_context({"status": "ok", "result": "hello"}, include_session=False)
        assert data["_contract"] == CONTRACT_VERSION

    def test_existing_contract_not_overwritten(self):
        data = build_response_with_context(
            {"status": "ok", "_contract": "custom/99.0"},
            include_session=False
        )
        # setdefault: pre-existing value preserved
        assert data["_contract"] == "custom/99.0"


# ---------------------------------------------------------------------------
# Golden fixture containment tests (required_keys <= response.keys())
# ---------------------------------------------------------------------------

GOLDEN_REQUIRED_KEYS = {
    "syntax_error": {"_contract", "status", "error_code", "message", "error"},
    "server_state_error": {"_contract", "status", "error_code", "message", "error"},
    "partial_module_structure": {"_contract", "status", "error_code", "message", "error"},
    "unprotected_writes": {"_contract", "status", "error_code", "message", "error"},
    "casting_issues_detected": {"_contract", "status", "error_code", "message", "error"},
    "api_discovery_required": {"_contract", "status", "error_code", "message", "error"},
    "undiscovered_entity": {"_contract", "status", "error_code", "message", "error"},
    "undefined_variables": {"_contract", "status", "error_code", "message", "error"},
    "missing_imports": {"_contract", "status", "error_code", "message", "error"},
    "wrong_library_imports": {"_contract", "status", "error_code", "message", "error"},
    "invalid_api_chain": {"_contract", "status", "error_code", "message", "error"},
    "project_locked": {"_contract", "status", "error_code", "message", "error"},
    "project_drive_unavailable": {"_contract", "status", "error_code", "message", "error"},
    "project_path_mismatch": {"_contract", "status", "error_code", "message", "error"},
    "project_not_found": {"_contract", "status", "error_code", "message", "error"},
    "runtime_error": {"_contract", "status", "error_code", "message", "error"},
}


class TestGoldenFixtures:
    """Golden fixture containment: required keys must be present in each fixture."""

    @pytest.mark.parametrize("code", list(GOLDEN_REQUIRED_KEYS.keys()))
    def test_golden_fixture_has_required_keys(self, code):
        fixture_path = GOLDEN_DIR / f"{code}.json"
        assert fixture_path.exists(), f"Missing golden fixture: {fixture_path}"
        with open(fixture_path) as f:
            data = json.load(f)
        required = GOLDEN_REQUIRED_KEYS[code]
        missing = required - data.keys()
        assert not missing, f"Fixture {code}.json missing keys: {missing}"

    @pytest.mark.parametrize("code", list(GOLDEN_REQUIRED_KEYS.keys()))
    def test_golden_fixture_dual_emit(self, code):
        """Each golden fixture must have BOTH canonical error_code AND nested error.code."""
        fixture_path = GOLDEN_DIR / f"{code}.json"
        with open(fixture_path) as f:
            data = json.load(f)
        assert data.get("error_code") == code, f"{code}.json: canonical error_code mismatch"
        assert isinstance(data.get("error"), dict), f"{code}.json: nested 'error' must be a dict"
        assert data["error"].get("code") == code, f"{code}.json: nested error.code mismatch"


# ---------------------------------------------------------------------------
# Round-trip: error_response() output validates against RejectionEnvelope
# ---------------------------------------------------------------------------

ALL_16_CODES = [
    ("syntax_error", dict(line_number=1, guidance="Fix syntax")),
    ("server_state_error", dict(server_state={"is_healthy": False, "issues": []})),
    ("partial_module_structure", dict(missing_elements=["docs"])),
    ("unprotected_writes", dict(mutating_calls=[])),
    ("casting_issues_detected", dict(casting_issues=[], severity="error")),
    ("api_discovery_required", dict(detected_candidates=[], session=None, hint="Discover first")),
    ("undiscovered_entity", dict(undiscovered=["FooOps"], session=None)),
    ("undefined_variables", dict(undefined_vars=["BAR"])),
    ("missing_imports", dict(missing_imports=["LexEntryOperations"], api_mode="flexicon")),
    ("wrong_library_imports", dict(wrong_imports=["flexlibs"], api_mode="flexicon", affected_symbols=["LexOps"])),
    ("invalid_api_chain", dict(issues=[], guidance="Fix chain")),
    ("project_locked", dict(guidance="Close FW")),
    ("project_drive_unavailable", dict(attempted_path="V:\\share")),
    ("project_path_mismatch", dict(attempted_path="C:\\old", discovered_at="C:\\new")),
    ("project_not_found", dict(hint="List projects")),
    ("runtime_error", dict(stderr="Traceback...", exit_code=1, error_type="ValueError")),
]


class TestRejectionEnvelopeRoundTrip:
    """Each of the 16 codes round-trips through RejectionEnvelope validation."""

    @pytest.mark.parametrize("code,extras", ALL_16_CODES)
    def test_validates_against_rejection_envelope(self, code, extras):
        resp = _parse_error_response(error_response(code, f"Test message for {code}", **extras))
        # Should not raise
        envelope = RejectionEnvelope.model_validate(resp, by_alias=True)
        assert envelope.error_code == code
        assert envelope.status == "error"
        assert envelope.contract == CONTRACT_VERSION

    @pytest.mark.parametrize("code,extras", ALL_16_CODES)
    def test_envelope_has_deprecated_nested_error(self, code, extras):
        resp = _parse_error_response(error_response(code, f"Test message for {code}", **extras))
        envelope = RejectionEnvelope.model_validate(resp, by_alias=True)
        # The deprecated nested error must be present
        assert envelope.error is not None
        assert envelope.error.get("code") == code


# ---------------------------------------------------------------------------
# Detail-model round-trips (discriminated union via error_code)
# ---------------------------------------------------------------------------

DETAIL_MODEL_MAP = {
    "syntax_error": SyntaxErrorDetail,
    "server_state_error": ServerStateErrorDetail,
    "partial_module_structure": PartialModuleStructureDetail,
    "unprotected_writes": UnprotectedWritesDetail,
    "casting_issues_detected": CastingIssuesDetectedDetail,
    "api_discovery_required": ApiDiscoveryRequiredDetail,
    "undiscovered_entity": UndiscoveredEntityDetail,
    "undefined_variables": UndefinedVariablesDetail,
    "missing_imports": MissingImportsDetail,
    "wrong_library_imports": WrongLibraryImportsDetail,
    "invalid_api_chain": InvalidApiChainDetail,
    "project_locked": ProjectLockedDetail,
    "project_drive_unavailable": ProjectDriveUnavailableDetail,
    "project_path_mismatch": ProjectPathMismatchDetail,
    "project_not_found": ProjectNotFoundDetail,
    "runtime_error": RuntimeErrorDetail,
}


class TestDetailModelRoundTrip:
    """Each detail model validates minimal fixture data without error."""

    @pytest.mark.parametrize("code,model_cls", list(DETAIL_MODEL_MAP.items()))
    def test_detail_model_validates(self, code, model_cls):
        detail = model_cls(error_code=code)
        assert detail.error_code == code


# ---------------------------------------------------------------------------
# Success shapes validated with extra keys tolerated
# ---------------------------------------------------------------------------

class TestSuccessModels:
    """Success models accept extra keys (forward-compat)."""

    def test_run_module_success_tolerates_extra(self):
        data = {
            "status": "ok",
            "_contract": CONTRACT_VERSION,
            "op_id": "op-1",
            "messages": ["hello"],
            "extra_future_key": True,
        }
        m = RunModuleSuccess.model_validate(data, by_alias=True)
        assert m.status == "ok"
        assert m.contract == CONTRACT_VERSION

    def test_get_object_api_success_tolerates_extra(self):
        data = {"status": "ok", "_contract": CONTRACT_VERSION, "entity": "ILexEntry", "methods": []}
        m = GetObjectApiSuccess.model_validate(data, by_alias=True)
        assert m.status == "ok"

    def test_search_by_capability_success_tolerates_extra(self):
        data = {"status": "ok", "_contract": CONTRACT_VERSION, "query": "gloss", "matches": []}
        m = SearchByCapabilitySuccess.model_validate(data, by_alias=True)
        assert m.status == "ok"


# ---------------------------------------------------------------------------
# Casting detail-key enrichment (issue #54)
# ---------------------------------------------------------------------------

class TestCastingDetailKeys:
    """Casting issues must carry correct_cast_expression, base_type, concrete_type."""

    def test_error_response_casting_issue_has_required_keys(self):
        issues = [
            {
                "line": 3,
                "property": "HeadWord",
                "rewrite": "ILexEntry(obj).HeadWord",
                "cast_interface": "ILexEntry",
                "missing_on": ["ICmObject"],
                "available_on": ["ILexEntry"],
                "fix": "cast it",
                "flexicon_helper": "use flexicon",
                "severity": "error",
                "imports_needed": ["from SIL.LCModel import ILexEntry"],
                "correct_cast_expression": "ILexEntry(obj).HeadWord",
                "base_type": "ICmObject",
                "concrete_type": "ILexEntry",
            }
        ]
        resp = _parse_error_response(
            error_response("casting_issues_detected", "Found casting issue", casting_issues=issues)
        )
        ci = resp["casting_issues"][0]
        assert "correct_cast_expression" in ci
        assert "base_type" in ci
        assert "concrete_type" in ci


# ---------------------------------------------------------------------------
# Wrong-library affected_symbols (issue #54)
# ---------------------------------------------------------------------------

class TestWrongLibraryAffectedSymbols:
    """Wrong library imports must carry affected_symbols at top level."""

    def test_affected_symbols_in_response(self):
        resp = _parse_error_response(
            error_response(
                "wrong_library_imports",
                "Wrong library",
                wrong_imports=["flexlibs"],
                api_mode="flexicon",
                affected_symbols=["LexEntryOperations", "LexSenseOperations"],
            )
        )
        assert resp["affected_symbols"] == ["LexEntryOperations", "LexSenseOperations"]
        # Also present in deprecated nested shape
        assert resp["error"]["affected_symbols"] == ["LexEntryOperations", "LexSenseOperations"]


# ---------------------------------------------------------------------------
# Requirement 2: outputSchema wiring
# ---------------------------------------------------------------------------

class TestOutputSchema:
    """outputSchema advertisement is DISABLED (issue #54 follow-up).

    Per MCP spec 2025-06-18, a tool advertising outputSchema MUST return
    structuredContent matching it. call_tool() currently returns text-only, so
    advertising the schema makes spec-compliant clients reject the response. Until
    the structured-content response path lands (Option B), list_tools() must NOT
    emit outputSchema for any tool. These tests guard that invariant so we do not
    accidentally re-break clients. The output_model METADATA is retained on ToolDef
    (checked below) so Option B has a live target to wire up.
    """

    def _get_tools(self):
        """Load list_tools() output via the server module."""
        import asyncio
        import importlib.util
        server_py = (
            Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server.py"
        )
        spec = importlib.util.spec_from_file_location("_srv_output_schema", str(server_py))
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(mod.list_tools())
        finally:
            loop.close()

    def test_no_tool_advertises_output_schema(self):
        # Guard: advertising outputSchema without returning structuredContent
        # breaks MCP-spec-compliant clients (issue #54 follow-up). Must stay empty
        # until call_tool() returns structured content.
        tools = self._get_tools()
        tools_with_schema = [
            t.name for t in tools
            if getattr(t, "outputSchema", None) is not None
        ]
        assert tools_with_schema == [], (
            "No tool may advertise outputSchema until call_tool() returns "
            f"structuredContent; found: {tools_with_schema}"
        )

    def test_output_model_metadata_retained_for_followup(self):
        # Option B target: the three tools still carry output_model metadata so the
        # schemas can be re-advertised once structured content is returned.
        from flextoolsmcp.server.tool_definitions import TOOLS
        with_model = [
            name for name, d in TOOLS.items()
            if getattr(d, "output_model", None) is not None
        ]
        for expected in (
            "flextools_run_module",
            "flextools_get_object_api",
            "flextools_search_by_capability",
        ):
            assert expected in with_model, (
                f"{expected} lost its output_model metadata (needed for the "
                f"structured-output follow-up); present: {with_model}"
            )


# ---------------------------------------------------------------------------
# P2: validate_detail helper
# ---------------------------------------------------------------------------

class TestValidateDetail:
    """validate_detail() selects the correct model via the error_code discriminator."""

    def test_syntax_error_detail(self):
        detail = validate_detail({"error_code": "syntax_error", "line": 3})
        assert isinstance(detail, SyntaxErrorDetail)
        assert detail.line == 3

    def test_runtime_error_detail(self):
        from flextoolsmcp.server.response_models import RuntimeErrorDetail
        detail = validate_detail({"error_code": "runtime_error", "exit_code": 1})
        assert isinstance(detail, RuntimeErrorDetail)
        assert detail.exit_code == 1

    def test_invalid_code_raises(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            validate_detail({"error_code": "nonexistent_code"})


# ---------------------------------------------------------------------------
# Issue #46: Auto-fix golden fixture tests
# ---------------------------------------------------------------------------

class TestAutoFixGoldenFixtures:
    """Golden fixtures for auto-fix scenarios (issue #46)."""

    def test_auto_fix_casting_applied_fixture_keys(self):
        fixture_path = GOLDEN_DIR / "auto_fix_casting_applied.json"
        assert fixture_path.exists(), "Missing auto_fix_casting_applied.json fixture"
        with open(fixture_path) as f:
            data = json.load(f)
        assert data["status"] == "ok"
        assert "auto_fixes_applied" in data
        assert "auto_fix_note" in data
        assert isinstance(data["auto_fixes_applied"], list)
        assert len(data["auto_fixes_applied"]) >= 1
        fix = data["auto_fixes_applied"][0]
        assert fix["kind"] == "casting"
        assert "line" in fix
        assert "cast_interface" in fix
        # Note must mention ACTION REQUIRED and source location
        assert "[ACTION REQUIRED]" in data["auto_fix_note"]

    def test_auto_fix_typo_applied_fixture_keys(self):
        fixture_path = GOLDEN_DIR / "auto_fix_typo_applied.json"
        assert fixture_path.exists(), "Missing auto_fix_typo_applied.json fixture"
        with open(fixture_path) as f:
            data = json.load(f)
        assert data["status"] == "ok"
        assert "auto_fixes_applied" in data
        fix = data["auto_fixes_applied"][0]
        assert fix["kind"] == "typo"
        assert "match_ratio" in fix

    def test_auto_fix_ambiguous_not_applied(self):
        """Ambiguous casting (cast_interface=None) must stay rejected with original payload."""
        fixture_path = GOLDEN_DIR / "auto_fix_ambiguous_not_applied.json"
        assert fixture_path.exists(), "Missing auto_fix_ambiguous_not_applied.json fixture"
        with open(fixture_path) as f:
            data = json.load(f)
        # Must be an error response, not success
        assert data["status"] == "error"
        assert data["error_code"] == "casting_issues_detected"
        # Must NOT carry auto_fixes_applied
        assert "auto_fixes_applied" not in data, (
            "Ambiguous casting must NOT carry auto_fixes_applied -- it was not applied"
        )
        # Confirm cast_interface is None in the payload (ambiguous)
        ci = data["casting_issues"][0]
        assert ci.get("cast_interface") is None

    def test_run_module_success_model_accepts_auto_fix_fields(self):
        """RunModuleSuccess model must accept auto_fixes_applied + auto_fix_note."""
        from flextoolsmcp.server.response_models import RunModuleSuccess
        from flextoolsmcp.response_utils import CONTRACT_VERSION
        data = {
            "status": "ok",
            "_contract": CONTRACT_VERSION,
            "op_id": "op-test-001",
            "auto_fixes_applied": [{"kind": "casting", "line": 3}],
            "auto_fix_note": "[AUTO-FIX] 1 rewrite applied.\n[ACTION REQUIRED] Update source.",
        }
        m = RunModuleSuccess.model_validate(data, by_alias=True)
        assert m.status == "ok"
        assert m.auto_fixes_applied == [{"kind": "casting", "line": 3}]
        assert "[ACTION REQUIRED]" in (m.auto_fix_note or "")

    def test_run_module_success_model_none_when_no_fix(self):
        """auto_fixes_applied and auto_fix_note default to None."""
        from flextoolsmcp.server.response_models import RunModuleSuccess
        from flextoolsmcp.response_utils import CONTRACT_VERSION
        data = {"status": "ok", "_contract": CONTRACT_VERSION}
        m = RunModuleSuccess.model_validate(data, by_alias=True)
        assert m.auto_fixes_applied is None
        assert m.auto_fix_note is None


# ---------------------------------------------------------------------------
# P1: collision guard in error_response()
# ---------------------------------------------------------------------------

class TestCollisionGuard:
    """error_response() must raise ValueError when extra keys collide with canonical keys.

    Note: error_code and message are positional parameters and cannot be passed
    as **extra kwargs; only the remaining canonical keys (_contract, status, error)
    are reachable via **extra.
    """

    @pytest.mark.parametrize("colliding_key", [
        "status", "_contract", "error"
    ])
    def test_collision_raises_value_error(self, colliding_key):
        with pytest.raises(ValueError, match="collide with canonical envelope keys"):
            error_response("syntax_error", "Test", **{colliding_key: "boom"})


# ---------------------------------------------------------------------------
# P2: make_golden --regen mechanism
# ---------------------------------------------------------------------------

class TestMakeGolden:
    """make_golden.py dry-run exits 0 when all fixtures are current."""

    def test_make_golden_dry_run_passes(self):
        """Dry-run (no --regen) should pass when all fixtures match."""
        import subprocess
        make_golden = Path(__file__).parent / "make_golden.py"
        result = subprocess.run(
            [sys.executable, str(make_golden)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"make_golden.py dry-run failed (stale fixtures):\n{result.stdout}\n{result.stderr}\n"
            "Run: python tests/make_golden.py --regen"
        )
