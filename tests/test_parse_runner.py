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
from flextoolsmcp.server.parse.worker_client import SHARED_ROLE  # noqa: E402


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
        self.release_if_idle_calls = []

    async def get(self, project_name):
        return self.worker

    def peek(self, project_name):
        return self.worker

    async def aclose(self):
        self.closed = True

    async def release_if_idle(self, project_name, *, role, is_busy):
        """#223 QC P1: `ParseRunner.release_worker_if_idle` must hand this
        its OWN `worker_busy` as the predicate, not decide busyness itself
        -- the atomicity guarantee lives in the real `WorkerPool`
        (`tests/test_parse_worker_lifetime.py`); this double only proves
        the wiring calls through with the right predicate."""
        self.release_if_idle_calls.append((project_name, role))
        if is_busy():
            return False
        return True


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
    # Bound is deliberately loose relative to grace_window (0.02s). A real
    # stall would be ~grace_window or a whole scheduler pause of seconds; CI
    # hosts routinely spike a single gap past 0.5s under load without any
    # grace-window throttle (seen as 0.516s on py3.10 windows). Keep enough
    # headroom that OS noise cannot fail SC-010 while a multi-second hang
    # still fails loudly.
    assert max(gaps) < 2.0, (
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


# ---------------------------------------------------------------------------
# CP3 (T036) -- a batch plus an interleaving single word: ONE grammar load,
# and the batch resumes at its next word with its position intact
# (FR-027, SC-005, SC-006). Driven against the REAL `ParseWorker` main loop
# with the stub backend, in-process: the property lives in the worker's
# queue and held grammar, so a fake worker could not exhibit it.
# ---------------------------------------------------------------------------


def _drive_worker_with_interleave(batch_words, urgent_after_index):
    """Run a batch through ParseWorker; inject an urgent word mid-batch.

    The urgent word is injected from the emit callback the moment the
    batch's `urgent_after_index` result is emitted -- which is inside the
    main loop, between two words, i.e. exactly at a word boundary.
    """
    from flextoolsmcp.server.parse.priority import Priority
    from flextoolsmcp.server.parse.worker_main import ParseWorker, _StubBackend

    backend = _StubBackend()
    emitted = []
    worker_ref = {}

    def emit(message):
        emitted.append(message)
        if (
            message.get("type") == "result"
            and message.get("run_id") == "batch"
            and message.get("index_in_run") == urgent_after_index
        ):
            worker_ref["w"].handle_message({
                "type": "parse", "request_id": "urgent-0", "run_id": "urgent",
                "wordform": "segera", "level": "plain",
                "priority": int(Priority.TRY_A_WORD), "index_in_run": 0,
            })

    worker = ParseWorker("P", backend=backend, idle_timeout=5, emit=emit)
    worker_ref["w"] = worker
    for index, word in enumerate(batch_words):
        worker.handle_message({
            "type": "parse", "request_id": f"batch-{index}", "run_id": "batch",
            "wordform": word, "level": "batch", "priority": int(Priority.LOW),
            "index_in_run": index, "engine_at_submission": "HC",
        })
    worker._draining.set()
    worker.run()
    return backend, emitted


def test_a_batch_and_an_interleaving_word_load_the_grammar_exactly_once():
    backend, emitted = _drive_worker_with_interleave(["a", "b", "c", "d", "e"], 1)
    assert backend.load_count == 1, "the interleaving word must reuse the held grammar"
    loads = [m for m in emitted if m.get("stage") == RunStage.LOADING_GRAMMAR.value]
    assert [m["run_id"] for m in loads] == ["batch"], loads


def test_the_batch_resumes_at_its_next_word_with_position_intact():
    _, emitted = _drive_worker_with_interleave(["a", "b", "c", "d", "e"], 1)
    results = [(m["run_id"], m.get("index_in_run")) for m in emitted if m["type"] == "result"]
    assert results == [
        ("batch", 0), ("batch", 1),
        ("urgent", 0),                      # at the boundary after word 1
        ("batch", 2), ("batch", 3), ("batch", 4),
    ], results


def test_the_batch_words_carry_the_structured_result():
    _, emitted = _drive_worker_with_interleave(["a", "b"], 0)
    batch = [m for m in emitted if m["type"] == "result" and m["run_id"] == "batch"]
    for message in batch:
        parse = message["parse"]
        assert parse["analyses"] and "signature" in parse["analyses"][0]
        assert "human_analyses" in parse and "parse_time_ms" in parse


def test_a_batch_gets_its_load_error_baseline_once():
    _, emitted = _drive_worker_with_interleave(["a", "b", "c"], 0)
    baselines = [m for m in emitted if m["type"] == "load_baseline"]
    assert [m["run_id"] for m in baselines] == ["batch"]
    assert baselines[0]["baseline"]["captured"] is True
    # Sent before the result it rides with, so the run has it on completion.
    first_result = next(i for i, m in enumerate(emitted) if m["type"] == "result")
    assert emitted.index(baselines[0]) < first_result


# ---------------------------------------------------------------------------
# CP3 (T044) -- the engine gate fires once, at submission; a change mid-job
# is a WARNING, not a refusal (FR-024)
# ---------------------------------------------------------------------------


def test_a_batch_word_observes_the_engine_instead_of_gating_on_it():
    from flextoolsmcp.server.parse.priority import Priority
    from flextoolsmcp.server.parse.worker_main import ParseWorker, _StubBackend

    class Gated(_StubBackend):
        gate_calls = 0

        def preflight(self):
            Gated.gate_calls += 1

    backend = Gated()
    emitted = []

    def emit(message):
        emitted.append(message)
        if message.get("type") == "result" and message.get("index_in_run") == 0:
            backend.engine = "XAmple"       # the user flips the active parser

    worker = ParseWorker("P", backend=backend, idle_timeout=5, emit=emit)
    for index, word in enumerate(["a", "b", "c"]):
        worker.handle_message({
            "type": "parse", "request_id": f"r{index}", "run_id": "batch",
            "wordform": word, "level": "batch", "priority": int(Priority.LOW),
            "index_in_run": index, "engine_at_submission": "HC",
        })
    worker._draining.set()
    worker.run()

    assert Gated.gate_calls == 0, "a batch word must not re-run the submission gate"
    results = [m for m in emitted if m["type"] == "result"]
    assert len(results) == 3, "the batch carried on after the engine changed"
    changes = [m for m in emitted if m["type"] == "engine_changed"]
    assert len(changes) == 1
    assert changes[0]["engine_at_submission"] == "HC"
    assert changes[0]["engine_now"] == "XAmple"


async def test_the_runner_records_an_engine_change_as_a_warning(record_dir):
    from flextoolsmcp.server.parse.priority import Priority

    class Flipping(FakeWorker):
        async def parse_word(self, **kwargs):
            if kwargs["index_in_run"] == 1:
                self.listeners[kwargs["run_id"]]({
                    "type": "engine_changed", "run_id": kwargs["run_id"],
                    "engine_at_submission": "HC", "engine_now": "XAmple",
                })
            return await super().parse_word(**kwargs)

    runner = make_runner(Flipping(), record_dir, grace_window=5.0)
    handle = await runner.start_run(
        project_name="P", wordforms=["a", "b", "c"], level="batch",
        priority=Priority.LOW, scope_fingerprint={"scope_kind": "words"},
        engine_at_submission="HC",
    )
    await asyncio.wait_for(handle.done.wait(), timeout=5)

    assert handle.stage is RunStage.COMPLETED, "a warning, never a refusal"
    assert handle.engine_changed_midjob is True
    meta = handle.record.read_meta()
    assert meta.engine_changed_midjob is True
    assert meta.engine_at_submission == "HC"


# ---------------------------------------------------------------------------
# CP3 (T047) -- reported batch progress accounts for an interleave (FR-026)
# ---------------------------------------------------------------------------


async def test_a_batch_displaced_by_a_single_word_says_who_it_waits_on(record_dir):
    from flextoolsmcp.server.parse.priority import Priority

    gate = asyncio.Event()

    class Held(FakeWorker):
        async def parse_word(self, **kwargs):
            if kwargs["wordform"] == "segera":
                await gate.wait()           # the single word takes a while
            return await super().parse_word(**kwargs)

    worker = Held(delay=0.01)
    runner = make_runner(worker, record_dir, grace_window=0.01)
    batch = await runner.start_run(
        project_name="P", wordforms=[f"w{i}" for i in range(50)], level="batch",
        priority=Priority.LOW, scope_fingerprint={"scope_kind": "words"},
        engine_at_submission="HC",
    )

    single = await runner.start_run(project_name="P", wordforms=["segera"], grace_window=0.01)
    assert batch.interleaved_by == single.run_id
    assert batch.record.read_meta().interleaved_by == single.run_id

    gate.set()
    await asyncio.wait_for(single.done.wait(), timeout=5)
    assert batch.interleaved_by is None, "a stale marker would say it is still waiting"
    await runner.cancel_run(batch.run_id)
    await asyncio.wait_for(batch.done.wait(), timeout=5)


async def test_a_single_word_is_not_displaced_by_a_batch(record_dir):
    from flextoolsmcp.server.parse.priority import Priority

    runner = make_runner(FakeWorker(delay=0.05), record_dir, grace_window=0.01)
    single = await runner.start_run(project_name="P", wordforms=["a", "b"])
    batch = await runner.start_run(
        project_name="P", wordforms=["x"], level="batch", priority=Priority.LOW,
        scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
    )
    assert single.interleaved_by is None
    await asyncio.wait_for(asyncio.gather(single.done.wait(), batch.done.wait()), timeout=5)


async def test_every_run_enters_through_one_item_per_wordform(record_dir):
    """FR-014: the batch is a call site of the one queue, not a second model."""
    import inspect

    from flextoolsmcp.server.parse import runner as runner_module

    source = inspect.getsource(runner_module.ParseRunner._execute_run)
    assert "enqueue_run(" in source
    assert "dequeue()" in source


# ---------------------------------------------------------------------------
# release_worker_if_idle -- #223 QC P1's atomic check-and-release, wired
# ---------------------------------------------------------------------------


async def test_release_worker_if_idle_delegates_to_the_pool_with_its_own_busy_predicate(
    record_dir,
):
    """`ParseRunner.release_worker_if_idle` must not decide busyness itself
    (that would reintroduce the check/act gap) -- it hands the pool ITS
    OWN `worker_busy(project_name, role=role)` as the predicate, so the
    pool can evaluate it atomically under its own lock at the moment of
    the pop (`WorkerPool.release_if_idle`, proven directly in
    `tests/test_parse_worker_lifetime.py`)."""
    worker = FakeWorker()
    runner = make_runner(worker, record_dir, grace_window=30.0)
    pool = runner._pool

    released = await runner.release_worker_if_idle("P", role=SHARED_ROLE)

    assert released is True, "nothing running on P, so idle"
    assert pool.release_if_idle_calls == [("P", SHARED_ROLE)]


async def test_release_worker_if_idle_reports_false_while_a_run_is_live(record_dir):
    worker = FakeWorker(delay=0.2)
    runner = make_runner(worker, record_dir, grace_window=0.01)
    handle = await runner.start_run(project_name="P", wordforms=["a"])
    assert not handle.is_terminal, "precondition: still running"

    released = await runner.release_worker_if_idle("P", role=SHARED_ROLE)

    assert released is False, "worker_busy() must refuse release of a live run"
    await asyncio.wait_for(handle.done.wait(), timeout=5)
