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
    "MEASUREMENT_ROLE",
    "SHARED_ROLE",
    "WORKER_MODULE_PATH",
    "WorkerError",
    "WorkerStartupError",
    "ParseWorkerClient",
    "WorkerPool",
    "register_role",
]

_log = logging.getLogger(__name__)

#: The child, addressed by dotted path and NEVER imported. `run_scan_module`
#: addresses `scan/grammar_scan_module.py` the same way.
WORKER_MODULE_PATH = "flextoolsmcp.server.parse.worker_main"

#: The pool's two keys per project (FR-051, R-05). Every run lands in the
#: SHARED worker -- one grammar, interleaving at word boundaries -- except the
#: bounded single-word measurement, which gets a worker of its own because
#: its bound is enforced by killing that worker's process tree, and a shared
#: worker would take any running batch down with it.
SHARED_ROLE = "shared"
MEASUREMENT_ROLE = "measurement"

#: Roles registered by OTHER packages: role -> (child module, client class).
#: The read spine names no role but its own two. CP4's filing package
#: registers its FILING worker here at import (`server/filing/client.py`), so
#: the module that opens a project for writing is addressed from the filing
#: package and never from this one (R-09, FR-029). Roles not registered run
#: the read worker.
_ROLE_CLIENTS: dict[str, tuple[str, type]] = {}


def register_role(role: str, module_path: str, client_class: Optional[type] = None) -> None:
    """Map a pool role to the child module (and client class) it runs."""
    _ROLE_CLIENTS[role] = (module_path, client_class or ParseWorkerClient)

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
        self,
        project_name: str,
        *,
        stub: bool = False,
        parse_delay: float = 0.0,
        module_path: str = WORKER_MODULE_PATH,
    ) -> None:
        self.project_name = project_name
        #: The child module this client spawns. The read worker by default;
        #: another package's worker for a role it registered (CP4, R-09).
        self._module_path = module_path
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
        self._worker_pid: Optional[int] = None
        self._closed = False
        self._write_lock = asyncio.Lock()

    # -- lifecycle --------------------------------------------------------

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None

    @property
    def worker_pid(self) -> Optional[int]:
        """The worker's OWN process id, as it reported it in `ready`.

        This is the id a project lock names. `pid` is the process the server
        spawned, which on Windows may be a launcher whose child is the worker.
        """
        return self._worker_pid

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
            self._module_path, args, env=_child_env()
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
        reported = ready.get("pid")
        self._worker_pid = reported if isinstance(reported, int) else self.pid
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

    async def terminate(self) -> None:
        """Kill the process tree NOW -- no polite `shutdown` first.

        The bounded measurement's enforcement (FR-052, D-4). `aclose` asks
        and then waits, which is right for teardown and wrong for a bound: a
        worker inside a parse is not reading its stdin, so the polite half
        would only add its own timeout to the bound being enforced. There is
        no in-parse alternative -- the engine takes no cancellation token,
        timeout or step budget, and a cooperative cancel lands at the next
        word boundary, which for a one-word parse is after the parse.
        """
        if self._closed:
            return
        self._closed = True
        proc, self._proc = self._proc, None
        if proc is not None and proc.returncode is None:
            _kill_process_tree(proc.pid)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), timeout=5)
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        self._fail_pending(
            WorkerError(f"Parse worker for {self.project_name!r} was terminated.")
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

        if kind in (
            "result", "resolved", "error", "engine", "scope_resolved", "parser_parameters",
            # CP4: the read worker's three read-only filing-preflight answers
            # (the agent probe, the gate's inputs, the preview's facts).
            "agent", "filing_gate", "filing_preview",
        ):
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

        if kind in ("stage", "cancelled", "interleaved", "engine_changed", "load_baseline"):
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
        vernacular_ws: Optional[str] = None,
        engine_at_submission: Optional[str] = None,
    ) -> dict[str, Any]:
        """Submit one word and await its result.

        `restricted_to` is passed through untouched, including the
        difference between `None` (unrestricted) and an empty sequence
        (which the worker refuses). Normalising the two here would be
        precisely the silent widening FR-019 forbids -- see spec.md Delta 2.

        `engine_at_submission` is set only for a batch word, whose engine
        gate already ran once at submission (FR-024). The two CP3 keys are
        sent only when set, so a CP2b request is byte-for-byte unchanged.
        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        message: dict[str, Any] = {
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
        if vernacular_ws is not None:
            message["vernacular_ws"] = vernacular_ws
        if engine_at_submission is not None:
            message["engine_at_submission"] = engine_at_submission

        try:
            await self._send(message)
        except Exception:
            self._pending.pop(request_id, None)
            raise

        return await future

    async def _request(self, message: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Send one request that carries a `request_id` and await its answer."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        request_id = message["request_id"]
        self._pending[request_id] = future
        try:
            await self._send(message)
        except Exception:
            self._pending.pop(request_id, None)
            raise
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    async def check_engine(self, *, request_id: str, timeout: float = 60.0) -> str:
        """Run the engine gate and return the engine that passed (FR-024).

        A mismatch arrives as a `WorkerError` carrying the
        `parser_engine_mismatch` detail unchanged, exactly as it does for a
        single word.
        """
        answer = await self._request(
            {"type": "engine_check", "request_id": request_id}, timeout
        )
        return str(answer.get("engine") or "")

    async def parser_parameters(
        self, *, request_id: str, timeout: float = 60.0
    ) -> Optional[dict[str, Any]]:
        """The project's stored parser parameters, READ (FR-055).

        Context for a slow parse, never a lever: nothing on this path writes
        them, because that would be a project-data write and CP3 has none.
        None when the worker could not read them.
        """
        answer = await self._request(
            {"type": "parser_parameters", "request_id": request_id}, timeout
        )
        parameters = answer.get("parameters")
        return dict(parameters) if isinstance(parameters, dict) else None

    async def resolve_scope(
        self, *, request_id: str, scope: dict[str, Any], timeout: float = 300.0
    ) -> dict[str, Any]:
        """Resolve a scope in the worker, where the project is open (US1).

        Generous timeout: an all-texts scope on a large project reads every
        text's unique wordforms. No parse runs.
        """
        answer = await self._request(
            {"type": "resolve_scope", "request_id": request_id, "scope": scope}, timeout
        )
        resolved = dict(answer.get("resolved") or {})
        # The one project-state probe rides with the resolution (FR-004); the
        # handler pops it before validating the resolved scope.
        resolved["project_state"] = answer.get("project_state")
        return resolved

    # -- CP4: the filing preflight, answered by the READ worker (read-only) --

    async def probe_agent(self, *, request_id: str, timeout: float = 60.0) -> dict[str, Any]:
        """The HermitCrab agent probe (CP4 FR-025), run in the read worker.

        Asked only by the filing handler's preflight, never on a try-a-word
        or batch path: the read spine itself still resolves no agent (CP2b
        FR-016). The worker answers it from `server/filing/preflight_reads.py`;
        a missing agent comes back as `state: "absent"` with the
        `parser_agent_missing` fields, never as an unhandled lookup failure.
        """
        answer = await self._request({"type": "agent_probe", "request_id": request_id}, timeout)
        return dict(answer.get("agent") or {})

    async def filing_gate(
        self,
        *,
        request_id: str,
        probe_word: Optional[str] = None,
        vernacular_ws: Optional[str] = None,
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        """The refuse-to-file gate's inputs, read in the read worker (FR-020..FR-023, FR-039).

        A current grammar (loaded now if it was stale or never loaded), THIS
        load's errors, whether the parser could be built (a probe parse of
        `probe_word`), and the eligible-entry set. Read-only: the gate's
        verdict is computed server-side (`filing/gate.py`). Generous timeout:
        it may pay for a grammar load.
        """
        message: dict[str, Any] = {"type": "filing_gate", "request_id": request_id}
        if probe_word is not None:
            message["probe_word"] = probe_word
        if vernacular_ws is not None:
            message["vernacular_ws"] = vernacular_ws
        answer = await self._request(message, timeout)
        return {k: answer.get(k) for k in ("morpher_null", "load", "eligible")}

    async def filing_preview(
        self,
        *,
        request_id: str,
        words: list,
        vernacular_ws: Optional[str] = None,
        timeout: float = 600.0,
    ) -> dict[str, Any]:
        """The stored-analysis facts the deletion projection is built from.

        Per word: every stored analysis's GUID, its human opinion, whether the
        parser has evaluated it, and whether any text segment references it --
        through a FRESH segment join, never the worker-lifetime cache (R-02).
        Opens nothing for writing.
        """
        message: dict[str, Any] = {
            "type": "filing_preview", "request_id": request_id, "words": list(words),
        }
        if vernacular_ws is not None:
            message["vernacular_ws"] = vernacular_ws
        answer = await self._request(message, timeout)
        return {"words": dict(answer.get("words") or {}),
                "join_known": bool(answer.get("join_known"))}

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
    """One shared worker per project, and the teardown that reaps all of them.

    The pool exists so that "one worker per project" is a property of the
    system rather than a convention each call site is trusted to follow,
    and so server shutdown has a single place to reap from. FR-042's
    release-on-project-switch is implemented here as the plainest possible
    thing: switching projects ends the process that held the old grammar.

    TWO KEYS PER PROJECT (CP3, FR-051, R-05). Workers are keyed by
    `(project, role)`. Every run uses `SHARED_ROLE`; the bounded measurement
    alone uses `MEASUREMENT_ROLE`, so killing it at its bound cannot take a
    batch on the same project with it. The measurement worker is terminated
    or released as soon as its one word is done -- it never becomes a second
    long-lived grammar holder.
    """

    def __init__(self, *, stub: bool = False, parse_delay: float = 0.0) -> None:
        self._workers: dict[tuple[str, str], ParseWorkerClient] = {}
        self._lock = asyncio.Lock()
        self._stub = stub
        self._parse_delay = parse_delay

    async def get(
        self, project_name: str, *, role: str = SHARED_ROLE
    ) -> ParseWorkerClient:
        """The worker for this project and role, started if necessary.

        A worker found dead is replaced rather than returned. The common
        cause is its own idle timeout, which is ordinary and not an error:
        the project was released because nobody was using it.
        """
        key = (project_name, role)
        async with self._lock:
            existing = self._workers.get(key)
            if existing is not None:
                if existing.is_running():
                    return existing
                self._workers.pop(key, None)
                await existing.aclose()

            module_path, client_class = _ROLE_CLIENTS.get(
                role, (WORKER_MODULE_PATH, ParseWorkerClient)
            )
            worker = client_class(
                project_name,
                stub=self._stub,
                parse_delay=self._parse_delay,
                module_path=module_path,
            )
            await worker.start()
            self._workers[key] = worker
            return worker

    def workers_for(self, project_name: str) -> dict[str, ParseWorkerClient]:
        """Every RUNNING worker for this project, keyed by role.

        For own-worker lock detection (#223): the shared read worker is not
        the only role that can hold the project's lock -- the bounded
        measurement worker (MEASUREMENT_ROLE) can too, briefly -- so a write
        gate needs every role, not just `peek`'s single SHARED_ROLE default.
        """
        return {
            role: worker
            for (name, role), worker in self._workers.items()
            if name == project_name and worker.is_running()
        }

    def peek(
        self, project_name: str, *, role: str = SHARED_ROLE
    ) -> Optional[ParseWorkerClient]:
        """The worker for this project if one exists, without starting one.

        For callers that only want to tidy up after themselves -- dropping
        a run listener, say. Starting a worker as a side effect of cleanup
        would open a project nobody asked for.
        """
        return self._workers.get((project_name, role))

    async def release(self, project_name: str, *, role: Optional[str] = None) -> None:
        """End this project's worker(s), dropping the held grammar.

        With no `role`, every worker for the project goes -- a project switch
        releases the project, not one of its keys.
        """
        async with self._lock:
            keys = [
                key for key in self._workers
                if key[0] == project_name and (role is None or key[1] == role)
            ]
            workers = [self._workers.pop(key) for key in keys]
        for worker in workers:
            await worker.aclose()

    async def release_if_idle(
        self,
        project_name: str,
        *,
        role: str,
        is_busy: Callable[[], bool],
    ) -> bool:
        """Check-and-release, atomically, under the SAME lock `get()` uses
        (#223 QC P1).

        The write gates (`handlers/execution.py`'s
        `_release_own_worker_or_refuse`, `handlers/parse.py`'s
        `handle_flextools_parse_release`) used to call `ParseRunner.worker_busy()`
        and this pool's `release()` as two separate steps, with a real
        `await` (worker teardown, `aclose()`) between them. A run that
        registers itself in `ParseRunner._runs` and then calls `get()` for
        this SAME `(project_name, role)` in that gap would find its worker
        torn out from under it mid-parse, because nothing re-checked
        busyness at the moment of the actual pop.

        `is_busy` is called from inside the lock, synchronously (it must
        not itself `await` -- `ParseRunner.worker_busy` is a plain
        generator expression over its own `_runs` dict, so it never does).
        `ParseRunner.start_run` registers a new run's handle in `_runs`
        *before* anything in it ever awaits (record.py's `RunRecord.create`
        is synchronous, and the handle is registered before the run's task
        is even created) and strictly before that run's own task calls
        `get()` for this same key -- so a caller re-checking `is_busy()`
        under this lock, right before the pop, cannot observe a worker as
        idle and then have a concurrent run silently start using it: either
        the new run's registration already happened (this call correctly
        sees busy and declines) or it has not (the new run's task has not
        reached `get()` yet either, since registration always precedes it).

        Returns `False` only when `is_busy()` said yes -- a genuine busy
        refusal the caller should report. Returns `True` both when a
        worker was actually released and when there was nothing to
        release (already gone on its own): either way, it was safe to
        proceed, which is the only thing callers use the return value for.
        """
        async with self._lock:
            if is_busy():
                return False
            keys = [
                key for key in self._workers
                if key[0] == project_name and key[1] == role
            ]
            workers = [self._workers.pop(key) for key in keys]
        for worker in workers:
            await worker.aclose()
        return True

    async def terminate(self, project_name: str, *, role: str) -> bool:
        """Kill one worker's process tree immediately (FR-052).

        Returns whether there was a worker to kill. Only the bounded
        measurement calls this, and only on its own role.
        """
        async with self._lock:
            worker = self._workers.pop((project_name, role), None)
        if worker is None:
            return False
        await worker.terminate()
        return True

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
        """Projects with a running worker, each named once."""
        names: list[str] = []
        for (name, _role), worker in self._workers.items():
            if worker.is_running() and name not in names:
                names.append(name)
        return names

    def active_workers(self) -> list[tuple[str, str]]:
        """`(project, role)` for every running worker."""
        return [key for key, worker in self._workers.items() if worker.is_running()]
