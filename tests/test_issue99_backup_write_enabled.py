#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #99: pre-write backup must not depend on preflight classifying the script
as mutating (needs_lock). write_enabled runs can commit LCM actions even when
is_mutating_script is False; backup must still fire once per (session, project),
and every write_enabled response must carry an explicit backup outcome.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server import kernel, project_discovery


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


@pytest.fixture(autouse=True)
def _bypass_project_resolution(monkeypatch):
    monkeypatch.setattr(
        "flextoolsmcp.server.handlers.admin.resolve_or_explain",
        lambda name: (name, None),
    )
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))


def _stub_write_enabled_non_mutating_preflight(monkeypatch, tmp_path):
    """Preflight says read-only (needs_lock=False) but write_enabled=True."""
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod,
        "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "protected_calls": [],
            "unprotected_liblcm_calls": [],
            "protected_liblcm_calls": [],
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
        lambda code, ci, tree, api_index=None: {"has_casting_issues": False, "casting_issues": []},
    )


class TestIssue99BackupWriteEnabled:
    def test_backup_runs_when_needs_lock_false_but_write_enabled(self, monkeypatch, tmp_path):
        _stub_write_enabled_non_mutating_preflight(monkeypatch, tmp_path)

        backup_calls = []

        def _fake_backup(name, **kwargs):
            backup_calls.append(name)
            return {"path": "/tmp/fake.fwdata", "created": True, "skipped_reason": None}

        monkeypatch.setattr(execution_mod, "perform_pre_write_backup", _fake_backup)

        async def _fake_run_script_async(path, timeout_seconds):
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

        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async)

        args = {
            "code": "report.Info('read-only probe')\n",
            "project_name": "SwahiliProbe",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)

        assert data.get("success") is True
        assert backup_calls == ["SwahiliProbe"], (
            "backup must run on write_enabled even when preflight needs_lock is False"
        )
        assert data["backup"]["created"] is True

    def test_write_enabled_response_always_includes_backup(self, monkeypatch, tmp_path):
        _stub_write_enabled_non_mutating_preflight(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod,
            "perform_pre_write_backup",
            lambda name, **k: {"path": None, "created": False, "skipped_reason": "project_fwdata_not_found"},
        )

        async def _fake_run_script_async(path, timeout_seconds):
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

        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async)

        args = {
            "code": "pass\n",
            "project_name": "NoFwdata",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))
        assert "backup" in data
        assert data["backup"]["created"] is False
        assert data["backup"]["skipped_reason"] == "project_fwdata_not_found"

    def test_second_run_surfaces_already_backed_up(self, monkeypatch, tmp_path):
        _stub_write_enabled_non_mutating_preflight(monkeypatch, tmp_path)
        calls = []

        def _fake_backup(name, **k):
            calls.append(name)
            return {"path": "/tmp/x.fwdata", "created": True, "skipped_reason": None}

        monkeypatch.setattr(execution_mod, "perform_pre_write_backup", _fake_backup)

        async def _fake_run_script_async(path, timeout_seconds):
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

        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async)

        base_args = {
            "code": "pass\n",
            "project_name": "Twice",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        _parse(asyncio.run(execution_mod.handle_run_module(base_args)))
        data2 = _parse(asyncio.run(execution_mod.handle_run_module(base_args)))

        assert calls == ["Twice"]
        assert data2["backup"]["skipped_reason"] == "already_backed_up_this_session"
