#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parse worker process lifetime (parser-check CP2b; research.md R-02;
data-model.md section 8).

WHY THIS FILE IS SCHEDULED RATHER THAN LEFT TO REVIEW. Issue #57 exists
because a pythonnet grandchild can outlive its parent while holding a
`.fwdata` lock. Until CP2b every project-touching child was one-shot, so
that window was the length of one call. The parse worker is **long-lived**
by design (FR-042 needs a held grammar, FR-031 needs a word boundary to
interleave at), which makes the same failure mode last for the whole
session. A lock held until the machine is rebooted is a worse outcome than
any parser defect in this checkpoint, so the three ways the worker is
supposed to go away each get a test:

  1. **idle release** -- it lets go by itself when nobody is using it;
  2. **graceful shutdown** -- it lets go when asked;
  3. **the kill** -- it is taken away when it will not let go.

(3) is the one that actually protects the lock, because (1) and (2) both
require a worker healthy enough to cooperate, and a worker wedged inside a
grammar load is neither.

Unlike `tests/test_parse_runner.py`, these tests spawn **real child
processes**. That is the point: a fake cannot be orphaned and cannot fail
to die, so a fake would assert nothing here. They run in `--stub` mode, so
no project is opened and no parser is constructed -- the lifetime is real,
the parsing is not.

Run with:
    python -m pytest tests/test_parse_worker_lifetime.py -q
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse import worker_client as wc  # noqa: E402
from flextoolsmcp.server.parse.worker_client import (  # noqa: E402
    ParseWorkerClient,
    WorkerPool,
)
from flextoolsmcp.server.subprocess_helpers import (  # noqa: E402
    _kill_process_tree,
    spawn_module_async,
)


async def _await_exit(proc, timeout=30):
    await asyncio.wait_for(proc.wait(), timeout=timeout)
    return proc.returncode


@pytest.fixture
async def client():
    """A started stub worker, reaped no matter how the test ends."""
    c = ParseWorkerClient("Lifetime Test Project", stub=True)
    await c.start()
    try:
        yield c
    finally:
        await c.aclose()


# ---------------------------------------------------------------------------
# 1. Idle release
# ---------------------------------------------------------------------------


async def test_the_worker_releases_the_project_on_idle_timeout():
    """It lets go by itself, with stdin still open and nobody asking.

    stdin is deliberately held open: closing it is a *different* exit path
    (the server hung up), and testing that one instead would leave the idle
    timeout -- the only mechanism that protects a lock the server has simply
    forgotten about -- unasserted.
    """
    proc = await spawn_module_async(
        wc.WORKER_MODULE_PATH,
        ["--project", "Idle Project", "--stub", "--idle-timeout", "1"],
        env=wc._child_env(),
    )
    try:
        ready = json.loads(await asyncio.wait_for(proc.stdout.readline(), timeout=60))
        assert ready["type"] == "ready"

        messages = []
        while True:
            raw = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
            if not raw:
                break
            messages.append(json.loads(raw))
            if messages[-1]["type"] == "bye":
                break

        assert messages[-1] == {"type": "bye", "reason": "idle"}, (
            f"expected an idle release, got {messages[-1]!r}"
        )
        assert await _await_exit(proc) == 0
    finally:
        if proc.returncode is None:
            _kill_process_tree(proc.pid)


async def test_the_worker_exits_when_the_server_hangs_up():
    """stdin closing is its own exit path: nothing more can arrive."""
    proc = await spawn_module_async(
        wc.WORKER_MODULE_PATH,
        ["--project", "EOF Project", "--stub", "--idle-timeout", "600"],
        env=wc._child_env(),
    )
    try:
        ready = json.loads(await asyncio.wait_for(proc.stdout.readline(), timeout=60))
        assert ready["type"] == "ready"

        proc.stdin.close()

        # Must not wait out the 600s idle timeout.
        assert await _await_exit(proc, timeout=60) == 0
    finally:
        if proc.returncode is None:
            _kill_process_tree(proc.pid)


# ---------------------------------------------------------------------------
# 2. Graceful shutdown
# ---------------------------------------------------------------------------


async def test_aclose_ends_the_worker_process(client):
    assert client.is_running()
    pid = client.pid

    await client.aclose()

    assert not client.is_running()
    assert pid is not None


async def test_aclose_is_idempotent(client):
    await client.aclose()
    await client.aclose()
    assert not client.is_running()


async def test_shutdown_does_not_discard_accepted_work():
    """A `shutdown` drains; it does not drop words already accepted.

    Dropping them would silently lose work the server was told had been
    accepted, and a silently lost word is the failure shape this whole
    checkpoint exists to prevent. Abandoning work is `cancel`'s job, and
    that is explicit (FR-032).
    """
    proc = await spawn_module_async(
        wc.WORKER_MODULE_PATH,
        ["--project", "Drain Project", "--stub", "--idle-timeout", "600"],
        env=wc._child_env(),
    )
    try:
        ready = json.loads(await asyncio.wait_for(proc.stdout.readline(), timeout=60))
        assert ready["type"] == "ready"

        words = [f"w{i}" for i in range(12)]
        for index, word in enumerate(words):
            proc.stdin.write(
                (
                    json.dumps(
                        {
                            "type": "parse",
                            "request_id": f"r{index}",
                            "run_id": "R",
                            "wordform": word,
                            "level": "plain",
                            "priority": 1,
                            "index_in_run": index,
                        }
                    )
                    + "\n"
                ).encode()
            )
        proc.stdin.write((json.dumps({"type": "shutdown"}) + "\n").encode())
        await proc.stdin.drain()

        parsed = []
        while True:
            raw = await asyncio.wait_for(proc.stdout.readline(), timeout=60)
            if not raw:
                break
            message = json.loads(raw)
            if message["type"] == "result":
                parsed.append(message["wordform"])
            if message["type"] == "bye":
                break

        assert parsed == words, (
            f"shutdown lost accepted work: parsed {len(parsed)} of {len(words)}"
        )
        assert await _await_exit(proc) == 0
    finally:
        if proc.returncode is None:
            _kill_process_tree(proc.pid)


# ---------------------------------------------------------------------------
# 3. The kill -- the orphan case
# ---------------------------------------------------------------------------


async def test_kill_process_tree_reaps_a_worker_that_will_not_cooperate():
    """The path that actually protects the `.fwdata` lock (issue #57).

    A worker wedged inside a grammar load answers neither `shutdown` nor
    its own idle timer. Simulated here by never asking it to stop and
    killing it outright, which is what `aclose` falls back to.
    """
    proc = await spawn_module_async(
        wc.WORKER_MODULE_PATH,
        ["--project", "Orphan Project", "--stub", "--idle-timeout", "3600"],
        env=wc._child_env(),
    )
    ready = json.loads(await asyncio.wait_for(proc.stdout.readline(), timeout=60))
    assert ready["type"] == "ready"
    assert proc.returncode is None, "precondition: the worker is alive"

    _kill_process_tree(proc.pid)

    await asyncio.wait_for(proc.wait(), timeout=30)
    assert proc.returncode is not None, "the worker survived a tree kill"


async def test_aclose_kills_a_worker_that_ignores_shutdown(monkeypatch):
    """`aclose` does not trust the polite request it just made.

    The graceful window is shortened rather than the worker sabotaged, so
    the assertion is about `aclose`'s own fallback rather than about a
    contrived child.
    """
    monkeypatch.setattr(wc, "_GRACEFUL_SHUTDOWN_SECONDS", 0.001)

    c = ParseWorkerClient("Stubborn Project", stub=True)
    await c.start()
    assert c.is_running()

    await c.aclose()
    assert not c.is_running()


# ---------------------------------------------------------------------------
# The pool -- one worker per project, and reaping all of them
# ---------------------------------------------------------------------------


async def test_pool_gives_one_worker_per_project():
    pool = WorkerPool(stub=True)
    try:
        first = await pool.get("Project A")
        again = await pool.get("Project A")
        other = await pool.get("Project B")

        assert first is again, "one worker per project, not one per call"
        assert other is not first
        assert sorted(pool.active_projects()) == ["Project A", "Project B"]
    finally:
        await pool.aclose()


async def test_releasing_a_project_ends_its_worker():
    """FR-042: the held grammar is released on project switch.

    Implemented as the plainest possible thing -- the process that held it
    ends -- so "released" is observable rather than asserted.
    """
    pool = WorkerPool(stub=True)
    try:
        worker = await pool.get("Project A")
        assert worker.is_running()

        await pool.release("Project A")

        assert not worker.is_running()
        assert pool.active_projects() == []
    finally:
        await pool.aclose()


async def test_pool_replaces_a_worker_that_died_on_its_own():
    """An idle-released worker is ordinary, not an error.

    The project was let go because nobody was using it; the next caller
    gets a fresh worker rather than a corpse.
    """
    pool = WorkerPool(stub=True)
    try:
        worker = await pool.get("Short Lived")
        # Its own idle timeout is long, so end it the way the OS would.
        _kill_process_tree(worker.pid)
        await asyncio.wait_for(worker._proc.wait(), timeout=30)
        assert not worker.is_running()

        replacement = await pool.get("Short Lived")
        assert replacement is not worker
        assert replacement.is_running()
    finally:
        await pool.aclose()


async def test_pool_aclose_reaps_every_worker():
    pool = WorkerPool(stub=True)
    workers = [await pool.get(f"Project {n}") for n in range(3)]
    assert all(w.is_running() for w in workers)

    await pool.aclose()

    assert pool.active_projects() == []
    for worker in workers:
        assert not worker.is_running(), "a worker survived pool teardown"


# ---------------------------------------------------------------------------
# The channel itself
# ---------------------------------------------------------------------------


async def test_every_request_gets_exactly_one_response(client):
    """The protocol invariant a cancelled run is most likely to break.

    The server awaits one word at a time, so an unanswered request is not a
    missing log line -- it is a permanently hung `await` and a tool call
    that never returns.
    """
    results = await asyncio.gather(
        *[
            client.parse_word(
                request_id=f"q{i}", run_id="R", wordform=f"w{i}", index_in_run=i
            )
            for i in range(8)
        ]
    )
    assert sorted(r["wordform"] for r in results) == sorted(f"w{i}" for i in range(8))


async def test_an_urgent_word_overtakes_a_queued_batch():
    """FR-031's ordering, over the real channel.

    The batch is submitted first and at the lowest priority; the urgent
    word is submitted last and must still overtake what is still queued.

    The stub is given a per-word delay on purpose. With an instant parse
    the batch is already drained before the urgent word is even written to
    the pipe, and the test would then be asserting nothing -- it would pass
    against a worker with no priority ordering at all.
    """
    client = ParseWorkerClient("Interleave Project", stub=True, parse_delay=0.05)
    await client.start()
    try:
        await _assert_urgent_overtakes(client)
    finally:
        await client.aclose()


async def _assert_urgent_overtakes(client):
    seen: list = []

    async def submit(request_id, run_id, word, priority, index=0):
        result = await client.parse_word(
            request_id=request_id,
            run_id=run_id,
            wordform=word,
            priority=priority,
            index_in_run=index,
        )
        seen.append(result["wordform"])
        return result

    batch = [
        asyncio.create_task(submit(f"b{i}", "batch", f"low{i}", 4, i))
        for i in range(10)
    ]
    # Long enough that the batch is genuinely under way, short enough that
    # most of it is still queued when the urgent word lands.
    await asyncio.sleep(0.12)
    urgent = asyncio.create_task(submit("u", "urgent", "URGENT", 1))

    await asyncio.gather(urgent, *batch)

    assert "URGENT" in seen
    assert seen.index("URGENT") < seen.index("low9"), (
        f"the urgent word did not overtake the batch: {seen}"
    )
    # It must jump the queue, not preempt: nothing is repeated and nothing
    # is lost (FR-031 -- a queue-jump, not a restart).
    assert len(seen) == len(set(seen)) == 11, f"words repeated or lost: {seen}"


async def test_a_dead_worker_fails_waiting_callers_rather_than_hanging(client):
    """A worker that dies mid-flight must not leave callers awaiting forever.

    One never-resolved future per outstanding word is one tool call that
    never returns, which is strictly worse than a loud failure.
    """
    # Enough words that plenty are still queued when the worker dies. A
    # single word is not enough: the stub answers it before the kill lands,
    # and the test would then assert nothing.
    pending = [
        asyncio.create_task(
            client.parse_word(
                request_id=f"orphan{i}", run_id="R", wordform=f"w{i}", index_in_run=i
            )
        )
        for i in range(400)
    ]
    await asyncio.sleep(0.05)
    _kill_process_tree(client.pid)

    # The assertion is as much about `wait_for` NOT timing out as about the
    # exception type: a hang is the defect, and a hang here fails as a
    # timeout rather than as a wrong answer.
    outcomes = await asyncio.wait_for(
        asyncio.gather(*pending, return_exceptions=True), timeout=30
    )
    failed = [o for o in outcomes if isinstance(o, BaseException)]
    assert failed, "killing the worker left every caller waiting on a dead process"
    assert all(isinstance(o, wc.WorkerError) for o in failed), (
        f"unexpected failure types: {sorted({type(o).__name__ for o in failed})}"
    )


async def test_stub_worker_opens_no_project_and_constructs_no_parser(client):
    """The stub is an honest stand-in: real lifetime, no FieldWorks.

    Asserted so a future edit cannot quietly make these lifetime tests
    depend on a live project, which would turn a fast suite into one that
    only runs on a FieldWorks machine.
    """
    result = await client.parse_word(request_id="q", run_id="R", wordform="uji")
    assert result["parse"]["stub"] is True
