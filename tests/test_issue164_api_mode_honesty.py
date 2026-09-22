#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #164: api_mode must not silently fall back to flexicon guidance."""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.constants import API_MODES, EXECUTION_API_MODE
from flextoolsmcp.server.handlers import admin as admin_mod
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server import session as session_mod


def _stub_run_module_env(monkeypatch, tmp_path):
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
        lambda code: {"is_cud": False, "operations": []},
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


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


@pytest.fixture(autouse=True)
def _fresh_session():
    admin_mod.session_state = session_mod.SessionState()
    execution_mod.session_state = admin_mod.session_state
    yield
    admin_mod.session_state = session_mod.SessionState()
    execution_mod.session_state = admin_mod.session_state


@pytest.fixture(autouse=True)
def _bypass_project_resolution(monkeypatch):
    monkeypatch.setattr(
        admin_mod,
        "resolve_or_explain",
        lambda name: (name, None),
    )


class TestIssue164ApiModeHonesty:
    def test_unknown_api_mode_is_rejected_without_configuring_session(self):
        before_id = admin_mod.session_state.session_id
        data = _parse(asyncio.run(admin_mod.handle_start({"api_mode": "not_a_mode"})))

        assert data["status"] == "error"
        assert data["error_code"] == "invalid_api_mode"
        assert data["allowed_modes"] == list(API_MODES)
        assert data["received"] == "not_a_mode"
        assert admin_mod.session_state.session_id == before_id
        assert admin_mod.session_state.initialized is False

    def test_liblcm_mode_keeps_session_but_surfaces_execution_seam(self):
        data = _parse(asyncio.run(admin_mod.handle_start({"api_mode": "liblcm"})))

        assert data["status"] != "error"
        assert admin_mod.session_state.api_mode == "liblcm"
        mode_info = data["mode_info"]
        assert mode_info["selected_api_mode"] == "liblcm"
        assert mode_info["execution_api_mode"] == EXECUTION_API_MODE
        assert "flextools_run_module" in mode_info["execution_note"]
        assert any("documentation/preflight" in w for w in data.get("warnings", []))

    def test_flexicon_mode_info_still_documents_execution_seam(self):
        data = _parse(asyncio.run(admin_mod.handle_start({"api_mode": "flexicon"})))

        mode_info = data["mode_info"]
        assert mode_info["selected_api_mode"] == "flexicon"
        assert mode_info["execution_api_mode"] == EXECUTION_API_MODE
        assert not any("documentation/preflight" in w for w in data.get("warnings", []))

    def test_run_module_preflight_warns_when_session_mode_is_not_flexicon(self, monkeypatch, tmp_path):
        admin_mod.session_state.configure(api_mode="liblcm", project_name="Proj164")
        _stub_run_module_env(monkeypatch, tmp_path)

        class _FakeLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

        monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda *_a, **_k: _FakeLock())
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
        monkeypatch.setattr(execution_mod, "_probe_undoable_capability", lambda: False)

        args = {
            "code": "report.Info('probe')",
            "project_name": "Proj164",
            "write_enabled": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))

        warnings = data.get("warnings") or []
        assert any("[api_mode]" in w for w in warnings)
