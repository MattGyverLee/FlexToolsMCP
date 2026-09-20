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
