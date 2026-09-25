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

import json
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
    "component": "fieldworks_hermitcrab",
    "expected_path": "C:\\Program Files\\SIL\\FieldWorks 9\\SIL.Machine.Morphology.HermitCrab.dll",
    "install_hint": "GenerateHCConfig.exe ships with FieldWorks 9; repair or reinstall FieldWorks.",
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
        assert detail.component == "fieldworks_hermitcrab"
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

    def test_the_retired_hc_component_is_rejected(self):
        """CP5 re-plan: `hc` left the enum with the `hc` console tool."""
        bad = dict(PARSER_TOOL_MISSING_EXAMPLE, component="hc")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

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


# ===========================================================================
# parser-check CP3 (T013, T014) -- the five additive refusal codes
#
# Contract source: specs/parser-check-cp3/contracts/tools.md section 2
#
# The field-ORDER assertion below does not hardcode the expected order. It
# parses it out of the contract table at test time and compares that against
# the live model. Hardcoding would let the contract and the model drift
# together the moment someone updates both to match each other and neither to
# match the table a caller actually reads.
# ===========================================================================

import re as _re

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.response_models import (
    AnyDetail,
    ParseScopeEmptyDetail,
    ParseScopeAmbiguousDetail,
    ParseScopeMismatchDetail,
    ParserTimeoutDetail,
    ParserJobFailedDetail,
)

_CONTRACT_PATH = (
    Path(__file__).parent.parent
    / "specs" / "parser-check-cp3" / "contracts" / "tools.md"
)

CP3_MODELS = {
    "parse_scope_empty": ParseScopeEmptyDetail,
    "parse_scope_ambiguous": ParseScopeAmbiguousDetail,
    "parse_scope_mismatch": ParseScopeMismatchDetail,
    "parser_timeout": ParserTimeoutDetail,
    "parser_job_failed": ParserJobFailedDetail,
}

CP3_EXAMPLES = {
    "parse_scope_empty": {
        "error_code": "parse_scope_empty",
        "scope": {"kind": "genre", "value": "Narrative"},
        "matched_texts": [],
        "hint": "No text is tagged with that genre.",
    },
    "parse_scope_ambiguous": {
        "error_code": "parse_scope_ambiguous",
        "scope": {"kind": "genre", "value": "nar"},
        "requested": "nar",
        "candidates": ["Narrative", "Narrative (oral)"],
    },
    "parse_scope_mismatch": {
        "error_code": "parse_scope_mismatch",
        "baseline_fingerprint": {"word_count": 120},
        "current_fingerprint": {"word_count": 131},
        "differing_fields": ["word_count", "text_ids"],
        "hint": (
            "Re-run the baseline, or force the comparison to run on the "
            "intersection."
        ),
    },
    "parser_timeout": {
        "error_code": "parser_timeout",
        "timeout_seconds": 300.0,
        "words_completed": 412,
        "run_id": "a" * 32,
        "hint": "The completed words are readable via flextools_parse_log.",
    },
    "parser_job_failed": {
        "error_code": "parser_job_failed",
        "state_at_failure": "parsing",
        "failure": "crashed",
        "words_completed": 412,
        "words_total": 900,
        "run_id": "a" * 32,
        "log_path": "runs/aaaa/meta.json",
    },
}

# Matches one row of the section-2 field table:
#     | `parse_scope_empty` | `scope`, `matched_texts`, `hint` |
_CONTRACT_ROW = _re.compile(r"^\|\s*.([a-z_]+).\s*\|\s*(.+?)\s*\|\s*$")


def _contract_field_order():
    """Field order per code, read out of contracts/tools.md section 2's table.

    Returns {error_code: [field, ...]}. Backticks are stripped; the table
    cells are comma-separated field names.
    """
    text = _CONTRACT_PATH.read_text(encoding="utf-8")
    order = {}
    for line in text.splitlines():
        m = _CONTRACT_ROW.match(line)
        if not m:
            continue
        code, cells = m.group(1), m.group(2)
        if code not in CP3_MODELS:
            continue
        order[code] = [f.strip().strip("`") for f in cells.split(",")]
    return order


class TestCP3ContractTableIsReadable:
    """Guard the parser above, so a silent no-op cannot pass as agreement.

    Without these two, a contract table that stopped matching the row regex
    would yield an empty mapping and every order assertion below would pass
    vacuously -- the exact failure mode a contract test exists to prevent.
    """

    def test_all_five_codes_are_found_in_the_contract_table(self):
        order = _contract_field_order()
        assert set(order) == set(CP3_MODELS), (
            "contracts/tools.md section 2's table no longer yields all five "
            "CP3 codes; parsed " + repr(sorted(order))
        )

    def test_every_parsed_row_has_fields(self):
        for code, fields in _contract_field_order().items():
            assert fields, code


class TestCP3FieldOrderMatchesContract:
    """T013 -- declared field order matches contracts/tools.md.

    Order is part of the contract, not an implementation detail: it is the
    order a caller reads the refusal in. A reordered model must fail here.
    """

    @pytest.mark.parametrize("code", sorted(CP3_MODELS))
    def test_declared_field_order_matches_contract(self, code):
        expected = _contract_field_order()[code]
        # error_code is the discriminator and leads every model; the contract
        # table lists only the payload fields that follow it.
        declared = [f for f in CP3_MODELS[code].model_fields if f != "error_code"]
        assert declared == expected, (
            code + ": model declares " + repr(declared)
            + " but contracts/tools.md section 2 specifies " + repr(expected)
        )

    def test_error_code_is_first_in_every_model(self):
        for code, model in CP3_MODELS.items():
            assert list(model.model_fields)[0] == "error_code", code


class TestCP3ExtraFieldsForbidden:
    """T013 -- extra="forbid" on all five."""

    @pytest.mark.parametrize("code", sorted(CP3_MODELS))
    def test_extra_field_is_rejected(self, code):
        bad = dict(CP3_EXAMPLES[code], unexpected_extra_field="x")
        with pytest.raises(pydantic.ValidationError):
            validate_detail(bad)

    @pytest.mark.parametrize("code", sorted(CP3_MODELS))
    def test_contract_example_validates_through_the_union(self, code):
        detail = validate_detail(CP3_EXAMPLES[code])
        assert isinstance(detail, CP3_MODELS[code])


class TestCP3JobFailureEnumIsClosed:
    """`out_of_memory | crashed | cancelled | engine_unavailable |
    id_map_invalid` and nothing else.

    They are kept distinct because the remedies differ: out of memory means
    cut the scope, crashed means read the log, cancelled means it was asked
    to stop and nothing is wrong. CP5 adds the sandbox worker's two (T114):
    the config never loaded into a Morpher, or its id map is invalid.
    """

    @pytest.mark.parametrize(
        "value",
        ["out_of_memory", "crashed", "cancelled", "engine_unavailable", "id_map_invalid"],
    )
    def test_accepts_each_contract_value(self, value):
        detail = validate_detail(
            dict(CP3_EXAMPLES["parser_job_failed"], failure=value)
        )
        assert detail.failure == value

    @pytest.mark.parametrize(
        "value",
        ["timeout", "Crashed", "OUT_OF_MEMORY", "", "engine_missing", "id_map_absent"],
    )
    def test_rejects_anything_else(self, value):
        with pytest.raises(pydantic.ValidationError):
            validate_detail(dict(CP3_EXAMPLES["parser_job_failed"], failure=value))

    @pytest.mark.parametrize("value", ["engine_unavailable", "id_map_invalid"])
    def test_cp5_golden_fixture_validates(self, value):
        """Each CP5 value's golden fixture is a valid detail, in field order."""
        path = (
            Path(__file__).parent / "golden" / "responses"
            / f"parser_job_failed_{value}.json"
        )
        fixture = json.loads(path.read_text(encoding="utf-8"))
        fields = list(ParserJobFailedDetail.model_fields)
        detail = {k: fixture[k] for k in fields}
        assert validate_detail(detail).failure == value
        present = [k for k in fixture if k in fields]
        assert present == fields


class TestCP3IsPurelyAdditive:
    """T014 -- contract version unchanged, and no existing code changed shape."""

    def test_contract_version_is_still_1_0(self):
        assert CONTRACT_VERSION == "tool-responses/1.0", (
            "CP3 adds five codes additively (FR-059). A contract-version bump "
            "would make it a breaking change, which it is not."
        )

    def test_union_carries_all_forty_one_codes(self):
        import typing
        members = typing.get_args(AnyDetail)
        assert len(members) == 41, (
            "expected 41 detail models: CP3's five additions on top of main's "
            "26 (incl. invalid_api_mode), internal_error (#89), CP4's two "
            "(parser_filing_in_progress, grammar_load_unclean), CP5's two "
            "(parser_config_failed, parse_sandbox_refused), #243's three "
            "(session_not_initialized, unknown_tool, invalid_input), "
            "deprecated_member (curated_deprecations.py), and "
            "raw_addcustomfield_write_risk (#70); found "
            + str(len(members))
        )
        for model in CP3_MODELS.values():
            assert model in members

    @pytest.mark.parametrize(
        "code,example",
        [
            ("parser_engine_mismatch", PARSER_ENGINE_MISMATCH_EXAMPLE),
            ("parser_core_missing", PARSER_CORE_MISSING_EXAMPLE),
        ],
    )
    def test_pre_cp3_codes_still_validate_unchanged(self, code, example):
        # The additive claim is only worth making if it is checked: adding a
        # model to a discriminated union can change how a NEIGHBOURING payload
        # resolves if the discriminator is not tight.
        detail = validate_detail(example)
        assert detail.error_code == code

    def test_cp3_codes_do_not_shadow_pre_cp3_codes(self):
        pre_cp3 = validate_detail(PARSER_ENGINE_MISMATCH_EXAMPLE)
        assert not isinstance(pre_cp3, tuple(CP3_MODELS.values()))


# ===========================================================================
# parser-check CP4 -- two additive codes (FR-035; contracts/tools.md s.2)
# ===========================================================================

from flextoolsmcp.server.response_models import (  # noqa: E402
    GrammarLoadUncleanDetail,
    ParserFilingInProgressDetail,
)

_CP4_CONTRACT_PATH = (
    Path(__file__).parent.parent / "specs" / "parser-check-cp4" / "contracts" / "tools.md"
)

CP4_MODELS = {
    "parser_filing_in_progress": ParserFilingInProgressDetail,
    "grammar_load_unclean": GrammarLoadUncleanDetail,
}

#: The parent spec's five grammar_load_unclean fields, in the parent's order
#: (specs/parser-check/SPEC.md section 14). CP4 may only APPEND after them.
PARENT_GRAMMAR_LOAD_UNCLEAN_PREFIX = [
    "signal", "new_error_count", "baseline_error_count", "baseline_source", "log_path",
]

CP4_EXAMPLES = {
    "parser_filing_in_progress": {
        "error_code": "parser_filing_in_progress",
        "run_id": "a" * 32,
        "started_at": "2026-09-24T12:00:00+00:00",
        "words_completed": 12,
        "hint": "Watch it with flextools_parse_status(run_id='" + "a" * 32 + "').",
    },
    "grammar_load_unclean": {
        "error_code": "grammar_load_unclean",
        "signal": "new_load_errors",
        "new_error_count": 2,
        "baseline_error_count": 3,
        "baseline_source": "prior_run:" + "b" * 32,
        "log_path": None,
        "new_errors": [{"type": "InvalidShape"}],
        "dropped_entries": [],
        "baseline_eligible_count": 10,
        "eligible_count": 10,
    },
}

# | `code` *(verbatim)* | fields... |
_CP4_ROW = _re.compile(r"^\|\s*`([a-z_]+)`[^|]*\|\s*(.+?)\s*\|\s*$")


def _cp4_contract_field_order():
    """Field order per CP4 code, read from contracts/tools.md section 2.

    The cells carry prose: "(required str)", "(required: `a` | `b`)", "then,
    appended after the parent's five". Parenthesised asides are removed first,
    so the backticked names left are exactly the fields, in order.
    """
    order = {}
    for line in _CP4_CONTRACT_PATH.read_text(encoding="utf-8").splitlines():
        m = _CP4_ROW.match(line)
        if not m or m.group(1) not in CP4_MODELS:
            continue
        cell = _re.sub(r"\([^()]*\)", "", m.group(2).replace("\\|", "/"))
        order[m.group(1)] = _re.findall(r"`([a-z_]+)`", cell)
    return order


class TestCP4ContractTableIsReadable:
    def test_both_codes_are_found_in_the_contract_table(self):
        assert set(_cp4_contract_field_order()) == set(CP4_MODELS)

    def test_every_parsed_row_has_fields(self):
        for code, fields in _cp4_contract_field_order().items():
            assert len(fields) >= 4, (code, fields)


class TestCP4FieldOrderMatchesContract:
    """FR-035: declared order == the contract row, error_code leading."""

    @pytest.mark.parametrize("code", sorted(CP4_MODELS))
    def test_declared_field_order_matches_contract(self, code):
        expected = _cp4_contract_field_order()[code]
        declared = [f for f in CP4_MODELS[code].model_fields if f != "error_code"]
        assert declared == expected, (code, declared, expected)

    @pytest.mark.parametrize("code", sorted(CP4_MODELS))
    def test_error_code_leads(self, code):
        assert list(CP4_MODELS[code].model_fields)[0] == "error_code"

    def test_the_parent_five_are_a_strict_prefix(self):
        declared = [f for f in GrammarLoadUncleanDetail.model_fields if f != "error_code"]
        assert declared[:5] == PARENT_GRAMMAR_LOAD_UNCLEAN_PREFIX
        assert declared[5:] == [
            "new_errors", "dropped_entries", "baseline_eligible_count", "eligible_count",
        ]


class TestCP4Validation:
    @pytest.mark.parametrize("code", sorted(CP4_MODELS))
    def test_examples_validate_through_the_union(self, code):
        assert isinstance(validate_detail(CP4_EXAMPLES[code]), CP4_MODELS[code])

    @pytest.mark.parametrize("code", sorted(CP4_MODELS))
    def test_extra_fields_are_forbidden(self, code):
        with pytest.raises(pydantic.ValidationError):
            validate_detail(dict(CP4_EXAMPLES[code], override=True))

    @pytest.mark.parametrize("value", ["morpher_null", "new_load_errors", "eligible_forms_dropped"])
    def test_the_three_signals_validate(self, value):
        validate_detail(dict(CP4_EXAMPLES["grammar_load_unclean"], signal=value))

    @pytest.mark.parametrize("value", ["load_errors", "MORPHER_NULL", "override", ""])
    def test_the_signal_enum_is_closed(self, value):
        with pytest.raises(pydantic.ValidationError):
            validate_detail(dict(CP4_EXAMPLES["grammar_load_unclean"], signal=value))

    @pytest.mark.parametrize("value", ["this_run", "absent", "prior_run:" + "c" * 32])
    def test_baseline_source_accepts_the_three_shapes(self, value):
        validate_detail(dict(CP4_EXAMPLES["grammar_load_unclean"], baseline_source=value))

    @pytest.mark.parametrize("value", ["prior_run", "prior_run:xyz", "flex_file", "PRIOR_RUN:" + "c" * 32])
    def test_baseline_source_refuses_anything_else(self, value):
        with pytest.raises(pydantic.ValidationError):
            validate_detail(dict(CP4_EXAMPLES["grammar_load_unclean"], baseline_source=value))

    @pytest.mark.parametrize("field", ["run_id", "started_at", "words_completed", "hint"])
    def test_every_in_progress_field_is_required(self, field):
        data = {k: v for k, v in CP4_EXAMPLES["parser_filing_in_progress"].items() if k != field}
        with pytest.raises(pydantic.ValidationError):
            validate_detail(data)

    def test_contract_version_is_still_1_0(self):
        assert CONTRACT_VERSION == "tool-responses/1.0"


# ===========================================================================
# parser-check CP5 -- two additive codes (contracts/tools.md section 4)
# ===========================================================================

from flextoolsmcp.server.response_models import (  # noqa: E402
    ParserConfigFailedDetail,
    ParseSandboxRefusedDetail,
)

_CP5_CONTRACT_PATH = (
    Path(__file__).parent.parent / "specs" / "parser-check-cp5" / "contracts" / "tools.md"
)

CP5_MODELS = {
    "parser_config_failed": ParserConfigFailedDetail,
    "parse_sandbox_refused": ParseSandboxRefusedDetail,
}

CP5_EXAMPLES = {
    "parser_config_failed": {
        "error_code": "parser_config_failed",
        "exit_code": 1,
        "stderr_tail": "The FieldWorks project is currently open in another application.",
        "log_path": "C:/runs/" + "a" * 32 + "/sandbox/generate-config.log",
        "run_id": "a" * 32,
    },
    "parse_sandbox_refused": {
        "error_code": "parse_sandbox_refused",
        "reason": "insufficient_disk_space",
        "name": None,
        "path": "C:/sandbox/work",
        "hint": "Free some disk space.",
        "needed_bytes": 2048,
        "free_bytes": 1024,
    },
}

# | **`code`** | status | fields... |   (escaped pipes are replaced first)
_CP5_ROW = _re.compile(r"^\|\s*\**`([a-z_]+)`\**\s*\|[^|]*\|\s*(.+?)\s*\|\s*$")
_CP5_REASON_HEADER = "`parse_sandbox_refused.reason` is a closed enum:"
_CP5_REASON_ITEM = _re.compile(r"^-\s*`([a-z_]+)`\s*$")


def _cp5_contract_text():
    return _CP5_CONTRACT_PATH.read_text(encoding="utf-8")


def _cp5_contract_field_order():
    """Field order per CP5 code, read from contracts/tools.md section 4.

    The cells read like "`exit_code` (int \\| null), `stderr_tail` (str)" and
    "`reason` (see below)". Escaped pipes and parenthesised asides are
    removed first, so the backticked names left are exactly the fields.
    """
    order = {}
    for line in _cp5_contract_text().splitlines():
        m = _CP5_ROW.match(line.replace("\\|", "/"))
        if not m or m.group(1) not in CP5_MODELS:
            continue
        cell = _re.sub(r"\([^()]*\)", "", m.group(2))
        order[m.group(1)] = _re.findall(r"`([a-z_]+)`", cell)
    return order


def _cp5_contract_reason_enum():
    """The bulleted reason list that follows the section 4 table."""
    lines = _cp5_contract_text().splitlines()
    start = lines.index(_CP5_REASON_HEADER) + 1
    reasons = []
    for line in lines[start:]:
        m = _CP5_REASON_ITEM.match(line.strip())
        if not m:
            if reasons:
                break
            continue
        reasons.append(m.group(1))
    return reasons


class TestCP5ContractTableIsReadable:
    def test_both_codes_are_found_in_the_contract_table(self):
        assert set(_cp5_contract_field_order()) == set(CP5_MODELS)

    def test_every_parsed_row_has_fields(self):
        for code, fields in _cp5_contract_field_order().items():
            assert len(fields) >= 4, (code, fields)

    def test_the_reason_list_is_found(self):
        assert len(_cp5_contract_reason_enum()) == 9


class TestCP5FieldOrderMatchesContract:
    """Section 4: declared order == the contract row, error_code leading."""

    @pytest.mark.parametrize("code", sorted(CP5_MODELS))
    def test_declared_field_order_matches_contract(self, code):
        expected = _cp5_contract_field_order()[code]
        declared = [f for f in CP5_MODELS[code].model_fields if f != "error_code"]
        assert declared == expected, (code, declared, expected)

    @pytest.mark.parametrize("code", sorted(CP5_MODELS))
    def test_error_code_leads(self, code):
        assert list(CP5_MODELS[code].model_fields)[0] == "error_code"

    def test_the_reason_enum_matches_the_contract_exactly(self):
        import typing
        annotation = ParseSandboxRefusedDetail.model_fields["reason"].annotation
        assert list(typing.get_args(annotation)) == _cp5_contract_reason_enum()


class TestCP5Validation:
    @pytest.mark.parametrize("code", sorted(CP5_MODELS))
    def test_examples_validate_through_the_union(self, code):
        assert isinstance(validate_detail(CP5_EXAMPLES[code]), CP5_MODELS[code])

    @pytest.mark.parametrize("code", sorted(CP5_MODELS))
    def test_extra_fields_are_forbidden(self, code):
        with pytest.raises(pydantic.ValidationError):
            validate_detail(dict(CP5_EXAMPLES[code], override=True))

    def test_config_failed_exit_code_and_run_id_are_nullable(self):
        # exit_code is null when the generator never returned one; run_id is
        # null only when generation failed before a run existed.
        detail = validate_detail(
            dict(CP5_EXAMPLES["parser_config_failed"], exit_code=None, run_id=None)
        )
        assert detail.exit_code is None and detail.run_id is None

    @pytest.mark.parametrize("field", ["stderr_tail", "log_path"])
    def test_config_failed_required_fields(self, field):
        data = {k: v for k, v in CP5_EXAMPLES["parser_config_failed"].items() if k != field}
        with pytest.raises(pydantic.ValidationError):
            validate_detail(data)

    @pytest.mark.parametrize("field", ["reason", "hint"])
    def test_sandbox_refused_required_fields(self, field):
        data = {k: v for k, v in CP5_EXAMPLES["parse_sandbox_refused"].items() if k != field}
        with pytest.raises(pydantic.ValidationError):
            validate_detail(data)

    @pytest.mark.parametrize(
        "value", ["name_taken", "SANDBOX_EXISTS", "disk_full", "runtime_error", ""]
    )
    def test_the_reason_enum_is_closed(self, value):
        with pytest.raises(pydantic.ValidationError):
            validate_detail(dict(CP5_EXAMPLES["parse_sandbox_refused"], reason=value))

    def test_contract_version_is_still_1_0(self):
        assert CONTRACT_VERSION == "tool-responses/1.0"
