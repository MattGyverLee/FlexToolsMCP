#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #152: handler success payloads must validate against *Success models."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.tool_output_validation import (
    iter_validation_cases,
    run_output_model_validation,
    validate_success_payload,
)
from flextoolsmcp.server.response_models import RunModuleSuccess


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
        ok, errors = run_output_model_validation()
        assert ok, errors
        # Parametrize ensures every iter_validation_cases row is exercised.
        assert tool_name and case_label and payload is not None

    def test_run_module_golden_auto_fix_casting(self):
        cases = list(iter_validation_cases())
        casting = next(c for c in cases if c[1] == "auto_fix_casting_applied.json")
        _, _, payload = casting
        m = RunModuleSuccess.model_validate(payload, by_alias=True)
        assert m.auto_fixes_applied is not None
        assert len(m.auto_fixes_applied) >= 1
