#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #307: no polymorphic (cast) hint for receivers a cast cannot fix.

`'ILcmServiceLocator' object has no attribute 'GetInstance'` (the C# generic
GetInstance<T>()), `'str' object has no attribute 'values'` and similar were
classified as PolymorphicAttributeError and told to cast / resolve_property.
A service locator, factory, repository, Python value or flexicon wrapper has
no concrete subclass to cast to, so the hint could never be satisfied.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.diagnostic import offered_store
from flextoolsmcp.server.handlers import diagnostic_report
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    detect_non_castable_attribute_error,
    detect_polymorphic_error,
)

GETINSTANCE_ERR = "AttributeError: 'ILcmServiceLocator' object has no attribute 'GetInstance'"


# --- detector level -------------------------------------------------------


def test_service_locator_getinstance_not_polymorphic():
    result = detect_polymorphic_error(GETINSTANCE_ERR)
    assert result["is_polymorphic_error"] is False
    assert result["object_type"] == "ILcmServiceLocator"
    assert result["property_name"] == "GetInstance"


def test_service_locator_getinstance_gets_lookup_guidance():
    result = detect_non_castable_attribute_error(GETINSTANCE_ERR)
    assert result["is_non_castable"] is True
    assert result["is_service_lookup"] is True
    assert result["receiver_kind"] == "lcm_service"
    suggestion = result["suggestion"]
    assert "GetInstance[IFooFactory]()" in suggestion
    assert "project.GetFactory(IFooFactory)" in suggestion
    assert "ServiceLocator.GetService(IFooFactory)" in suggestion
    assert "resolve_property" not in suggestion
    assert "cast_to_concrete" not in suggestion
    assert "resubmit" not in suggestion.lower()


@pytest.mark.parametrize(
    "error, kind",
    [
        ("'str' object has no attribute 'values'", "python_builtin"),
        ("'str' object has no attribute 'get_String'", "python_builtin"),
        ("'NoneType' object has no attribute 'SensesOS'", "python_builtin"),
        ("'FLExProject' object has no attribute 'LexEntries'", "not_lcm_interface"),
        ("'ILexEntryFactory' object has no attribute 'CreateEntry'", "lcm_service"),
        ("'ILexEntryRepository' object has no attribute 'AllInstancesX'", "lcm_service"),
    ],
)
def test_non_castable_receivers_not_polymorphic(error, kind):
    assert detect_polymorphic_error(error)["is_polymorphic_error"] is False
    result = detect_non_castable_attribute_error(error)
    assert result["is_non_castable"] is True
    assert result["receiver_kind"] == kind
    assert result["is_service_lookup"] is False
    assert "cast_to_concrete" not in result["suggestion"]
    assert "resolve_property" not in result["suggestion"]


def test_abstract_model_interface_still_polymorphic():
    error = "'ICmObject' object has no attribute 'HeadWord'"
    assert detect_non_castable_attribute_error(error)["is_non_castable"] is False
    result = detect_polymorphic_error(error)
    assert result["is_polymorphic_error"] is True
    assert result["object_type"] == "ICmObject"


def test_lcmcache_redundant_hop_unaffected():
    # #108's special case runs before the #307 receiver check.
    result = detect_polymorphic_error("'LcmCache' object has no attribute 'Cache'")
    assert result["is_polymorphic_error"] is True
    assert result["rewrite"] == "project.project"


# --- handle_run_module wiring --------------------------------------------


def _stub_env(monkeypatch, tmp_path, error):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {"is_certified_readonly": True, "confidence": 1.0, "mutating_calls": []},
    )
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs",
        lambda code, idx, tree: {"has_casting_issues": False, "casting_issues": [], "severity": "none"},
    )
    session_log = tmp_path / "session.log"
    session_log.write_text("", encoding="utf-8")
    monkeypatch.setattr(kernel, "get_current_session_log_path", lambda: session_log)
    monkeypatch.setattr(diagnostic_report, "get_current_session_log_path", lambda: session_log)
    monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: tmp_path / "reports")
    monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(offered_store, "get_reports_dir", lambda: tmp_path / "offered_state")

    async def _fake_run(script_path, timeout_seconds=300):
        payload = {"success": False, "error": error}
        stdout = "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload)
        return {"stdout": stdout, "stderr": "", "returncode": 0, "timeout": False}

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)


def _run(monkeypatch, tmp_path, error):
    _stub_env(monkeypatch, tmp_path, error)
    args = {
        # run_script_async is mocked; the code only has to clear static preflight.
        "code": "report.Info('probe')",
        "project_name": "TestProject",
        "write_enabled": False,
        "skip_module_check": True,
        "skip_api_check": True,
    }
    result = asyncio.run(execution_mod.handle_run_module(args))
    return json.loads(result[0].text)


def test_handler_getinstance_emits_service_lookup_guidance(monkeypatch, tmp_path):
    payload = _run(monkeypatch, tmp_path, GETINSTANCE_ERR)
    assert payload.get("error_type") == "ServiceLookupAttributeError"
    assert not payload.get("polymorphic_error_detected")
    assert "GetInstance[IFooFactory]()" in payload.get("help", "")
    assert "cast_to_concrete" not in payload.get("help", "")


def test_handler_str_receiver_no_polymorphic_hint(monkeypatch, tmp_path):
    payload = _run(monkeypatch, tmp_path, "AttributeError: 'str' object has no attribute 'values'")
    assert payload.get("error_type") != "PolymorphicAttributeError"
    assert not payload.get("polymorphic_error_detected")
    assert "plain Python 'str'" in payload.get("help", "")


def test_handler_abstract_interface_keeps_polymorphic_hint(monkeypatch, tmp_path):
    payload = _run(monkeypatch, tmp_path, "AttributeError: 'ICmObject' object has no attribute 'HeadWord'")
    assert payload.get("error_type") == "PolymorphicAttributeError"
    assert payload.get("polymorphic_error_detected") is True
