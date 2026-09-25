#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The run lifecycle (parser-check CP2b, FR-026/FR-028/FR-032/FR-034;
data-model.md sections 1 and 6).

**THIS IS THE ONE EXECUTION PATH.** FR-026 says all parser execution goes
through one run mechanism and that there must not be a separate synchronous
path. Every story in this checkpoint runs through `ParseRunner.start_run`:
the single word of US2, the restricted trace of US3, the long batch of US4.
There is no "quick" variant for single words, and adding one would break the
requirement no matter how much simpler it looked -- a single word is a run
with `words_total == 1`, nothing more.

That is also why this module is the only thing that constructs a
`RunRecord`, drives stage transitions and talks to `worker_client`. A second
caller doing any of those would be the second path FR-026 forbids, and
`tests/test_cp1_boundary.py` (T060) asserts structurally that no handler
reaches the parser facade outside this package.

THE GRACE WINDOW REPORTS; IT DOES NOT EXECUTE. This is the single most
misreadable requirement in the checkpoint, so it is stated plainly here and
asserted in `tests/test_parse_runner.py` (T024):

    FR-028 -- "The window governs reporting only -- it MUST NOT cancel,
    time out or throttle the run."
    SC-010 -- "Exceeding the grace window cancels or slows 0 runs."

The window is a **`wait_for` on a copy of the run's completion signal**, not
a deadline imposed on the work. When it closes, exactly one thing happens:
this function stops waiting and returns a handle. The run does not learn
that the window closed; there is no cancellation, no timeout, no throttle,
and no branch anywhere below that treats a windowed-out run differently from
one that was never waited on. Written any other way -- a timeout passed to
the worker, a deadline stored on the run, a cancel on the task -- the window
would be executing rather than reporting, and SC-010 would be false.

A useful way to keep it honest while editing: the grace window is on the
**caller's** side of the conversation. Nothing downstream of `_execute_run`
takes it as an argument, and nothing downstream may start.

WHY A FAILURE POINTS AT DIAGNOSTICS RATHER THAN A RETRY. `RunFailure`
carries a `next_step` naming `flextools_health` and `flextools_grammar_health`
(FR-034). The case that motivates it is memory exhaustion during
`loading_grammar`: retrying re-runs the step that just exhausted memory,
whereas the diagnostic instruments say what the project would need. So the
guidance names the instruments, and deliberately does not say "try again".

This module is server-side. It holds no project, constructs no parser, and
imports nothing from `worker_main` -- the worker is reached only through
`worker_client`, which addresses it by dotted path (research.md R-02).

CP3'S BATCH IS A CALL SITE, NOT A SECOND RUNNER (FR-014, R-01). A batch is
`start_run(..., level="batch", priority=Priority.LOW)`: the same record, the
same stages, the same cancellation, the same worker. Every run -- a single
word included -- now enters through `ParseQueue.enqueue_run`, one item per
wordform, and is drained one word at a time. That per-wordform granularity is
what gives an interleaving single word a boundary to land on (FR-031), and
the batch resumes at its next word with its position intact because nothing
about it was touched (SC-005).

WHAT A BATCH ADDS TO A RUN, all of it on the record (contracts/artifact.md):
the resolved word list (`words.txt`), the scope fingerprint and the engine at
submission, the host counters as they accumulate, a warning if the engine
changes mid-job, and the grammar load-error baseline keyed to the
fingerprint. Progress and counters are persisted after EVERY word, not only
on stage change (FR-016): a run killed at word four thousand says so.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional

from .priority import DEFAULT_SINGLE_WORD_PRIORITY, Priority
from .queue import ParseQueue
from .record import HostCounters, RunRecord
from .retention import prune_runs
from .stages import (
    InvalidStageTransition,
    RunStage,
    can_transition,
    is_terminal,
    working_stage,
)
from .worker_client import MEASUREMENT_ROLE, SHARED_ROLE, WorkerError, WorkerPool
from ..sandbox.client import SANDBOX_ROLE, SandboxClient

__all__ = [
    "DEFAULT_GRACE_WINDOW_SECONDS",
    "RunFailure",
    "RunHandle",
    "RunAlreadyTerminal",
    "ParseRunner",
    "MEASUREMENT_ROLE",
    "SHARED_ROLE",
    "SANDBOX_ROLE",
]

_log = logging.getLogger(__name__)

#: FR-028's default. A *starting value*, configurable, and explicitly not a
#: timeout -- see the module docstring.
DEFAULT_GRACE_WINDOW_SECONDS = 5.0

_ENV_GRACE_WINDOW = "FLEXTOOLSMCP_PARSE_GRACE_WINDOW"

#: What a failed run points a caller at. Named instruments, never "retry"
#: (FR-034).
#:
#: FR-058's revisit: the words a failed run completed are readable with
#: flextools_parse_log, which CP3 ships -- so the guidance now says so.
_FAILURE_NEXT_STEP = (
    "Run flextools_grammar_health for this project's grammar and "
    "flextools_health for the environment. A run that failed while loading "
    "the grammar has usually exhausted memory, and repeating the run repeats "
    "the step that exhausted it -- the diagnostics say what the project needs. "
    "Words completed before the failure are readable with flextools_parse_log."
)


def _grace_window_default() -> float:
    raw = os.environ.get(_ENV_GRACE_WINDOW)
    if not raw:
        return DEFAULT_GRACE_WINDOW_SECONDS
    try:
        return float(raw)
    except ValueError:
        _log.warning("Ignoring unparseable %s=%r", _ENV_GRACE_WINDOW, raw)
        return DEFAULT_GRACE_WINDOW_SECONDS


@dataclass
class RunFailure:
    """Why a run ended in `failed`, and what to do about it.

    `stage_at_failure` is the diagnostic payload: attributing a death to
    `loading_grammar` rather than to a vague "parse failed" is the whole
    reason that stage is distinct (FR-027, FR-034).
    """

    message: str
    stage_at_failure: str
    error_type: Optional[str] = None
    next_step: str = _FAILURE_NEXT_STEP
    #: Set when the failure was a worker-side REFUSAL rather than a crash --
    #: `parser_engine_mismatch`, `parser_core_missing`. Carried so the
    #: handler can re-emit the refusal under its own code instead of
    #: flattening every death into `runtime_error`, which would lose the one
    #: thing the caller can act on. `detail` is the worker's payload,
    #: UNCHANGED: it is already shaped like the matching response model, and
    #: the field ORDER of `parser_engine_mismatch` is pinned by the parent
    #: spec, so a round-trip through a rebuilt dict is where it would drift
    #: (research.md R-03).
    error_code: Optional[str] = None
    detail: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "stage_at_failure": self.stage_at_failure,
            "error_type": self.error_type,
            "next_step": self.next_step,
            "error_code": self.error_code,
            "detail": self.detail,
        }


@dataclass
class RunHandle:
    """A run in flight, and everything the server knows about it.

    Held in memory for the life of the server process; the durable copy is
    the `RunRecord` on disk, which is what survives the process dying
    (FR-029).
    """

    run_id: str
    project_name: str
    words_total: int
    record: RunRecord
    priority: Priority = DEFAULT_SINGLE_WORD_PRIORITY
    stage: RunStage = RunStage.STARTING
    words_completed: int = 0
    #: Set by the server; observed by the worker at the next word boundary
    #: (FR-032). Never a terminal state by itself -- the run is `cancelled`
    #: only once the worker has actually stopped.
    cancel_requested: bool = False
    #: The stage the run was in when cancellation actually took effect --
    #: `parse_job_cancelled`'s `state_at_cancel` (FR-036). Declared here
    #: rather than set ad hoc so the field exists whether or not the run
    #: was ever cancelled.
    stage_at_cancel: Optional[str] = None
    interleaved_by: Optional[str] = None
    failure: Optional[RunFailure] = None
    results: list[dict[str, Any]] = field(default_factory=list)
    #: Set when the run reaches a terminal stage. The grace window waits on
    #: this; nothing else does.
    done: asyncio.Event = field(default_factory=asyncio.Event)
    task: Optional[asyncio.Task] = None

    # -- CP3 (batch) ------------------------------------------------------

    level: str = "plain"
    #: `ScopeFingerprint.to_dict()` for a batch; None for a single word.
    scope_fingerprint: Optional[dict[str, Any]] = None
    engine_at_submission: Optional[str] = None
    #: A WARNING on the summary, never a refusal (FR-024).
    engine_changed_midjob: bool = False
    engine_now: Optional[str] = None
    load_error_baseline: Optional[dict[str, Any]] = None
    vernacular_ws: Optional[str] = None
    counters: Optional[HostCounters] = None
    #: The run's own queue: one item per wordform (FR-014). Held so a
    #: cancel can drop what has not been sent yet.
    queue: Optional[ParseQueue] = None
    #: Runs this one has displaced on the same worker, for FR-026's
    #: progress accounting. Cleared when this run ends.
    displacing: list[str] = field(default_factory=list)

    # -- CP3 (US6) --------------------------------------------------------

    #: Which of the project's pool keys this run's worker lives under.
    #: `SHARED_ROLE` for every run but the bounded measurement, which runs
    #: alone under `MEASUREMENT_ROLE` so that killing it at its bound cannot
    #: take a batch with it (FR-051, R-05).
    worker_role: str = SHARED_ROLE
    #: `time.monotonic()` when the run entered its current stage. What lets
    #: "a batch that entered grammar loading and STAYED there" be a
    #: measured fact rather than a guess (FR-056).
    stage_entered_at: float = field(default_factory=time.monotonic)

    # -- CP4 (filing) -----------------------------------------------------

    #: True only for a run created with `filing=True`: its words are parsed
    #: AND filed, in a worker of its own. Every other run is read-only.
    is_filing: bool = False
    #: The run's `filing` meta section, kept current by its observer.
    filing: Optional[dict[str, Any]] = None
    #: The filing run's observer (`filing/observer.py`): per-word
    #: bookkeeping and the terminal hook. None on every read-only run.
    observer: Any = None

    # -- CP5 (sandbox spine) ----------------------------------------------

    #: The run's OWN `SandboxClient`, built per run under `SANDBOX_ROLE`
    #: and never pooled (F-13). None on every in-process run.
    sandbox_client: Any = None

    @property
    def is_terminal(self) -> bool:
        return is_terminal(self.stage)

    @property
    def is_batch(self) -> bool:
        return self.scope_fingerprint is not None

    @property
    def words_pending(self) -> int:
        return max(self.words_total - self.words_completed, 0)


class RunAlreadyTerminal(Exception):
    """A cancel arrived for a run that had already ended (FR-036).

    Carries a `parse_job_cancelled`-shaped detail, so a caller re-emits it
    rather than rebuilding it -- the same discipline the worker channel
    follows for `parser_engine_mismatch` (research.md R-03).

    NOT raised by `flextools_parse_status`. Asking after a terminal run is a
    successful query; this is for something trying to ACT on one. The two
    directions are easy to implement backwards, which is why they are
    separated here at the source rather than at the tool boundary.
    """

    def __init__(self, handle: "RunHandle") -> None:
        state = handle.stage_at_cancel or handle.stage.value
        super().__init__(
            f"Run {handle.run_id} has already ended ({handle.stage.value})."
        )
        self.detail = {
            "error_code": "parse_job_cancelled",
            "run_id": handle.run_id,
            "words_completed": handle.words_completed,
            "state_at_cancel": state,
            "hint": (
                f"This run ended in {handle.stage.value!r} and cannot be "
                f"cancelled again. {handle.words_completed} of "
                f"{handle.words_total} words completed before it stopped, and "
                f"those results are readable -- they were written as they "
                f"were produced. Use flextools_parse_status to read them."
            ),
        }
        self.handle = handle


class ParseRunner:
    """Owns every run: its stages, its record, and its worker.

    One instance per server process. `WorkerPool` underneath it owns one
    worker per project, so the runner never has to reason about which
    process holds which grammar.
    """

    def __init__(
        self,
        *,
        pool: Optional[WorkerPool] = None,
        grace_window: Optional[float] = None,
        record_dir=None,
        stub: bool = False,
    ) -> None:
        self._pool = pool if pool is not None else WorkerPool(stub=stub)
        self._grace_window = (
            grace_window if grace_window is not None else _grace_window_default()
        )
        self._record_dir = record_dir
        self._runs: dict[str, RunHandle] = {}
        # Projects whose shared read worker holds a cache older than a write
        # made elsewhere, and was busy when that write ended (CP4 R-09).
        self._stale_read_workers: set[str] = set()
        # CP5 R-11: the third way a copy is deleted -- once, before this
        # server's first sandbox job, every marked `work/<id>/` whose run is
        # not live here.
        self._sandbox_swept = False

    # -- introspection ----------------------------------------------------

    @property
    def grace_window(self) -> float:
        return self._grace_window

    @property
    def record_dir(self):
        """Where this runner's records live, for the artifact readers.

        None means the default (`record.get_record_dir()`). The log and diff
        tools read the artifact through this rather than through a handle, so
        a run from an earlier server process is as readable as a live one.
        """
        return self._record_dir

    @property
    def pool(self):
        """The worker pool. Exposed for the one caller that needs a worker
        WITHOUT starting a run: the morph resolver, which must reach the
        lexicon before any parse is enqueued (FR-019)."""
        return self._pool

    def get(self, run_id: str) -> Optional[RunHandle]:
        return self._runs.get(run_id)

    # -- batch submission (CP3) -------------------------------------------

    async def check_engine(self, project_name: str) -> str:
        """Run the engine gate once, for a batch about to be submitted.

        FR-024: the batch handler's first project-touching statement. The
        worker runs `check_active_parser` and nothing else; a mismatch comes
        back as a `WorkerError` carrying `parser_engine_mismatch` unchanged.
        Returns the engine that passed, which the run records as
        `engine_at_submission` and the fingerprint records as `engine`.
        """
        worker = await self._pool.get(project_name)
        return await worker.check_engine(request_id=f"engine:{uuid.uuid4().hex[:12]}")

    async def resolve_scope(self, project_name: str, scope: dict[str, Any]) -> dict[str, Any]:
        """Resolve a scope in the project's worker. Parses nothing."""
        worker = await self._pool.get(project_name)
        return await worker.resolve_scope(
            request_id=f"scope:{uuid.uuid4().hex[:12]}", scope=scope
        )

    # -- CP4: the filing preflight's reads, put to the READ worker ---------
    #
    # Three questions the filing handler asks before any preview exists
    # (contracts/tools.md rows 5 and 9). Each is a read, answered by the
    # shared read-only worker because it is the one process with the project
    # open; none of them starts a run, parses a batch word or writes.

    def read_worker_pid(self, project_name: str) -> Optional[int]:
        """The PID of this project's shared read worker, if one is running."""
        worker = self._pool.peek(project_name)
        if worker is None:
            return None
        pid = getattr(worker, "worker_pid", None)
        if not isinstance(pid, int):
            pid = getattr(worker, "pid", None)
        return pid if isinstance(pid, int) else None

    def read_worker_busy(self, project_name: str) -> bool:
        """Is any live run using this project's shared read worker?"""
        return self.worker_busy(project_name, role=SHARED_ROLE)

    def worker_busy(self, project_name: str, *, role: str) -> bool:
        """Is any live run using this project's worker of the given role?

        Generalizes `read_worker_busy` (SHARED_ROLE only) to any role, so a
        write gate that finds the lock held by a MEASUREMENT_ROLE worker can
        ask the same question (#223).
        """
        return any(
            not other.is_terminal and other.project_name == project_name
            and other.worker_role == role
            for other in self._runs.values()
        )

    def active_run_ids(self, project_name: str, *, role: str) -> List[str]:
        """Non-terminal run IDs on this project's worker of the given role.

        For a refusal that needs to NAME the run occupying our own worker
        (#223), rather than just saying "busy".
        """
        return [
            other.run_id for other in self._runs.values()
            if not other.is_terminal and other.project_name == project_name
            and other.worker_role == role
        ]

    def own_worker_role_for_pid(self, project_name: str, pid: Optional[int]) -> Optional[str]:
        """Which role (if any) of this project's own workers holds PID `pid`?

        Checks every role the pool is tracking for this project (SHARED_ROLE
        and MEASUREMENT_ROLE), not just the shared read worker -- a write
        gate's probe can find the lock held by either (#223). `None` if
        `pid` is `None` or it does not match any worker this server started.
        """
        if pid is None:
            return None
        for role, worker in self._pool.workers_for(project_name).items():
            worker_pid = getattr(worker, "worker_pid", None)
            if not isinstance(worker_pid, int):
                worker_pid = getattr(worker, "pid", None)
            if worker_pid == pid:
                return role
        return None

    def mark_read_worker_stale(self, project_name: str) -> None:
        """Recycle this project's read worker before its next preflight read.

        For a write that ended while the worker was busy: the worker is not
        killed under a user's word, but it is not trusted again either.
        """
        self._stale_read_workers.add(project_name)

    async def _preflight_worker(self, project_name: str):
        """The read worker for a preflight read, recycled first if stale.

        If it is stale AND still busy, the stale worker answers: the filing
        worker re-checks every word against its own fresh read (R-02), so a
        stale preview costs skipped words, never an unconfirmed deletion.
        """
        if project_name in self._stale_read_workers and not self.read_worker_busy(project_name):
            self._stale_read_workers.discard(project_name)
            await self.release_worker(project_name, role=SHARED_ROLE)
        return await self._pool.get(project_name)

    async def probe_agent(self, project_name: str) -> dict[str, Any]:
        """Is the HermitCrab parser agent resolvable? (CP4 FR-025)."""
        worker = await self._preflight_worker(project_name)
        return await worker.probe_agent(request_id=f"agent:{uuid.uuid4().hex[:12]}")

    async def filing_gate(
        self, project_name: str, *, probe_word: Optional[str], vernacular_ws: Optional[str]
    ) -> dict[str, Any]:
        """The refuse-to-file gate's inputs, from this load (CP4 FR-020..FR-023, FR-039)."""
        worker = await self._preflight_worker(project_name)
        return await worker.filing_gate(
            request_id=f"gate:{uuid.uuid4().hex[:12]}",
            probe_word=probe_word,
            vernacular_ws=vernacular_ws,
        )

    async def filing_preview(
        self, project_name: str, *, words: list[str], vernacular_ws: Optional[str]
    ) -> dict[str, Any]:
        """The stored-analysis facts the deletion projection is built from."""
        worker = await self._preflight_worker(project_name)
        return await worker.filing_preview(
            request_id=f"preview:{uuid.uuid4().hex[:12]}",
            words=list(words),
            vernacular_ws=vernacular_ws,
        )

    def known_run_ids(self) -> list[str]:
        """Backs `parse_run_not_found`'s "here are the handles that exist"."""
        return list(self._runs)

    # -- stage transitions ------------------------------------------------

    def _set_stage(self, handle: RunHandle, stage: RunStage, **updates: Any) -> None:
        """Move a run to a stage, validating the edge and persisting it.

        The edge is validated rather than assumed so a wrong transition
        fails where it is made, instead of producing a stage history that is
        not a path through the graph. `filing` in particular has no inbound
        edge, so this is also what makes FR-027's "no CP2b code path can
        produce filing" true by construction rather than by inspection.
        """
        if stage is not handle.stage and not can_transition(
            handle.stage, stage, filing=handle.is_filing
        ):
            raise InvalidStageTransition(handle.stage, stage)
        if stage is not handle.stage:
            handle.stage_entered_at = time.monotonic()
        handle.stage = stage
        for key, value in updates.items():
            setattr(handle, key, value)

        meta_updates = self._progress_updates(handle)
        if handle.failure is not None:
            meta_updates["failure"] = handle.failure.to_dict()
        if stage is RunStage.CANCELLED:
            meta_updates["stage_at_cancel"] = updates.get(
                "stage_at_cancel", handle.stage.value
            )
        with contextlib.suppress(Exception):
            handle.record.set_stage(stage, **meta_updates)

        if is_terminal(stage):
            self._release_displaced(handle)
            if handle.observer is not None:
                # A filing run's claim clears in the SAME transition that
                # makes it terminal (FR-028), before anyone waiting on the run
                # is woken -- so no caller can see a finished run whose
                # project still reads as busy.
                with contextlib.suppress(Exception):
                    handle.observer.on_terminal(handle)
            handle.done.set()

    @staticmethod
    def _progress_updates(handle: RunHandle) -> dict[str, Any]:
        """The meta fields that move while a run is going."""
        updates: dict[str, Any] = {
            "words_completed": handle.words_completed,
            "words_total": handle.words_total,
            "interleaved_by": handle.interleaved_by,
        }
        if handle.is_batch:
            updates["engine_changed_midjob"] = handle.engine_changed_midjob
            updates["load_error_baseline"] = handle.load_error_baseline
            if handle.counters is not None:
                updates["counters"] = handle.counters.to_dict()
        if handle.is_filing and handle.filing is not None:
            # The record's `filing` SECTION (a meta field), not the stage: the
            # stage is produced only through stages.py's filing-run table.
            updates.update(dict(filing=handle.filing))
        return updates

    def _persist_progress(self, handle: RunHandle) -> None:
        """Write progress without a stage change (FR-016: incrementally)."""
        with contextlib.suppress(Exception):
            handle.record.set_stage(handle.stage, **self._progress_updates(handle))

    # -- interleave accounting (FR-026) -----------------------------------

    def _displace(self, handle: RunHandle) -> None:
        """Mark every less urgent live run on this project as waiting on us.

        The worker also reports interleaves, but only when the displaced run
        still has a word queued ON THE WORKER'S SIDE -- and this runner sends
        a run's words one at a time, so between two batch words the batch
        has nothing queued there and the worker has nothing to report. The
        runner is the party that knows both runs exist, so it records the
        fact itself: a batch paused behind a single word says who it is
        waiting on instead of appearing to stall.
        """
        for other in self._runs.values():
            if (
                other is handle
                or other.is_terminal
                or other.project_name != handle.project_name
                # A run in another worker does not share this one's word
                # boundaries: the bounded measurement never pauses a batch.
                or other.worker_role != handle.worker_role
                or int(other.priority) <= int(handle.priority)
            ):
                continue
            other.interleaved_by = handle.run_id
            handle.displacing.append(other.run_id)
            self._persist_progress(other)

    def _release_displaced(self, handle: RunHandle) -> None:
        for run_id in handle.displacing:
            other = self._runs.get(run_id)
            if other is not None and other.interleaved_by == handle.run_id:
                other.interleaved_by = None
                if not other.is_terminal:
                    self._persist_progress(other)
        handle.displacing = []

    # -- starting a run ---------------------------------------------------

    async def start_run(
        self,
        *,
        project_name: str,
        wordforms: list[str],
        level: str = "plain",
        restricted_to: Optional[tuple[int, ...]] = None,
        priority: Priority = DEFAULT_SINGLE_WORD_PRIORITY,
        grace_window: Optional[float] = None,
        scope_fingerprint: Optional[dict[str, Any]] = None,
        engine_at_submission: Optional[str] = None,
        vernacular_ws: Optional[str] = None,
        project_state: Optional[dict[str, Any]] = None,
        worker_role: str = SHARED_ROLE,
        filing: bool = False,
        filing_setup: Optional[dict[str, Any]] = None,
        observer: Any = None,
        record_guard: Any = None,
        spine: Optional[str] = None,
        sandbox: Optional[dict[str, Any]] = None,
        sandbox_launch: Any = None,
    ) -> RunHandle:
        """Start a run and wait out the grace window. THE only entry point.

        Returns as soon as either the run reaches a terminal stage or the
        grace window closes -- whichever comes first. The caller tells the
        two apart with `handle.is_terminal`: terminal means results are
        available inline and no handle need be issued; non-terminal means a
        handle is issued and **the run is still going, untouched**.

        The window does not reach the run. It is a `wait_for` on the run's
        own completion event, and when it expires this function simply stops
        waiting. `handle.task` is not cancelled, no deadline is passed
        downstream, and nothing below records that a window ever existed
        (FR-028, SC-010).

        A BATCH is this same call with `scope_fingerprint` and
        `engine_at_submission` set -- the caller has already run the engine
        gate once and resolved the scope. The word list is written to
        `words.txt` before the first `meta.json` (record.py), and retention
        runs here, at creation, over this project's other runs (FR-022).

        The BOUNDED MEASUREMENT is this same call too (US6): one word, at
        `TRY_A_WORD`, under `worker_role=MEASUREMENT_ROLE`, with the bound as
        its window. What happens when the window closes is the measurement's
        business (`measure.py`), not this method's -- here it still only
        stops waiting.

        A FILING run (CP4) is this same call too, with `filing=True`, under
        the filing package's worker role, carrying the `filing_setup` its
        worker is handed before the first word and the `observer` that keeps
        the record's `filing` section. The caller -- the filing handler --
        has already walked every rung of the write ladder; this method only
        runs what it was given. `record_guard` vets the record's directory
        (FR-042) before anything is created in it.

        A SANDBOX run (CP5) is this same call too, under `SANDBOX_ROLE`, with
        `spine="sandbox"`, its initial `sandbox` meta section, and the
        `sandbox_launch` (a `sandbox.client.SandboxLaunch` or the handler's
        dict: fwdata_path, generate_hc_config_path, hc_path, hc_invoke_argv,
        config_path, timeout_seconds) its client is built from. The client is
        built HERE, fresh for this run, instead of taken from the pool (F-13):
        two concurrent sandbox jobs on one project get two clients and two
        copies. `sandbox_launch` is not persisted.
        """
        window = grace_window if grace_window is not None else self._grace_window
        batch = scope_fingerprint is not None
        section = observer.initial_section() if (filing and observer is not None) else None

        record = RunRecord.create(
            project_name=project_name,
            words_total=len(wordforms),
            record_dir=self._record_dir,
            words=list(wordforms) if batch else None,
            scope_fingerprint=scope_fingerprint,
            engine_at_submission=engine_at_submission,
            project_state=project_state,
            filing=section,
            guard=record_guard,
            spine=spine,
            sandbox=sandbox,
        )
        sandbox_client = None
        if worker_role == SANDBOX_ROLE:
            if sandbox_launch is None:
                raise ValueError("A sandbox run needs its sandbox_launch.")
            self._sweep_sandbox_copies(exclude=record.run_id)
            sandbox_client = SandboxClient(
                project_name,
                run_id=record.run_id,
                record=record,
                wordforms=list(wordforms),
                launch=sandbox_launch,
            )
        handle = RunHandle(
            run_id=record.run_id,
            project_name=project_name,
            words_total=len(wordforms),
            record=record,
            priority=priority,
            level=level,
            scope_fingerprint=scope_fingerprint,
            engine_at_submission=engine_at_submission,
            vernacular_ws=vernacular_ws,
            counters=HostCounters() if batch else None,
            worker_role=worker_role,
            is_filing=bool(filing),
            filing=section,
            observer=observer if filing else None,
            sandbox_client=sandbox_client,
        )
        self._runs[handle.run_id] = handle
        self._displace(handle)
        self._prune(project_name)
        if handle.observer is not None:
            handle.observer.on_start(handle)

        handle.task = asyncio.create_task(
            self._execute_run(handle, wordforms, level, restricted_to, filing_setup)
        )

        # The grace window, in full. Note what is NOT here: no cancel, no
        # deadline handed downstream, no flag set on the run. The only
        # consequence of the window closing is that this `await` ends.
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.shield(handle.done.wait()), timeout=window
            )

        return handle

    def _prune(self, project_name: str) -> None:
        """Keep this project's newest twenty runs (FR-022). Never fatal.

        Every run this server holds live is protected, whatever its age: a
        live run's directory is still being appended to.
        """
        live = [h.run_id for h in self._runs.values() if not h.is_terminal]
        try:
            prune_runs(project_name, protect=live, record_dir=self._record_dir)
        except Exception as exc:  # noqa: BLE001 -- retention must not fail a run
            _log.warning("Run retention failed for %s: %s", project_name, exc)

    async def _execute_run(
        self,
        handle: RunHandle,
        wordforms: list[str],
        level: str,
        restricted_to: Optional[tuple[int, ...]],
        filing_setup: Optional[dict[str, Any]] = None,
    ) -> None:
        """Drive one run to a terminal stage. Never raises.

        Takes no grace-window argument, and must never be given one: the
        window belongs to the caller's side of the conversation. A failure
        here becomes `failed` with a `RunFailure`, because a run that raised
        into a background task and left no stage would be indistinguishable
        from one still running.

        A FILING run (CP4) differs in four places, and only four:

          * its worker is handed `filing_setup` before the first word;
          * after its first word it works in `filing`, not `parsing`;
          * each word's outcome goes to the run's observer;
          * before it reports ANY terminal state -- completed, cancelled,
            refused mid-run, failed -- its worker is asked to persist what
            was filed (FR-034), and the record says whether that worked. A
            filing run never reports success over unsaved changes.
        """
        worker = None
        try:
            worker = await self._worker_for(handle)
            worker.listen_to_run(handle.run_id, lambda m: self._on_run_message(handle, m))
            if handle.sandbox_client is not None:
                # CP5: the per-run client resolves its config (generating it
                # on a cache miss) and launches the script for the whole list.
                # Listening first, so its `loading_grammar` stage is heard.
                await worker.start()
            if handle.is_filing:
                await worker.filing_setup(
                    request_id=f"setup:{handle.run_id}:{uuid.uuid4().hex[:8]}",
                    run_id=handle.run_id,
                    setup=dict(filing_setup or {}, record_root=str(handle.record.root)),
                )

            # THE STAGE IS NOT ANNOUNCED FROM HERE. It used to be: this line
            # set `loading_grammar` unconditionally, before the worker had
            # been asked for anything. The worker is the only party that
            # knows whether a load is actually about to happen -- it holds
            # the grammar -- and it already emits the stage when one is, so
            # announcing it here overrode the truth with a guess. The first
            # live run of quickstart scenario 1 caught it: a second call
            # against a HELD grammar reported a multi-second grammar load
            # that never occurred, which is exactly the report FR-027 makes
            # this stage distinct in order to give honestly.
            #
            # So the run stays in `starting` until the worker says
            # otherwise, and `starting -> parsing` is a real edge for the
            # warm case (stages.py).
            #
            # ONE ITEM PER WORDFORM (FR-014). The run's words enter its own
            # `ParseQueue` individually and are drained one at a time, so
            # each word is a boundary: a cancel drops everything not yet
            # sent, and a more urgent word on the same worker overtakes the
            # next batch word rather than waiting for the whole batch.
            queue = handle.queue = ParseQueue()
            queue.enqueue_run(handle.run_id, wordforms, handle.priority, restricted_to)

            batch_kwargs: dict[str, Any] = {}
            if handle.is_batch:
                batch_kwargs = {
                    "vernacular_ws": handle.vernacular_ws,
                    "engine_at_submission": handle.engine_at_submission,
                }

            while True:
                if handle.cancel_requested:
                    break
                queued = queue.dequeue()
                if queued is None:
                    break
                index, wordform = queued.index_in_run, queued.wordform

                try:
                    result = await worker.parse_word(
                        request_id=f"{handle.run_id}:{index}:{uuid.uuid4().hex[:8]}",
                        run_id=handle.run_id,
                        wordform=wordform,
                        level=level,
                        restricted_to=queued.restricted_to,
                        priority=int(handle.priority),
                        index_in_run=index,
                        **batch_kwargs,
                    )
                except WorkerError as exc:
                    if not self._is_word_error(handle, worker, exc):
                        raise
                    # ONE WORD FAILED; THE RUN DID NOT. A batch over ten
                    # thousand words must not die because one of them made
                    # the parser throw -- that word is recorded with its
                    # error and the batch moves to the next boundary. A dead
                    # worker, a cancellation or a coded refusal still end
                    # the run, through the handlers below.
                    self._record_word_error(handle, index, wordform, exc)
                    continue

                # A word came back, so the run is parsing whatever the
                # worker's stage messages did or did not arrive in time to
                # say. Reached from `starting` on the warm path and from
                # `loading_grammar` on the cold one.
                if handle.stage in (RunStage.STARTING, RunStage.LOADING_GRAMMAR):
                    self._set_stage(handle, RunStage.PARSING)
                if handle.is_filing and handle.stage is RunStage.PARSING:
                    # The first word is filed: the run is now filing, an edge
                    # that exists only in a filing run's table (stages.py).
                    self._set_stage(handle, working_stage(filing=True))

                entry = {
                    "index": index,
                    "wordform": wordform,
                    "parse": result.get("parse"),
                }
                if "assertion" in result:
                    # CP5 test mode: the data-model 6.5 assertion line.
                    entry["assertion"] = result["assertion"]
                trace_xml = result.get("trace_xml")
                if trace_xml:
                    # Out of line: a trace is tens or hundreds of KB, and
                    # inlining one makes the response unreadable and can
                    # overflow the transport (record.py, R-07).
                    with contextlib.suppress(Exception):
                        handle.record.write_trace(index, trace_xml)
                    entry["trace_path"] = f"traces/{index}.xml"

                handle.results.append(entry)
                handle.words_completed += 1
                with contextlib.suppress(Exception):
                    handle.record.append_result(entry)
                if handle.observer is not None:
                    handle.observer.on_result(handle, entry)
                if handle.is_batch:
                    # Counters accumulate from the line just written, and
                    # progress is persisted per word: a killed run's meta
                    # agrees with its results.jsonl (FR-016, FR-020).
                    handle.counters._add(entry)
                    self._persist_progress(handle)

            # CP5: the script's outcome is folded into the record and the copy
            # deleted BEFORE any terminal stage, so a caller woken by it
            # reads a finished record (and an empty work/, FR-011).
            await self._finalize_sandbox(handle)
            if handle.cancel_requested:
                stage_at_cancel = handle.stage.value
                if handle.is_filing:
                    await self._commit_filing(handle, worker, state="cancelled")
                self._set_stage(
                    handle, RunStage.CANCELLED, stage_at_cancel=stage_at_cancel
                )
            else:
                if handle.stage in (RunStage.STARTING, RunStage.LOADING_GRAMMAR):
                    # An empty run still passes through parsing, so the
                    # stage history stays a path through the graph.
                    self._set_stage(handle, RunStage.PARSING)
                if handle.is_filing and not await self._commit_filing(
                    handle, worker, state="completed"
                ):
                    raise WorkerError(
                        "The filing worker could not persist the filed words; the "
                        "run is not reported as completed. See the run record."
                    )
                self._set_stage(handle, RunStage.COMPLETED)

        except asyncio.CancelledError:
            # Only reachable if something cancels the task directly. The
            # grace window never does -- see start_run.
            with contextlib.suppress(Exception):
                self._set_stage(
                    handle,
                    RunStage.CANCELLED,
                    stage_at_cancel=handle.stage.value,
                )
            raise
        except Exception as exc:  # noqa: BLE001 -- recorded, see below
            # A cancelled run's outstanding words come back as errors
            # (`parse_job_cancelled`), because the worker answers every
            # request exactly once and those words will never be parsed.
            # That is the run ending as asked, not the run failing -- and
            # reporting it as `failed` would both lose the distinction and
            # attach diagnostic guidance to a user's own decision.
            if handle.is_filing and not handle.is_terminal:
                await self._end_filing_on_error(handle, worker, exc)
            await self._finalize_sandbox(handle)
            if handle.cancel_requested:
                with contextlib.suppress(InvalidStageTransition):
                    self._set_stage(
                        handle,
                        RunStage.CANCELLED,
                        stage_at_cancel=handle.stage.value,
                    )
            else:
                self._fail(handle, exc)
        finally:
            if handle.observer is not None:
                # Idempotent: already done in the terminal transition; here
                # only for a path that ended without one.
                with contextlib.suppress(Exception):
                    handle.observer.on_terminal(handle)
            handle.done.set()
            # Drop the run listener so a long-lived worker does not
            # accumulate one closure per run it has ever served.
            with contextlib.suppress(Exception):
                existing = self._peek_worker(handle)
                if existing is not None:
                    await existing.run_end(handle.run_id)
                    existing.stop_listening(handle.run_id)
            if handle.sandbox_client is not None:
                # Idempotent backstop: no process, watchdog or copy outlives
                # the run, however it ended (R-11).
                with contextlib.suppress(Exception):
                    await self._finalize_sandbox(handle)
                with contextlib.suppress(Exception):
                    await handle.sandbox_client.aclose()
            if handle.is_filing:
                # The filing worker is spawned for one run and released with
                # it: the process that holds a writable open does not outlive
                # the job (R-09).
                with contextlib.suppress(Exception):
                    await self._pool.release(handle.project_name, role=handle.worker_role)
                if handle.observer is not None:
                    with contextlib.suppress(Exception):
                        await handle.observer.after_terminal(handle, self)

    async def _commit_filing(
        self, handle: RunHandle, worker: Any, *, state: str, cause: Optional[str] = None
    ) -> bool:
        """Ask the filing worker to persist what it filed; record the outcome.

        FR-034: "filed changes are persisted to the project before the run
        reports success", and a cancelled or refused run persists what it
        already filed. Returns whether the save succeeded; the observer
        records it either way. `cause` is why a run that stopped early
        stopped: it is recorded even when the save itself succeeds (a run
        that ended `failed` with `error: null` tells nobody anything -- found
        live by CP4 L-0).
        """
        ok, error = False, None
        try:
            answer = await worker.filing_commit(
                request_id=f"commit:{handle.run_id}:{uuid.uuid4().hex[:8]}",
                run_id=handle.run_id,
            )
            ok = bool(answer.get("ok"))
            error = answer.get("error")
        except Exception as exc:  # noqa: BLE001 -- recorded, never raised past here
            error = f"{type(exc).__name__}: {exc}"
        if cause and error:
            error = f"{cause}; the save afterwards also failed: {error}"
        elif cause:
            error = cause
        if handle.observer is not None:
            handle.observer.finish(handle, state=state if ok else "failed",
                                   persisted=ok, error=error)
        self._persist_progress(handle)
        return ok

    async def _end_filing_on_error(self, handle: RunHandle, worker: Any, exc: Exception) -> None:
        """A filing run that stopped on an error: persist what was filed, name why.

        `refused_midrun` for a grammar the gate refused on a reload (FR-024:
        whatever was already filed is persisted and reported, and nothing is
        asked); `crashed` when the worker process is gone (nothing can be
        persisted from a dead process, and the record says so); `failed`
        otherwise.
        """
        code = getattr(exc, "error_code", None)
        alive = False
        with contextlib.suppress(Exception):
            alive = bool(worker is not None and worker.is_running())
        if handle.cancel_requested:
            state = "cancelled"
        elif code == "grammar_load_unclean":
            state = "refused_midrun"
        elif not alive:
            state = "crashed"
        else:
            state = "failed"
        cause = f"{type(exc).__name__}: {exc}"
        if alive:
            ok = await self._commit_filing(handle, worker, state=state, cause=cause)
            if not ok and handle.observer is not None:
                handle.observer.finish(handle, state=state, persisted=False,
                                       error=f"{cause}; the save after the error did not succeed")
        elif handle.observer is not None:
            handle.observer.finish(handle, state=state, persisted=False, error=cause)

    @staticmethod
    def _is_word_error(handle: RunHandle, worker: Any, exc: Exception) -> bool:
        """A per-word failure a batch survives, as opposed to a run failure."""
        if not handle.is_batch or handle.cancel_requested:
            return False
        if getattr(exc, "error_code", None):
            return False
        try:
            return bool(worker.is_running())
        except Exception:  # noqa: BLE001
            return False

    def _record_word_error(
        self, handle: RunHandle, index: int, wordform: str, exc: Exception
    ) -> None:
        entry = {
            "index": index,
            "wordform": wordform,
            "parse": None,
            "error": {"message": str(exc), "error_type": type(exc).__name__},
        }
        handle.results.append(entry)
        handle.words_completed += 1
        with contextlib.suppress(Exception):
            handle.record.append_result(entry)
        if handle.counters is not None:
            handle.counters._add(entry)
        self._persist_progress(handle)

    def _fail(self, handle: RunHandle, exc: Exception) -> None:
        """Record a failure at the stage it happened in."""
        failure = RunFailure(
            message=str(exc),
            stage_at_failure=handle.stage.value,
            error_type=type(exc).__name__,
        )
        detail = getattr(exc, "detail", None)
        if handle.sandbox_client is not None:
            detail = self._sandbox_failure_detail(handle, exc)
        if isinstance(detail, dict):
            failure.detail = detail
            if detail.get("hint"):
                failure.message = detail["hint"]
        error_code = getattr(exc, "error_code", None)
        if error_code:
            failure.error_code = error_code
        handle.failure = failure
        _log.warning(
            "Parse run %s failed during %s: %s",
            handle.run_id,
            handle.stage.value,
            exc,
        )
        with contextlib.suppress(InvalidStageTransition):
            self._set_stage(handle, RunStage.FAILED)
        handle.done.set()

    # -- CP5: the sandbox spine's terminal states --------------------------

    def _sweep_sandbox_copies(self, *, exclude: str) -> None:
        """R-11's sweep, once per server, before its first sandbox job."""
        if self._sandbox_swept:
            return
        self._sandbox_swept = True
        from ..sandbox import workdir

        live = [h.run_id for h in self._runs.values() if not h.is_terminal] + [exclude]
        try:
            workdir.sweep(live)
        except Exception as exc:  # noqa: BLE001 -- a sweep never fails a run
            _log.warning("Sandbox copy sweep failed: %s", exc)

    @staticmethod
    async def _finalize_sandbox(handle: RunHandle) -> None:
        """Fold a sandbox run's script outcome into its record. Never raises."""
        if handle.sandbox_client is None:
            return
        try:
            await handle.sandbox_client.finalize()
        except Exception as exc:  # noqa: BLE001 -- the run's own outcome stands
            _log.warning("Sandbox run %s could not be finalized: %s", handle.run_id, exc)

    @staticmethod
    def _sandbox_failure_detail(handle: RunHandle, exc: Exception) -> Optional[dict[str, Any]]:
        """The error detail a sandbox failure is re-emitted with (CP5
        contracts/tools.md section 3 step 8; section 4 field order).

          parser_timeout      timeout_seconds, words_completed, run_id, hint
          parser_job_failed   state_at_failure, failure ("crashed"),
                              words_completed, words_total, run_id, log_path,
                              then `load_error` (hc's line) on a start failure
          parser_config_failed / parser_engine_mismatch
                              the client's detail, `run_id` filled in

        A failure with none of these codes (a bug in the client) keeps no
        detail and surfaces through `error_type`, like any other run.
        """
        code = getattr(exc, "error_code", None)
        facts = dict(getattr(exc, "facts", None) or {})
        if code == "parser_timeout":
            timeout = facts.get("timeout_seconds")
            in_flight = facts.get("in_flight_index")
            where = ""
            if isinstance(in_flight, int) and not isinstance(in_flight, bool):
                where = (
                    f" Word {in_flight + 1} of {handle.words_total} was in flight when "
                    f"it was stopped (meta.sandbox.worker.in_flight_index and in_flight_word)."
                )
            hint = (
                f"The sandbox parse worker did not finish within {timeout} seconds and "
                f"was stopped.{where} {handle.words_completed} completed words are recorded "
                f"and readable with flextools_parse_log. Raise timeout_seconds or send "
                f"fewer words; flextools_grammar_health shows what the grammar costs."
            )
            return {
                "error_code": "parser_timeout",
                "timeout_seconds": timeout,
                "words_completed": handle.words_completed,
                "run_id": handle.run_id,
                "hint": hint,
            }
        if code == "parser_job_failed":
            detail = {
                "error_code": "parser_job_failed",
                "state_at_failure": handle.stage.value,
                "failure": facts.get("failure") or "crashed",
                "words_completed": handle.words_completed,
                "words_total": handle.words_total,
                "run_id": handle.run_id,
                "log_path": str(facts.get("log_path") or handle.record.root),
            }
            if "load_error" in facts:
                # hc's verbatim `Load Error:` / `IO Error:` line: a DATA field
                # the handler passes through (FR-016, FR-044).
                detail["load_error"] = facts["load_error"]
            return detail
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            detail = dict(detail)
            if "run_id" in detail and detail.get("run_id") is None:
                detail["run_id"] = handle.run_id
            return detail
        return None

    def _on_run_message(self, handle: RunHandle, message: dict[str, Any]) -> None:
        """Apply a worker message that belongs to a run rather than a word.

        `interleaved_by` is the one that matters for a caller: without it a
        batch paused by an urgent word looks stalled, and SC-009's "reported
        batch progress accounts for the interleave" has no observable
        (data-model.md section 1).
        """
        kind = message.get("type")
        if kind == "stage":
            stage_value = message.get("stage")
            try:
                stage = RunStage(stage_value)
            except ValueError:
                return
            if stage is not handle.stage and can_transition(handle.stage, stage):
                with contextlib.suppress(InvalidStageTransition):
                    self._set_stage(handle, stage)
        elif kind == "interleaved":
            # Who currently has the worker, or None when this run does.
            # Recorded rather than derived: only the worker knows, and a
            # server-side guess would be wrong exactly when it mattered.
            handle.interleaved_by = message.get("by")
            with contextlib.suppress(Exception):
                handle.record.set_stage(
                    handle.stage, interleaved_by=handle.interleaved_by
                )
        elif kind == "cancelled":
            # #223 follow-up (scenario 6 regression): this used to trust the
            # worker's own `words_completed` counter verbatim. That counter
            # and this run's `handle.results` list are filled from two
            # different code paths over the SAME stream -- a word's
            # `result` message resolves a per-request future (whose
            # `_execute_run` continuation, which appends to
            # `handle.results`/`handle.record` and increments
            # `words_completed`, only *runs* on a later event-loop tick),
            # while `cancelled` is a run-listener message `_dispatch`
            # invokes synchronously, in-line, the moment it is read.
            # `ParseWorkerClient._read_loop` does not force a real
            # scheduler yield between reading two already-buffered lines,
            # so a `result` for the last word and the `cancelled` right
            # behind it can be *read* in order but *applied* out of
            # order: this branch used to run first and stamp
            # `words_completed` with a count that already includes that
            # last word, and then the delayed continuation added 1 more
            # on top -- one word double-counted, so `words_completed`
            # read N+1 while only N results ever reached `handle.record`
            # (live scenario 6: "10 words completed but 9 readable on
            # disk"). `len(handle.results)` is filled by that same
            # continuation, in the same statement group as the record
            # write and the increment this replaces, so it can never
            # race ahead of what is actually on disk: if the last word's
            # continuation has not run yet, this reads one short (correct
            # for what has landed so far) and the continuation's own `+=
            # 1` catches it up when it runs; if it already ran, this
            # matches. Either scheduling order is now correct.
            handle.words_completed = len(handle.results)
        elif kind == "engine_changed":
            # A warning, never a refusal (FR-024). The run carries on and
            # its results stay labelled with the submission engine.
            handle.engine_changed_midjob = True
            handle.engine_now = message.get("engine_now")
            self._persist_progress(handle)
        elif kind == "load_baseline":
            # Keyed to the fingerprint and stored BESIDE it (FR-023, D-3).
            from .fingerprint import fingerprint_key

            baseline = dict(message.get("baseline") or {})
            if handle.scope_fingerprint is not None:
                baseline["scope_fingerprint_key"] = fingerprint_key(
                    handle.scope_fingerprint
                )
            handle.load_error_baseline = baseline
            self._persist_progress(handle)

    # -- cancellation -----------------------------------------------------

    async def cancel_run(self, run_id: str) -> Optional[RunHandle]:
        """Request cancellation. Returns the handle, or None if unknown.

        Sets `cancel_requested` and asks the worker; it does **not** make
        the run terminal. The run becomes `cancelled` only when the worker
        has actually stopped at a word boundary, which is what keeps
        partial results readable and honest (FR-032, FR-029).

        A run already terminal raises `RunAlreadyTerminal`, which carries
        the `parse_job_cancelled` payload (FR-036). Raised here rather than
        left to each caller so the refusal cannot be forgotten at one call
        site and issued at another.

        Note the asymmetry this does NOT create: *asking* after a terminal
        run stays a successful query. `flextools_parse_status` never calls
        this method.
        """
        handle = self._runs.get(run_id)
        if handle is None:
            return None
        if handle.is_terminal:
            # FR-036: a cancel against a run that has already ended is
            # `parse_job_cancelled`, carrying what survived. Raised rather
            # than returned quietly, because "cancelled successfully" for a
            # run that ended ten minutes ago tells the caller something
            # false about what just happened.
            raise RunAlreadyTerminal(handle)

        handle.cancel_requested = True
        if handle.queue is not None:
            # Words not yet sent are dropped here, at the server's own
            # boundary; the one in flight finishes (FR-032).
            handle.queue.cancel_run(run_id)
        with contextlib.suppress(WorkerError, Exception):
            worker = await self._worker_for(handle)
            await worker.cancel_run(run_id)
        return handle

    async def terminate_run(self, run_id: str, *, wait: float = 10.0) -> Optional[RunHandle]:
        """Kill a MEASUREMENT run's worker outright (FR-052, D-4).

        Cooperative cancellation cannot bound a one-word parse: it lands at
        the next word boundary, which is after the parse. So the run is
        marked cancel-requested -- which is what makes it end `cancelled`
        rather than `failed` when its in-flight word comes back as a dead
        worker -- and then its worker's process tree is killed.

        Refused for any run in the shared worker. That worker may be holding
        a batch, and this method is the one place that could take it down;
        the refusal makes "the measurement never kills a batch" a property of
        the runner rather than of its callers (FR-051).
        """
        handle = self._runs.get(run_id)
        if handle is None:
            return None
        if handle.worker_role == SHARED_ROLE:
            raise ValueError(
                f"Run {run_id} is in the shared worker; only a measurement run "
                f"may be terminated (FR-051)."
            )
        if handle.is_terminal:
            return handle
        handle.cancel_requested = True
        if handle.queue is not None:
            handle.queue.cancel_run(run_id)
        with contextlib.suppress(Exception):
            await self._pool.terminate(handle.project_name, role=handle.worker_role)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(handle.done.wait()), timeout=wait)
        return handle

    async def release_worker(self, project_name: str, *, role: str) -> None:
        """End one of a project's workers. The measurement's cleanup."""
        with contextlib.suppress(Exception):
            await self._pool.release(project_name, role=role)

    async def release_worker_if_idle(self, project_name: str, *, role: str) -> bool:
        """Release this project's `role` worker, but only if idle, atomically
        (#223 QC P1). See `WorkerPool.release_if_idle` for why the
        check-then-release used to race a run starting in between.

        Returns `False` for a genuine busy refusal (the caller should
        report it); `True` otherwise (released, or nothing was there).
        """
        try:
            return await self._pool.release_if_idle(
                project_name,
                role=role,
                is_busy=lambda: self.worker_busy(project_name, role=role),
            )
        except Exception:
            # Same fail-open-to-"nothing to release" posture as
            # `release_worker`'s `contextlib.suppress(Exception)`: a
            # release that could not complete must not be mistaken for a
            # busy refusal by its caller.
            return True

    async def worker(self, project_name: str, *, role: str = SHARED_ROLE):
        """The worker for a project and role, started if necessary."""
        if role == SHARED_ROLE:
            return await self._pool.get(project_name)
        return await self._pool.get(project_name, role=role)

    async def _worker_for(self, handle: RunHandle):
        if handle.sandbox_client is not None:
            # CP5: the run's own client, never a pooled worker (F-13).
            return handle.sandbox_client
        return await self.worker(handle.project_name, role=handle.worker_role)

    def _peek_worker(self, handle: RunHandle):
        if handle.sandbox_client is not None:
            return handle.sandbox_client
        if handle.worker_role == SHARED_ROLE:
            return self._pool.peek(handle.project_name)
        return self._pool.peek(handle.project_name, role=handle.worker_role)

    async def aclose(self) -> None:
        """Reap every worker. The runs' records are already on disk."""
        await self._pool.aclose()
