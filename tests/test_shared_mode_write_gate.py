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
    held_by_other  -> refuse `project_locked` + the foreign-holder remedy and
                      model-actionable `next_steps` (issue #315)

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
    build_access_next_steps,
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
    @pytest.mark.parametrize("verdict", ["free", "open_shared", "stale_lock", "unknown"])
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
        assert "PID 4242" in remedy
        assert "python" in remedy
        # Sharing is already on here -- must not tell the user to enable it.
        assert "does not resolve it" in remedy

    def test_held_by_other_remedy_never_tells_the_model_to_end_it(self):
        """Issue #315: the model has no tool to end a process. The remedy
        points at what it CAN do and leaves ending the PID to the user."""
        remedy = build_access_remedy(
            _access("held_by_other", pid=4242, process="python", sharing=False),
            own_workers_ruled_out=True,
        )
        assert "(or end it)" not in remedy
        # Sharing is off: even a read-only open takes the lock.
        assert "will likely fail too" in remedy
        assert "still work" not in remedy
        # Our own workers were ruled out, so releasing them cannot help.
        assert "flextools_parse_release" not in remedy
        assert "ask the user" in remedy
        assert "end PID 4242 in Task Manager" in remedy
        assert "do not try to end it yourself" in remedy
        assert "NOT one of the parse workers this server tracks" in remedy
        assert "another MCP server instance or Claude session" in remedy

    def test_held_by_other_post_hoc_remedy_does_not_claim_foreign(self):
        """Issue #315: only the write gate has ruled out our own workers;
        a post-hoc diagnosis must not assert that the holder is foreign."""
        remedy = build_access_remedy(
            _access("held_by_other", pid=4242, process="python")
        )
        assert "NOT one of the parse workers" not in remedy
        assert "Unless it is one of this server's own parse workers" in remedy
        assert "flextools_parse_release" in remedy

    @pytest.mark.parametrize("sharing,expected", [
        (True, "still work"),
        (False, "will likely fail too"),
        (None, "will likely fail too"),
    ])
    def test_read_only_claim_depends_on_sharing(self, sharing, expected):
        """Issue #315: on a non-shared project even a read-only open takes
        the .fwdata.lock, so "read-only still works" holds only with
        sharing on."""
        remedy = build_access_remedy(
            _access("held_by_other", pid=4242, process="python", sharing=sharing)
        )
        assert expected in remedy


class TestBuildAccessNextSteps:
    """Issue #315: `project_locked`'s `next_steps`, numbered like the
    preflight refusals' (validators.py)."""

    @pytest.mark.parametrize("verdict", ["free", "open_shared", "stale_lock", "unknown"])
    def test_non_blocking_verdicts_have_no_steps(self, verdict):
        assert build_access_next_steps(_access(verdict)) == []

    def test_held_by_other_steps_are_actionable_and_numbered(self):
        steps = build_access_next_steps(
            _access("held_by_other", pid=4242, process="python")
        )
        assert [s.split(".", 1)[0] for s in steps] == ["1", "2", "3", "4"]
        text = " ".join(steps)
        assert "Read-only runs" in steps[0]
        assert "will likely fail too" in steps[0]
        assert "flextools_parse_release" in steps[1]
        assert "600 s" in steps[2]
        assert "ask the user" in steps[3]
        assert "PID 4242" in steps[3]
        assert "Do not try to end it yourself" in steps[3]
        assert "(or end it)" not in text

    def test_held_by_other_steps_drop_release_once_own_workers_ruled_out(self):
        """Issue #315: the write gate refuses only after it has released our
        own idle workers, so a flextools_parse_release step could not help."""
        steps = build_access_next_steps(
            _access("held_by_other", pid=4242, process="python", sharing=True),
            own_workers_ruled_out=True,
        )
        assert [s.split(".", 1)[0] for s in steps] == ["1", "2", "3"]
        assert not any("flextools_parse_release" in s for s in steps)
        assert "still work" in steps[0]
        assert "600 s" in steps[1]
        assert "PID 4242" in steps[2]

    def test_open_exclusive_steps_point_at_sharing(self):
        steps = build_access_next_steps(_access("open_exclusive", sharing=False))
        assert any("Sharing tab" in s for s in steps)
        # FieldWorks holds the lock with sharing off: reads collide too.
        assert "will likely fail too" in steps[0]

    def test_open_exclusive_unreadable_lock_steps_do_not_blame_fieldworks(self):
        steps = build_access_next_steps(_access("open_exclusive", pid=None, process=None))
        assert steps
        assert not any("Sharing tab" in s for s in steps)
        assert any(".fwdata.lock" in s for s in steps)

    @pytest.mark.parametrize("verdict,kwargs", [
        ("held_by_other", {"pid": 4242, "process": "python"}),
        ("open_exclusive", {"sharing": False}),
        ("open_exclusive", {"pid": None, "process": None}),
    ])
    def test_write_ladder_refusal_validates_against_the_detail_model(
        self, monkeypatch, tmp_path, verdict, kwargs
    ):
        """Every call site spreads `decision.refusal` into
        error_response("project_locked", ...) (run_module, filing), so the
        dict itself must fit ProjectLockedDetail, which is extra="forbid"."""
        from flextoolsmcp.server import write_ladder
        from flextoolsmcp.server.response_models import ProjectLockedDetail

        _stub_probe(monkeypatch, _access(verdict, **kwargs))
        monkeypatch.setattr(
            project_discovery, "find_lock_file",
            lambda name: tmp_path / f"{name}.fwdata.lock",
        )
        decision = write_ladder.probe_write_access("TestProj")
        detail = ProjectLockedDetail.model_validate(decision.refusal)
        assert detail.next_steps
        assert detail.next_steps == build_access_next_steps(
            decision.access, own_workers_ruled_out=True
        )
        assert not any("flextools_parse_release" in s for s in detail.next_steps)


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
        project_discovery, "find_lock_file",
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
        # The advisory must not overstate what a peer can safely do -- and,
        # since the exclusive-access gate now refuses those changes up front,
        # it points at that refusal instead of warning after the fact
        # (exclusive-access-gate FR-013).
        assert "Custom-field and writing-system changes are NOT safe" not in advisory["note"]
        assert "requires_exclusive_access" in advisory["note"]

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
        assert "PID 4242" in data["remedy"]
        # Issue #315: actionable steps travel with the refusal -- but not
        # flextools_parse_release: the gate already ruled out our workers.
        assert any("ask the user" in s for s in data["next_steps"])
        assert not any("flextools_parse_release" in s for s in data["next_steps"])
        assert "flextools_parse_release" not in data["remedy"]
        assert "(or end it)" not in data["remedy"]

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


# ---------------------------------------------------------------------------
# Issue #315: the run-time FP_FileLockedError diagnosis gets the same holder
# check, remedy and next_steps as the pre-flight refusal.
# ---------------------------------------------------------------------------

_LOCKED_RESULT = {
    "error": (
        "Failed to open project 'TestProj': FP_FileLockedError: This project "
        "is in use by another program."
    ),
}


class _FakeRunner:
    """Just the three methods the diagnosis asks of a ParseRunner."""

    def __init__(self, pid, *, busy=False):
        self._pid, self._busy = pid, busy

    def own_worker_role_for_pid(self, project_name, pid):
        return "shared" if pid == self._pid else None

    def worker_busy(self, project_name, *, role):
        return self._busy

    def active_run_ids(self, project_name, *, role):
        return ["run-7"] if self._busy else []


def _stub_runner(monkeypatch, runner):
    from flextoolsmcp.server.handlers import parse as parse_mod

    monkeypatch.setattr(parse_mod, "peek_runner", lambda: runner)


def _diagnose():
    return execution_mod._diagnose_project_open_error(dict(_LOCKED_RESULT), "TestProj")


def _detail_fields(diag):
    """The diagnosis keys that ProjectLockedDetail declares, validated."""
    from flextoolsmcp.server.response_models import ProjectLockedDetail

    return ProjectLockedDetail.model_validate(
        {k: v for k, v in diag.items() if k in ProjectLockedDetail.model_fields}
    )


class TestRuntimeLockDiagnosis:
    def test_foreign_holder_matches_the_preflight_refusal(self, monkeypatch, tmp_path):
        from flextoolsmcp.server import write_ladder

        access = _access("held_by_other", pid=4242, process="python", sharing=False)
        _stub_probe(monkeypatch, access)
        _stub_runner(monkeypatch, _FakeRunner(pid=999))  # ours, but not the holder
        monkeypatch.setattr(
            project_discovery, "find_lock_file",
            lambda name: tmp_path / f"{name}.fwdata.lock",
        )

        diag = _diagnose()
        refusal = write_ladder.probe_write_access("TestProj").refusal
        assert diag["error_code"] == "project_locked"
        assert "Close FieldWorks" not in diag["hint"]
        assert diag["remedy"] == refusal["remedy"]
        assert diag["next_steps"] == refusal["next_steps"]
        assert diag["holder_pid"] == 4242
        assert not any("flextools_parse_release" in s for s in diag["next_steps"])
        assert _detail_fields(diag).next_steps == diag["next_steps"]

    def test_open_exclusive_carries_the_sharing_steps(self, monkeypatch):
        _stub_probe(monkeypatch, _access("open_exclusive", sharing=False))
        _stub_runner(monkeypatch, None)

        diag = _diagnose()
        assert diag["remedy"] == project_access.ENABLE_SHARING_REMEDY
        assert any("Sharing tab" in s for s in diag["next_steps"])

    def test_idle_own_worker_is_named_not_reported_foreign(self, monkeypatch):
        _stub_probe(monkeypatch, _access("held_by_other", pid=4242, process="python"))
        _stub_runner(monkeypatch, _FakeRunner(pid=4242))

        diag = _diagnose()
        assert diag["error_code"] == "project_locked"
        assert "own idle parse worker" in diag["message"]
        assert "do not end it" in diag["hint"]
        assert diag["holder_process"] == "this server's own parse worker"
        assert diag["holder_pid"] == 4242
        assert "flextools_parse_release" in diag["next_steps"][0]
        assert "Task Manager" not in " ".join(diag["next_steps"])
        _detail_fields(diag)

    def test_busy_own_worker_says_wait_or_cancel(self, monkeypatch):
        _stub_probe(monkeypatch, _access("held_by_other", pid=4242, process="python"))
        _stub_runner(monkeypatch, _FakeRunner(pid=4242, busy=True))

        diag = _diagnose()
        assert "busy running a parse (run run-7)" in diag["message"]
        assert any("flextools_parse_cancel" in s for s in diag["next_steps"])
        assert not any("flextools_parse_release" in s for s in diag["next_steps"])

    def test_probe_failure_keeps_the_generic_hint(self, monkeypatch):
        def boom(name):
            raise OSError("registry unavailable")

        monkeypatch.setattr(project_access, "probe_project_access", boom)
        diag = _diagnose()
        assert diag["error_code"] == "project_locked"
        assert "Close FieldWorks" in diag["hint"]
        assert "next_steps" not in diag


class TestReadOnlyUnaffected:
    def test_read_only_run_is_not_gated_even_when_exclusively_held(self, monkeypatch, tmp_path):
        """T4.3: needs_lock is False for a read-only run, so the gate never
        fires -- exploring a project while FLEx holds it exclusively keeps
        working."""
        _stub_env(monkeypatch, tmp_path, is_cud=False)
        _stub_probe(monkeypatch, _access("open_exclusive", sharing=False))
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
        assert "shared_mode_read_back" not in data

    def test_read_only_open_shared_surfaces_read_back_advisory(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path, is_cud=False)
        _stub_probe(monkeypatch, _access("open_shared", sharing=True))
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)

        data = _parse(asyncio.run(execution_mod.handle_run_module({
            "code": "entries = project.LexEntry.GetAll()\n",
            "project_name": "TestProj_ro_shared",
            "write_enabled": False,
            "skip_api_check": True,
            "skip_module_check": True,
        })))
        assert data.get("error_code") is None
        advisory = data["shared_mode_read_back"]
        assert advisory["verdict"] == "open_shared"
        assert advisory["sharing_enabled"] is True
        assert advisory["holder_pid"] == 68436
        assert advisory["holder_process"] == "FieldWorks"
        assert "Do not treat this read-back as proof a write was lost" in advisory["note"]


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
