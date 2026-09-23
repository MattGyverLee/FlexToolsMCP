#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Completeness tiers: how far a human got with an analysis (parser-check CP3,
US5; FR-038, FR-039; data-model.md section 8).

    none          no human analysis at all
    meaning_only  meaning recorded (a gloss, a category), no decomposition
    sketched      a decomposition begun, not every morph linked
    fully_linked  every morph bundle present and complete

ONLY `fully_linked` enters the approval comparison (FR-039). The other two are
reported by name and never counted as agreement or disagreement: the human has
not disagreed with the parser -- they have not yet spoken on the question the
parser answers.

DERIVED FROM THE PUBLIC FLAG, NOT A REIMPLEMENTED PREDICATE (FR-038). The host
application's `WfiAnalysis.IsFullyFormed` is `internal`, so not callable from
pythonnet, and reimplementing it would drift from it silently. The tier comes
from two facts the worker recorded as read: the bundle count
(`MorphBundlesOS.Count`) and how many bundles report the public
`IWfiMorphBundle.IsComplete`. Nothing here inspects a bundle's morph, MSA or
sense itself.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable

__all__ = ["TIERS", "tier_of", "unlinked_count", "word_tier"]

#: Verbatim, in order of how far the human got.
TIERS = ("none", "meaning_only", "sketched", "fully_linked")


def unlinked_count(record: Dict[str, Any]) -> int:
    """Bundles whose public `IsComplete` is false (the sketched sentence's N)."""
    total = int(record.get("bundle_count") or 0)
    complete = int(record.get("complete_bundle_count") or 0)
    return max(total - complete, 0)


def tier_of(record: Dict[str, Any]) -> str:
    """The tier of ONE stored analysis, from bundle count and the flag."""
    total = int(record.get("bundle_count") or 0)
    if total == 0:
        return "meaning_only"
    return "fully_linked" if unlinked_count(record) == 0 else "sketched"


def word_tier(records: Iterable[Dict[str, Any]]) -> str:
    """The furthest tier any human analysis of a word reached."""
    best = "none"
    for record in records:
        tier = tier_of(record)
        if TIERS.index(tier) > TIERS.index(best):
            best = tier
    return best
