#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`flextools_parse_status` -- a dead run is a successful answer
(parser-check CP2b; FR-033, FR-035, FR-036; contracts/tools.md,
"The one asymmetry that is easy to implement wrong").

THE ASYMMETRY, AND WHY IT GETS ITS OWN FILE:

    ASKING about a run that failed or was cancelled  -> status "ok"
    ACTING on a run that failed or was cancelled     -> parse_job_cancelled

Both directions are tested, because getting one right is no evidence for
the other and the natural wrong implementation gets exactly one of them
wrong. Reporting a dead run as an error conflates "your question was wrong"
with "the thing you asked about went wrong": a caller polling a batch would
see their poll fail rather than learn that their batch did, and the obvious
reaction to a failing poll is to stop polling -- which is precisely when the
partial results stop being read.

The only refusal this tool issues is `parse_run_not_found`, for a handle
that corresponds to no run at all. That is the one case where the REQUEST is
wrong rather than the run.

Run with:
    python -m pytest tests/test_parse_status_handler.py -q
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import (  # noqa: E402
    ParseRunner,
    RunAlreadyTerminal,
)
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402
from flextoolsmcp.server.parse.worker_client import WorkerError  # noqa: E402

from test_try_word_handler import Pool, RecordingWorker  # noqa: E402


class SlowWorker(RecordingWorker):
    """A worker that holds each word until released.

    Lets a test observe a run mid-flight -- which is the only way to check
    a non-terminal status response, and the only way to cancel something
    that has not already finished.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.release = asyncio.Event()
        self.reached = asyncio.Event()

    async def parse_word(self, **kwargs):
        self.calls.append(kwargs)
        self.reached.set()
        await self.release.wait()
        return {"parse": {"parsed": True, "analysis_count": 1}, "trace_xml": None}


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    instance = ParseRunner(
        pool=Pool(RecordingWorker()), record_dir=tmp_path / "runs", grace_window=30.0
    )
    parse_handler.set_runner(instance)
    try:
        yield instance
    finally:
        parse_handler.set_runner(None)


async def status(run_id):
    response = await parse_handler.handle_flextools_parse_status({"run_id": run_id})
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# FR-033 -- a terminal run is a SUCCESSFUL response
# ---------------------------------------------------------------------------


async def test_a_completed_run_reports_ok_with_its_summary(runner):
    handle = await runner.start_run(project_name="P", wordforms=["makan", "pukul"])
    assert handle.stage is RunStage.COMPLETED

    payload = await status(handle.run_id)

    assert payload["status"] == "ok"
    assert payload["stage"] == "completed"
    assert payload["words_completed"] == 2
    assert payload["words_total"] == 2
    assert payload["result_summary"]["words"] == 2
    assert payload["next_step"] is None, (
        "a completed run has nothing to advise; the results are where the "
        "response says they are"
    )


async def test_a_completed_explain_runs_summary_reports_nonzero_parsed(
    tmp_path, monkeypatch
):
    """The NEW HIGH sibling QC found: before this fix, `entry["parse"]` was
    `None` for every explain/restricted entry (`worker_main.py`'s
    `BackendFacade.parse()` returned `{"parse": None, ...}` for both), so
    `_result_summary` read `parse.get("parsed")` against an always-empty
    dict and reported `parsed: 0` on ANY completed explain/restricted run
    -- indistinguishable from "every word failed to parse" even when every
    word held. This pins the fix: a successful explain run's summary must
    report the words that parsed, not zero.
    """
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    worker = RecordingWorker(trace_outcome="success")
    instance = ParseRunner(
        pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=30.0
    )
    parse_handler.set_runner(instance)
    try:
        handle = await instance.start_run(
            project_name="P", wordforms=["makan", "pukul"], level="explain"
        )
        assert handle.stage is RunStage.COMPLETED

        payload = await status(handle.run_id)
    finally:
        parse_handler.set_runner(None)

    summary = payload["result_summary"]
    assert summary["words"] == 2
    assert summary["parsed"] == 2, (
        "both words held under explain; reporting 0 here is the exact "
        "defect this test exists to catch"
    )
    assert summary["hypotheses_held"] == 0, (
        "explain never carries hypothesis_held -- that question was never "
        "asked at this level"
    )


async def test_a_completed_restricted_runs_summary_counts_hypotheses_held(
    tmp_path, monkeypatch
):
    """The `restricted` counterpart: its entries carry `hypothesis_held`,
    never `parsed`, so the summary must count them under their own key
    rather than conflating -- or silently dropping -- them into `parsed`.
    """
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    worker = RecordingWorker(trace_outcome="success")
    instance = ParseRunner(
        pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=30.0
    )
    parse_handler.set_runner(instance)
    try:
        handle = await instance.start_run(
            project_name="P",
            wordforms=["makan"],
            level="restricted",
            restricted_to=(5001,),
        )
        assert handle.stage is RunStage.COMPLETED

        payload = await status(handle.run_id)
    finally:
        parse_handler.set_runner(None)

    summary = payload["result_summary"]
    assert summary["hypotheses_held"] == 1
    assert summary["parsed"] == 0, (
        "restricted's entries never carry `parsed`, so it must not be "
        "credited here either"
    )


async def test_a_failed_run_reports_ok_and_carries_its_failure(runner, tmp_path):
    """The run failed. The question did not.

    Reported as `status: ok` with a `failure` block -- not as an error
    envelope. This is the direction most likely to be implemented
    backwards, because "the run failed, so return an error" reads as
    obviously right until you are the caller polling it.
    """
    boom = WorkerError("the grammar would not load")
    failing = ParseRunner(
        pool=Pool(RecordingWorker(fail_with=boom)),
        record_dir=tmp_path / "failruns",
        grace_window=30.0,
    )
    parse_handler.set_runner(failing)
    try:
        handle = await failing.start_run(project_name="P", wordforms=["makan"])
        assert handle.stage is RunStage.FAILED

        payload = await status(handle.run_id)
    finally:
        parse_handler.set_runner(None)

    assert payload["status"] == "ok", (
        "a failed run was reported as a failed REQUEST; asking about a dead "
        "run is a successful query (FR-033)"
    )
    assert "error_code" not in payload
    assert payload["stage"] == "failed"
    assert payload["failure"]["message"]
    assert payload["failure"]["stage_at_failure"]


async def test_a_failed_runs_guidance_names_instruments_never_a_retry(
    runner, tmp_path
):
    """FR-034: diagnose, do not repeat.

    The commonest failure is memory exhausted while loading the grammar,
    and repeating the run repeats the step that exhausted it.
    """
    failing = ParseRunner(
        pool=Pool(RecordingWorker(fail_with=WorkerError("out of memory"))),
        record_dir=tmp_path / "failruns2",
        grace_window=30.0,
    )
    parse_handler.set_runner(failing)
    try:
        handle = await failing.start_run(project_name="P", wordforms=["makan"])
        payload = await status(handle.run_id)
    finally:
        parse_handler.set_runner(None)

    tools = [rung["tool"] for rung in payload["next_step"]]
    assert "flextools_health" in tools
    assert "flextools_grammar_health" in tools
    assert "flextools_try_word" not in tools, (
        "the guidance offers a retry; FR-034 says name the instruments"
    )
    prose = " ".join(r["action"] + r["rationale"] for r in payload["next_step"]).lower()
    assert "try again" not in prose and "retry" not in prose


async def test_a_cancelled_run_reports_ok_with_what_survived(tmp_path, monkeypatch):
    """FR-036, the reporting half: success, `words_completed`, stage at cancel."""
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    worker = SlowWorker()
    instance = ParseRunner(
        pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=0.05
    )
    parse_handler.set_runner(instance)
    try:
        handle = await instance.start_run(
            project_name="P", wordforms=["a", "b", "c", "d"]
        )
        assert not handle.is_terminal, "the slow worker should outlive the window"

        await asyncio.wait_for(worker.reached.wait(), timeout=5)
        await instance.cancel_run(handle.run_id)
        worker.release.set()
        await asyncio.wait_for(handle.done.wait(), timeout=10)

        payload = await status(handle.run_id)
    finally:
        parse_handler.set_runner(None)

    assert payload["status"] == "ok", (
        "a cancelled run was reported as a failed request; the caller asked "
        "a fair question and got a true answer (FR-033)"
    )
    assert "error_code" not in payload
    assert payload["stage"] == "cancelled"
    assert payload["state_at_cancel"], "the stage it was in when it stopped"
    assert payload["words_completed"] >= 1, (
        "the words that finished before the cancel are not lost (FR-029)"
    )
    assert payload["words_completed"] < payload["words_total"]
    assert payload["partial_results_available"] is True


# ---------------------------------------------------------------------------
# FR-036 -- the other direction: ACTING on a terminal run refuses
# ---------------------------------------------------------------------------


async def test_a_second_cancel_raises_parse_job_cancelled(runner):
    """The direction `flextools_parse_status` must NOT take.

    Paired with the test above deliberately: together they are the
    asymmetry. One of them passing is no evidence about the other, and an
    implementation that returned an error from both -- or success from both
    -- would pass whichever one was written first.
    """
    handle = await runner.start_run(project_name="P", wordforms=["makan"])
    assert handle.stage is RunStage.COMPLETED

    with pytest.raises(RunAlreadyTerminal) as caught:
        await runner.cancel_run(handle.run_id)

    detail = caught.value.detail
    assert detail["error_code"] == "parse_job_cancelled"
    assert detail["run_id"] == handle.run_id
    assert detail["words_completed"] == 1
    assert detail["state_at_cancel"] == "completed"
    assert detail["hint"]

    # And the run is unchanged by having been asked.
    assert handle.stage is RunStage.COMPLETED


async def test_asking_after_that_same_run_is_still_a_successful_query(runner):
    """The asymmetry, on ONE run, in one test.

    The two tests above establish each direction separately; this one puts
    them on the same object, which is where a shared "is it terminal?"
    branch would collapse them.
    """
    handle = await runner.start_run(project_name="P", wordforms=["makan"])

    with pytest.raises(RunAlreadyTerminal):
        await runner.cancel_run(handle.run_id)

    payload = await status(handle.run_id)
    assert payload["status"] == "ok"
    assert payload["stage"] == "completed"
    assert "error_code" not in payload


def test_parse_job_cancelled_is_not_reachable_from_the_status_handler():
    """Structural: the status handler never calls `cancel_run`.

    The behavioural tests cover the paths they walk. This one fails if a
    future edit routes a cancel through the status tool at all -- which is
    the change that would break the asymmetry everywhere at once rather
    than on one path.
    """
    import ast
    import inspect
    import textwrap

    source = textwrap.dedent(
        inspect.getsource(parse_handler.handle_flextools_parse_status)
    )
    tree = ast.parse(source)
    function = tree.body[0]

    # The docstring is STRIPPED before scanning, and comments never reach
    # the AST. Both discuss cancellation at length, and rightly so -- the
    # asymmetry is the hardest thing about this handler to get right, so
    # explaining it there is the point. What must not appear is the ACT.
    body = function.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    code = ast.unparse(ast.Module(body=body, type_ignores=[]))

    assert "cancel_run" not in code, (
        "flextools_parse_status calls cancel_run; it is a read-only query "
        "and must not act on the run it reports (FR-033 / FR-036)"
    )
    assert "parse_job_cancelled" not in code, (
        "flextools_parse_status emits parse_job_cancelled; that code is for "
        "ACTING on a terminal run, and asking about one is not acting on it"
    )
    # `stage_at_cancel` IS read here, and must be: it is what a cancelled
    # run reports. Asserted so the check above is understood to be about
    # the verb and not about the word.
    assert "stage_at_cancel" in code


# ---------------------------------------------------------------------------
# FR-035 -- the only refusal, and it names the alternatives
# ---------------------------------------------------------------------------


async def test_an_unknown_handle_refuses_naming_the_handles_that_exist(runner):
    known = await runner.start_run(project_name="P", wordforms=["makan"])

    payload = await status("0" * 32)

    assert payload["status"] == "error"
    assert payload["error_code"] == "parse_run_not_found"
    assert payload["run_id"] == "0" * 32
    assert known.run_id in payload["available_runs"], (
        "a handle is an opaque 32-character string; told only 'no such run', "
        "a caller has nothing to compare theirs against (FR-035)"
    )
    assert known.run_id in payload["hint"]


async def test_an_unknown_handle_on_a_server_with_no_runs_says_so(runner):
    """The empty case reads differently, and should.

    "This server has no runs at all" points at the real cause -- a handle
    from an earlier server process -- which "no such run" alone does not.
    """
    payload = await status("0" * 32)

    assert payload["error_code"] == "parse_run_not_found"
    assert payload["available_runs"] == []
    assert "earlier server process" in payload["hint"]


async def test_parse_run_not_found_is_the_only_refusal_the_tool_issues(
    runner, tmp_path
):
    """Swept across every terminal stage, not argued from one.

    completed, failed and cancelled must all come back `ok`. The refusal is
    reserved for a handle naming no run.
    """
    outcomes = {}

    completed = await runner.start_run(project_name="P", wordforms=["makan"])
    outcomes["completed"] = await status(completed.run_id)

    failing = ParseRunner(
        pool=Pool(RecordingWorker(fail_with=WorkerError("boom"))),
        record_dir=tmp_path / "sweep-fail",
        grace_window=30.0,
    )
    parse_handler.set_runner(failing)
    try:
        failed = await failing.start_run(project_name="P", wordforms=["makan"])
        outcomes["failed"] = await status(failed.run_id)
    finally:
        parse_handler.set_runner(runner)

    for stage, payload in outcomes.items():
        assert payload["status"] == "ok", f"{stage} was reported as an error"
        assert "error_code" not in payload, f"{stage} carried an error code"

    unknown = await status("f" * 32)
    assert unknown["error_code"] == "parse_run_not_found"


# ---------------------------------------------------------------------------
# SC-009's observable
# ---------------------------------------------------------------------------


async def test_interleaved_by_is_reported(runner):
    """A batch paused by an urgent word must not look stalled.

    Set directly here rather than by driving a real interleave -- that is
    `tests/test_parse_priority_queue.py`'s job. What this asserts is that
    the field reaches the caller at all, which is what makes SC-009
    observable rather than merely true.
    """
    handle = await runner.start_run(project_name="P", wordforms=["makan"])
    handle.interleaved_by = "urgent-run-id"

    payload = await status(handle.run_id)

    assert payload["interleaved_by"] == "urgent-run-id"


async def test_a_run_with_the_worker_to_itself_reports_null(runner):
    """Clearing matters as much as setting.

    A stale `interleaved_by` would tell a caller their finished run is
    still queued behind someone else's.
    """
    handle = await runner.start_run(project_name="P", wordforms=["makan"])

    payload = await status(handle.run_id)

    assert payload["interleaved_by"] is None
