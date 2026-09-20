#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse run priority levels (parser-check CP2b, FR-030; data-model.md
section 3).

Five levels, mirroring the host application's own names and values so a
linguist reading FieldWorks documentation and a maintainer reading this file
are talking about the same thing. **Lower value wins.** Within a level the
queue is FIFO, and work is enqueued per wordform rather than per batch --
that granularity is what lets an urgent single word interleave at the next
word boundary without the running batch restarting (FR-031).

THE ORDERING GUARANTEE IS THIS FEATURE'S OWN, and that needs saying
explicitly because the obvious place to look for precedent is misleading.
The local FieldWorks tree carries an uncommitted change that drains its
queue into a parallel batch and loses priority ordering within it. We do not
use `ParserScheduler`, it does not bind us, and its behaviour must never be
cited as rationale for a change here or copied into this module. The names
and numbers below are borrowed; the semantics are ours and are pinned by
tests/test_parse_priority_queue.py.

WHY FIVE LEVELS WHEN CP2b ONLY ENQUEUES AT ONE. A single-word
`flextools_try_word` enqueues at `TRY_A_WORD`, and that is the only level
this checkpoint produces. `MEDIUM` and `LOW` exist now because CP3's batch
work will enqueue at them, and FR-026 says there is exactly one run
mechanism -- no second, simpler execution path. Declaring the levels a
checkpoint early costs nothing and is what stops CP3 from arriving with its
own runner because ours "only did single words".

`RELOAD_GRAMMAR_AND_LEXICON` sits above everything at 0 for the same reason
it does in the host application: once the grammar is known stale, every
parse queued behind it would otherwise be answered from a grammar that is
about to be discarded.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["Priority", "DEFAULT_SINGLE_WORD_PRIORITY"]


class Priority(IntEnum):
    """Run priority. Lower value wins; FIFO within a level.

    `IntEnum` rather than `Enum` because the queue orders on the value
    directly and "lower wins" should be expressible as `<` rather than
    through a lookup table that could disagree with the names.
    """

    RELOAD_GRAMMAR_AND_LEXICON = 0
    TRY_A_WORD = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


#: What `flextools_try_word` enqueues at. Named rather than written as a
#: literal at the call site so that the single-word path's priority is
#: greppable, and so CP3 adding batch levels does not have to guess which
#: bare `Priority.TRY_A_WORD` in the tree meant "the single-word default".
DEFAULT_SINGLE_WORD_PRIORITY: Priority = Priority.TRY_A_WORD
