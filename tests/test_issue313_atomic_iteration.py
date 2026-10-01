#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #313: iterating an *OA / *RA (single-object) property.

`for hf in entry.LexemeFormOA:` raises "'IMoForm' object is not iterable".
Preflight used to emit only a warning-tier casting advisory on LexemeFormOA
(the wrong diagnosis); it now hard-rejects with atomic_property_iteration,
and the runtime error carries a matching hint.
"""

import ast
import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    detect_atomic_property_iteration,
    detect_not_iterable_error,
)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


# ---------------------------------------------------------------------------
# Static detector
# ---------------------------------------------------------------------------

class TestDetectAtomicPropertyIteration:
    def test_for_loop_over_lexeme_form_flagged_with_sibling(self):
        code = (
            "for entry in project.LexEntry.GetAll():\n"
            "    for hf in entry.LexemeFormOA:\n"
            "        report.Info(str(hf))\n"
        )
        result = detect_atomic_property_iteration(code)
        assert result["has_atomic_iteration"] is True
        [finding] = result["findings"]
        assert finding["line"] == 2
        assert finding["property"] == "LexemeFormOA"
        assert finding["expr"] == "entry.LexemeFormOA"
        assert finding["kind"] == "owning_atomic"
        assert finding["list_sibling"] == "AlternateFormsOS"
        assert "Owning-Atomic" in finding["suggestion"]
        assert "list(entry.AlternateFormsOS)" in finding["suggestion"]
        assert "LexemeFormOA" in result["message"]
        assert any("AlternateFormsOS" in s for s in result["next_steps"])

    def test_reference_atomic_flagged(self):
        code = "for pos in analysis.CategoryRA:\n    pass\n"
        [finding] = detect_atomic_property_iteration(code)["findings"]
        assert finding["kind"] == "reference_atomic"
        assert finding["property"] == "CategoryRA"
        assert "Reference-Atomic" in finding["suggestion"]
        assert "list_sibling" not in finding

    def test_async_for_flagged(self):
        code = "async def f(e):\n    async for x in e.LexemeFormOA:\n        pass\n"
        assert detect_atomic_property_iteration(code)["has_atomic_iteration"] is True

    @pytest.mark.parametrize("code", [
        "forms = [f for f in entry.LexemeFormOA]\n",
        "forms = {f: 1 for f in entry.LexemeFormOA}\n",
        "forms = list(entry.LexemeFormOA)\n",
        "n = len(sense.MorphoSyntaxAnalysisRA)\n",
        "for i, f in enumerate(entry.LexemeFormOA):\n    pass\n",
        "s = sorted(obj.FooOA)\n",
    ])
    def test_comprehension_and_builtin_args_flagged(self, code):
        assert detect_atomic_property_iteration(code)["has_atomic_iteration"] is True

    @pytest.mark.parametrize("code", [
        "for f in entry.AlternateFormsOS:\n    pass\n",
        "for s in entry.SensesOS:\n    pass\n",
        "lf = entry.LexemeFormOA\nif lf is not None:\n    report.Info(str(lf))\n",
        "for x in obj.DATA:\n    pass\n",
        "for x in obj.ERA:\n    pass\n",
        "forms = [entry.LexemeFormOA] + list(entry.AlternateFormsOS)\n",
        "for x in LexemeFormOA:\n    pass\n",  # bare name, not an attribute
        "x = 'for hf in entry.LexemeFormOA:'\n",  # string literal
        "def (:\n",  # syntax error -> empty
    ])
    def test_not_flagged(self, code):
        result = detect_atomic_property_iteration(code)
        assert result["has_atomic_iteration"] is False
        assert result["findings"] == []

    def test_accepts_prebuilt_tree(self):
        code = "for hf in entry.LexemeFormOA:\n    pass\n"
        assert detect_atomic_property_iteration(code, ast.parse(code))["has_atomic_iteration"]


class TestDetectNotIterableError:
    def test_specific_hint_when_code_iterates_atomic(self):
        code = "for hf in entry.LexemeFormOA:\n    pass\n"
        info = detect_not_iterable_error(
            "Execution error: 'IMoForm' object is not iterable\nTraceback ...", code
        )
        assert info["is_not_iterable_error"] is True
        assert info["is_atomic_iteration_error"] is True
        assert info["object_type"] == "IMoForm"
        assert info["property"] == "LexemeFormOA"
        assert info["line"] == 1
        assert "AlternateFormsOS" in info["suggestion"]

    def test_generic_hint_without_static_finding(self):
        code = "lf = entry.LexemeFormOA\nfor hf in lf:\n    pass\n"
        info = detect_not_iterable_error("'IMoForm' object is not iterable", code)
        assert info["is_not_iterable_error"] is True
        assert info["is_atomic_iteration_error"] is False
        assert info["object_type"] == "IMoForm"
        assert info["property"] is None
        assert "OS/OC/RS/RC" in info["suggestion"]
        assert "OA" in info["suggestion"]

    def test_unrelated_error(self):
        info = detect_not_iterable_error("NameError: name 'x' is not defined", "x\n")
        assert info["is_not_iterable_error"] is False


# ---------------------------------------------------------------------------
# Casting defense in depth
# ---------------------------------------------------------------------------

def test_casting_decision_drops_issue_on_iterated_atomic(monkeypatch):
    code = "for hf in entry.LexemeFormOA:\n    x = entry.Gloss\n"
    monkeypatch.setattr(
        execution_mod, "_detect_casting_needs_compat",
        lambda code, casting_index, tree, api_idx: {
            "has_casting_issues": True,
            "casting_issues": [
                {"property": "LexemeFormOA", "line": 1, "severity": "warning"},
                {"property": "Gloss", "line": 2, "severity": "error"},
            ],
            "severity": "error",
        },
    )
    monkeypatch.setattr(
        execution_mod, "detect_interface_attribute_typos",
        lambda tree, api_idx: {"has_typos": False, "issues": []},
    )
    check = execution_mod._compute_casting_decision(code, None, ast.parse(code), None)
    assert [i["property"] for i in check["casting_issues"]] == ["Gloss"]
    assert check["has_casting_issues"] is True


# ---------------------------------------------------------------------------
# validate_only gate
# ---------------------------------------------------------------------------

class TestValidateOnlyGate:
    def _checks(self, code, *, write_enabled=False):
        return execution_mod._build_validate_only_checks(
            code=code,
            code_tree=ast.parse(code),
            syntax_error=None,
            api_idx=None,
            session_state_obj=object(),
            write_enabled=write_enabled,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )[0]

    @pytest.mark.parametrize("write_enabled", [False, True])
    def test_gate_fails(self, write_enabled):
        code = "for entry in project.LexEntry.GetAll():\n    for hf in entry.LexemeFormOA:\n        pass\n"
        checks = self._checks(code, write_enabled=write_enabled)
        gate = next(c for c in checks if c["gate"] == "atomic_property_iteration")
        assert gate["passed"] is False
        assert gate["issues"][0]["property"] == "LexemeFormOA"
        assert gate["message"]
        assert gate["next_steps"]

    def test_gate_passes(self):
        code = "for entry in project.LexEntry.GetAll():\n    for f in entry.AlternateFormsOS:\n        pass\n"
        gate = next(c for c in self._checks(code) if c["gate"] == "atomic_property_iteration")
        assert gate == {"gate": "atomic_property_iteration", "passed": True}


# ---------------------------------------------------------------------------
# run_module: hard block + runtime hint
# ---------------------------------------------------------------------------

def _boom(*a, **k):
    raise AssertionError("must not get past preflight")


def _stub_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom)
    monkeypatch.setattr(execution_mod, "run_script_async", _boom)


class TestRunModule:
    @pytest.mark.parametrize("write_enabled", [False, True])
    def test_rejects_atomic_iteration_not_casting(self, monkeypatch, tmp_path, write_enabled):
        _stub_env(monkeypatch, tmp_path)
        # Casting must never be consulted for this code: the gate runs first.
        monkeypatch.setattr(execution_mod, "_compute_casting_decision", _boom)
        args = {
            "code": (
                "for entry in project.LexEntry.GetAll():\n"
                "    for hf in entry.LexemeFormOA:\n"
                "        report.Info(str(hf))\n"
            ),
            "project_name": "TestProj_313",
            "write_enabled": write_enabled,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(run_async(execution_mod.handle_run_module(args)))
        assert data["status"] == "error"
        assert data["error_code"] == "atomic_property_iteration"
        assert data["error_code"] != "casting_issues_detected"
        assert data["findings"][0]["property"] == "LexemeFormOA"
        assert data["findings"][0]["list_sibling"] == "AlternateFormsOS"
        assert "AlternateFormsOS" in "\n".join(data["next_steps"])

    def test_runtime_not_iterable_gets_hint(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)

        async def _fake_run(path, timeout_seconds):
            payload = {
                "success": False,
                "error": "Execution error: 'IMoForm' object is not iterable",
                "summary": {"info_count": 0, "warning_count": 0, "error_count": 1},
                "messages": [],
            }
            return {"stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
                    "stderr": "", "timeout": False, "returncode": 0}

        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)
        args = {
            # Aliased: not statically detectable, so the generic hint applies.
            "code": (
                "for entry in project.LexEntry.GetAll():\n"
                "    lf = entry.LexemeFormOA\n"
                "    for hf in lf:\n"
                "        report.Info(str(hf))\n"
            ),
            "project_name": "TestProj_313b",
            "write_enabled": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(run_async(execution_mod.handle_run_module(args)))
        assert data.get("error_type") == "NotIterableError", data
        assert data.get("object_type") == "IMoForm"
        assert "OS/OC/RS/RC" in data.get("help", "")
