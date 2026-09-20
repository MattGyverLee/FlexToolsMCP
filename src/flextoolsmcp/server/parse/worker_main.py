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

Responses (stdout):

    {"type": "ready",     "protocol": 1, "project": str}
    {"type": "stage",     "run_id": str, "stage": "loading_grammar"|"parsing"}
    {"type": "result",    "request_id": str, "run_id": str, "wordform": str,
                          "index_in_run": int, "parse": {...}|null,
                          "trace_xml": str|null}
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
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import threading
import time
import traceback
from typing import Any, Optional

from .priority import Priority
from .queue import ParseQueue, QueuedWord
from .stages import RunStage

__all__ = [
    "PROTOCOL_VERSION",
    "DEFAULT_IDLE_TIMEOUT_SECONDS",
    "ParseWorker",
    "loaded_assembly_names",
    "main",
]

#: Bumped only on a breaking change to the message shapes above. The server
#: refuses a worker whose protocol it does not know rather than guessing.
PROTOCOL_VERSION = 1

#: How long the worker sits idle before releasing the project and exiting.
#: Generous enough that a linguist thinking between words does not pay a
#: grammar reload, short enough that a forgotten worker does not hold a
#: `.fwdata` lock for the rest of the day (issue #57).
DEFAULT_IDLE_TIMEOUT_SECONDS = 600.0

_ENV_IDLE_TIMEOUT = "FLEXTOOLSMCP_PARSE_WORKER_IDLE_TIMEOUT"

#: How long the main loop blocks waiting for work before re-checking the
#: idle deadline and the shutdown flag. Small enough to be responsive,
#: large enough not to spin a core.
_POLL_INTERVAL_SECONDS = 0.05


# ---------------------------------------------------------------------------
# stdout is the protocol. Everything else goes to stderr.
# ---------------------------------------------------------------------------

_EMIT_LOCK = threading.Lock()


def _force_utf8_stdio() -> None:
    """Put this process's stdio on UTF-8, whatever the console says.

    THIS IS NOT COSMETIC. On Windows `sys.stdout` defaults to the console
    codepage (cp1252 here), so a wordform or a trace containing a character
    outside that codepage is **silently replaced** on its way across the
    channel -- the first live run of this worker produced a U+FFFD in an
    Indonesian trace for exactly this reason. For a tool whose entire
    subject matter is minority-language orthographies, a stdio encoding
    that quietly mangles non-Latin text is a correctness bug, not a
    configuration detail.

    Called before anything is written, and paired with `ensure_ascii=True`
    on the wire (see `_emit`): the two are deliberate belt and braces,
    because they fail in different places. `ensure_ascii` protects the
    protocol; this protects the diagnostics on stderr, which carry
    arbitrary text and are the only record of a failure between messages.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _emit(message: dict[str, Any]) -> None:
    """Write one protocol line to stdout and flush it.

    The ONLY writer to stdout in this process. The flush is not an
    optimization: the server is reading line by line and a buffered
    response is indistinguishable from a hung worker.

    `ensure_ascii=True` so the wire is pure ASCII regardless of what any
    stdio layer on either side believes the encoding to be. JSON escapes
    non-ASCII as `\\uXXXX`, which survives every codepage; the far side
    decodes it back to the original characters. It costs a few bytes on
    non-Latin text and removes a whole class of platform-dependent
    corruption.
    """
    line = json.dumps(message, ensure_ascii=True)
    with _EMIT_LOCK:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _log(message: str) -> None:
    """Diagnostics. stderr, never stdout -- see the module docstring."""
    sys.stderr.write(f"[parse-worker] {message}\n")
    sys.stderr.flush()


def loaded_assembly_names() -> list[str]:
    """Every CLR assembly loaded into THIS process, by simple name.

    Exists for one caller: `HCParser_DoesNotLoadXCore`
    (tests/test_parser_no_xcore.py), which backs the `READ_ONLY_SAFE`
    annotation on the parse tools. That test has to read the list from the
    process that actually parsed -- the server process never loads
    `ParserCore` at all, so asserting there would prove nothing.

    Returns `[]` when pythonnet is not loaded, which is the stub case. The
    test treats an empty list as "could not observe" and skips rather than
    passing: a vacuous green here would retire the one guarantee that makes
    the read-only claim checkable.
    """
    try:
        import clr  # noqa: F401  -- import side effect: starts the CLR bridge
        from System import AppDomain
    except Exception:  # noqa: BLE001 -- no CLR here; see docstring
        return []

    names = []
    for assembly in AppDomain.CurrentDomain.GetAssemblies():
        with contextlib.suppress(Exception):
            names.append(str(assembly.GetName().Name))
    return names


# ---------------------------------------------------------------------------
# The parse backend seam
# ---------------------------------------------------------------------------


class _ParseBackend:
    """What the worker needs from a parser, and nothing more.

    Two implementations: `_StubBackend` and `_RealBackend`. Keeping the
    surface this small is what makes the stub an honest stand-in rather
    than a simplification that hides the parts that will actually be hard.
    """

    def preflight(self) -> None:
        """The engine gate. Called FIRST, before anything else per request.

        Separate from `ensure_grammar` precisely so it cannot drift into
        being second: FR-015 wants nothing in the parser area touched
        before the active engine has been checked, and a gate folded into
        the grammar load would run after the load on any path that reuses
        a held grammar.
        """
        return None

    def ensure_grammar(self, run_id: str) -> bool:
        """Make a current grammar available. True if a load was performed.

        The return value is what lets the caller report `loading_grammar`
        only when a load really happened -- reporting it on every word
        would make the stage meaningless, and reporting it never would hide
        the step that most often exhausts memory (FR-034).
        """
        raise NotImplementedError

    def parse(
        self,
        wordform: str,
        level: str,
        restricted_to: Optional[tuple[int, ...]],
    ) -> dict[str, Any]:
        """Parse one word. Returns `{"parse": ..., "trace_xml": ...}`."""
        raise NotImplementedError

    def lexicon_rows(self) -> list:
        """Every entry, as plain rows the resolver can index (FR-018).

        Plain data, never LCM objects: `LexiconIndex` must hold no reference
        into a cache, and the rows cross no process boundary carrying one.
        """
        raise NotImplementedError

    def release(self) -> None:
        """Drop the held grammar and any project handle."""
        raise NotImplementedError


class _StubBackend(_ParseBackend):
    """A parse backend that cannot fail for parser reasons.

    Exists so the queue, the interleave, the cancellation boundary and the
    run record are provable on their own (plan.md Phase C). Its results are
    deterministic functions of the wordform, so a test can assert *which*
    word produced a line without a live project.

    It models the two timing facts the machinery actually depends on: the
    first word pays a grammar load and later words do not, and a parse
    takes non-zero time so a boundary exists to interleave at.
    """

    def __init__(self, *, parse_seconds: float = 0.0) -> None:
        self._loaded = False
        self._parse_seconds = parse_seconds
        #: Counts every load. A test asserts this is exactly 1 across a
        #: batch and an interleaving urgent word (SC-009).
        self.load_count = 0

    def ensure_grammar(self, run_id: str) -> bool:
        if self._loaded:
            return False
        self._loaded = True
        self.load_count += 1
        return True

    def parse(
        self,
        wordform: str,
        level: str,
        restricted_to: Optional[tuple[int, ...]],
    ) -> dict[str, Any]:
        if self._parse_seconds:
            time.sleep(self._parse_seconds)

        if level == "restricted" and not restricted_to:
            # The stub refuses exactly where the real backend refuses. It is
            # the offline oracle the queue, interleave and cancellation
            # tests assert against, so a stub that quietly accepted an empty
            # restriction would report the widening FR-019 forbids as a
            # clean unrestricted parse -- and those tests would go green
            # over the one failure they exist to catch.
            raise ValueError(
                "An empty restriction reached the parser. This is a refusal "
                "(parse_morph_unresolved), never a widening to an "
                "unrestricted parse (FR-019)."
            )

        analyses = [
            {
                "morphs": [wordform],
                # `is not None`, not a truthiness test: None means "no
                # restriction" and an empty sequence means "admit nothing".
                # Collapsing them here would make the echo lie about which
                # one the caller sent.
                "restricted_to": (
                    list(restricted_to) if restricted_to is not None else None
                ),
            }
        ]
        trace_xml = None
        if level in ("restricted", "explain"):
            trace_xml = (
                f"<trace stub='1' word='{wordform}' level='{level}'></trace>"
            )
        return {
            "parse": {"word": wordform, "analyses": analyses, "stub": True},
            "trace_xml": trace_xml,
        }

    def lexicon_rows(self) -> list:
        """A tiny fixed lexicon, shaped to exercise all three outcomes.

        `pukul` resolves; `kirim` is ambiguous between two entries; `kosong`
        exists and carries no analysis. Without the last two the stub would
        make `ambiguous` and `no_msa` unreachable, and a stub that can only
        produce success is the one that lets a collapse of the three
        outcomes pass unnoticed.
        """
        return [
            {"headword": "pukul", "entry_hvo": 101,
             "senses": ["hit"], "msa_hvos": [5001]},
            {"headword": "kirim", "entry_hvo": 102,
             "senses": ["send"], "msa_hvos": [5002]},
            {"headword": "kirim", "entry_hvo": 103,
             "senses": ["deliver"], "msa_hvos": [5003]},
            {"headword": "kosong", "entry_hvo": 104,
             "senses": ["empty"], "msa_hvos": []},
        ]

    def release(self) -> None:
        self._loaded = False


class ParserUnavailableError(RuntimeError):
    """`GetAvailability()` said no. Carries the contract's refusal payload.

    Raised instead of a bare `RuntimeError` so the refusal survives the
    channel. `_report_exception` marshals any exception carrying a `detail`
    dict under its own `error_code`; without one this arrives at the caller
    as `runtime_error`, which the contract's refusal table explicitly does
    not say (contracts/tools.md: "`parser_core_missing` -- GetAvailability()
    reports unavailable; `reason` is carried through").

    The facade's `reason` is free text, so it rides in `load_error` rather
    than in `signal`: `signal` is a CLOSED enum shared with the health
    block's `read.reason` / `write.reason` and must not be widened to hold
    a sentence. `load_failed` is the member that fits -- the parser answered
    and said it cannot serve, which is not the same as it being absent.

    `detail` is shaped to match `response_models.ParserCoreMissingDetail`
    exactly, field for field, because that model is `extra="forbid"`: a
    stray key here is a validation failure at the far end, not a tolerated
    extra.
    """

    def __init__(self, project_name: str, reason: str, availability: Any) -> None:
        super().__init__(
            f"The parser is not available for {project_name!r}: {reason}"
        )
        self.detail = {
            "error_code": "parser_core_missing",
            "signal": "load_failed",
            "expected_path": str(getattr(availability, "path", "") or ""),
            "detected_version": _as_text(getattr(availability, "version", None)),
            "missing_members": [],
            "lcmodel_install_path": None,
            "install_hint": (
                "Run flextools_health to see which parser components this "
                "machine has. The parser reported itself unavailable rather "
                "than missing, so the usual cause is a component present but "
                "not usable -- see load_error for what it said."
            ),
            "load_error": reason,
        }


class _RealBackend(_ParseBackend):
    """The real thing: an open project and `project.Parser` (T026).

    Everything in this class runs **only in the worker process**. It opens
    an LCM cache, holds a loaded grammar and lives inside pythonnet -- all
    of which are exactly what must never reach the server (R-02).

    THE FACADE IS SIX MEMBERS, and the three this class calls are bound
    with care:

        GetAvailability()                  -> (available, reason, version)
        ParseWord(word)                    -> structured, live LCM objects
        TraceWordXml(word, analyses=None)  -> serialized trace document
        Reload() / IsUpToDate()            -> the held-grammar contract

    `TryWord`, `TryWordXml` and `TraceWord` -- the names `CP2-SPEC.md`
    section 3.1 tabulates -- **do not exist**. That table describes a design
    that was not built (spec.md Delta 1).

    WHY THE XML CALLS ARE BOUND POSITIONALLY (FR-012). The shipped
    implementation names its first parameter `word`; flexicon's own offline
    test double for the same facade names it `form`
    (`flexicon:tests/test_parser_offline.py`). Binding by keyword to either
    name therefore works against one and raises `TypeError` against the
    other. Positional binding is the only form that is correct against
    both, which is why it is a requirement rather than a preference.

    WHY `GetAvailability()` IS CALLED RATHER THAN INFERRED. It would be
    cheaper to read the `CAPABILITIES` token and conclude the parser is
    usable. The token records what the build was compiled to support, not
    what this machine can currently do, so inferring from it reports a
    working parser on a machine where the HC tool is absent. The facade is
    asked directly (research.md R-03, spec.md Delta 4).
    """

    def __init__(self, project_name: str) -> None:
        self._project_name = project_name
        self._project = None
        self._initialized = False
        self._grammar_loaded = False
        self._availability_checked = False

    # -- lifetime ---------------------------------------------------------

    def open(self) -> None:
        """Open the project read-only. Called once, at worker startup.

        `writeEnabled=False` is not defensive decoration: FR-002 says the
        parser area exposes no way to write, and this checkpoint keeps that
        promise at the point where it can actually be enforced. The
        `undoable=False` / headless-UI conventions are the same ones the
        scan seam uses (`handlers/execution.py`), reused rather than
        reinvented -- a generated runner has no WinForms message pump, so a
        dialog with no owner hangs forever (issue #96, flexicon #238).
        """
        from flexicon import FLExInitialize, FLExProject

        try:
            from flexicon.code.headless_ui import HeadlessLcmUI

            lcm_ui = HeadlessLcmUI()
        except ImportError:
            lcm_ui = None
            _log(
                "HeadlessLcmUI unavailable in this flexicon build; falling "
                "back to the WinForms FwLcmUI."
            )

        FLExInitialize()
        self._initialized = True

        project = FLExProject()
        project.OpenProject(
            projectName=self._project_name,
            writeEnabled=False,
            undoable=False,
            ui=lcm_ui,
        )
        self._project = project

    def release(self) -> None:
        """Close the project and drop the grammar. Safe to call twice."""
        self._grammar_loaded = False
        project, self._project = self._project, None
        if project is not None:
            try:
                project.CloseProject()
            except Exception as exc:  # noqa: BLE001
                _log(f"CloseProject failed: {type(exc).__name__}: {exc}")
        if self._initialized:
            self._initialized = False
            try:
                from flexicon import FLExCleanup

                FLExCleanup()
            except Exception:  # noqa: BLE001
                pass

    # -- the gate ---------------------------------------------------------

    def preflight(self) -> None:
        """`check_active_parser` -- the first thing that happens per request.

        Re-read live on every request and never memoized: a user can flip
        the active parser mid-session via Words > Parser > Choose Parser,
        so a cached verdict would outlive the fact it describes
        (`parser_probe.py`). The raised `ParserEngineMismatchError` already
        carries a `detail` dict shaped like the matching response model, and
        `_report_exception` marshals it back unchanged.

        WHAT IS PASSED MATTERS, and it is not obvious. `check_active_parser`
        reads `project.MorphologicalDataOA`, which lives on the LCM
        **language project** -- not on flexicon's `FLExProject` wrapper.
        Passing the wrapper raises `AttributeError: 'FLExProject' object has
        no attribute 'MorphologicalDataOA'`, which is what the first live
        run of this backend did. CP1 shipped this helper with no production
        caller, so the distinction had never been exercised; the flexicon
        idiom for it throughout that codebase is `project.lp`.

        This is why it is `self._project.lp` below and why that is spelled
        out rather than left to read as a stray attribute: bound to the
        wrong object the gate does not merely fail, it fails *identically*
        for an HC project and an XAmple one, which would make the engine
        refusal untestable.
        """
        from ..parser_probe import check_active_parser

        check_active_parser(self._project.lp, supported_engines=("HC",))

    # -- the held grammar -------------------------------------------------

    def ensure_grammar(self, run_id: str) -> bool:
        """Report whether the next parse will pay for a grammar load.

        Returns True when a load is about to happen, so the worker reports
        `loading_grammar` only when the run really pays for one.

        **THIS DOES NOT LOAD THE GRAMMAR, AND MUST NOT.** The facade already
        confirms currency and reloads a stale grammar on every parse -- its
        own `Reload()` documentation says so explicitly and adds that you
        rarely need to call it. Calling `Reload()` here would therefore be a
        **second currency path** running alongside the facade's, which is
        exactly what spec.md Delta 2 forbids for the sibling case (the
        restriction-clearing path). It would also be actively harmful:
        `Reload()` is unconditional by design, so calling it on the first
        word of every worker would discard and rebuild a grammar the facade
        was about to load correctly anyway -- paying the most expensive step
        in the run twice, for nothing.

        FR-043's "currency confirmed before every reuse" is satisfied by the
        facade doing it, not by this class doing it again. What CP2b owes on
        top is the *reporting* FR-027 requires: `loading_grammar` must be
        distinguishable from `parsing`, because it is the step that most
        often exhausts memory and the one that dominates a cold run. So
        `IsUpToDate()` is asked as a **question**, never as a trigger.

        The first word of a worker's life is reported as a load without
        asking anything, because on a cold parser the question itself would
        do the loading and the stage would then be announced after the fact.
        """
        parser = self._project.Parser

        if not self._availability_checked:
            # Asked, not inferred from the CAPABILITIES token: the token
            # records what the build supports, not what this machine can
            # currently do (spec.md Delta 4).
            availability = parser.GetAvailability()
            self._availability_checked = True
            if not getattr(availability, "available", False):
                reason = getattr(availability, "reason", None) or "no reason given"
                raise ParserUnavailableError(self._project_name, reason, availability)

        if not self._grammar_loaded:
            self._grammar_loaded = True
            return True

        # A question about what the next parse will do. The facade performs
        # any reload itself, as part of that parse.
        try:
            return not parser.IsUpToDate()
        except Exception as exc:  # noqa: BLE001
            # Reporting is best-effort; a run must not fail because the
            # stage could not be predicted.
            _log(f"IsUpToDate() failed, reporting no load: {exc}")
            return False

    def lexicon_rows(self) -> list:
        """Read every entry once: headword, senses, and its MSA identifiers.

        Verified against `IndonesianHC-Complete` before being written --
        `LexEntry.GetAll()`, `LexEntry.GetHeadword(entry)`,
        `MSA.GetAll(entry)` with `.Hvo` on each, and
        `LexEntry.GetAllSenses` + `Senses.GetGloss`. Guessing this surface
        is how CP2's section 3.1 came to tabulate three operations that do
        not exist (spec.md Delta 1).

        AN ENTRY WITH NO MSAs IS KEPT, with an empty `msa_hvos`. That row is
        the `no_msa` outcome; dropping it would turn "this entry carries no
        analysis" into "no such entry" and send the caller to fix a spelling
        that is already correct.

        Per-entry failures are skipped rather than fatal, but only for the
        OPTIONAL parts: an entry whose headword cannot be read cannot be
        named by one, so it can never answer a headword lookup. Senses and
        analyses degrade to empty, which is a true statement about what
        could be read.
        """
        project = self._project
        rows: list[dict[str, Any]] = []

        for entry in project.LexEntry.GetAll():
            try:
                headword = project.LexEntry.GetHeadword(entry)
            except Exception as exc:  # noqa: BLE001 -- see docstring
                _log(f"skipping an entry with no readable headword: {exc}")
                continue
            if not headword:
                continue

            try:
                msa_hvos = [int(msa.Hvo) for msa in project.MSA.GetAll(entry)]
            except Exception as exc:  # noqa: BLE001
                _log(f"no analyses readable for {headword!r}: {exc}")
                msa_hvos = []

            senses: list[str] = []
            try:
                for sense in project.LexEntry.GetAllSenses(entry):
                    gloss = project.Senses.GetGloss(sense)
                    if gloss:
                        senses.append(str(gloss))
            except Exception as exc:  # noqa: BLE001
                _log(f"no senses readable for {headword!r}: {exc}")

            try:
                entry_hvo = int(entry.Hvo)
            except Exception:  # noqa: BLE001
                entry_hvo = 0

            rows.append(
                {
                    "headword": str(headword),
                    "entry_hvo": entry_hvo,
                    "senses": senses,
                    "msa_hvos": msa_hvos,
                }
            )

        return rows

    def reload_grammar(self) -> None:
        """Discard and rebuild the grammar now, as reset-then-update.

        The facade's `Reload()` is two steps in that order, and the order
        matters: the component's update short-circuits when it believes the
        model is unchanged, so a reload bound to a bare update would return
        having done nothing and serve the next parse from the very grammar
        the caller asked to discard (SC-014).

        Not called on any ordinary parse path -- see `ensure_grammar`. This
        exists for an explicit, caller-requested reload.
        """
        self._project.Parser.Reload()
        self._grammar_loaded = True

    # -- parsing ----------------------------------------------------------

    def parse(
        self,
        wordform: str,
        level: str,
        restricted_to: Optional[tuple[int, ...]],
    ) -> dict[str, Any]:
        """Map the three levels onto the three calls (FR-012).

            restricted -> TraceWordXml(word, analyses)
            plain      -> ParseWord(word)
            explain    -> TraceWordXml(word, None)

        Note the positional binding on both XML calls -- see the class
        docstring for why that is load-bearing rather than stylistic.
        """
        parser = self._project.Parser

        if level == "restricted":
            if not restricted_to:
                # Defence in depth. An empty restriction must have been
                # refused long before here (FR-019, spec.md Delta 2); the
                # facade raises FP_ParameterError on an empty iterable and
                # the setting OUTLIVES THE CALL, so letting one through
                # would corrupt the next parse too.
                raise ValueError(
                    "An empty restriction reached the parser. This is a "
                    "refusal (parse_morph_unresolved), never a widening to "
                    "an unrestricted parse (FR-019)."
                )
            trace = parser.TraceWordXml(wordform, list(restricted_to))
            return {"parse": None, "trace_xml": _as_text(trace)}

        if level == "explain":
            trace = parser.TraceWordXml(wordform, None)
            return {"parse": None, "trace_xml": _as_text(trace)}

        # plain
        result = parser.ParseWord(wordform)
        return {"parse": _summarize_plain(result), "trace_xml": None}


def _as_text(value: Any) -> Optional[str]:
    """Coerce a facade return to a plain string for the channel.

    The trace comes back as a serialized document, but "serialized" does
    not guarantee `str` across the CLR boundary. Everything crossing this
    channel is JSON, so it is coerced here rather than at the far end where
    the original object is no longer available to inspect.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _summarize_plain(result: Any) -> dict[str, Any]:
    """Reduce `ParseWord`'s live objects to something JSON can carry.

    `ParseWord` returns live LCM object references, which cannot cross a
    JSON channel and must not be smuggled across it either -- they belong
    to the worker's LCM cache and mean nothing in the server process.

    What the plain level actually owes its caller is narrow: FR-013 says it
    reports only **that** nothing parsed and points at the explaining
    levels; it must never present itself as an explanation. So this
    deliberately extracts a count and nothing more. Enriching it here would
    be the first step toward the plain level explaining itself, which is
    the thing the requirement forbids.
    """
    analyses = getattr(result, "Analyses", None)
    count = 0
    if analyses is not None:
        # A CLR ReadOnlyCollection[ParseAnalysis]. `Count` is its own
        # property and is tried first; `len()` works through pythonnet's
        # ICollection mapping and is the fallback. Both are tried because
        # this is the one number the whole plain level rests on, and a
        # silent 0 here would report "nothing parsed" for a word that
        # parsed perfectly well -- the exact silent-wrong-answer shape
        # CP2a shipped for a whole checkpoint.
        count = getattr(analyses, "Count", None)
        if count is None:
            try:
                count = len(analyses)
            except TypeError:
                count = sum(1 for _ in analyses)

    return {"parsed": int(count) > 0, "analysis_count": int(count)}


class _SpecView:
    """A `MorphSpec` as it arrives over the channel: a plain dict.

    `resolver.resolve_spec` reads `headword` / `sense` / `msa_hvo` /
    `position` by attribute, and the server-side model supplies them that
    way. Rather than import the pydantic model into the worker -- which
    would drag the whole `server.models` import graph into a process whose
    job is to hold a grammar -- this gives the dict the same four
    attributes. The resolver stays indifferent to which side called it,
    which is what lets one implementation serve both.
    """

    __slots__ = ("headword", "sense", "msa_hvo", "position")

    def __init__(self, raw: dict[str, Any]) -> None:
        self.headword = raw.get("headword")
        self.sense = raw.get("sense")
        self.msa_hvo = raw.get("msa_hvo")
        self.position = raw.get("position")

    @property
    def morph(self) -> Any:
        return self.headword if self.headword is not None else self.msa_hvo


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


class ParseWorker:
    """One worker, one project, one held grammar.

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
        elif kind == "assemblies":
            # A diagnostic, not part of the parse path. It exists so
            # `HCParser_DoesNotLoadXCore` can read the loaded-assembly list
            # of the process that did the parsing; asked from the server
            # process the answer would be about the wrong process.
            self._emit({"type": "assemblies", "names": loaded_assembly_names()})
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
        }
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
        """
        while True:
            self._drain_cancellations()
            # Answered at a word boundary, like everything else that is not
            # a parse. One word of latency, never more.
            self._drain_resolves()

            word = self._queue.dequeue()

            if word is not None:
                self._deadline = time.monotonic() + self._idle_timeout
                self._parse_one(word)
                continue

            # Queue empty. Now -- and only now -- is it safe to stop.
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
        (`handlers/parse.py`); this end reports what it found, including the
        candidates it rejected, because those are what make a refusal
        actionable rather than merely final.
        """
        with self._resolve_lock:
            pending, self._resolve_pending = self._resolve_pending, []
        if not pending:
            return

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
            self._emit(
                {
                    "type": "error",
                    "request_id": meta.get("request_id"),
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
        """
        meta = self._pending_meta.pop(
            (word.run_id, word.index_in_run), {"request_id": None, "level": "plain"}
        )

        if self._queue.is_cancelled(word.run_id):
            self._report_cancelled(word.run_id)
            return

        self._note_interleave(word)

        try:
            self._before_parse(word)
        except Exception as exc:  # noqa: BLE001 -- marshalled, see below
            self._report_exception(exc, meta.get("request_id"), word.run_id)
            return

        # Re-checked after the grammar load: loading is the longest step in
        # the run, so it is the most likely place for a cancel to arrive.
        # Without this second check a cancelled run would still parse one
        # word after a multi-second load.
        if self._queue.is_cancelled(word.run_id):
            self._report_cancelled(word.run_id)
            return

        try:
            outcome = self._backend.parse(
                word.wordform, meta.get("level", "plain"), word.restricted_to
            )
        except Exception as exc:  # noqa: BLE001
            self._report_exception(exc, meta.get("request_id"), word.run_id)
            return

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

    def _before_parse(self, word: QueuedWord) -> None:
        """The engine gate, THEN the grammar. The order is the requirement.

        `preflight()` is the first statement, before anything touches the
        parser area (FR-015, R-03). It is first here rather than inside
        `ensure_grammar` so that it still runs on the common path where a
        held grammar is reused and no load happens at all -- folded into
        the load, the gate would silently stop running from the second word
        onwards, which is precisely when a user is most likely to have
        flipped the active parser.
        """
        self._backend.preflight()

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
        error_code = None
        if isinstance(detail, dict):
            error_code = detail.get("error_code")
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
                "message": f"{type(exc).__name__}: {exc}",
            }
        )

    # -- teardown ---------------------------------------------------------

    def release(self) -> None:
        """Drop the grammar and the project. Safe to call twice."""
        try:
            self._backend.release()
        except Exception as exc:  # noqa: BLE001
            _log(f"backend release failed: {type(exc).__name__}: {exc}")


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
        required=True,
        help="FieldWorks project name. Opened writeEnabled=False.",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=None,
        help=(
            "Seconds of inactivity before releasing the project and exiting. "
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

    idle_timeout = (
        args.idle_timeout
        if args.idle_timeout is not None
        else _idle_timeout_from_env(DEFAULT_IDLE_TIMEOUT_SECONDS)
    )

    backend: _ParseBackend
    if args.stub:
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
    _emit({"type": "ready", "protocol": PROTOCOL_VERSION, "project": args.project})

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
