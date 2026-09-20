#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The morph resolver: three outcomes, one index, zero parses on a refusal
(parser-check CP2b; FR-018, FR-019, FR-020; SC-005, SC-007;
data-model.md section 4).

THE RESOLVER IS THE CORRECTNESS RISK OF THIS CHECKPOINT, and the plan says
so. Everything downstream of it is a restriction handed to `TraceWordXml`:
resolve to too little and a valid decomposition is refused; resolve to too
much and the parser is restricted to something the caller did not write.
Both are the silently-narrowed-search failure FR-019 exists to prevent,
arriving from underneath it rather than from the tool surface.

WHAT IS TESTED HERE AND WHAT IS NOT. This file tests the resolver's
DECISION-MAKING, which is pure: headword to candidates to outcome, over a
plain index. No project is opened and no FieldWorks install is needed, which
is why these are the tests that will actually run on every commit. The
lexicon READ that feeds the index lives in the worker and is exercised in
`tests/test_parse_live.py`; the handler's behaviour around a refusal -- and
the zero-parses negative at the tool boundary -- is in
`tests/test_try_word_handler.py`.

THE THREE FAILURES ARE THREE TESTS, not one parameterised over a shared
assertion. That is deliberate. The failure mode the requirement guards
against is exactly a shared assertion: an implementation that returns "could
not resolve" for all three would pass a test that only checked "it refused",
and the caller would be left unable to tell whether to fix a spelling, pick
a homograph, or conclude the entry has no analysis.

Run with:
    python -m pytest tests/test_parse_resolver.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.models import MorphSpec  # noqa: E402
from flextoolsmcp.server.parse.resolver import (  # noqa: E402
    AMBIGUOUS,
    NO_MSA,
    NONE,
    OK,
    Candidate,
    LexiconIndex,
    normalize_sense,
    refusal_detail,
    resolve_all,
    resolve_spec,
)


#: A lexicon shaped so that every outcome is reachable. Each row is a fact
#: the tests below depend on, so they are named rather than left implicit:
#:
#:   pukul   one entry, one analysis          -> ok
#:   kirim   TWO entries                      -> ambiguous
#:   kosong  one entry, NO analyses           -> no_msa
#:   makan   one entry, TWO analyses          -> ok, both carried through
ROWS = [
    {"headword": "pukul", "entry_hvo": 101, "senses": ["hit"], "msa_hvos": [5001]},
    {"headword": "kirim", "entry_hvo": 102, "senses": ["send"], "msa_hvos": [5002]},
    {"headword": "kirim", "entry_hvo": 103, "senses": ["deliver"], "msa_hvos": [5003]},
    {"headword": "kosong", "entry_hvo": 104, "senses": ["empty"], "msa_hvos": []},
    {
        "headword": "makan",
        "entry_hvo": 105,
        "senses": ["eat", "consume"],
        "msa_hvos": [5004, 5005],
    },
]


@pytest.fixture
def index():
    LexiconIndex.reset_build_count()
    return LexiconIndex(ROWS)


# ---------------------------------------------------------------------------
# FR-018 -- the three input forms a caller can actually write
# ---------------------------------------------------------------------------


def test_a_headword_resolves(index):
    resolution = resolve_spec(MorphSpec(headword="pukul"), index)

    assert resolution.outcome == OK
    assert resolution.msa_hvos == [5001]


def test_a_headword_plus_sense_picks_the_homograph(index):
    """`kirim` alone is ambiguous; `kirim` + a gloss is not."""
    ambiguous = resolve_spec(MorphSpec(headword="kirim"), index)
    assert ambiguous.outcome == AMBIGUOUS

    picked = resolve_spec(MorphSpec(headword="kirim", sense="deliver"), index)
    assert picked.outcome == OK
    assert picked.msa_hvos == [5003]


def test_a_sense_given_as_a_number_also_picks(index):
    """A caller writes whichever of gloss or number is in front of them."""
    picked = resolve_spec(MorphSpec(headword="makan", sense=2), index)
    assert picked.outcome == OK
    assert picked.msa_hvos == [5004, 5005]


def test_a_gloss_matches_regardless_of_case(index):
    """A linguist typing a gloss from memory is not refused over a capital.

    A gloss differing only in case is not a distinct sense in any project
    this tool has seen, so refusing would be a rule with no referent.
    """
    picked = resolve_spec(MorphSpec(headword="kirim", sense="DELIVER"), index)
    assert picked.outcome == OK
    assert picked.msa_hvos == [5003]


def test_an_identifier_resolves_to_itself(index):
    """`msa_hvo` IS the identifier; there is nothing to look up."""
    resolution = resolve_spec(MorphSpec(msa_hvo=5002), index)

    assert resolution.outcome == OK
    assert resolution.msa_hvos == [5002]


def test_an_unknown_identifier_is_refused_rather_than_passed_through(index):
    """A stale hvo must not reach the parser.

    An hvo is a session-scoped handle that liblcm renumbers on every cache
    load, so one carried over from an earlier session resolves to a real but
    DIFFERENT object -- the restriction would be applied to something the
    caller never named, with no exception raised anywhere (issue #103). So
    it is checked against the index rather than trusted.
    """
    resolution = resolve_spec(MorphSpec(msa_hvo=999999), index)

    assert resolution.outcome == NONE
    assert resolution.msa_hvos == []


def test_all_analyses_of_an_entry_are_carried_through(index):
    """An entry with two analyses restricts to both, not to the first.

    Picking one would be the tool choosing between readings on the caller's
    behalf -- a narrowing they did not ask for and cannot see.
    """
    resolution = resolve_spec(MorphSpec(headword="makan"), index)

    assert resolution.outcome == OK
    assert resolution.msa_hvos == [5004, 5005]


# ---------------------------------------------------------------------------
# The three failures, kept distinct (FR-019, data-model.md section 4)
# ---------------------------------------------------------------------------


def test_no_such_headword_is_none(index):
    """Nothing carries it. The action is: fix the spelling."""
    resolution = resolve_spec(MorphSpec(headword="zzzznotaword"), index)

    assert resolution.outcome == NONE
    assert resolution.candidates == []


def test_several_homographs_is_ambiguous_and_names_them(index):
    """Several carry it. The action is: pick one -- and here they are."""
    resolution = resolve_spec(MorphSpec(headword="kirim"), index)

    assert resolution.outcome == AMBIGUOUS
    entry_hvos = sorted(c.entry_hvo for c in resolution.candidates)
    assert entry_hvos == [102, 103], (
        "an ambiguity refusal that does not name the candidates can only be "
        "retried, not acted on"
    )
    assert all(c.msa_hvo is not None for c in resolution.candidates)


def test_an_entry_with_no_analysis_is_no_msa_not_none(index):
    """One carries it, and it has nothing usable. The ENTRY needs work.

    The distinction that matters: reporting this as `none` would send the
    caller off to fix a spelling that is already correct, and they would
    never discover that the lexicon entry is the thing missing an analysis.
    """
    resolution = resolve_spec(MorphSpec(headword="kosong"), index)

    assert resolution.outcome == NO_MSA
    assert resolution.msa_hvos == []
    assert len(resolution.candidates) == 1
    assert resolution.candidates[0].entry_hvo == 104
    assert resolution.candidates[0].msa_hvo is None, (
        "a null msa_hvo IS the no_msa signal (data-model.md section 4); it "
        "must not be omitted or filled with a sentinel"
    )


def test_the_three_outcomes_are_three_different_values(index):
    """The distinction, asserted as a set rather than one at a time.

    A collapse would not show up in any single test above -- each would
    still see "a refusal" -- so the three are compared against each other.
    """
    outcomes = {
        resolve_spec(MorphSpec(headword=h), index).outcome
        for h in ("zzzznotaword", "kirim", "kosong")
    }
    assert outcomes == {NONE, AMBIGUOUS, NO_MSA}, (
        f"the three failures collapsed into {outcomes}"
    )


def test_a_sense_that_matches_nothing_stays_ambiguous(index):
    """A wrong sense must not turn an ambiguity into "no such headword".

    Narrowing to nothing and reporting `none` would be a false statement
    about a project where the headword plainly exists -- and, again, would
    send the caller to fix a spelling that is correct. The filter is
    abandoned instead, and the real candidates are named.
    """
    resolution = resolve_spec(
        MorphSpec(headword="kirim", sense="no-such-gloss"), index
    )

    assert resolution.outcome == AMBIGUOUS
    assert len(resolution.candidates) == 2


# ---------------------------------------------------------------------------
# The refusal payload (FR-019, T037)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headword,expected",
    [("zzzznotaword", NONE), ("kirim", AMBIGUOUS), ("kosong", NO_MSA)],
)
def test_the_refusal_carries_five_fields_in_order(index, headword, expected):
    """`morph`, `position`, `resolved_to`, `candidates`, `hint` -- that order.

    Pinned because the order was the subject of a three-way agreement check
    during CP2's cycle 3, and because a dict whose keys drift is the kind of
    change that passes every behavioural test.
    """
    resolution = resolve_spec(MorphSpec(headword=headword, position=2), index)
    assert resolution.outcome == expected

    detail = refusal_detail(resolution)
    keys = [k for k in detail if k != "error_code"]
    assert keys == ["morph", "position", "resolved_to", "candidates", "hint"], keys
    assert detail["morph"] == headword
    assert detail["position"] == 2
    assert detail["resolved_to"] == expected
    assert detail["hint"]


def test_the_refusal_validates_against_the_shipped_model(index):
    """`extra="forbid"`, so a stray key fails at the far end.

    Validated here, where the payload is built, rather than only at the
    tool boundary -- a mismatch discovered there is discovered by a caller.
    """
    from flextoolsmcp.server.response_models import ParseMorphUnresolvedDetail

    for headword in ("zzzznotaword", "kirim", "kosong"):
        detail = refusal_detail(
            resolve_spec(MorphSpec(headword=headword, position=0), index)
        )
        ParseMorphUnresolvedDetail.model_validate(detail)


def test_the_three_hints_differ(index):
    """Three outcomes, three actions, three hints.

    The enum staying distinct is not enough on its own: a shared hint would
    undo the distinction in the only place the caller actually reads.
    """
    hints = {
        headword: refusal_detail(resolve_spec(MorphSpec(headword=headword), index))[
            "hint"
        ]
        for headword in ("zzzznotaword", "kirim", "kosong")
    }
    assert len(set(hints.values())) == 3, hints


# ---------------------------------------------------------------------------
# FR-020 / SC-007 -- the index is built exactly once per run
# ---------------------------------------------------------------------------


def test_the_index_is_built_once_however_many_pieces_are_resolved():
    """SC-007, counted rather than timed.

    The shape this guards against is an index built per piece: a four-piece
    decomposition would walk the whole lexicon four times, which on a real
    project is the difference between a resolve that is free and one that
    dominates the call. Counted because a timing assertion would be flaky
    and would not say what went wrong.
    """
    LexiconIndex.reset_build_count()
    index = LexiconIndex(ROWS)
    assert LexiconIndex.build_count == 1

    specs = [
        MorphSpec(headword="pukul"),
        MorphSpec(headword="makan"),
        MorphSpec(msa_hvo=5002),
        MorphSpec(headword="kirim", sense="send"),
    ]
    resolutions = resolve_all(specs, index)

    assert len(resolutions) == 4
    assert LexiconIndex.build_count == 1, (
        "the index was rebuilt during resolution; SC-007 requires exactly "
        "one construction per run"
    )


def test_resolve_all_does_not_stop_at_the_first_failure():
    """Every piece is resolved, even after one has failed.

    Only the first failure is reported to the caller -- a refusal names one
    piece -- but resolving the rest costs a dictionary lookup each and means
    a caller with three bad pieces is not made to discover them one round
    trip at a time.
    """
    LexiconIndex.reset_build_count()
    index = LexiconIndex(ROWS)

    resolutions = resolve_all(
        [
            MorphSpec(headword="zzzznotaword"),
            MorphSpec(headword="kirim"),
            MorphSpec(headword="pukul"),
        ],
        index,
    )

    assert [r.outcome for r in resolutions] == [NONE, AMBIGUOUS, OK]


# ---------------------------------------------------------------------------
# The index itself
# ---------------------------------------------------------------------------


def test_an_entry_with_no_analyses_is_kept_in_the_index():
    """Dropping it at build time would turn `no_msa` into `none`.

    This is the single most consequential line in the index builder, so it
    gets a test of its own rather than resting on the `no_msa` case above:
    a filter added here for tidiness would break that case and this one
    names the reason.
    """
    LexiconIndex.reset_build_count()
    index = LexiconIndex(ROWS)

    assert index.entries_for("kosong"), (
        "an entry carrying no analysis was filtered out of the index; it is "
        "what makes the no_msa outcome reachable"
    )


def test_an_entry_with_no_headword_is_not_indexed_under_the_empty_string():
    """It could never answer a headword lookup, and lumping them is worse.

    Stored under `""`, every blank-headword entry would become a candidate
    for every spec whose headword failed to parse -- turning `none` into a
    large and meaningless `ambiguous`.
    """
    LexiconIndex.reset_build_count()
    index = LexiconIndex(
        ROWS + [{"headword": "", "entry_hvo": 106, "senses": [], "msa_hvos": [5006]}]
    )

    assert index.entries_for("") == []
    assert len(index) == len(ROWS)


def test_normalize_sense_distinguishes_absent_from_blank():
    """`None` means "not disambiguated"; it is not a gloss.

    A blank string collapsing to `None` is right; `None` collapsing to `""`
    would make every undisambiguated spec look like it named an empty gloss.
    """
    assert normalize_sense(None) is None
    assert normalize_sense("") is None
    assert normalize_sense("   ") is None
    assert normalize_sense("eat") == "eat"
    assert normalize_sense(2) == "2"
    assert normalize_sense(True) is None, (
        "bool is an int in Python; a True that became the sense '1' would "
        "silently pick the first sense"
    )


def test_a_candidate_serialises_to_the_four_contract_fields():
    candidate = Candidate(headword="kirim", sense=None, msa_hvo=None, entry_hvo=102)

    assert candidate.to_dict() == {
        "headword": "kirim",
        "sense": None,
        "msa_hvo": None,
        "entry_hvo": 102,
    }
