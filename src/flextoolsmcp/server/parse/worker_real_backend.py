"""
The real, project-bound parse backend: `_RealBackend` over flexicon's
`ParserOperations` facade, and the headless-UI `OpenProject` helper.

One of the two modules allowed to run parse operations
(tests/test_cp1_boundary.py, CP2B_PARSE_OPERATION_ALLOWLIST).

Worker-process only: imported by `worker_main.py` (the parse worker) and the
filing worker, never by the MCP server process -- see `worker_main.py`'s
header for why.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from .worker_analysis import (
    _as_text,
    _clr_list,
    _guid,
    _multi_text,
    _structured_analysis,
    _summarize_plain,
    _summarize_trace,
)
from .worker_backend import (
    _ParseBackend,
)
from .worker_protocol import (
    _log,
)


def headless_ui_kwargs(flex_project_class: Any) -> dict[str, Any]:
    """`OpenProject`'s headless-UI argument, where this flexicon build takes it.

    A generated runner has no WinForms message pump, so a dialog with no
    owner hangs forever (issue #96, flexicon #238): the project is opened with
    flexicon's `HeadlessLcmUI` when the build advertises `ui-injection`.

    Issue #159: the `ui=` kwarg only exists on flexicon >=4.4.0
    `OpenProject()`. A stray older build (mismatched venv) rejects it with
    TypeError at the session's very first action, so the INSTALLED signature
    is probed in THIS process -- a server-side probe would describe the
    server's flexicon, not this worker's.

    Used by the CP4 filing worker. The read worker keeps its own inline copy
    in `_RealBackend.open`, because `tests/test_issue159_openproject_ui_kwarg.py`
    pins that method's source; the two must stay in step.
    """
    import flexicon as _flexicon_pkg

    caps = getattr(_flexicon_pkg, "CAPABILITIES", frozenset())
    lcm_ui = None
    if "ui-injection" in caps:
        try:
            from flexicon import HeadlessLcmUI

            lcm_ui = HeadlessLcmUI()
        except ImportError:
            _log(
                "flexicon advertises ui-injection but HeadlessLcmUI is not "
                "importable; OpenProject will omit ui=."
            )
    else:
        _log(
            "flexicon build does not advertise ui-injection in CAPABILITIES; "
            "OpenProject will omit ui=."
        )
    try:
        import inspect

        accepts_ui = "ui" in inspect.signature(flex_project_class.OpenProject).parameters
    except Exception:  # noqa: BLE001
        accepts_ui = False
    if not accepts_ui:
        _log(
            "this flexicon build's OpenProject() does not accept the ui= "
            "argument; opening with this build's default LCM UI instead "
            "(issue #159)."
        )
        return {}
    return {"ui": lcm_ui}


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

    def is_open(self) -> bool:
        """Is the project currently open (#223)?"""
        return self._project is not None

    def open(self) -> None:
        """Open the project read-only.

        Called at worker startup, AND -- since #223 -- again whenever
        `ParseWorker._ensure_project_open()` finds the project closed
        because it was released while idle (`release()` below). Safe to
        call repeatedly in one process: `FLExInitialize()` / `Sldr.Initialize()`
        are documented as no-ops when already initialized
        (`flexicon/code/FLExInit.py`, "repeated FLExInitialize() calls [are]
        a no-op -- examples and per-test setUp rely on that"), and each call
        here constructs a brand-new `FLExProject()` / `LcmCache`, which is
        exactly what makes `ParserOperations._CurrentHandle` discard and
        rebuild the grammar automatically on the next `project.Parser` call
        (`flexicon/code/Parser/ParserOperations.py`, `_parser_cache is not
        cache`) -- no special "reload the grammar" code is needed on our
        side for that part.

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
        """Close the project and drop the grammar. Safe to call twice.

        #223: also called between requests now, whenever the worker goes
        idle with nothing in flight -- not only once, at the end of the
        worker's whole life. That makes `_wordforms_by_ws` (`_wordform_index`
        above) load-bearing to clear here: its entries are live
        `IWfiWordform` objects read off `project.Wordforms.GetAll()`
        (`_wordform_index`, this class), bound to THIS `LcmCache`. A later
        `open()` builds a brand-new cache (`FLExProject()` + `OpenProject()`
        again), so reusing them would touch objects the disposed cache
        already tore down. The grammar itself needs no matching code here:
        `ParserOperations._CurrentHandle` already discards and rebuilds it
        by comparing cache identity (see `open()`'s docstring) the next
        time anything asks `project.Parser` for a fresh `self._project`.

        `_occurrence` (`_segment_occurrence`, this class) is the same shape
        of bug as `_wordforms_by_ws`, found in QC after the idle-release
        change shipped: it is a join built from live LCM objects
        (`_iter_segments`'s `IStTxtPara`/segment objects) read off THIS
        cache, and its own docstring says "held for the worker's life" --
        which stopped being true the moment release-on-idle made
        "the worker's life" outlive any one open project. Left uncleared,
        a reopened worker would serve a segment-occurrence join built
        against a cache that no longer exists, for every FR-043 currency
        check made against the new one. Cleared here for the same reason
        `_wordforms_by_ws` is.
        """
        self._grammar_loaded = False
        self._wordforms_by_ws = None
        self._occurrence = None
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

    def parse_raw(self, wordform: str) -> Any:
        """The parser's own `ParseResult`, live objects and all (CP4, R-04).

        What FieldWorks' filer takes: analyses holding live `IMoForm` /
        `IMoMorphSynAnalysis` references, never reduced to plain data. Only the
        FILING worker calls this -- it lives here, in the one module allowed
        to parse (FR-026), so the filing spine reaches the parser through the
        same facade and the same code, and never on its own. A stale grammar
        is reloaded by the facade first; `None` means the morpher could not be
        built (`HCParser.cs:89-90`).
        """
        return self._project.Parser.ParseWord(wordform)

    def grammar_is_current(self) -> bool:
        """`IsUpToDate()`, asked as a question (see `ensure_grammar`)."""
        return bool(self._project.Parser.IsUpToDate())

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
        a batch reads and held while the project stays open -- `release()`
        clears it (#223: a released/reopened worker gets a new cache, and
        this join is built from objects bound to the old one).
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

    # -- CP4: the filing preflight's reads --------------------------------
    #
    # Delegated to `server/filing/preflight_reads.py` and `filing/eligibility.py`
    # (see the protocol notes at the top of this module): the filing spine's
    # reads run in this process because it holds the open project, and are
    # kept out of this package so the read spine stays provably what it was.

    def agent_facts(self) -> dict[str, Any]:
        from ..filing.preflight_reads import agent_facts

        return agent_facts(self._project, self.active_engine())

    def filing_preview(self, words: list, vernacular_ws: Optional[str]) -> dict[str, Any]:
        from ..filing.preflight_reads import preview_facts

        return preview_facts(self, list(words), vernacular_ws)

    def gate_probe(
        self, probe_word: Optional[str], vernacular_ws: Optional[str]
    ) -> tuple[Optional[float], bool]:
        """A current grammar, and whether the parser could be built (FR-020).

        `ensure_grammar` says whether the next parse will pay for a load; the
        probe parse then performs it (the facade reloads a stale grammar
        itself). `ParseWord` returns null when the morpher could not be
        built (`HCParser.cs:89-90`), which the facade passes through (R-04).
        """
        started = time.time()
        loaded = self.ensure_grammar("filing-gate")
        if not probe_word:
            return (started if loaded else None), False
        result = self._project.Parser.ParseWord(probe_word)
        return (started if loaded else None), result is None

    def eligible_entries(self) -> dict[str, Any]:
        try:
            from ..filing.eligibility import eligible_entries
        except ImportError:
            return {"known": False, "entries": []}
        try:
            return {"known": True, "entries": eligible_entries(self._project)}
        except Exception as exc:  # noqa: BLE001 -- unknown, never "none eligible"
            _log(f"eligibility read failed: {exc}")
            return {"known": False, "entries": []}
