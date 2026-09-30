"""
`ParseWorker`: one worker, one project, at most one held grammar -- the
queue, the interleave, cancellation and the release-when-idle rule.

Worker-process only: imported by `worker_main.py` (the parse worker) and the
filing worker, never by the MCP server process -- see `worker_main.py`'s
header for why.
"""

from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Optional

from .priority import Priority
from .queue import ParseQueue, QueuedWord
from .stages import RunStage
from .worker_analysis import (
    _SpecView,
)
from .worker_backend import (
    _ParseBackend,
    _StubBackend,
)
from .worker_protocol import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    _POLL_INTERVAL_SECONDS,
    _emit,
    _log,
    loaded_assembly_names,
)
from .worker_sandbox_backend import (
    SANDBOX_REFUSAL_MESSAGE,
    SANDBOX_REFUSED_MESSAGES,
    SandboxJobFailed,
)


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


class ParseWorker:
    """One worker, one project, at most one held grammar at a time.

    #223: the project (and its grammar) is open only while something is
    actually in flight or the queue has not yet gone idle since the last
    request -- see `run()`'s docstring, `_ensure_project_open` and
    `_release_if_idle`. Not "one project, held for the worker's life": that
    was the bug.

    Split deliberately from `main()` so the whole request/response cycle is
    testable in-process against the stub backend without spawning anything.
    `tests/test_parse_worker_lifetime.py` drives this class directly.
    """

    def __init__(
        self,
        project_name: str,
        *,
        backend: Optional[_ParseBackend] = None,
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
        emit=_emit,
    ) -> None:
        self.project_name = project_name
        self._backend = backend if backend is not None else _StubBackend()
        self._idle_timeout = idle_timeout
        self._emit = emit

        self._queue = ParseQueue()
        #: Resolve requests parked by the reader thread for the main loop.
        #: A list plus a lock rather than a Queue because the main loop takes
        #: the whole batch at once: resolves are answered at word boundaries,
        #: and draining them one per boundary would make a four-piece
        #: decomposition wait four words behind a running batch.
        self._resolve_pending: list[dict[str, Any]] = []
        self._resolve_lock = threading.Lock()
        #: The lexicon index, built ONCE and held for the worker's life
        #: (FR-020, SC-007). Held here rather than in the backend so that
        #: "how many times was it built" is answerable in one place.
        self._index = None
        #: The run whose word was served last. Only used to notice when the
        #: worker changes hands, which is what an interleave IS.
        self._current_run: Optional[str] = None
        #: Per-word channel metadata, keyed by (run_id, index_in_run):
        #: the request id to answer and the trace level asked for. Carried
        #: alongside the queue rather than inside `QueuedWord`, because the
        #: queue is a server-side structure shared with CP3 and has no
        #: business knowing about this channel's request ids.
        self._pending_meta: dict[tuple[str, int], dict[str, Any]] = {}
        #: Set by a `shutdown` request. Means "accept no new work and exit
        #: once the queue is empty" -- NOT "stop now". See `run()`.
        self._draining = threading.Event()
        self._stdin_closed = threading.Event()
        #: run_id -> words completed, so a cancellation can report how much
        #: work survived it (FR-032, `parse_job_cancelled`'s detail).
        self._completed: dict[str, int] = {}
        #: Cancelled runs awaiting their `cancelled` line. The queue drops a
        #: cancelled run's words at dequeue, so the report cannot be emitted
        #: from `_parse_one` -- that code never sees them. The main loop
        #: drains this set at a word boundary instead.
        self._cancel_pending: set[str] = set()
        #: Runs already reported as cancelled, so a second cancel for the
        #: same run does not emit a second `cancelled` line.
        self._cancel_reported: set[str] = set()
        self._deadline = time.monotonic() + self._idle_timeout
        self._exit_reason = "shutdown"
        #: CP3 control requests (`engine_check`, `resolve_scope`) parked by
        #: the reader thread. Both touch the project, so -- like resolves --
        #: they are answered on the main loop at a word boundary.
        self._control_pending: list[dict[str, Any]] = []
        #: Runs already told the active engine changed under them. Reported
        #: once per run: the warning is about the run, not about each word.
        self._engine_change_reported: set[str] = set()
        #: The load-error baseline of this worker's most recent grammar load,
        #: and the runs it has been sent to (FR-023). ONE held grammar, so
        #: ONE current baseline: an interleaving word uses the same grammar
        #: and the same baseline (FR-027).
        self._load_baseline: Optional[dict[str, Any]] = None
        self._baseline_sent: set[str] = set()
        #: Run ids the server has opened on the wire but not yet closed with
        #: `run_end`. The runner sends one word at a time and awaits each
        #: result (#235); without this the worker queue is empty between
        #: words of the same run and `_release_if_idle` would drop the
        #: project and reload the grammar for every word.
        self._open_runs: set[str] = set()

    # -- inbound ----------------------------------------------------------

    def handle_message(self, message: dict[str, Any]) -> None:
        """Apply one inbound protocol message.

        Runs on the **reader thread**, so it must stay cheap and must never
        parse: everything here is a queue push or a flag. The parsing
        happens on the main loop, which is what keeps the cancel set
        readable between words rather than only between batches.
        """
        kind = message.get("type")
        self._deadline = time.monotonic() + self._idle_timeout

        if self._backend.SANDBOX and (
            kind in SANDBOX_REFUSED_MESSAGES
            or (kind == "parse" and message.get("restricted_to") is not None)
        ):
            self._emit(
                {
                    "type": "error",
                    "request_id": message.get("request_id"),
                    "run_id": message.get("run_id"),
                    "error_code": None,
                    "detail": None,
                    "message": SANDBOX_REFUSAL_MESSAGE,
                }
            )
            return

        if kind == "parse":
            self._enqueue_parse(message)
        elif kind == "cancel":
            run_id = message.get("run_id")
            if run_id:
                # Drops everything of this run still queued. A word already
                # handed to the main loop finishes -- cancellation is
                # cooperative and lands at the next boundary (FR-032).
                self._queue.cancel_run(run_id)
                # The queue silently discards a cancelled run's words at
                # dequeue, so `_parse_one` will never see one and cannot be
                # the thing that reports the cancellation. The main loop
                # picks this up at the next word boundary instead.
                self._cancel_pending.add(run_id)
        elif kind == "ping":
            self._emit({"type": "pong"})
        elif kind == "resolve":
            # Queued for the MAIN loop, never answered here. This runs on the
            # reader thread, and reading the lexicon means touching the LCM
            # cache -- which the parse loop is also touching. One thread owns
            # the project; that rule is what keeps this worker's behaviour
            # explicable.
            with self._resolve_lock:
                self._resolve_pending.append(message)
        elif kind in (
            "engine_check", "resolve_scope", "parser_parameters",
            # CP4: the filing preflight's three reads (see the protocol notes).
            "agent_probe", "filing_gate", "filing_preview",
        ):
            # Main loop, for the same one-thread-owns-the-project reason.
            with self._resolve_lock:
                self._control_pending.append(message)
        elif kind == "assemblies":
            # A diagnostic, not part of the parse path. It exists so
            # `HCParser_DoesNotLoadXCore` can read the loaded-assembly list
            # of the process that did the parsing; asked from the server
            # process the answer would be about the wrong process.
            self._emit({"type": "assemblies", "names": loaded_assembly_names()})
        elif kind == "run_end":
            run_id = message.get("run_id")
            if run_id:
                self._open_runs.discard(str(run_id))
        elif kind == "shutdown":
            self._exit_reason = "shutdown"
            self._draining.set()
        else:
            self._emit(
                {
                    "type": "error",
                    "request_id": message.get("request_id"),
                    "run_id": message.get("run_id"),
                    "error_code": None,
                    "detail": None,
                    "message": f"Unknown message type {kind!r}.",
                }
            )

    def _enqueue_parse(self, message: dict[str, Any]) -> None:
        restricted = message.get("restricted_to")
        restricted_tuple = tuple(restricted) if restricted else None

        # An empty (rather than absent) restriction is a refusal, never a
        # widening (FR-019, spec.md Delta 2). `ParseQueue.enqueue` rejects
        # it too; catching it here as well means the worker names the
        # wordform in its refusal instead of dying on a ValueError the
        # server would have to reconstruct.
        if restricted is not None and len(restricted) == 0:
            self._emit(
                {
                    "type": "error",
                    "request_id": message.get("request_id"),
                    "run_id": message.get("run_id"),
                    "error_code": "parse_morph_unresolved",
                    "detail": None,
                    "message": (
                        f"Refusing {message.get('wordform')!r}: an empty "
                        f"restriction is a refusal, never a widening to an "
                        f"unrestricted parse (FR-019)."
                    ),
                }
            )
            return

        try:
            priority = Priority(int(message.get("priority", Priority.TRY_A_WORD)))
        except (TypeError, ValueError):
            priority = Priority.TRY_A_WORD

        word = QueuedWord(
            run_id=str(message.get("run_id") or ""),
            wordform=str(message.get("wordform") or ""),
            priority=priority,
            index_in_run=int(message.get("index_in_run", 0) or 0),
            restricted_to=restricted_tuple,
        )
        self._pending_meta[(word.run_id, word.index_in_run)] = {
            "request_id": message.get("request_id"),
            "level": str(message.get("level") or "plain"),
            "vernacular_ws": message.get("vernacular_ws"),
            "engine_at_submission": message.get("engine_at_submission"),
        }
        if word.run_id:
            self._open_runs.add(word.run_id)
        self._queue.enqueue(word)

    # -- the main loop ----------------------------------------------------

    def run(self) -> str:
        """Parse until the queue is drained and the worker is told to stop.

        Returns the exit reason, which `main()` reports as `bye`.

        **`shutdown` drains rather than stops.** A `shutdown` request means
        "accept no more work and exit once what you already accepted is
        done", not "drop it". Dropping would silently lose words the server
        had been told were accepted -- and a silently lost word is the
        failure shape this whole checkpoint exists to prevent. Abandoning
        work is what `cancel` is for, and it is explicit (FR-032).

        That leaves the case of a huge batch delaying teardown, and it is
        already answered a layer up: the server's teardown path kills the
        process tree (`worker_client.py`, issue #57). Graceful drain here,
        hard kill there -- which is the layering data-model.md section 8
        describes rather than one this loop invents.

        Every iteration is a **word boundary**, so cancellations are
        reported here, between words, rather than from `_parse_one` -- the
        queue discards a cancelled run's words at dequeue and `_parse_one`
        never sees them.

        **THE PROJECT (AND ITS LOCK) IS RELEASED AS SOON AS THE QUEUE IS
        EMPTY, NOT ONLY WHEN THE PROCESS EXITS (#223).** Holding
        The project's fwdata lock WHILE a parse is running is fine and
        unchanged -- that is every iteration where `word is not None`. What
        changed is the gap AFTER a request's results are back and BEFORE
        the next one, if any, arrives within `_idle_timeout`: this worker
        used to keep the project (and the lock) open for that whole
        window, up to `DEFAULT_IDLE_TIMEOUT_SECONDS`; it now drops it the
        moment the queue empties (`_release_if_idle`) and reopens on
        demand (`_ensure_project_open`, called from `_parse_one`,
        `_drain_resolves` and `_drain_controls`) if another request lands
        before the PROCESS itself times out. The process still lives out
        `_idle_timeout` so a request in that window reuses the warm
        interpreter/pythonnet bridge; it pays again for `OpenProject()` and
        the first grammar load, which `_ensure_project_open` accounts for
        by invalidating this worker's own caches too (see its docstring).
        """
        while True:
            self._drain_cancellations()
            # Answered at a word boundary, like everything else that is not
            # a parse. One word of latency, never more.
            self._drain_resolves()
            self._drain_controls()

            word = self._queue.dequeue()

            if word is not None:
                self._deadline = time.monotonic() + self._idle_timeout
                self._parse_one(word)
                continue

            # Queue empty and nothing else pending (both drains above are
            # no-ops when they have nothing to answer). Release only when
            # no run is still open on the wire (#235) -- the server sends
            # one word at a time, so the queue is empty between words of a
            # batch even while the run continues.
            self._release_if_idle()

            # Now -- and only now -- is it safe to stop the PROCESS.
            if self._draining.is_set():
                self._exit_reason = "shutdown"
                break
            if self._stdin_closed.is_set():
                # The server hung up. Nothing more can arrive, so there is
                # no point waiting out the idle timeout.
                self._exit_reason = "shutdown"
                break
            if time.monotonic() >= self._deadline:
                self._exit_reason = "idle"
                break
            time.sleep(_POLL_INTERVAL_SECONDS)

        self._drain_cancellations()
        return self._exit_reason

    def _ensure_project_open(self) -> None:
        """Reopen the project if `_release_if_idle` closed it (#223).

        Called before anything actually touches the backend: at the top of
        `_parse_one`, and inside `_drain_resolves` / `_drain_controls` once
        they know they have a pending message to answer. A no-op when the
        project is already open (the common case: most requests land while
        the project never closed at all, e.g. mid-batch).

        Anything THIS worker cached from the closed project is invalid the
        instant it reopens, not just the backend's own state
        (`_RealBackend.release`'s docstring covers `_wordforms_by_ws`):
        `self._index` (`LexiconIndex`, built from `_backend.lexicon_rows()`)
        holds entry/MSA **HVOs**, and an HVO "is a session-scoped handle
        that liblcm renumbers on every cache load" (this module,
        `_batch_parse`'s docstring, issue #103) -- reusing it against a
        newly-opened cache would resolve to the wrong entries, or none.
        `self._load_baseline` describes a specific grammar load that no
        longer exists once the grammar is rebuilt, so it is dropped too
        rather than served stale until the next load overwrites it.
        """
        if self._backend.is_open():
            return
        self._backend.open()
        self._index = None
        self._load_baseline = None

    def _release_if_idle(self) -> None:
        """Drop the project -- and its fwdata lock -- now that nothing is
        in flight (#223), rather than waiting for `_idle_timeout`.

        A no-op when the backend is already closed (checked here rather
        than relying solely on `_RealBackend.release()`'s own idempotence,
        so the common already-idle poll tick does not even call into the
        backend), or when the server still has a run open (#235).
        """
        if self._open_runs:
            return
        if self._backend.is_open():
            self._backend.release()

    def _drain_resolves(self) -> None:
        """Answer every parked resolve request. Runs on the main loop only.

        THE ENGINE GATE RUNS FIRST HERE TOO. Resolving touches the lexicon,
        not the parser area, so FR-015 does not strictly reach it -- but a
        project this tool will refuse to parse should not be quietly
        surveyed either, and running the gate uniformly is one fewer place
        for it to be forgotten. It also means an `XAmple` project refuses
        having done no lexicon work at all.

        A resolve answers with the RESOLUTIONS, not with a verdict. Which
        outcome refuses and what the refusal says is the server's business
        (`handlers/parse/`); this end reports what it found, including the
        candidates it rejected, because those are what make a refusal
        actionable rather than merely final.
        """
        with self._resolve_lock:
            pending, self._resolve_pending = self._resolve_pending, []
        if not pending:
            return
        self._ensure_project_open()

        from .resolver import LexiconIndex, resolve_spec

        for message in pending:
            request_id = message.get("request_id")
            try:
                self._backend.preflight()

                if self._index is None and message.get("only_if_indexed"):
                    # The bounded proposal assist asks this way. FR-021 is a
                    # MAY, and a MAY must never make the caller pay for a
                    # full lexicon walk it did not ask for: on a large
                    # project building the index dominates the call, and a
                    # plain yes/no that silently became a lexicon sweep
                    # would be a worse tool than one that offered nothing.
                    self._emit(
                        {
                            "type": "resolved",
                            "request_id": request_id,
                            "run_id": message.get("run_id"),
                            "resolutions": [],
                            "index_ready": False,
                            "index_entries": 0,
                        }
                    )
                    continue

                if self._index is None:
                    # Once per worker, which is at least once per run and
                    # strictly stronger than SC-007 asks for.
                    self._index = LexiconIndex(self._backend.lexicon_rows())
                    _log(f"lexicon index built: {len(self._index)} entries")

                resolutions = []
                for raw in message.get("morphs") or []:
                    resolution = resolve_spec(_SpecView(raw), self._index)
                    resolutions.append(
                        {
                            "position": _SpecView(raw).position,
                            "outcome": resolution.outcome,
                            "msa_hvos": list(resolution.msa_hvos),
                            "candidates": [
                                c.to_dict() for c in resolution.candidates
                            ],
                            "morph": _SpecView(raw).morph,
                        }
                    )

                self._emit(
                    {
                        "type": "resolved",
                        "request_id": request_id,
                        "run_id": message.get("run_id"),
                        "resolutions": resolutions,
                        "index_ready": True,
                        "index_entries": len(self._index),
                    }
                )
            except Exception as exc:  # noqa: BLE001 -- marshalled below
                self._report_exception(exc, request_id, message.get("run_id"))

    def _drain_controls(self) -> None:
        """Answer parked `engine_check` / `resolve_scope` requests (CP3).

        `engine_check` IS the gate: `preflight()` and nothing else, then the
        engine it passed. The batch handler sends it before anything else it
        asks this worker for, which is what makes FR-024's "first statement
        of the batch handler, before any parser is constructed" true of the
        process that would construct one.

        `resolve_scope` also runs the gate first. It reads texts, not the
        parser area, but a project this tool will refuse to parse should not
        be quietly surveyed -- the same reasoning as `_drain_resolves`.
        """
        with self._resolve_lock:
            pending, self._control_pending = self._control_pending, []
        if not pending:
            return
        self._ensure_project_open()
        for message in pending:
            request_id = message.get("request_id")
            try:
                self._backend.preflight()
                if message.get("type") == "engine_check":
                    self._emit(
                        {
                            "type": "engine",
                            "request_id": request_id,
                            "engine": self._backend.active_engine() or "HC",
                        }
                    )
                elif message.get("type") == "parser_parameters":
                    self._emit(
                        {
                            "type": "parser_parameters",
                            "request_id": request_id,
                            "parameters": self._backend.parser_parameters(),
                        }
                    )
                elif message.get("type") == "agent_probe":
                    self._emit(
                        {"type": "agent", "request_id": request_id,
                         "agent": self._backend.agent_facts()}
                    )
                elif message.get("type") == "filing_gate":
                    self._answer_filing_gate(message)
                elif message.get("type") == "filing_preview":
                    preview = self._backend.filing_preview(
                        list(message.get("words") or []), message.get("vernacular_ws")
                    )
                    self._emit({"type": "filing_preview", "request_id": request_id, **preview})
                else:
                    resolved = self._backend.resolve_scope(dict(message.get("scope") or {}))
                    try:
                        # The one probe (FR-004), read at submission: the
                        # oracle's precondition. A batch writes nothing, so
                        # the state cannot change under the run.
                        state = self._backend.project_state()
                    except Exception as exc:  # noqa: BLE001 -- unknown, not absent
                        _log(f"project-state probe failed: {exc}")
                        state = None
                    self._emit(
                        {
                            "type": "scope_resolved",
                            "request_id": request_id,
                            "resolved": resolved,
                            "project_state": state,
                        }
                    )
            except Exception as exc:  # noqa: BLE001 -- marshalled below
                self._report_exception(exc, request_id, None)

    def _drain_cancellations(self) -> None:
        """Report every run cancelled since the last word boundary.

        **EVERY `parse` REQUEST GETS EXACTLY ONE RESPONSE.** That is a
        protocol invariant, not a nicety, and cancellation is where it is
        easiest to break: the queue discards a cancelled run's words at
        dequeue, so without this they would simply never be answered. The
        server awaits one word at a time, so an unanswered word is not a
        missing line in a log -- it is a permanently hung `await`, a tool
        call that never returns, and a worker that looks alive while the
        run it is serving is frozen.

        So the words that will never run are answered here, at the word
        boundary, with `parse_job_cancelled`. The word already in flight is
        not among them: `_parse_one` popped its metadata before parsing and
        emits its own `result`, so it is answered exactly once too.
        """
        while self._cancel_pending:
            run_id = self._cancel_pending.pop()
            self._answer_orphaned_requests(run_id)
            self._report_cancelled(run_id)

    def _answer_orphaned_requests(self, run_id: str) -> None:
        """Answer every accepted-but-never-run word of a cancelled run."""
        orphaned = [key for key in self._pending_meta if key[0] == run_id]
        for key in orphaned:
            meta = self._pending_meta.pop(key, None)
            if meta is None:
                continue
            self._answer_word_cancelled(meta, run_id)

    def _answer_word_cancelled(self, meta: dict[str, Any], run_id: str) -> None:
        """Resolve ONE word's own per-request future as `parse_job_cancelled`.

        Shared by `_answer_orphaned_requests` (a word never dequeued at
        all) and `_parse_one`'s two in-flight cancellation checks (#223
        scenario 6 -- see there for why the second call site is
        load-bearing, not defensive). Every caller has already popped
        `meta` from `self._pending_meta`, so this is the ONLY place left
        that can still answer that word's `request_id`; skipping it here
        is not "the word is lost, but harmlessly" -- it is a `request_id`
        this worker accepted and will now never answer, which on the
        server side is not a missing result but a permanently hung
        `await` (see `_drain_cancellations`'s docstring for the general
        case this is the specific one of).
        """
        request_id = meta.get("request_id")
        if request_id is None:
            # No caller is waiting on a bare request_id of `None` (the
            # stub default `_parse_one` substitutes when `meta` was
            # already gone) -- nothing to resolve.
            return
        self._emit(
            {
                "type": "error",
                "request_id": request_id,
                "run_id": run_id,
                "error_code": "parse_job_cancelled",
                "detail": None,
                "message": (
                    f"Run {run_id} was cancelled before this word was "
                    f"parsed. Words already completed are unaffected "
                    f"(FR-032)."
                ),
            }
        )

    def _parse_one(self, word: QueuedWord) -> None:
        """Parse one word. THIS IS THE WORD BOUNDARY.

        Cancellation is checked here, before any work, so a run cancelled
        while the previous word was in flight stops without that word being
        lost and without this one starting (FR-032).

        BOTH CHECKS BELOW MUST ANSWER `meta`'S OWN `request_id` (#223
        scenario 6), not just call `_report_cancelled`. `meta` is popped
        from `self._pending_meta` at the top of this method, before either
        check runs -- so a word that reaches either check discovering its
        run already cancelled is answered by NEITHER of this protocol's
        other two paths: `dequeue()` only discards a cancelled run's words
        BEFORE they are handed to `_parse_one` (this word already was), and
        `_answer_orphaned_requests` only finds requests still IN
        `_pending_meta` (this word's entry is already gone). Without
        `_answer_word_cancelled` here, that word's own per-request future
        is never resolved by anything, and the server's `_execute_run` loop
        -- which awaits it one word at a time -- hangs on it forever. Found
        live: `_before_parse` (grammar load / preflight, the longest step)
        is real wall-clock time during which the reader thread can process
        an incoming `cancel` and set `is_cancelled` for THIS run, so the
        SECOND check below is not a defensive extra -- it is the one that
        actually fires under load.
        """
        meta = self._pending_meta.pop(
            (word.run_id, word.index_in_run), {"request_id": None, "level": "plain"}
        )

        if self._queue.is_cancelled(word.run_id):
            self._answer_word_cancelled(meta, word.run_id)
            self._report_cancelled(word.run_id)
            return

        self._note_interleave(word)
        # #223: reopen first if `_release_if_idle` closed the project since
        # the last word -- covers BOTH the gated path (`preflight()` inside
        # `_before_parse`) and the batch path, which skips `preflight()`
        # for a word carrying `engine_at_submission` (see `_before_parse`).
        self._ensure_project_open()

        try:
            load_started = self._before_parse(word, meta)
        except Exception as exc:  # noqa: BLE001 -- marshalled, see below
            self._report_exception(exc, meta.get("request_id"), word.run_id)
            return

        # Re-checked after the grammar load: loading is the longest step in
        # the run, so it is the most likely place for a cancel to arrive.
        # Without this second check a cancelled run would still parse one
        # word after a multi-second load.
        if self._queue.is_cancelled(word.run_id):
            self._answer_word_cancelled(meta, word.run_id)
            self._report_cancelled(word.run_id)
            return

        try:
            outcome = self._backend.parse(
                word.wordform,
                meta.get("level", "plain"),
                word.restricted_to,
                vernacular_ws=meta.get("vernacular_ws"),
            )
        except Exception as exc:  # noqa: BLE001
            self._report_exception(exc, meta.get("request_id"), word.run_id)
            return

        if load_started is not None:
            # This parse paid for the grammar load, so the load-error file
            # on disk is now ours (FR-023). Read it once, here, and hold it
            # as the one current baseline beside the one held grammar.
            self._capture_load_baseline(load_started)
        if meta.get("engine_at_submission") is not None or self._backend.SANDBOX:
            self._send_baseline_once(word.run_id)

        self._completed[word.run_id] = self._completed.get(word.run_id, 0) + 1
        self._emit(
            {
                "type": "result",
                "request_id": meta.get("request_id"),
                "run_id": word.run_id,
                "wordform": word.wordform,
                "index_in_run": word.index_in_run,
                "parse": outcome.get("parse"),
                "trace_xml": outcome.get("trace_xml"),
            }
        )

    def _before_parse(
        self, word: QueuedWord, meta: Optional[dict[str, Any]] = None
    ) -> Optional[float]:
        """The engine gate, THEN the grammar. The order is the requirement.

        `preflight()` is the first statement, before anything touches the
        parser area (FR-015, R-03). It is first here rather than inside
        `ensure_grammar` so that it still runs on the common path where a
        held grammar is reused and no load happens at all -- folded into
        the load, the gate would silently stop running from the second word
        onwards, which is precisely when a user is most likely to have
        flipped the active parser.

        A BATCH WORD IS THE ONE EXCEPTION, and it is FR-024's own: for a
        batch the gate fires once, at submission (`engine_check`), and an
        engine change mid-job is a warning on the run, not a refusal. So a
        word carrying `engine_at_submission` observes the engine instead of
        gating on it. Every other word -- `try_word`'s, an interleaving one
        -- still runs the gate first.

        Returns the wall-clock time a grammar load began, or None when the
        held grammar was reused. The caller reads the load-error baseline
        only after a parse that actually paid for a load.
        """
        engine_at_submission = (meta or {}).get("engine_at_submission")
        if engine_at_submission is None:
            self._backend.preflight()
        else:
            self._observe_engine(word.run_id, engine_at_submission)

        load_started = time.time()
        loaded = self._backend.ensure_grammar(word.run_id)
        if loaded:
            self._emit(
                {
                    "type": "stage",
                    "run_id": word.run_id,
                    "stage": RunStage.LOADING_GRAMMAR.value,
                }
            )
        self._emit(
            {
                "type": "stage",
                "run_id": word.run_id,
                "stage": RunStage.PARSING.value,
            }
        )
        return load_started if loaded else None

    def _observe_engine(self, run_id: str, engine_at_submission: str) -> None:
        """Warn a batch, once, if the active engine is not the one it began on.

        A read, not the gate: nothing here raises, and the word goes on to
        be parsed. The results stay labelled with the submission engine,
        which is the one the run was admitted under (FR-024).
        """
        if run_id in self._engine_change_reported:
            return
        engine_now = self._backend.active_engine()
        if engine_now is None or engine_now == engine_at_submission:
            return
        self._engine_change_reported.add(run_id)
        self._emit(
            {
                "type": "engine_changed",
                "run_id": run_id,
                "engine_at_submission": engine_at_submission,
                "engine_now": engine_now,
            }
        )

    def _answer_filing_gate(self, message: dict[str, Any]) -> None:
        """The refuse-to-file gate's inputs (CP4 FR-020..FR-023, FR-039).

        Makes the grammar current (paying a load if it was stale or never
        loaded), probes whether the parser could be built, and reports THIS
        worker's own load-error baseline -- read from the file its own load
        wrote, never FLEx's copy by itself (FR-023) -- with the eligible
        forms. The VERDICT is not computed here: the gate compares these
        against the run records' baseline server-side (`filing/gate.py`).
        """
        load_started, morpher_null = self._backend.gate_probe(
            message.get("probe_word"), message.get("vernacular_ws")
        )
        if load_started is not None:
            self._capture_load_baseline(load_started)
        load = dict(self._load_baseline) if self._load_baseline is not None else {
            "captured": False, "errors": [],
            "reason": "no grammar load has been observed by this worker",
        }
        load.pop("eligible_entries", None)
        self._emit(
            {
                "type": "filing_gate",
                "request_id": message.get("request_id"),
                "morpher_null": bool(morpher_null),
                "load": load,
                "eligible": self._backend.eligible_entries(),
            }
        )

    def _capture_load_baseline(self, load_started: float) -> None:
        """Read the load-error file OUR load just wrote (FR-023). Never raises."""
        try:
            self._load_baseline = self._backend.load_error_baseline(load_started)
        except Exception as exc:  # noqa: BLE001 -- a baseline must not fail a word
            self._load_baseline = {
                "captured": False, "errors": [],
                "reason": f"{type(exc).__name__}: {exc}",
            }

    def _send_baseline_once(self, run_id: str) -> None:
        """Hand a batch the current load-error baseline, once.

        A batch that begins on a warm worker paid no load of its own; the
        baseline it records is that of the grammar it is actually parsing
        with, which is the held one (FR-027). Recording nothing would leave
        CP4's gate with no baseline to compare against for exactly the runs
        that were cheapest to start.

        CP4 (FR-039, additive): a batch's baseline also records the entries
        whose forms can reach that grammar -- `eligible_entries`, read once
        per grammar load and only for a batch, so a single word never pays
        for the lexicon walk. That is what lets a read-only run re-baseline
        BOTH halves of the refuse-to-file gate (FR-021).
        """
        if run_id in self._baseline_sent or self._load_baseline is None:
            return
        if "eligible_entries" not in self._load_baseline:
            eligible = self._backend.eligible_entries()
            if eligible.get("known"):
                self._load_baseline["eligible_entries"] = list(eligible.get("entries") or [])
        self._baseline_sent.add(run_id)
        self._emit(
            {"type": "load_baseline", "run_id": run_id, "baseline": self._load_baseline}
        )

    # -- outbound helpers -------------------------------------------------

    def _note_interleave(self, word: QueuedWord) -> None:
        """Announce a change of hands, so a paused batch does not look stalled.

        THE INTERLEAVE IS A QUEUE-JUMP, NOT PREEMPTION (FR-031). Nothing
        here stops, restarts or rewinds the running batch: a
        higher-priority word simply wins the next `dequeue()`, which is a
        word boundary. The batch keeps its position, loses no work, and the
        grammar is not reloaded -- all three because nothing about the
        batch is touched at all.

        What WOULD go wrong without this notice is purely a reporting
        failure, and a bad one: a caller polling their batch during an
        interleave sees `words_completed` stop advancing with no
        explanation, concludes the run has hung, and cancels it. So the
        displaced run is told who has the worker, and told again when it
        gets it back. That pair is SC-009's "reported batch progress
        accounts for the interleave" -- without it the criterion has no
        observable (data-model.md section 1).

        Only emitted when the run actually CHANGES. A batch running
        uninterrupted emits nothing, which keeps the channel quiet in the
        common case.
        """
        previous = self._current_run
        current = word.run_id
        if previous == current:
            return
        self._current_run = current

        # The run that just lost the worker -- but only if it still has
        # work pending. A run whose last word simply finished has not been
        # interleaved with; it is done.
        if previous is not None and self._queue.pending_count(previous):
            self._emit(
                {"type": "interleaved", "run_id": previous, "by": current}
            )

        # The run that just got the worker is, by definition, waiting on
        # nobody. Clearing is as important as setting: a stale
        # `interleaved_by` would tell a caller their finished run is still
        # queued behind someone.
        self._emit({"type": "interleaved", "run_id": current, "by": None})

    def _report_cancelled(self, run_id: str) -> None:
        """Announce a cancelled run once, carrying what survived it."""
        if run_id in self._cancel_reported:
            return
        self._cancel_reported.add(run_id)
        self._emit(
            {
                "type": "cancelled",
                "run_id": run_id,
                "words_completed": self._completed.get(run_id, 0),
            }
        )

    def _report_exception(
        self, exc: Exception, request_id: Optional[str], run_id: Optional[str]
    ) -> None:
        """Marshal a worker-side exception back over the channel.

        An engine mismatch carries its `detail` dict through **unchanged**,
        because `ParserEngineMismatchError.detail` is already shaped exactly
        like `response_models.ParserEngineMismatchDetail`. Reshaping it here
        would be the place the field names quietly drift (R-03).
        """
        detail = getattr(exc, "detail", None)
        error_code = getattr(exc, "error_code", None)
        if isinstance(detail, dict):
            error_code = detail.get("error_code", error_code)
        else:
            detail = None

        _log(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
        self._emit(
            {
                "type": "error",
                "request_id": request_id,
                "run_id": run_id,
                "error_code": error_code,
                "detail": detail,
                "message": (
                    str(exc) if isinstance(exc, SandboxJobFailed)
                    else f"{type(exc).__name__}: {exc}"
                ),
            }
        )

    # -- teardown ---------------------------------------------------------

    def release(self) -> None:
        """Drop the grammar and the project. Safe to call twice."""
        try:
            self._backend.release()
        except Exception as exc:  # noqa: BLE001
            _log(f"backend release failed: {type(exc).__name__}: {exc}")
