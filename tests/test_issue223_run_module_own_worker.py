#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #223: run_module must release our idle parse read worker before write."""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_access, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.handlers import parse as parse_mod
from flextoolsmcp.server.project_access import LockHolder, ProjectAccess
from flextoolsmcp.server.parse.worker_client import SHARED_ROLE


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _access(verdict, *, pid=31337, process="python", sharing=True):
    holder = LockHolder(pid=pid, process_name=process, timestamp_ticks=None)
    return ProjectAccess(
        project_name="TestProj",
        verdict=verdict,
        sharing_enabled=sharing,
        holder=holder,
        lock_age_seconds=None,
    )


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


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


class _FakeRunner:
    def __init__(self, own_pid=31337):
        self.own_pid = own_pid
        self.released = []

    def read_worker_pid(self, project_name):
        return self.own_pid

    async def release_worker(self, project, *, role):
        self.released.append((project, role))


def _stub_env(monkeypatch, tmp_path, runner):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(
        project_discovery,
        "check_project_locked",
        lambda name: tmp_path / f"{name}.fwdata.lock",
    )
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
        lambda code: {"is_cud": True, "operations": ["CREATE (Create())"]},
    )
    monkeypatch.setattr(
        execution_mod,
        "detect_casting_needs",
        lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []},
    )
    monkeypatch.setattr(parse_mod, "get_runner", lambda: runner)
    monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
    monkeypatch.setattr(
        execution_mod,
        "perform_pre_write_backup",
        lambda name, **k: {
            "path": None,
            "created": False,
            "skipped_reason": "backup_before_write=false",
        },
    )


WRITE_ARGS = {
    "code": "if modifyAllowed:\n    project.LexEntry.SetLexemeForm(entry, 'x')\n",
    "write_enabled": True,
    "confirmed": True,
    "skip_api_check": True,
    "skip_module_check": True,
}


def test_own_read_worker_is_released_then_write_proceeds(monkeypatch, tmp_path):
    runner = _FakeRunner()
    _stub_env(monkeypatch, tmp_path, runner)
    calls = []

    def probe(name):
        calls.append(name)
        if len(calls) == 1:
            return _access("held_by_other")
        return _access("free", pid=None, process=None, sharing=True)

    monkeypatch.setattr(project_access, "probe_project_access", probe)

    data = _parse(asyncio.run(execution_mod.handle_run_module(
        dict(WRITE_ARGS, project_name="TestProj")
    )))
    assert data.get("error_code") is None
    assert runner.released == [("TestProj", SHARED_ROLE)]
    assert len(calls) == 2


def test_foreign_python_holder_still_refuses(monkeypatch, tmp_path):
    runner = _FakeRunner(own_pid=11111)
    _stub_env(monkeypatch, tmp_path, runner)
    monkeypatch.setattr(
        project_access,
        "probe_project_access",
        lambda name: _access("held_by_other", pid=4242),
    )

    data = _parse(asyncio.run(execution_mod.handle_run_module(
        dict(WRITE_ARGS, project_name="TestProj")
    )))
    assert data["error_code"] == "project_locked"
    assert data["verdict"] == "held_by_other"
    assert runner.released == []
