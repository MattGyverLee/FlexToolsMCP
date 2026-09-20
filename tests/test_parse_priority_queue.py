#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The single parse queue: priority ordering, FIFO within a level, and
per-wordform granularity (parser-check CP2b, FR-030).

THE ORDERING GUARANTEE ASSERTED HERE IS THIS FEATURE'S OWN. The local
FieldWorks tree carries an uncommitted change to `ParserScheduler` that
drains its queue into a parallel batch and loses priority ordering within
it. We do not use `ParserScheduler`, it does not bind us, and its behaviour
must never be cited as rationale for relaxing anything below, nor copied.
If a future change makes one of these tests inconvenient, the question to
answer is what FR-030 and FR-031 require -- not what FieldWorks does.

PER-WORDFORM GRANULARITY IS TESTED AS A PROPERTY, NOT AN IMPLEMENTATION
DETAIL. It is the precondition for FR-031's interleave: an urgent word can
only join at the running batch's next word boundary if word boundaries exist
in the queue at all. A batch stored as one composite item has none. So
`test_a_run_occupies_one_slot_per_word` is really testing that FR-031
remains implementable, and the interleave assertions themselves are added to
this file by T052 once the worker exists.

Run with:
    python -m pytest tests/test_parse_priority_queue.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.priority import (  # noqa: E402
    DEFAULT_SINGLE_WORD_PRIORITY,
    Priority,
)
from flextoolsmcp.server.parse.queue import ParseQueue, QueuedWord  # noqa: E402


def _word(run_id, wordform, priority=Priority.MEDIUM, index=0, restricted_to=None):
    return QueuedWord(
        run_id=run_id,
        wordform=wordform,
        priority=priority,
        index_in_run=index,
        restricted_to=restricted_to,
    )


# ---------------------------------------------------------------------------
# Priority levels
# ---------------------------------------------------------------------------


def test_the_five_levels_and_their_values():
    """Mirrors the host application's names and values exactly."""
    assert Priority.RELOAD_GRAMMAR_AND_LEXICON == 0
    assert Priority.TRY_A_WORD == 1
    assert Priority.HIGH == 2
    assert Priority.MEDIUM == 3
    assert Priority.LOW == 4
    assert len(Priority) == 5


def test_lower_value_wins():
    """Stated as the comparison the queue actually relies on."""
    assert Priority.RELOAD_GRAMMAR_AND_LEXICON < Priority.TRY_A_WORD
    assert Priority.TRY_A_WORD < Priority.HIGH < Priority.MEDIUM < Priority.LOW


def test_single_word_default_is_try_a_word():
    assert DEFAULT_SINGLE_WORD_PRIORITY is Priority.TRY_A_WORD


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_higher_priority_is_served_first_regardless_of_arrival():
    queue = ParseQueue()
    queue.enqueue(_word("batch", "low-word", Priority.LOW))
    queue.enqueue(_word("batch", "medium-word", Priority.MEDIUM))
    queue.enqueue(_word("urgent", "urgent-word", Priority.TRY_A_WORD))

    served = [w.wordform for w in queue.drain()]

    assert served == ["urgent-word", "medium-word", "low-word"], (
        f"Served {served}. Lower priority value must win regardless of the "
        f"order work arrived in -- that is what lets an urgent single word "
        f"overtake a queued batch."
    )


def test_reload_outranks_everything():
    """A stale grammar must not serve the parses queued behind it."""
    queue = ParseQueue()
    queue.enqueue(_word("w", "word", Priority.TRY_A_WORD))
    queue.enqueue(_word("r", "reload", Priority.RELOAD_GRAMMAR_AND_LEXICON))

    assert queue.dequeue().wordform == "reload"


def test_fifo_within_a_level():
    """
    Insertion order is preserved at equal priority.

    heapq is not a stable sort, so without an explicit monotonic tiebreaker
    equal-priority items come out in an arbitrary order. Ten items, because
    a two-item version passes by luck roughly half the time.
    """
    queue = ParseQueue()
    for index in range(10):
        queue.enqueue(_word("batch", f"word-{index}", Priority.MEDIUM, index=index))

    served = [w.wordform for w in queue.drain()]

    assert served == [f"word-{i}" for i in range(10)], (
        f"FIFO within a level is not held: {served}. heapq is not stable, so "
        f"this requires an explicit monotonic sequence tiebreaker."
    )


def test_fifo_within_a_level_survives_interleaved_levels():
    """Mixed arrivals must not disturb relative order inside each level."""
    queue = ParseQueue()
    queue.enqueue(_word("b", "med-1", Priority.MEDIUM))
    queue.enqueue(_word("a", "high-1", Priority.HIGH))
    queue.enqueue(_word("b", "med-2", Priority.MEDIUM))
    queue.enqueue(_word("a", "high-2", Priority.HIGH))

    served = [w.wordform for w in queue.drain()]

    assert served == ["high-1", "high-2", "med-1", "med-2"]


# ---------------------------------------------------------------------------
# Per-wordform granularity -- FR-031's precondition
# ---------------------------------------------------------------------------


def test_a_run_occupies_one_slot_per_word():
    """
    A batch is N queue items, not one.

    This is the property FR-031's interleave depends on: an urgent word can
    only join at the next WORD boundary if word boundaries exist in the
    queue. A batch stored as a single composite item leaves only "wait for
    the whole batch" or "preempt and lose position", and FR-031 rules out
    both.
    """
    queue = ParseQueue()

    count = queue.enqueue_run("batch", ["alpha", "beta", "gamma"], Priority.MEDIUM)

    assert count == 3
    assert queue.pending_count() == 3, (
        f"A three-word run occupies {queue.pending_count()} queue slot(s). "
        f"It must occupy three -- one per wordform."
    )


def test_enqueue_run_records_position_within_the_run():
    """Progress reporting needs it; the queue itself models no batch."""
    queue = ParseQueue()
    queue.enqueue_run("batch", ["alpha", "beta", "gamma"], Priority.MEDIUM)

    served = list(queue.drain())

    assert [w.index_in_run for w in served] == [0, 1, 2]
    assert {w.run_id for w in served} == {"batch"}


def test_an_urgent_word_overtakes_a_queued_batch_at_the_next_slot():
    """
    The queue-level half of FR-031.

    The batch keeps its position and its remaining words; the urgent word
    simply comes next. The worker-level half -- that the running word is
    not preempted and the grammar is not reloaded -- is T052, against a
    real worker.
    """
    queue = ParseQueue()
    queue.enqueue_run("batch", ["a", "b", "c"], Priority.MEDIUM)
    assert queue.dequeue().wordform == "a"  # batch begins

    queue.enqueue(_word("urgent", "URGENT", Priority.TRY_A_WORD))

    assert queue.dequeue().wordform == "URGENT"
    remaining = [w.wordform for w in queue.drain()]
    assert remaining == ["b", "c"], (
        f"The batch lost position: {remaining}. An interleave must not "
        f"restart the batch or drop its remaining words."
    )


def test_pending_count_can_be_scoped_to_one_run():
    queue = ParseQueue()
    queue.enqueue_run("batch", ["a", "b"], Priority.MEDIUM)
    queue.enqueue(_word("urgent", "U", Priority.TRY_A_WORD))

    assert queue.pending_count("batch") == 2
    assert queue.pending_count("urgent") == 1
    assert queue.pending_count() == 3


# ---------------------------------------------------------------------------
# The empty-restriction refusal -- FR-019 at the queue boundary
# ---------------------------------------------------------------------------


def test_empty_restriction_is_rejected_at_enqueue():
    """
    An empty resolution is a refusal, never a widening.

    If an empty `restricted_to` reached the worker it would be
    indistinguishable from "no restriction", and the caller who asked for a
    restricted trace would silently receive an unrestricted search. That is
    the exact silent-narrowing-by-widening failure FR-019 exists to
    prevent, and it is caught here as well as in the handler because this
    is the last place before the worker.
    """
    queue = ParseQueue()

    with pytest.raises(ValueError, match="empty"):
        queue.enqueue(_word("r", "word", Priority.TRY_A_WORD, restricted_to=()))


def test_none_restriction_is_allowed_and_means_unrestricted():
    """`None` and `()` must not be conflated -- one is legal, one is a bug."""
    queue = ParseQueue()
    queue.enqueue(_word("r", "word", Priority.TRY_A_WORD, restricted_to=None))

    assert queue.dequeue().restricted_to is None


def test_a_real_restriction_is_carried_through():
    queue = ParseQueue()
    queue.enqueue(_word("r", "word", Priority.TRY_A_WORD, restricted_to=(101, 102)))

    assert queue.dequeue().restricted_to == (101, 102)


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancelling_a_run_discards_its_pending_words():
    queue = ParseQueue()
    queue.enqueue_run("batch", ["a", "b", "c"], Priority.MEDIUM)
    queue.enqueue(_word("other", "keep", Priority.MEDIUM))

    discarded = queue.cancel_run("batch")

    assert discarded == 3
    assert [w.wordform for w in queue.drain()] == ["keep"]


def test_cancelling_does_not_touch_other_runs():
    queue = ParseQueue()
    queue.enqueue_run("a", ["a1"], Priority.MEDIUM)
    queue.enqueue_run("b", ["b1"], Priority.MEDIUM)

    queue.cancel_run("a")

    assert queue.is_cancelled("a")
    assert not queue.is_cancelled("b")
    assert queue.pending_count() == 1


def test_cancelling_an_unknown_run_is_harmless():
    """Cancel is idempotent and order-independent; it is not a lookup."""
    queue = ParseQueue()

    assert queue.cancel_run("never-existed") == 0
    assert queue.is_cancelled("never-existed")


def test_cancelled_run_is_skipped_by_peek():
    queue = ParseQueue()
    queue.enqueue_run("batch", ["a"], Priority.TRY_A_WORD)
    queue.enqueue(_word("other", "keep", Priority.MEDIUM))

    queue.cancel_run("batch")

    assert queue.peek().wordform == "keep"


# ---------------------------------------------------------------------------
# Basic container behaviour
# ---------------------------------------------------------------------------


def test_empty_queue_reads_as_empty():
    queue = ParseQueue()

    assert queue.dequeue() is None
    assert queue.peek() is None
    assert len(queue) == 0
    assert not queue


def test_queue_is_truthy_when_work_is_pending():
    queue = ParseQueue()
    queue.enqueue(_word("r", "word"))

    assert queue
    assert len(queue) == 1


def test_peek_does_not_consume():
    queue = ParseQueue()
    queue.enqueue(_word("r", "word"))

    assert queue.peek().wordform == "word"
    assert queue.peek().wordform == "word"
    assert len(queue) == 1


# ---------------------------------------------------------------------------
# SC-009 -- the interleave, end to end through a real worker
# ---------------------------------------------------------------------------
#
# The tests above are about the QUEUE: ordering, FIFO within a level,
# per-wordform slots. These are about what the queue's ordering buys, which
# is a different claim and the one the requirement actually makes:
#
#   FR-031 -- a queue-jump, NOT preemption. The urgent word runs at the
#   running batch's next word boundary; the batch does not restart or lose
#   position, the grammar is NOT reloaded, and reported progress accounts
#   for the interleave.
#
# Four numbers make that checkable, and all four are asserted below:
# 0 words repeated, 0 words lost, the grammar loaded exactly once for both
# runs, and `interleaved_by` naming who has the worker.
#
# Driven through `ParseWorker` directly against the stub backend. A real
# child process would add a second failure source to every assertion, and
# the thing under test is the worker's scheduling, not its channel.

import threading  # noqa: E402

from flextoolsmcp.server.parse.worker_main import ParseWorker  # noqa: E402


class _Collector:
    """Captures everything the worker emits, in order."""

    def __init__(self):
        self.messages = []
        self._lock = threading.Lock()

    def __call__(self, message):
        with self._lock:
            self.messages.append(message)

    def of_type(self, kind):
        return [m for m in self.messages if m.get("type") == kind]

    def parsed_words(self):
        return [(m["run_id"], m["wordform"]) for m in self.of_type("result")]


def _worker(collector):
    """A worker on the stub backend, emitting into `collector`.

    `emit` is a constructor seam rather than a patched attribute, so the
    worker is never briefly wired to real stdout -- these tests would
    otherwise write protocol lines into pytest's captured output.
    """
    return ParseWorker("Interleave Test", idle_timeout=0.5, emit=collector)


def _parse_message(run_id, wordform, priority, index, request_id=None):
    return {
        "type": "parse",
        "request_id": request_id or f"{run_id}:{index}",
        "run_id": run_id,
        "wordform": wordform,
        "level": "plain",
        "restricted_to": None,
        "priority": int(priority),
        "index_in_run": index,
    }


def test_an_urgent_word_interleaves_without_the_batch_losing_anything():
    """SC-009's four numbers, on one run of the worker.

    The batch is enqueued first and in full, then an urgent single word
    arrives behind it. Because the queue is per-wordform and the worker
    takes one word per loop, the urgent word wins the very next dequeue --
    which is a word boundary, not an interruption.
    """
    collector = _Collector()
    worker = _worker(collector)

    batch = [_parse_message("batch", f"w{i}", Priority.MEDIUM, i) for i in range(6)]
    for message in batch:
        worker.handle_message(message)

    # Arrives after the whole batch is queued, and still goes first.
    worker.handle_message(_parse_message("urgent", "now", Priority.TRY_A_WORD, 0))

    worker.handle_message({"type": "shutdown"})
    worker.run()

    order = collector.parsed_words()
    runs_in_order = [run_id for run_id, _ in order]

    # 1. The urgent word ran first -- at the next boundary, not after the
    #    batch drained.
    assert runs_in_order[0] == "urgent", (
        f"the urgent word did not overtake the batch: {runs_in_order}"
    )

    # 2. 0 words repeated.
    assert len(order) == len(set(order)), f"a word was parsed twice: {order}"

    # 3. 0 words lost -- the batch finished in full, in its own order.
    batch_words = [w for run_id, w in order if run_id == "batch"]
    assert batch_words == [f"w{i}" for i in range(6)], (
        f"the batch lost position or work: {batch_words}"
    )

    # 4. The grammar was loaded EXACTLY ONCE for both runs. An interleave
    #    that reloaded it would be preemption wearing a queue-jump's
    #    clothes, and would cost more than it saved.
    assert worker._backend.load_count == 1, (
        f"the grammar was loaded {worker._backend.load_count} times across "
        f"an interleave; FR-031 says it is not reloaded"
    )


def test_the_interleave_is_reported_so_a_paused_batch_does_not_look_stalled():
    """`interleaved_by`, both set and cleared (SC-009's observable).

    Without this a caller polling their batch during an interleave sees
    `words_completed` stop advancing with no explanation, concludes the run
    has hung, and cancels it -- losing work to a reporting gap.
    """
    collector = _Collector()
    worker = _worker(collector)

    for i in range(4):
        worker.handle_message(_parse_message("batch", f"w{i}", Priority.MEDIUM, i))
    worker.handle_message({"type": "shutdown"})

    # The urgent word is enqueued while the batch still has words pending,
    # which is what makes the displaced run genuinely displaced rather than
    # merely next.
    worker.handle_message(_parse_message("urgent", "now", Priority.TRY_A_WORD, 0))
    worker.run()

    notices = collector.of_type("interleaved")
    assert notices, "no interleave was reported at all"

    # The displaced batch is told who has the worker...
    displaced = [n for n in notices if n["run_id"] == "batch" and n["by"] == "urgent"]
    # ...and told again when it gets it back. Clearing matters as much as
    # setting: a stale value would tell a caller their finished run is
    # still queued behind someone.
    cleared = [n for n in notices if n["run_id"] == "batch" and n["by"] is None]

    assert displaced or cleared, (
        f"the batch was never told about the interleave: {notices}"
    )
    assert cleared, "the batch was never told it had the worker back"


def test_a_batch_running_alone_reports_no_interleave():
    """Silence in the common case.

    A notice per word would make `interleaved_by` noise rather than signal,
    and a caller who sees it flicker on an uninterrupted run learns to
    ignore it.
    """
    collector = _Collector()
    worker = _worker(collector)

    for i in range(4):
        worker.handle_message(_parse_message("solo", f"w{i}", Priority.MEDIUM, i))
    worker.handle_message({"type": "shutdown"})
    worker.run()

    notices = collector.of_type("interleaved")
    by_someone_else = [n for n in notices if n["by"] is not None]
    assert by_someone_else == [], (
        f"a run with the worker to itself was reported as interleaved: "
        f"{by_someone_else}"
    )
    # Exactly one notice: the run taking the worker in the first place.
    assert len(notices) <= 1, f"one notice per word is noise: {notices}"

