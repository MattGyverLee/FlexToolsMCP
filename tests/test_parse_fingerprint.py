#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The scope fingerprint (parser-check CP3, US1; T020).

Three properties, each of which a plausible wrong implementation violates:

  * EXACTLY the eight fields of data-model.md section 3 -- no more, no fewer,
    in that order. The field list is transcribed, not re-derived.
  * NOTHING DESCRIBING THE GRAMMAR (FR-011, D-3). A grammar edit between two
    runs is what a comparison exists to measure; a fingerprint that folded in
    a grammar hash would refuse every interesting comparison. The scan below
    looks for grammar-shaped names so that "just add a hash, it's harmless"
    fails a test rather than a review.
  * TWO RUNS DIFFERING ONLY IN ENGINE ARE NOT COMPARABLE (FR-010).

Plus the comparison rule (FR-012): differing fingerprints refuse with
`parse_scope_mismatch` naming `differing_fields`, unless forced; a forced
comparison runs on the intersection only and says so.
"""

import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.models import ResolvedScope  # noqa: E402
from flextoolsmcp.server.parse import fingerprint as fp_mod  # noqa: E402
from flextoolsmcp.server.parse.fingerprint import (  # noqa: E402
    FINGERPRINT_FIELDS,
    FORCED_INTERSECTION_NOTE,
    ScopeFingerprint,
    ScopeMismatch,
    build_fingerprint,
    check_comparable,
    differing_fields,
    restrict_to_intersection,
)
from flextoolsmcp.server.response_models import ParseScopeMismatchDetail  # noqa: E402


# Transcribed from specs/parser-check-cp3/data-model.md section 3, in order.
EXPECTED_FIELDS = (
    "scope_kind",
    "scope_value",
    "text_ids",
    "word_count",
    "limit",
    "truncated",
    "engine",
    "vernacular_ws",
)

GRAMMAR_SHAPED = (
    "grammar", "rule", "phonolog", "morphotactic", "affix", "template",
    "hash", "checksum", "digest", "stamp", "version", "load_error",
    "baseline", "msa", "allomorph", "stratum",
)


def _resolved(**overrides):
    base = dict(
        scope_kind="genre",
        scope_value="Folklore",
        text_ids=[10, 11],
        words=["cicak", "apel", "mangga"],
        count_before_limit=6,
        limit=3,
        truncated=True,
        vernacular_ws="id",
    )
    base.update(overrides)
    return ResolvedScope(**base)


def _fp(**overrides):
    engine = overrides.pop("engine", "HermitCrab")
    return build_fingerprint(_resolved(**overrides), engine=engine)


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

def test_fingerprint_has_exactly_the_eight_fields_in_order():
    names = tuple(f.name for f in dataclasses.fields(ScopeFingerprint))
    assert names == EXPECTED_FIELDS
    assert FINGERPRINT_FIELDS == EXPECTED_FIELDS
    assert tuple(_fp().to_dict()) == EXPECTED_FIELDS


def test_word_count_is_before_the_limit():
    fp = _fp()
    assert fp.word_count == 6
    assert fp.limit == 3
    assert fp.truncated is True


def test_nothing_describing_the_grammar_is_present():
    for name in FINGERPRINT_FIELDS:
        for shape in GRAMMAR_SHAPED:
            assert shape not in name.lower(), (
                f"fingerprint field {name!r} looks grammar-shaped ({shape!r}). "
                f"FR-011/D-3: grammar state is deliberately absent."
            )
    blob = repr(_fp().to_dict()).lower()
    for shape in ("grammar", "hash", "load_error", "baseline"):
        assert shape not in blob


def test_build_fingerprint_takes_no_grammar_input():
    import inspect
    params = set(inspect.signature(build_fingerprint).parameters)
    assert params == {"resolved", "engine"}


def test_fingerprint_round_trips_through_a_dict():
    fp = _fp()
    assert ScopeFingerprint.from_dict(fp.to_dict()) == fp


def test_from_dict_rejects_an_extra_field():
    data = _fp().to_dict()
    data["grammar_hash"] = "abc"
    with pytest.raises(ValueError, match="grammar_hash"):
        ScopeFingerprint.from_dict(data)


def test_text_ids_are_order_insensitive():
    assert _fp(text_ids=[11, 10]) == _fp(text_ids=[10, 11])


# ---------------------------------------------------------------------------
# Comparability (FR-010, FR-012)
# ---------------------------------------------------------------------------

def test_identical_fingerprints_are_comparable():
    outcome = check_comparable(_fp(), _fp())
    assert outcome.comparable is True
    assert outcome.forced is False
    assert outcome.differing_fields == []
    assert outcome.note is None


def test_runs_differing_only_in_engine_are_not_comparable():
    baseline = _fp(engine="HermitCrab")
    current = _fp(engine="XAmple")

    assert differing_fields(baseline, current) == ["engine"]
    with pytest.raises(ScopeMismatch) as refusal:
        check_comparable(baseline, current)

    detail = ParseScopeMismatchDetail.model_validate(refusal.value.detail)
    assert detail.differing_fields == ["engine"]
    assert list(refusal.value.detail) == [
        "error_code", "baseline_fingerprint", "current_fingerprint",
        "differing_fields", "hint",
    ]


def test_runs_differing_in_vernacular_ws_are_not_comparable():
    with pytest.raises(ScopeMismatch) as refusal:
        check_comparable(_fp(vernacular_ws="id"), _fp(vernacular_ws="id-fonipa"))
    assert refusal.value.detail["differing_fields"] == ["vernacular_ws"]


def test_a_text_added_to_a_genre_shows_as_a_difference():
    fields = differing_fields(_fp(text_ids=[10, 11]), _fp(text_ids=[10, 11, 12], count_before_limit=7))
    assert fields == ["text_ids", "word_count"]


def test_differing_fields_are_reported_in_fingerprint_order():
    fields = differing_fields(
        _fp(),
        _fp(vernacular_ws="x", scope_kind="text", limit=None, truncated=False),
    )
    assert fields == ["scope_kind", "limit", "truncated", "vernacular_ws"]


def test_forced_comparison_proceeds_on_the_intersection_and_says_so():
    outcome = check_comparable(_fp(), _fp(text_ids=[10]), force=True)

    assert outcome.comparable is True
    assert outcome.forced is True
    assert outcome.differing_fields == ["text_ids"]
    assert outcome.note == FORCED_INTERSECTION_NOTE
    assert "intersection" in outcome.note


def test_restrict_to_intersection_keeps_baseline_order():
    both = restrict_to_intersection(["c", "a", "b", "d"], ["d", "b", "x", "a"])
    assert both == ["a", "b", "d"]


def test_forcing_identical_fingerprints_is_not_reported_as_forced():
    outcome = check_comparable(_fp(), _fp(), force=True)
    assert outcome.forced is False
    assert outcome.note is None


def test_fingerprint_module_mentions_no_grammar_reader():
    source = Path(fp_mod.__file__).read_text(encoding="utf-8")
    for reader in ("HCParser", "GetGrammar", "PhonologicalData", "MorphologicalData"):
        assert reader not in source


# ---------------------------------------------------------------------------
# Durable text identity (issue #103): the fingerprint records GUIDs, so a
# cache reload that renumbers hvos does not make two runs incomparable
# ---------------------------------------------------------------------------


def test_the_fingerprint_records_text_guids_not_session_hvos():
    today = _fp(text_ids=[10, 11], text_guids=["guid-b", "guid-a"])
    tomorrow = _fp(text_ids=[512, 513], text_guids=["guid-a", "guid-b"])
    assert today == tomorrow, "renumbered hvos must not break comparability"
    assert today.text_ids == ("guid-a", "guid-b")


def test_different_texts_are_still_a_difference():
    fields = differing_fields(
        _fp(text_guids=["guid-a"]), _fp(text_guids=["guid-a", "guid-c"])
    )
    assert fields == ["text_ids"]


def test_a_fingerprint_round_trips_through_meta_json_with_guids():
    import json

    original = _fp(text_guids=["guid-b", "guid-a"])
    restored = ScopeFingerprint.from_dict(json.loads(json.dumps(original.to_dict())))
    assert restored == original
