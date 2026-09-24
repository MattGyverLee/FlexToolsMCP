#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #223: `flextools_run_module`'s write gate must not report this
server's own idle parse worker as a foreign holder to kill, and must not
gate on a worker that's genuinely still busy -- and `flextools_parse_release`
gives a caller a tool to drop the lock on purpose.

`write_ladder.probe_write_access` is pure filesystem: it answers
`held_by_other` for ANY Python process holding the project's fwdata lock,
including the server's own shared read worker left running after
`flextools_try_word` / `flextools_parse_text` (idle timeout:
`DEFAULT_IDLE_TIMEOUT_SECONDS`). Filing already told the two apart
(`handlers/parse.py:_held_by_own_read_worker`); this file covers the same
detection generalized through `parse/own_worker.py` and wired into
`run_module`'s write gate (`handlers/execution.py:_release_own_worker_or_refuse`),
plus the new release tool.

Reuses `tests/test_shared_mode_write_gate.py`'s harness (`_stub_env`,
`_access`, `_stub_probe`, `_allow_execution`, `_refuse_execution`, `_run`,
`WRITE_ARGS`) rather than reinventing it -- the write gate itself is
unchanged outside the own-worker branch, so the same stubbing suffices.
"""

import asyncio
import json

import pytest

import test_shared_mode_write_gate as swg
from flextoolsmcp.server import project_access
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.handlers import parse as parse_mod


# ---------------------------------------------------------------------------
# A lightweight double for the two methods `_release_own_worker_or_refuse`
# and `handle_flextools_parse_release` need -- not a real ParseRunner, so a
# regression in the real one's own tests (test_parse_worker_lifetime.py,
# test_filing_fail_closed.py) is the one that would catch it there; this
# double only has to answer honestly.
# ---------------------------------------------------------------------------


class _FakeWorker:
    def __init__(self, pid):
        self.worker_pid = pid


class _FakePool:
    def __init__(self, workers):
        self._workers = dict(workers)

    def workers_for(self, project_name):
        return dict(self._workers)


class _FakeOwnWorkerRunner:
    """`workers`: role -> pid. `busy_roles`: roles with a live run."""

    def __init__(self, workers=None, *, busy_roles=None, run_ids=None):
        self._workers = dict(workers or {})
        self._busy_roles = set(busy_roles or ())
        self._run_ids = dict(run_ids or {})
        self.released = []
        self.pool = _FakePool(self._workers)

    def own_worker_role_for_pid(self, project_name, pid):
        for role, worker_pid in self._workers.items():
            if worker_pid == pid:
                return role
        return None

    def worker_busy(self, project_name, *, role):
        return role in self._busy_roles

    def active_run_ids(self, project_name, *, role):
        return list(self._run_ids.get(role, []))

    async def release_worker(self, project_name, *, role):
        self.released.append((project_name, role))
        self._workers.pop(role, None)
        self._busy_roles.discard(role)
        self.pool._workers.pop(role, None)


@pytest.fixture(autouse=True)
def _reset_runner():
    """`peek_runner()` reads the module global; never leak a fake across tests."""
    parse_mod.set_runner(None)
    yield
    parse_mod.set_runner(None)


def _probe_sequence(monkeypatch, *accesses):
    """Successive `probe_project_access` calls answer `accesses` in order,
    repeating the last one past the end (mirrors
    `tests/test_filing_fail_closed.py::_probe_sequence`)."""
    calls = []

    def probe(name):
        calls.append(name)
        return accesses[min(len(calls), len(accesses)) - 1]

    monkeypatch.setattr(project_access, "probe_project_access", probe)
    return calls


# ---------------------------------------------------------------------------
# run_module's write gate
# ---------------------------------------------------------------------------


class TestRunModuleOwnWorkerGate:
    def test_own_idle_shared_worker_is_released_and_the_write_proceeds(
        self, monkeypatch, tmp_path
    ):
        """Non-shared project: the pre-#223 repro (issue text's example)."""
        swg._stub_env(monkeypatch, tmp_path)
        _probe_sequence(
            monkeypatch,
            swg._access("held_by_other", pid=33452, process="python", sharing=False),
            swg._access("free", holder=False),
        )
        swg._allow_execution(monkeypatch)
        runner = _FakeOwnWorkerRunner({"shared": 33452})
        parse_mod.set_runner(runner)

        data = swg._run("TestProj_ownidle")

        assert data.get("error_code") is None, data
        assert runner.released == [("TestProj_ownidle", "shared")]

    def test_own_idle_worker_is_released_even_on_a_shared_project(
        self, monkeypatch, tmp_path
    ):
        """The issue's second finding: sharing_enabled=True did not save the
        write either, because the probe's `held_by_other` verdict does not
        vary with the project's sharing setting for a Python holder. The
        fix releases regardless of the sharing flag."""
        swg._stub_env(monkeypatch, tmp_path)
        _probe_sequence(
            monkeypatch,
            swg._access("held_by_other", pid=33452, process="python", sharing=True),
            swg._access("free", holder=False),
        )
        swg._allow_execution(monkeypatch)
        runner = _FakeOwnWorkerRunner({"shared": 33452})
        parse_mod.set_runner(runner)

        data = swg._run("TestProj_ownidle_shared")

        assert data.get("error_code") is None, data
        assert runner.released == [("TestProj_ownidle_shared", "shared")]

    def test_own_busy_worker_refuses_naming_the_run_with_no_kill_remedy(
        self, monkeypatch, tmp_path
    ):
        swg._stub_env(monkeypatch, tmp_path)
        _probe_sequence(
            monkeypatch,
            swg._access("held_by_other", pid=33452, process="python", sharing=False),
        )
        swg._refuse_execution(monkeypatch)
        runner = _FakeOwnWorkerRunner(
            {"shared": 33452}, busy_roles={"shared"}, run_ids={"shared": ["run-abc123"]}
        )
        parse_mod.set_runner(runner)

        data = swg._run("TestProj_ownbusy")

        assert data["error_code"] == "project_locked"
        assert runner.released == [], "a busy worker is never released"
        assert "run-abc123" in data["message"]
        assert "this server's own parse worker" in data["message"].lower()
        # The one thing #223 says never to tell the caller about our own
        # worker: end (kill) the process. "do not end it" is the one
        # allowed use of "end" -- an instruction NOT to kill it.
        for field in ("message", "guidance", "remedy"):
            text = str(data.get(field, "")).lower()
            assert "kill" not in text
            assert "end the process" not in text
        assert "do not end it" in data["message"].lower()

    def test_a_foreign_holder_is_still_refused_as_before(self, monkeypatch, tmp_path):
        """No worker of ours matches this PID -- own_worker_role_for_pid
        returns None, and the original refusal is untouched."""
        swg._stub_env(monkeypatch, tmp_path)
        _probe_sequence(
            monkeypatch,
            swg._access("held_by_other", pid=999, process="python", sharing=False),
        )
        swg._refuse_execution(monkeypatch)
        runner = _FakeOwnWorkerRunner({"shared": 33452})
        parse_mod.set_runner(runner)

        data = swg._run("TestProj_foreign")

        assert data["error_code"] == "project_locked"
        assert data["holder_pid"] == 999
        assert runner.released == []

    def test_no_runner_at_all_behaves_exactly_as_before(self, monkeypatch, tmp_path):
        """peek_runner() returning None (no worker ever started this
        process) must not crash the gate -- own_worker_role short-circuits."""
        swg._stub_env(monkeypatch, tmp_path)
        _probe_sequence(
            monkeypatch,
            swg._access("open_exclusive", pid=68436, process="FieldWorks", sharing=False),
        )
        swg._refuse_execution(monkeypatch)
        # No set_runner call: peek_runner() is None (autouse fixture reset it).

        data = swg._run("TestProj_norunner")

        assert data["error_code"] == "project_locked"
        assert data["holder_pid"] == 68436

    def test_an_unconfirmed_run_never_releases_a_warm_worker(self, monkeypatch, tmp_path):
        """Rung order (#223): confirmation_required fires before the access
        gate is even consulted, so an unconfirmed preview must not release
        anything -- releasing there would tear down a worker under a call
        that might never be resubmitted."""
        swg._stub_env(monkeypatch, tmp_path)
        _probe_sequence(
            monkeypatch,
            swg._access("held_by_other", pid=33452, process="python", sharing=False),
        )
        swg._refuse_execution(monkeypatch)
        runner = _FakeOwnWorkerRunner({"shared": 33452})
        parse_mod.set_runner(runner)

        args = dict(swg.WRITE_ARGS, project_name="TestProj_unconfirmed", confirmed=False)
        data = swg._parse(asyncio.run(execution_mod.handle_run_module(args)))

        assert data["error_code"] == "confirmation_required"
        assert runner.released == []

    def test_a_measurement_role_worker_is_detected_the_same_way(self, monkeypatch, tmp_path):
        """The pool tracks more than SHARED_ROLE -- a write gate that only
        checked the shared read worker would misreport the bounded
        measurement worker as foreign too."""
        swg._stub_env(monkeypatch, tmp_path)
        _probe_sequence(
            monkeypatch,
            swg._access("held_by_other", pid=5150, process="python", sharing=False),
            swg._access("free", holder=False),
        )
        swg._allow_execution(monkeypatch)
        runner = _FakeOwnWorkerRunner({"measurement": 5150})
        parse_mod.set_runner(runner)

        data = swg._run("TestProj_measurement")

        assert data.get("error_code") is None, data
        assert runner.released == [("TestProj_measurement", "measurement")]


# ---------------------------------------------------------------------------
# flextools_parse_release
# ---------------------------------------------------------------------------


def _call_release(args):
    result = asyncio.run(parse_mod.handle_flextools_parse_release(args))
    item = result[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


class TestParseRelease:
    def test_no_worker_at_all_is_a_success_no_op(self, monkeypatch):
        monkeypatch.setattr(parse_mod, "_resolve_project", lambda name: (name or "P", None))
        # peek_runner() is None (autouse fixture reset it).
        data = _call_release({"project_name": "NoWorkerProj"})

        assert data["status"] == "ok"
        assert data["released"] == []

    def test_an_idle_worker_is_released(self, monkeypatch):
        monkeypatch.setattr(parse_mod, "_resolve_project", lambda name: (name or "P", None))
        runner = _FakeOwnWorkerRunner({"shared": 111})
        parse_mod.set_runner(runner)

        data = _call_release({"project_name": "IdleProj"})

        assert data["status"] == "ok"
        assert data["released"] == ["shared"]
        assert runner.released == [("IdleProj", "shared")]

    def test_a_busy_worker_refuses_and_points_at_parse_cancel(self, monkeypatch):
        monkeypatch.setattr(parse_mod, "_resolve_project", lambda name: (name or "P", None))
        runner = _FakeOwnWorkerRunner(
            {"shared": 111}, busy_roles={"shared"}, run_ids={"shared": ["run-xyz"]}
        )
        parse_mod.set_runner(runner)

        data = _call_release({"project_name": "BusyProj"})

        assert data["error_code"] == "project_locked"
        assert runner.released == []
        assert "run-xyz" in data["message"]
        assert "flextools_parse_cancel" in data["message"] or (
            "flextools_parse_cancel" in data.get("guidance", "")
        )

    def test_multiple_idle_roles_are_all_released(self, monkeypatch):
        monkeypatch.setattr(parse_mod, "_resolve_project", lambda name: (name or "P", None))
        runner = _FakeOwnWorkerRunner({"shared": 111, "measurement": 222})
        parse_mod.set_runner(runner)

        data = _call_release({"project_name": "TwoRolesProj"})

        assert data["status"] == "ok"
        assert sorted(data["released"]) == ["measurement", "shared"]
        assert sorted(runner.released) == [
            ("TwoRolesProj", "measurement"), ("TwoRolesProj", "shared"),
        ]
