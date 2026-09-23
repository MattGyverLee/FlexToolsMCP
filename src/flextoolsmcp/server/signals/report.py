#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The batch report: every US5 signal over one finished artifact (parser-check
CP3, US5; FR-035..FR-050).

Reads `results.jsonl` lines and the run's recorded `project_state`; touches
no project and no engine. `flextools_parse_log` serves it inside the
`summary` section of a batch run -- the section list is frozen
(contracts/tools.md section 1), so the report is an additive key there, not
a new section.

Ordering inside a word follows FR-044/FR-045: candidate pairings first, then
the analyses in promotion-only order, then the lexicalization finding if
there is one.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .batch_signals import batch_signals
from .clustering import DrillDownBudget, cluster_words, suspect_words
from .oracle import build_oracle
from .pairing import candidate_pairings, human_gloss, lexicalization_finding
from .projections import deletion_projection, duplicate_projection
from .ranking import promote

__all__ = ["build_report"]


def _word_findings(line: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    parse = line.get("parse") or {}
    analyses = list(parse.get("analyses") or [])
    pairings = candidate_pairings(line)
    lexicalized = lexicalization_finding(line)
    gloss = human_gloss(parse)
    ranked = promote(analyses, gloss) if gloss else []
    if not (pairings or lexicalized or any(e["promoted"] for e in ranked)):
        return None
    entry: Dict[str, Any] = {"wordform": line.get("wordform")}
    entry["candidate_pairings"] = pairings  # first (FR-044)
    entry["ranked_analyses"] = [
        {
            "original_position": e["original_position"],
            "promoted": e["promoted"],
            "basis": e["basis"],
            "rendered_morphs": list(e["analysis"].get("rendered_morphs") or []),
        }
        for e in ranked
    ]
    if lexicalized:
        entry["lexicalization"] = lexicalized
    return entry


def build_report(
    results: Iterable[Dict[str, Any]],
    project_state: Optional[Dict[str, Any]],
    budget: Optional[DrillDownBudget] = None,
    offset: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """The whole US5 report. Per-analysis and per-word lists are paged."""
    lines = [
        row for row in results if (row.get("parse") or {}).get("analyses") is not None
    ]
    signals = batch_signals(lines)
    oracle = build_oracle(lines, project_state)
    if "analyses" in oracle:
        page = oracle["analyses"][offset:offset + limit]
        oracle["analyses_total"] = len(oracle["analyses"])
        oracle["analyses_offset"] = offset
        oracle["analyses"] = page
    words: List[Dict[str, Any]] = [
        w for w in (_word_findings(row) for row in lines) if w
    ]
    return {
        "signals": signals,
        "oracle": oracle,
        "words": words[offset:offset + limit],
        "words_total": len(words),
        "clusters": cluster_words(suspect_words(lines, signals), budget),
        "projections": [deletion_projection(lines), duplicate_projection(lines)],
    }
