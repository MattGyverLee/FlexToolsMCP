#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Promotion-only ranking (parser-check CP3, US5; FR-045, SC-014, R-10).

THE SINGLE MOST IMPORTANT REGRESSION TEST IN CP3, and written before the
function it tests existed (T075), because the wrong implementation is the
shorter, more natural one: sort the parser's analyses by how close their
composed gloss is to the human's gloss. Morphology is not reliably
compositional -- English `understand` is not `under` + `stand` -- so that sort
systematically demotes the CORRECT analysis of exactly the words where the
morphology is most interesting.

The rule (SPEC 9.3.2):
  * agreement between a composed gloss and the human's gloss PROMOTES;
  * disagreement NEVER demotes;
  * everything not promoted keeps its original order.

The fixture: a non-compositional word whose correct analysis has a composed
gloss FAR from the human gloss, and a compositional-but-wrong competitor whose
composed gloss shares words with it. A sort by gloss distance puts the wrong
one first; this file asserts that ours does not, AND that the sort does -- so
the fixture cannot silently lose the property that makes it worth having.

Run with:
    python -m pytest tests/test_signals_ranking.py -q
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.signals.ranking import glosses_agree, promote  # noqa: E402


def _analysis(name, glosses, kinds=None):
    return {
        "name": name,
        "signature": [[f"f-{name}-{i}", f"m-{name}-{i}", None] for i in range(len(glosses))],
        "rendered_morphs": [f"{name}{i}" for i in range(len(glosses))],
        "category_labels": ["v"] * len(glosses),
        "has_guessed_form": False,
        "morph_glosses": list(glosses),
        "morph_kinds": kinds or (["affix"] * (len(glosses) - 1) + ["stem"]),
    }


HUMAN_GLOSS = "stand firm"

#: CORRECT, and non-compositional: the derivation is real, but its parts do
#: not add up to the word's meaning. The parser lists it first.
CORRECT = _analysis("under-stand", ["beneath", "stand"], ["affix", "stem"])

#: WRONG, and compositional-looking: its composed gloss shares two words with
#: the human's, so any similarity measure puts it closer.
WRONG = _analysis("un-der-stand", ["not", "firm", "stand"], ["affix", "affix", "stem"])


def _names(ranked):
    return [entry["analysis"]["name"] for entry in ranked]


def _sort_by_gloss_distance(analyses, human_gloss):
    """The WRONG implementation this test exists to fail (token overlap)."""
    wanted = set(human_gloss.casefold().split())

    def distance(analysis):
        composed = set(" ".join(analysis["morph_glosses"]).casefold().split())
        return -len(wanted & composed)

    return sorted(analyses, key=distance)


def test_the_correct_non_compositional_analysis_is_not_demoted():
    ranked = promote([CORRECT, WRONG], HUMAN_GLOSS)
    assert _names(ranked) == ["under-stand", "un-der-stand"], (
        "the correct analysis was pushed below a compositional-but-wrong competitor"
    )


def test_a_sort_by_gloss_distance_fails_this_fixture():
    """The fixture discriminates: the natural wrong implementation inverts it."""
    wrong_order = [a["name"] for a in _sort_by_gloss_distance([CORRECT, WRONG], HUMAN_GLOSS)]
    assert wrong_order == ["un-der-stand", "under-stand"]
    assert wrong_order != _names(promote([CORRECT, WRONG], HUMAN_GLOSS))


def test_neither_analysis_is_rendered_as_less_likely():
    ranked = promote([CORRECT, WRONG], HUMAN_GLOSS)
    for entry in ranked:
        assert entry["promoted"] is False
        for key in ("score", "distance", "likelihood", "demoted", "penalty"):
            assert key not in entry, f"{key} renders an analysis as less likely"


def test_agreement_promotes_and_everything_else_keeps_its_order():
    agreeing = _analysis("agree", ["stand firm"], ["stem"])
    other = _analysis("other", ["x", "y"])
    ranked = promote([CORRECT, WRONG, other, agreeing], HUMAN_GLOSS)
    assert _names(ranked) == ["agree", "under-stand", "un-der-stand", "other"]
    assert ranked[0]["promoted"] is True
    assert ranked[0]["basis"] == "gloss_agreement"
    assert [e["original_position"] for e in ranked] == [3, 0, 1, 2]


def test_several_agreeing_analyses_keep_their_order_among_themselves():
    first = _analysis("first", ["stand firm"], ["stem"])
    second = _analysis("second", ["stand", "firm"], ["stem", "stem"])
    ranked = promote([WRONG, second, CORRECT, first], HUMAN_GLOSS)
    assert _names(ranked)[:2] == ["second", "first"]
    assert _names(ranked)[2:] == ["un-der-stand", "under-stand"]


def test_no_human_gloss_changes_nothing():
    ranked = promote([WRONG, CORRECT], "")
    assert _names(ranked) == ["un-der-stand", "under-stand"]
    assert not any(entry["promoted"] for entry in ranked)


def test_agreement_is_strict_not_a_similarity_measure():
    assert glosses_agree(["stand firm"], HUMAN_GLOSS)
    assert glosses_agree(["stand", "firm"], HUMAN_GLOSS)
    assert glosses_agree(["Stand-Firm"], HUMAN_GLOSS)
    assert not glosses_agree(["not", "firm", "stand"], HUMAN_GLOSS)
    assert not glosses_agree(["beneath", "stand"], HUMAN_GLOSS)
    assert not glosses_agree([], HUMAN_GLOSS)


def test_promotion_is_stable_and_total():
    """Nothing is dropped or duplicated by ranking."""
    analyses = [CORRECT, WRONG, _analysis("agree", ["stand firm"], ["stem"])]
    ranked = promote(analyses, HUMAN_GLOSS)
    assert sorted(e["original_position"] for e in ranked) == [0, 1, 2]
