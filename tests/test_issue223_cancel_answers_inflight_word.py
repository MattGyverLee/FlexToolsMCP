#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #223 scenario 6 (live regression): cancelling a run must not leave the
word already in flight -- the one `_parse_one` popped from `_pending_meta`
before discovering the cancellation -- with NO response at all.

`_drain_cancellations`'s own docstring states the protocol invariant this
file locks: "EVERY parse REQUEST GETS EXACTLY ONE RESPONSE." Before this
fix, a word that reached either of `_parse_one`'s two `is_cancelled` checks
was answered by NEITHER of this protocol's other two paths --
`ParseQueue.dequeue()` only discards a cancelled run's words BEFORE they
are handed to `_parse_one` (this word already was), and
`_answer_orphaned_requests` only finds requests still in `_pending_meta`
(this word's entry was already popped, at the very top of `_parse_one`,
before either check runs). The only thing that ran was `_report_cancelled`,
a RUN-scoped message with no `request_id` -- so on the server side, the
`asyncio.Future` keyed to THIS word's `request_id` was never resolved by
anything, and `ParseRunner._execute_run`'s `await worker.parse_word(...)`
for that exact word hung forever. Live evidence:
`specs/parser-check-cp2/evidence/issue223-live.md`
(`test_scenario_6_cancel_stops_at_a_boundary_and_keeps_what_finished`
timing out after 120s waiting on `handle.done.wait()`, reproduced twice).

Driven directly against `ParseWorker` + `_StubBackend`, like
`tests/test_issue223_idle_release.py` -- the thing under test is
`_parse_one`'s own bookkeeping, not the channel or a real project.

Run with:
    python -m pytest tests/test_issue223_cancel_answers_inflight_word.py -q
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.priority import Priority  # noqa: E402
from flextoolsmcp.server.parse.queue import QueuedWord  # noqa: E402
from flextoolsmcp.server.parse.worker_main import (  # noqa: E402
    ParseWorker,
    _StubBackend,
)


class _Collector:
    def __init__(self):
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)

    def of_type(self, kind):
        return [m for m in self.messages if m.get("type") == kind]


def _make_worker():
    backend = _StubBackend()
    collector = _Collector()
    worker = ParseWorker("Cancel223 Project", backend=backend, idle_timeout=600, emit=collector)
    return worker, collector


def _seed_pending_meta(worker, run_id, index, request_id):
    """What `_enqueue_parse` (driven by a real `parse` message) would have
    stored -- reproduced directly so the test can dequeue the word itself
    and control exactly when cancellation lands, rather than racing a real
    background reader thread (which is what makes this bug timing-
    dependent live and hard to hit deterministically through the public
    `handle_message`/`run()` surface)."""
    worker._pending_meta[(run_id, index)] = {
        "request_id": request_id,
        "level": "plain",
        "vernacular_ws": None,
        "engine_at_submission": None,
    }


def test_a_word_cancelled_before_any_work_still_gets_its_own_response():
    """The FIRST `is_cancelled` check inside `_parse_one` (before any work
    at all): the word was already dequeued when the run's cancellation
    landed. It must still resolve ITS OWN `request_id`, not just report the
    run-scoped `cancelled` message."""
    worker, collector = _make_worker()
    word = QueuedWord(
        run_id="run-a", wordform="kata", priority=Priority.TRY_A_WORD, index_in_run=0,
    )
    _seed_pending_meta(worker, "run-a", 0, "req-a-0")

    # The run is ALREADY cancelled by the time _parse_one looks -- the
    # narrow-window case (GIL switch between dequeue() and this check).
    worker._queue.cancel_run("run-a")

    worker._parse_one(word)

    errors = collector.of_type("error")
    assert any(
        m.get("request_id") == "req-a-0" and m.get("error_code") == "parse_job_cancelled"
        for m in errors
    ), (
        f"the in-flight word's own request_id was never answered: {collector.messages}"
    )
    # The run-level report still goes out too -- this fix adds an answer,
    # it does not replace the existing one.
    assert collector.of_type("cancelled"), "the run-scoped report must still fire"


def test_a_word_cancelled_mid_grammar_load_still_gets_its_own_response():
    """The SECOND `is_cancelled` check (after `_before_parse`) -- found
    live to be the one that actually fires under load: `_before_parse` is
    real wall-clock time (grammar load / preflight), during which a
    concurrent reader thread can process an incoming `cancel` for this run.
    Simulated here by having `_before_parse` itself request the
    cancellation, since this test has no real second thread to race.
    """
    worker, collector = _make_worker()
    word = QueuedWord(
        run_id="run-b", wordform="kata", priority=Priority.TRY_A_WORD, index_in_run=0,
    )
    _seed_pending_meta(worker, "run-b", 0, "req-b-0")
    assert not worker._queue.is_cancelled("run-b"), "precondition: not yet cancelled"

    real_before_parse = worker._before_parse

    def _before_parse_then_cancel(word, meta):
        result = real_before_parse(word, meta)
        worker._queue.cancel_run("run-b")
        return result

    worker._before_parse = _before_parse_then_cancel

    worker._parse_one(word)

    errors = collector.of_type("error")
    assert any(
        m.get("request_id") == "req-b-0" and m.get("error_code") == "parse_job_cancelled"
        for m in errors
    ), (
        f"the word cancelled mid-load was never answered: {collector.messages}"
    )
    assert not collector.of_type("result"), (
        "a word discovered cancelled after its load must not ALSO report a "
        "result -- exactly one response per request"
    )


def test_an_uncancelled_word_is_unaffected():
    """The ordinary path: no cancellation, one `result`, no `error`."""
    worker, collector = _make_worker()
    word = QueuedWord(
        run_id="run-c", wordform="kata", priority=Priority.TRY_A_WORD, index_in_run=0,
    )
    _seed_pending_meta(worker, "run-c", 0, "req-c-0")

    worker._parse_one(word)

    results = collector.of_type("result")
    assert len(results) == 1 and results[0]["request_id"] == "req-c-0"
    assert not collector.of_type("error")


def test_orphaned_requests_still_answered_the_same_way():
    """`_answer_orphaned_requests` (a word never dequeued at all) shares
    `_answer_word_cancelled` with `_parse_one` now -- same message shape,
    one implementation."""
    worker, collector = _make_worker()
    _seed_pending_meta(worker, "run-d", 0, "req-d-0")
    _seed_pending_meta(worker, "run-d", 1, "req-d-1")

    worker._answer_orphaned_requests("run-d")

    errors = {m["request_id"]: m for m in collector.of_type("error")}
    assert set(errors) == {"req-d-0", "req-d-1"}
    for message in errors.values():
        assert message["error_code"] == "parse_job_cancelled"
    assert worker._pending_meta == {}
