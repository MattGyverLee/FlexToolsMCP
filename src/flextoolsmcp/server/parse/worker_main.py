#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The long-lived parse worker (parser-check CP2b, FR-031/FR-032/FR-042/FR-043;
research.md R-02/R-03; data-model.md section 8).

**THE MCP SERVER PROCESS MUST NEVER IMPORT THIS MODULE.** It opens a
project, holds an LCM cache, lives inside pythonnet and keeps a loaded
grammar alive for its whole lifetime. Importing it server-side would pull
every one of those into the server and destroy the ownership boundary this
package exists to express. It is addressed by **dotted module path** and
launched as a child process, exactly the way `run_scan_module` addresses
`scan/grammar_scan_module.py`:

    python -m flextoolsmcp.server.parse.worker_main --project "<name>"

WHY THIS PROCESS EXISTS AT ALL. Every other project-touching operation in
this repository runs in a one-shot child that opens a project, does one
thing and dies. That model cannot satisfy this checkpoint. FR-042 requires a
*held* loaded grammar; FR-031 requires an urgent word to interleave at the
running batch's next word boundary with the grammar loaded **exactly once**
for both; FR-043 requires the held grammar's currency to be confirmed before
every reuse. A process that dies after one call holds nothing, has no
boundary to interleave at, and has no "reuse" to confirm currency for. So
the worker is long-lived -- not because long-lived is nicer, but because
every alternative forfeits a requirement outright (research.md R-02).

WHAT THAT COSTS, STATED UP FRONT. A long-lived pythonnet process holding a
`.fwdata` lock is issue #57's known failure made worse: the orphan window is
now the worker's whole lifetime rather than one call. Two mechanisms answer
that and both are load-bearing rather than belt-and-braces:

  * an **idle timeout** -- the worker closes the project and exits on its
    own once it has been idle long enough, so a server that forgets about it
    does not leave a lock held indefinitely;
  * **server-side teardown** through the existing `_kill_process_tree` path
    (`worker_client.py`), so shutdown reaches pythonnet grandchildren too.

THE CHANNEL. Line-delimited JSON, one object per line, over stdin/stdout.

  **stdout is the protocol and nothing else.** Any stray `print()` in this
  process or in a library it calls corrupts the channel, because the reader
  on the other side parses every line. Diagnostics go to **stderr**, which
  the server drains separately. This is why `_emit` is the only writer to
  stdout in the module and why `_log` exists at all.

Requests (stdin):

    {"type": "parse",  "request_id": str, "run_id": str, "wordform": str,
     "level": "plain"|"restricted"|"explain",
     "restricted_to": [int, ...] | null,
     "priority": int, "index_in_run": int}
    {"type": "cancel", "run_id": str}
    {"type": "ping"}
    {"type": "shutdown"}

  CP3 additions (additive; protocol stays 1):

    {"type": "parse", ..., "level": "batch", "vernacular_ws": str,
     "engine_at_submission": str}
        -- one word of a batch. `engine_at_submission` says the engine gate
           already ran, ONCE, at submission (FR-024); this word therefore
           observes the active engine rather than re-running the gate, and a
           change is reported as `engine_changed`, never as a refusal.
    {"type": "engine_check", "request_id": str}
        -- the engine gate on its own, before any scope is resolved or any
           parse is queued. It is the batch handler's first project-touching
           statement (FR-024).
    {"type": "resolve_scope", "request_id": str, "scope": {...}}
        -- scope resolution (US1). No parse: it reads texts and wordforms.
    {"type": "parser_parameters", "request_id": str}
        -- the stored parser parameters, READ as context for a slow parse
           (US6, FR-055). Never written: CP3 has no project-data write.

  CP4 additions (additive; protocol stays 1) -- the FILING preflight's three
  questions. Each is a READ, asked only by the filing handler, and answered
  from `server/filing/preflight_reads.py` (the read spine itself still
  resolves no agent and files nothing):

    {"type": "agent_probe", "request_id": str}
        -- is the HermitCrab parser agent resolvable? (FR-025)
    {"type": "filing_gate", "request_id": str, "probe_word": str,
     "vernacular_ws"?: str}
        -- a current grammar, THIS load's errors, whether the parser could
           be built at all (a probe parse), and the forms eligible to reach
           the grammar (FR-020..FR-023, FR-039).
    {"type": "filing_preview", "request_id": str, "words": [str],
     "vernacular_ws"?: str}
        -- every stored analysis of every word, with its user opinion and its
           segment use through a FRESH join (FR-011..FR-015, R-02).

Responses (stdout):

    {"type": "ready",     "protocol": 1, "project": str, "pid": int}
        `pid` is THIS process's own id -- the one LCM records as the holder
        of the project it opens. On Windows a venv's python.exe is a launcher
        whose child is the real interpreter, so the id the server spawned is
        not it (CP4 L-0).
    {"type": "stage",     "run_id": str, "stage": "loading_grammar"|"parsing"}
    {"type": "result",    "request_id": str, "run_id": str, "wordform": str,
                          "index_in_run": int, "parse": {...},
                          "trace_xml": str|null}

    `parse` is never null as of CP2b's honesty-gap fix: every level derives
    it from the same document, and its keys tell the caller which question
    was asked and answered (`_summarize_trace`, below).

      plain / explain -> {"parsed": bool, "analysis_count": int}
      restricted       -> {"hypothesis_held": bool, "restricted_analysis_count": int}
      batch            -> {"parsed", "analysis_count", "analyses": [...],
                           "human_analyses": [...], "error_message",
                           "parse_time_ms"} -- from the TYPED structured
                           result, never the document (FR-035, R-11)
      any level, on <Error> -> {"parse_error": str} instead of the above --
        the parse threw, so nothing about it parsing or not is asserted.
    {"type": "engine",        "request_id": str, "engine": str}
    {"type": "scope_resolved", "request_id": str, "resolved": {...}}
    {"type": "parser_parameters", "request_id": str, "parameters": {...}|null}
    {"type": "agent",          "request_id": str, "agent": {...}}
    {"type": "filing_gate",    "request_id": str, "morpher_null": bool,
                               "load": {...}, "eligible": {"known": bool,
                               "entries": [{"entry_guid", "headword"}]}}
    {"type": "filing_preview", "request_id": str, "words": {...},
                               "join_known": bool}
    {"type": "engine_changed", "run_id": str, "engine_at_submission": str,
                               "engine_now": str|null}
    {"type": "load_baseline",  "run_id": str, "baseline": {...}}
    {"type": "cancelled", "run_id": str, "words_completed": int}
    {"type": "error",     "request_id": str|null, "run_id": str|null,
                          "error_code": str|null, "detail": {...}|null,
                          "message": str}
    {"type": "pong"}
    {"type": "bye", "reason": "shutdown"|"idle"}

WHY THERE IS A READER THREAD. Cancellation must be observed **at a word
boundary** (FR-032), and an urgent word must overtake a queued batch
(FR-031). Both require the worker to learn about a message that arrives
*while it is busy parsing*. A single loop that blocked on `readline()` and
then parsed would only ever see a cancel after it had already drained the
queue -- which is to say, never in the case that matters. So a daemon reader
thread owns stdin and feeds an in-process `ParseQueue`; the main loop pops
one word at a time and checks the cancel set **between words**. The boundary
is therefore a real consequence of the structure, not a promise in a
comment.

WHY THE QUEUE IS DUPLICATED HERE. The server has a `ParseQueue` too. This is
not redundancy: the server's queue orders work it has not yet handed over,
and this one orders work already in flight in the worker. A word can only
overtake another word that is on the same side of the pipe, so the interleave
FR-031 describes happens here, in the worker's own queue. Both use the same
`ParseQueue` class so the ordering semantics cannot drift apart.

THE HELD GRAMMAR IS ONE SLOT. `_GrammarSlot` holds at most one loaded
grammar and confirms `IsUpToDate()` before **every** reuse (FR-043). A
reload is `Reload()` -- which the facade defines as reset **then** update,
two steps (SC-014). The slot is released when the project is released.

THE ENGINE GATE RUNS FIRST. `check_active_parser(project,
supported_engines=("HC",))` is the first statement of the request handler,
before any parser area is touched (FR-015, R-03). It lives here rather than
in the server because it reads `project.MorphologicalDataOA.ActiveParser`,
which needs an open project -- and by R-02 an open project exists only in
this process. It is re-read live on every request and never memoized,
because a user can flip the active parser mid-session.

STUB-FIRST, BY SCHEDULE. This module ships with a **stub** parse backend
(T021) and is pointed at the real `flexicon.ParserOperations` facade in a
separate, later task (T026). That ordering is deliberate: the queue, the
interleave, the cancellation boundary and the run record are proven against
a backend that cannot fail for parser reasons, so a queue defect and a
parser defect can never be mistaken for one another (plan.md Phase C). The
seam is `_ParseBackend`; the real one arrives beside the stub, it does not
replace this file.

WHERE THE PIECES LIVE (#298). This module is the process entry point; the
worker itself is split across sibling modules, all worker-process only:

    worker_protocol.py         protocol constants, `_emit`, `_log`
    worker_backend.py          the `_ParseBackend` seam and `_StubBackend`
    worker_real_backend.py     `_RealBackend` (flexicon's ParserOperations)
    worker_analysis.py         reducing parser results to channel data
    worker_sandbox_backend.py  `_SandboxBackend` (bundled HermitCrab, CP5)
    worker_loop.py             `ParseWorker`

None of them imports this module: it runs as `__main__`, and a second import
under its dotted name would build a second copy of it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import traceback
from typing import Optional

from .worker_backend import _ParseBackend, _StubBackend
from .worker_loop import ParseWorker
from .worker_protocol import (
    _ENV_IDLE_TIMEOUT,
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    PROTOCOL_VERSION,
    _emit,
    _force_utf8_stdio,
    _log,
)
from .worker_real_backend import _RealBackend
from .worker_sandbox_backend import _SandboxBackend, _StubSandboxBackend

# The worker's pieces live in the worker_*.py modules beside this one (#298);
# these names stay importable from here, the module every caller and test
# already addresses.
from .worker_analysis import _structured_analysis, _summarize_trace  # noqa: F401
from .worker_protocol import loaded_assembly_names  # noqa: F401
from .worker_real_backend import (  # noqa: F401
    ParserUnavailableError,
    headless_ui_kwargs,
)
from .worker_sandbox_backend import (  # noqa: F401
    SANDBOX_REFUSAL_MESSAGE,
    SANDBOX_REFUSED_MESSAGES,
)

__all__ = [
    "PROTOCOL_VERSION",
    "DEFAULT_IDLE_TIMEOUT_SECONDS",
    "ParseWorker",
    "loaded_assembly_names",
    "main",
]


# ---------------------------------------------------------------------------
# Process entry point
# ---------------------------------------------------------------------------


def _reader_thread(worker: ParseWorker, stream=None) -> None:
    """Own stdin; feed the worker. Daemon, so it never blocks exit.

    A malformed line is reported and skipped rather than fatal: one bad
    line from a future protocol version must not take down a worker that is
    mid-batch and holding a grammar.
    """
    stream = stream if stream is not None else sys.stdin
    try:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                _log(f"unparseable line skipped: {exc}")
                continue
            if not isinstance(message, dict):
                _log(f"non-object message skipped: {message!r}")
                continue
            try:
                worker.handle_message(message)
            except Exception as exc:  # noqa: BLE001
                _log(f"handle_message failed: {type(exc).__name__}: {exc}")
    finally:
        worker._stdin_closed.set()


def _idle_timeout_from_env(default: float) -> float:
    raw = os.environ.get(_ENV_IDLE_TIMEOUT)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        _log(f"ignoring unparseable {_ENV_IDLE_TIMEOUT}={raw!r}")
        return default


def main(argv: Optional[list[str]] = None) -> int:
    """Run one worker until shutdown, stdin close, or idle timeout."""
    _force_utf8_stdio()

    parser = argparse.ArgumentParser(
        prog="flextoolsmcp.server.parse.worker_main",
        description="Long-lived FLEx parse worker (one per project).",
    )
    parser.add_argument(
        "--project",
        default=None,
        help=(
            "FieldWorks project name. Opened writeEnabled=False. Required "
            "unless --sandbox, where it is a diagnostic label only and no "
            "project is opened."
        ),
    )
    # CP5 (contracts/sandbox-worker.md section 1): parse an exported
    # HermitCrab config with no project, no LCM and no flexicon.
    parser.add_argument("--sandbox", action="store_true",
                        help="Sandbox mode: parse --config, open no project.")
    parser.add_argument("--config", default=None,
                        help="--sandbox: the hc-config.xml to load (lazily, at the first parse).")
    parser.add_argument("--hc-params", default=None,
                        help="--sandbox: JSON file of the resolved Morpher parameters (D3).")
    parser.add_argument("--id-map", default=None,
                        help="--sandbox: the config source's lcm-ids.json (FR-050).")
    parser.add_argument("--engine-dir", default=None,
                        help="--sandbox: the FieldWorks folder holding the HermitCrab engine.")
    parser.add_argument("--named-sandbox", action="store_true",
                        help="--sandbox: the config is a user-edited named sandbox (FR-050 rule a).")
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=None,
        help=(
            "Seconds of inactivity before this PROCESS exits (#223: the "
            "project, and its lock, is released as soon as the queue is "
            "idle, not only at process exit -- this bounds how long the "
            "warm process is kept around for a later request). "
            f"Default {DEFAULT_IDLE_TIMEOUT_SECONDS}s, or ${_ENV_IDLE_TIMEOUT}."
        ),
    )
    parser.add_argument(
        "--stub",
        action="store_true",
        help=(
            "Use the stub parse backend: no project is opened and no parser "
            "is constructed. This is how the queue, interleave, cancellation "
            "and record machinery are proven without FieldWorks (plan.md "
            "Phase C)."
        ),
    )
    parser.add_argument(
        "--parse-delay",
        type=float,
        default=0.0,
        help=(
            "Seconds the STUB backend spends per word. Ignored without "
            "--stub. Exists because a zero-cost parse has no word boundary "
            "to observe: an interleave or a cancellation test needs the "
            "batch to still be running when the second message arrives. "
            "Part of the stub, which is scaffolding by design -- the real "
            "backend takes its timing from the parser."
        ),
    )
    args = parser.parse_args(argv)
    if args.sandbox:
        if not args.config:
            parser.error("--sandbox requires --config")
    elif not args.project:
        parser.error("--project is required")

    idle_timeout = (
        args.idle_timeout
        if args.idle_timeout is not None
        else _idle_timeout_from_env(DEFAULT_IDLE_TIMEOUT_SECONDS)
    )

    backend: _ParseBackend
    if args.sandbox:
        sandbox_kwargs = {
            "hc_params_path": args.hc_params,
            "id_map_path": args.id_map,
            "engine_dir": args.engine_dir,
            "named_sandbox": args.named_sandbox,
        }
        if args.stub:
            backend = _StubSandboxBackend(
                args.config, parse_seconds=args.parse_delay, **sandbox_kwargs
            )
        else:
            backend = _SandboxBackend(args.config, **sandbox_kwargs)
    elif args.stub:
        backend = _StubBackend(parse_seconds=args.parse_delay)
    else:
        backend = _RealBackend(args.project)
        try:
            backend.open()
        except Exception as exc:  # noqa: BLE001
            # Opening the project is the one failure that must be reported
            # before `ready`: the server waits for that handshake, and a
            # worker that never sends it would otherwise surface as a
            # startup timeout naming nothing.
            _log(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            _emit(
                {
                    "type": "error",
                    "request_id": None,
                    "run_id": None,
                    "error_code": None,
                    "detail": None,
                    "message": (
                        f"Failed to open project {args.project!r}: "
                        f"{type(exc).__name__}: {exc}"
                    ),
                }
            )
            return 2

    worker = ParseWorker(args.project, backend=backend, idle_timeout=idle_timeout)

    # `ready` is emitted BEFORE the reader thread starts, so it is always
    # the first line on the wire. Started first, the reader can answer a
    # request that is already buffered in the pipe and put its response
    # ahead of the handshake -- which a server reading `ready` as the first
    # line would then never match.
    _emit({"type": "ready", "protocol": PROTOCOL_VERSION, "project": args.project,
           "pid": os.getpid()})

    reader = threading.Thread(
        target=_reader_thread, args=(worker,), name="parse-worker-stdin", daemon=True
    )
    reader.start()

    try:
        reason = worker.run()
    finally:
        worker.release()

    _emit({"type": "bye", "reason": reason})
    return 0


if __name__ == "__main__":
    sys.exit(main())
