#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 re-plan T103 (FR-017, FR-018, FR-019, FR-031..FR-033,
SC-005; R-10, R-14; data-model 6.4-6.6): `server/sandbox/classify.py`.

The sandbox worker returns each word as a structured `parse` dict
(contracts/sandbox-worker.md section 4):

    {"outcome": "parsed" | "not_parsed" | "invalid_segment" | "error",
     "analyses": [{"morphs": [{form, gloss, guessed, is_circumfix,
                               user_added}, ...], "guessed": bool}] | null,
     "position": int | null,        # 0-based, invalid_segment only
     "error_message": str | null,   # error only
     "parse_time_ms": int | null}

Parse mode turns it into the data-model 6.4 `results.jsonl` line; test mode
compares its analyses, as SETS of ordered (form, gloss) sequences, against a
corpus assertion's expected parses (R-10's four-way table). No text is read:
`hc`'s Expected/Actual sections are retired with the `hc` CLI.

Counters (data-model 6.6 `engine_counters`) are the client's running tally,
reconciled against the recorded lines: FR-017's invariant is that the
summary counts are the direct sum of the per-word classifications.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from flextoolsmcp.server.sandbox import classify as c

LINE_KEYS = ["index", "wordform", "parse"]
PARSE_KEYS = ["parsed", "analysis_count", "outcome", "analyses", "position", "flags",
              "parse_time_ms"]
ANALYSIS_KEYS = ["signature", "rendered_morphs", "morphs", "guessed", "readable", "raw"]
MORPH_KEYS = ["form", "gloss", "guessed", "is_circumfix", "user_added"]
ASSERTION_KEYS = ["classification", "label", "missing", "unexpected", "error_reason"]


def morph(form, gloss, **flags):
    return {"form": form, "gloss": gloss, **flags}


def analysis(*pairs, **flags):
    return {"morphs": [morph(f, g) for f, g in pairs], **flags}


def parsed(*analyses, ms=5):
    return {"outcome": "parsed", "analyses": list(analyses), "parse_time_ms": ms}


NOT_PARSED = {"outcome": "not_parsed", "analyses": [], "parse_time_ms": 1}
INVALID = {"outcome": "invalid_segment", "position": 2, "analyses": None,
           "parse_time_ms": None}
ERROR = {"outcome": "error", "error_message": "RuntimeError: boom", "analyses": None,
         "parse_time_ms": 3}

MEM = [("mem", "ACT"), ("baca", "read")]
BOOK = [("baca", "book")]
READ = [("baca", "read")]


def corpus(*parses):
    """Expected parses in the corpus file's shape: lists of {form, gloss}."""
    return [[{"form": f, "gloss": g} for f, g in p] for p in parses]


# ---------------------------------------------------------------------------
# Parse mode: the data-model 6.4 line
# ---------------------------------------------------------------------------


def test_outcome_enum_is_closed_and_ordered():
    assert c.OUTCOMES == ("parsed", "not_parsed", "invalid_segment", "not_expressible",
                          "error_no_output", "not_reached")


@pytest.mark.parametrize("worker,outcome", [
    (parsed(analysis(*MEM)), "parsed"),
    (NOT_PARSED, "not_parsed"),
    (INVALID, "invalid_segment"),
    (ERROR, "error_no_output"),
    (None, "error_no_output"),
    ({"outcome": "surprise"}, "error_no_output"),
])
def test_worker_outcomes_map_onto_the_line_enum(worker, outcome):
    assert c.outcome_of_worker_parse(worker) == outcome
    line = c.worker_parse_to_line(3, "w", worker)
    assert list(line) == LINE_KEYS and list(line["parse"])[:7] == PARSE_KEYS
    assert line["index"] == 3 and line["wordform"] == "w"
    assert line["parse"]["outcome"] == outcome
    assert line["parse"]["parsed"] is (outcome == "parsed")


def test_a_parsed_line_matches_the_data_model():
    line = c.worker_parse_to_line(0, "membaca", parsed(
        {"morphs": [morph("mem", "ACT"), morph("baca", "read", guessed=True)]}, ms=47))
    section = line["parse"]
    assert section["analysis_count"] == 1 and section["parse_time_ms"] == 47
    assert section["position"] is None and section["flags"] == []
    (only,) = section["analyses"]
    assert list(only) == ANALYSIS_KEYS
    assert only["signature"] is None and only["readable"] is True and only["raw"] is None
    assert only["rendered_morphs"] == ["mem", "baca"]     # forms only (R-14)
    assert [list(m) for m in only["morphs"]] == [MORPH_KEYS, MORPH_KEYS]
    assert only["morphs"][1]["guessed"] is True
    assert only["guessed"] is True                          # any morph guessed


def test_shaping_flags_are_carried_per_morph():
    line = c.worker_parse_to_line(0, "w", parsed({"morphs": [
        morph("a", "A", is_circumfix=True), morph("b", "B", user_added=True)]}))
    morphs = line["parse"]["analyses"][0]["morphs"]
    assert morphs[0]["is_circumfix"] is True and morphs[0]["user_added"] is False
    assert morphs[1]["user_added"] is True and morphs[1]["guessed"] is False


def test_a_not_parsed_line_has_an_empty_list_not_null():
    section = c.worker_parse_to_line(0, "xyz", NOT_PARSED)["parse"]
    assert section["analyses"] == [] and section["analysis_count"] == 0


def test_invalid_segment_position_is_one_based_and_nothing_else_is_kept():
    section = c.worker_parse_to_line(0, "q#", INVALID)["parse"]
    assert section["position"] == 3                          # 0-based 2 -> 1-based 3
    assert section["analyses"] is None and section["analysis_count"] == 0
    assert section["parse_time_ms"] is None


def test_an_engine_error_keeps_its_message_and_no_analyses():
    section = c.worker_parse_to_line(0, "boom", ERROR)["parse"]
    assert section["outcome"] == "error_no_output"
    assert section["error_message"] == "RuntimeError: boom"
    assert section["analyses"] is None                       # FR-018: never zero-parse


def test_a_question_mark_gloss_is_kept_verbatim():
    section = c.worker_parse_to_line(0, "w", parsed(analysis(("w", "?"))))["parse"]
    assert section["analyses"][0]["morphs"][0]["gloss"] == "?"


def test_flags_are_carried():
    section = c.worker_parse_to_line(0, "w", NOT_PARSED, flags=["x"])["parse"]
    assert section["flags"] == ["x"]


@pytest.mark.parametrize("outcome", ["error_no_output", "not_reached", "not_expressible"])
def test_placeholder_lines(outcome):
    line = c.placeholder_line(4, "w", outcome)
    assert line["parse"]["outcome"] == outcome and line["parse"]["analyses"] is None
    assert line["parse"]["parsed"] is False


@pytest.mark.parametrize("outcome", ["parsed", "not_parsed", "nonsense"])
def test_a_placeholder_is_never_a_listed_outcome(outcome):
    with pytest.raises(ValueError):
        c.placeholder_line(0, "w", outcome)


# -- tallies and FR-017's reconciliation ---------------------------------------


def _lines():
    return [
        c.worker_parse_to_line(0, "a", parsed(analysis(*MEM))),
        c.worker_parse_to_line(1, "b", parsed(analysis(*READ), analysis(*BOOK))),
        c.worker_parse_to_line(2, "c", NOT_PARSED),
        c.worker_parse_to_line(3, "d", INVALID),
        c.worker_parse_to_line(4, "e", ERROR),
        c.placeholder_line(5, "f", "not_reached"),
    ]


def test_tally_counts_every_outcome_including_zeros():
    assert c.tally_outcomes(_lines()) == {
        "parsed": 2, "not_parsed": 1, "invalid_segment": 1, "not_expressible": 0,
        "error_no_output": 1, "not_reached": 1}


def test_the_running_tally_reconciles_with_the_lines():
    tally = c.tally_outcomes(_lines())
    counters = c.parse_counters_from(tally)
    assert counters.to_dict() == {"parses": 4, "successful": 2, "failed": 1, "error": 1}
    assert c.reconcile_parse_counters(_lines(), counters) == []


def test_a_diverging_tally_is_recorded_on_neither_side():
    wrong = c.ParseCounters(parses=4, successful=3, failed=0, error=1)
    found = c.reconcile_parse_counters(_lines(), wrong)
    assert [d.counter for d in found] == ["successful", "failed"]
    assert found[0].reported == 3 and found[0].per_word == 2
    assert found[0].text.isascii() and "neither is preferred" in found[0].text


def test_reconciliation_table():
    assert c.PARSE_COUNTER_RECONCILIATION == (
        ("parses", ("parsed", "not_parsed", "invalid_segment")),
        ("successful", ("parsed",)),
        ("failed", ("not_parsed",)),
        ("error", ("invalid_segment",)),
    )


# ---------------------------------------------------------------------------
# Test mode: R-10's four-way table from structured analyses (FR-031..FR-033)
# ---------------------------------------------------------------------------

#: classification -> (expected corpus parses, the worker's returned parses)
FOUR_WAY = {
    "pass": ([MEM], [MEM]),
    "regression": ([MEM, READ], [MEM]),
    "new_ambiguity": ([READ], [READ, BOOK]),
    "changed": ([READ], [BOOK]),
}


def _worker(parses):
    return parsed(*[analysis(*p) for p in parses]) if parses else NOT_PARSED


def test_classification_constants():
    assert c.CLASSIFICATIONS == ("pass", "regression", "new_ambiguity", "changed", "error")
    assert c.ERROR_REASONS == ("invalid_segment", "not_expressible", "error_no_output",
                               "not_reached", "timeout")
    assert c.LABEL_NOW_PARSES == "now_parses"


@pytest.mark.parametrize("classification", list(FOUR_WAY))
def test_four_way_table(classification):
    expected, returned = FOUR_WAY[classification]
    result = c.classify_assertion(corpus(*expected), _worker(returned))
    assert result.classification == classification
    assert result.label is None and result.error_reason is None
    returned_pairs = [tuple(p) for p in returned]
    assert result.missing == tuple(tuple(p) for p in expected if tuple(p) not in returned_pairs)
    unexpected = [tuple((m["form"], m["gloss"]) for m in a["morphs"]) for a in result.unexpected]
    assert unexpected == [tuple(p) for p in returned if list(p) not in [list(e) for e in expected]]


def test_order_of_parses_does_not_matter_but_order_of_morphs_does():
    """Sets of parses; each parse an ORDERED (form, gloss) sequence."""
    result = c.classify_assertion(corpus(READ, BOOK), _worker([BOOK, READ]))
    assert result.classification == "pass"
    swapped = [("baca", "read"), ("mem", "ACT")]
    assert c.classify_assertion(corpus(MEM), _worker([swapped])).classification == "changed"


def test_duplicate_returned_parses_count_once():
    result = c.classify_assertion(corpus(READ), _worker([READ, READ]))
    assert result.classification == "pass"


def test_pair_form_expectations_are_accepted():
    assert c.classify_assertion([MEM], _worker([MEM])).classification == "pass"


def test_nfc_equivalent_forms_match():
    composed, decomposed = "été", "été"
    result = c.classify_assertion(corpus([(composed, "summer")]),
                                  _worker([[(decomposed, "summer")]]))
    assert result.classification == "pass"


def test_expected_no_parse_that_now_parses_is_new_ambiguity_now_parses():
    result = c.classify_assertion([], _worker([READ]))
    assert result.classification == "new_ambiguity"
    assert result.label == "now_parses"


def test_expected_no_parse_still_no_parse_is_pass():
    assert c.classify_assertion([], NOT_PARSED).classification == "pass"


def test_new_ambiguity_with_expectations_has_no_label():
    assert c.classify_assertion(corpus(READ), _worker([READ, BOOK])).label is None


def test_a_question_mark_gloss_expectation_round_trips():
    assert c.classify_assertion(corpus([("w", "?")]),
                                _worker([[("w", "?")]])).classification == "pass"


@pytest.mark.parametrize("worker,reason", [
    (INVALID, "invalid_segment"),
    (ERROR, "error_no_output"),
    (None, "error_no_output"),
])
def test_errors_are_error_with_reason(worker, reason):
    result = c.classify_assertion(corpus(MEM), worker)
    assert (result.classification, result.error_reason) == ("error", reason)
    assert result.missing == () and result.unexpected == ()


@pytest.mark.parametrize("outcome", ["not_reached", "not_expressible", "error_no_output"])
def test_a_placeholder_outcome_overrides_the_worker(outcome):
    result = c.classify_assertion(corpus(MEM), None, outcome=outcome)
    assert (result.classification, result.error_reason) == ("error", outcome)


def test_timeout_reason_for_the_in_flight_word():
    result = c.classify_assertion(corpus(MEM), None, timed_out=True)
    assert result.error_reason == "timeout"


def test_sc005_one_regression_one_new_ambiguity():
    """quickstart's corpus scenario: one edit removes a word's only parse,
    another gives a second word a second parse."""
    baseline = {"membaca": corpus(MEM), "baca": corpus(READ), "xyz": []}
    after = {"membaca": NOT_PARSED, "baca": _worker([READ, BOOK]), "xyz": NOT_PARSED}
    results = {w: c.classify_assertion(baseline[w], after[w]) for w in baseline}
    assert results["membaca"].classification == "regression"
    assert results["membaca"].missing == (tuple(MEM),)
    assert results["baca"].classification == "new_ambiguity"
    assert [a["morphs"] for a in results["baca"].unexpected] == [[morph("baca", "book")]]
    assert results["xyz"].classification == "pass"


def test_bucket_mapping():
    assert c.CLASSIFICATION_BUCKETS == {"pass": "unchanged", "regression": "broken",
                                        "new_ambiguity": "changed", "changed": "changed",
                                        "error": "not_compared"}
    assert c.bucket_for("regression") == "broken"
    with pytest.raises(KeyError):
        c.bucket_for("fixed")


def test_the_word_fixed_is_used_nowhere():
    """FR-033: a word is never called repaired."""
    source = Path(c.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\bfixed\b", source, re.I), "classify.py must not say 'fixed'"
    values = (list(c.CLASSIFICATIONS) + [c.LABEL_NOW_PARSES] + list(c.ERROR_REASONS)
              + list(c.CLASSIFICATION_BUCKETS.values()))
    assert not any("fixed" in v.lower() for v in values)
    for expected, returned in FOUR_WAY.values():
        line = c.assertion_to_line(0, "w", corpus(*expected), _worker(returned))
        assert "fixed" not in json.dumps(line).lower()


# -- the assertion line (data-model 6.5) ---------------------------------------


def test_assertion_line_on_a_pass():
    line = c.assertion_to_line(2, "membaca", corpus(MEM), _worker([MEM]))
    assert list(line) == ["index", "wordform", "parse", "assertion"]
    assert list(line["assertion"]) == ASSERTION_KEYS
    assert line["assertion"]["classification"] == "pass"
    section = line["parse"]
    assert section["outcome"] == "parsed" and section["analysis_count"] == 1
    assert section["analyses"] == []                       # unmatched actual only


def test_assertion_line_on_a_changed():
    line = c.assertion_to_line(0, "baca", corpus(READ), _worker([BOOK]))
    assertion = line["assertion"]
    assert assertion["classification"] == "changed"
    assert assertion["missing"] == [[{"form": "baca", "gloss": "read"}]]
    assert assertion["unexpected"] == [[{"form": "baca", "gloss": "book"}]]
    assert line["parse"]["analyses"][0]["rendered_morphs"] == ["baca"]


def test_assertion_line_counts_distinct_returned_parses():
    line = c.assertion_to_line(0, "baca", corpus(READ), _worker([READ, BOOK, BOOK]))
    assert line["parse"]["analysis_count"] == 2


def test_assertion_line_regression_to_no_parse():
    line = c.assertion_to_line(0, "membaca", corpus(MEM), NOT_PARSED)
    assert line["assertion"]["classification"] == "regression"
    assert line["parse"]["outcome"] == "not_parsed" and line["parse"]["analysis_count"] == 0


def test_assertion_line_expected_no_parse_pass_is_not_parsed():
    line = c.assertion_to_line(0, "xyz", [], NOT_PARSED)
    assert line["assertion"]["classification"] == "pass"
    assert line["parse"]["outcome"] == "not_parsed"


def test_assertion_line_on_an_invalid_segment():
    line = c.assertion_to_line(0, "q#", corpus(MEM), INVALID)
    assert line["assertion"]["error_reason"] == "invalid_segment"
    assert line["parse"]["outcome"] == "invalid_segment"
    assert line["parse"]["position"] == 3 and line["parse"]["analyses"] is None


def test_assertion_line_for_a_placeholder():
    line = c.assertion_to_line(0, "w", corpus(MEM), None, outcome="not_reached")
    assert line["assertion"] == {"classification": "error", "label": None, "missing": [],
                                 "unexpected": [], "error_reason": "not_reached"}
    assert line["parse"]["outcome"] == "not_reached"


def test_assertion_line_timeout():
    line = c.assertion_to_line(0, "w", corpus(MEM), None, timed_out=True)
    assert line["assertion"]["error_reason"] == "timeout"
    assert line["parse"]["outcome"] == "error_no_output"


# -- test-mode tallies (data-model 6.6) -----------------------------------------


def _assertion_lines():
    return [
        c.assertion_to_line(0, "a", corpus(MEM), _worker([MEM])),              # pass
        c.assertion_to_line(1, "b", corpus(READ), _worker([READ, BOOK])),      # new_ambiguity
        c.assertion_to_line(2, "c", corpus(MEM), NOT_PARSED),                  # regression
        c.assertion_to_line(3, "d", corpus(READ), _worker([BOOK])),            # changed
        c.assertion_to_line(4, "e", corpus(MEM), INVALID),                     # error
        c.assertion_to_line(5, "f", corpus(MEM), None, outcome="not_reached"), # error
    ]


def test_tally_classifications():
    assert c.tally_classifications(_assertion_lines()) == {
        "pass": 1, "regression": 1, "new_ambiguity": 1, "changed": 1, "error": 2}


def test_test_counters_count_only_invalid_segment_errors():
    lines = _assertion_lines()
    tally = dict(c.tally_classifications(lines), invalid_segment=1)
    counters = c.test_counters_from(tally)
    assert counters.to_dict() == {"tests": 5, "passed": 1, "failed": 3, "error": 1}
    assert c.reconcile_test_counters(lines, counters) == []


def test_a_diverging_test_tally_is_recorded():
    wrong = c.TestCounters(tests=5, passed=2, failed=2, error=1)
    found = c.reconcile_test_counters(_assertion_lines(), wrong)
    assert [d.counter for d in found] == ["passed", "failed"]
    assert "the running test tally" in found[0].text
