#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The filing preflight's READS, answered by the read-only worker (parser-check
CP4; FR-025, FR-010..FR-015, FR-020..FR-023, FR-039; R-02, R-13).

WHY THESE RUN IN THE READ WORKER. A preview must be built without opening the
project for writing (FR-005) and without spawning the filing worker (SC-001).
The one process with the project open is the read worker, opened
`writeEnabled=False` -- so the preview's three questions are put to it:

  * `agent_facts`   -- is the HermitCrab parser agent resolvable? (FR-025)
  * `preview_facts` -- per word in scope, every stored analysis, its user
                       opinion, whether the parser has evaluated it, and
                       whether a text segment uses it, through a FRESH join
                       (R-02);
  * the gate's inputs are assembled by the worker itself
    (`ParseWorker._answer_filing_gate`), because they depend on the held
    grammar and its load-error baseline, which the worker owns.

WHY THE CODE LIVES HERE AND NOT IN `server/parse/`. The read spine carries a
standing structural guarantee that it never names the agent probe (CP2b
FR-016: try-a-word resolves no agent) and never writes. These reads are the
FILING spine's, run in the read worker's process only because that process
holds the open project, and only when the filing handler asks. Keeping them in
the filing package keeps `server/parse/` exactly as provable as it was; the
worker only dispatches the three message types here.

EVERYTHING HERE READS. Nothing creates, deletes, evaluates or saves; the
inverse confinement test holds this module to no write call, the same scan
the read spine is held to.
"""

from __future__ import annotations

import unicodedata
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from . import projection

__all__ = [
    "agent_facts",
    "user_agent_opinion",
    "stored_analyses",
    "preview_facts",
]


def agent_facts(flex_project: Any, active_engine: Optional[str]) -> Dict[str, Any]:
    """The HermitCrab agent probe over the open project (FR-025, R-13).

    `parser_probe.probe_hc_agent` reads one property off the LANGUAGE PROJECT's
    cache (`flex_project.project` is the `LcmCache`), and turns the documented
    `KeyNotFoundException` into `state: "absent"` with the
    `parser_agent_missing` fields. It is the probe's first production caller.
    """
    from ..parser_probe import probe_hc_agent

    return asdict(probe_hc_agent(flex_project.project, active_engine))


_OPINION_NAMES = {"approves": "approves", "disapproves": "disapproves", "noopinion": "noopinion"}


def _opinion_name(value: Any) -> str:
    """An LCM `Opinions` value as its name. By NAME, never by number: the
    enum's integer values are an implementation detail of liblcm."""
    text = str(value).rsplit(".", 1)[-1].strip().lower()
    return _OPINION_NAMES.get(text, "unreadable")


def user_agent_opinion(flex_project: Any, analysis: Any) -> str:
    """The DEFAULT USER AGENT's opinion -- the one the filer reads.

    `SetUnsuccessfulParseEvals` asks `analysis.GetAgentOpinion(m_userAgent)`
    with `m_userAgent = LanguageProject.DefaultUserAgent`
    (`ParseFiler.cs:116, 314`), so the preview asks the same agent. Where that
    cannot be read, the human approval status (any human evaluation) is the
    fallback, and failing that the opinion is `unreadable` -- which the
    projection counts toward the bound.
    """
    try:
        user_agent = flex_project.lp.DefaultUserAgent
        return _opinion_name(analysis.GetAgentOpinion(user_agent))
    except Exception:  # noqa: BLE001 -- fall back, then report unreadable
        pass
    try:
        status = int(flex_project.WfiAnalyses.GetApprovalStatus(analysis))
        return {2: "approves", 0: "disapproves", 1: "noopinion"}.get(status, "unreadable")
    except Exception:  # noqa: BLE001
        return "unreadable"


def _fresh_wordform_index(flex_project: Any, ws: int) -> Tuple[Dict[str, Any], int]:
    """NFC form -> wordform, built NOW (not the worker-lifetime cache), and
    how many wordforms' forms could not be read.

    A wordform created since the read worker built its cache must be found:
    missing it would under-project, and the preview errs the other way. For
    the same reason an unreadable form is COUNTED, not skipped: while any is
    unreadable, a word the index lacks may be that wordform.
    """
    index: Dict[str, Any] = {}
    unreadable = 0
    for wordform in flex_project.Wordforms.GetAll():
        try:
            form = flex_project.Wordforms.GetForm(wordform, ws)
        except Exception:  # noqa: BLE001 -- counted: see the docstring
            unreadable += 1
            continue
        form = unicodedata.normalize("NFC", str(form or "")).strip()
        if form:
            index.setdefault(form, wordform)
    return index, unreadable


def stored_analyses(
    backend: Any, words: List[str], vernacular_ws: Optional[str]
) -> Dict[str, Optional[List[Dict[str, Any]]]]:
    """Every stored analysis of every word, as plain facts.

    `backend` is the read worker's `_RealBackend`; its own readers are reused
    (the writing-system handle, the evaluation-facts read) rather than
    re-implemented. A word with no wordform in the project maps to None; a
    word whose analyses (or whose lookup) could not be read maps to
    `projection.UNREADABLE` -- never to an empty list, which would assert
    "nothing to delete" for a word nobody could see into.
    """
    flex_project = backend._project
    ws = backend._ws_handle(vernacular_ws)
    index, forms_unreadable = _fresh_wordform_index(flex_project, ws)
    stored: Dict[str, Any] = {}
    for word in words:
        target = index.get(unicodedata.normalize("NFC", word).strip())
        if target is None:
            stored[word] = projection.UNREADABLE if forms_unreadable else None
            continue
        records: List[Dict[str, Any]] = []
        try:
            analyses = list(flex_project.WfiAnalyses.GetAll(target))
        except Exception:  # noqa: BLE001 -- unreadable, not empty
            stored[word] = projection.UNREADABLE
            continue
        for analysis in analyses:
            guid = getattr(analysis, "Guid", None)
            if guid is None:
                continue
            _evaluator, _at, parser_evaluated = backend._evaluation_facts(analysis)
            records.append({
                "analysis_guid": str(guid).lower(),
                "user_opinion": user_agent_opinion(flex_project, analysis),
                "parser_evaluated": bool(parser_evaluated),
            })
        stored[word] = records
    return stored


def preview_facts(
    backend: Any, words: List[str], vernacular_ws: Optional[str]
) -> Dict[str, Any]:
    """The preview's per-word facts, with a FRESH segment join (R-02)."""
    stored = stored_analyses(backend, words, vernacular_ws)
    occurrence = projection.fresh_occurrence(backend._iter_segments)
    return {
        "words": projection.attach_segment_use(stored, occurrence),
        "join_known": occurrence.known,
    }
