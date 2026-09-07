#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #93 CP4: the write gate is driven by the access probe, not by the mere
existence of a .fwdata.lock file.

Issue #33 refused every write whenever a lock file was present. That was an
over-correction: with projectSharing="true" in the project's
SharedSettings\\LexiconSettings.plsx, LCM promotes the backend to
SharedXMLBackendProvider (LcmCache.cs:211-226) and our process attaches as a
non-master peer that reads and writes through the shared commit log -- so the
write lands and shows up live in the FLEx UI. Only two verdicts genuinely
block a write.

Verdict table under test (SPEC "CP4 -- Writes allowed in shared mode", T4.1):

    free           -> proceed, no advisory
    open_shared    -> proceed, `shared_mode` advisory on the result
    stale_lock     -> proceed, `shared_mode` advisory naming the dead PID
    open_exclusive -> refuse `project_locked` + the enable-sharing remedy
    held_by_other  -> refuse `project_locked` + the wait-for-PID remedy

Covers:
- TestBuildAccessRemedy: the remedy text is produced for exactly the two
  blocking verdicts, and the unidentified-holder fallback is distinguished
  from "FieldWorks has it with sharing off".
- TestGateWiring: each verdict's effect on handle_run_module -- refusals take
  no project lock and spawn no subprocess; proceeds do both and carry the
  advisory.
- TestReadOnlyUnaffected: T4.3 -- a read-only run is not gated at all, so
  exploring a project FieldWorks holds exclusively still works.
- TestBackupHonesty: T4.2 -- with a live FLEx peer the backup note says the
  copy is a floor, not a snapshot.

Follows tests/test_nested_uow_gate.py's harness: handle_run_module is driven
directly with the environment stubbed, and probe_project_access is
monkeypatched on the module object (the gate's from-import resolves at call
time, so patching the attribute takes effect).
"""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_access, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.project_access import (
    LockHolder,
    ProjectAccess,
    build_access_remedy,
)


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _access(verdict, *, pid=68436, process="FieldWorks", sharing=None, holder=True):
    return ProjectAccess(
        project_name="TestProj",
        verdict=verdict,
        sharing_enabled=sharing,
        holder=LockHolder(pid=pid, process_name=process, timestamp_ticks=None) if holder else None,
        lock_age_seconds=None,
    )


# ---------------------------------------------------------------------------
# build_access_remedy() -- shared by this gate and (CP3) the post-hoc
# FP_FileLockedError diagnosis, so it is unit-tested on its own.
# ---------------------------------------------------------------------------

class TestBuildAccessRemedy:
    @pytest.mark.parametrize("verdict", ["free", "open_shared", "stale_lock"])
    def test_non_blocking_verdicts_have_no_remedy(self, verdict):
        """Nothing for the user to do -- these proceed."""
        assert build_access_remedy(_access(verdict)) is None

    def test_open_exclusive_gives_the_enable_sharing_recipe(self):
        remedy = build_access_remedy(_access("open_exclusive", sharing=False))
        assert remedy == project_access.ENABLE_SHARING_REMEDY
        assert "Sharing tab" in remedy
        # Settled decision: we never write LexiconSettings.plsx ourselves.
        assert "never writes LexiconSettings.plsx" in remedy

    def test_open_exclusive_with_unreadable_lock_does_not_blame_fieldworks(self):
        """The empty/malformed-lock fallback reaches open_exclusive with no
        identifiable holder. Telling that user to toggle a sharing checkbox
        would be a guess, so the remedy differs."""
        remedy = build_access_remedy(_access("open_exclusive", pid=None, process=None))
        assert remedy != project_access.ENABLE_SHARING_REMEDY
        assert "could not be identified" in remedy
        assert "never deletes lock files" in remedy

    def test_held_by_other_names_the_holding_process(self):
        remedy = build_access_remedy(
            _access("held_by_other", pid=4242, process="python", sharing=True)
        )
        assert "4242" in remedy
        assert "python" in remedy
        # Sharing is already on here -- must not tell the user to enable it.
        assert "does not resolve it" in remedy


# ---------------------------------------------------------------------------
# Gate wiring inside handle_run_module.
# ---------------------------------------------------------------------------

def _boom_lock(*a, **k):
    raise AssertionError("get_project_write_lock must NOT be called")


def _boom_subprocess(*a, **k):
    raise AssertionError("run_script_async must NOT be called")


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


def _stub_env(monkeypatch, tmp_path, *, is_cud=True):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(
        project_discovery, "check_project_locked",
        lambda name: tmp_path / f"{name}.fwdata.lock",
    )
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
            "confidence": "high",
        },
    )
    monkeypatch.setattr(
        execution_mod, "detect_cud_operations",
        lambda code: {"is_cud": is_cud, "operations": ["CREATE (Create())"] if is_cud else []},
    )
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs",
        lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []},
    )


def _stub_probe(monkeypatch, access):
    monkeypatch.setattr(project_access, "probe_project_access", lambda name: access)


def _allow_execution(monkeypatch, *, backup=None):
    monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
    monkeypatch.setattr(
        execution_mod, "perform_pre_write_backup",
        lambda name, **k: backup or {
            "path": None, "created": False, "skipped_reason": "backup_before_write=false",
        },
    )


def _refuse_execution(monkeypatch):
    monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
    monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)


WRITE_ARGS = {
    "code": "if modifyAllowed:\n    project.LexEntry.SetLexemeForm(entry, 'x')\n",
    "write_enabled": True,
    "confirmed": True,
    "skip_api_check": True,
    "skip_module_check": True,
}


def _run(project_name):
    return _parse(asyncio.run(execution_mod.handle_run_module(
        dict(WRITE_ARGS, project_name=project_name)
    )))


class TestGateWiring:
    def test_free_proceeds_with_no_advisory(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("free", holder=False))
        _allow_execution(monkeypatch)

        data = _run("TestProj_free")
        assert data.get("error_code") is None
        assert "shared_mode" not in data

    def test_open_shared_proceeds_and_advises(self, monkeypatch, tmp_path):
        """The regression this checkpoint exists to undo: a lock file is
        present and FieldWorks holds it, but sharing is on, so the write
        goes through as a non-master peer."""
        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("open_shared", sharing=True))
        _allow_execution(monkeypatch)

        data = _run("TestProj_shared")
        assert data.get("error_code") is None
        advisory = data["shared_mode"]
        assert advisory["verdict"] == "open_shared"
        assert advisory["sharing_enabled"] is True
        assert advisory["holder_pid"] == 68436
        assert advisory["holder_process"] == "FieldWorks"
        # The advisory must not overstate what a peer can safely do.
        assert "Custom-field" in advisory["note"]

    def test_stale_lock_proceeds_and_names_the_dead_holder(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("stale_lock", pid=999, process="python"))
        _allow_execution(monkeypatch)

        data = _run("TestProj_stale")
        assert data.get("error_code") is None
        advisory = data["shared_mode"]
        assert advisory["verdict"] == "stale_lock"
        assert advisory["holder_pid"] == 999
        assert "never deletes lock files" in advisory["note"]

    def test_open_exclusive_refuses_with_the_sharing_remedy(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("open_exclusive", sharing=False))
        _refuse_execution(monkeypatch)

        data = _run("TestProj_excl")
        assert data["error_code"] == "project_locked"
        assert data["verdict"] == "open_exclusive"
        assert data["sharing_enabled"] is False
        assert data["holder_pid"] == 68436
        assert data["holder_process"] == "FieldWorks"
        assert data["remedy"] == project_access.ENABLE_SHARING_REMEDY
        assert data["guidance"] == data["remedy"]
        assert data["lock_file_path"].endswith(".fwdata.lock")

    def test_held_by_other_refuses(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("held_by_other", pid=4242, process="python", sharing=True))
        _refuse_execution(monkeypatch)

        data = _run("TestProj_other")
        assert data["error_code"] == "project_locked"
        assert data["verdict"] == "held_by_other"
        assert "4242" in data["remedy"]

    def test_refusal_payload_validates_against_the_detail_model(self, monkeypatch, tmp_path):
        """ProjectLockedDetail is extra="forbid" -- the handler must not send
        a key the model does not declare."""
        from flextoolsmcp.server.response_models import RejectionEnvelope

        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("open_exclusive", sharing=False))
        _refuse_execution(monkeypatch)

        data = _run("TestProj_model")
        envelope = RejectionEnvelope.model_validate(data, by_alias=True)
        assert envelope.error_code == "project_locked"


class TestReadOnlyUnaffected:
    def test_read_only_run_is_not_gated_even_when_exclusively_held(self, monkeypatch, tmp_path):
        """T4.3: needs_lock is False for a read-only run, so the gate never
        fires -- exploring a project while FLEx holds it exclusively keeps
        working."""
        _stub_env(monkeypatch, tmp_path, is_cud=False)

        def _boom_probe(name):
            raise AssertionError("the probe must not run for a read-only script")

        monkeypatch.setattr(project_access, "probe_project_access", _boom_probe)
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)

        data = _parse(asyncio.run(execution_mod.handle_run_module({
            "code": "entries = project.LexEntry.GetAll()\n",
            "project_name": "TestProj_ro",
            "write_enabled": False,
            "skip_api_check": True,
            "skip_module_check": True,
        })))
        assert data.get("error_code") is None
        assert "shared_mode" not in data


class TestBackupHonesty:
    def test_peer_backup_note_says_floor_not_snapshot(self, monkeypatch, tmp_path):
        """T4.2: with FLEx attached, the .fwdata on disk lags its unsaved
        in-memory state, so the copy is a floor, not a snapshot."""
        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("open_shared", sharing=True))
        _allow_execution(monkeypatch, backup={
            "path": str(tmp_path / "Demo.fwdata"), "created": True, "skipped_reason": None,
        })

        data = _run("TestProj_backup")
        note = data["backup"]["note"]
        assert "lags" in note
        assert "not a snapshot" in note

    def test_no_peer_backup_has_no_caveat(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        _stub_probe(monkeypatch, _access("free", holder=False))
        _allow_execution(monkeypatch, backup={
            "path": str(tmp_path / "Demo.fwdata"), "created": True, "skipped_reason": None,
        })

        data = _run("TestProj_backup_free")
        assert "note" not in data["backup"]
