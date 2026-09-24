#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The FILING worker: the one process that opens a project for writing
(parser-check CP4, FR-017..FR-019, FR-024, FR-029, FR-031, FR-034; research
R-03, R-05, R-09).

    python -m flextoolsmcp.server.filing.worker_filing --project "<name>"

THE ONLY WRITABLE OPEN. This module holds the parser area's single
`OpenProject(..., writeEnabled=True)`, pinned by
`tests/test_filing_write_confinement.py`. The read worker, its module and its
standing no-write tests are exactly as they were: this is a DIFFERENT worker,
spawned for one filing run under the filing package's own pool role and
released when the run ends.

IT IS AN ORDINARY WORKER OTHERWISE. It speaks the read worker's protocol --
the same `ParseWorker` loop, the same one-message-per-word, the same
word-boundary cancellation, the same reader thread -- plus three messages:

    {"type": "filing_setup",  "request_id", "run_id", "setup": {...}}
        -> {"type": "filing_ready", "request_id"}
    {"type": "filing_commit", "request_id", "run_id"}
        -> {"type": "filing_committed", "request_id", "ok": bool, "error"}
    {"type": "parse", ..., "level": "file"}   -- parse AND file one word

and it parses through the read backend's own `parse_raw`, in the one module
allowed to parse (FR-026), so the filing spine reaches the parser through the
same facade and never on its own.

PER WORD (`FilingBackend.parse`):

  1. THE GATE ON EVERY GRAMMAR LOAD (FR-024, R-05). The facade reloads a stale
     grammar silently before any parse. So before each word the worker asks
     `IsUpToDate()`; on the first word, and on every stale grammar, it reloads
     explicitly and re-runs the WHOLE refuse-to-file gate -- morpher null, the
     load-error diff, the eligibility diff -- against the confirmed call's own
     load (`baseline_source: "this_run"`). A refusal ends the run at that word
     boundary, `refused_midrun`, having asked nobody anything; what was filed
     already is persisted and reported.
  2. THE PARSE -- the raw `ParseResult`, live objects and all (R-04).
  3. THE FILING -- `classify.file_word`: liveness, the R-02 guard against the
     confirmed projection, the captures (fsynced to the run record BEFORE the
     pump), the pump through a fresh `ParseFiler` and a paused `IdleQueue`,
     and the before/after outcome.
  4. PERSISTENCE -- saved at intervals while the run goes, so a crash loses
     at most the last interval (and the record says which words were saved),
     and always on `filing_commit`, before the runner reports any terminal
     state (FR-034).

NO UNIT OF WORK IS HELD OPEN. The project is opened in flexicon's
per-operation mode (`undoable` left at its default), so there is no
session-long task: `ParseFiler` opens its own unit of work for each word, and
`CanStartUow` is true when it asks. A session-long task would make the filer
decline every word.

TEARDOWN reuses #147's step (`106a2ff`): `RefreshFromDisk` before
`CloseProject`, gated on the same flexicon `refresh-from-disk` capability, so
a foreign save during the run does not leave a stale cache to be committed
over it.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import threading
import time
import traceback
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..parse.worker_main import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    PROTOCOL_VERSION,
    ParseWorker,
    _clr_list,
    _emit,
    _force_utf8_stdio,
    _guid,
    _idle_timeout_from_env,
    _log,
    _multi_text,
    _reader_thread,
    _RealBackend,
    _structured_analysis,
    _StubBackend,
    headless_ui_kwargs,
)
from . import classify, filer, gate, paths

__all__ = ["FilingBackend", "FilingWorker", "FilingRefusal", "main"]

#: How often filed words are saved while a run goes (seconds). A crash loses
#: at most this much work; every terminal state saves regardless.
DEFAULT_SAVE_INTERVAL_SECONDS = 15.0
_ENV_SAVE_INTERVAL = "FLEXTOOLSMCP_FILING_SAVE_SECONDS"



def filing_ui_kwargs(flex_project_class: Any) -> Dict[str, Any]:
    """`headless_ui_kwargs`, with an `ILcmUI` whose `SynchronizeInvoke` is real.

    flexicon's `HeadlessLcmUI` returns None from `SynchronizeInvoke`, which
    its own docstring says is safe only while nothing subscribes to LCM's
    change notifications. The filing worker breaks that premise: the
    `HCParser` it builds registers a `ParserModelChangeListener`, so when
    FieldWorks' filer ends its unit of work, `SendPropChangedNotifications`
    dereferences the null invoker and the word dies with a
    NullReferenceException (found live by CP4 L-0; evidence/l0-coexistence.json).

    `SingleThreadedSynchronizeInvoke` (SIL.LCModel.Utils) reports
    `InvokeRequired = False`, so notifications run inline on the calling
    thread -- the filing worker's only LCM thread. Every other decision stays
    `HeadlessLcmUI`'s: non-blocking, and a conflicting save still raises.
    """
    kwargs = dict(headless_ui_kwargs(flex_project_class))
    if kwargs.get("ui") is None:
        return kwargs
    try:
        kwargs["ui"] = _filing_lcm_ui()
    except Exception as exc:  # noqa: BLE001 -- keep the headless UI, and say so
        _log(f"filing UI unavailable, using HeadlessLcmUI: {type(exc).__name__}: {exc}")
    return kwargs


_FILING_UI_CLASS: Any = None


def _filing_lcm_ui() -> Any:
    global _FILING_UI_CLASS
    if _FILING_UI_CLASS is None:
        import clr  # type: ignore[import-not-found]
        from flexicon import HeadlessLcmUI  # type: ignore[import-not-found]

        clr.AddReference("SIL.LCModel.Utils")
        from SIL.LCModel.Utils import SingleThreadedSynchronizeInvoke  # type: ignore

        class FilingLcmUI(HeadlessLcmUI):
            __namespace__ = "FlexToolsMCP.Filing"

            def __init__(self):
                super().__init__()
                self._invoker = SingleThreadedSynchronizeInvoke()

            @property
            def SynchronizeInvoke(self):
                return self._invoker

            def get_SynchronizeInvoke(self):
                return self._invoker

        _FILING_UI_CLASS = FilingLcmUI
    return _FILING_UI_CLASS()


class FilingRefusal(Exception):
    """A coded refusal the worker channel carries to the runner unchanged.

    `detail` is shaped like the matching response model, `error_code` first;
    `_report_exception` marshals it, and the runner ends the run with it.
    """

    def __init__(self, message: str, detail: Dict[str, Any]) -> None:
        super().__init__(message)
        self.detail = detail


def _save_interval() -> float:
    raw = os.environ.get(_ENV_SAVE_INTERVAL)
    try:
        return float(raw) if raw else DEFAULT_SAVE_INTERVAL_SECONDS
    except ValueError:
        return DEFAULT_SAVE_INTERVAL_SECONDS


def _opinion_name(value: Any) -> str:
    text = str(value).rsplit(".", 1)[-1].strip().lower()
    return text if text in ("approves", "disapproves", "noopinion") else "unreadable"


def _maybe_refresh_from_disk(project: Any) -> None:
    """#147 (`106a2ff`): reconcile with a foreign save before CloseProject.

    The same capability gate as run_module's runner uses; a build without
    `refresh-from-disk` is left alone. Never raises.
    """
    try:
        import flexicon

        if "refresh-from-disk" not in getattr(flexicon, "CAPABILITIES", ()):
            return
        refresh = getattr(project, "RefreshFromDisk", None)
        if callable(refresh):
            refresh()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# One word's live objects, as the classifier needs them
# ---------------------------------------------------------------------------


class LiveWord:
    """`classify.WordSurface` over one LCM wordform and its fresh parse."""

    def __init__(self, backend: "FilingBackend", wordform: str, wf: Any, result: Any,
                 duplicate_budget: int) -> None:
        self.wordform = wordform
        self._backend = backend
        self._wf = wf
        self._result = result
        self._duplicate_budget = duplicate_budget
        self._duplicates_used = 0

    # -- reads --------------------------------------------------------------

    def is_valid(self) -> bool:
        try:
            return bool(self._wf is not None and self._wf.IsValidObject and self._result.IsValid)
        except Exception:  # noqa: BLE001 -- unreadable is not valid
            return False

    def checksum_matches(self) -> bool:
        try:
            return int(self._wf.Checksum) == int(self._result.GetHashCode())
        except Exception:  # noqa: BLE001
            return False

    def errored(self) -> bool:
        return getattr(self._result, "ErrorMessage", None) is not None

    def _segment_refs(self) -> Optional[set]:
        """GUIDs every segment of this wordform's occurrences references.

        The filer's own source for "in use" -- `wordform.OccurrencesBag`,
        each segment's `AnalysesRS` (`ParseFiler.cs:304-306`). None when it
        cannot be read: an unreadable join is UNKNOWN, never "no segment
        uses anything" (which would unshield every analysis at once).
        """
        refs = set()
        try:
            for segment in list(self._wf.OccurrencesBag):
                for item in list(segment.AnalysesRS):
                    guid = _guid(item)
                    if guid:
                        refs.add(guid)
        except Exception:  # noqa: BLE001 -- unknown, not empty
            return None
        return refs

    def _analyses(self) -> List[Any]:
        return _clr_list(getattr(self._wf, "AnalysesOC", None))

    def existing(self) -> List[Dict[str, Any]]:
        refs = self._segment_refs()
        errored = self.errored()
        parsed = [] if errored else _clr_list(getattr(self._result, "Analyses", None))
        facts = []
        for analysis in self._analyses():
            guid = _guid(analysis)
            if not guid:
                continue
            glosses = {_guid(g) for g in _clr_list(getattr(analysis, "MeaningsOC", None))}
            matched = False
            for candidate in parsed:
                with contextlib.suppress(Exception):
                    if candidate.MatchesIWfiAnalysis(analysis):
                        matched = True
                        break
            facts.append({
                "analysis_guid": guid,
                "user_opinion": self._backend.user_opinion(analysis),
                "in_use": None if refs is None else (guid in refs or bool(glosses & refs)),
                "matched": matched,
            })
        return facts

    def _find(self, guid: str) -> Any:
        for analysis in self._analyses():
            if _guid(analysis) == guid:
                return analysis
        return None

    def capture(self, guid: str) -> Dict[str, Any]:
        """Enough of the analysis to recognise and rebuild it (FR-031)."""
        analysis = self._find(guid)
        vern, anal = self._backend.writing_systems()
        out: Dict[str, Any] = {"morph_bundles": [], "glosses": [], "evaluations": [],
                               "category": ""}
        if analysis is None:
            return out
        for bundle in _clr_list(getattr(analysis, "MorphBundlesOS", None)):
            out["morph_bundles"].append({
                "morph_guid": _guid(getattr(bundle, "MorphRA", None)),
                "msa_guid": _guid(getattr(bundle, "MsaRA", None)),
                "infl_type_guid": _guid(getattr(bundle, "InflTypeRA", None)),
                "form": _multi_text(getattr(bundle, "Form", None), vern) if vern else "",
            })
        for gloss in _clr_list(getattr(analysis, "MeaningsOC", None)):
            out["glosses"].append({
                "guid": _guid(gloss),
                "form_by_ws": {str(anal): _multi_text(getattr(gloss, "Form", None), anal)}
                if anal else {},
            })
        for evaluation in _clr_list(getattr(analysis, "EvaluationsRC", None)):
            agent = getattr(evaluation, "Owner", None)
            with contextlib.suppress(Exception):
                from SIL.LCModel import ICmAgent  # type: ignore[import-not-found]

                agent = ICmAgent(agent)
            approves = getattr(evaluation, "Approves", None)
            out["evaluations"].append({
                "agent_guid": _guid(agent),
                "agent_name": _multi_text(getattr(agent, "Name", None), anal) if anal else "",
                "human": bool(getattr(agent, "Human", False)),
                "opinion": ("approves" if approves else "disapproves") if approves is not None
                else "unreadable",
                "date": str(getattr(evaluation, "DateCreated", "") or ""),
            })
        category = getattr(analysis, "CategoryRA", None)
        if category is not None and anal:
            out["category"] = _multi_text(getattr(category, "Abbreviation", None), anal)
        return out

    # -- the write -----------------------------------------------------------

    def pump(self) -> str:
        return filer.file_one(
            surface=self._backend.clr_surface,
            cache=self._backend.cache,
            agent=self._backend.parser_agent,
            wordform=self._wf,
            parse_result=self._result,
        ).outcome

    def after(self) -> List[Dict[str, Any]]:
        return [
            {"analysis_guid": _guid(a), "user_opinion": self._backend.user_opinion(a)}
            for a in self._analyses() if _guid(a)
        ]

    def is_duplicate(self, guid: str) -> bool:
        """CP3's pairing predicate, counted (FR-016): a created analysis
        duplicates a gloss-only record when CP3 would have paired them."""
        if self._duplicates_used < self._duplicate_budget:
            self._duplicates_used += 1
            return True
        return False


# ---------------------------------------------------------------------------
# The backend
# ---------------------------------------------------------------------------


class FilingBackend(_RealBackend):
    """The read backend's readers, with a writable open and the filing path."""

    def __init__(self, project_name: str) -> None:
        super().__init__(project_name)
        self.clr_surface: Any = None
        self.parser_agent: Any = None
        self._surface_problem: Optional[Dict[str, Any]] = None
        self._ctx: Optional[classify.FilingContext] = None
        self._reference: Optional[gate.Baseline] = None
        self._gated_once = False
        self._reloads = 0
        self._last_save = time.monotonic()
        self._save_interval = _save_interval()
        self._wordforms: Optional[Dict[str, Any]] = None
        self._user_agent: Any = None

    # -- lifetime -------------------------------------------------------------

    def open(self) -> None:
        """Probe the filing surface, THEN open the project for writing.

        Every member this worker binds is probed first (R-03); if any is
        missing the project is NOT opened, and `filing_setup` refuses with
        `parser_core_missing`. Nothing is ever opened for writing that the
        worker could not then file through.
        """
        from flexicon import FLExInitialize, FLExProject

        FLExInitialize()
        self._initialized = True
        try:
            self.clr_surface = filer.ClrFilerSurface()
            missing = filer.probe_bound_members(self.clr_surface.namespace())
        except Exception as exc:  # noqa: BLE001 -- reported as a refusal at setup
            self._surface_problem = {"signal": "load_failed", "missing_members": [],
                                     "load_error": f"{type(exc).__name__}: {exc}"}
            return
        if missing:
            self._surface_problem = {"signal": "incompatible_surface",
                                     "missing_members": missing, "load_error": None}
            return

        project = FLExProject()
        # THE ONE WRITABLE OPEN (FR-029). `undoable` is left at its default --
        # flexicon's per-operation mode -- so no session-long unit of work is
        # open and the filer's own `CanStartUow` holds.
        project.OpenProject(
            projectName=self._project_name,
            writeEnabled=True,
            **filing_ui_kwargs(FLExProject),
        )
        self._project = project

    def release(self) -> None:
        if self._project is not None:
            _maybe_refresh_from_disk(self._project)
        super().release()

    @property
    def cache(self) -> Any:
        return self._project.project

    def writing_systems(self) -> tuple:
        vern = anal = None
        with contextlib.suppress(Exception):
            vern = int(self._project.GetDefaultVernacularWSHandle())
        with contextlib.suppress(Exception):
            anal = int(self._project.GetDefaultAnalysisWSHandle())
        return vern, anal

    def user_opinion(self, analysis: Any) -> str:
        """The DEFAULT USER AGENT's opinion -- the one the filer reads."""
        try:
            if self._user_agent is None:
                self._user_agent = self._project.lp.DefaultUserAgent
            return _opinion_name(analysis.GetAgentOpinion(self._user_agent))
        except Exception:  # noqa: BLE001
            return "unreadable"

    # -- setup ------------------------------------------------------------------

    def setup(self, run_id: str, setup: Dict[str, Any]) -> None:
        """Bind this worker to one confirmed run. Raises a `FilingRefusal`."""
        if self._surface_problem is not None:
            detail = filer.SurfaceProbe(ok=False, **self._surface_problem).refusal_detail()
            raise FilingRefusal(
                "Filing is unavailable: FieldWorks' parse filer could not be bound in "
                "the filing worker. Nothing was opened for writing.",
                {"error_code": "parser_core_missing", **detail},
            )
        record_root = Path(setup["record_root"])
        paths.assert_outside_project(record_root)
        from ..parse.record import RunRecord

        record = RunRecord(run_id, record_dir=record_root.parent)

        def _sink(line: Dict[str, Any]) -> None:
            record.append_jsonl(paths.DELETIONS_RELPATH, line,
                                guard=paths.assert_outside_project)

        self._ctx = classify.FilingContext(
            projection={w: list(g) for w, g in (setup.get("projection") or {}).items()},
            overwrites={w: list(g) for w, g in (setup.get("overwrites") or {}).items()},
            sink=_sink,
        )
        self._reference = gate.reference_from(setup.get("gate_reference") or {})
        self.parser_agent = self._resolve_hc_agent()

    def _resolve_hc_agent(self) -> Any:
        """The HermitCrab agent BY GUID, as `ParserWorker.cs:71` resolves it."""
        from SIL.LCModel import CmAgentTags, ICmAgentRepository  # type: ignore

        repository = self._project.ObjectRepository(ICmAgentRepository)
        try:
            return repository.GetObject(CmAgentTags.kguidAgentHermitCrabParser)
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ != "KeyNotFoundException":
                raise
            raise FilingRefusal(
                "The HermitCrab parser agent could not be resolved in the filing worker.",
                {
                    "error_code": "parser_agent_missing",
                    "agent_guid": "kguidAgentHermitCrabParser",
                    "agent_name": "HermitCrab",
                    "active_engine": self.active_engine() or "HC",
                    "probe_source": "lookup_failed",
                    "hint": (
                        "The HermitCrab parser agent was not found by its GUID. Open the "
                        "project in FieldWorks with the HC parser active and run Try a "
                        "Word once so FieldWorks creates it, then retry."
                    ),
                },
            ) from exc

    # -- per word ---------------------------------------------------------------

    def _wordform_for(self, word: str, ws: int) -> Any:
        if self._wordforms is None:
            self._wordforms = {}
            for wordform in self._project.Wordforms.GetAll():
                with contextlib.suppress(Exception):
                    form = self._project.Wordforms.GetForm(wordform, ws)
                    form = unicodedata.normalize("NFC", str(form or "")).strip()
                    if form:
                        self._wordforms.setdefault(form, wordform)
        return self._wordforms.get(unicodedata.normalize("NFC", word).strip())

    def _gated_parse(self, word: str) -> Any:
        """The raw parse, with the gate re-run on EVERY grammar load (R-05)."""
        if not self._gated_once:
            started = time.time()
            result = self.parse_raw(word)
            self._gated_once = True
            self._check_gate(started, result)
            return result
        if not self.grammar_is_current():
            started = time.time()
            self.reload_grammar()
            result = self.parse_raw(word)
            self._reloads += 1
            # R-05 / Q3: a reload mid-run means the grammar changed under the
            # run -- or that filing itself marks it stale. Either way, say so.
            _log(f"filing: grammar reloaded mid-run before {word!r} (reload {self._reloads})")
            self._check_gate(started, result)
            return result
        return self.parse_raw(word)

    def _check_gate(self, started: float, result: Any) -> None:
        current = {
            "morpher_null": result is None,
            "load": self.load_error_baseline(started),
            "eligible": self.eligible_entries(),
        }
        standing = gate.evaluate(current, self._reference)
        if standing.refused:
            raise FilingRefusal(
                standing.message(),
                {"error_code": "grammar_load_unclean", **standing.refusal_detail()},
            )

    def parse(
        self,
        wordform: str,
        level: str,
        restricted_to: Optional[tuple] = None,
        *,
        vernacular_ws: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse AND file one word. The filing worker has no read levels."""
        if level != "file":
            raise ValueError("The filing worker files; it answers no read-only level.")
        if self._ctx is None:
            raise FilingRefusal("No filing run was set up.",
                                {"error_code": "runtime_error", "error_type": "NotSetUp"})
        result = self._gated_parse(wordform)
        if result is None:
            self._check_gate(time.time(), None)  # morpher null: always refused

        ws = self._ws_handle(vernacular_ws)
        analysis_ws = self._analysis_ws()
        line: Dict[str, Any] = {
            "analyses": [_structured_analysis(a, ws, analysis_ws)
                         for a in _clr_list(getattr(result, "Analyses", None))],
            "error_message": (str(result.ErrorMessage)
                              if getattr(result, "ErrorMessage", None) else None),
        }
        line["parsed"] = bool(line["analyses"])
        line["analysis_count"] = len(line["analyses"])
        try:
            line["human_analyses"] = self._human_analyses(wordform, ws)
        except Exception:  # noqa: BLE001 -- reporting only; never blocks filing
            line["human_analyses"] = []
        from ..signals.pairing import candidate_pairings

        try:
            budget = len(candidate_pairings({"wordform": wordform, "parse": line}))
        except Exception:  # noqa: BLE001
            budget = 0

        wf = self._wordform_for(wordform, ws)
        try:
            outcome = classify.file_word(
                self._ctx, LiveWord(self, wordform, wf, result, budget)
            )
        except FilingRefusal:
            raise
        except Exception as exc:  # noqa: BLE001 -- ends the run; never a silent skip
            # A CLR exception's own stack is the only pointer into FieldWorks'
            # code; the Python traceback stops at the pump.
            clr_stack = str(getattr(exc, "StackTrace", "") or "")
            raise FilingRefusal(
                f"Filing {wordform!r} failed: {type(exc).__name__}: {exc}"
                + (f" [CLR stack: {clr_stack.strip()[:1500]}]" if clr_stack else ""),
                {"error_code": "runtime_error", "error_type": type(exc).__name__,
                 "traceback": traceback.format_exc(), "clr_stack": clr_stack or None},
            ) from exc
        outcome["persisted"] = self._maybe_save()
        line["filing"] = outcome
        return {"parse": line, "trace_xml": None}

    # -- persistence (FR-034) -------------------------------------------------

    def _maybe_save(self) -> bool:
        if time.monotonic() - self._last_save < self._save_interval:
            return False
        self.commit()
        return True

    def commit(self) -> None:
        """Save every change made so far. Raises on failure.

        On the XML backend this HANDS the write to LCM's background commit
        thread; the bytes reach disk later. Interval saves accept that. The
        run's last save does not -- see `final_commit`.
        """
        self._project.SaveChanges()
        self._last_save = time.monotonic()

    def final_commit(self) -> None:
        """The run's last save: save, then close the project. Raises on failure.

        `filing_commit` is always the run's last request, and the runner
        reports a terminal state only after it answers. Closing here -- the
        #147 teardown, `RefreshFromDisk` then `CloseProject`, whose dispose
        completes every pending commit -- makes `ok` mean "on disk, and the
        project released". Found live (CP4 Q5): after a bare `SaveChanges`
        the run was reported `completed`/`persisted` while the file on disk
        was still the pre-run file, and the claim cleared while this worker
        still held the project's lock.
        """
        self.commit()
        project = self._project
        if project is not None:
            _maybe_refresh_from_disk(project)
            # NOT the base `release()`, which logs a failed close and moves
            # on: a close that fails here is a save that may not have landed.
            project.CloseProject()
            self._project = None
        self.release()   # the rest of the teardown; the project is already closed


class StubFilingBackend(_StubBackend):
    """Files nothing: every word reports `filed`. The offline stub (--stub)."""

    def setup(self, run_id: str, setup: Dict[str, Any]) -> None:
        paths.assert_outside_project(Path(setup["record_root"]))

    def parse(self, wordform, level, restricted_to=None, *, vernacular_ws=None):
        if level != "file":
            raise ValueError("The filing worker files; it answers no read-only level.")
        if self._parse_seconds:
            time.sleep(self._parse_seconds)
        counts = classify.empty_counts()
        counts["reapproved"] = 1
        return {"parse": {"parsed": True, "analysis_count": 1, "analyses": [],
                          "error_message": None,
                          "filing": {"wordform": wordform, "outcome": "filed",
                                     "skip_reason": None, "errored": False,
                                     "counts": counts, "deleted": [], "created": [],
                                     "overwritten": [], "in_use_approvals_recorded": 0,
                                     "persisted": False}},
                "trace_xml": None}

    def commit(self) -> None:
        return None

    def final_commit(self) -> None:
        return None


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


class FilingWorker(ParseWorker):
    """`ParseWorker`, plus the two messages only a filing worker answers."""

    _FILING_CONTROLS = ("filing_setup", "filing_commit")

    def handle_message(self, message: Dict[str, Any]) -> None:
        if message.get("type") in self._FILING_CONTROLS:
            self._deadline = time.monotonic() + self._idle_timeout
            with self._resolve_lock:
                self._control_pending.append(message)
            return
        super().handle_message(message)

    def _drain_controls(self) -> None:
        with self._resolve_lock:
            pending = self._control_pending
            self._control_pending = [m for m in pending
                                     if m.get("type") not in self._FILING_CONTROLS]
            ours = [m for m in pending if m.get("type") in self._FILING_CONTROLS]
        for message in ours:
            request_id = message.get("request_id")
            run_id = message.get("run_id")
            try:
                if message.get("type") == "filing_setup":
                    self._backend.setup(str(run_id), dict(message.get("setup") or {}))
                    self._emit({"type": "filing_ready", "request_id": request_id})
                else:
                    ok, error = True, None
                    try:
                        self._backend.final_commit()
                    except Exception as exc:  # noqa: BLE001 -- reported, not raised
                        ok, error = False, f"{type(exc).__name__}: {exc}"
                    self._emit({"type": "filing_committed", "request_id": request_id,
                                "ok": ok, "error": error})
            except Exception as exc:  # noqa: BLE001 -- marshalled with its detail
                self._report_exception(exc, request_id, run_id)
        super()._drain_controls()

    def _send_baseline_once(self, run_id: str) -> None:
        """A filing run is never a gate baseline (gate.py): nothing to send."""
        return None


def main(argv: Optional[List[str]] = None) -> int:
    """Run one filing worker until shutdown, stdin close, or idle timeout."""
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="flextoolsmcp.server.filing.worker_filing",
        description="The FILING worker: one project, opened for writing, one run.",
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--idle-timeout", type=float, default=None)
    parser.add_argument("--stub", action="store_true")
    parser.add_argument("--parse-delay", type=float, default=0.0)
    args = parser.parse_args(argv)
    idle_timeout = (args.idle_timeout if args.idle_timeout is not None
                    else _idle_timeout_from_env(DEFAULT_IDLE_TIMEOUT_SECONDS))

    if args.stub:
        backend: Any = StubFilingBackend(parse_seconds=args.parse_delay)
    else:
        backend = FilingBackend(args.project)
        try:
            backend.open()
        except Exception as exc:  # noqa: BLE001 -- reported before `ready`
            _log(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            _emit({"type": "error", "request_id": None, "run_id": None,
                   "error_code": None, "detail": None,
                   "message": f"Failed to open project {args.project!r} for filing: "
                              f"{type(exc).__name__}: {exc}"})
            return 2

    worker = FilingWorker(args.project, backend=backend, idle_timeout=idle_timeout)
    _emit({"type": "ready", "protocol": PROTOCOL_VERSION, "project": args.project})
    reader = threading.Thread(target=_reader_thread, args=(worker,),
                              name="filing-worker-stdin", daemon=True)
    reader.start()
    try:
        reason = worker.run()
    finally:
        worker.release()
    _emit({"type": "bye", "reason": reason})
    return 0


if __name__ == "__main__":
    sys.exit(main())
