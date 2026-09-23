#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Promotion-only ranking (parser-check CP3, US5; FR-045, SC-014, R-10;
SPEC 9.3.2).

THE WRONG IMPLEMENTATION IS THE SHORTER ONE. Sorting a word's analyses by how
close each composed gloss is to the human's gloss is one line, and it is
confidently wrong about exactly the words a linguist cares most about.
Morphology is not reliably compositional -- English `understand` is not
`under` + `stand` -- so a mismatch is ambiguous between "wrong analysis" and
"correct analysis of a non-compositional word". A sort treats every mismatch
as the first and pushes the correct analysis of a lexicalized form down.

So the ordering is asymmetric:

  * a composed gloss that AGREES with the human's gloss promotes;
  * a composed gloss that disagrees does NOT demote -- nothing is ever
    pushed down, scored, or rendered as less likely;
  * everything not promoted keeps its original (parser) order, and the
    promoted analyses keep their original order among themselves.

Agreement is a strict test, not a similarity measure: the composed gloss and
the human gloss must be the same words after case-folding and splitting on
the punctuation glosses conventionally carry. A partial overlap is not
agreement -- partial overlap is exactly what a compositional-but-wrong
analysis has. `tests/test_signals_ranking.py` (written first, T075) holds
the fixture that makes a sort fail.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

__all__ = ["glosses_agree", "composed_gloss", "promote"]

#: What separates gloss words: whitespace and the punctuation interlinear
#: glosses conventionally use between morpheme glosses (`-`, `.`, `=`, `_`).
_SPLIT = re.compile(r"[\s\-.=_]+")


def _words(text: str) -> List[str]:
    return [w for w in _SPLIT.split((text or "").casefold()) if w]


def composed_gloss(morph_glosses: Iterable[str]) -> str:
    """The analysis's composed gloss: its morph glosses, in order."""
    return " ".join(w for g in morph_glosses or () for w in _words(g))


def glosses_agree(morph_glosses: Sequence[str], human_gloss: str) -> bool:
    """Strict agreement between a composed gloss and a human word gloss."""
    composed = _words(" ".join(morph_glosses or ()))
    wanted = _words(human_gloss)
    return bool(composed) and bool(wanted) and composed == wanted


def promote(analyses: Sequence[Dict[str, Any]], human_gloss: str) -> List[Dict[str, Any]]:
    """Reorder by promotion only. Stable, total, never demoting.

    Each entry is `{"analysis", "original_position", "promoted", "basis"}`.
    There is deliberately no score, distance or likelihood key: ranking
    reorders, it does not judge (SPEC 9.3.2).
    """
    promoted: List[Dict[str, Any]] = []
    rest: List[Dict[str, Any]] = []
    for position, analysis in enumerate(analyses):
        agrees = glosses_agree(analysis.get("morph_glosses") or [], human_gloss)
        entry = {
            "analysis": analysis,
            "original_position": position,
            "promoted": agrees,
            "basis": "gloss_agreement" if agrees else None,
        }
        (promoted if agrees else rest).append(entry)
    return promoted + rest
