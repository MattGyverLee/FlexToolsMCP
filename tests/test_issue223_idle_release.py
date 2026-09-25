#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #223 (scope change): the parse worker must not hold
`<project>.fwdata.lock` while it sits idle between requests, only while a
parse is actually running.

Before this change `ParseWorker` opened the project once at startup and
held it -- and the lock -- until the worker PROCESS exited, up to
`DEFAULT_IDLE_TIMEOUT_SECONDS` (600s) after the last word. `run_module`'s
write gate (see `tests/test_issue223_own_worker_release.py`, committed as
the safety net in 1181a33) worked around the resulting collision but did
not close the underlying gap: a write landing in that up-to-600s idle
window still had to detect and release the worker itself.

This file is the fix at the source: `ParseWorker._release_if_idle` drops
the project the instant the queue goes empty (`run()`'s main loop), and
`ParseWorker._ensure_project_open` reopens it on demand before the next
request touches the backend. The PROCESS still lives out `idle_timeout`
(so a later request in the same window reuses the warm interpreter), but
the project -- and the lock -- does not.

Driven through `ParseWorker` directly against `_StubBackend`, like
`tests/test_parse_priority_queue.py` and `tests/test_parse_runner.py`: the
thing under test is the worker's open/close bookkeeping, not its channel or
a real FieldWorks project.

Run with:
    python -m pytest tests/test_issue223_idle_release.py -q
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.priority import Priority  # noqa: E402
from flextoolsmcp.server.parse.worker_main import (  # noqa: E402
    ParseWorker,
    _StubBackend,
)


def _parse_message(run_id, wordform, priority, index, **extra):
    message = {
        "type": "parse",
        "request_id": f"{run_id}:{index}",
        "run_id": run_id,
        "wordform": wordform,
        "level": "plain",
        "restricted_to": None,
        "priority": int(priority),
        "index_in_run": index,
    }
    message.update(extra)
    return message


class _Collector:
    def __init__(self):
        self.messages = []

    def __call__(self, message):
        self.messages.append(message)

    def of_type(self, kind):
        return [m for m in self.messages if m.get("type") == kind]

    def parsed_words(self):
        return [(m["run_id"], m["wordform"]) for m in self.of_type("result")]


# ---------------------------------------------------------------------------
# The lock drops as soon as the queue is idle -- not at process exit
# ---------------------------------------------------------------------------


def test_the_project_is_released_the_moment_the_queue_goes_idle():
    """A single request, then shutdown: the project is closed by the time
    `run()` returns, well inside the (generous) idle_timeout."""
    backend = _StubBackend()
    collector = _Collector()
    worker = ParseWorker("Idle223 Project", backend=backend, idle_timeout=600, emit=collector)

    worker.handle_message(_parse_message("first", "kata", Priority.TRY_A_WORD, 0))
    worker.handle_message({"type": "run_end", "run_id": "first"})
    worker.handle_message({"type": "shutdown"})
    worker.run()

    assert collector.parsed_words() == [("first", "kata")]
    assert backend.is_open() is False
    assert backend.release_count == 1
    # Nothing reopened it -- a straight run to shutdown, exactly like #223's
    # pre-fix behaviour otherwise would have, minus the lock.
    assert backend.open_count == 0


def test_holding_the_lock_while_a_parse_runs_is_unaffected():
    """The scope change is explicit that this half is fine and unchanged:
    a whole batch, queued up front and drained without the queue ever
    going empty mid-batch, must not release between words."""
    backend = _StubBackend()
    collector = _Collector()
    worker = ParseWorker("Idle223 Batch", backend=backend, idle_timeout=600, emit=collector)

    for index in range(6):
        worker.handle_message(
            _parse_message("batch", f"w{index}", Priority.MEDIUM, index,
                            level="batch", engine_at_submission="HC")
        )
    worker.handle_message({"type": "run_end", "run_id": "batch"})
    worker.handle_message({"type": "shutdown"})
    worker.run()

    assert len(collector.parsed_words()) == 6
    # Released exactly once -- after the whole batch drained, not between
    # any two of its words.
    assert backend.release_count == 1
    assert backend.load_count == 1, "one grammar load for the whole batch"


# ---------------------------------------------------------------------------
# A follow-up request still works: the worker reopens on demand
# ---------------------------------------------------------------------------


def test_a_follow_up_request_after_idle_release_still_works():
    """The scope change's other half: dropping the lock must not strand a
    later request in the same idle window. Hooks `_release_if_idle` (the
    one place idle-release happens) to inject a second request exactly
    once release has been proven to have happened -- not merely "soon
    after" -- and a third round to let the loop reach shutdown."""
    backend = _StubBackend()
    collector = _Collector()
    worker = ParseWorker("Idle223 Followup", backend=backend, idle_timeout=600, emit=collector)

    worker.handle_message(_parse_message("first", "kata", Priority.TRY_A_WORD, 0))

    calls = {"n": 0}
    original = worker._release_if_idle

    def hook():
        calls["n"] += 1
        if calls["n"] == 1:
            # #235: the first run is still open on the wire, so no release
            # yet even though the queue is empty.
            assert backend.is_open() is True
            worker.handle_message({"type": "run_end", "run_id": "first"})
        original()
        if calls["n"] == 1:
            assert backend.is_open() is False
            assert backend.release_count == 1
            worker.handle_message(_parse_message("second", "lagi", Priority.TRY_A_WORD, 0))
        elif calls["n"] == 2:
            worker.handle_message({"type": "run_end", "run_id": "second"})
            original()
            worker.handle_message({"type": "shutdown"})

    worker._release_if_idle = hook
    worker.run()

    assert collector.parsed_words() == [("first", "kata"), ("second", "lagi")]
    # Reopened exactly once, for "second"; released again after it, too.
    assert backend.open_count == 1
    assert backend.release_count == 2
    # The stub's grammar "reloads" (in the sense ensure_grammar reports a
    # load) once per open, mirroring `ParserOperations._CurrentHandle`
    # rebuilding against a fresh LcmCache after every real reopen.
    assert backend.load_count == 2


def test_a_follow_up_resolve_request_also_reopens():
    """`_drain_resolves` is a second call site for `_ensure_project_open` --
    covered separately since it is not reached by `_parse_one`'s path."""
    backend = _StubBackend()
    collector = _Collector()
    worker = ParseWorker("Idle223 Resolve", backend=backend, idle_timeout=600, emit=collector)

    worker.handle_message(_parse_message("first", "kata", Priority.TRY_A_WORD, 0))

    calls = {"n": 0}
    original = worker._release_if_idle

    def hook():
        calls["n"] += 1
        if calls["n"] == 1:
            assert backend.is_open() is True
            worker.handle_message({"type": "run_end", "run_id": "first"})
        original()
        if calls["n"] == 1:
            assert backend.is_open() is False
            worker.handle_message({
                "type": "resolve", "request_id": "r1", "run_id": "first",
                "morphs": [], "only_if_indexed": True,
            })
        elif calls["n"] == 2:
            worker.handle_message({"type": "shutdown"})

    worker._release_if_idle = hook
    worker.run()

    assert backend.open_count == 1
    resolved = collector.of_type("resolved")
    assert len(resolved) == 1, "the resolve was answered, not dropped or errored"


# ---------------------------------------------------------------------------
# Reopening invalidates state scoped to the closed cache
# ---------------------------------------------------------------------------


def test_ensure_project_open_is_a_no_op_when_already_open():
    backend = _StubBackend()
    worker = ParseWorker("P", backend=backend, idle_timeout=600, emit=lambda m: None)
    worker._index = "sentinel-index"
    worker._load_baseline = {"captured": True}

    worker._ensure_project_open()

    assert backend.open_count == 0, "already open -- nothing to reopen"
    assert worker._index == "sentinel-index", "not touched when nothing reopened"
    assert worker._load_baseline == {"captured": True}


def test_reopen_drops_the_hvo_scoped_index_and_the_load_baseline():
    """Issue #103: an HVO is a session-scoped handle liblcm renumbers on
    every cache load. `self._index` holds entry/MSA HVOs
    (`_backend.lexicon_rows()`), so it must not survive a reopen -- it is
    rebuilt fresh (`_drain_resolves`) against the new cache's HVOs instead."""
    backend = _StubBackend()
    worker = ParseWorker("P", backend=backend, idle_timeout=600, emit=lambda m: None)
    worker._index = "sentinel-index-from-the-old-cache"
    worker._load_baseline = {"captured": True, "source": "the old grammar load"}
    backend.release()
    assert backend.is_open() is False

    worker._ensure_project_open()

    assert backend.is_open() is True
    assert backend.open_count == 1
    assert worker._index is None, "must rebuild against the new cache's HVOs"
    assert worker._load_baseline is None, "described a load that no longer exists"


def test_release_if_idle_is_a_no_op_when_already_closed():
    backend = _StubBackend()
    backend.release()
    assert backend.release_count == 1
    worker = ParseWorker("P", backend=backend, idle_timeout=600, emit=lambda m: None)

    worker._release_if_idle()

    assert backend.release_count == 1, "no second release() call when already closed"
