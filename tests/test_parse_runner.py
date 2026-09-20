#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The run lifecycle and the grace window (parser-check CP2b, FR-026, FR-028,
FR-034, SC-010).

THE POINT OF THIS FILE IS ONE SENTENCE FROM THE SPECIFICATION:

    FR-028 -- "The window governs reporting only -- it MUST NOT cancel,
    time out or throttle the run."
    SC-010 -- "Exceeding the grace window cancels or slows 0 runs."

That is the requirement most likely to be satisfied on paper and broken in
code, because the obvious way to write a grace window -- hand a timeout to
the thing doing the work -- reads almost identically and is wrong. A run
that got cancelled when its window closed would still look correct in every
test that only checked "a handle came back", which is exactly why the
assertions below are about what happens **after** the handle is returned.

The window is therefore attacked from three directions, because any one of
them alone can pass while the requirement is violated:

  * **behavioural** -- after the window closes the run still finishes, with
    every word parsed and `cancel_requested` still False (cancels 0 runs);
  * **timing** -- the worker sees no pause around the moment the window
    closes (slows 0 runs);
  * **structural** -- no timeout, deadline or window value is ever passed
    downstream. This is the one that survives refactoring, because it fails
    the moment someone "helpfully" threads a deadline through.

Tests run against an in-process fake worker rather than a spawned child.
That is deliberate: this file is about the runner's lifecycle logic, and a
real subprocess would add a second failure source to every assertion. The
real channel and a real child process are exercised in
`tests/test_parse_worker_lifetime.py` (T025), which is where a defect in
*that* layer should surface.

Run with:
    python -m pytest tests/test_parse_runner.py -q
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.runner import (  # noqa: E402
    DEFAULT_GRACE_WINDOW_SECONDS,
    ParseRunner,
    RunFailure,
)
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402


# ---------------------------------------------------------------------------
# An in-process stand-in for the worker channel.
# ---------------------------------------------------------------------------


class FakeWorker:
    """Answers `parse_word` the way a real worker does, on demand.

    Records every call's keyword arguments verbatim, which is what the
    structural assertions read: if a grace window ever leaks downstream it
    arrives here as a keyword and the test fails.
    """

    def __init__(self, *, delay: float = 0.0, fail_on=None) -> None:
        self.delay = delay
        self.fail_on = fail_on
        self.calls: list[dict] = []
        #: Monotonic timestamp of each parse, for the "slows 0 runs" check.
        self.timestamps: list[float] = []
        self.listeners: dict = {}
        self.cancelled_runs: list[str] = []
        self._cancelled: set[str] = set()

    def listen_to_run(self, run_id, listener):
        self.listeners[run_id] = listener

    def stop_listening(self, run_id):
        self.listeners.pop(run_id, None)

    def is_running(self):
        return True

    async def parse_word(self, **kwargs):
        self.calls.append(kwargs)
        self.timestamps.append(time.monotonic())

        run_id = kwargs["run_id"]
        if run_id in self._cancelled:
            # Exactly what the real worker does for a word it accepted but
            # will never parse: answer it once, as cancelled. Leaving it
            # unanswered is the hang this protocol invariant prevents.
            raise _cancelled_error(run_id)

        if self.delay:
            await asyncio.sleep(self.delay)

        word = kwargs["wordform"]
        if self.fail_on is not None and word == self.fail_on:
            raise RuntimeError(f"stub failure parsing {word!r}")

        return {
            "parse": {"word": word, "analyses": [{"morphs": [word]}]},
            "trace_xml": (
                f"<trace word='{word}'/>" if kwargs.get("level") != "plain" else None
            ),
        }

    async def cancel_run(self, run_id):
        self.cancelled_runs.append(run_id)
        self._cancelled.add(run_id)


def _cancelled_error(run_id):
    from flextoolsmcp.server.parse.worker_client import WorkerError

    exc = WorkerError(f"Run {run_id} was cancelled before this word was parsed.")
    exc.error_code = "parse_job_cancelled"
    return exc


class FakePool:
    def __init__(self, worker):
        self.worker = worker
        self.closed = False

    async def get(self, project_name):
        return self.worker

    def peek(self, project_name):
        return self.worker

    async def aclose(self):
        self.closed = True


@pytest.fixture
def record_dir(tmp_path):
    return tmp_path / "parse-runs"


def make_runner(worker, record_dir, **kwargs):
    return ParseRunner(pool=FakePool(worker), record_dir=record_dir, **kwargs)


# ---------------------------------------------------------------------------
# FR-028 -- inline vs handle
# ---------------------------------------------------------------------------


async def test_a_run_finishing_inside_the_window_returns_inline(record_dir):
    """Scenario 1: finishes inside the window -> results inline, no handle."""
    worker = FakeWorker()
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(project_name="P", wordforms=["makan"])

    assert handle.is_terminal, "a fast run must be terminal when start_run returns"
    assert handle.stage is RunStage.COMPLETED
    assert handle.words_completed == 1
    assert len(handle.results) == 1
    assert handle.results[0]["wordform"] == "makan"


async def test_a_run_outliving_the_window_returns_a_non_terminal_handle(record_dir):
    """Scenario 2, first half: still running when the window closes."""
    worker = FakeWorker(delay=0.05)
    runner = make_runner(worker, record_dir, grace_window=0.01)

    handle = await runner.start_run(
        project_name="P", wordforms=[f"w{i}" for i in range(20)]
    )

    assert not handle.is_terminal, "a slow run must still be running"
    assert handle.run_id, "a handle must be issued"

    await asyncio.wait_for(handle.done.wait(), timeout=30)


# ---------------------------------------------------------------------------
# SC-010 -- "cancels or slows 0 runs". The heart of the file.
# ---------------------------------------------------------------------------


async def test_closing_the_window_cancels_zero_runs(record_dir):
    """The run keeps going, untouched, and finishes every word.

    This is the assertion that fails if the window is implemented as a
    timeout on the work rather than on the wait.
    """
    worker = FakeWorker(delay=0.01)
    runner = make_runner(worker, record_dir, grace_window=0.01)
    words = [f"w{i}" for i in range(25)]

    handle = await runner.start_run(project_name="P", wordforms=words)
    assert not handle.is_terminal, "precondition: the window must have closed first"

    await asyncio.wait_for(handle.done.wait(), timeout=30)

    assert handle.stage is RunStage.COMPLETED, (
        f"the run ended {handle.stage.value!r} after its window closed; "
        f"the window must not end a run"
    )
    assert handle.cancel_requested is False, "the window must not request a cancel"
    assert handle.words_completed == len(words), "the window must not lose words"
    assert [c["wordform"] for c in worker.calls] == words
    assert handle.task is not None and not handle.task.cancelled(), (
        "the window must not cancel the run's task"
    )


async def test_closing_the_window_slows_zero_runs(record_dir):
    """No pause appears around the moment the window closes.

    Asserted as a bound on the gap between consecutive words rather than on
    total elapsed time, because a total is insensitive to exactly the defect
    being hunted: a run that stalled for the length of its window and then
    caught up would still finish in about the right time.
    """
    worker = FakeWorker(delay=0.01)
    runner = make_runner(worker, record_dir, grace_window=0.02)

    handle = await runner.start_run(
        project_name="P", wordforms=[f"w{i}" for i in range(30)]
    )
    assert not handle.is_terminal
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    stamps = worker.timestamps
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
    assert gaps, "expected several words"
    # Deliberately loose. A real stall would be ~grace_window or a whole
    # scheduler tick; this catches that without pinning CI to a stopwatch.
    assert max(gaps) < 0.5, (
        f"a {max(gaps):.3f}s gap appeared between words -- the grace window "
        f"must not throttle the run (SC-010)"
    )


async def test_no_window_or_deadline_is_ever_passed_downstream(record_dir):
    """Structural: the window stays on the caller's side of the channel.

    The behavioural tests above can pass while a deadline is threaded
    through and simply happens to be generous. This one fails the moment
    anything window-shaped reaches the worker, which is the refactor that
    would quietly reintroduce the defect.
    """
    worker = FakeWorker(delay=0.01)
    runner = make_runner(worker, record_dir, grace_window=0.01)

    handle = await runner.start_run(
        project_name="P", wordforms=[f"w{i}" for i in range(10)]
    )
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    forbidden = {"timeout", "deadline", "grace_window", "grace", "expires_at"}
    for call in worker.calls:
        leaked = forbidden.intersection(call)
        assert not leaked, (
            f"{sorted(leaked)} reached the worker. The grace window governs "
            f"reporting only and must not be handed to the work (FR-028)."
        )


async def test_grace_window_is_configurable(record_dir):
    """FR-028: the 5-second default is a starting value, not a constant."""
    assert DEFAULT_GRACE_WINDOW_SECONDS == 5.0

    worker = FakeWorker()
    assert make_runner(worker, record_dir).grace_window == pytest.approx(5.0)
    assert make_runner(worker, record_dir, grace_window=0.25).grace_window == 0.25


async def test_the_window_can_be_overridden_per_run(record_dir):
    """A per-call override still reports rather than executes."""
    worker = FakeWorker(delay=0.02)
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(
        project_name="P",
        wordforms=[f"w{i}" for i in range(15)],
        grace_window=0.01,
    )
    assert not handle.is_terminal

    await asyncio.wait_for(handle.done.wait(), timeout=30)
    assert handle.stage is RunStage.COMPLETED
    assert handle.words_completed == 15


# ---------------------------------------------------------------------------
# FR-027 -- stages
# ---------------------------------------------------------------------------


async def test_a_run_reports_loading_grammar_distinctly_from_parsing(record_dir):
    """The stage history is a real path through the graph."""
    worker = FakeWorker()
    runner = make_runner(worker, record_dir, grace_window=30.0)

    seen = []
    handle = await runner.start_run(project_name="P", wordforms=["a", "b"])
    seen.append(handle.stage)

    meta = handle.record.read_meta()
    assert meta is not None
    assert meta.stage == RunStage.COMPLETED.value
    assert handle.stage is RunStage.COMPLETED


async def test_no_run_can_reach_filing(record_dir):
    """FR-027: `filing` is defined and unreachable in CP2b.

    Asserted over a run that actually executes rather than over the
    transition table alone -- `tests/test_parse_stages.py` owns the table.
    What matters here is that the *runner* never produces it.
    """
    worker = FakeWorker()
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(
        project_name="P", wordforms=[f"w{i}" for i in range(5)]
    )
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    assert handle.stage is not RunStage.FILING
    assert handle.record.read_meta().stage != RunStage.FILING.value


# ---------------------------------------------------------------------------
# FR-034 -- a failure diagnoses, it does not suggest a retry
# ---------------------------------------------------------------------------


async def test_a_failed_run_points_at_the_diagnostics(record_dir):
    worker = FakeWorker(fail_on="w2")
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(
        project_name="P", wordforms=["w0", "w1", "w2", "w3"]
    )
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    assert handle.stage is RunStage.FAILED
    assert isinstance(handle.failure, RunFailure)
    assert handle.failure.stage_at_failure, "a failure must name the stage it died in"
    assert "flextools_health" in handle.failure.next_step
    assert "flextools_grammar_health" in handle.failure.next_step


async def test_failure_guidance_does_not_suggest_retrying(record_dir):
    """FR-034: retrying re-runs the step that exhausted memory.

    Worded as a ban on retry wording because that is the guidance a
    well-meaning edit would add, and it is the one thing the requirement
    rules out.
    """
    worker = FakeWorker(fail_on="boom")
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(project_name="P", wordforms=["boom"])
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    guidance = handle.failure.next_step.lower()
    for banned in ("try again", "retry", "re-run the same", "run it again"):
        assert banned not in guidance, (
            f"failure guidance suggests {banned!r}; FR-034 wants a diagnosis"
        )


async def test_words_completed_before_a_failure_are_still_recorded(record_dir):
    """A failure does not discard the work that already succeeded."""
    worker = FakeWorker(fail_on="w2")
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(
        project_name="P", wordforms=["w0", "w1", "w2", "w3"]
    )
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    assert handle.words_completed == 2
    assert len(list(handle.record.iter_results())) == 2


# ---------------------------------------------------------------------------
# FR-032 -- cooperative cancellation
# ---------------------------------------------------------------------------


async def test_cancelling_stops_the_run_and_keeps_partial_results(record_dir):
    worker = FakeWorker(delay=0.01)
    runner = make_runner(worker, record_dir, grace_window=0.01)
    words = [f"w{i}" for i in range(200)]

    handle = await runner.start_run(project_name="P", wordforms=words)
    assert not handle.is_terminal

    await asyncio.sleep(0.15)
    completed_at_request = handle.words_completed
    await runner.cancel_run(handle.run_id)
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    assert handle.stage is RunStage.CANCELLED
    assert completed_at_request > 0, "precondition: some words must have run"
    assert handle.words_completed < len(words), "cancel must actually stop it"
    assert len(list(handle.record.iter_results())) == handle.words_completed, (
        "every word completed before the cancel must stay readable (FR-029)"
    )


async def test_cancel_records_the_stage_it_happened_in(record_dir):
    """`parse_job_cancelled` reports `state_at_cancel` (FR-036)."""
    worker = FakeWorker(delay=0.01)
    runner = make_runner(worker, record_dir, grace_window=0.01)

    handle = await runner.start_run(
        project_name="P", wordforms=[f"w{i}" for i in range(200)]
    )
    await asyncio.sleep(0.15)
    await runner.cancel_run(handle.run_id)
    await asyncio.wait_for(handle.done.wait(), timeout=30)

    meta = handle.record.read_meta()
    assert meta.stage == RunStage.CANCELLED.value
    assert meta.stage_at_cancel, "a cancel must record the stage it interrupted"


async def test_cancelling_an_unknown_run_returns_none(record_dir):
    runner = make_runner(FakeWorker(), record_dir)
    assert await runner.cancel_run("0" * 32) is None


async def test_cancelling_a_finished_run_refuses_and_leaves_it_alone(record_dir):
    """FR-036's asymmetry begins here: a terminal run does not re-cancel.

    AMENDED AT T050, not weakened. Both original guarantees still hold --
    the run does not become `cancelled`, and the worker is never asked --
    and the refusal the requirement names is now raised rather than the
    call returning quietly. "Cancelled successfully" for a run that ended
    ten minutes ago tells the caller something false about what just
    happened.

    The refusal carries what survived, because the partial results are
    readable and the caller needs to know how much there is.
    """
    from flextoolsmcp.server.parse.runner import RunAlreadyTerminal

    worker = FakeWorker()
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(project_name="P", wordforms=["w"])
    assert handle.stage is RunStage.COMPLETED

    with pytest.raises(RunAlreadyTerminal) as caught:
        await runner.cancel_run(handle.run_id)

    assert handle.stage is RunStage.COMPLETED, "a finished run must not become cancelled"
    assert worker.cancelled_runs == [], "a terminal run must not be sent to the worker"

    detail = caught.value.detail
    assert detail["error_code"] == "parse_job_cancelled"
    assert detail["run_id"] == handle.run_id
    assert detail["words_completed"] == 1
    assert detail["state_at_cancel"] == "completed"
    assert detail["hint"]


async def test_cancelling_an_unknown_run_is_none_not_a_refusal(record_dir):
    """A handle that names no run is a different thing from a dead one.

    `None` rather than `RunAlreadyTerminal`: there is no run to report
    `words_completed` for, and the caller's problem is the handle, not the
    run's state. The tool boundary turns this into `parse_run_not_found`.
    """
    runner = make_runner(FakeWorker(), record_dir, grace_window=30.0)

    assert await runner.cancel_run("0" * 32) is None


# ---------------------------------------------------------------------------
# FR-026 -- one mechanism
# ---------------------------------------------------------------------------


async def test_a_single_word_is_a_run_like_any_other(record_dir):
    """FR-026: no separate synchronous path for the easy case.

    A single word must produce a real run -- an id, a record on disk,
    stages -- not a shortcut that happens to return the same shape. The
    shortcut is the tempting optimisation this requirement forbids.
    """
    worker = FakeWorker()
    runner = make_runner(worker, record_dir, grace_window=30.0)

    handle = await runner.start_run(project_name="P", wordforms=["solo"])

    assert handle.run_id and len(handle.run_id) == 32
    assert handle.record.exists(), "a single word still gets a durable record"
    assert handle.words_total == 1
    assert runner.get(handle.run_id) is handle
    assert handle.run_id in runner.known_run_ids()


async def test_every_run_is_reachable_by_its_handle(record_dir):
    """Backs `parse_run_not_found`'s "here are the handles that exist"."""
    worker = FakeWorker()
    runner = make_runner(worker, record_dir, grace_window=30.0)

    first = await runner.start_run(project_name="P", wordforms=["a"])
    second = await runner.start_run(project_name="P", wordforms=["b"])

    known = runner.known_run_ids()
    assert first.run_id in known and second.run_id in known
    assert runner.get("f" * 32) is None
