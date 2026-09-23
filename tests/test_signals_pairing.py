#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Candidate pairings and lexicalized forms (parser-check CP3, US5; FR-044,
FR-046).

  * A pairing of one parser analysis with one human meaning-only record is
    surfaced, ranked FIRST in the word's report, names its confidence
    basis, is worded as a suggestion, and is NEVER filed (T083).
  * A derivable word whose parts do not add up to its recorded meaning is a
    candidate lexicalized form with the mandated wording -- not a parse
    error (T084).

Run with:
    python -m pytest tests/test_signals_pairing.py -q
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from flextoolsmcp.server.signals import pairing  # noqa: E402
from flextoolsmcp.server.signals.pairing import (  # noqa: E402
    SENTENCE_LEXICALIZED,
    candidate_pairings,
    lexicalization_finding,
)
from flextoolsmcp.server.signals.report import build_report  # noqa: E402
from fixtures.signals_runs import PARSED_STATE, line, parser_analysis, stored  # noqa: E402

SIGNALS_DIR = REPO_ROOT / "src" / "flextoolsmcp" / "server" / "signals"

#: Verbatim from specs/parser-check/SPEC.md 9.3.2.
MANDATED = (
    "The parser can derive this word, but its parts do not add up to the "
    "recorded meaning. That may indicate a lexicalized form that deserves its "
    "own entry or sense, rather than a parsing error."
)


def _meaning(guid="h", gloss="house"):
    return stored(guid, bundles=0, gloss=gloss)


# ---------------------------------------------------------------------------
# T083
# ---------------------------------------------------------------------------


def test_one_to_one_is_paired_with_its_basis_named():
    l = line(0, "rumah", [parser_analysis("r", glosses=["abode"])], [_meaning()])
    [p] = candidate_pairings(l)
    assert p["confidence_basis"] == ["one_to_one"]
    assert p["human_record_guid"] == "h"
    assert p["filed"] is False


def test_gloss_agreement_picks_the_agreeing_analysis_among_several():
    l = line(0, "rumah", [
        parser_analysis("x", glosses=["", "roof"]),
        parser_analysis("y", glosses=["", "house"]),
    ], [_meaning()])
    [p] = candidate_pairings(l)
    assert p["confidence_basis"] == ["gloss_agreement"]
    assert p["analysis_position"] == 1


def test_both_bases_are_named_when_both_hold():
    l = line(0, "rumah", [parser_analysis("r", glosses=["house"])], [_meaning()])
    assert candidate_pairings(l)[0]["confidence_basis"] == ["one_to_one", "gloss_agreement"]


def test_no_basis_no_pairing():
    l = line(0, "rumah", [parser_analysis("x"), parser_analysis("y")], [_meaning()])
    assert candidate_pairings(l) == []


def test_a_pairing_is_worded_as_a_suggestion():
    l = line(0, "rumah", [parser_analysis("r", glosses=["house"])], [_meaning()])
    text = candidate_pairings(l)[0]["suggestion"]
    assert text.startswith("Suggestion:")
    assert "may be" in text
    assert "nothing has been filed" in text


def test_pairings_are_ranked_first_in_the_word_report():
    l = line(0, "rumah", [parser_analysis("r", glosses=["house"])], [_meaning()])
    [word] = build_report([l], PARSED_STATE)["words"]
    assert list(word)[:2] == ["wordform", "candidate_pairings"]
    assert word["candidate_pairings"]


def test_nothing_in_signals_can_file_a_pairing():
    """No write-shaped call anywhere in the package (FR-044, FR-063)."""
    writes = ("Create", "Add", "SetApprovalStatus", "Delete", "Set", "File", "ProcessParse")
    for path in SIGNALS_DIR.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert not node.func.attr.startswith(writes), f"{path.name}: {node.func.attr}"


# ---------------------------------------------------------------------------
# T084
# ---------------------------------------------------------------------------


def test_the_lexicalization_sentence_is_the_mandated_one():
    assert SENTENCE_LEXICALIZED == MANDATED


def test_a_non_compositional_derivation_is_a_candidate_lexicalized_form():
    l = line(0, "understand",
             [parser_analysis("u", glosses=["beneath", "stand"], forms=["under", "stand"])],
             [_meaning(gloss="comprehend")])
    finding = lexicalization_finding(l)
    assert finding["kind"] == "candidate_lexicalized_form"
    assert finding["sentence"] == MANDATED
    assert finding["is_parse_error"] is False


def test_a_composing_derivation_is_not_lexicalized():
    l = line(0, "rumah2", [parser_analysis("r", glosses=["house", "PL"])],
             [_meaning(gloss="house.PL")])
    assert lexicalization_finding(l) is None


def test_an_underived_word_or_one_without_recorded_meaning_is_not_lexicalized():
    single = line(0, "ya", [parser_analysis("y", glosses=["yes"])], [_meaning(gloss="agree")])
    assert lexicalization_finding(single) is None
    unglossed = line(0, "w", [parser_analysis("w", glosses=["a", "b"])], [])
    assert lexicalization_finding(unglossed) is None


def test_lexicalization_is_not_reported_as_a_parse_error_anywhere():
    l = line(0, "understand",
             [parser_analysis("u", glosses=["beneath", "stand"], forms=["under", "stand"])],
             [_meaning(gloss="comprehend")])
    report = build_report([l], PARSED_STATE)
    [word] = report["words"]
    assert word["lexicalization"]["sentence"] == MANDATED
    assert "error" not in {k for k in word}
    assert pairing.SENTENCE_LEXICALIZED in word["lexicalization"]["sentence"]
