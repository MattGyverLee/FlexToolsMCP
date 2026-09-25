#!/usr/bin/env python3
"""Issue #70: refuse raw AddCustomField on write-enabled runs."""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import detect_raw_addcustomfield_risk


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _boom_lock(*_a, **_k):
    raise AssertionError("get_project_write_lock must NOT be called")


def _boom_subprocess(*_a, **_k):
    raise AssertionError("run_script_async must NOT be called")


def _stub_env(monkeypatch, tmp_path, *, is_cud=True):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(
        execution_mod,
        "validate_server_state",
        lambda: {"is_healthy": True, "issues": []},
    )
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
        lambda code: {"is_cud": is_cud, "operations": ["CREATE"] if is_cud else []},
    )
    monkeypatch.setattr(
        execution_mod,
        "detect_casting_needs",
        lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []},
    )


async def _fake_run_script_async_ok(path, timeout_seconds):
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


class TestDetectRawAddCustomFieldRisk:
    def test_addcustomfield_call_flagged(self):
        code = "mdc.AddCustomField('LexEntry', 'Probe', 1, 0)\n"
        result = detect_raw_addcustomfield_risk(code)
        assert result["has_raw_addcustomfield_risk"] is True
        assert len(result["findings"]) == 1

    def test_field_ws_zero_with_save_notes_hang(self):
        code = (
            "mdc.AddCustomField('LexEntry', 'Probe', 1, 0, 'help', 0, guid)\n"
            "usm.Save()\n"
        )
        result = detect_raw_addcustomfield_risk(code)
        assert result["has_raw_addcustomfield_risk"] is True
        assert result["has_undo_stack_save"] is True
        assert result["findings"][0]["field_ws_zero"] is True
        assert "issue #70" in result["findings"][0]["detail"]

    def test_createfield_not_flagged(self):
        code = "project.CustomFields.CreateField('LexEntry', 'Probe', 'Integer')\n"
        result = detect_raw_addcustomfield_risk(code)
        assert result["has_raw_addcustomfield_risk"] is False

    def test_syntax_error_returns_empty(self):
        result = detect_raw_addcustomfield_risk("def (:\n")
        assert result["has_raw_addcustomfield_risk"] is False
        assert result["findings"] == []


class TestIssue70GateWiring:
    def test_write_enabled_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": (
                "mdc.AddCustomField('LexEntry', 'Probe', 1, 0, 'help', 0, list_root)\n"
                "usm.Save()\n"
            ),
            "project_name": "TestProj_acf1",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "raw_addcustomfield_write_risk"
        assert data["findings"]

    def test_read_only_not_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path, is_cud=False)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)

        args = {
            "code": "mdc.AddCustomField('LexEntry', 'Probe', 1, 0)\n",
            "project_name": "TestProj_acf_ro",
            "write_enabled": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "raw_addcustomfield_write_risk"
