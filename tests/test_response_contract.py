#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #54: Tests for the tool-response envelope contract.

Tests:
- Required keys present (containment, not equality) per golden fixtures
- Dual-emit: both canonical top-level error_code AND deprecated nested error.code present
- Round-trip: each of the 18 error codes validates against RejectionEnvelope
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
    TopLevelMainInvocationDetail,
    UnprotectedWritesDetail,
    CastingIssuesDetectedDetail,
    ApiDiscoveryRequiredDetail,
    UndiscoveredEntityDetail,
    UndefinedVariablesDetail,
    MissingImportsDetail,
    WrongLibraryImportsDetail,
    InvalidApiModeDetail,
    InvalidApiChainDetail,
    ProjectLockedDetail,
    ProjectDriveUnavailableDetail,
    ProjectPathMismatchDetail,
    ProjectNotFoundDetail,
    RuntimeErrorDetail,
    HvoLiteralWriteRiskDetail,
    DeprecatedMemberDetail,
    RawAddCustomFieldWriteRiskDetail,
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
    "deprecated_member": {
        "_contract", "status", "error_code", "message", "error",
        "findings", "deprecations", "replacement_example", "next_steps",
    },
    # Parser-check CP4 (FR-035): the detail fields ride at top level too.
    "parser_filing_in_progress": {
        "_contract", "status", "error_code", "message", "error",
        "run_id", "started_at", "words_completed", "hint",
    },
    "grammar_load_unclean": {
        "_contract", "status", "error_code", "message", "error",
        "signal", "new_error_count", "baseline_error_count", "baseline_source", "log_path",
        "new_errors", "dropped_entries", "baseline_eligible_count", "eligible_count",
    },
    # Parser-check CP5 (contracts/tools.md section 4): same top-level mirror.
    "parser_config_failed": {
        "_contract", "status", "error_code", "message", "error",
        "exit_code", "stderr_tail", "log_path", "run_id",
    },
    "parse_sandbox_refused": {
        "_contract", "status", "error_code", "message", "error",
        "reason", "name", "path", "hint", "needed_bytes", "free_bytes",
    },
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

ALL_ERROR_CODES = [
    ("syntax_error", dict(line_number=1, guidance="Fix syntax")),
    ("server_state_error", dict(server_state={"is_healthy": False, "issues": []})),
    ("partial_module_structure", dict(missing_elements=["docs"])),
    ("top_level_main_invocation", dict(call_lines=[4])),
    ("unprotected_writes", dict(mutating_calls=[])),
    ("casting_issues_detected", dict(casting_issues=[], severity="error")),
    ("api_discovery_required", dict(detected_candidates=[], session=None, hint="Discover first")),
    ("undiscovered_entity", dict(undiscovered=["FooOps"], session=None)),
    ("undefined_variables", dict(undefined_vars=["BAR"])),
    ("missing_imports", dict(missing_imports=["LexEntryOperations"], api_mode="flexicon")),
    ("wrong_library_imports", dict(wrong_imports=["flexlibs"], api_mode="flexicon", affected_symbols=["LexOps"])),
    ("invalid_api_mode", dict(allowed_modes=["flexicon", "flexlibs_stable", "liblcm"], received="bogus")),
    ("invalid_api_chain", dict(issues=[], guidance="Fix chain")),
    ("nested_unit_of_work", dict(constructs=[{"construct": "UndoableUnitOfWorkHelper(...)", "line": 3}])),
    ("project_locked", dict(
        guidance="Enable project sharing in FLEx, then retry",
        lock_file_path="C:\\Projects\\Demo\\Demo.fwdata.lock",
        verdict="open_exclusive",
        sharing_enabled=False,
        holder_pid=68436,
        holder_process="FieldWorks",
        remedy="Enable project sharing in FLEx, then retry",
    )),
    ("project_drive_unavailable", dict(attempted_path="V:\\share")),
    ("project_path_mismatch", dict(attempted_path="C:\\old", discovered_at="C:\\new")),
    ("project_not_found", dict(hint="List projects")),
    ("runtime_error", dict(stderr="Traceback...", exit_code=1, error_type="ValueError")),
    ("hvo_literal_write_risk", dict(
        findings=[{"line": 3, "detail": "SetGloss(sense_or_hvo=12345)"}],
        next_steps=["Carry the GUID and re-resolve with project.Object(guid_str)"],
    )),
    ("deprecated_member", dict(
        findings=[{"member": "DoNotUseForParsing", "access": "write", "line": 2}],
        deprecations=[{"id": "lexentry-donotuseforparsing"}],
        replacement_example="entry.LexemeFormOA.IsAbstract = True",
        next_steps=["Set IsAbstract on the entry's forms"],
    )),
    ("raw_addcustomfield_write_risk", dict(
        findings=[{"line": 2, "detail": "mdc.AddCustomField(...)"}],
        next_steps=["Use project.CustomFields.CreateField or FLEx UI"],
    )),
    # parser-check CP2b
    ("parse_morph_unresolved", dict(
        morph="kirim",
        position=1,
        resolved_to="ambiguous",
        candidates=[
            {"headword": "kirim", "sense": "send", "msa_hvo": 5002, "entry_hvo": 102},
            {"headword": "kirim", "sense": "deliver", "msa_hvo": 5003, "entry_hvo": 103},
        ],
        hint="Pick one with `sense`, or give its msa_hvo directly.",
    )),
    ("parse_run_not_found", dict(
        run_id="0" * 32,
        available_runs=["a" * 32],
        hint="Handles are issued by flextools_try_word.",
    )),
    ("parse_job_cancelled", dict(
        run_id="a" * 32,
        words_completed=17,
        state_at_cancel="parsing",
        hint="This run has already ended; its partial results are readable.",
    )),
]


class TestRejectionEnvelopeRoundTrip:
    """Each of the 18 codes round-trips through RejectionEnvelope validation."""

    @pytest.mark.parametrize("code,extras", ALL_ERROR_CODES)
    def test_validates_against_rejection_envelope(self, code, extras):
        resp = _parse_error_response(error_response(code, f"Test message for {code}", **extras))
        # Should not raise
        envelope = RejectionEnvelope.model_validate(resp, by_alias=True)
        assert envelope.error_code == code
        assert envelope.status == "error"
        assert envelope.contract == CONTRACT_VERSION

    @pytest.mark.parametrize("code,extras", ALL_ERROR_CODES)
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
    "top_level_main_invocation": TopLevelMainInvocationDetail,
    "unprotected_writes": UnprotectedWritesDetail,
    "casting_issues_detected": CastingIssuesDetectedDetail,
    "api_discovery_required": ApiDiscoveryRequiredDetail,
    "undiscovered_entity": UndiscoveredEntityDetail,
    "undefined_variables": UndefinedVariablesDetail,
    "missing_imports": MissingImportsDetail,
    "wrong_library_imports": WrongLibraryImportsDetail,
    "invalid_api_mode": InvalidApiModeDetail,
    "invalid_api_chain": InvalidApiChainDetail,
    "project_locked": ProjectLockedDetail,
    "project_drive_unavailable": ProjectDriveUnavailableDetail,
    "project_path_mismatch": ProjectPathMismatchDetail,
    "project_not_found": ProjectNotFoundDetail,
    "runtime_error": RuntimeErrorDetail,
    "hvo_literal_write_risk": HvoLiteralWriteRiskDetail,
    "deprecated_member": DeprecatedMemberDetail,
    "raw_addcustomfield_write_risk": RawAddCustomFieldWriteRiskDetail,
}

#: CP2b's three. Separate from the map above because two of them have
#: REQUIRED fields, so `model_cls(error_code=code)` -- which is what the
#: map's test does -- cannot construct them. Constructing them with their
#: required fields is the point: a model whose required fields could be
#: omitted would not be pinning anything.
CP2B_DETAIL_FIXTURES = {
    "parse_morph_unresolved": dict(
        morph="kosong",
        position=0,
        resolved_to="no_msa",
        candidates=[
            {"headword": "kosong", "sense": None, "msa_hvo": None, "entry_hvo": 104}
        ],
        hint="That entry carries no morphosyntactic analysis.",
    ),
    "parse_run_not_found": dict(
        run_id="0" * 32, available_runs=[], hint="No runs on this server."
    ),
    "parse_job_cancelled": dict(
        run_id="a" * 32,
        words_completed=4,
        state_at_cancel="parsing",
        hint="Already ended.",
    ),
}


class TestDetailModelRoundTrip:
    """Each detail model validates minimal fixture data without error."""

    @pytest.mark.parametrize("code,model_cls", list(DETAIL_MODEL_MAP.items()))
    def test_detail_model_validates(self, code, model_cls):
        detail = model_cls(error_code=code)
        assert detail.error_code == code


class TestParserCheckCP2bCodes:
    """The three CP2b codes: the count, the field ORDER, and the closures.

    `parse_morph_unresolved`'s field order is pinned rather than merely its
    membership. The order was the subject of a three-way agreement check
    during CP2's cycle 3, and a reordering is exactly the change that passes
    every behavioural test -- the keys are all still there, and every caller
    reading them by name still works. What breaks is the agreement.
    """

    @pytest.mark.parametrize("code,fixture", list(CP2B_DETAIL_FIXTURES.items()))
    def test_detail_model_validates_with_its_required_fields(self, code, fixture):
        from flextoolsmcp.server.response_models import (
            ParseJobCancelledDetail,
            ParseMorphUnresolvedDetail,
            ParseRunNotFoundDetail,
        )

        models = {
            "parse_morph_unresolved": ParseMorphUnresolvedDetail,
            "parse_run_not_found": ParseRunNotFoundDetail,
            "parse_job_cancelled": ParseJobCancelledDetail,
        }
        detail = models[code].model_validate(dict(fixture, error_code=code))
        assert detail.error_code == code

    def test_parse_morph_unresolved_field_order_is_pinned(self):
        """`morph`, `position`, `resolved_to`, `candidates`, `hint`. That order.

        Do not reorder, rename, recase or pluralize. If this test fails
        because a field was added, the addition is the thing to reconsider:
        the model is `extra="forbid"` precisely so the shape is closed.
        """
        from flextoolsmcp.server.response_models import ParseMorphUnresolvedDetail

        fields = [
            name
            for name in ParseMorphUnresolvedDetail.model_fields
            if name != "error_code"
        ]
        assert fields == [
            "morph",
            "position",
            "resolved_to",
            "candidates",
            "hint",
        ], f"parse_morph_unresolved's field order drifted: {fields}"

    def test_resolved_to_is_a_closed_enum_of_exactly_three(self):
        """The three failures stay three.

        Widening this enum is how "could not resolve" creeps back in as a
        fourth, catch-all value -- which is the collapse the three exist to
        prevent.
        """
        import typing

        from flextoolsmcp.server.response_models import ParseMorphUnresolvedDetail

        annotation = ParseMorphUnresolvedDetail.model_fields["resolved_to"].annotation
        assert set(typing.get_args(annotation)) == {"none", "ambiguous", "no_msa"}

    @pytest.mark.parametrize(
        "code", ["parse_morph_unresolved", "parse_run_not_found", "parse_job_cancelled"]
    )
    def test_extra_keys_are_forbidden(self, code):
        """A typo'd field fails loudly rather than vanishing."""
        import pydantic

        from flextoolsmcp.server.response_models import (
            ParseJobCancelledDetail,
            ParseMorphUnresolvedDetail,
            ParseRunNotFoundDetail,
        )

        models = {
            "parse_morph_unresolved": ParseMorphUnresolvedDetail,
            "parse_run_not_found": ParseRunNotFoundDetail,
            "parse_job_cancelled": ParseJobCancelledDetail,
        }
        payload = dict(CP2B_DETAIL_FIXTURES[code], error_code=code, sneaky=1)
        with pytest.raises(pydantic.ValidationError):
            models[code].model_validate(payload)

    def test_the_documented_error_code_count_is_forty_one(self):
        """FR-037: the hand-maintained count in the contract doc tracks reality.

        Hand-maintained counts drift silently, which is why this compares
        the prose against the union rather than trusting either.
        """
        import re
        import typing
        from pathlib import Path

        from flextoolsmcp.server.response_models import AnyDetail

        union_size = len(typing.get_args(AnyDetail))
        # 31 through CP3; #89 adds internal_error -> 32; CP4 adds
        # parser_filing_in_progress and grammar_load_unclean -> 34; CP5 adds
        # parser_config_failed and parse_sandbox_refused (M-2) -> 36;
        # #243 adds session_not_initialized, unknown_tool, invalid_input -> 39;
        # curated deprecations add deprecated_member -> 40;
        # #70 adds raw_addcustomfield_write_risk -> 41;
        # #279 adds top_level_main_invocation -> 42.
        assert union_size == 42, f"the detail union holds {union_size} models"

        doc = (
            Path(__file__).parent.parent / "docs" / "TOOL-CONTRACT.md"
        ).read_text(encoding="utf-8")
        stated = re.search(r"one of the (\d+) codes below", doc)
        assert stated, "TOOL-CONTRACT.md no longer states a code count"
        assert int(stated.group(1)) == union_size, (
            f"TOOL-CONTRACT.md says {stated.group(1)} codes; the union has "
            f"{union_size}"
        )

    @pytest.mark.parametrize(
        "code", ["parse_morph_unresolved", "parse_run_not_found", "parse_job_cancelled"]
    )
    def test_each_new_code_has_a_row_in_the_contract_doc(self, code):
        from pathlib import Path

        doc = (
            Path(__file__).parent.parent / "docs" / "TOOL-CONTRACT.md"
        ).read_text(encoding="utf-8")
        assert f"`{code}`" in doc, (
            f"{code} is emitted but undocumented; FR-037 requires a row"
        )

    @pytest.mark.parametrize(
        "code, model_name",
        [
            ("parse_scope_empty", "ParseScopeEmptyDetail"),
            ("parse_scope_ambiguous", "ParseScopeAmbiguousDetail"),
            ("parse_scope_mismatch", "ParseScopeMismatchDetail"),
            ("parser_timeout", "ParserTimeoutDetail"),
            ("parser_job_failed", "ParserJobFailedDetail"),
            # CP4 (FR-035): same transcription check for the two new rows.
            ("parser_filing_in_progress", "ParserFilingInProgressDetail"),
            ("grammar_load_unclean", "GrammarLoadUncleanDetail"),
            # CP5 (contracts/tools.md section 4): the two new rows.
            ("parser_config_failed", "ParserConfigFailedDetail"),
            ("parse_sandbox_refused", "ParseSandboxRefusedDetail"),
        ],
    )
    def test_each_cp3_row_lists_its_fields_in_the_models_order(self, code, model_name):
        """FR-060: the CP3 rows are transcribed, field order included.

        CP2's field-order divergence happened during transcription, so the
        doc row is checked against the model rather than trusted.
        """
        from pathlib import Path

        from flextoolsmcp.server import response_models

        doc = (
            Path(__file__).parent.parent / "docs" / "TOOL-CONTRACT.md"
        ).read_text(encoding="utf-8")
        row = next(
            (line for line in doc.splitlines() if line.startswith(f"| `{code}` |")),
            None,
        )
        assert row is not None, f"{code} has no row in TOOL-CONTRACT.md"
        # Everything after the code cell: the row escapes pipes inside enums.
        detail_cell = row[len(f"| `{code}` |"):]
        model = getattr(response_models, model_name)
        expected = [name for name in model.model_fields if name != "error_code"]
        positions = [detail_cell.find(f"`{name}`") for name in expected]
        assert -1 not in positions, (
            f"{code}'s row omits {[n for n, p in zip(expected, positions, strict=True) if p < 0]}"
        )
        assert positions == sorted(positions), (
            f"{code}'s row lists its fields out of the model's order {expected}"
        )
        assert "In this order" in detail_cell, "the row does not say its order is fixed"

    def test_the_contract_version_did_not_move(self):
        """Additive throughout: three codes, same contract version."""
        assert CONTRACT_VERSION == "tool-responses/1.0"


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
