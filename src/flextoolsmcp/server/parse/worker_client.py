#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The server side of the parse-worker channel (parser-check CP2b;
research.md R-02; data-model.md section 8).

This module runs **in the MCP server process**. Its opposite number,
`worker_main.py`, runs in the child and is never imported here -- only
named, as a dotted module path handed to `subprocess_helpers`. That is the
whole point of the split: the server keeps the queue, the run records and
the tool handlers; the child keeps the project, the LCM cache and the held
grammar (R-02).

WHAT THIS MODULE OWNS:

  * spawning one worker **per project**, through the existing
    `subprocess_helpers.spawn_module_async` -- the long-lived sibling of
    `run_script_async`, not a second execution mechanism;
  * the line-delimited JSON conversation with that child;
  * routing each response back to whoever is waiting for it;
  * **teardown**, via the existing `_kill_process_tree` path.

WHY TEARDOWN IS THE PART TO GET RIGHT. Issue #57 exists because a pythonnet
grandchild can outlive its parent holding a `.fwdata` lock, and a one-shot
child made that a per-call window. A long-lived worker makes it a
whole-session window, so a graceful `shutdown` request is **not** the
teardown story -- it is the polite first half of it. `aclose()` asks, waits
briefly, and then kills the tree regardless. A worker that ignores the
request, is wedged inside a grammar load, or has already lost its stdin
still gets reaped. Anything less and a stuck worker keeps a project locked
until the machine is rebooted.

WHY ONE WORKER PER PROJECT AND NOT PER RUN. An interleaving urgent word and
the batch it interrupts are two *runs* that must share one loaded grammar
(FR-031, SC-009). A worker per run would load the grammar twice and could
not interleave at all. A worker per project is the smallest unit that can
hold the single grammar slot FR-042 describes.

WHY RESPONSES ARE ROUTED RATHER THAN AWAITED IN ORDER. The worker answers
out of order **by design**: an urgent word overtakes a queued batch, so its
`result` arrives before results for words submitted earlier. A client that
assumed request/response pairing in submission order would mis-attribute
every interleaved result. So each `parse` carries a `request_id`, and the
reader task resolves the matching future; `stage` and `cancelled` messages,
which belong to a run rather than to a request, go to a per-run listener
instead.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
from typing import Any, Callable, Optional

from ..subprocess_helpers import _kill_process_tree, spawn_module_async

__all__ = [
    "WORKER_MODULE_PATH",
    "WorkerError",
    "WorkerStartupError",
    "ParseWorkerClient",
    "WorkerPool",
]

_log = logging.getLogger(__name__)

#: The child, addressed by dotted path and NEVER imported. `run_scan_module`
#: addresses `scan/grammar_scan_module.py` the same way.
WORKER_MODULE_PATH = "flextoolsmcp.server.parse.worker_main"

#: How long to wait for the worker's `ready` handshake before giving up.
#: Generous: the child pays a full interpreter start plus a pythonnet import.
_STARTUP_TIMEOUT_SECONDS = 60.0

#: How long a polite `shutdown` gets before the tree is killed anyway.
_GRACEFUL_SHUTDOWN_SECONDS = 5.0


def _child_env() -> dict:
    """The child's environment, with this process's import path carried over.

    The worker is launched as `python -m flextoolsmcp.server.parse.worker_main`,
    so the child must be able to import `flextoolsmcp` by itself. When the
    package is installed that is automatic; when it is being run from a
    source checkout without an install -- which is how the test suite runs,
    since `tests/conftest.py` adds `src/` to `sys.path` at runtime -- the
    child inherits no such path and fails with an import error that says
    nothing about the real cause.

    Propagating `sys.path` through PYTHONPATH makes the child resolve the
    package exactly the way its parent did. Existing PYTHONPATH entries are
    kept and come first, so a deliberate override still wins.
    """
    env = dict(os.environ)
    # The child's stdio must be UTF-8 regardless of the console codepage.
    # On Windows it would otherwise default to cp1252 and silently replace
    # any character outside it -- in a tool about minority-language
    # orthographies that is data corruption, not a display quirk. The
    # worker also reconfigures its own streams; this covers anything that
    # reads the encoding before that runs.
    env["PYTHONIOENCODING"] = "utf-8"
    entries = [p for p in sys.path if p and os.path.isdir(p)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        entries = existing.split(os.pathsep) + entries
    seen: set = set()
    ordered = [e for e in entries if not (e in seen or seen.add(e))]
    env["PYTHONPATH"] = os.pathsep.join(ordered)
    return env


class WorkerError(RuntimeError):
    """The worker failed in a way the server could not route to a caller."""


class WorkerStartupError(WorkerError):
    """The worker never produced a usable `ready` handshake."""


class ParseWorkerClient:
    """One worker process, one project.

    Not reused across projects: FR-042 releases the held grammar on project
    switch, and the simplest honest way to do that is for the process that
    holds it to end. `WorkerPool` enforces the one-per-project rule.
    """

    def __init__(
        self, project_name: str, *, stub: bool = False, parse_delay: float = 0.0
    ) -> None:
        self.project_name = project_name
        self._stub = stub
        #: Stub-only, and only meaningful to tests that need a word boundary
        #: to still exist when a second message arrives. Ignored by the real
        #: backend, which takes its timing from the parser.
        self._parse_delay = parse_delay
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        #: request_id -> future awaiting that word's `result` / `error`.
        self._pending: dict[str, asyncio.Future] = {}
        #: run_id -> callback for messages that belong to a run rather than
        #: to one request (`stage`, `cancelled`).
        self._run_listeners: dict[str, Callable[[dict[str, Any]], None]] = {}
        #: Futures awaiting an `assemblies` answer. A plain list rather than
        #: an id-keyed dict because the message carries no request id: it is
        #: a diagnostic about the process, not about a request, and every
        #: waiter wants the same answer.
        self._assembly_waiters: list[asyncio.Future] = []
        self._protocol: Optional[int] = None
        self._closed = False
        self._write_lock = asyncio.Lock()

    # -- lifecycle --------------------------------------------------------

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        """Spawn the worker and wait for its `ready` line.

        Waiting for the handshake rather than returning optimistically is
        deliberate: a worker that dies on startup (missing project, wrong
        engine, pythonnet failure) must surface as a failure *here*, where
        there is a caller to tell. Discovered later, it would surface as a
        word that mysteriously never came back.
        """
        args = ["--project", self.project_name]
        if self._stub:
            args.append("--stub")
            if self._parse_delay:
                args += ["--parse-delay", str(self._parse_delay)]

        self._proc = await spawn_module_async(
            WORKER_MODULE_PATH, args, env=_child_env()
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        try:
            ready = await asyncio.wait_for(
                self._read_message(), timeout=_STARTUP_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError as exc:
            await self.aclose()
            raise WorkerStartupError(
                f"Parse worker for {self.project_name!r} produced no ready "
                f"handshake within {_STARTUP_TIMEOUT_SECONDS}s."
            ) from exc

        if ready is None or ready.get("type") != "ready":
            await self.aclose()
            raise WorkerStartupError(
                f"Parse worker for {self.project_name!r} did not start: "
                f"{(ready or {}).get('message') or ready!r}"
            )

        self._protocol = ready.get("protocol")
        self._reader_task = asyncio.create_task(self._read_loop())

    async def aclose(self) -> None:
        """Ask the worker to stop, then make sure it did.

        The kill is unconditional rather than a fallback for an error path.
        A worker wedged inside a grammar load will not answer a `shutdown`,
        and it is holding a `.fwdata` lock while it does not -- so the tree
        goes regardless of how politely it was asked (issue #57).
        """
        if self._closed:
            return
        self._closed = True

        proc, self._proc = self._proc, None
        if proc is None:
            return

        with contextlib.suppress(Exception):
            if proc.returncode is None and proc.stdin is not None:
                proc.stdin.write((json.dumps({"type": "shutdown"}) + "\n").encode())
                await proc.stdin.drain()
                proc.stdin.close()

        with contextlib.suppress(asyncio.TimeoutError, Exception):
            await asyncio.wait_for(proc.wait(), timeout=_GRACEFUL_SHUTDOWN_SECONDS)

        if proc.returncode is None:
            _log.warning(
                "Parse worker for %r did not exit within %ss; killing its "
                "process tree (issue #57).",
                self.project_name,
                _GRACEFUL_SHUTDOWN_SECONDS,
            )
            _kill_process_tree(proc.pid)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=5)

        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

        self._fail_pending(
            WorkerError(f"Parse worker for {self.project_name!r} was shut down.")
        )

    # -- the channel ------------------------------------------------------

    async def _read_message(self) -> Optional[dict[str, Any]]:
        """One protocol line, or None at EOF. Malformed lines are skipped.

        An oversize line -- `asyncio.LimitOverrunError`, a `ValueError`
        subclass, raised by `readline()` when a line exceeds the stream's
        `limit` (see `subprocess_helpers._STREAM_LIMIT_BYTES`) -- is also
        handled here rather than left to kill the read loop. Confirmed
        live (cycle 5 verification, `Claude-Swahili`'s `mtu` at
        `level='explain'`) before that ceiling was raised, and still
        reachable after: any trace bigger even than the raised ceiling
        hits the same path.

        NO MANUAL BYTE-DRAINING IS DONE, and this is deliberate rather
        than an oversight. CPython's own `StreamReader.readline()`
        already discards the line that overflowed *before* raising (see
        `asyncio/streams.py`): either the offending line plus its
        separator is removed, or -- when the separator has not even
        arrived yet, which is this bug's actual shape -- the whole
        buffer is cleared. Either way the NEXT `readline()` call resumes
        cleanly from real data; a probe reproducing the exact "Separator
        is not found" message confirmed this empirically (a still-too-
        long remainder can raise once or twice more before the tail
        finally fits, then normal lines resume). Retrying is therefore
        sufficient to resynchronize the byte stream.

        What retrying CANNOT do is recover the lost message's meaning:
        the request_id was inside the JSON this discarded, so there is no
        way to know which pending request's answer just vanished -- and
        with several words in flight (a batch, an interleaved urgent
        word) it is not necessarily only one. Guessing would risk
        resolving the wrong future with the wrong result, which is a
        silent protocol violation, not a fix. So every request pending
        AT THIS MOMENT is failed loudly instead (`_fail_pending`) and the
        loop continues: the specific word(s) affected get a clear error,
        every OTHER already-answered word is unaffected, and -- unlike
        the previous behaviour of ending the read loop entirely -- the
        channel keeps working for every request submitted afterward.
        """
        proc = self._proc
        if proc is None or proc.stdout is None:
            return None
        while True:
            try:
                raw = await proc.stdout.readline()
            except ValueError as exc:
                _log.warning(
                    "Parse worker for %r sent a line too large for the "
                    "channel; failing %d pending request(s) and "
                    "resynchronizing: %s",
                    self.project_name,
                    len(self._pending),
                    exc,
                )
                self._fail_pending(
                    WorkerError(
                        f"Parse worker for {self.project_name!r} sent a "
                        f"response too large for the channel; that "
                        f"request's result was lost, but the worker is "
                        f"still running."
                    )
                )
                continue
            if not raw:
                return None
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                # Not fatal. stdout is protocol-only by contract, but a
                # library in the child printing one stray line must not take
                # down a worker holding a loaded grammar.
                _log.warning("Parse worker emitted a non-JSON line: %r", text[:200])
                continue
            if isinstance(message, dict):
                return message
            _log.warning("Parse worker emitted a non-object message: %r", text[:200])

    async def _read_loop(self) -> None:
        """Route every response until the worker's stdout closes."""
        try:
            while True:
                message = await self._read_message()
                if message is None:
                    break
                self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _log.warning("Parse worker read loop failed: %s", exc)
        finally:
            self._fail_pending(
                WorkerError(
                    f"Parse worker for {self.project_name!r} closed its "
                    f"channel before answering."
                )
            )

    def _dispatch(self, message: dict[str, Any]) -> None:
        kind = message.get("type")

        if kind in ("result", "resolved", "error"):
            request_id = message.get("request_id")
            future = self._pending.pop(request_id, None) if request_id else None
            if future is not None and not future.done():
                if kind == "error":
                    future.set_exception(_error_from(message))
                else:
                    future.set_result(message)
                return
            # An `error` with no request_id is a worker-level failure (a
            # failed startup, an unroutable message). It has no caller to
            # raise in, so it is logged rather than dropped silently.
            if kind == "error":
                _log.warning(
                    "Parse worker error with no matching request: %s",
                    message.get("message"),
                )
            return

        if kind in ("stage", "cancelled", "interleaved"):
            listener = self._run_listeners.get(message.get("run_id") or "")
            if listener is not None:
                try:
                    listener(message)
                except Exception as exc:  # noqa: BLE001
                    _log.warning("Run listener failed: %s", exc)
            return

        if kind == "assemblies":
            waiters, self._assembly_waiters = self._assembly_waiters, []
            for future in waiters:
                if not future.done():
                    future.set_result(list(message.get("names") or []))
            return

        if kind in ("pong", "ready", "bye"):
            return

        _log.warning("Unknown worker message type %r", kind)

    def _fail_pending(self, exc: Exception) -> None:
        """Resolve every waiting caller rather than leaving them hanging.

        A worker that dies mid-batch would otherwise leave one future per
        outstanding word never resolved, and each of those is a tool call
        that never returns. Failing them loudly is strictly better than a
        caller waiting forever on a process that no longer exists.
        """
        pending, self._pending = self._pending, {}
        for future in pending.values():
            if not future.done():
                future.set_exception(exc)
        waiters, self._assembly_waiters = self._assembly_waiters, []
        for future in waiters:
            if not future.done():
                future.set_exception(exc)

    async def _send(self, message: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None:
            raise WorkerError(
                f"Parse worker for {self.project_name!r} is not running."
            )
        # ensure_ascii=True to match `_emit` on the worker side: the wire
        # stays pure ASCII, so no stdio layer on either side can mangle a
        # non-Latin wordform on its way to the parser.
        line = (json.dumps(message, ensure_ascii=True) + "\n").encode("utf-8")
        async with self._write_lock:
            proc.stdin.write(line)
            await proc.stdin.drain()

    # -- requests ---------------------------------------------------------

    def listen_to_run(
        self, run_id: str, listener: Callable[[dict[str, Any]], None]
    ) -> None:
        """Receive this run's `stage` and `cancelled` messages."""
        self._run_listeners[run_id] = listener

    def stop_listening(self, run_id: str) -> None:
        self._run_listeners.pop(run_id, None)

    async def parse_word(
        self,
        *,
        request_id: str,
        run_id: str,
        wordform: str,
        level: str = "plain",
        restricted_to: Optional[tuple] = None,
        priority: int = 1,
        index_in_run: int = 0,
    ) -> dict[str, Any]:
        """Submit one word and await its result.

        `restricted_to` is passed through untouched, including the
        difference between `None` (unrestricted) and an empty sequence
        (which the worker refuses). Normalising the two here would be
        precisely the silent widening FR-019 forbids -- see spec.md Delta 2.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        try:
            await self._send(
                {
                    "type": "parse",
                    "request_id": request_id,
                    "run_id": run_id,
                    "wordform": wordform,
                    "level": level,
                    "restricted_to": (
                        list(restricted_to) if restricted_to is not None else None
                    ),
                    "priority": int(priority),
                    "index_in_run": int(index_in_run),
                }
            )
        except Exception:
            self._pending.pop(request_id, None)
            raise

        return await future

    async def cancel_run(self, run_id: str) -> None:
        """Ask the worker to stop a run at its next word boundary.

        Returns as soon as the request is sent. It does **not** wait for the
        run to stop, because cancellation is cooperative: the worker
        finishes the word in flight first (FR-032). The `cancelled` message
        arrives on the run listener when that boundary is reached.
        """
        await self._send({"type": "cancel", "run_id": run_id})

    async def resolve_morphs(
        self,
        *,
        request_id: str,
        run_id: str,
        morphs: list,
        only_if_indexed: bool = False,
        timeout: float = 120.0,
    ) -> dict:
        """Resolve a decomposition against the project's lexicon.

        NOT A PARSE. The worker answers this from its lexicon index without
        touching the parser area, which is what makes FR-019's "an
        unresolvable piece runs no parse" achievable rather than merely
        asserted -- the refusal happens before anything is enqueued.

        The generous timeout is for the first call on a large project: the
        index is built once, and building it walks every entry. Later calls
        answer from memory.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        try:
            await self._send(
                {
                    "type": "resolve",
                    "request_id": request_id,
                    "run_id": run_id,
                    "morphs": morphs,
                    "only_if_indexed": bool(only_if_indexed),
                }
            )
        except Exception:
            self._pending.pop(request_id, None)
            raise

        return await asyncio.wait_for(future, timeout=timeout)

    async def loaded_assemblies(self, *, timeout: float = 30.0) -> list:
        """The worker's OWN loaded CLR assemblies, by simple name.

        A diagnostic, off the parse path entirely. Its one caller is
        `HCParser_DoesNotLoadXCore`, which backs the `READ_ONLY_SAFE`
        annotation: the assertion has to be made against the process that
        parsed, and this process is not it.

        Answered on the worker's reader thread, so it does not queue behind
        a word being parsed -- which matters, because the test asks right
        after a parse and a queued answer would time out behind the next.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._assembly_waiters.append(future)
        try:
            await self._send({"type": "assemblies"})
            return await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            with contextlib.suppress(ValueError):
                self._assembly_waiters.remove(future)
            raise

    async def ping(self) -> bool:
        """Liveness check. False rather than raising if the worker is gone."""
        try:
            await self._send({"type": "ping"})
            return True
        except WorkerError:
            return False

    async def _drain_stderr(self) -> None:
        """Forward the worker's diagnostics into the server's log.

        Drained rather than ignored for two reasons: an undrained stderr
        pipe eventually fills and blocks the child, and the worker's
        tracebacks are the only diagnostic available for a failure that
        happens between protocol messages.
        """
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        try:
            while True:
                raw = await proc.stderr.readline()
                if not raw:
                    return
                _log.debug(
                    "[parse-worker %s] %s",
                    self.project_name,
                    raw.decode("utf-8", errors="replace").rstrip(),
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            return


def _error_from(message: dict[str, Any]) -> Exception:
    """Rebuild a worker-side failure as a server-side exception.

    A `detail` dict is carried through **unchanged** and attached as
    `.detail`, because the worker already shapes it exactly like the
    matching `response_models` detail model. Rewriting it here is where the
    field names would quietly drift apart (R-03).
    """
    exc = WorkerError(message.get("message") or "Parse worker error.")
    detail = message.get("detail")
    if isinstance(detail, dict):
        exc.detail = detail  # type: ignore[attr-defined]
    error_code = message.get("error_code")
    if error_code:
        exc.error_code = error_code  # type: ignore[attr-defined]
    return exc


class WorkerPool:
    """One worker per project, and the teardown that reaps all of them.

    The pool exists so that "one worker per project" is a property of the
    system rather than a convention each call site is trusted to follow,
    and so server shutdown has a single place to reap from. FR-042's
    release-on-project-switch is implemented here as the plainest possible
    thing: switching projects ends the process that held the old grammar.
    """

    def __init__(self, *, stub: bool = False, parse_delay: float = 0.0) -> None:
        self._workers: dict[str, ParseWorkerClient] = {}
        self._lock = asyncio.Lock()
        self._stub = stub
        self._parse_delay = parse_delay

    async def get(self, project_name: str) -> ParseWorkerClient:
        """The worker for this project, started if necessary.

        A worker found dead is replaced rather than returned. The common
        cause is its own idle timeout, which is ordinary and not an error:
        the project was released because nobody was using it.
        """
        async with self._lock:
            existing = self._workers.get(project_name)
            if existing is not None:
                if existing.is_running():
                    return existing
                self._workers.pop(project_name, None)
                await existing.aclose()

            worker = ParseWorkerClient(
                project_name, stub=self._stub, parse_delay=self._parse_delay
            )
            await worker.start()
            self._workers[project_name] = worker
            return worker

    def peek(self, project_name: str) -> Optional[ParseWorkerClient]:
        """The worker for this project if one exists, without starting one.

        For callers that only want to tidy up after themselves -- dropping
        a run listener, say. Starting a worker as a side effect of cleanup
        would open a project nobody asked for.
        """
        return self._workers.get(project_name)

    async def release(self, project_name: str) -> None:
        """End the worker for one project, dropping its held grammar."""
        async with self._lock:
            worker = self._workers.pop(project_name, None)
        if worker is not None:
            await worker.aclose()

    async def aclose(self) -> None:
        """Reap every worker. Called on server shutdown.

        Each is closed independently so one wedged worker cannot stop the
        others being reaped -- the failure mode that would leave a lock held
        is exactly the one that would also refuse to shut down politely.
        """
        async with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            with contextlib.suppress(Exception):
                await worker.aclose()

    def active_projects(self) -> list[str]:
        return [name for name, w in self._workers.items() if w.is_running()]
