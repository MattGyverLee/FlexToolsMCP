#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The single parse queue (parser-check CP2b, FR-030; data-model.md section 3).

ONE queue, ordered by priority (lower value wins) and FIFO within a level,
holding work at **wordform granularity**.

WHY WORDFORM GRANULARITY IS THE WHOLE DESIGN. It would be simpler to queue
a batch as one item. Doing so makes FR-031 unimplementable: an urgent single
word must interleave at the running batch's *next word boundary*, without
the batch restarting, losing position, or reloading the grammar. If a batch
is one queue item, there is no boundary to interleave at -- the only choices
left are "wait for the whole batch" or "preempt and lose position", and the
requirement rules out both. Queuing each wordform separately makes the
boundary a natural consequence of the data structure rather than something
the worker has to synthesise.

THE ORDERING GUARANTEE IS THIS FEATURE'S OWN. The obvious precedent is
misleading and is called out here so nobody goes looking: the local
FieldWorks tree carries an uncommitted change that drains its queue into a
parallel batch and loses priority ordering within it. We do not use
`ParserScheduler`, it does not bind us, and its behaviour must never be
cited as rationale for a change here or copied. The semantics below are ours
and are pinned by tests/test_parse_priority_queue.py.

BUILT NOW FOR CP3. CP2b only ever enqueues at `TRY_A_WORD`. The queue
nonetheless accepts every level, because CP3's batch work will enqueue at
`MEDIUM` / `LOW` and FR-026 says there is exactly one run mechanism. A queue
that only understood single words would force CP3 to bring its own runner,
which is the outcome FR-026 exists to prevent.

This module is pure server-side: no pythonnet, no project, no FieldWorks.
It is deliberately testable without any of them.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from threading import Lock
from typing import Iterable, Iterator, Optional

from .priority import Priority

__all__ = ["QueuedWord", "ParseQueue"]


@dataclass(frozen=True)
class QueuedWord:
    """One wordform awaiting a parse.

    `run_id` is what ties the individual wordforms of a batch back together
    for progress reporting -- the queue itself has no concept of a batch,
    which is the point.
    """

    run_id: str
    wordform: str
    priority: Priority
    #: 0-based position within its own run, so a batch's progress can be
    #: reported without the queue having to model the batch.
    index_in_run: int = 0
    #: Set on the restricted level: the resolved MSA identifiers this parse
    #: is restricted to. `None` means an unrestricted parse. An EMPTY tuple
    #: is never valid here -- an empty resolution is a refusal, never a
    #: widening (FR-019), and `enqueue` rejects it rather than letting it
    #: reach the worker as "no restriction".
    restricted_to: Optional[tuple[int, ...]] = None


@dataclass(order=True)
class _Entry:
    """Heap entry. Ordering is (priority, sequence) -- the item never compares."""

    priority: int
    sequence: int
    word: QueuedWord = field(compare=False)
    cancelled: bool = field(default=False, compare=False)


class ParseQueue:
    """A priority queue of wordforms. Lower priority value wins; FIFO within.

    Thread-safe: the runner enqueues from the server's async handlers while
    the worker channel drains it, so every mutation is under one lock. The
    lock is deliberately coarse -- these operations are microseconds and
    contention is not the bottleneck; a loaded grammar is.
    """

    def __init__(self) -> None:
        self._heap: list[_Entry] = []
        self._lock = Lock()
        # Monotonic tiebreaker. This is what delivers FIFO *within* a level:
        # heapq is not stable, so without an explicit sequence two words at
        # the same priority would come out in an arbitrary order that tests
        # would then accidentally pin.
        self._counter = itertools.count()
        #: Run ids asked to cancel. Checked at dequeue rather than by
        #: scanning the heap, so cancelling is O(1) and does not have to
        #: reorder anything. Cooperative by design (FR-032): a word already
        #: handed to the worker is not clawed back -- the worker stops at
        #: the next boundary.
        self._cancelled_runs: set[str] = set()

    # -- writing ----------------------------------------------------------

    def enqueue(self, word: QueuedWord) -> None:
        """Add one wordform.

        Rejects an empty `restricted_to`. That tuple reaching the worker as
        "no restriction" is precisely the silent widening FR-019 forbids:
        the caller asked for a restricted trace, resolution produced
        nothing, and the correct answer is a refusal naming the piece -- not
        an unrestricted search that returns plausible-looking results the
        caller never asked for.
        """
        if word.restricted_to is not None and len(word.restricted_to) == 0:
            raise ValueError(
                f"QueuedWord for {word.wordform!r} carries an empty "
                f"restricted_to. An empty resolution is a REFUSAL, never a "
                f"widening to an unrestricted parse (FR-019). Refuse before "
                f"enqueueing, naming the piece that did not resolve."
            )
        with self._lock:
            heapq.heappush(
                self._heap,
                _Entry(int(word.priority), next(self._counter), word),
            )

    def enqueue_run(
        self,
        run_id: str,
        wordforms: Iterable[str],
        priority: Priority,
        restricted_to: Optional[tuple[int, ...]] = None,
    ) -> int:
        """Enqueue a run's wordforms as INDIVIDUAL items. Returns the count.

        This is the only way a multi-word run enters the queue, and it is a
        loop rather than a single composite item on purpose -- see the
        module docstring. A caller that wanted "one item per batch" would be
        removing the word boundaries FR-031 interleaves at.
        """
        count = 0
        for index, wordform in enumerate(wordforms):
            self.enqueue(
                QueuedWord(
                    run_id=run_id,
                    wordform=wordform,
                    priority=priority,
                    index_in_run=index,
                    restricted_to=restricted_to,
                )
            )
            count += 1
        return count

    # -- reading ----------------------------------------------------------

    def dequeue(self) -> Optional[QueuedWord]:
        """The next wordform to parse, or None when nothing is pending.

        Words belonging to a cancelled run are discarded here rather than
        returned. Cancellation is cooperative and observed at a word
        boundary (FR-032); this is that boundary for work not yet started.
        """
        with self._lock:
            while self._heap:
                entry = heapq.heappop(self._heap)
                if entry.word.run_id in self._cancelled_runs:
                    continue
                return entry.word
            return None

    def peek(self) -> Optional[QueuedWord]:
        """The next wordform without removing it. Skips cancelled runs."""
        with self._lock:
            for entry in sorted(self._heap):
                if entry.word.run_id not in self._cancelled_runs:
                    return entry.word
            return None

    def drain(self) -> Iterator[QueuedWord]:
        """Every pending wordform in service order. Mainly for tests.

        Deliberately NOT how the worker consumes the queue: draining
        eagerly would defeat the interleave, since a word enqueued at a
        higher priority mid-run could no longer overtake work already
        drained. The worker calls `dequeue()` one word at a time.
        """
        while True:
            word = self.dequeue()
            if word is None:
                return
            yield word

    # -- cancellation -----------------------------------------------------

    def cancel_run(self, run_id: str) -> int:
        """Mark a run cancelled. Returns how many of its words were pending.

        Does not touch a word already handed to the worker -- that one
        finishes, and the worker observes the cancellation at the next
        boundary. Partial results stay readable (FR-029, SC-008).
        """
        with self._lock:
            self._cancelled_runs.add(run_id)
            return sum(
                1 for entry in self._heap if entry.word.run_id == run_id
            )

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._cancelled_runs

    # -- introspection ----------------------------------------------------

    def pending_count(self, run_id: Optional[str] = None) -> int:
        """Pending words, optionally for one run. Excludes cancelled runs."""
        with self._lock:
            return sum(
                1
                for entry in self._heap
                if entry.word.run_id not in self._cancelled_runs
                and (run_id is None or entry.word.run_id == run_id)
            )

    def __len__(self) -> int:
        return self.pending_count()

    def __bool__(self) -> bool:
        return self.pending_count() > 0
