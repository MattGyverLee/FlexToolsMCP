#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The deletion projection: an UPPER BOUND on what filing can delete
(parser-check CP4, FR-011..FR-015, FR-040; research R-01).

THE PREDICATE IS FR-011'S TWO CONJUNCTS, AND ONLY THOSE:

    user opinion is `noopinion`   AND   not referenced by any text segment,
                                        directly or through one of its glosses

That is FLEx's own deletion rule. `ParseFiler.UpdateWordforms` first resets
the PARSER's opinion to `noopinion` on every analysis of the word; then
`SetUnsuccessfulParseEvals` gives every in-use analysis a user approval and
deletes every analysis still holding parser `noopinion` and user `noopinion`
(`ParseFiler.cs:226-227, 305-318`). Nothing there asks who created the
analysis -- which is why this is NOT CP3's `signals.projections.deletion_projection`.
CP3's predicate adds "parser-created", so it cannot see the analysis a person
made, never evaluated and never used, which FLEx deletes all the same. Reused
here it would make FR-014 false (R-01; `tests/test_filing_projection.py` holds
the fixture that proves it).

WHAT IS REUSED (FR-015). The segment join is CP3's -- `oracle.segment_occurrence`,
THE implementation of "which analyses does some segment reference", gloss path
included. The project-state probe is CP3's -- `parse/project_state.py`, run
once at scope resolution; this module consumes its result and never probes
again. Only the predicate is new.

THE BOUND IS PESSIMISTIC WHERE IT CANNOT KNOW. The parser's NEXT result is not
known at preview time (filing parses fresh), so every analysis satisfying the
predicate is counted, whether or not the parser would produce it again: "may
delete up to N", never a prediction. Where the join could not be evaluated, or
an opinion could not be read, the analysis is COUNTED -- the opposite of CP3's
information projection, and deliberately: for a bound, "could not tell" rounds
toward "may be deleted". The per-word guard at filing time (R-02,
`classify.py`) then refuses to file any word whose live would-delete set
reaches outside the confirmed bound, which is what makes the bound hold.

A NEVER-PARSED PROJECT IS NOT SHORT-CIRCUITED. SC-003 expects 0 there, and 0
is what this computes when every analysis is spoken for -- approved by a
person, or in use. But a never-parsed project that holds an unused analysis
nobody has spoken for loses it to FLEx's filer like any other, so it counts.
The probe's result is carried beside the number, never used to force it.

DISAPPROVALS (D-2, FR-040). A human-disapproved analysis is never deletable.
But `SetUnsuccessfulParseEvals` sets the user agent to `approves` on every
in-use analysis unconditionally, so an in-use disapproval IS overwritten.
Those are projected on their own, never folded into the in-use approvals
FR-033 counts, and never labelled with any word implying review.

TWO HALVES. `fresh_occurrence` / `attach_segment_use` run in the READ worker
(on the preview's request, through `preflight_reads.py`), where the project is
open; they only read. `project` runs anywhere: it is plain data in, plain data
out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

from ..parse.project_state import ProjectParseState, deletion_projection_precondition
from ..signals.oracle import SegmentOccurrence, segment_occurrence

__all__ = [
    "PREDICATE",
    "ProjectionResult",
    "fresh_occurrence",
    "attach_segment_use",
    "project",
]

#: The fixed predicate string (data-model section 3).
PREDICATE = "user_noopinion AND not_referenced_by_any_segment_directly_or_via_gloss"

#: Opinions that are a human's recorded view. Anything else -- `noopinion`,
#: or an opinion that could not be read -- leaves the analysis unshielded.
_SPOKEN_FOR = ("approves", "disapproves")


def fresh_occurrence(iter_segments: Callable[[], Iterable[Any]]) -> SegmentOccurrence:
    """A FRESH segment join, through THE join (R-02, FR-015).

    Never the worker-lifetime cache CP3's reports use: a preview built from a
    join cached hours ago would under-project, and the preview must err the
    other way. A traversal that fails is UNKNOWN (`segment_occurrence(None)`),
    never "no text uses anything".
    """
    try:
        return segment_occurrence(iter_segments())
    except Exception:  # noqa: BLE001 -- unknown, never "none"
        return segment_occurrence(None)


#: A word whose stored analyses could not be read (or whose wordform lookup
#: could not be completed). Not "no analyses": the bound cannot cover it, and
#: the plan says so (`words_unreadable`). The filer's own guard still refuses
#: to delete anything for it that the plan does not name (R-02).
UNREADABLE = "unreadable"


def attach_segment_use(
    stored_by_word: Dict[str, Optional[List[Dict[str, Any]]]],
    occurrence: SegmentOccurrence,
) -> Dict[str, Dict[str, Any]]:
    """Per-word preview facts: each stored analysis with its segment use.

    `stored_by_word[w]` is None when the word has no wordform in the project
    (it then has nothing to delete), `UNREADABLE` when its analyses could not
    be read, and otherwise the stored analyses as the worker read them --
    `analysis_guid`, `user_opinion`, `parser_evaluated`.
    """
    facts: Dict[str, Dict[str, Any]] = {}
    for word, stored in stored_by_word.items():
        if stored == UNREADABLE:
            facts[word] = {"wordform": word, "found": None, "analyses": [],
                           "analyses_unreadable": True}
            continue
        analyses = []
        for record in stored or []:
            entry = dict(record)
            entry["in_segment"] = occurrence.contains(record.get("analysis_guid"))
            analyses.append(entry)
        facts[word] = {"wordform": word, "found": stored is not None, "analyses": analyses}
    return facts


@dataclass
class ProjectionResult:
    """The three projected populations, as the plan carries them."""

    deletion: Dict[str, Any]
    disapproval_overwrites: Dict[str, Any] = field(
        default_factory=lambda: {"count": 0, "by_wordform": {}}
    )
    in_use_approvals_projected: int = 0

    def by_wordform(self) -> Dict[str, List[str]]:
        return self.deletion["by_wordform"]


def _state_context(project_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The probe's result, carried beside the bound (FR-015: consumed, not re-run).

    `parser_created_present` is the probe's own consumer 3
    (`deletion_projection_precondition`), reported as context: with no
    parser-created analyses, only human-made unreviewed ones can be deleted.
    """
    if not project_state:
        return {"project_state": project_state, "parser_created_present": None}
    try:
        state = ProjectParseState(**project_state)
        present = deletion_projection_precondition(state)
    except TypeError:
        present = None
    return {"project_state": project_state, "parser_created_present": present}


def project(
    facts: Dict[str, Dict[str, Any]],
    project_state: Optional[Dict[str, Any]] = None,
) -> ProjectionResult:
    """Compute the deletion upper bound and the two in-use populations.

    Per analysis of every word in scope:

      user opinion      segment use       -> counted as
      ---------------   ---------------      -----------------------------
      approves          any                  nothing (never deletable)
      disapproves       not in use           excluded_disapproved
      disapproves       in use / unknown     excluded_disapproved, and a
                                             projected disapproval overwrite
      noopinion         in use               a projected in-use approval
      noopinion         not in use           DELETABLE (upper bound)
      noopinion         unknown              DELETABLE, and segment_use_unknown
      unreadable        not in use / unknown DELETABLE, and opinion_unknown
      unreadable        in use               nothing deletable (in-use analyses
                                             are approved, never deleted)
    """
    by_wordform: Dict[str, List[str]] = {}
    overwrites: Dict[str, List[str]] = {}
    in_use_approvals = 0
    excluded_disapproved = 0
    segment_use_unknown = 0
    opinion_unknown = 0
    words_unreadable = []

    for word, entry in facts.items():
        if (entry or {}).get("analyses_unreadable"):
            words_unreadable.append(word)
        for analysis in (entry or {}).get("analyses") or []:
            guid = analysis.get("analysis_guid")
            opinion = analysis.get("user_opinion")
            in_segment = analysis.get("in_segment")
            if not guid:
                continue

            if opinion == "approves":
                continue
            if opinion == "disapproves":
                excluded_disapproved += 1
                if in_segment is not False:
                    overwrites.setdefault(word, []).append(guid)
                continue

            if in_segment is True:
                if opinion == "noopinion":
                    in_use_approvals += 1
                continue

            by_wordform.setdefault(word, []).append(guid)
            if in_segment is None:
                segment_use_unknown += 1
            if opinion not in _SPOKEN_FOR and opinion != "noopinion":
                opinion_unknown += 1

    by_wordform = {w: sorted(set(g)) for w, g in sorted(by_wordform.items())}
    overwrites = {w: sorted(set(g)) for w, g in sorted(overwrites.items())}
    deletion = {
        "predicate": PREDICATE,
        "upper_bound": sum(len(g) for g in by_wordform.values()),
        "by_wordform": by_wordform,
        "segment_use_unknown": segment_use_unknown,
        "opinion_unknown": opinion_unknown,
        "excluded_disapproved": excluded_disapproved,
        # Words the bound does NOT cover: their analyses could not be read.
        "words_unreadable": sorted(words_unreadable),
        **_state_context(project_state),
    }
    return ProjectionResult(
        deletion=deletion,
        disapproval_overwrites={
            "count": sum(len(g) for g in overwrites.values()),
            "by_wordform": overwrites,
        },
        in_use_approvals_projected=in_use_approvals,
    )
