#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The caller's hypothesis is never overruled
(parser-check CP2b; FR-023, FR-024, FR-025; SC-006; contracts/tools.md,
"The caller's hypothesis is never overruled").

WHAT THIS FILE PROTECTS, in one sentence: a linguist reaches for the
restricted level precisely when the word is irregular and the recorded
analyses are wrong or absent, so a tool that quietly prefers recorded
analyses is useless in exactly the case it was built for.

SC-006 IS SIX ZEROS, and they are asserted as zeros rather than as
behaviour, because each has a plausible-looking implementation that would
pass a "does it work" test:

    0 substitutions   -- "the caller clearly meant this other entry"
    0 widenings       -- "nothing matched, so search everything"
    0 reorderings     -- "canonical order makes the trace easier to read"
    0 scorings        -- "rank the analyses so the best is first"
    0 demotions       -- "this one disagrees with the lexicon, so last"
    0 confidence figures on a user hypothesis
    0 remarks when the proposal agrees with recorded analyses

THE TEST THAT MATTERS MOST is
`test_a_decomposition_disagreeing_with_everything_is_still_traced`. A
ranking-by-agreement implementation -- the most natural wrong thing to
build, because it feels helpful -- passes every other test in this file and
fails that one. It is written so that it cannot be made to pass by
weakening: it asserts the trace happened, with the caller's exact selection,
and that nothing was said about the disagreement.

These run against doubles. The restriction reaching the parser unchanged in
a LIVE run is quickstart scenario 4 (`tests/test_parse_live.py`).

Run with:
    python -m pytest tests/test_parse_proposal.py -q
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402

# The doubles are shared with the handler tests rather than re-declared:
# two stand-ins for one worker drift, and the one in the newer file always
# drifts toward whatever makes its own assertions pass.
from test_try_word_handler import Pool, RecordingWorker  # noqa: E402


#: Any key that would amount to a judgement on the caller's hypothesis.
#: Asserted as an ABSENCE across the whole response, at every nesting level,
#: because the failure mode is additive: someone adds a `confidence` "just
#: for information" and the tool starts grading a linguist's analysis.
_JUDGEMENT_KEYS = re.compile(
    r"confidence|score|rank|probability|likelihood|certainty|"
    r"best|preferred|recommended|quality|grade",
    re.IGNORECASE,
)


def _walk(node, path="$"):
    """Every (path, key, value) in a nested response."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def assert_no_judgement(payload):
    offenders = [
        f"{path}.{key}"
        for path, key, _ in _walk(payload)
        if _JUDGEMENT_KEYS.search(str(key))
    ]
    assert not offenders, (
        "the response grades the caller's hypothesis: "
        + ", ".join(offenders)
        + ". A confidence figure attached to a linguist's own analysis is "
        "the tool substituting its judgement for theirs (FR-024, SC-006)."
    )


@pytest.fixture
def worker():
    return RecordingWorker()


@pytest.fixture
def wired(worker, tmp_path, monkeypatch):
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    parse_handler.set_runner(
        ParseRunner(pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=30.0)
    )
    try:
        yield worker
    finally:
        parse_handler.set_runner(None)


async def call(**kwargs):
    args = {"project_name": "P"}
    args.update(kwargs)
    response = await parse_handler.handle_flextools_try_word(args)
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# FR-023 -- traced exactly as given
# ---------------------------------------------------------------------------


async def test_the_selection_reaching_the_parser_is_the_one_given(wired):
    payload = await call(
        word="makan",
        level="restricted",
        morphs=[{"msa_hvo": 5001}, {"msa_hvo": 5002}],
    )

    assert list(wired.calls[0]["restricted_to"]) == [5001, 5002]
    assert payload["restricted_to"] == [5001, 5002]


async def test_the_order_given_is_the_order_traced(wired):
    """No canonical reordering, however tidy it would look.

    Order is information in a decomposition: it is the caller saying which
    piece comes first. Sorting it would silently answer a different
    question and there would be no way for the caller to see that from the
    response.
    """
    await call(
        word="makan",
        level="restricted",
        morphs=[{"msa_hvo": 5003}, {"msa_hvo": 5001}, {"msa_hvo": 5002}],
    )

    assert list(wired.calls[0]["restricted_to"]) == [5003, 5001, 5002], (
        "the selection was reordered on its way to the parser"
    )


async def test_no_substitution_when_a_similar_entry_exists(wired):
    """`kirim` is ambiguous in the stub lexicon, so it REFUSES.

    It must not quietly pick one of the two. "The caller clearly meant this
    one" is a substitution, and the whole point of the `ambiguous` outcome
    is that the tool does not know which they meant.
    """
    payload = await call(
        word="mengirim", level="restricted", morphs=[{"headword": "kirim"}]
    )

    assert payload["status"] == "error"
    assert payload["error_code"] == "parse_morph_unresolved"
    assert payload["resolved_to"] == "ambiguous"
    assert wired.calls == [], "a substitute was parsed instead of refusing"


async def test_a_refusal_never_widens_to_an_unrestricted_search(wired):
    """Nothing resolved is a refusal, never a fallback to `explain`.

    The underlying component reads an empty restriction as "admit nothing",
    the opposite of "no restriction", and the setting outlives the call --
    so a widening here would not even be contained to this request.
    """
    payload = await call(
        word="makan", level="restricted", morphs=[{"headword": "zzzznotaword"}]
    )

    assert payload["error_code"] == "parse_morph_unresolved"
    assert wired.calls == [], "the refusal widened into a parse"
    assert payload.get("level") != "explain"


# ---------------------------------------------------------------------------
# THE ONE THAT CATCHES RANKING BY AGREEMENT
# ---------------------------------------------------------------------------


async def test_a_decomposition_disagreeing_with_everything_is_still_traced(wired):
    """The case most likely to be implemented wrong, and the reason for it.

    `makan` has nothing to do with `pukul`, so this decomposition disagrees
    with every recorded analysis of the word. It must be traced EXACTLY as
    given: not refused, not widened, not demoted, and not remarked upon as
    a mistake.

    This is not a pedantic case. A proposal diverging from every recorded
    analysis may be the correct analysis of an irregular word -- which is
    precisely when a linguist reaches for this tool. An implementation that
    ranked, demoted or refused by agreement with the lexicon would pass
    every other test in this file and fail here.
    """
    payload = await call(
        word="pukul", level="restricted", morphs=[{"headword": "makan"}]
    )

    assert payload["status"] == "ok", (
        f"a decomposition that disagrees with the lexicon was refused: {payload}"
    )
    assert wired.calls, "nothing was traced"
    assert list(wired.calls[0]["restricted_to"]) == [5004], (
        "the caller's selection was not the one traced"
    )
    assert wired.calls[0]["wordform"] == "pukul"
    assert wired.calls[0]["level"] == "restricted"
    assert_no_judgement(payload)

    # Scanned with the filesystem paths removed: `trace_path` lands under
    # pytest's tmp_path, which embeds the name of THIS test -- so a naive
    # scan matches its own title and fails for a reason that has nothing to
    # do with the response.
    prose = {k: v for k, v in payload.items() if not k.endswith("_path")}
    text = json.dumps(prose).lower()
    for word in ("disagree", "unlikely", "incorrect", "should be", "did you mean"):
        assert word not in text, (
            f"the response editorialises about the caller's hypothesis "
            f"({word!r}); FR-024 allows an observation, not a verdict"
        )


# ---------------------------------------------------------------------------
# FR-024 / FR-025 -- no scoring, and silence on agreement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "morphs",
    [
        [{"msa_hvo": 5001}],
        [{"headword": "makan"}],
        [{"msa_hvo": 5001}, {"msa_hvo": 5002}],
    ],
)
async def test_no_confidence_figure_is_ever_attached(wired, morphs):
    payload = await call(word="makan", level="restricted", morphs=morphs)

    assert payload["status"] == "ok", payload
    assert_no_judgement(payload)


async def test_agreement_produces_no_commentary(wired):
    """The proposal matches a recorded analysis. The tool says nothing.

    A tool that congratulates every correct guess teaches the caller to
    skim the field where the real warnings live -- so the absence here is
    protecting the signal elsewhere, not saving bytes.
    """
    payload = await call(
        word="makan", level="restricted", morphs=[{"headword": "makan"}]
    )

    assert payload["status"] == "ok"
    assert payload["next_step"] is None, (
        "the caller used the right level with a hypothesis that resolved; "
        "there is nothing to steer them toward"
    )
    assert "proposed_decomposition" not in payload, (
        "a decomposition was proposed to a caller who supplied one"
    )
    for key in ("commentary", "observations", "notes", "remarks", "agreement"):
        assert key not in payload, f"agreement produced commentary: {key!r}"


async def test_the_restricted_response_carries_no_alternatives_block(wired):
    """No "you might also have meant" alongside a resolved hypothesis.

    Offering alternatives to a caller who already chose is a demotion
    wearing a helpful hat: it presents the tool's options as peers of the
    caller's analysis.
    """
    payload = await call(
        word="makan", level="restricted", morphs=[{"msa_hvo": 5001}]
    )

    for key in ("alternatives", "candidates", "suggestions", "other_analyses"):
        assert key not in payload, (
            f"{key!r} rides alongside a successful restricted trace; "
            f"candidates belong in a REFUSAL, where they help, not beside a "
            f"result the caller did not question"
        )


# ---------------------------------------------------------------------------
# SC-006 as a count
# ---------------------------------------------------------------------------


async def test_sc006_zeros_across_a_batch_of_hypotheses(wired):
    """The six zeros, counted over a spread of decompositions.

    SC-006 is phrased as "100% of cases" and "0 cases of". A handful of
    individually-passing tests is not a count, so this walks a set and
    tallies, which is also what makes the failure message say how many and
    which.
    """
    cases = [
        ("makan", [{"msa_hvo": 5001}]),
        ("makan", [{"msa_hvo": 5002}, {"msa_hvo": 5001}]),
        ("pukul", [{"headword": "makan"}]),
        ("pukul", [{"headword": "pukul"}]),
        ("mengirim", [{"msa_hvo": 5003}, {"msa_hvo": 5004}]),
    ]

    traced_as_given = 0
    judgements = []
    for word, morphs in cases:
        before = len(wired.calls)
        payload = await call(word=word, level="restricted", morphs=morphs)
        assert payload["status"] == "ok", payload

        expected = [m["msa_hvo"] for m in morphs if "msa_hvo" in m] or None
        recorded = list(wired.calls[before]["restricted_to"])
        if expected is None or recorded == expected:
            traced_as_given += 1

        judgements.extend(
            key for _p, key, _v in _walk(payload) if _JUDGEMENT_KEYS.search(str(key))
        )

    assert traced_as_given == len(cases), (
        f"{len(cases) - traced_as_given} of {len(cases)} decompositions were "
        f"not traced exactly as given"
    )
    assert judgements == [], f"{len(judgements)} confidence figures: {judgements}"
