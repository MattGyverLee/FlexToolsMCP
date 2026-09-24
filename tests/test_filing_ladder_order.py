#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The filing request's check order (parser-check CP4, FR-002, FR-003, FR-005,
FR-025, FR-030; contracts/tools.md section 1).

A wrong-implementation TRIPWIRE (tasks.md T050). The rung order is
`run_module`'s, literally: session `write_enabled`, then confirmation, then
the access gate, then backup. The tempting order -- refuse a locked project
before asking for confirmation -- is the one the plan first had and the QC
gate caught: an UNCONFIRMED request against a project FLEx holds exclusively
must get the preview (whose `access` names the remedy), and only the
CONFIRMED call is refused `project_locked`.

Every step after a refusal is boom-stubbed (the `_boom_lock` pattern from
`test_issue55_write_safety_ladder.py`): if a later step runs, the test fails
loudly rather than merely disagreeing. And no refusal ever carries a
`run_id` -- the run exists only after every rung has passed (FR-003).

Also the offline half of SC-001: across an unconfirmed request the project
file is byte-identical, no backup directory exists, and the filing worker was
never spawned.
"""

import asyncio

import pytest

import filing_fakes
from filing_fakes import FakeReadWorker, analysis, call, filing_args
from flextoolsmcp.server import backup as backup_mod
from flextoolsmcp.server.filing import claims
from flextoolsmcp.server.parse import runner as runner_mod

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env


def _boom(*_a, **_k):
    raise AssertionError("this step must not run after an earlier refusal")


async def _aboom(*_a, **_k):
    raise AssertionError("this step must not run after an earlier refusal")


@pytest.fixture
def no_run(monkeypatch):
    """start_run and the backup are booms: nothing past a refusal may reach them."""
    monkeypatch.setattr(runner_mod.ParseRunner, "start_run", _aboom)
    monkeypatch.setattr(backup_mod, "perform_pre_write_backup", _boom)


def _worker():
    return FakeReadWorker(facts={"pukul": [analysis("a1")], "kirim": [analysis("a2")]})


def _preview_then_confirm(**confirm_extra):
    first = asyncio.run(call(filing_args()))
    assert first["error_code"] == "confirmation_required", first
    return first, asyncio.run(call(filing_args(confirmed=True, plan_id=first["plan_id"],
                                               **confirm_extra)))


# ---------------------------------------------------------------------------
# Row 2 -- the claim, before anything touches the project
# ---------------------------------------------------------------------------


def test_a_held_claim_refuses_before_the_worker_is_asked_anything(filing_env, no_run):
    worker = _worker()
    filing_env.install(worker)
    claims.acquire(filing_fakes.PROJECT, "c" * 32, started_at="2026-09-24T01:00:00+00:00")
    payload = asyncio.run(call(filing_args()))
    assert payload["error_code"] == "parser_filing_in_progress"
    assert worker.calls == [], "row 2 comes before the engine, scope, preview and gate"


# ---------------------------------------------------------------------------
# Row 3 -- the session grants writing, not the call
# ---------------------------------------------------------------------------


def test_a_read_only_session_refuses_naming_flextools_start_and_parses_nothing(filing_env, no_run):
    worker = _worker()
    filing_env.install(worker)
    filing_env.monkeypatch.setattr(filing_fakes.parse_handler.session_state, "write_enabled", False)
    payload = asyncio.run(call(filing_args()))
    assert payload["error_code"] == "server_state_error"
    assert payload["server_state"] == "write_disabled"
    assert payload["component"] == "session"
    assert "flextools_start(write_enabled=true)" in payload["state_description"]
    assert worker.calls == []
    assert "run_id" not in payload


# ---------------------------------------------------------------------------
# Rows 4-6 -- filing's own preflights
# ---------------------------------------------------------------------------


def test_a_missing_agent_refuses_before_any_preview_is_built(filing_env, no_run):
    agent = {"state": "absent", "agent_guid": "kguidAgentHermitCrabParser",
             "agent_name": "HermitCrab", "active_engine": "HC",
             "probe_source": "bootstrap_absent", "hint": "Run Try a Word once in FLEx."}
    worker = FakeReadWorker(facts={"pukul": [analysis("a1")]}, agent=agent)
    filing_env.install(worker)
    payload = asyncio.run(call(filing_args()))
    assert payload["error_code"] == "parser_agent_missing"
    assert payload["probe_source"] == "bootstrap_absent"
    assert "filing_preview" not in worker.calls and "resolve_scope" not in worker.calls
    assert "run_id" not in payload


def test_the_agent_refusal_validates_as_the_existing_model(filing_env, no_run):
    from flextoolsmcp.server.response_models import ParserAgentMissingDetail

    agent = {"state": "absent", "agent_guid": "kguidAgentHermitCrabParser",
             "agent_name": "HermitCrab", "active_engine": "HC",
             "probe_source": "lookup_failed", "hint": "h"}
    filing_env.install(FakeReadWorker(agent=agent))
    payload = asyncio.run(call(filing_args()))
    ParserAgentMissingDetail(**{k: payload[k] for k in
                                ("agent_guid", "agent_name", "active_engine", "probe_source", "hint")})


def test_a_missing_filing_surface_refuses_before_the_scope(filing_env, no_run):
    from flextoolsmcp.server.filing import filer

    worker = _worker()
    filing_env.install(worker)
    filing_env.monkeypatch.setattr(filer, "probe_filing_surface", lambda: filer.SurfaceProbe(
        ok=False, signal="incompatible_surface", missing_members=["ParseFiler.ProcessParse"]))
    payload = asyncio.run(call(filing_args()))
    assert payload["error_code"] == "parser_core_missing"
    assert payload["missing_members"] == ["ParseFiler.ProcessParse"]
    assert "resolve_scope" not in worker.calls


# ---------------------------------------------------------------------------
# Rows 8, 10, 11 -- THE TRIPWIRE: confirmation before the access gate
# ---------------------------------------------------------------------------


def test_unconfirmed_against_an_exclusive_hold_gets_the_preview_not_project_locked(filing_env, no_run):
    filing_env.install(_worker())
    filing_env.set_access("open_exclusive")
    payload = asyncio.run(call(filing_args()))
    assert payload["error_code"] == "confirmation_required", (
        "run_module's rung order: an unconfirmed request is previewed first"
    )
    access = payload["plan"]["access"]
    assert access["verdict"] == "open_exclusive"
    assert access["refused_on_confirm"] is True
    assert access["remedy"]


def test_confirmed_against_an_exclusive_hold_is_project_locked(filing_env, no_run):
    filing_env.install(_worker())
    filing_env.set_access("open_exclusive")
    _, confirmed = _preview_then_confirm()
    assert confirmed["error_code"] == "project_locked"
    assert confirmed["verdict"] == "open_exclusive"
    assert "run_id" not in confirmed
    assert filing_env.pool.spawned == []


def test_confirmed_against_another_live_holder_is_project_locked(filing_env, no_run):
    filing_env.install(_worker())
    filing_env.set_access("held_by_other")
    _, confirmed = _preview_then_confirm()
    assert confirmed["error_code"] == "project_locked"


def test_an_unknown_access_state_is_refused_on_confirm_unlike_run_module(filing_env, no_run):
    """#118: run_module proceeds on `unknown`; filing refuses it (a disclosed divergence)."""
    filing_env.install(_worker())
    filing_env.set_access("unknown")
    first, confirmed = _preview_then_confirm()
    assert first["plan"]["access"]["refused_on_confirm"] is True
    assert confirmed["error_code"] == "project_drive_unavailable"
    assert "run_id" not in confirmed


def test_a_shared_project_proceeds_with_the_verbatim_advisory(filing_env):
    from flextoolsmcp.server.filing import wording

    filing_env.install(_worker())
    filing_env.set_access("open_shared")
    first, started = _preview_then_confirm()
    assert first["plan"]["access"]["shared_mode_advisory"] == wording.SHARED_MODE_ADVISORY
    assert started["filing"] == "started", started
    assert started["shared_mode_advisory"] == wording.SHARED_MODE_ADVISORY


# ---------------------------------------------------------------------------
# FR-003 -- the run exists only after every rung
# ---------------------------------------------------------------------------


def test_start_run_is_reached_only_on_the_confirmed_call(filing_env, monkeypatch):
    calls = []
    real = runner_mod.ParseRunner.start_run

    async def _spy(self, **kwargs):
        calls.append(kwargs)
        return await real(self, **kwargs)

    monkeypatch.setattr(runner_mod.ParseRunner, "start_run", _spy)
    filing_env.install(_worker())
    first, started = _preview_then_confirm()
    assert "run_id" not in first
    assert len(calls) == 1 and calls[0].get("filing") is True
    assert started["run_id"] and started["filing"] == "started"


def test_the_backup_is_taken_before_the_filing_worker_is_spawned(filing_env, monkeypatch):
    """FR-008: backed up before the project is opened for writing."""
    order = []
    real_backup = backup_mod.perform_pre_write_backup

    def _spy_backup(name, **kwargs):
        order.append("backup")
        return real_backup(name, **kwargs)

    monkeypatch.setattr(backup_mod, "perform_pre_write_backup", _spy_backup)
    filing_env.install(_worker())
    real_get = filing_env.pool.get

    async def _spy_get(name, *, role="shared"):
        if role == "filing":
            order.append("spawn")
        return await real_get(name, role=role)

    filing_env.pool.get = _spy_get
    _preview_then_confirm()
    assert order[:2] == ["backup", "spawn"], order


# ---------------------------------------------------------------------------
# SC-001 (offline half) -- the preview writes nothing
# ---------------------------------------------------------------------------


def test_an_unconfirmed_request_writes_nothing(filing_env, no_run):
    filing_env.install(_worker())
    before = filing_env.fwdata_sha256()
    for extra in ({}, {"confirmed": True}, {"confirmed": True, "plan_id": "e" * 64}):
        payload = asyncio.run(call(filing_args(**extra)))
        assert payload["error_code"] == "confirmation_required"
        assert "run_id" not in payload
    assert filing_env.fwdata_sha256() == before
    assert not filing_env.backup_root.exists() or not any(filing_env.backup_root.rglob("*"))
    assert filing_env.pool.spawned == []
    assert claims.lookup(filing_fakes.PROJECT) is None


def test_the_preview_message_states_the_bound_as_a_number_even_zero(filing_env, no_run):
    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1", opinion="approves")]}))
    payload = asyncio.run(call(filing_args()))
    assert "may delete up to 0 analyses" in payload["message"]
    assert payload["plan"]["deletion_projection"]["upper_bound"] == 0
