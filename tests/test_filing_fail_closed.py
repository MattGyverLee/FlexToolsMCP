#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unknown is never clean: the fail-open siblings the CP4 pattern audit found
(specs/parser-check-cp4/reviews/pattern-audit-3-4.md, sweep #4; and
pattern-audit-1-2.md, sweep #2, for the read worker's cache).

Each test below pins one path whose failure used to read as the PERMISSIVE
answer -- "the parser was built", "nothing to delete for these words", "the
read worker is current" -- and now reads as a refusal or as unknown.
The filer-side halves (an unreadable opinion or segment join is not a
shield) live beside the guard, in `tests/test_filing_classify.py`.
"""

import asyncio
import types
from pathlib import Path

import pytest

import filing_fakes
from filing_fakes import PROJECT, FakeFilingWorker, FakeReadWorker, analysis, call, filing_args
from flextoolsmcp.server import backup as backup_mod
from flextoolsmcp.server import project_access
from flextoolsmcp.server.filing import gate
from flextoolsmcp.server.filing.observer import FilingObserver
from flextoolsmcp.server.parse.worker_client import SHARED_ROLE

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env


# ---------------------------------------------------------------------------
# The gate: a probe that did not say is not a probe that said "built"
# ---------------------------------------------------------------------------


def _current(**over):
    current = {"load": {"captured": True, "errors": [], "source": "x"},
               "eligible": {"known": True, "entries": []}}
    current.update(over)
    return current


def test_a_missing_morpher_answer_refuses():
    standing = gate.evaluate(_current(), None)
    assert standing.status == "refused" and standing.signal == "morpher_null"


def test_an_explicit_built_morpher_passes_that_rung():
    assert gate.evaluate(_current(morpher_null=False), None).signal != "morpher_null"


# ---------------------------------------------------------------------------
# The preview: an incomplete answer is not "nothing to delete"
# ---------------------------------------------------------------------------


class _IncompletePreview(FakeReadWorker):
    async def filing_preview(self, **kwargs):
        self.calls.append("filing_preview")
        return {"join_known": True, "words": {}}


async def test_a_preview_that_omits_words_in_scope_refuses_and_writes_nothing(filing_env):
    filing_env.install(_IncompletePreview(facts={"pukul": [analysis("a1")]}), FakeFilingWorker())
    before = filing_env.fwdata_sha256()
    response = await call(filing_args())
    assert response["status"] == "error" and response["error_code"] == "runtime_error"
    assert response["error_type"] == "IncompletePreview"
    assert "plan_id" not in response
    assert filing_env.fwdata_sha256() == before
    assert filing_env.pool.spawned == [], "no filing worker for an unbounded plan"


# ---------------------------------------------------------------------------
# The read worker's cache after a filing run (R-09): deferred, not skipped
# ---------------------------------------------------------------------------


async def test_a_stale_read_worker_is_recycled_before_the_next_preflight_read(filing_env):
    runner = filing_env.install(FakeReadWorker())
    runner.mark_read_worker_stale(PROJECT)
    await runner.probe_agent(PROJECT)
    assert (PROJECT, SHARED_ROLE) in filing_env.pool.released
    filing_env.pool.released.clear()
    await runner.probe_agent(PROJECT)
    assert filing_env.pool.released == [], "recycled once, not on every read"


async def test_a_busy_stale_worker_is_not_killed_under_a_users_word(filing_env):
    runner = filing_env.install(FakeReadWorker())
    busy = types.SimpleNamespace(is_terminal=False, project_name=PROJECT, worker_role=SHARED_ROLE)
    runner._runs["busy"] = busy
    runner.mark_read_worker_stale(PROJECT)
    await runner.filing_preview(PROJECT, words=["pukul"], vernacular_ws=None)
    assert filing_env.pool.released == []
    busy.is_terminal = True
    await runner.filing_preview(PROJECT, words=["pukul"], vernacular_ws=None)
    assert (PROJECT, SHARED_ROLE) in filing_env.pool.released


class _Runner:
    def __init__(self, busy):
        self._busy = busy
        self.stale = []
        self.released = []

    def read_worker_busy(self, project):
        return self._busy

    def mark_read_worker_stale(self, project):
        self.stale.append(project)

    async def release_worker(self, project, *, role):
        self.released.append((project, role))


def _observer():
    return FilingObserver(project_name=PROJECT, plan={}, plan_id="0" * 64, backup={},
                          no_recovery_warning=None, send_receive=False,
                          access_verdict="free", recycle_read_worker=True,
                          claim_token="t")


def test_after_filing_an_idle_read_worker_is_released_and_a_busy_one_marked():
    idle, busy = _Runner(False), _Runner(True)
    asyncio.run(_observer().after_terminal(None, idle))
    asyncio.run(_observer().after_terminal(None, busy))
    assert idle.released == [(PROJECT, SHARED_ROLE)] and idle.stale == []
    assert busy.released == [] and busy.stale == [PROJECT]


# ---------------------------------------------------------------------------
# The backup a run names must exist (sweep #3: backup_retention)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("retention", [0, "0", "not-a-number", None])
def test_the_backup_just_taken_survives_any_retention_setting(tmp_path, monkeypatch, retention):
    fwdata = tmp_path / "Projects" / "RetProj" / "RetProj.fwdata"
    fwdata.parent.mkdir(parents=True)
    fwdata.write_bytes(b"data")
    monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: fwdata)
    monkeypatch.setattr(backup_mod, "BACKUP_ROOT", tmp_path / "backups")
    monkeypatch.setattr(backup_mod, "config_get",
                        lambda key, default: retention if key == backup_mod.BACKUP_RETENTION_KEY else default)
    result = backup_mod.perform_pre_write_backup("RetProj")
    assert result["created"] is True, result
    assert result["path"] and Path(result["path"]).is_file()


# ---------------------------------------------------------------------------
# The self-lock (found live by L-0): our own read worker is not "another program"
# ---------------------------------------------------------------------------



def _access(verdict, pid=None, process="python"):
    holder = project_access.LockHolder(pid=pid, process_name=process, timestamp_ticks=None) \
        if pid is not None else None
    return project_access.ProjectAccess(
        project_name=PROJECT, verdict=verdict, sharing_enabled=False, holder=holder,
        lock_age_seconds=None, probed=True)


class _PidReadWorker(FakeReadWorker):
    pid = 31337


def _probe_sequence(monkeypatch, *answers):
    calls = []

    def probe(name):
        calls.append(name)
        return answers[min(len(calls), len(answers)) - 1]

    monkeypatch.setattr(project_access, "probe_project_access", probe)
    return calls


async def test_a_lock_held_by_our_own_read_worker_is_released_then_filing_starts(filing_env, monkeypatch):
    filing_env.install(_PidReadWorker(facts={"pukul": [analysis("a1")]}), FakeFilingWorker())
    # Preview and confirm both see our worker's lock; after the release: free.
    _probe_sequence(monkeypatch, _access("held_by_other", 31337), _access("held_by_other", 31337),
                    _access("free"))
    preview = await call(filing_args())
    assert preview["error_code"] == "confirmation_required"
    assert preview["plan"]["access"]["verdict"] == "held_by_mcp_read_worker"
    assert "refused_on_confirm" not in preview["plan"]["access"]
    started = await call(filing_args(confirmed=True, plan_id=preview["plan_id"]))
    assert started.get("run_id"), started
    assert (PROJECT, SHARED_ROLE) in filing_env.pool.released
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)


async def test_after_the_release_anyone_else_holding_it_is_still_refused(filing_env, monkeypatch):
    filing_env.install(_PidReadWorker(facts={"pukul": [analysis("a1")]}), FakeFilingWorker())
    _probe_sequence(monkeypatch, _access("held_by_other", 31337), _access("held_by_other", 31337),
                    _access("open_exclusive", 999, "FieldWorks"))
    preview = await call(filing_args())
    refused = await call(filing_args(confirmed=True, plan_id=preview["plan_id"]))
    assert refused["error_code"] == "project_locked"
    assert refused["holder_pid"] == 999
    assert filing_env.pool.spawned == []


async def test_a_lock_held_by_another_python_process_is_not_mistaken_for_ours(filing_env, monkeypatch):
    filing_env.install(_PidReadWorker(facts={"pukul": [analysis("a1")]}), FakeFilingWorker())
    _probe_sequence(monkeypatch, _access("held_by_other", 4242))
    preview = await call(filing_args())
    assert preview["plan"]["access"]["verdict"] == "held_by_other"
    assert preview["plan"]["access"]["refused_on_confirm"] is True


async def test_on_a_shared_project_our_read_worker_stays_open_and_the_claim_is_shared(
        filing_env, monkeypatch):
    """Live: on a shared project the two opens coexist, so nothing is released
    and reads keep answering (FR-027) -- sharing read off the SETTING, since the
    lock verdict for a Python holder is `held_by_other` either way."""
    from flextoolsmcp.server.filing import claims

    filing_env.install(_PidReadWorker(facts={"pukul": [analysis("a1")]}),
                       FakeFilingWorker(delay=2.0), grace_window=0.1)
    shared_self = project_access.ProjectAccess(
        project_name=PROJECT, verdict="held_by_other", sharing_enabled=True,
        holder=project_access.LockHolder(pid=31337, process_name="python", timestamp_ticks=None),
        lock_age_seconds=None, probed=True)
    monkeypatch.setattr(project_access, "probe_project_access", lambda name: shared_self)
    preview = await call(filing_args())
    assert preview["plan"]["access"]["verdict"] == "held_by_mcp_read_worker"
    assert "stays open" in preview["plan"]["access"]["note"]
    started = await call(filing_args(confirmed=True, plan_id=preview["plan_id"]))
    assert started.get("run_id"), started
    # While the run goes: the read worker was NOT released for the writable
    # open, the claim is shared, and reads are not refused (FR-027).
    assert (PROJECT, SHARED_ROLE) not in filing_env.pool.released
    claim = claims.lookup(PROJECT)
    assert claim is not None and claim.shared is True
    assert claims.reads_refused(PROJECT) is None
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)


def test_the_in_progress_hint_does_not_promise_reads_on_a_non_shared_project():
    """Live (S6): on a non-shared project a try-word IS refused during filing."""
    from flextoolsmcp.server.filing import claims

    non_shared = claims.FilingClaim(project=PROJECT, run_id="r1", started_at="t", shared=False)
    shared = claims.FilingClaim(project=PROJECT, run_id="r2", started_at="t", shared=True)
    assert "not blocked" not in claims.in_progress_hint(non_shared)
    assert "wait for it too" in claims.in_progress_hint(non_shared)
    assert "not blocked" in claims.in_progress_hint(shared)
