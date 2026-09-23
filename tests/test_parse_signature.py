#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The durable analysis signature (parser-check CP3, US4; FR-031, FR-031a,
FR-032, FR-033; D-2).

  * The signature is the ordered (form, MSA, inflection type) triples, and the
    inflection type distinguishes analyses a two-component signature would
    collapse (D-2).
  * Identical rendered forms under differing identifiers is an IDENTITY
    change -- reported as behavioural change 0 times, and never collapsed to
    unchanged (FR-032, SC-010).
  * The rendered-form fallback is exercised BY FIXTURE, whatever the live
    verification finds, and its ambiguity is stated (FR-033).
  * A guessed-form analysis compares as provisional, never as asserted
    identity (FR-031a).

Run with:
    python -m pytest tests/test_parse_signature.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse import signature as sig  # noqa: E402
from flextoolsmcp.server.parse.signature import (  # noqa: E402
    DurableAnalysisSignature,
    SignatureMode,
    compare_word,
)

ID = SignatureMode.IDENTIFIER
FALLBACK = SignatureMode.RENDERED_FALLBACK
BOTH = pytest.mark.parametrize("mode", [ID, FALLBACK])


def _a(triples, rendered, labels, guessed=False):
    return DurableAnalysisSignature.from_record({
        "signature": [list(t) for t in triples],
        "rendered_morphs": list(rendered),
        "category_labels": list(labels),
        "has_guessed_form": guessed,
    })


MEMBUAT = _a([("f-meN", "m-meN", None), ("f-buat", "m-buat", None)], ["mem", "buat"], ["v", "v"])
# Same text, same categories -- built from re-created lexical objects.
MEMBUAT_RELINKED = _a(
    [("f-meN-2", "m-meN-2", None), ("f-buat", "m-buat", None)], ["mem", "buat"], ["v", "v"]
)
MEMBUAT_NOUN = _a([("f-meN", "m-meN", None), ("f-buat", "m-buat-n", None)], ["mem", "buat"], ["v", "n"])


# ---------------------------------------------------------------------------
# The signature itself
# ---------------------------------------------------------------------------


def test_the_signature_is_the_ordered_identifier_triples():
    assert MEMBUAT.identifier_key() == (("f-meN", "m-meN", None), ("f-buat", "m-buat", None))
    reordered = _a([("f-buat", "m-buat", None), ("f-meN", "m-meN", None)],
                   ["buat", "mem"], ["v", "v"])
    assert reordered.identifier_key() != MEMBUAT.identifier_key(), "order is identity"


@BOTH
def test_the_inflection_type_distinguishes_otherwise_equal_analyses(mode):
    regular = _a([("f-go", "m-go", None)], ["went"], ["v"])
    irregular = _a([("f-go", "m-go", "t-past")], ["went"], ["v"])
    assert regular.identifier_key() != irregular.identifier_key()
    if mode == ID:
        outcome = compare_word("went", [regular], [irregular], mode)
        assert outcome.bucket != "unchanged", "a two-component signature collapses these"


def test_a_two_component_triple_is_padded_not_misread():
    short = DurableAnalysisSignature.from_record({"signature": [["f", "m"]]})
    assert short.identifier_key() == (("f", "m", None),)


def test_a_signature_is_legible_without_the_project():
    assert MEMBUAT.legible() == "mem+buat [v+v]"


# ---------------------------------------------------------------------------
# T063 -- FR-032 / SC-010: identity change is neither changed nor unchanged
# ---------------------------------------------------------------------------


@BOTH
def test_identical_rendered_forms_under_different_ids_is_an_identity_change(mode):
    outcome = compare_word("membuat", [MEMBUAT], [MEMBUAT_RELINKED], mode)
    assert outcome.identity_change is True
    assert outcome.bucket is None, "reported as behavioural change or unchanged"
    assert outcome.bucket != "changed"
    assert outcome.bucket != "unchanged"


@BOTH
def test_a_real_behavioural_change_is_not_called_an_identity_change(mode):
    outcome = compare_word("membuat", [MEMBUAT], [MEMBUAT_NOUN], mode)
    assert outcome.identity_change is False
    assert outcome.bucket == "changed"


@BOTH
def test_identical_analyses_are_unchanged_and_not_an_identity_change(mode):
    outcome = compare_word("membuat", [MEMBUAT], [MEMBUAT], mode)
    assert outcome.bucket == "unchanged" and outcome.identity_change is False


# ---------------------------------------------------------------------------
# T064 -- FR-033: the fallback, by fixture, with its ambiguity stated
# ---------------------------------------------------------------------------


def test_the_fallback_is_in_force_until_stability_is_confirmed(monkeypatch):
    monkeypatch.delenv("FLEXTOOLSMCP_IDENTIFIER_STABILITY", raising=False)
    assert sig.IDENTIFIER_STABILITY != "confirmed", (
        "identifier stability is recorded as confirmed only by the live T125 run"
    )
    assert sig.signature_mode() == FALLBACK
    monkeypatch.setenv("FLEXTOOLSMCP_IDENTIFIER_STABILITY", "confirmed")
    assert sig.signature_mode() == ID
    monkeypatch.setenv("FLEXTOOLSMCP_IDENTIFIER_STABILITY", "disproved")
    assert sig.signature_mode() == FALLBACK


def test_the_fallback_compares_rendered_forms_and_categories():
    """Two homographs with the same category collapse in the fallback --
    the very weakness its note states."""
    homograph_a = _a([("f-bisa-1", "m-bisa-1", None)], ["bisa"], ["adj"])   # 'can'
    homograph_b = _a([("f-bisa-2", "m-bisa-2", None)], ["bisa"], ["adj"])   # 'venom'
    fallback = compare_word("bisa", [homograph_a], [homograph_b], FALLBACK)
    identifier = compare_word("bisa", [homograph_a], [homograph_b], ID)
    assert fallback.identity_change is True
    assert identifier.identity_change is True
    different_category = _a([("f-bisa-1", "m-bisa-1", None)], ["bisa"], ["v"])
    assert compare_word("bisa", [homograph_a], [different_category], FALLBACK).bucket == "changed"


def test_the_fallback_note_states_the_ambiguity():
    note = sig.FALLBACK_AMBIGUITY_NOTE
    assert "rendered morph forms and category labels" in note
    assert "weaker" in note
    assert "may have changed which entry" in note


# ---------------------------------------------------------------------------
# T066 -- FR-031a: a guessed form makes a match provisional
# ---------------------------------------------------------------------------


@BOTH
def test_a_guessed_form_analysis_compares_as_provisional(mode):
    guessed = _a([("f-x", "m-x", None)], ["kucing"], ["n"], guessed=True)
    outcome = compare_word("kucing", [guessed], [guessed], mode)
    assert outcome.provisional is True
    assert outcome.to_dict()["provisional"] is True


@BOTH
def test_no_guessed_form_means_no_provisional_marker(mode):
    outcome = compare_word("membuat", [MEMBUAT], [MEMBUAT], mode)
    assert outcome.provisional is False
    assert "provisional" not in outcome.to_dict()


def test_the_provisional_note_does_not_claim_confirmation():
    assert "provisional rather than confirmed" in sig.PROVISIONAL_NOTE
