#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Idle `--sandbox` worker pooling (parser-check CP5 Phase 11; issue #242; SC-006).

A warm sandbox run used to pay a full worker spawn every time: process start,
interpreter + pythonnet/CLR init, the HermitCrab DLL load and
`XmlLanguageLoader.Load` -- about three seconds on a small grammar, barely less
than the generation the cache skip saves. That is why SC-006's old 2x bar sat at
1.78x-1.93x. This pool keeps idle workers warm between runs, keyed so a worker
can only ever serve the exact grammar it loaded:

* project-cache runs: `(entry.key, params-sha)` -- the entry key already
  fingerprints the fwdata (path, size, mtime), the generator and
  HCPARSE_VERSION, and an entry directory is immutable once built;
* named sandboxes: `(config path, config mtime/size, id-map path/stat,
  params-sha)` -- the config is user-editable in place, so an edit changes
  the key and a pooled worker can never serve a grammar it did not load.

Both shapes also carry the `--engine-dir` and `--parse-delay` spawn
arguments (and the stub flag): a worker is never reused for a run that
would start it differently.

The params are hashed by CONTENT, not path: the worker reads `--hc-params`
from a per-run file at load time, so the path is useless as a key.

The worker side needed no change for this: `_SandboxBackend.release()` keeps
the Morpher for the process's life, and `_send_baseline_once` re-sends the
held grammar's baseline once per new run_id, so a reusing run's record stays
complete with no wire change.

Eviction: `cache.invalidate(project)` notifies every live pool (those workers'
entries are unusable); `cache.prune(project)` notifies with its deleted keys;
and an idle-timeout sweeper reaps workers nobody reuses. Checkout is
exclusive, so two concurrent runs on one key still get separate workers
(F-13). A worker is only ever admitted after it loaded a grammar (the client
checks this via the received `load_baseline` -- `SandboxClient._can_pool`):
a worker that never loaded would re-read its per-run `--hc-params`/`--id-map`
files at a later load, and those live under the first run's record.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import threading
import time
import weakref
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..parse.worker_client import ParseWorkerClient, SandboxSpawn

__all__ = [
    "IDLE_TIMEOUT_SECONDS",
    "SWEEP_INTERVAL_SECONDS",
    "SandboxWorkerPool",
    "compute_pool_key",
    "notify_project_invalidated",
    "notify_keys_pruned",
]

_log = logging.getLogger(__name__)

#: An idle worker older than this is reaped by the sweeper. A sandbox worker
#: holds no project lock (no project is ever opened), so the timeout is about
#: memory, not lock hygiene -- generous on purpose.
IDLE_TIMEOUT_SECONDS = 300.0

#: How often the sweeper looks for idle-expired workers.
SWEEP_INTERVAL_SECONDS = 60.0

#: How long a pooled worker gets to answer a liveness ping at checkout.
_PING_TIMEOUT_SECONDS = 5.0


def _stat_signature(path: Optional[str]) -> Optional[Tuple[int, int]]:
    """`(mtime_ns, size)` for `path`, or None when it cannot be statted.

    A cheap change detector for user-editable files (named-sandbox configs
    and their sidecars): an in-place edit changes the pool key, so a pooled
    worker can never serve a grammar it did not load.
    """
    if not path:
        return None
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _params_sha(parameters: Optional[Dict[str, Any]]) -> str:
    """Stable hash of the resolved Morpher parameters (D3, FR-047)."""
    canonical = json.dumps(parameters or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def compute_pool_key(
    *,
    kind: str,
    entry_key: Optional[str] = None,
    config_path: Optional[str] = None,
    id_map_path: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    engine_dir: Optional[str] = None,
    parse_delay: float = 0.0,
    stub: bool = False,
) -> tuple:
    """The pool key for one sandbox run's worker (T116).

    `kind="cache"`: a project-cache run -- `entry_key` is the cache entry's
    key, which already fingerprints the fwdata, the generator and
    HCPARSE_VERSION. `kind="named"`: a named sandbox -- the config path plus
    file signatures, because the user can edit it in place. `engine_dir` is
    the `--engine-dir` spawn argument (None: the worker's standard install):
    a worker must never serve a run that would start it with a different
    engine. `parse_delay` is the `--parse-delay` spawn argument (test-only).
    `stub` is part of the key: a `--stub` test worker must never serve a
    real run, and a real worker must never serve a stub run.
    """
    params_sha = _params_sha(parameters)
    engine = str(engine_dir) if engine_dir else None
    delay = float(parse_delay or 0.0)
    if kind == "cache":
        if not entry_key:
            raise ValueError("a cache-kind pool key needs the cache entry key")
        return ("cache", entry_key, params_sha, engine, delay, bool(stub))
    if kind == "named":
        if not config_path:
            raise ValueError("a named-kind pool key needs the config path")
        return (
            "named",
            str(config_path),
            _stat_signature(config_path),
            str(id_map_path) if id_map_path else None,
            _stat_signature(id_map_path),
            params_sha,
            engine,
            delay,
            bool(stub),
        )
    raise ValueError("pool key kind must be 'cache' or 'named', not %r" % (kind,))


def _worker_client_class():
    """`ParseWorkerClient` as the sandbox client module sees it.

    Indirected (not imported at top) so tests can monkeypatch
    `flextoolsmcp.server.sandbox.client.ParseWorkerClient` -- the same seam
    the pre-pool client used -- and have pool spawns go through the spy.
    `client` never imports this module at top level (it imports it lazily),
    so there is no import cycle.
    """
    from . import client as _client_mod

    return _client_mod.ParseWorkerClient


@dataclass
class _PooledWorker:
    worker: ParseWorkerClient
    key: tuple
    project_name: str
    #: The cache entry key for cache-kind workers (prune eviction); None for named.
    entry_key: Optional[str]
    idle_since: float = field(default_factory=time.monotonic)


#: Every live pool, so `cache.invalidate`/`cache.prune` can notify without
#: the pool being threaded through their callers. Weak: a closed pool
#: disappears on its own.
_POOLS: "weakref.WeakSet[SandboxWorkerPool]" = weakref.WeakSet()


def notify_project_invalidated(project_name: str) -> None:
    """A project's cache was invalidated: evict its pooled workers everywhere.

    Called from `cache.invalidate` (lazy import there, no cycle). Their
    entries are unusable, so their grammars are stale by definition.
    """
    for pool in list(_POOLS):
        with contextlib.suppress(Exception):
            pool.evict_project(project_name)


def notify_keys_pruned(entry_keys: List[str]) -> None:
    """Cache entries were pruned from disk: evict workers holding those keys."""
    doomed = set(entry_keys)
    if not doomed:
        return
    for pool in list(_POOLS):
        with contextlib.suppress(Exception):
            pool.evict_keys(doomed)


class SandboxWorkerPool:
    """Idle `--sandbox` workers, kept warm between runs.

    Owned by `ParseRunner` (one per server process), like `WorkerPool`.
    The bookkeeping lock is a plain `threading.Lock`: every critical
    section is a few dict operations with no awaits inside, so eviction can
    be triggered synchronously from `cache.invalidate`/`cache.prune` while
    checkout/checkin stay async.
    """

    def __init__(
        self,
        *,
        idle_timeout: float = IDLE_TIMEOUT_SECONDS,
        sweep_interval: float = SWEEP_INTERVAL_SECONDS,
    ) -> None:
        self._idle: Dict[tuple, List[_PooledWorker]] = {}
        self._guard = threading.Lock()
        #: Workers currently checked out. `aclose()` reaps these too: a
        #: borrower that drops a worker without checking it back in (or
        #: closing it) must not leak the process past the pool's life.
        #: Same ownership as `WorkerPool`, which reaps every worker it
        #: spawned.
        self._checked_out: Set[ParseWorkerClient] = set()
        self._idle_timeout = idle_timeout
        self._sweep_interval = sweep_interval
        #: The loop workers were spawned on; captured on first async use.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sweeper: Optional[asyncio.Task] = None
        #: Background close tasks, strongly held so they are not GC'd mid-flight.
        self._tasks: Set[asyncio.Task] = set()
        self._closed = False
        _POOLS.add(self)

    # -- checkout / checkin -------------------------------------------------

    async def checkout(
        self,
        key: tuple,
        *,
        project_name: str,
        spawn: SandboxSpawn,
        stub: bool = False,
        parse_delay: float = 0.0,
    ) -> Tuple[ParseWorkerClient, bool]:
        """A worker for `key`: a warm idle one when possible.

        Returns `(worker, reused)`. A pooled worker found dead or unresponsive
        is discarded and replaced, never handed out. On a miss (or when the
        pool is closed) a fresh worker is spawned and started, exactly as a
        run would without the pool. `stub`/`parse_delay` describe the worker
        this run needs (test-only); they are part of the key, so a stub
        worker can never be handed to a real run.
        """
        self._capture_loop()
        if not self._closed:
            entry = self._take_idle(key)
            if entry is not None:
                worker = entry.worker
                if await self._is_usable(worker):
                    worker.clear_run_listeners()
                    worker.set_stderr_sink(None)
                    with self._guard:
                        self._checked_out.add(worker)
                    return worker, True
                _log.info(
                    "Discarding a pooled sandbox worker for %r that did not "
                    "survive idle.", project_name)
                with contextlib.suppress(Exception):
                    await worker.aclose()
        worker = await self._spawn(project_name, spawn, stub=stub,
                                   parse_delay=parse_delay)
        with self._guard:
            self._checked_out.add(worker)
        return worker, False

    async def checkin(
        self,
        key: tuple,
        worker: ParseWorkerClient,
        *,
        project_name: str,
        entry_key: Optional[str] = None,
    ) -> bool:
        """Park `worker` as idle under `key`. False when it was refused.

        Refusals (closed pool, dead worker, requests still in flight) never
        close the worker here -- the caller does that, so the refusal path
        is one line at the call site either way.
        """
        self._capture_loop()
        if self._closed or not worker.is_running() or worker.has_pending_requests:
            return False
        with self._guard:
            for entries in self._idle.values():
                for entry in entries:
                    if entry.worker is worker:
                        # Already parked: a second checkin of the same worker
                        # would hand one process to two runs at once (F-13).
                        # The client detaches at finalize so this cannot
                        # happen in production; refuse defensively.
                        _log.warning(
                            "Refusing a double checkin of a pooled sandbox "
                            "worker for %r.", project_name)
                        return False
            worker.clear_run_listeners()
            worker.set_stderr_sink(None)
            self._checked_out.discard(worker)
            self._idle.setdefault(key, []).append(
                _PooledWorker(
                    worker=worker,
                    key=key,
                    project_name=project_name,
                    entry_key=entry_key,
                )
            )
        self._ensure_sweeper()
        return True

    async def _spawn(
        self,
        project_name: str,
        spawn: SandboxSpawn,
        *,
        stub: bool = False,
        parse_delay: float = 0.0,
    ) -> ParseWorkerClient:
        worker = _worker_client_class()(
            project_name,
            stub=stub,
            parse_delay=parse_delay,
            sandbox=spawn,
        )
        await worker.start()
        return worker

    async def _is_usable(self, worker: ParseWorkerClient) -> bool:
        """Alive AND answering: `is_running` alone can lag a dead process."""
        if not worker.is_running():
            return False
        try:
            return await asyncio.wait_for(worker.ping(), timeout=_PING_TIMEOUT_SECONDS)
        except Exception:  # noqa: BLE001 -- any failure means "not usable"
            return False

    def _take_idle(self, key: tuple) -> Optional[_PooledWorker]:
        with self._guard:
            entries = self._idle.get(key)
            if not entries:
                return None
            entry = entries.pop()
            if not entries:
                del self._idle[key]
            return entry

    # -- eviction -----------------------------------------------------------

    def evict_project(self, project_name: str) -> None:
        """Drop every idle worker for `project_name` (cache invalidation)."""
        self._evict(lambda entry: entry.project_name == project_name)

    def evict_keys(self, entry_keys: Set[str]) -> None:
        """Drop idle workers holding one of these cache entry keys (prune)."""
        doomed = set(entry_keys)
        self._evict(lambda entry: entry.entry_key in doomed)

    def _evict(self, predicate: Callable[[_PooledWorker], bool]) -> None:
        with self._guard:
            doomed = [
                entry
                for entries in self._idle.values()
                for entry in entries
                if predicate(entry)
            ]
            if doomed:
                doomed_ids = {id(entry) for entry in doomed}
                for key in list(self._idle):
                    kept = [
                        entry
                        for entry in self._idle[key]
                        if id(entry) not in doomed_ids
                    ]
                    if kept:
                        self._idle[key] = kept
                    else:
                        del self._idle[key]
        for entry in doomed:
            _log.info(
                "Evicting a pooled sandbox worker for %r (stale key).",
                entry.project_name,
            )
            self._close_soon(entry.worker)

    def _close_soon(self, worker: ParseWorkerClient) -> None:
        """Close `worker` on its loop without blocking the caller."""
        loop = self._loop
        if loop is None or loop.is_closed():
            # No worker can exist yet: workers are only made on a loop, and
            # the loop is captured before the first one is.
            return

        def _schedule() -> None:
            task = asyncio.ensure_future(self._close_worker(worker))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(_schedule)

    @staticmethod
    async def _close_worker(worker: ParseWorkerClient) -> None:
        with contextlib.suppress(Exception):
            await worker.aclose()

    # -- idle sweeping ------------------------------------------------------

    def _capture_loop(self) -> None:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

    def _ensure_sweeper(self) -> None:
        if self._sweeper is None or self._sweeper.done():
            self._sweeper = asyncio.get_running_loop().create_task(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self._sweep_interval)
                await self._sweep_once()
        except asyncio.CancelledError:
            pass

    async def _sweep_once(self) -> None:
        now = time.monotonic()
        with self._guard:
            stale = [
                entry
                for entries in self._idle.values()
                for entry in entries
                if now - entry.idle_since >= self._idle_timeout
            ]
            if stale:
                stale_ids = {id(entry) for entry in stale}
                for key in list(self._idle):
                    kept = [
                        entry
                        for entry in self._idle[key]
                        if id(entry) not in stale_ids
                    ]
                    if kept:
                        self._idle[key] = kept
                    else:
                        del self._idle[key]
        for entry in stale:
            _log.info(
                "Reaping an idle sandbox worker for %r after %ss.",
                entry.project_name,
                int(self._idle_timeout),
            )
            with contextlib.suppress(Exception):
                await entry.worker.aclose()

    # -- lifecycle ----------------------------------------------------------

    def idle_count(self) -> int:
        """Idle workers currently parked, for tests and diagnostics."""
        with self._guard:
            return sum(len(entries) for entries in self._idle.values())

    async def aclose(self) -> None:
        """Reap every worker the pool knows about, idle or checked out.

        Idempotent. A borrower holding a checked-out worker across `aclose`
        gets it closed underneath it; `ParseWorkerClient.aclose` is
        idempotent, so the borrower's own teardown stays safe.
        """
        if self._closed:
            return
        self._closed = True
        sweeper, self._sweeper = self._sweeper, None
        if sweeper is not None:
            sweeper.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sweeper
        with self._guard:
            workers = [
                entry.worker
                for entries in self._idle.values()
                for entry in entries
            ]
            self._idle.clear()
            # Idle and checked-out are disjoint: checkout removes from idle,
            # checkin removes from checked-out.
            workers.extend(self._checked_out)
            self._checked_out.clear()
        for worker in workers:
            with contextlib.suppress(Exception):
                await worker.aclose()
        tasks, self._tasks = set(self._tasks), set()
        for task in tasks:
            with contextlib.suppress(Exception):
                await task
        with contextlib.suppress(Exception):
            _POOLS.discard(self)
