#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One filing job per project, without freezing the lexicon (parser-check CP4,
US4; FR-026..FR-028; SC-006, SC-007; research R-10, R-11).

  * a second filing request against a busy project is refused in under a
    second with the four fields, BEFORE the engine check (row 2) -- a
    boom-stub on the engine proves nothing heavy ran first;
  * the claim clears on every terminal state -- success, refusal, cancel,
    worker crash -- and the server-crash case is the startup sweep;
  * the claim is not a lock: filing on project Q is not refused on P's
    account, and read-only tools keep working. On a project with sharing OFF,
    FR-027 as amended after L-0 (claims.READS_REFUSED_ON_NON_SHARED_DURING_FILING)
    refuses reads while a job runs -- a writable and a read-only open cannot
    coexist there; both cases are pinned here.
"""

import asyncio
import json
import time

import pytest

import filing_fakes
from filing_fakes import PROJECT, FakeFilingWorker, FakeReadWorker, analysis, call, filing_args
from flextoolsmcp.server.filing import claims
from flextoolsmcp.server.handlers import parse as parse_handler
from flextoolsmcp.server.parse.record import RunRecord
from flextoolsmcp.server.parse.worker_client import WorkerError

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env

WORDS = ["w1", "w2", "w3", "w4"]


async def _start(filing_env, *, filing_worker=None, shared=False):
    filing_env.install(
        FakeReadWorker(facts={w: [analysis(f"a-{w}")] for w in WORDS}),
        filing_worker or FakeFilingWorker(delay=0.3),
        grace_window=0.05,
    )
    if shared:
        filing_env.set_access("open_shared")
    first = await call(filing_args(scope_value=WORDS))
    started = await call(filing_args(scope_value=WORDS, confirmed=True, plan_id=first["plan_id"]))
    assert started["filing"] == "started", started
    return started


async def _try_word(word="pukul"):
    response = await parse_handler.handle_flextools_try_word({"word": word, "level": "plain"})
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# FR-026 / SC-006 -- the second request
# ---------------------------------------------------------------------------


async def test_a_second_filing_request_is_refused_fast_with_four_fields(filing_env):
    started = await _start(filing_env)

    async def _boom(*_a, **_k):
        raise AssertionError("row 2 comes before the engine check")

    filing_env.read.check_engine = _boom
    t0 = time.perf_counter()
    refused = await call(filing_args(scope_value=WORDS))
    elapsed = time.perf_counter() - t0

    assert refused["error_code"] == "parser_filing_in_progress"
    assert elapsed < 1.0, f"refused in {elapsed:.3f}s"
    assert refused["run_id"] == started["run_id"]
    assert refused["started_at"] and isinstance(refused["words_completed"], int)
    assert f"flextools_parse_status(run_id='{started['run_id']}')" in refused["hint"]
    handle = filing_env.runner.get(started["run_id"])
    await asyncio.wait_for(handle.done.wait(), timeout=10)


async def test_words_completed_is_read_live(filing_env):
    started = await _start(filing_env)
    handle = filing_env.runner.get(started["run_id"])
    while handle.words_completed < 2:
        await asyncio.sleep(0.02)
    assert claims.lookup(PROJECT).words_completed >= 2
    await asyncio.wait_for(handle.done.wait(), timeout=10)


async def test_another_project_is_not_refused_on_this_ones_account(filing_env):
    await _start(filing_env)
    assert claims.lookup("Other") is None
    assert claims.acquire("Other", "o" * 32) is not None


def test_the_claim_is_one_per_project_and_case_insensitive():
    claims.clear()
    assert claims.acquire("Demo", "a" * 32) is not None
    assert claims.acquire("DEMO", "b" * 32) is None
    assert claims.lookup("demo").run_id == "a" * 32
    assert claims.release("Demo", "b" * 32) is False, "only the holder releases"
    assert claims.release("Demo", "a" * 32) is True
    claims.clear()


# ---------------------------------------------------------------------------
# FR-028 -- the claim clears on EVERY terminal state
# ---------------------------------------------------------------------------


async def _ends(filing_env, filing_worker):
    started = await _start(filing_env, filing_worker=filing_worker)
    handle = filing_env.runner.get(started["run_id"])
    await asyncio.wait_for(handle.done.wait(), timeout=10)
    return handle, json.loads((filing_env.record_dir / started["run_id"] / "meta.json")
                              .read_text("utf-8"))["filing"]


async def test_it_clears_on_success(filing_env):
    handle, section = await _ends(filing_env, FakeFilingWorker())
    assert section["state"] == "completed" and section["persisted"] is True
    assert claims.lookup(PROJECT) is None


async def test_it_clears_on_a_mid_run_refusal(filing_env):
    refusal = WorkerError("grammar changed")
    refusal.error_code = "grammar_load_unclean"
    refusal.detail = {"error_code": "grammar_load_unclean", "signal": "new_load_errors"}
    handle, section = await _ends(filing_env, FakeFilingWorker(fail_with=refusal, fail_after=1))
    assert section["state"] == "refused_midrun"
    assert section["filed_words"] == ["w1"], "what was filed before the refusal is reported"
    assert section["persisted"] is True, "and persisted (FR-034)"
    assert claims.lookup(PROJECT) is None


async def test_it_clears_when_the_worker_crashes(filing_env):
    worker = FakeFilingWorker(fail_with=WorkerError("worker died"), fail_after=1, alive=False)
    handle, section = await _ends(filing_env, worker)
    assert handle.stage.value == "failed"
    assert section["state"] == "crashed" and section["persisted"] is False
    assert claims.lookup(PROJECT) is None


async def test_it_clears_on_cancel(filing_env):
    started = await _start(filing_env)
    await parse_handler.handle_flextools_parse_cancel({"run_id": started["run_id"]})
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)
    assert claims.lookup(PROJECT) is None


async def test_a_failed_save_is_not_reported_as_completed(filing_env):
    handle, section = await _ends(filing_env, FakeFilingWorker(commit_ok=False))
    assert handle.stage.value == "failed"
    assert section["state"] == "failed" and section["persisted"] is False
    assert claims.lookup(PROJECT) is None


def test_the_startup_sweep_marks_an_orphaned_filing_run_crashed(tmp_path):
    record = RunRecord.create(project_name=PROJECT, words_total=3, record_dir=tmp_path,
                              filing={"requested": True, "state": "filing",
                                      "filed_words": ["a"], "backup": {"path": "C:/b/x.fwdata"},
                                      "no_recovery_warning": None})
    record.set_stage(__import__("flextoolsmcp.server.parse.stages", fromlist=["RunStage"])
                     .RunStage.PARSING)
    swept = claims.sweep_orphaned_filing_runs(tmp_path)
    assert swept == [record.run_id]
    meta = record.read_meta()
    assert meta.filing["state"] == "crashed" and meta.stage == "failed"
    assert "C:/b/x.fwdata" in meta.filing["crash_note"]
    assert claims.sweep_orphaned_filing_runs(tmp_path) == [], "idempotent"


def test_the_sweep_leaves_finished_and_read_only_runs_alone(tmp_path):
    RunRecord.create(project_name=PROJECT, record_dir=tmp_path,
                     filing={"requested": True, "state": "completed"})
    RunRecord.create(project_name=PROJECT, record_dir=tmp_path)
    assert claims.sweep_orphaned_filing_runs(tmp_path) == []


# ---------------------------------------------------------------------------
# FR-027 / SC-007 (amended after L-0) -- reads during a filing run
# ---------------------------------------------------------------------------


async def test_try_word_answers_during_a_filing_run_on_a_shared_project(filing_env):
    started = await _start(filing_env, shared=True)
    answer = await _try_word()
    assert answer.get("error_code") != "parser_filing_in_progress", answer
    assert answer["status"] == "ok"
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)


async def test_reads_on_a_non_shared_project_are_refused_while_filing(filing_env):
    assert claims.READS_REFUSED_ON_NON_SHARED_DURING_FILING is True, "FR-027 as amended"
    started = await _start(filing_env)
    answer = await _try_word()
    assert answer["error_code"] == "parser_filing_in_progress"
    assert "sharing turned off" in answer["message"]
    assert "wait for it too" in answer["hint"]
    batch = await call({"scope_kind": "words", "scope_value": ["x"]})
    assert batch["error_code"] == "parser_filing_in_progress"
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)


async def test_once_l0_clears_reads_on_a_non_shared_project_proceed(filing_env, monkeypatch):
    monkeypatch.setattr(claims, "READS_REFUSED_ON_NON_SHARED_DURING_FILING", False)
    started = await _start(filing_env)
    answer = await _try_word()
    assert answer["status"] == "ok", answer
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)


async def test_the_run_reading_tools_never_consult_the_claim(filing_env):
    started = await _start(filing_env)
    status = json.loads((await parse_handler.handle_flextools_parse_status(
        {"run_id": started["run_id"]}))[0].text)
    assert status["status"] == "ok"
    log = json.loads((await parse_handler.handle_flextools_parse_log(
        {"run_id": started["run_id"], "section": "summary"}))[0].text)
    assert log["status"] == "ok"
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)


def test_no_project_wide_lock_name_appears_in_the_claim_module():
    import ast
    from pathlib import Path

    source = Path(claims.__file__).read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Attribute)}
    assert not names & {"get_project_write_lock", "project_write_locks",
                        "find_lock_file", "locking", "flock", "lockf"}
    assert ".fwdata.lock" not in source


@pytest.fixture(autouse=True)
def _clean_claims():
    claims.clear()
    yield
    claims.clear()
