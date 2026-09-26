#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #277: reflection bypass preflight gate."""

import asyncio
import json

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import detect_reflection_bypass


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


class TestDetectReflectionBypass:
    def test_operator_methodcaller(self):
        code = (
            "import operator\n"
            "if modifyAllowed:\n"
            '    operator.methodcaller("Add", pub)(sense_rc)\n'
        )
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]
        assert result["reflection_bypass_count"] == 1
        assert result["findings"][0]["kind"] == "operator.methodcaller"

    def test_importlib_lcmodule(self):
        code = 'import importlib\nlcm = importlib.import_module("SIL.LCModel")\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]
        assert any(f["kind"] == "importlib.import_module" for f in result["findings"])

    def test_setattr_lcm_member(self):
        code = 'if modifyAllowed:\n    setattr(rhs, "RightContextOA", seq)\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]
        assert any("RightContextOA" in f.get("expr", "") for f in result["findings"])

    def test_string_literal_in_comment_not_flagged(self):
        code = '# operator.methodcaller("Add")(x)\nreport.Info("ok")\n'
        result = detect_reflection_bypass(code)
        assert not result["has_reflection_bypass"]

    def test_getattr_lowercase_not_flagged(self):
        code = 'getattr(obj, "lower_name")\n'
        result = detect_reflection_bypass(code)
        assert not result["has_reflection_bypass"]


def _stub_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod,
        "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
            "confidence": "high",
        },
    )
    monkeypatch.setattr(
        execution_mod,
        "detect_cud_operations",
        lambda code: {"is_cud": True, "operations": ["UPDATE"]},
    )
    monkeypatch.setattr(
        execution_mod,
        "detect_casting_needs",
        lambda code, ci, tree, api_index=None: {"has_casting_issues": False, "casting_issues": []},
    )


class TestGateWiring:
    def test_write_enabled_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod,
            "get_project_write_lock",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no lock")),
        )
        monkeypatch.setattr(
            execution_mod,
            "run_script_async",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subprocess")),
        )
        args = {
            "code": 'import operator\noperator.methodcaller("set_String", ws, t)(ms)\n',
            "project_name": "TestProj_refl",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))
        assert data["error_code"] == "reflection_bypass_detected"
        assert data.get("reflection_bypass_count", 0) >= 1

    def test_read_only_not_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod,
            "detect_cud_operations",
            lambda code: {"is_cud": False, "operations": []},
        )

        async def _fake_run(*a, **k):
            payload = {
                "success": True,
                "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
                "messages": [],
            }
            return {
                "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
                "stderr": "",
                "timeout": False,
                "returncode": 0,
            }

        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)
        monkeypatch.setattr(
            execution_mod,
            "get_project_write_lock",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no lock on read-only")),
        )
        args = {
            "code": 'import operator\noperator.methodcaller("Add", x)(y)\n',
            "project_name": "TestProj_refl_ro",
            "write_enabled": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))
        assert data.get("error_code") != "reflection_bypass_detected"
