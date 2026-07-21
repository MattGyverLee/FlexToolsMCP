#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #55: Write-path safety ladder -- undoable by default (Rung 1),
automatic pre-write backup (Rung 2), enforced mutation confirmation (Rung 3).

Covers each rung's acceptance criteria:
- Rung 1: start(write_enabled=True) -> undoable active; explicit
  undoable=False respected; same-project restart inherits prior value.
- Rung 2: perform_pre_write_backup() creates/retains/opts-out/skips-on-low-disk;
  session_state.was_backed_up/record_backup track per-(session, project);
  wired so the FIRST confirmed mutating run backs up, the second does not.
- Rung 3: a mutating run without confirmed=True is refused
  (confirmation_required + mutation plan, no subprocess spawn, no lock
  taken); confirmed=True executes; read-only runs are unaffected.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.handlers.admin import handle_start
from flextoolsmcp.server import kernel, project_discovery, backup as backup_mod
from flextoolsmcp.server import session as session_mod


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


def _start(project_name, write_enabled, user_provided_extra=None, **kwargs):
    args = {
        "api_mode": "flexicon",
        "project_name": project_name,
        "output_type": "auto",
        "write_enabled": write_enabled,
        "_user_provided_keys": {"project_name", "write_enabled"} | (user_provided_extra or set()),
    }
    args.update(kwargs)
    r = asyncio.run(handle_start(args))
    return json.loads(r[0].text)


# ---------------------------------------------------------------------------
# Rung 1: undoable defaults to True when write_enabled=True
# ---------------------------------------------------------------------------

class TestRung1UndoableDefault:
    def test_fresh_write_enabled_defaults_undoable_true(self):
        data = _start("Proj_r1_default", write_enabled=True)
        ss = kernel.get_session_state()
        assert ss.undoable is True
        assert any("undoable=True" in w for w in data.get("warnings", []))

    def test_explicit_undoable_false_respected(self):
        data = _start(
            "Proj_r1_explicit_false", write_enabled=True, undoable=False,
            user_provided_extra={"undoable"},
        )
        ss = kernel.get_session_state()
        assert ss.undoable is False

    def test_read_only_start_defaults_undoable_false(self):
        _start("Proj_r1_readonly", write_enabled=False)
        ss = kernel.get_session_state()
        assert ss.undoable is False

    def test_same_project_restart_inherits_prior_default(self):
        _start("Proj_r1_inherit", write_enabled=True)  # implicit True
        ss = kernel.get_session_state()
        assert ss.undoable is True
        # Restart on the SAME project, write_enabled explicit, undoable implicit.
        _start("Proj_r1_inherit", write_enabled=True)
        ss = kernel.get_session_state()
        assert ss.undoable is True

    def test_undo_checkpoint_cap_documented_on_session_state(self):
        """Checkpoint-501 rollover semantics: maxlen=500, FIFO eviction."""
        assert session_mod._UNDO_CHECKPOINT_CAP == 500
        ss = session_mod.SessionState()
        assert ss.undo_checkpoints.maxlen == 500


# ---------------------------------------------------------------------------
# Rung 2: automatic pre-write backup
# ---------------------------------------------------------------------------

class TestRung2BackupModule:
    def test_creates_backup_and_returns_path(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "Projects" / "MyProj"
        project_dir.mkdir(parents=True)
        fwdata = project_dir / "MyProj.fwdata"
        fwdata.write_bytes(b"fake-fwdata-content")

        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: fwdata)
        monkeypatch.setattr(backup_mod, "BACKUP_ROOT", tmp_path / "backups")
        monkeypatch.setattr(backup_mod, "config_get", lambda key, default: default)

        result = backup_mod.perform_pre_write_backup("MyProj")
        assert result["created"] is True
        assert result["skipped_reason"] is None
        dest = tmp_path / "backups"
        assert dest.exists()
        copied = list(dest.glob("MyProj/*/MyProj.fwdata"))
        assert len(copied) == 1
        assert copied[0].read_bytes() == b"fake-fwdata-content"

    def test_opt_out_skips_backup(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: None)
        result = backup_mod.perform_pre_write_backup("AnyProj", backup_before_write=False)
        assert result["created"] is False
        assert result["skipped_reason"] == "backup_before_write=false"

    def test_missing_fwdata_skips_gracefully(self, monkeypatch):
        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: None)
        monkeypatch.setattr(backup_mod, "config_get", lambda key, default: default)
        result = backup_mod.perform_pre_write_backup("Ghost")
        assert result["created"] is False
        assert result["skipped_reason"] == "project_fwdata_not_found"

    def test_insufficient_disk_space_skips_with_reason(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "Projects" / "BigProj"
        project_dir.mkdir(parents=True)
        fwdata = project_dir / "BigProj.fwdata"
        fwdata.write_bytes(b"x" * 1000)

        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: fwdata)
        monkeypatch.setattr(backup_mod, "config_get", lambda key, default: default)

        class _FakeUsage:
            free = 500  # less than 2x the 1000-byte file
        monkeypatch.setattr(backup_mod.shutil, "disk_usage", lambda path: _FakeUsage())

        result = backup_mod.perform_pre_write_backup("BigProj")
        assert result["created"] is False
        assert result["skipped_reason"] == "insufficient_disk_space"

    def test_retention_prunes_to_newest_n(self, tmp_path, monkeypatch):
        project_dir = tmp_path / "Projects" / "RetProj"
        project_dir.mkdir(parents=True)
        fwdata = project_dir / "RetProj.fwdata"
        fwdata.write_bytes(b"data")

        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: fwdata)
        monkeypatch.setattr(backup_mod, "BACKUP_ROOT", tmp_path / "backups")

        def _config_get(key, default):
            if key == backup_mod.BACKUP_RETENTION_KEY:
                return 2
            return default
        monkeypatch.setattr(backup_mod, "config_get", _config_get)

        import time as _time
        for i in range(4):
            backup_mod.perform_pre_write_backup("RetProj")
            # Force distinct timestamps (the resolution is whole seconds).
            # Compute the fake timestamp up front (not as a lambda default --
            # that would be a function call in an argument default, B008)
            # and bind it via a closure-safe default so each patched
            # gmtime() call returns this iteration's fixed value.
            fake_time = _time.gmtime(_time.time() + (i + 1) * 2)
            monkeypatch.setattr(
                _time, "gmtime",
                lambda *a, _fake_time=fake_time: _fake_time,
            )
        remaining = sorted((tmp_path / "backups" / "RetProj").iterdir())
        assert len(remaining) <= 2

    def test_never_raises_on_unexpected_error(self, monkeypatch):
        def _boom(name):
            raise RuntimeError("disk exploded")
        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", _boom)
        result = backup_mod.perform_pre_write_backup("Whatever")
        assert result["created"] is False
        assert "backup_failed" in result["skipped_reason"]


class TestRung2SessionBackupTracking:
    def test_was_backed_up_and_record_backup(self):
        ss = session_mod.SessionState()
        assert ss.was_backed_up("ProjA") is False
        ss.record_backup("ProjA")
        assert ss.was_backed_up("ProjA") is True
        assert ss.was_backed_up("ProjB") is False

    def test_clear_discovered_apis_also_resets_backed_up_projects(self):
        ss = session_mod.SessionState()
        ss.record_backup("ProjA")
        ss.clear_discovered_apis()
        assert ss.was_backed_up("ProjA") is False


# ---------------------------------------------------------------------------
# Rung 3: enforced confirmation + wiring into handle_run_module
# ---------------------------------------------------------------------------

def _stub_mutating_write_env(monkeypatch, tmp_path, *, is_cud=True):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,  # properly modifyAllowed-guarded
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
            "confidence": "high",
        },
    )
    monkeypatch.setattr(
        execution_mod, "detect_cud_operations",
        lambda code: {"is_cud": is_cud, "operations": ["CREATE (Create())"] if is_cud else []},
    )
    monkeypatch.setattr(execution_mod, "detect_casting_needs", lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []})


def _boom_lock(*a, **k):
    raise AssertionError("get_project_write_lock must NOT be called")


def _boom_subprocess(*a, **k):
    raise AssertionError("run_script_async must NOT be called")


class TestRung3ConfirmationEnforcement:
    def test_mutating_write_without_confirmed_is_refused(self, monkeypatch, tmp_path):
        _stub_mutating_write_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": "if modifyAllowed:\n    project.LexEntry.Create(x)\n",
            "project_name": "TestProj",
            "write_enabled": True,
            "confirmed": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "confirmation_required"
        assert "mutations_detected" in data
        assert "writeability" in data
        assert "backup" in data

    def test_confirmed_true_executes(self, monkeypatch, tmp_path):
        _stub_mutating_write_env(monkeypatch, tmp_path)


        class _FakeLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False
        monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())

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
        monkeypatch.setattr(execution_mod, "perform_pre_write_backup", lambda name, **k: {"path": None, "created": False, "skipped_reason": "backup_before_write=false"})

        args = {
            "code": "if modifyAllowed:\n    project.LexEntry.Create(x)\n",
            "project_name": "TestProj_confirmed",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("success") is True
        assert "error_code" not in data or data.get("error_code") is None

    def test_read_only_run_unaffected_by_confirmed(self, monkeypatch, tmp_path):
        """Read-only runs (no mutation certified) never require confirmation."""
        _stub_mutating_write_env(monkeypatch, tmp_path, is_cud=False)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)

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
            "code": "x = project.LexEntry.GetAll()\n",
            "project_name": "TestProj_readonly",
            "write_enabled": False,
            "confirmed": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("success") is True

    def test_backup_fires_once_per_session_project(self, monkeypatch, tmp_path):
        """First confirmed mutating run backs up; the second (same session,
        same project) does not call perform_pre_write_backup again."""
        _stub_mutating_write_env(monkeypatch, tmp_path)

        class _FakeLock:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False
        monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())

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

        calls = {"n": 0}

        def _fake_backup(name, **kwargs):
            calls["n"] += 1
            return {"path": f"/fake/{calls['n']}", "created": True, "skipped_reason": None}
        monkeypatch.setattr(execution_mod, "perform_pre_write_backup", _fake_backup)

        project = "TestProj_backup_once"
        execution_mod.session_state.backed_up_projects = set()

        args = {
            "code": "if modifyAllowed:\n    project.LexEntry.Create(x)\n",
            "project_name": project,
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result1 = asyncio.run(execution_mod.handle_run_module(args))
        data1 = _parse(result1)
        assert data1["backup"]["created"] is True
        assert calls["n"] == 1

        result2 = asyncio.run(execution_mod.handle_run_module(args))
        data2 = _parse(result2)
        assert calls["n"] == 1, "backup must not fire twice for the same (session, project)"
        assert "backup" not in data2 or data2.get("backup") is None
