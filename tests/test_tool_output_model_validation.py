#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #152: handler success payloads must validate against *Success models.

Phase 2 (#369, ruling R2): the get_object_api / search_by_capability cases
are real payloads captured from the actual handlers (fake index data, real
handler code paths -- see flextoolsmcp.tool_output_validation), and each
parametrized case validates ITS OWN payload against its tool's model.
The pre-Phase-2 version re-ran the whole validation for every case and
never validated the parametrized payload at all, and its "minimal"
fixtures carried invented keys (``entity``/``matches``) the handlers
never emit.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.tool_output_validation import (
    iter_validation_cases,
    run_output_model_validation,
)
from flextoolsmcp.server.response_models import (
    GetObjectApiSuccess,
    RunModuleSuccess,
    SearchByCapabilitySuccess,
)

_MODELS = {
    "flextools_run_module": RunModuleSuccess,
    "flextools_get_object_api": GetObjectApiSuccess,
    "flextools_search_by_capability": SearchByCapabilitySuccess,
}


class TestToolOutputModelValidation:
    def test_integrity_runner_passes(self):
        ok, errors = run_output_model_validation()
        assert ok, "\n".join(errors)

    @pytest.mark.parametrize(
        "tool_name,case_label,payload",
        [
            (tool, label, data)
            for tool, label, data in iter_validation_cases()
        ],
    )
    def test_each_case_validates(self, tool_name, case_label, payload):
        # Validate THIS case's payload against THIS tool's model -- the
        # pre-Phase-2 body ignored `payload` entirely.
        model = _MODELS[tool_name]
        validated = model.model_validate(payload, by_alias=True)
        assert validated.status == "ok", (tool_name, case_label)
        assert validated.contract == "tool-responses/1.0", (tool_name, case_label)

    def test_run_module_golden_auto_fix_casting(self):
        cases = list(iter_validation_cases())
        casting = next(c for c in cases if c[1] == "auto_fix_casting_applied.json")
        _, _, payload = casting
        m = RunModuleSuccess.model_validate(payload, by_alias=True)
        assert m.auto_fixes_applied is not None
        assert len(m.auto_fixes_applied) >= 1

    def test_real_get_object_api_payloads_carry_envelope_and_traced_keys(self):
        cases = {
            label: payload
            for tool, label, payload in iter_validation_cases()
            if tool == "flextools_get_object_api"
        }
        assert set(cases) == {"real:found", "real:not_found"}
        found = cases["real:found"]
        # Regression for the handlers/api.py shadowing bug (#369 R2.1):
        # real payloads carry the TOOL-CONTRACT success envelope...
        assert found["status"] == "ok"
        assert found["_contract"] == "tool-responses/1.0"
        # ...and the always-present traced keys.
        assert found["object_type"] == "FakeWidget"
        assert found["found"] is True
        assert found["api_mode"] == "flexicon"
        assert "flexicon" in found
        not_found = cases["real:not_found"]
        assert not_found["status"] == "ok"
        assert not_found["_contract"] == "tool-responses/1.0"
        assert not_found["found"] is False
        assert "message" in not_found

    def test_real_search_payload_carries_traced_keys(self):
        cases = [
            payload
            for tool, _label, payload in iter_validation_cases()
            if tool == "flextools_search_by_capability"
        ]
        assert len(cases) == 1
        (payload,) = cases
        assert payload["status"] == "ok"
        assert payload["_contract"] == "tool-responses/1.0"
        for key in (
            "query", "api_mode", "api_mode_description", "search_method",
            "sources_searched", "fallback_used", "semantic_available",
            "results_count", "canonical_matches", "results",
            "worked_examples", "worked_examples_count", "recipes",
            "recipes_count", "recipes_ambiguous",
        ):
            assert key in payload, key
        # The fake index's GetGloss method is a real keyword hit.
        assert payload["results_count"] >= 1
        assert payload["results"][0]["name"] == "GetGloss"
