#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The backup rung for filing (parser-check CP4, FR-007, FR-008, FR-009, FR-042,
FR-043; SC-004).

BEST-EFFORT, AND STATED BEFORE CONFIRMATION (FR-007; constitution Principle I).
A backup failure never raises and never refuses the run -- but the plan says,
before the human confirms, whether a recovery point will exist, and a run
without one carries the verbatim no-recovery warning in its response AND its
run record. The stated intent must equal what happened (SC-004).

A `run_module` backup taken earlier in the session does not satisfy filing
(FR-008): separate session key, and filing backs up before EVERY run, before
the project is opened for writing.

Nothing filing writes lives inside a project folder (FR-042). A Send/Receive
project -- `.hg` present, or the projects directory unknown -- is told the real
recovery route: do not Send/Receive, delete the copy, re-download (FR-043).
"""

import asyncio
import json
import os

import pytest

import filing_fakes
from filing_fakes import PROJECT, FakeReadWorker, analysis, call, filing_args
from flextoolsmcp.server import backup as backup_mod
from flextoolsmcp.server.filing import paths, wording

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env


def _worker():
    return FakeReadWorker(facts={"pukul": [analysis("a1")]})


def _file(filing_env):
    first = asyncio.run(call(filing_args()))
    assert first["error_code"] == "confirmation_required", first
    started = asyncio.run(call(filing_args(confirmed=True, plan_id=first["plan_id"])))
    return first, started


def _meta_filing(filing_env, run_id):
    return json.loads((filing_env.record_dir / run_id / "meta.json").read_text("utf-8"))["filing"]


# ---------------------------------------------------------------------------
# SC-004 -- intent == outcome
# ---------------------------------------------------------------------------


def test_the_default_backup_is_promised_taken_and_named(filing_env):
    filing_env.install(_worker())
    first, started = _file(filing_env)
    assert first["plan"]["backup"]["outcome"] == "will_be_taken"
    assert started["filing"] == "started"
    backup = started["backup"]
    assert backup["created"] is True and backup["path"]
    assert os.path.isfile(backup["path"])
    assert "no_recovery_warning" not in started
    assert _meta_filing(filing_env, started["run_id"])["backup"]["path"] == backup["path"]


def test_insufficient_disk_space_is_predicted_and_the_run_still_proceeds(filing_env, monkeypatch):
    class _Full:
        free = 1

    monkeypatch.setattr(backup_mod.shutil, "disk_usage", lambda path: _Full())
    filing_env.install(_worker())
    first, started = _file(filing_env)
    plan_backup = first["plan"]["backup"]
    assert plan_backup["outcome"] == "not_expected"
    assert plan_backup["reason"] == "insufficient_disk_space"
    assert plan_backup["no_recovery_warning"].startswith(
        "NO BACKUP WAS TAKEN (insufficient_disk_space). Filing cannot be undone"
    )
    assert started["filing"] == "started", "a failed backup never refuses (Principle I)"
    assert started["no_recovery_warning"].startswith("NO BACKUP WAS TAKEN (insufficient_disk_space)")
    assert _meta_filing(filing_env, started["run_id"])["no_recovery_warning"] == started["no_recovery_warning"]


def test_the_config_opt_out_is_disclosed_and_honoured(filing_env):
    filing_env.set_config("backup_before_write", False)
    filing_env.install(_worker())
    first, started = _file(filing_env)
    assert first["plan"]["backup"]["outcome"] == "disabled_by_configuration"
    assert started["filing"] == "started"
    assert "NO BACKUP WAS TAKEN (backup_before_write=false)" in started["no_recovery_warning"]
    assert not filing_env.backup_root.exists() or not any(filing_env.backup_root.rglob("*.fwdata"))


def test_the_warning_is_verbatim(filing_env):
    text = wording.no_recovery_warning("insufficient_disk_space", False)
    assert text == (
        "NO BACKUP WAS TAKEN (insufficient_disk_space). Filing cannot be undone, and "
        "no recovery point exists for this run."
    )


# ---------------------------------------------------------------------------
# FR-008 -- separate key; before the writable open; every run
# ---------------------------------------------------------------------------


def test_a_run_module_backup_does_not_satisfy_filing(filing_env):
    session = filing_fakes.parse_handler.session_state
    session.record_backup(PROJECT)  # run_module backed this project up already
    filing_env.install(_worker())
    first, started = _file(filing_env)
    assert first["plan"]["backup"]["outcome"] == "will_be_taken"
    assert started["backup"]["created"] is True
    assert PROJECT in session.filing_backed_up_projects


def test_every_filing_run_takes_its_own_backup(filing_env):
    filing_env.install(_worker())
    _, first_run = _file(filing_env)
    asyncio.run(asyncio.wait_for(
        filing_env.runner.get(first_run["run_id"]).done.wait(), timeout=5))
    _, second_run = _file(filing_env)
    # A second run in the same session is backed up again (not skipped as
    # "already backed up", which is run_module's once-per-session rule).
    assert second_run["filing"] == "started"
    assert second_run["backup"]["created"] is True
    assert "no_recovery_warning" not in second_run


# ---------------------------------------------------------------------------
# FR-009 -- a path or the warning, always
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("opt_out", [False, True])
def test_the_started_response_names_a_path_or_carries_the_warning(filing_env, opt_out):
    if opt_out:
        filing_env.set_config("backup_before_write", False)
    filing_env.install(_worker())
    _, started = _file(filing_env)
    has_path = bool((started.get("backup") or {}).get("path"))
    has_warning = bool(started.get("no_recovery_warning"))
    assert has_path != has_warning, started


# ---------------------------------------------------------------------------
# FR-042 -- nothing inside a project folder
# ---------------------------------------------------------------------------


def test_the_backup_lives_outside_every_project_folder(filing_env):
    filing_env.install(_worker())
    _, started = _file(filing_env)
    paths.assert_outside_project(started["backup"]["path"], projects_root=filing_env.projects_dir)


def test_a_record_dir_inside_a_project_folder_is_refused(filing_env, no_spawn):
    inside = filing_env.project_dir / "runs"
    filing_env.install(_worker())
    filing_env.runner._record_dir = inside
    first = asyncio.run(call(filing_args()))
    confirmed = asyncio.run(call(filing_args(confirmed=True, plan_id=first["plan_id"])))
    assert confirmed["error_code"] == "server_state_error"
    assert confirmed["server_state"] == "record_dir_inside_project"
    assert "run_id" not in confirmed
    assert not inside.exists(), "nothing was written inside the project folder"
    assert filing_env.pool.spawned == []


def test_assert_outside_project_refuses_a_path_inside_the_projects_root(tmp_path):
    root = tmp_path / "Projects"
    (root / "Demo").mkdir(parents=True)
    with pytest.raises(paths.ArtifactInsideProject):
        paths.assert_outside_project(root / "Demo" / "x.jsonl", projects_root=root)
    with pytest.raises(paths.ArtifactInsideProject):
        paths.assert_outside_project(str(root / "DEMO" / "sub" / "y"), projects_root=root)
    assert paths.assert_outside_project(tmp_path / "elsewhere", projects_root=root)


# ---------------------------------------------------------------------------
# FR-043 -- Send/Receive
# ---------------------------------------------------------------------------


def test_a_send_receive_project_is_told_the_real_recovery_route(filing_env):
    (filing_env.project_dir / ".hg").mkdir()
    filing_env.set_config("backup_before_write", False)
    filing_env.install(_worker())
    first, started = _file(filing_env)
    assert first["plan"]["send_receive"] is True
    assert first["plan"]["recovery_route"] == wording.SEND_RECEIVE_ROUTE
    assert started["no_recovery_warning"].endswith(wording.SEND_RECEIVE_ROUTE)


def test_a_non_send_receive_project_is_told_what_a_restore_costs(filing_env):
    """No version history behind it: a restore loses everything after the backup."""
    filing_env.install(_worker())
    first, _ = _file(filing_env)
    assert first["plan"]["send_receive"] is False
    assert first["plan"]["recovery_route"] == wording.RESTORE_ROUTE
    assert "replaces the ENTIRE project" in wording.RESTORE_ROUTE
    assert "is lost" in wording.RESTORE_ROUTE and "no version history" in wording.RESTORE_ROUTE


def test_an_unresolvable_projects_directory_is_worded_as_send_receive(monkeypatch):
    monkeypatch.setattr(paths, "projects_directory", lambda: None)
    assert paths.send_receive_status("Anything") == "unknown"
    assert paths.treats_as_send_receive("unknown") is True
    assert wording.no_recovery_warning("r", "unknown").endswith(wording.SEND_RECEIVE_ROUTE)


@pytest.fixture
def no_spawn(monkeypatch):
    from flextoolsmcp.server.parse import runner as runner_mod

    async def _aboom(*_a, **_k):
        raise AssertionError("start_run must not be reached")

    monkeypatch.setattr(runner_mod.ParseRunner, "start_run", _aboom)
