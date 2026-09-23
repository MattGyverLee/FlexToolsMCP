#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The oracle: what the human analysis record affirms, and what it cannot
(parser-check CP3, US5; FR-039..FR-043; data-model.md section 9).

THE WORDING IS THE CONTRACT. The six sentences below and the population
sentence are transcribed verbatim from `contracts/tools.md` section 3 and are
rendered by substitution only -- never paraphrased, never shortened, never
"improved" (FR-040). `tests/test_signals_oracle_wording.py` pins them
byte-exact against the contract file itself, so an edit here that drifts from
the contract fails the build rather than a review.

THE SPLIT IS {affirmed, indeterminate}, NEVER {affirmed, tacit} (FR-042).
Approval is recorded for anything left in use in a text, so an approved
analysis that occurs in a segment may have been affirmed or merely used, and
nothing in the data model says which. The join is ONE-SIDED on purpose:

    approved, in no segment        -> affirmed       (reliable)
    approved, in some segment      -> indeterminate  (unknowable)
    approved, segment use unknown  -> indeterminate  (never promoted to affirmed)

No individual analysis is ever labelled tacit, unreviewed or auto-approved.
The indeterminate population is named and counted; its members are not
characterised, because the only honest characterisation is "cannot tell".

ONLY FULLY LINKED HUMAN ANALYSES ENTER THE APPROVAL COMPARISON (FR-039).
Meaning-only and sketched records are listed separately and BY NAME: never
folded into a count, never dropped, never rendered as disagreeing with the
parser -- a human who glossed a word without decomposing it has not disagreed
with the parser's decomposition; they have not spoken on it.

THE ORACLE IS ABSENT ON A NEVER-PARSED PROJECT (FR-041). The precondition is
the ONE project-state probe (`parse/project_state.py`, FR-004), recorded on
the run at submission. Where the parser has never run, the per-analysis
report is not emitted at all: every analysis would read as unreviewed, and a
corpus-wide "nobody checked this" is not a finding.

THE SEGMENT-OCCURRENCE JOIN IS BUILT ONCE (FR-043). `segment_occurrence`
below is the only implementation of "which analyses does some text segment
reference". The worker walks the project to feed it (the traversal needs the
open project); this module owns the join. CP4's deletion projection needs the
same join for the opposite purpose -- "not referenced by any segment" -- and
must import this one; a CP4 that rebuilds it is a review finding
(contracts/artifact.md section 9, rule 4).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from .tiers import tier_of, unlinked_count

__all__ = [
    "SENTENCE_APPROVED",
    "SENTENCE_APPROVED_IN_TEXT",
    "SENTENCE_DISAPPROVED",
    "SENTENCE_NO_OPINION",
    "SENTENCE_MEANING_ONLY",
    "SENTENCE_SKETCHED",
    "SENTENCE_POPULATION",
    "SENTENCE_ORACLE_ABSENT",
    "PROVENANCE_SPLIT",
    "SegmentOccurrence",
    "segment_occurrence",
    "is_human_record",
    "describe_analysis",
    "oracle_is_absent",
    "build_oracle",
]

# ---------------------------------------------------------------------------
# The mandated sentences -- verbatim from contracts/tools.md section 3.
# The bracketed placeholders are the contract's own; `render` substitutes them.
# ---------------------------------------------------------------------------

SENTENCE_APPROVED = "Approved by [user] on [date]."

SENTENCE_APPROVED_IN_TEXT = (
    "Approved under [user] on [date]. This analysis is in use in a text, and "
    "approval is recorded for anything left in use -- so it may have been "
    "affirmed, or merely used. There is no way to tell which."
)

SENTENCE_DISAPPROVED = "Marked incorrect by [user] on [date]."

SENTENCE_NO_OPINION = (
    "Not yet reviewed by a human -- this is not evidence it is wrong, only that "
    "nobody has checked it."
)

SENTENCE_MEANING_ONLY = (
    "A human recorded what this word means, but not how it decomposes -- there "
    "is no morphology here to compare the parser against."
)

SENTENCE_SKETCHED = (
    "A human began a morphological analysis but did not finish linking it -- "
    "[N] of [M] morphs are not linked to a lexical entry, so it cannot be "
    "compared to the parser's output."
)

SENTENCE_POPULATION = (
    "[N] analyses carry a human approval. [M] of those appear in a text, where "
    "approval is recorded for anything left in use -- so some of those were "
    "used rather than affirmed. There is no way to tell which."
)

#: FR-041's "own sentence". The contract mandates that the absent case has
#: one, not its text; this is it. It says why there is no report rather than
#: rendering a report in which everything reads as unreviewed.
SENTENCE_ORACLE_ABSENT = (
    "The parser has never run against this project, so there is no parser "
    "output for the human analysis record to confirm or contradict. The oracle "
    "is absent: no per-analysis comparison is reported, because every analysis "
    "would appear unexamined only because the parser has not been run."
)

#: What an unreadable evaluator or date renders as. Never a guess at a name.
UNKNOWN_USER = "an unrecorded user"
UNKNOWN_DATE = "an unrecorded date"

#: The provenance split, exactly (FR-042).
PROVENANCE_SPLIT = ("affirmed", "indeterminate")


def _render(template: str, **values: Any) -> str:
    out = template
    for key, value in values.items():
        out = out.replace(f"[{key}]", str(value))
    return out


# ---------------------------------------------------------------------------
# The segment-occurrence join (FR-043) -- built once, reused by CP4.
# ---------------------------------------------------------------------------


def _guid_text(obj: Any) -> Optional[str]:
    guid = getattr(obj, "Guid", None)
    if guid is None:
        return None
    return str(guid).lower()


class SegmentOccurrence:
    """Which analyses some text segment references, as a set of GUID strings.

    `contains` answers True, False, or None when the join could not be built.
    None is carried, never collapsed to False: "we could not read the texts"
    and "no text uses this" call for opposite conclusions -- the first is
    unknowable, the second is what makes an approval reliably affirmed.
    """

    def __init__(self, analysis_guids: Optional[Iterable[str]]) -> None:
        self.known = analysis_guids is not None
        self._guids = frozenset(g.lower() for g in (analysis_guids or ()) if g)

    def contains(self, analysis_guid: Optional[str]) -> Optional[bool]:
        if not self.known or not analysis_guid:
            return None
        return analysis_guid.lower() in self._guids

    def referenced(self) -> frozenset:
        """Every referenced analysis GUID. CP4's projection reads this."""
        return self._guids

    def __len__(self) -> int:
        return len(self._guids)


def segment_occurrence(segments: Optional[Iterable[Any]]) -> SegmentOccurrence:
    """Join segments to the analyses they reference. THE only implementation.

    A segment's `AnalysesRS` holds wordforms, analyses, glosses and
    punctuation. An analysis counts as occurring when a segment references it
    directly or references one of its glosses. A wordform-only reference
    does not count: it names the word, not any analysis of it.

    The gloss -> analysis step reads the gloss's `Owner`, which is typed as
    base `ICmObject`. Only `.Guid` is read from it, and `Guid` IS on
    `ICmObject`, so no cast is needed -- the one-line check the plan asks
    for on the unguarded-`.Owner` class (#32/#97/#98). Any other member read
    on that owner would need an `IWfiAnalysis` cast first.

    `segments=None` means the traversal could not run: the result is unknown,
    not empty.
    """
    if segments is None:
        return SegmentOccurrence(None)
    guids = set()
    for segment in segments:
        for item in _items(getattr(segment, "AnalysesRS", None)):
            kind = str(getattr(item, "ClassName", "") or "")
            if kind == "WfiAnalysis":
                guid = _guid_text(item)
            elif kind == "WfiGloss":
                guid = _guid_text(getattr(item, "Owner", None))  # Guid is on ICmObject
            else:
                continue
            if guid:
                guids.add(guid)
    return SegmentOccurrence(guids)


def _items(collection: Any) -> List[Any]:
    if collection is None:
        return []
    try:
        return list(collection)
    except TypeError:
        return []


# ---------------------------------------------------------------------------
# Per-analysis description
# ---------------------------------------------------------------------------


def is_human_record(record: Dict[str, Any]) -> bool:
    """True for a stored analysis a human made or has spoken on.

    A stored analysis the parser evaluated and no human has an opinion on is
    the parser's own record, not the human oracle. Anything carrying a human
    opinion is human by definition; anything the parser never evaluated was
    made by a person (the parser does not store what it did not evaluate).
    """
    opinion = record.get("opinion")
    if opinion in ("approves", "disapproves"):
        return True
    return not bool(record.get("parser_evaluated"))


def _who(record: Dict[str, Any]) -> Dict[str, str]:
    return {
        "user": record.get("evaluator") or UNKNOWN_USER,
        "date": record.get("evaluated_at") or UNKNOWN_DATE,
    }


def describe_analysis(record: Dict[str, Any]) -> Dict[str, Any]:
    """One stored analysis: its tier, its provenance, its mandated sentence.

    The returned `sentence` is always one of the contract's, substituted.
    `provenance` is set only for an approval, and only ever to one of
    `PROVENANCE_SPLIT`. There is no `label` key: nothing here is labelled
    tacit, unreviewed or auto-approved (FR-042).
    """
    human = is_human_record(record)
    # The tier measures how far a HUMAN got. The parser's own stored record
    # has no tier; it is reported by its (absent) human opinion alone.
    tier = tier_of(record) if human else None
    entry: Dict[str, Any] = {
        "analysis_guid": record.get("analysis_guid"),
        "rendered_morphs": list(record.get("rendered_morphs") or []),
        "gloss": record.get("gloss") or "",
        "human_record": human,
        "tier": tier,
        "opinion": record.get("opinion"),
        "in_segment": record.get("in_segment"),
        "enters_approval_comparison": tier == "fully_linked",
    }
    if tier == "meaning_only":
        entry["sentence"] = SENTENCE_MEANING_ONLY
        return entry
    if tier == "sketched":
        entry["unlinked_morphs"] = unlinked_count(record)
        entry["morphs"] = int(record.get("bundle_count") or 0)
        entry["sentence"] = _render(
            SENTENCE_SKETCHED, N=entry["unlinked_morphs"], M=entry["morphs"]
        )
        return entry

    opinion = record.get("opinion")
    if opinion == "approves":
        if record.get("in_segment") is False:
            entry["provenance"] = "affirmed"
            entry["sentence"] = _render(SENTENCE_APPROVED, **_who(record))
        else:
            # In a segment, or segment use unknown: never promoted to affirmed.
            entry["provenance"] = "indeterminate"
            entry["sentence"] = _render(SENTENCE_APPROVED_IN_TEXT, **_who(record))
    elif opinion == "disapproves":
        entry["sentence"] = _render(SENTENCE_DISAPPROVED, **_who(record))
    elif opinion == "noopinion":
        entry["sentence"] = SENTENCE_NO_OPINION
    else:
        # The stored opinion could not be read. Not "no opinion": that would
        # be a claim about the record we could not make.
        entry["sentence"] = "The stored opinion on this analysis could not be read."
    return entry


# ---------------------------------------------------------------------------
# The whole-run oracle
# ---------------------------------------------------------------------------


def oracle_is_absent(project_state: Optional[Dict[str, Any]]) -> Optional[bool]:
    """True on a never-parsed project; None when the probe did not run."""
    if not project_state:
        return None
    return not bool(project_state.get("parser_has_ever_run"))


def _signature_key(signature: Any) -> tuple:
    return tuple(tuple(triple) for triple in (signature or []))


def build_oracle(
    results: Iterable[Dict[str, Any]],
    project_state: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """The oracle over a batch's `results.jsonl` lines (FR-039..FR-042).

    Returns a block whose `status` is `absent` (FR-041) or `present`. When
    the project-state probe could not run, the oracle is still reported --
    every sentence it renders is true regardless -- and `project_state_known`
    is False so the reader can see the precondition was not checked.
    """
    lines = list(results)
    absent = oracle_is_absent(project_state)

    meaning_only: List[Dict[str, Any]] = []
    sketched: List[Dict[str, Any]] = []
    analyses: List[Dict[str, Any]] = []
    approved = 0
    approved_in_text = 0
    segment_use_unknown = 0
    affirmed = 0
    indeterminate = 0

    for line in lines:
        parse = line.get("parse") or {}
        wordform = line.get("wordform")
        produced = {_signature_key(a.get("signature")) for a in parse.get("analyses") or []}
        for record in parse.get("human_analyses") or []:
            entry = describe_analysis(record)
            entry["wordform"] = wordform
            if entry["tier"] == "meaning_only":
                meaning_only.append(entry)
                continue
            if entry["tier"] == "sketched":
                sketched.append(entry)
                continue
            if absent:
                # Never-parsed: no per-analysis comparison (FR-041).
                continue
            entry["parser_produced"] = _signature_key(record.get("signature")) in produced
            if entry.get("provenance"):
                approved += 1
                if entry["provenance"] == "affirmed":
                    affirmed += 1
                else:
                    indeterminate += 1
                if record.get("in_segment") is True:
                    approved_in_text += 1
                elif record.get("in_segment") is None:
                    segment_use_unknown += 1
            analyses.append(entry)

    block: Dict[str, Any] = {
        "project_state_known": absent is not None,
        # Named separately, by name, never folded into a count (FR-039).
        "meaning_only": meaning_only,
        "sketched": sketched,
    }
    if absent:
        block["status"] = "absent"
        block["sentence"] = SENTENCE_ORACLE_ABSENT
        return block

    block["status"] = "present"
    block["provenance_split"] = {"affirmed": affirmed, "indeterminate": indeterminate}
    block["population_sentence"] = _render(SENTENCE_POPULATION, N=approved, M=approved_in_text)
    if segment_use_unknown:
        # Counted as indeterminate, never as affirmed -- and said so, because
        # the population sentence's M counts only what was SEEN in a text.
        block["segment_use_unknown"] = segment_use_unknown
        block["segment_use_note"] = (
            f"For {segment_use_unknown} approved analyses the texts could not be "
            f"read, so whether they appear in a text is unknown. They are "
            f"counted as indeterminate, not as affirmed."
        )
    block["analyses"] = analyses
    return block
