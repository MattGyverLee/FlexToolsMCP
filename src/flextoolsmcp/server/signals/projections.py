#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Projections: what a future write WOULD do (parser-check CP3, US5; FR-050,
SC-015; data-model.md section 13).

COMPUTED, REPORTED, ACTED ON BY NOTHING. CP3 is entirely read-only (FR-063).
These two numbers are information about what CP4's write paths would touch;
nothing here deletes, files, confirms or stages anything, and there is no
part of the write ladder -- no confirmation step, no filing path, no
"apply" -- anywhere in this module or its callers.

THE DELETION PREDICATE HAS THREE CONJUNCTS, AND ALL THREE ARE REQUIRED:

    parser-created  AND  carrying no user opinion  AND  not referenced by any segment

A bare no-opinion projection drops the last one and counts analyses a text
is using -- deleting those would tear interlinear text. SC-015's fixture
(one segment-referenced candidate, one unreferenced) returns exactly one
here and two under the bare predicate, which is how the bare predicate
fails its test.

The segment conjunct reads `in_segment`, which the worker computed through
the ONE segment-occurrence join (`oracle.segment_occurrence`, FR-043). An
analysis whose segment use is unknown is NOT counted: "could not tell" never
rounds toward "safe to delete". Those are reported separately.

THE DUPLICATE PROJECTION counts filings that would duplicate an existing
meaning-only record: a candidate pairing (`pairing.candidate_pairings`) whose
human record already holds the meaning. Filing it as a new analysis instead
of completing that record would leave two.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .oracle import is_human_record
from .pairing import candidate_pairings

__all__ = ["deletion_projection", "duplicate_projection", "INFORMATION_NOTE"]

INFORMATION_NOTE = (
    "Projections are information only: they say what a later write would "
    "touch. Nothing in this checkpoint acts on them, and nothing has been "
    "changed in the project."
)


def _is_deletion_candidate(record: Dict[str, Any]) -> bool:
    return (
        not is_human_record(record)                    # parser-created
        and record.get("opinion") == "noopinion"       # no user opinion
        and record.get("in_segment") is False          # referenced by no segment
    )


def deletion_projection(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Stored analyses a deletion pass WOULD remove. Nothing is removed.

    NOT THE FILING BOUND: CP4's upper bound is `filing.projection.deletion_upper_bound`,
    because FLEx's filer also deletes human-made, never-evaluated, unused
    analyses, which the parser-created conjunct here excludes (CP4 R-01).
    """
    candidates: List[Dict[str, Any]] = []
    unknown = 0
    for line in results:
        for record in (line.get("parse") or {}).get("human_analyses") or []:
            if _is_deletion_candidate(record):
                candidates.append(
                    {
                        "wordform": line.get("wordform"),
                        "analysis_guid": record.get("analysis_guid"),
                        "rendered_morphs": list(record.get("rendered_morphs") or []),
                    }
                )
            elif (
                not is_human_record(record)
                and record.get("opinion") == "noopinion"
                and record.get("in_segment") is None
            ):
                unknown += 1
    out: Dict[str, Any] = {
        "projection": "deletion",
        "predicate": "parser_created AND no_user_opinion AND not_referenced_by_any_segment",
        "count": len(candidates),
        "candidates": candidates,
        "acted_on": False,
        "note": INFORMATION_NOTE,
    }
    if unknown:
        out["segment_use_unknown"] = unknown
        out["segment_use_note"] = (
            f"{unknown} further parser-created analyses carry no opinion but "
            f"their use in texts could not be read. They are not counted: an "
            f"unknown is never treated as unreferenced."
        )
    return out


def duplicate_projection(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Filings that WOULD duplicate an existing meaning-only record."""
    duplicates = []
    for line in results:
        for pairing in candidate_pairings(line):
            duplicates.append(
                {
                    "wordform": pairing["wordform"],
                    "existing_meaning_only_record": pairing["human_record_guid"],
                    "human_gloss": pairing["human_gloss"],
                }
            )
    return {
        "projection": "duplicate",
        "count": len(duplicates),
        "would_duplicate": duplicates,
        "acted_on": False,
        "note": INFORMATION_NOTE,
    }
