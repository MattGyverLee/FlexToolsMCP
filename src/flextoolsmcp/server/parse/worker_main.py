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

Responses (stdout):

    {"type": "ready",     "protocol": 1, "project": str}
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
        *,
        vernacular_ws: Optional[str] = None,
    ) -> dict[str, Any]:
        """Parse one word. Returns `{"parse": ..., "trace_xml": ...}`."""
        raise NotImplementedError

    def lexicon_rows(self) -> list:
        """Every entry, as plain rows the resolver can index (FR-018).

        Plain data, never LCM objects: `LexiconIndex` must hold no reference
        into a cache, and the rows cross no process boundary carrying one.
        """
        raise NotImplementedError

    def active_engine(self) -> Optional[str]:
        """The project's active parser, READ -- not gated (CP3, FR-024).

        The gate (`preflight`) refuses; this only reports. A batch runs the
        gate once, at submission, and from then on its words observe the
        engine through this read so a mid-job change becomes a warning on the
        run rather than a refusal of the words still queued.
        """
        return None

    def resolve_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        """Resolve a `ParseScope` dump to a `ResolvedScope` dump (US1).

        Raises `scope.ScopeRefusal` (carrying its `detail`) for the two
        scope refusals, which `_report_exception` marshals unchanged.
        """
        raise NotImplementedError

    def project_state(self) -> Optional[dict[str, Any]]:
        """`ProjectParseState.to_dict()` from the one probe, or None."""
        return None

    def parser_parameters(self) -> Optional[dict[str, Any]]:
        """The stored parser parameters, summarised, or None (FR-055).

        A READ. The measurement reports them as context for a slow parse;
        nothing on any CP3 path writes them.
        """
        return None

    def load_error_baseline(self, load_started: float) -> Optional[dict[str, Any]]:
        """The grammar load errors of a load that began at `load_started`.

        Called after the parse that paid for a grammar load. Returns None
        when this backend cannot establish them; the baseline then records
        that it was not captured, rather than recording zero errors (FR-023).
        """
        return None

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

    #: The stub's corpus for `resolve_scope(all_texts)`. Fixed, so a test can
    #: assert the resolved order: descending occurrence, then alphabetical.
    STUB_CORPUS: dict[str, int] = {"pukul": 3, "kirim": 3, "kosong": 1, "memukul": 2}

    def __init__(self, *, parse_seconds: float = 0.0) -> None:
        self._loaded = False
        self._parse_seconds = parse_seconds
        #: Counts every load. A test asserts this is exactly 1 across a
        #: batch and an interleaving urgent word (SC-009).
        self.load_count = 0
        #: What `active_engine()` reports. A test flips it mid-batch to
        #: exercise FR-024's warning-not-refusal path.
        self.engine = "HC"
        #: Per-word overrides for the batch level: word -> list of analysis
        #: dicts, and word -> list of human-analysis dicts. Absent words get
        #: the deterministic default below.
        self.analyses_by_word: dict[str, list] = {}
        self.human_by_word: dict[str, list] = {}

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
        *,
        vernacular_ws: Optional[str] = None,
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

        if level == "batch":
            return {"parse": self._batch_parse(wordform), "trace_xml": None}

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

    def _batch_parse(self, wordform: str) -> dict[str, Any]:
        """A batch-level result, shaped exactly like `_RealBackend`'s.

        Default: one analysis per word whose signature is derived from the
        word, so two runs over the same words compare `unchanged` and a test
        that overrides one word's analyses sees exactly that word move.
        """
        if wordform in self.analyses_by_word:
            analyses = list(self.analyses_by_word[wordform])
        else:
            analyses = [
                {
                    "signature": [[f"stub-form:{wordform}", f"stub-msa:{wordform}", None]],
                    "rendered_morphs": [wordform],
                    "category_labels": ["stub"],
                    "has_guessed_form": False,
                }
            ]
        return {
            "parsed": len(analyses) > 0,
            "analysis_count": len(analyses),
            "analyses": analyses,
            "human_analyses": list(self.human_by_word.get(wordform, [])),
            "error_message": None,
            "parse_time_ms": 0,
        }

    def active_engine(self) -> Optional[str]:
        return self.engine

    def resolve_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        """`words` and `all_texts` only; the stub has no genres or texts.

        Goes through the real ordering helper so the stub cannot disagree
        with production about order-then-truncate (FR-009).
        """
        from .scope import ScopeRefusal, _order_and_limit, _nfc

        kind = scope.get("kind")
        limit = scope.get("limit")
        if kind == "words":
            counts: dict[str, int] = {}
            for word in scope.get("value") or []:
                form = _nfc(word)
                if form:
                    counts[form] = counts.get(form, 0) + 1
            value = sorted(counts)
            text_ids: list[int] = []
        elif kind == "all_texts":
            counts = dict(self.STUB_CORPUS)
            value = None
            text_ids = [1]
        else:
            raise ScopeRefusal(
                {
                    "error_code": "parse_scope_empty",
                    "scope": dict(scope),
                    "matched_texts": [],
                    "hint": (
                        "The stub backend holds no genres or named texts; use "
                        "kind='words' or kind='all_texts'."
                    ),
                }
            )
        words, total, truncated = _order_and_limit(counts, limit)
        return {
            "scope_kind": kind,
            "scope_value": value,
            "text_ids": text_ids,
            "words": words,
            "count_before_limit": total,
            "limit": limit,
            "truncated": truncated,
            "vernacular_ws": scope.get("vernacular_ws") or "stub-vern",
            "never_tokenized_text_ids": [],
            "unreadable_wordform_count": 0,
            "notes": [],
        }

    def load_error_baseline(self, load_started: float) -> Optional[dict[str, Any]]:
        return {"captured": True, "source": "stub", "errors": []}

    #: What `project_state()` reports; a test may replace it.
    stub_project_state: dict[str, Any] = {
        "parser_has_ever_run": True, "analyses_total": 0, "parser_created_analyses": 1,
        "human_opinion_analyses": 0, "indeterminate_analyses": 0, "truncated": False,
    }

    def project_state(self) -> Optional[dict[str, Any]]:
        return dict(self.stub_project_state)

    #: What `parser_parameters()` summarises: a minimal stored-parameters
    #: document, run through the same summariser the real backend uses.
    STUB_PARSER_PARAMETERS = (
        "<ParserParameters><ActiveParser>HC</ActiveParser>"
        "<HC><GuessRoots>false</GuessRoots><MaxCompoundRules>4</MaxCompoundRules></HC>"
        "</ParserParameters>"
    )

    def parser_parameters(self) -> Optional[dict[str, Any]]:
        from .measure import summarize_parser_parameters

        return summarize_parser_parameters(self.STUB_PARSER_PARAMETERS)

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

        import flexicon as _flexicon_pkg

        _UI_CAPS = getattr(_flexicon_pkg, "CAPABILITIES", frozenset())
        if "ui-injection" in _UI_CAPS:
            try:
                from flexicon import HeadlessLcmUI

                lcm_ui = HeadlessLcmUI()
            except ImportError:
                lcm_ui = None
                _log(
                    "flexicon advertises ui-injection but HeadlessLcmUI is not "
                    "importable; OpenProject will omit ui=."
                )
        else:
            lcm_ui = None
            _log(
                "flexicon build does not advertise ui-injection in CAPABILITIES; "
                "OpenProject will omit ui=."
            )

        # Issue #159: the `ui=` kwarg only exists on flexicon >=4.4.0
        # OpenProject(). A stray older build (mismatched venv) rejects it
        # with TypeError at the session's very first action. Probe the
        # INSTALLED signature in THIS process -- a server-side probe would
        # describe the server's flexicon, not this worker's.
        try:
            import inspect
            _openproject_accepts_ui = "ui" in inspect.signature(FLExProject.OpenProject).parameters
        except Exception:
            _openproject_accepts_ui = False

        FLExInitialize()
        self._initialized = True

        project = FLExProject()
        if _openproject_accepts_ui:
            project.OpenProject(
                projectName=self._project_name,
                writeEnabled=False,
                undoable=False,
                ui=lcm_ui,
            )
        else:
            _log(
                "this flexicon build's OpenProject() does not accept the "
                "ui= argument; opening with this build's default LCM UI "
                "instead (issue #159)."
            )
            project.OpenProject(
                projectName=self._project_name,
                writeEnabled=False,
                undoable=False,
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
        *,
        vernacular_ws: Optional[str] = None,
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
            summary = _summarize_trace(trace)
            # A restriction is a pre-parse narrowing (HCParser.cs:186-199,
            # 211), so its survivors answer "does my restriction still admit
            # an analysis" -- never "does this word parse". Renamed here,
            # at the one place that already knows which question this call
            # asked, so every consumer downstream (the inline response AND
            # the parse_status summary) receives a self-describing entry
            # rather than having to re-derive the level to interpret it.
            if "parse_error" not in summary:
                summary = {
                    "hypothesis_held": summary["parsed"],
                    "restricted_analysis_count": summary["analysis_count"],
                }
            return {"parse": summary, "trace_xml": _as_text(trace)}

        if level == "explain":
            trace = parser.TraceWordXml(wordform, None)
            return {"parse": _summarize_trace(trace), "trace_xml": _as_text(trace)}

        if level == "batch":
            return {"parse": self._batch_parse(wordform, vernacular_ws), "trace_xml": None}

        # plain
        result = parser.ParseWord(wordform)
        return {"parse": _summarize_plain(result), "trace_xml": None}

    # -- CP3: the batch level ---------------------------------------------

    def active_engine(self) -> Optional[str]:
        """`ActiveParser`, read off the language project -- `.lp`, for the
        reason `preflight` spells out. A read, never a gate."""
        try:
            return str(self._project.lp.MorphologicalDataOA.ActiveParser)
        except Exception as exc:  # noqa: BLE001 -- a report, not a gate
            _log(f"ActiveParser unreadable: {exc}")
            return None

    def resolve_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        """US1's resolver, run where the project is open.

        Imports the server's scope model here, lazily and only for this
        call: resolution needs `ParseScope`'s validation, and running it in
        the server would need an open project there, which is the thing
        R-02 forbids. The parse path never pays for this import.
        """
        from ..models import ParseScope
        from .scope import resolve_scope

        return resolve_scope(self._project, ParseScope(**scope)).model_dump()

    def _ws_handle(self, vernacular_ws: Optional[str]) -> int:
        """The explicit handle words are read and rendered in (live note)."""
        if vernacular_ws:
            handle = self._project.WSHandle(vernacular_ws)
            if handle is not None:
                return int(handle)
        return int(self._project.GetDefaultVernacularWSHandle())

    def _wordform_index(self, ws: int) -> dict[str, Any]:
        """NFC form -> wordform at `ws`, built once per writing system.

        `Wordforms.Find` walks every wordform on every call; a batch of ten
        thousand words would make that ten thousand full walks. Built lazily
        on the first batch word and held for the worker's life, like the
        lexicon index.
        """
        cache = getattr(self, "_wordforms_by_ws", None)
        if cache is None:
            cache = self._wordforms_by_ws = {}
        if ws not in cache:
            import unicodedata

            index: dict[str, Any] = {}
            for wordform in self._project.Wordforms.GetAll():
                try:
                    form = self._project.Wordforms.GetForm(wordform, ws)
                except Exception:  # noqa: BLE001
                    continue
                form = unicodedata.normalize("NFC", str(form or "")).strip()
                if form:
                    index.setdefault(form, wordform)
            cache[ws] = index
        return cache[ws]

    def _batch_parse(self, wordform: str, vernacular_ws: Optional[str]) -> dict[str, Any]:
        """`ParseWord` -> plain data, from the TYPED result (FR-035, R-11).

        `ParseWord` returns a `ParseResult` whose analyses hold LIVE
        `IMoForm` / `IMoMorphSynAnalysis` / `ILexEntryInflType` references
        (`ParseResult.cs`). They are read here, in the process that owns the
        cache, and reduced to identifiers and rendered text before anything
        crosses the channel (FR-021). The document-returning calls keep only
        integer ids and are not used.

        IDENTIFIERS ARE GUIDS, NOT HVOS. An hvo is a session-scoped handle
        that liblcm renumbers on every cache load (issue #103), so an
        hvo-triple signature recorded today would fail to match the same
        analysis tomorrow and every word would read as `changed`. The object
        GUID is the identity the host's own `ParseMorph.GetHashCode` uses,
        and it persists in the project file.

        The wordform's HUMAN analyses are read beside the parse, because the
        host's counters (`ParseReport`) are defined against them and the
        artifact must be reportable without reopening the project.
        """
        ws = self._ws_handle(vernacular_ws)
        analysis_ws = self._analysis_ws()
        parser = self._project.Parser

        started = time.perf_counter()
        result = parser.ParseWord(wordform)
        elapsed_ms = int(round((time.perf_counter() - started) * 1000))

        analyses = []
        for analysis in _clr_list(getattr(result, "Analyses", None)):
            analyses.append(_structured_analysis(analysis, ws, analysis_ws))

        error = getattr(result, "ErrorMessage", None)
        return {
            "parsed": len(analyses) > 0,
            "analysis_count": len(analyses),
            "analyses": analyses,
            "human_analyses": self._human_analyses(wordform, ws),
            "error_message": str(error) if error else None,
            "parse_time_ms": elapsed_ms,
        }

    def _human_analyses(self, wordform: str, ws: int) -> list[dict[str, Any]]:
        """The stored analyses on this wordform, as plain facts.

        `opinion` is the HUMAN opinion from `GetApprovalStatus` (human
        evaluations only; 2 approves, 0 disapproves, 1 none recorded). The
        bundle count and the count of bundles whose public `IsComplete` is
        true are recorded as read -- the tier is derived from them later and
        the host's internal fully-formed predicate is never reimplemented
        (FR-038).
        """
        import unicodedata

        form = unicodedata.normalize("NFC", wordform).strip()
        target = self._wordform_index(ws).get(form)
        if target is None:
            return []
        project = self._project
        records: list[dict[str, Any]] = []
        try:
            stored = list(project.WfiAnalyses.GetAll(target))
        except Exception as exc:  # noqa: BLE001
            _log(f"analyses unreadable for {form!r}: {exc}")
            return []
        for analysis in stored:
            try:
                status = int(project.WfiAnalyses.GetApprovalStatus(analysis))
            except Exception:  # noqa: BLE001
                status = None
            opinion = {2: "approves", 0: "disapproves", 1: "noopinion"}.get(status, "unreadable")
            bundles = _clr_list(getattr(analysis, "MorphBundlesOS", None))
            signature = []
            rendered = []
            complete = 0
            for bundle in bundles:
                signature.append(
                    [
                        _guid(getattr(bundle, "MorphRA", None)),
                        _guid(getattr(bundle, "MsaRA", None)),
                        _guid(getattr(bundle, "InflTypeRA", None)),
                    ]
                )
                rendered.append(_multi_text(getattr(bundle, "Form", None), ws))
                try:
                    if bool(bundle.IsComplete):
                        complete += 1
                except Exception:  # noqa: BLE001
                    pass
            analysis_guid = _guid(analysis)
            evaluator, evaluated_at, parser_evaluated = self._evaluation_facts(analysis)
            records.append(
                {
                    "analysis_guid": analysis_guid,
                    "opinion": opinion,
                    "bundle_count": len(bundles),
                    "complete_bundle_count": complete,
                    "signature": signature,
                    "rendered_morphs": rendered,
                    # CP3 US5 additions (additive): what the oracle and the
                    # projections need, recorded as read.
                    "gloss": self._analysis_gloss(analysis),
                    "category_label": self._analysis_category(analysis),
                    "parser_evaluated": parser_evaluated,
                    "evaluator": evaluator,
                    "evaluated_at": evaluated_at,
                    "in_segment": self._segment_occurrence().contains(analysis_guid),
                }
            )
        return records

    # -- CP3 US5: facts the oracle reads ----------------------------------

    def _analysis_ws(self) -> Optional[int]:
        try:
            return int(self._project.GetDefaultAnalysisWSHandle())
        except Exception:  # noqa: BLE001
            return None

    def _analysis_gloss(self, analysis: Any) -> str:
        """The first word gloss (`IWfiGloss.Form`) at the analysis WS."""
        ws = self._analysis_ws()
        if ws is None:
            return ""
        for gloss in _clr_list(getattr(analysis, "MeaningsOC", None)):
            text = _multi_text(getattr(gloss, "Form", None), ws)
            if text:
                return text
        return ""

    def _analysis_category(self, analysis: Any) -> str:
        ws = self._analysis_ws()
        category = getattr(analysis, "CategoryRA", None)
        if category is None or ws is None:
            return ""
        return _multi_text(getattr(category, "Abbreviation", None), ws)

    def _evaluation_facts(self, analysis: Any) -> tuple:
        """(human evaluator name, human evaluation date, parser evaluated?).

        The evaluator is the evaluation's owning agent. `Owner` is typed as
        base `ICmObject`, which has no `Name`, so it is cast to `ICmAgent`
        before the read (the #32/#97/#98 class). Unreadable facts are None,
        never a guess.
        """
        evaluator = None
        evaluated_at = None
        parser_evaluated = False
        ws = self._analysis_ws()
        for evaluation in _clr_list(getattr(analysis, "EvaluationsRC", None)):
            try:
                human = bool(getattr(evaluation, "Human", False))
            except Exception:  # noqa: BLE001
                continue
            if not human:
                parser_evaluated = True
                continue
            if evaluator is None:
                agent = getattr(evaluation, "Owner", None)
                try:
                    from SIL.LCModel import ICmAgent  # type: ignore[import-not-found]

                    agent = ICmAgent(agent)
                except Exception:  # noqa: BLE001
                    pass
                name = _multi_text(getattr(agent, "Name", None), ws) if ws is not None else ""
                evaluator = name or None
                stamp = getattr(evaluation, "DateCreated", None)
                evaluated_at = str(stamp) if stamp is not None else None
        return evaluator, evaluated_at, parser_evaluated

    def _segment_occurrence(self):
        """The ONE segment-occurrence join (FR-043), built once per worker.

        The traversal (texts -> paragraphs -> segments) lives here because it
        needs the open project; the join itself -- which analyses a segment
        references, resolving a gloss to its owning analysis -- is
        `signals.oracle.segment_occurrence`, the implementation CP4's
        deletion projection reuses. Built lazily on the first stored analysis
        a batch reads and held for the worker's life.
        """
        cached = getattr(self, "_occurrence", None)
        if cached is None:
            from ..signals.oracle import segment_occurrence

            try:
                cached = segment_occurrence(self._iter_segments())
            except Exception as exc:  # noqa: BLE001 -- unknown, never "none"
                _log(f"segment-occurrence join failed: {exc}")
                cached = segment_occurrence(None)
            self._occurrence = cached
        return cached

    def _iter_segments(self):
        """Every segment of every text. Paragraphs are cast to `IStTxtPara`:
        `ParagraphsOS` is typed as base `IStPara`, which has no `SegmentsOS`."""
        try:
            from SIL.LCModel import IStTxtPara  # type: ignore[import-not-found]
        except Exception:  # noqa: BLE001
            IStTxtPara = None  # noqa: N806
        for text in self._project.Texts.GetAll():
            contents = getattr(text, "ContentsOA", None)
            for para in _clr_list(getattr(contents, "ParagraphsOS", None)):
                if IStTxtPara is not None:
                    try:
                        para = IStTxtPara(para)
                    except Exception:  # noqa: BLE001 -- not a text paragraph
                        continue
                for segment in _clr_list(getattr(para, "SegmentsOS", None)):
                    yield segment

    def project_state(self) -> dict[str, Any]:
        """The ONE project-state probe (FR-004), for the oracle precondition."""
        from .project_state import probe_project_state

        return probe_project_state(self._project).to_dict()

    def parser_parameters(self) -> Optional[dict[str, Any]]:
        """`MorphologicalDataOA.ParserParameters`, read and summarised.

        A plain string property holding the stored parameters document. Read
        through `.lp`, as `active_engine` is; never assigned anywhere in this
        package (FR-055, FR-063).
        """
        from .measure import summarize_parser_parameters

        try:
            raw = self._project.lp.MorphologicalDataOA.ParserParameters
        except Exception as exc:  # noqa: BLE001 -- context, not a gate
            _log(f"ParserParameters unreadable: {exc}")
            return None
        return summarize_parser_parameters(None if raw is None else str(raw))

    def load_error_baseline(self, load_started: float) -> Optional[dict[str, Any]]:
        """Read the load-error file OUR load just wrote (FR-023).

        HermitCrab's loader writes `<project>HCLoadErrors.xml` into the temp
        directory on every grammar load (`HCParser.cs:154`). The host's copy
        of that file is provenance-blind -- whichever process loaded last
        wrote it -- which is why the parent spec rejects it as CP4's
        baseline. The baseline here is ours because of WHEN it is read: right
        after the parse that paid for this worker's own load, and only if the
        file's modification time is not older than that load's start. A file
        older than our load was written by someone else and is NOT recorded.

        `Hvo` children are dropped: they are session-scoped handles (issue
        #103) and would make two baselines of an unchanged grammar differ.
        """
        import tempfile
        import xml.etree.ElementTree as ET

        path = os.path.join(tempfile.gettempdir(), f"{self._project_name}HCLoadErrors.xml")
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return {"captured": False, "source": path, "errors": [],
                    "reason": "the grammar load wrote no load-error file"}
        if mtime + 1.0 < load_started:
            return {"captured": False, "source": path, "errors": [],
                    "reason": "the load-error file predates this worker's grammar load"}
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as exc:
            return {"captured": False, "source": path, "errors": [],
                    "reason": f"the load-error file could not be read: {exc}"}
        errors = []
        for element in root:
            entry: dict[str, Any] = {"type": element.get("type")}
            for child in element:
                if child.tag != "Hvo":
                    entry[child.tag] = child.text
            errors.append(entry)
        return {"captured": True, "source": path, "errors": errors}


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


def _summarize_trace(trace: Any) -> dict[str, Any]:
    """Derive the same parsed/analysis_count facts `_summarize_plain`
    reports, straight from the trace `XDocument` -- BEFORE `_as_text`
    discards its structure.

    DERIVE, DO NOT RE-PARSE. `TraceWordXml` and `ParseWordXml` are the same
    C# method underneath (`HCParser.cs:120-131`): both build one
    `<Wordform>` document (root, `:207`) and append an `<Analysis>` child
    per surviving analysis (`:213-215`) *independently of the tracing
    flag*. The `<Trace>` sibling (`:217-218`) that `tracing=True` adds holds
    only explored/rejected paths -- they are never promoted into
    `<Analysis>`. So `len(root.Elements("Analysis"))` is not an estimate of
    what `ParseWord`'s own `Analyses.Count` would report; it is the same
    count, because `:104-113` applies the identical `GetMorphs` filter to
    build both. Counting it here is therefore never a second parse.

    THE <Error> CASE IS BLOCKING, and is checked FIRST. `ParseToXml` catches
    an exception and appends an `<Error>` child to `<Wordform>` *instead of*
    any `<Analysis>` (`HCParser.cs:219-222`). Zero `<Analysis>` is therefore
    ambiguous on its own: it means either "genuinely did not parse" or "the
    parse threw", and those are not the same fact. Reporting `parsed: False`
    for a document that actually holds `<Error>` would assert something
    false -- a worse defect than the silence it replaces, because today
    explain reports nothing about a thrown parse; a derived `False` would
    report a definite negative that never happened. So this returns
    `{"parse_error": str}` alone, with neither `parsed` nor `analysis_count`
    riding along -- the caller must not be able to mistake "the parse threw"
    for "the parse failed".

    ONE NO-ARGUMENT `Elements()` PASS, MATCHED BY `.Name.LocalName`.
    `XContainer.Element(XName)` / `.Elements(XName)` do not accept a bare
    `str` under pythonnet in this environment -- there is no implicit
    `str -> XName` conversion for that overload, so `root.Element("Error")`
    raised `TypeError: No method matches given arguments for
    XContainer.Element: (<class 'str'>)` on every live call (cycle 3
    verification). The no-arg `Elements()` overload (`IEnumerable<XElement>
    Elements()`) has no such binding problem, so this walks the children
    once, comparing each child's `.Name.LocalName` to the two names this
    function cares about, and counts/detects both in that single pass.
    Neither `XName` nor `System.Xml.Linq` needs importing into the worker
    for this, and no bare string is left behind for the next call site to
    reintroduce. <Error> still wins over <Analysis> when both are somehow
    present -- checked after the full walk, so the order children arrive in
    cannot flip the precedence.

    Returns:
        `{"parsed": bool, "analysis_count": int}` when the document has no
        `<Error>` (whether or not it has any `<Analysis>`), or
        `{"parse_error": str}` alone when it does, or when the document has
        no root at all (see below).
    """
    root = getattr(trace, "Root", None)
    if root is None:
        # A document we could not read is not a word that did not parse --
        # that is Delta 6's own stated principle, applied here. Silently
        # reporting `parsed: False` would invent the very fact absence was
        # supposed to avoid inventing: it would tell the caller the word
        # was tried and failed, when in truth nothing was ever established
        # about it at all. An unreadable document is indeterminate, and
        # `parse_error` is the outcome this function already has for "this
        # response asserts nothing about whether the word parses".
        return {"parse_error": "the trace document has no root element"}

    error_element = None
    analysis_count = 0
    for child in root.Elements():
        name = getattr(getattr(child, "Name", None), "LocalName", None)
        if name == "Error":
            if error_element is None:
                error_element = child
        elif name == "Analysis":
            analysis_count += 1

    if error_element is not None:
        text = getattr(error_element, "Value", None)
        if not text:
            text = str(error_element)
        return {"parse_error": str(text)}

    return {"parsed": analysis_count > 0, "analysis_count": analysis_count}


# ---------------------------------------------------------------------------
# CP3: reducing the typed structured result to plain data (FR-021, FR-035)
# ---------------------------------------------------------------------------


def _clr_list(collection: Any) -> list:
    """A CLR collection (or None) as a Python list. Never raises."""
    if collection is None:
        return []
    try:
        return list(collection)
    except TypeError:
        return []


def _guid(obj: Any) -> Optional[str]:
    """An LCM object's GUID as a lowercase string, or None for a null ref.

    The durable identity (see `_RealBackend._batch_parse`). A null reference
    stays None rather than becoming "" -- a triple whose inflection type is
    absent is a different triple from one whose inflection type is unknown.
    """
    if obj is None:
        return None
    guid = getattr(obj, "Guid", None)
    if guid is None:
        return None
    return str(guid).lower()


def _multi_text(multi: Any, ws: int) -> str:
    """One alternative of a multistring at an EXPLICIT writing system.

    Never `BestVernacularAlternative` and never the default: the live note
    for US1 records a whole text whose forms read back empty at the default
    writing system (the #36/#39/#40 class). Missing is "", not "***".
    """
    if multi is None:
        return ""
    try:
        text = multi.get_String(ws).Text
    except Exception:  # noqa: BLE001
        return ""
    if not text or text == "***":
        return ""
    return str(text)


def _msa_label(msa: Any) -> str:
    """A short category label for a morph's MSA, best-effort.

    Rendered text only, carried so a report is legible without reopening the
    project (FR-031). Nothing compares on it except the FR-033 fallback, and
    that fallback states its own ambiguity.
    """
    if msa is None:
        return ""
    for name in ("InterlinearAbbr", "ShortName"):
        try:
            value = getattr(msa, name, None)
        except Exception:  # noqa: BLE001
            value = None
        if value:
            text = getattr(value, "Text", value)
            if text and str(text) != "***":
                return str(text)
    return ""


def _morph_kind(form: Any) -> str:
    """'stem', 'affix' or 'unknown', from the form's morph type flags."""
    morph_type = getattr(form, "MorphTypeRA", None)
    if morph_type is None:
        return "unknown"
    try:
        if bool(getattr(morph_type, "IsAffixType", False)):
            return "affix"
        if bool(getattr(morph_type, "IsStemType", False)):
            return "stem"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _sense_gloss(entry: Any, msa: Any, analysis_ws: Optional[int]) -> str:
    """The gloss of the entry's sense that carries this MSA, best-effort.

    What a composed gloss is built from (SPEC 9.3.2). The entry arrives as
    the form's `Owner`, typed as base `ICmObject` -- `AllSenses` is not on
    that interface, so it is cast to `ILexEntry` first (the #32/#97/#98
    class: an unguarded member read on a base-typed `.Owner`).
    """
    if entry is None or msa is None or analysis_ws is None:
        return ""
    try:
        from SIL.LCModel import ILexEntry  # type: ignore[import-not-found]

        entry = ILexEntry(entry)
    except Exception:  # noqa: BLE001 -- not an entry, or no CLR (a test double)
        pass
    msa_guid = _guid(msa)
    for sense in _clr_list(getattr(entry, "AllSenses", None)):
        if _guid(getattr(sense, "MorphoSyntaxAnalysisRA", None)) == msa_guid:
            return _multi_text(getattr(sense, "Gloss", None), analysis_ws)
    return ""


def _structured_analysis(
    analysis: Any, ws: int, analysis_ws: Optional[int] = None
) -> dict[str, Any]:
    """One `ParseAnalysis` as an AnalysisRecord (data-model.md section 6).

    `signature` is the ordered (form, MSA, inflection type) GUID triples --
    the host's `MatchesIWfiAnalysis` predicate made durable (D-2). The
    inflection type is the third component, not an optional extra: without
    it two analyses differing only in inflection type collapse into one.

    `has_guessed_form` is the honest residue (FR-031a): where a morph carries
    a guessed surface string, the host predicate also requires that string to
    match one of the bundle's writing-system alternatives, and a serialized
    signature cannot reproduce that comparison.
    """
    signature = []
    rendered = []
    labels = []
    entries = []
    kinds = []
    glosses = []
    guessed = False
    for morph in _clr_list(getattr(analysis, "Morphs", None)):
        form = getattr(morph, "Form", None)
        msa = getattr(morph, "Msa", None)
        infl = getattr(morph, "InflType", None)
        guess = getattr(morph, "GuessedString", None)
        signature.append([_guid(form), _guid(msa), _guid(infl)])
        if guess is not None:
            guessed = True
            rendered.append(str(guess))
        else:
            rendered.append(_multi_text(getattr(form, "Form", None), ws))
        labels.append(_msa_label(msa))
        # CP3 US5 additions (additive to the frozen line shape): what the
        # batch signals need without reopening the project -- the owning
        # entry (root-entry disagreement), the morph kind (a root analysed
        # as affixes) and the sense gloss (the composed gloss, SPEC 9.3.2).
        owner = getattr(form, "Owner", None)
        entries.append(_guid(owner))
        kinds.append(_morph_kind(form))
        glosses.append(_sense_gloss(owner, msa, analysis_ws))
    return {
        "signature": signature,
        "rendered_morphs": rendered,
        "category_labels": labels,
        "has_guessed_form": guessed,
        "entry_guids": entries,
        "morph_kinds": kinds,
        "morph_glosses": glosses,
    }


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
        elif kind in ("engine_check", "resolve_scope", "parser_parameters"):
            # Main loop, for the same one-thread-owns-the-project reason.
            with self._resolve_lock:
                self._control_pending.append(message)
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
            "vernacular_ws": message.get("vernacular_ws"),
            "engine_at_submission": message.get("engine_at_submission"),
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
            self._drain_controls()

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
            load_started = self._before_parse(word, meta)
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
            try:
                self._load_baseline = self._backend.load_error_baseline(load_started)
            except Exception as exc:  # noqa: BLE001 -- a baseline must not fail a word
                self._load_baseline = {
                    "captured": False, "errors": [],
                    "reason": f"{type(exc).__name__}: {exc}",
                }
        if meta.get("engine_at_submission") is not None:
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

    def _send_baseline_once(self, run_id: str) -> None:
        """Hand a batch the current load-error baseline, once.

        A batch that begins on a warm worker paid no load of its own; the
        baseline it records is that of the grammar it is actually parsing
        with, which is the held one (FR-027). Recording nothing would leave
        CP4's gate with no baseline to compare against for exactly the runs
        that were cheapest to start.
        """
        if run_id in self._baseline_sent or self._load_baseline is None:
            return
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
