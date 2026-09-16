#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T006: Envelope tests for the four parser-check CP1 error-code detail models.

Contract source: specs/parser-check/contracts/error-codes.md

Models under test:
    - ParserEngineMismatchDetail  (parser_engine_mismatch)
    - ParserCoreMissingDetail     (parser_core_missing)
    - ParserAgentMissingDetail    (parser_agent_missing)
    - ParserToolMissingDetail     (parser_tool_missing)

Every assertion goes THROUGH validate_detail(), the shared discriminated-union
validator (AnyDetail / TypeAdapter keyed on error_code) that every other
error code's detail payload is checked against. A model can be perfectly
correct in isolation and still be invisible to real callers if it was left
out of the AnyDetail Union -- testing only the bare model class would not
catch that. This file exists specifically to catch it.
"""

import sys
from pathlib import Path

import pydantic
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.response_models import (
    validate_detail,
    ParserEngineMismatchDetail,
    ParserCoreMissingDetail,
    ParserAgentMissingDetail,
    ParserToolMissingDetail,
)


# ---------------------------------------------------------------------------
# Contract examples (field tables from contracts/error-codes.md, verbatim
# field names)
# ---------------------------------------------------------------------------

PARSER_ENGINE_MISMATCH_EXAMPLE = {
    "error_code": "parser_engine_mismatch",
    "configured_engine": "XAmple",
    "supported_engines": ["HC"],
    "hint": "Switch the active parser to HC via Words > Parser > Choose Parser.",
}

PARSER_CORE_MISSING_EXAMPLE = {
    "error_code": "parser_core_missing",
    "signal": "absent",
    "expected_path": "C:\\FieldWorks\\SIL.LCModel.dll",
    "detected_version": None,
    "missing_members": [],
    "lcmodel_install_path": None,
    "install_hint": "Install FieldWorks to obtain SIL.LCModel.dll.",
    "load_error": None,
}

PARSER_AGENT_MISSING_EXAMPLE = {
    "error_code": "parser_agent_missing",
    "agent_guid": "00000000-0000-0000-0000-000000000000",
    "agent_name": "HermitCrab",
    "active_engine": "HC",
    "probe_source": "bootstrap_absent",
    "hint": "The HermitCrab agent was never created for this project.",
}

PARSER_TOOL_MISSING_EXAMPLE = {
    "error_code": "parser_tool_missing",
    "component": "hc",
    "expected_path": "C:\\Users\\me\\.dotnet\\tools\\hc.exe",
    "install_hint": "dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool",
}


# ---------------------------------------------------------------------------
# parser_engine_mismatch
# ---------------------------------------------------------------------------

class TestParserEngineMismatchDetail:
    def test_contract_example_validates_through_validate_detail(self):
        detail = validate_detail(PARSER_ENGINE_MISMATCH_EXAMPLE)
        assert isinstance(detail, ParserEngineMismatchDetail)
        assert detail.error_code == "parser_engine_mismatch"
        assert detail.configured_engine == "XAmple"
        assert detail.supported_engines == ["HC"]
        assert detail.hint == PARSER_ENGINE_MISMATCH_EXAMPLE["hint"]

    def test_unknown_field_rejected(self):
        bad = dict(PARSER_ENGINE_MISMATCH_EXAMPLE, unexpected_field="boom")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    @pytest.mark.parametrize(
        "field", ["configured_engine", "supported_engines", "hint"]
    )
    def test_omitting_required_field_raises_validation_error(self, field):
        # None of parser_engine_mismatch's three fields carry a default in
        # response_models.py -- all are required.
        data = {k: v for k, v in PARSER_ENGINE_MISMATCH_EXAMPLE.items() if k != field}
        with pytest.raises(pydantic.ValidationError):
            validate_detail(data)


# ---------------------------------------------------------------------------
# parser_core_missing
# ---------------------------------------------------------------------------

class TestParserCoreMissingDetail:
    def test_contract_example_validates_through_validate_detail(self):
        detail = validate_detail(PARSER_CORE_MISSING_EXAMPLE)
        assert isinstance(detail, ParserCoreMissingDetail)
        assert detail.error_code == "parser_core_missing"
        assert detail.signal == "absent"
        assert detail.expected_path == PARSER_CORE_MISSING_EXAMPLE["expected_path"]
        assert detail.detected_version is None
        assert detail.missing_members == []
        assert detail.lcmodel_install_path is None
        assert detail.install_hint == PARSER_CORE_MISSING_EXAMPLE["install_hint"]
        assert detail.load_error is None

    def test_unknown_field_rejected(self):
        bad = dict(PARSER_CORE_MISSING_EXAMPLE, unexpected_field="boom")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    @pytest.mark.parametrize(
        "signal", ["foreign_install", "incompatible_surface", "load_failed"]
    )
    def test_signal_enum_accepts_all_contract_values(self, signal):
        data = dict(PARSER_CORE_MISSING_EXAMPLE, signal=signal)
        detail = validate_detail(data)
        assert isinstance(detail, ParserCoreMissingDetail)
        assert detail.signal == signal

    def test_signal_enum_rejects_value_outside_set(self):
        bad = dict(PARSER_CORE_MISSING_EXAMPLE, signal="nonexistent_signal")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    def test_signal_enum_rejects_case_variant(self):
        # "absent" is valid; "ABSENT" must not be silently accepted -- the
        # enum is a case-sensitive contract value shared with the health block.
        bad = dict(PARSER_CORE_MISSING_EXAMPLE, signal="ABSENT")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    @pytest.mark.parametrize(
        "field", ["signal", "expected_path", "missing_members", "install_hint"]
    )
    def test_omitting_required_field_raises_validation_error(self, field):
        # signal, expected_path, missing_members and install_hint carry no
        # default in response_models.py -- required, unlike the three
        # Optional[...] = None fields covered below.
        data = {k: v for k, v in PARSER_CORE_MISSING_EXAMPLE.items() if k != field}
        with pytest.raises(pydantic.ValidationError):
            validate_detail(data)

    @pytest.mark.parametrize(
        "field", ["detected_version", "lcmodel_install_path", "load_error"]
    )
    def test_omitting_optional_field_validates_as_none(self, field):
        # detected_version, lcmodel_install_path and load_error are the only
        # three fields marked "or null" in contracts/error-codes.md, matching
        # their Optional[...] = None declarations in response_models.py --
        # omitting them must still validate, with the field defaulting to None.
        data = {k: v for k, v in PARSER_CORE_MISSING_EXAMPLE.items() if k != field}
        detail = validate_detail(data)
        assert isinstance(detail, ParserCoreMissingDetail)
        assert getattr(detail, field) is None


# ---------------------------------------------------------------------------
# parser_agent_missing
# ---------------------------------------------------------------------------

class TestParserAgentMissingDetail:
    def test_contract_example_validates_through_validate_detail(self):
        detail = validate_detail(PARSER_AGENT_MISSING_EXAMPLE)
        assert isinstance(detail, ParserAgentMissingDetail)
        assert detail.error_code == "parser_agent_missing"
        assert detail.agent_guid == PARSER_AGENT_MISSING_EXAMPLE["agent_guid"]
        assert detail.agent_name == "HermitCrab"
        assert detail.active_engine == "HC"
        assert detail.probe_source == "bootstrap_absent"
        assert detail.hint == PARSER_AGENT_MISSING_EXAMPLE["hint"]

    def test_unknown_field_rejected(self):
        bad = dict(PARSER_AGENT_MISSING_EXAMPLE, unexpected_field="boom")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    def test_probe_source_enum_accepts_other_contract_value(self):
        data = dict(PARSER_AGENT_MISSING_EXAMPLE, probe_source="lookup_failed")
        detail = validate_detail(data)
        assert isinstance(detail, ParserAgentMissingDetail)
        assert detail.probe_source == "lookup_failed"

    def test_probe_source_enum_rejects_value_outside_set(self):
        bad = dict(PARSER_AGENT_MISSING_EXAMPLE, probe_source="nonexistent_source")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    def test_probe_source_enum_rejects_case_variant(self):
        bad = dict(PARSER_AGENT_MISSING_EXAMPLE, probe_source="Bootstrap_Absent")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    def test_agent_name_enum_rejects_value_outside_set(self):
        bad = dict(PARSER_AGENT_MISSING_EXAMPLE, agent_name="SomeOtherAgent")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    def test_agent_name_enum_rejects_case_variant(self):
        # "HermitCrab" is the only accepted value; "hermitcrab" must be rejected.
        bad = dict(PARSER_AGENT_MISSING_EXAMPLE, agent_name="hermitcrab")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    @pytest.mark.parametrize(
        "field", ["agent_guid", "agent_name", "active_engine", "probe_source", "hint"]
    )
    def test_omitting_required_field_raises_validation_error(self, field):
        # All five parser_agent_missing fields carry no default in
        # response_models.py -- all are required.
        data = {k: v for k, v in PARSER_AGENT_MISSING_EXAMPLE.items() if k != field}
        with pytest.raises(pydantic.ValidationError):
            validate_detail(data)


# ---------------------------------------------------------------------------
# parser_tool_missing
# ---------------------------------------------------------------------------

class TestParserToolMissingDetail:
    def test_contract_example_validates_through_validate_detail(self):
        detail = validate_detail(PARSER_TOOL_MISSING_EXAMPLE)
        assert isinstance(detail, ParserToolMissingDetail)
        assert detail.error_code == "parser_tool_missing"
        assert detail.component == "hc"
        assert detail.expected_path == PARSER_TOOL_MISSING_EXAMPLE["expected_path"]
        assert detail.install_hint == PARSER_TOOL_MISSING_EXAMPLE["install_hint"]

    def test_unknown_field_rejected(self):
        bad = dict(PARSER_TOOL_MISSING_EXAMPLE, unexpected_field="boom")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    def test_component_enum_accepts_other_contract_value(self):
        data = dict(PARSER_TOOL_MISSING_EXAMPLE, component="GenerateHCConfig.exe")
        detail = validate_detail(data)
        assert isinstance(detail, ParserToolMissingDetail)
        assert detail.component == "GenerateHCConfig.exe"

    def test_component_enum_rejects_value_outside_set(self):
        bad = dict(PARSER_TOOL_MISSING_EXAMPLE, component="nonexistent_component")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    def test_component_enum_rejects_case_variant(self):
        # "hc" is valid; "HC" must not be silently accepted -- shared with
        # flextools_health's sandbox.components[].component.
        bad = dict(PARSER_TOOL_MISSING_EXAMPLE, component="HC")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    @pytest.mark.parametrize(
        "field", ["component", "expected_path", "install_hint"]
    )
    def test_omitting_required_field_raises_validation_error(self, field):
        # All three parser_tool_missing fields carry no default in
        # response_models.py -- all are required.
        data = {k: v for k, v in PARSER_TOOL_MISSING_EXAMPLE.items() if k != field}
        with pytest.raises(pydantic.ValidationError):
            validate_detail(data)
