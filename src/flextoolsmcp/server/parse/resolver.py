#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The morph resolver: a caller's decomposition -> the MSA identifiers the parser
requires (parser-check CP2b, FR-018 .. FR-020, SC-005, SC-007;
data-model.md section 4).

THIS IS THE CORRECTNESS RISK OF THE CHECKPOINT, and the plan says so in as
many words. Everything downstream of it is a restriction handed to
`TraceWordXml`, so a resolver that resolves to too little refuses a
decomposition that is in fact valid, and one that resolves to too much hands
the parser a restriction the caller did not write. Both are the
silently-narrowed-search failure FR-019 exists to prevent, arriving from
underneath it rather than from the tool surface.

WHICH PROCESS RUNS WHAT, and why the split is where it is.

  This module is PURE. It holds no project, opens no cache, imports nothing
  from pythonnet, and every function in it is a decision over plain data. It
  is importable from the server process -- and is, for the refusal shape --
  which is what makes the three outcomes unit-testable without a FieldWorks
  install (`tests/test_parse_resolver.py`).

  The LEXICON READ lives in the worker (`worker_main.py`), because it is the
  only process that has a project open. The server process must never open
  one (research.md R-02; `tests/test_cp1_boundary.py`), so a resolver that
  reached for `LexEntry.GetAll()` on the server side could not exist however
  it were written. The worker builds `LexiconIndex` once, holds it, and
  answers resolve requests from it.

  `parse/__init__.py` originally listed this module under the server process
  without qualification. That was written before the resolver existed and is
  corrected there: the module is server-importable, the data it works over
  is not.

"RESOLUTION BEFORE EXECUTION" IS ABOUT PARSES, NOT ABOUT MESSAGES. The
contract says every `MorphSpec` resolves "before the worker is asked for
anything"; the guarantee underneath that phrasing is FR-019's "no parse
runs", which SC-005 pins at 0. Resolving is its own request on the channel
and parses nothing -- `ParseWorker` answers it without touching the parser
area at all -- so a decomposition that fails to resolve costs one lexicon
lookup and zero parses. `tests/test_parse_resolver.py` asserts the zero by
recorded calls rather than by inference.

THE THREE FAILURES ARE KEPT DISTINCT ON PURPOSE (FR-019, data-model.md
section 4). `none`, `ambiguous` and `no_msa` are three different things a
linguist does three different things about:

    none       no entry has that headword           -> fix the spelling
    ambiguous  several entries do                   -> pick the homograph
    no_msa     one does, and it carries no analysis -> the entry needs work

Collapsing them into a bare "could not resolve" reproduces exactly the
failure the requirement exists to prevent: the caller cannot tell which of
those three situations they are in, and the tool has the information and
withheld it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

__all__ = [
    "Candidate",
    "Resolution",
    "LexiconIndex",
    "ResolveOutcome",
    "resolve_spec",
    "resolve_all",
    "refusal_detail",
    "normalize_sense",
]

#: The closed outcome set. Exactly these four strings; the three failures are
#: `parse_morph_unresolved.resolved_to`'s enum verbatim (data-model.md
#: section 4), so renaming one is a contract break.
ResolveOutcome = str

OK = "ok"
NONE = "none"
AMBIGUOUS = "ambiguous"
NO_MSA = "no_msa"

FAILURE_OUTCOMES = frozenset({NONE, AMBIGUOUS, NO_MSA})


# ---------------------------------------------------------------------------
# Plain data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One entry that a piece of the decomposition might have meant.

    `msa_hvo is None` IS the `no_msa` signal -- see data-model.md section 4,
    which spells that out rather than leaving it to be inferred. The field is
    not omitted in that case and not set to a sentinel integer: `None` is the
    fact, and the refusal echoes it so the caller can see *which* candidate
    carried no analysis rather than being told only that something did not.
    """

    headword: str
    sense: Optional[str]
    msa_hvo: Optional[int]
    entry_hvo: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "headword": self.headword,
            "sense": self.sense,
            "msa_hvo": self.msa_hvo,
            "entry_hvo": self.entry_hvo,
        }


@dataclass
class Resolution:
    """What one `MorphSpec` resolved to, and everything considered on the way.

    `candidates` carries the rejected ones too. That is the difference
    between a refusal a caller can act on and one they can only retry: being
    told "kirim is ambiguous" is useless without being told which entries it
    is ambiguous between.
    """

    spec: Any
    msa_hvos: list[int] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    outcome: ResolveOutcome = OK

    @property
    def ok(self) -> bool:
        return self.outcome == OK


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------


def normalize_sense(sense: Any) -> Optional[str]:
    """Reduce a sense given as a gloss or a number to a comparable string.

    A caller writes `sense` as whichever of the two they have in front of
    them, so both are accepted; `None` means "not disambiguated" and is not
    the same as the empty string, which would be a gloss that happens to be
    blank.
    """
    if sense is None:
        return None
    if isinstance(sense, bool):  # bool is an int; never a sense
        return None
    if isinstance(sense, int):
        return str(sense)
    text = str(sense).strip()
    return text or None


class LexiconIndex:
    """Headword -> the entries carrying it, with their analyses.

    BUILT FROM PLAIN ROWS, never from LCM objects. The worker reads the
    project and hands this constructor a list of dicts; this class holds no
    reference to anything belonging to an LCM cache. That is what lets the
    whole of the resolver's decision-making be tested without FieldWorks, and
    it is also why the index can be held across runs without pinning a cache
    open.

    Each row:

        {"headword": str, "entry_hvo": int,
         "senses": [str, ...], "msa_hvos": [int, ...]}

    `msa_hvos` EMPTY IS MEANINGFUL: it is the `no_msa` case, an entry that
    exists and carries no usable analysis. It must not be filtered out at
    build time -- dropping those rows would turn `no_msa` into `none` and
    tell the caller to fix a spelling that is already correct.

    BUILT EXACTLY ONCE PER RUN (FR-020, SC-007). The worker constructs one
    and holds it; `build_count` is incremented here so a test can assert the
    number rather than infer it from timing.
    """

    #: Class-level, deliberately: SC-007 is a claim about how many times the
    #: structure is constructed at all, and an instance counter cannot count
    #: instances that were never meant to exist.
    #:
    #: THIS IS PROCESS-GLOBAL STATE, and it is safe here for one specific
    #: reason: each worker is its own Python process, so the counter is
    #: per-worker and starts at zero when the worker starts -- which is
    #: exactly the scope SC-007 is about. Do not copy this idiom into a
    #: context where several independent users share one import; there it
    #: would count everyone's constructions together and the number would
    #: mean nothing. `reset_build_count()` exists for tests, which do share
    #: an import.
    build_count = 0

    def __init__(self, rows: Iterable[dict[str, Any]]) -> None:
        LexiconIndex.build_count += 1
        self._by_headword: dict[str, list[dict[str, Any]]] = {}
        self._by_msa_hvo: set[int] = set()
        self.row_count = 0

        for row in rows:
            headword = str(row.get("headword") or "").strip()
            if not headword:
                # An entry with no headword cannot be named by one, so it can
                # never be the answer to a headword lookup. Skipped rather
                # than stored under "" -- which would make every spec with a
                # blank headword ambiguous between all of them.
                continue
            self._by_headword.setdefault(headword, []).append(row)
            self._by_msa_hvo.update(int(h) for h in (row.get("msa_hvos") or []))
            self.row_count += 1

    @classmethod
    def reset_build_count(cls) -> None:
        """For tests. Production never calls this."""
        cls.build_count = 0

    def entries_for(self, headword: str) -> list[dict[str, Any]]:
        return list(self._by_headword.get(str(headword).strip(), ()))

    def knows_msa(self, msa_hvo: int) -> bool:
        return int(msa_hvo) in self._by_msa_hvo

    def __len__(self) -> int:
        return self.row_count


def _candidates_from(row: dict[str, Any], sense: Optional[str]) -> list[Candidate]:
    """Every analysis on one entry, as candidates.

    An entry with no analyses still produces ONE candidate, carrying
    `msa_hvo=None`. That candidate is the whole point: it is how the refusal
    can say "this entry exists and has nothing usable on it" instead of
    saying nothing at all.
    """
    headword = str(row.get("headword") or "")
    entry_hvo = int(row.get("entry_hvo") or 0)
    msa_hvos = [int(h) for h in (row.get("msa_hvos") or [])]
    if not msa_hvos:
        return [Candidate(headword, sense, None, entry_hvo)]
    return [Candidate(headword, sense, hvo, entry_hvo) for hvo in msa_hvos]


def _sense_matches(row: dict[str, Any], wanted: Optional[str]) -> bool:
    """Whether an entry carries the sense the caller named.

    Matched against the entry's glosses AND against its 1-based sense
    numbers, because a caller writes whichever they are looking at.
    Case-insensitive on glosses; a linguist typing a gloss from memory should
    not be refused over capitalisation, and a gloss differing only in case is
    not a distinct sense in any project this tool has seen.
    """
    if wanted is None:
        return True
    senses = [str(s) for s in (row.get("senses") or [])]
    if wanted.casefold() in (s.casefold() for s in senses):
        return True
    if wanted.isdigit():
        index = int(wanted)
        return 1 <= index <= len(senses)
    return False


def _sense_filtered(
    rows: list[dict[str, Any]], wanted: Optional[str]
) -> list[dict[str, Any]]:
    """Narrow by sense, but NEVER to nothing.

    If the sense matches no entry, the filter is abandoned and every entry is
    returned. That looks permissive and is the opposite: it keeps the outcome
    `ambiguous` (with the real candidates named) instead of collapsing it to
    `none`. `none` means "no entry has that headword", which would be a false
    statement about a project where the headword exists and only the sense
    was wrong -- and it would send the caller off to fix a spelling that is
    already correct.
    """
    if wanted is None:
        return rows
    narrowed = [row for row in rows if _sense_matches(row, wanted)]
    return narrowed or rows


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


def resolve_spec(spec: Any, index: LexiconIndex) -> Resolution:
    """Resolve one piece. Never raises; the outcome carries the verdict.

    `msa_hvo` wins when present: it IS the identifier, so there is nothing to
    look up. It is still checked against the index, because an identifier
    from a previous session is a session-scoped handle that liblcm renumbers
    on every cache load -- passing one through unverified is the
    stale-hvo class of bug this repository already knows by name (issue
    #103). An unknown identifier resolves to `none` rather than being handed
    to the parser.
    """
    msa_hvo = getattr(spec, "msa_hvo", None)
    if msa_hvo is not None:
        if index.knows_msa(msa_hvo):
            return Resolution(spec=spec, msa_hvos=[int(msa_hvo)], outcome=OK)
        return Resolution(spec=spec, candidates=[], outcome=NONE)

    headword = getattr(spec, "headword", None)
    sense = normalize_sense(getattr(spec, "sense", None))
    rows = index.entries_for(str(headword or ""))

    if not rows:
        # No entry carries this headword. Fix the spelling.
        return Resolution(spec=spec, candidates=[], outcome=NONE)

    rows = _sense_filtered(rows, sense)

    if len(rows) > 1:
        # Several entries carry it. Pick the homograph -- and here are they.
        candidates: list[Candidate] = []
        for row in rows:
            candidates.extend(_candidates_from(row, sense))
        return Resolution(spec=spec, candidates=candidates, outcome=AMBIGUOUS)

    row = rows[0]
    msa_hvos = [int(h) for h in (row.get("msa_hvos") or [])]
    if not msa_hvos:
        # Exactly one entry, and it carries no usable analysis. The entry
        # needs work; the spelling does not.
        return Resolution(
            spec=spec, candidates=_candidates_from(row, sense), outcome=NO_MSA
        )

    return Resolution(
        spec=spec,
        msa_hvos=msa_hvos,
        candidates=_candidates_from(row, sense),
        outcome=OK,
    )


def resolve_all(specs: Iterable[Any], index: LexiconIndex) -> list[Resolution]:
    """Resolve every piece. ALL of them, even after one has failed.

    Deliberately not short-circuiting. Stopping at the first failure would
    let a caller with three bad pieces discover them one round trip at a
    time, and the cost of continuing is a dictionary lookup per piece. Only
    the FIRST failure is reported -- a refusal names one piece and its
    position -- but the rest are resolved so that a future caller-facing
    summary does not need this function changed to provide one.
    """
    return [resolve_spec(spec, index) for spec in specs]


def refusal_detail(resolution: Resolution) -> dict[str, Any]:
    """The `parse_morph_unresolved` payload for a failed resolution.

    FIVE FIELDS, IN THIS EXACT ORDER: `morph`, `position`, `resolved_to`,
    `candidates`, `hint`. The order was the subject of a three-way agreement
    check during CP2's cycle 3 and is pinned by a test
    (`tests/test_response_contract.py`); it is reproduced here rather than
    built from a loop so that reading this function is enough to check it.

    The hint is written per outcome because the three outcomes call for three
    different actions, and a shared hint would be the collapse the outcomes
    exist to avoid.
    """
    spec = resolution.spec
    headword = getattr(spec, "headword", None)
    msa_hvo = getattr(spec, "msa_hvo", None)
    morph = headword if headword is not None else msa_hvo

    if resolution.outcome == AMBIGUOUS:
        hint = (
            f"{morph!r} matches more than one entry, so it is not clear which "
            f"one you mean. Pick one with `sense` (a gloss or a 1-based sense "
            f"number), or give its `msa_hvo` directly -- the candidates below "
            f"carry both."
        )
    elif resolution.outcome == NO_MSA:
        hint = (
            f"{morph!r} matches an entry, but that entry carries no "
            f"morphosyntactic analysis, so there is nothing for the parser to "
            f"be restricted to. This is a gap in the lexicon rather than a "
            f"mistake in your decomposition -- the entry needs an analysis "
            f"before it can appear in one."
        )
    else:
        hint = (
            f"Nothing in this project matches {morph!r}. Pieces are named by "
            f"entry headword, not by the surface string as it appears in the "
            f"word, and there is no segmenter here to bridge the two. Check "
            f"the spelling against the lexicon."
        )

    return {
        "error_code": "parse_morph_unresolved",
        "morph": morph,
        "position": getattr(spec, "position", None),
        "resolved_to": resolution.outcome,
        "candidates": [c.to_dict() for c in resolution.candidates],
        "hint": hint,
    }
