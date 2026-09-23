#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Candidate pairings and lexicalized forms (parser-check CP3, US5; FR-044,
FR-046; SPEC 9.3.2).

WHERE THE ORACLE DEGRADES, IT DEGRADES TO MEANING, NOT TO NOTHING. A human
meaning-only record -- a gloss with no decomposition -- cannot be compared to
the parser's morphology (FR-039). It can still say something: when a parser
analysis meets it, the pair is a candidate for "this is the decomposition of
that meaning". That is the pairing.

A PAIRING IS A SUGGESTION, NEVER A WRITE. Gloss agreement is a prior, not a
proof -- polysemy, homography, non-compositional meaning, and a human gloss
describing a sense the parser's root does not carry all defeat it. So every
pairing is worded as a suggestion, names its confidence basis, and carries
`filed: False`. There is no code path here, or anywhere in CP3, that files
one (FR-063); filing is CP4's, behind its own confirmation.

THE CONFIDENCE BASIS IS STATED, NOT SCORED (SPEC 9.3.2): the parser produced
exactly one analysis for a word carrying exactly one meaning-only record
(`one_to_one`), a composed gloss agrees with the human's (`gloss_agreement`),
or both. There is no numeric confidence -- a number would invite the reader
to rank on it, which is the sort FR-045 forbids.

LEXICALIZATION IS A FINDING, NOT AN ERROR (FR-046). A word the parser can
derive, none of whose analyses composes to the human's recorded meaning, is
reported with the mandated sentence as a candidate lexicalized form. That is
precisely what a lexical entry, or a sense on a complex form, exists to
record; it is not a parse failure and is never counted as one.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .oracle import is_human_record
from .ranking import composed_gloss, glosses_agree, promote
from .tiers import tier_of

__all__ = [
    "SENTENCE_LEXICALIZED",
    "candidate_pairings",
    "lexicalization_finding",
    "human_gloss",
]

#: Verbatim from SPEC 9.3.2 (FR-046).
SENTENCE_LEXICALIZED = (
    "The parser can derive this word, but its parts do not add up to the "
    "recorded meaning. That may indicate a lexicalized form that deserves its "
    "own entry or sense, rather than a parsing error."
)


def _meaning_only_records(parse: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        r for r in parse.get("human_analyses") or []
        if is_human_record(r) and tier_of(r) == "meaning_only"
    ]


def human_gloss(parse: Dict[str, Any]) -> str:
    """The first non-empty gloss a human recorded on this word, or ''."""
    for record in parse.get("human_analyses") or []:
        if is_human_record(record) and record.get("gloss"):
            return str(record["gloss"])
    return ""


def candidate_pairings(line: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pairings of a parser analysis with a human meaning-only record.

    Returned FIRST in the word's report (FR-044). Proposed only where the
    basis is real: a one-to-one meeting, or strict gloss agreement. A word
    with several analyses and no agreeing gloss yields no pairing -- guessing
    which one the human meant is what the suggestion must not do.
    """
    parse = line.get("parse") or {}
    analyses = list(parse.get("analyses") or [])
    records = _meaning_only_records(parse)
    if not analyses or not records:
        return []

    one_to_one = len(analyses) == 1 and len(records) == 1
    pairings: List[Dict[str, Any]] = []
    for record in records:
        gloss = str(record.get("gloss") or "")
        ranked = promote(analyses, gloss)
        agreeing = [entry for entry in ranked if entry["promoted"]]
        if one_to_one:
            chosen = ranked[0]
        elif len(agreeing) == 1:
            chosen = agreeing[0]
        else:
            continue  # no basis to pick one analysis
        basis = []
        if one_to_one:
            basis.append("one_to_one")
        if chosen["promoted"]:
            basis.append("gloss_agreement")
        analysis = chosen["analysis"]
        morphs = " + ".join(analysis.get("rendered_morphs") or []) or "(no forms recorded)"
        pairings.append(
            {
                "wordform": line.get("wordform"),
                "human_record_guid": record.get("analysis_guid"),
                "human_gloss": gloss,
                "analysis_position": chosen["original_position"],
                "analysis_signature": analysis.get("signature"),
                "rendered_morphs": list(analysis.get("rendered_morphs") or []),
                "confidence_basis": basis,
                "suggestion": (
                    f"Suggestion: the parser's analysis {morphs} may be the "
                    f"decomposition of the meaning a human recorded"
                    + (f" ('{gloss}')" if gloss else "")
                    + f". Basis: {' and '.join(b.replace('_', ' ') for b in basis)}. "
                    f"This is a suggestion for a human to confirm; nothing has "
                    f"been filed."
                ),
                "filed": False,
            }
        )
    return pairings


def lexicalization_finding(line: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The candidate-lexicalized-form finding for one word, or None (FR-046).

    Fires when the parser DERIVES the word (at least one analysis of more
    than one morph), a human recorded its meaning, and no analysis's composed
    gloss agrees with that meaning. Morph glosses that were not recorded at
    all make the comparison impossible, so such analyses are not evidence.
    """
    parse = line.get("parse") or {}
    gloss = human_gloss(parse)
    if not gloss:
        return None
    derived = [
        a for a in parse.get("analyses") or []
        if len(a.get("rendered_morphs") or []) > 1 and any(a.get("morph_glosses") or [])
    ]
    if not derived:
        return None
    if any(glosses_agree(a.get("morph_glosses") or [], gloss) for a in derived):
        return None
    return {
        "wordform": line.get("wordform"),
        "kind": "candidate_lexicalized_form",
        "is_parse_error": False,
        "human_gloss": gloss,
        "composed_glosses": [composed_gloss(a.get("morph_glosses") or []) for a in derived],
        "sentence": SENTENCE_LEXICALIZED,
    }
