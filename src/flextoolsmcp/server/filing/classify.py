#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
One word's filing, from guard to outcome (parser-check CP4, FR-014, FR-017,
FR-019, FR-031, FR-033, FR-040, FR-041; research R-02; data-model sections 7
and 9).

THE SEQUENCE, per word, and why each step is where it is:

  1. LIVENESS (FR-019). The wordform and every object the parse result points
     at must still exist -- `ParseResult.IsValid`, `IsValidObject` -- or the
     word is skipped `invalid_object` and nothing is asked of it. This catches
     a deleted object, not a changed rule that leaves the objects alive, and
     the report does not claim more than that.
  2. UNCHANGED. When the wordform's stored checksum equals the new result's,
     FLEx's filer skips the word (`ParseFiler.cs:208`). It is reported
     `unchanged`, never `filed`, and not pumped.
  3. THE R-02 GUARD. The filer's own would-delete set is computed on the LIVE
     objects with the filer's exact predicate -- an existing analysis the new
     result does not match, with user `noopinion`, used by no segment of the
     wordform's occurrences, directly or through a gloss
     (`ParseFiler.cs:302-318`). If any member is outside the CONFIRMED
     projection for this word -- or any live in-use disapproval is outside the
     confirmed overwrite projection -- the word is skipped
     `outside_projection` and NOTHING is filed for it. FR-014 and SC-011 hold
     by construction, not by hope.
  4. THE CAPTURES (FR-031, FR-041). One `pre_deletion` line per analysis that
     may be deleted, one `disapproval_overwrite` line per human disapproval
     that will be overwritten (with the PRIOR evaluation), appended to
     `filing/deletions.jsonl` and fsynced BEFORE the pump -- the only moment
     the analysis still exists to be described.
  5. THE PUMP (`filer.file_one`): `filed`, or `filer_declined`.
  6. THE OUTCOME, from the live objects before and after: created,
     re-approved, duplicated, deleted, in-use approvals recorded, overwrites
     confirmed -- plus a `confirmed_after` line per capture (the file is
     append-only, so the result is a second line, never a rewrite).

AN ERRORED WORD IS FILED AS FLEX FILES IT (FR-017). Its parser opinions are
cleared and nothing matches, so every unshielded, unapproved analysis goes.
It is counted in `errored_words`, and what it lost in `errored_word_deletions`.

This module never touches LCM itself: the `WordSurface` it is handed does
(the filing worker's real one, or a test's fake), so every branch here is
provable offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Protocol, Set

__all__ = [
    "SKIP_REASONS",
    "FilingContext",
    "WordSurface",
    "would_delete",
    "file_word",
    "empty_counts",
    "add_counts",
]

#: data-model section 7: exactly three.
SKIP_REASONS = ("invalid_object", "outside_projection", "filer_declined")


class WordSurface(Protocol):
    """One word's live objects, as the classifier needs them."""

    wordform: str

    def is_valid(self) -> bool: ...
    def checksum_matches(self) -> bool: ...
    def errored(self) -> bool: ...
    def existing(self) -> List[Dict[str, Any]]: ...
    def capture(self, guid: str) -> Dict[str, Any]: ...
    def pump(self) -> str: ...
    def after(self) -> List[Dict[str, Any]]: ...
    def is_duplicate(self, guid: str) -> bool: ...


@dataclass
class FilingContext:
    """What the confirmed call bound this run to, and where captures go."""

    #: The confirmed deletion projection, `{wordform: [analysis_guid]}`.
    projection: Dict[str, List[str]]
    #: The confirmed disapproval-overwrite projection, same shape.
    overwrites: Dict[str, List[str]]
    #: Appends one `deletions.jsonl` line, durably, before returning.
    sink: Callable[[Dict[str, Any]], None]


def empty_counts() -> Dict[str, Any]:
    """`FilingCounts` (data-model section 7), all zero."""
    return {
        "created": 0, "reapproved": 0, "duplicated": 0, "deleted": 0, "unchanged": 0,
        "errored_words": 0, "errored_word_deletions": 0,
        "skipped": {reason: 0 for reason in SKIP_REASONS},
    }


def add_counts(totals: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    """Accumulate one word's counts into the run's totals."""
    for key, value in delta.items():
        if key == "skipped":
            for reason, n in (value or {}).items():
                totals["skipped"][reason] = totals["skipped"].get(reason, 0) + int(n)
        else:
            totals[key] = totals.get(key, 0) + int(value)
    return totals


def would_delete(existing: Iterable[Dict[str, Any]], *, errored: bool) -> Set[str]:
    """The filer's deletion predicate on live facts (`ParseFiler.cs:302-318`).

    Every analysis's parser opinion is reset to `noopinion`; a MATCHED one is
    approved again (none is, for an errored word); an in-use one is given a
    user approval. What is left with parser `noopinion` AND user `noopinion`
    is deleted.

    UNKNOWN IS NOT SAFE, as in the preview's bound: an opinion that could not
    be read counts as `noopinion`, and a segment use that could not be read
    (`in_use` None) as not in use. The guard is a subset check, so reading an
    unknown as "shielded" would let FieldWorks' filer delete what nobody
    confirmed, with no capture.
    """
    doomed: Set[str] = set()
    for analysis in existing:
        if analysis.get("in_use") is True:
            continue
        if analysis.get("matched") and not errored:
            continue
        if analysis.get("user_opinion") in ("approves", "disapproves"):
            continue
        doomed.add(analysis["analysis_guid"])
    return doomed


def _in_use_disapprovals(existing: Iterable[Dict[str, Any]]) -> Set[str]:
    """In-use analyses whose user opinion is `disapproves` -- overwritten (D-2).

    Unknown segment use counts as in use: the overwrite is then guarded too.
    """
    return {a["analysis_guid"] for a in existing
            if a.get("in_use") is not False and a.get("user_opinion") == "disapproves"}


def _outcome(wordform: str, outcome: str, **extra: Any) -> Dict[str, Any]:
    counts = empty_counts()
    reason = extra.pop("skip_reason", None)
    if reason:
        counts["skipped"][reason] = 1
    if outcome == "unchanged":
        counts["unchanged"] = 1
    base = {
        "wordform": wordform, "outcome": outcome, "skip_reason": reason,
        "errored": False, "counts": counts, "deleted": [], "created": [],
        "overwritten": [], "in_use_approvals_recorded": 0,
    }
    base.update(extra)
    return base


def file_word(ctx: FilingContext, surface: WordSurface) -> Dict[str, Any]:
    """File one word, or say exactly why it was not."""
    word = surface.wordform

    # (1) Liveness.
    if not surface.is_valid():
        return _outcome(word, "skipped", skip_reason="invalid_object")

    # (2) Unchanged.
    if surface.checksum_matches():
        return _outcome(word, "unchanged")

    # (3) The R-02 guard, on the live objects.
    errored = bool(surface.errored())
    before = surface.existing()
    doomed = would_delete(before, errored=errored)
    overwrites = _in_use_disapprovals(before)
    outside = sorted(doomed - set(ctx.projection.get(word) or ()))
    outside += sorted(overwrites - set(ctx.overwrites.get(word) or ()))
    if outside:
        return _outcome(word, "skipped", skip_reason="outside_projection",
                        outside=outside, errored=errored)

    # (4) The captures, BEFORE the pump.
    by_guid = {a["analysis_guid"]: a for a in before}
    for guid in sorted(doomed):
        ctx.sink({"kind": "pre_deletion", "wordform": word, "analysis_guid": guid,
                  **surface.capture(guid)})
    for guid in sorted(overwrites):
        ctx.sink({"kind": "disapproval_overwrite", "wordform": word, "analysis_guid": guid,
                  "prior_user_opinion": by_guid[guid].get("user_opinion"),
                  **surface.capture(guid)})

    # (5) The pump.
    pumped = surface.pump()
    if pumped != "filed":
        for guid in sorted(doomed):
            ctx.sink({"kind": "pre_deletion", "wordform": word, "analysis_guid": guid,
                      "confirmed_after": "survived"})
        for guid in sorted(overwrites):
            ctx.sink({"kind": "disapproval_overwrite", "wordform": word,
                      "analysis_guid": guid, "confirmed_after": "unchanged"})
        return _outcome(word, "skipped", skip_reason="filer_declined", errored=errored)

    # (6) The outcome, from the live objects after the pump.
    after = surface.after()
    after_by_guid = {a["analysis_guid"]: a for a in after}
    before_guids = set(by_guid)
    after_guids = set(after_by_guid)
    deleted = sorted(before_guids - after_guids)
    created = sorted(after_guids - before_guids)
    reapproved = [g for g, a in by_guid.items()
                  if a.get("matched") and not errored and g in after_guids]
    in_use_recorded = sum(
        1 for g, a in by_guid.items()
        if a.get("in_use") and a.get("user_opinion") == "noopinion"
        and (after_by_guid.get(g) or {}).get("user_opinion") == "approves"
    )
    overwritten = sorted(
        g for g in overwrites if (after_by_guid.get(g) or {}).get("user_opinion") == "approves"
    )
    for guid in sorted(doomed):
        ctx.sink({"kind": "pre_deletion", "wordform": word, "analysis_guid": guid,
                  "confirmed_after": "deleted" if guid not in after_guids else "survived"})
    for guid in sorted(overwrites):
        ctx.sink({"kind": "disapproval_overwrite", "wordform": word, "analysis_guid": guid,
                  "confirmed_after": "overwritten" if guid in overwritten else "unchanged"})

    counts = empty_counts()
    counts.update({
        "created": len(created),
        "reapproved": len(reapproved),
        "duplicated": sum(1 for g in created if surface.is_duplicate(g)),
        "deleted": len(deleted),
    })
    if errored:
        counts["errored_words"] = 1
        counts["errored_word_deletions"] = len(deleted)
    return _outcome(
        word, "filed", errored=errored, counts=counts, deleted=deleted, created=created,
        overwritten=overwritten, in_use_approvals_recorded=in_use_recorded,
    )
