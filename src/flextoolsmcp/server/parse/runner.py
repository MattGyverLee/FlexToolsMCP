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
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from .priority import DEFAULT_SINGLE_WORD_PRIORITY, Priority
from .record import RunRecord
from .stages import (
    InvalidStageTransition,
    RunStage,
    can_transition,
    is_terminal,
)
from .worker_client import WorkerError, WorkerPool

__all__ = [
    "DEFAULT_GRACE_WINDOW_SECONDS",
    "RunFailure",
    "RunHandle",
    "RunAlreadyTerminal",
    "ParseRunner",
]

_log = logging.getLogger(__name__)

#: FR-028's default. A *starting value*, configurable, and explicitly not a
#: timeout -- see the module docstring.
DEFAULT_GRACE_WINDOW_SECONDS = 5.0

_ENV_GRACE_WINDOW = "FLEXTOOLSMCP_PARSE_GRACE_WINDOW"

#: What a failed run points a caller at. Named instruments, never "retry"
#: (FR-034).
_FAILURE_NEXT_STEP = (
    "Run flextools_health for the environment and flextools_grammar_health "
    "for this project's grammar. A run that failed while loading the grammar "
    "has usually exhausted memory, and repeating the run repeats the step "
    "that exhausted it -- the diagnostics say what the project needs."
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

    @property
    def is_terminal(self) -> bool:
        return is_terminal(self.stage)


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

    # -- introspection ----------------------------------------------------

    @property
    def grace_window(self) -> float:
        return self._grace_window

    @property
    def pool(self):
        """The worker pool. Exposed for the one caller that needs a worker
        WITHOUT starting a run: the morph resolver, which must reach the
        lexicon before any parse is enqueued (FR-019)."""
        return self._pool

    def get(self, run_id: str) -> Optional[RunHandle]:
        return self._runs.get(run_id)

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
        if stage is not handle.stage and not can_transition(handle.stage, stage):
            raise InvalidStageTransition(handle.stage, stage)
        handle.stage = stage
        for key, value in updates.items():
            setattr(handle, key, value)

        meta_updates: dict[str, Any] = {
            "words_completed": handle.words_completed,
            "words_total": handle.words_total,
            "interleaved_by": handle.interleaved_by,
        }
        if handle.failure is not None:
            meta_updates["failure"] = handle.failure.to_dict()
        if stage is RunStage.CANCELLED:
            meta_updates["stage_at_cancel"] = updates.get(
                "stage_at_cancel", handle.stage.value
            )
        with contextlib.suppress(Exception):
            handle.record.set_stage(stage, **meta_updates)

        if is_terminal(stage):
            handle.done.set()

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
        """
        window = grace_window if grace_window is not None else self._grace_window

        record = RunRecord.create(
            project_name=project_name,
            words_total=len(wordforms),
            record_dir=self._record_dir,
        )
        handle = RunHandle(
            run_id=record.run_id,
            project_name=project_name,
            words_total=len(wordforms),
            record=record,
            priority=priority,
        )
        self._runs[handle.run_id] = handle

        handle.task = asyncio.create_task(
            self._execute_run(handle, wordforms, level, restricted_to)
        )

        # The grace window, in full. Note what is NOT here: no cancel, no
        # deadline handed downstream, no flag set on the run. The only
        # consequence of the window closing is that this `await` ends.
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.shield(handle.done.wait()), timeout=window
            )

        return handle

    async def _execute_run(
        self,
        handle: RunHandle,
        wordforms: list[str],
        level: str,
        restricted_to: Optional[tuple[int, ...]],
    ) -> None:
        """Drive one run to a terminal stage. Never raises.

        Takes no grace-window argument, and must never be given one: the
        window belongs to the caller's side of the conversation. A failure
        here becomes `failed` with a `RunFailure`, because a run that raised
        into a background task and left no stage would be indistinguishable
        from one still running.
        """
        try:
            worker = await self._pool.get(handle.project_name)
            worker.listen_to_run(handle.run_id, lambda m: self._on_run_message(handle, m))

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
            for index, wordform in enumerate(wordforms):
                if handle.cancel_requested:
                    break

                result = await worker.parse_word(
                    request_id=f"{handle.run_id}:{index}:{uuid.uuid4().hex[:8]}",
                    run_id=handle.run_id,
                    wordform=wordform,
                    level=level,
                    restricted_to=restricted_to,
                    priority=int(handle.priority),
                    index_in_run=index,
                )

                # A word came back, so the run is parsing whatever the
                # worker's stage messages did or did not arrive in time to
                # say. Reached from `starting` on the warm path and from
                # `loading_grammar` on the cold one.
                if handle.stage in (RunStage.STARTING, RunStage.LOADING_GRAMMAR):
                    self._set_stage(handle, RunStage.PARSING)

                entry = {
                    "index": index,
                    "wordform": wordform,
                    "parse": result.get("parse"),
                }
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

            if handle.cancel_requested:
                stage_at_cancel = handle.stage.value
                self._set_stage(
                    handle, RunStage.CANCELLED, stage_at_cancel=stage_at_cancel
                )
            else:
                if handle.stage in (RunStage.STARTING, RunStage.LOADING_GRAMMAR):
                    # An empty run still passes through parsing, so the
                    # stage history stays a path through the graph.
                    self._set_stage(handle, RunStage.PARSING)
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
            handle.done.set()
            # Drop the run listener so a long-lived worker does not
            # accumulate one closure per run it has ever served.
            with contextlib.suppress(Exception):
                existing = self._pool.peek(handle.project_name)
                if existing is not None:
                    existing.stop_listening(handle.run_id)

    def _fail(self, handle: RunHandle, exc: Exception) -> None:
        """Record a failure at the stage it happened in."""
        failure = RunFailure(
            message=str(exc),
            stage_at_failure=handle.stage.value,
            error_type=type(exc).__name__,
        )
        detail = getattr(exc, "detail", None)
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
            handle.words_completed = int(
                message.get("words_completed", handle.words_completed)
            )

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
        with contextlib.suppress(WorkerError, Exception):
            worker = await self._pool.get(handle.project_name)
            await worker.cancel_run(run_id)
        return handle

    async def aclose(self) -> None:
        """Reap every worker. The runs' records are already on disk."""
        await self._pool.aclose()
