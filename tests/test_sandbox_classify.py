#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 T039 (FR-017, FR-018, FR-019, R-06, R-14): the parse-mode half
of `server/sandbox/classify.py` -- a `hc_output.WordResult` becomes the
`results.jsonl` sandbox line of data-model section 6.4, and the per-word tally
is reconciled against hc's `stats -p` counters. T064 adds test mode: the
assertion classification and the assertion line of section 6.5.

The API this file specifies
---------------------------
``word_result_to_line(index, wordform, result, flags=None) -> dict``::

    {
      "index": <index>,
      "wordform": <wordform>,            # the SENT word (from dispatch), not the header
      "parse": {
        "parsed": <outcome == "parsed">,  # true ONLY for outcome parsed
        "analysis_count": len(result.analyses),
        "outcome": <outcome>,
        "analyses": [analysis_to_dict(a) ...]   # a list for parsed / not_parsed;
                                                # null for every other outcome, so a
                                                # word hc produced nothing for never
                                                # reads as a zero-parse word
        "position": <printed position> | null,  # set only for invalid_segment
        "flags": list(flags or []),             # e.g. "leading_dash_unverified"
        "parse_time_ms": <int> | null           # CP3's key, when hc printed a time
      }
    }

Key order is exactly as above. ``analysis_to_dict(analysis) -> dict``::

    {"signature": null,
     "rendered_morphs": [forms] | null,               # forms only (R-14)
     "morphs": [{"form", "gloss"}, ...] | null,
     "readable": bool,
     "raw": [morphs_line, gloss_line] | null}         # set only when unreadable

``tally_outcomes(results) -> dict[str, int]``: a count for EVERY value of
``hc_output.OUTCOMES`` (zeros included), in that order. ``results`` items are
``WordResult``s or `results.jsonl` line dicts (``line["parse"]["outcome"]``).

``reconcile_parse_counters(results, counters) -> list[CounterDivergence]``
compares ``hc_output.ParseCounters`` with the per-word tally:

    parses     == parsed + not_parsed + invalid_segment
    successful == parsed
    failed     == not_parsed
    error      == invalid_segment

``PARSE_COUNTER_RECONCILIATION`` is that table as
``(("parses", ("parsed", "not_parsed", "invalid_segment")), ("successful",
("parsed",)), ("failed", ("not_parsed",)), ("error", ("invalid_segment",)))``.
``CounterDivergence`` (frozen dataclass): ``counter`` (hc's name), ``hc``
(hc's value), ``per_word`` (the tally), ``outcomes`` (the tuple compared),
and ``text`` -- one ASCII sentence naming the counter and both numbers, for
the run's ``counter_divergences`` list. Divergences come in table order.
Neither side is corrected; an empty list means agreement. ``command`` is
``"stats -p"`` (default) or ``"stats -t"`` and appears in ``text``.

Test mode (T064; FR-031..FR-033, SC-005; research F-8, R-10; data-model 6.5)
---------------------------------------------------------------------------
Constants: ``CLASS_PASS = "pass"``, ``CLASS_REGRESSION = "regression"``,
``CLASS_NEW_AMBIGUITY = "new_ambiguity"``, ``CLASS_CHANGED = "changed"``,
``CLASS_ERROR = "error"``; ``CLASSIFICATIONS`` (that order);
``LABEL_NOW_PARSES = "now_parses"``; ``ERROR_REASONS = ("invalid_segment",
"not_expressible", "error_no_output", "not_reached", "timeout")``;
``BUCKET_BROKEN = "broken"``, ``BUCKET_CHANGED = "changed"``,
``BUCKET_UNCHANGED = "unchanged"``, ``BUCKET_NOT_COMPARED = "not_compared"``;
``CLASSIFICATION_BUCKETS`` = {pass: unchanged, regression: broken,
new_ambiguity: changed, changed: changed, error: not_compared};
``bucket_for(classification) -> str`` (KeyError for an unknown one).

``classify_assertion(expected, result, timed_out=False) -> AssertionResult``.
``expected`` is the corpus assertion's parse list: each parse a list of
``{"form", "gloss"}`` dicts or ``(form, gloss)`` pairs; ``[]`` = "no parse".
``result`` is an ``hc_output.TestResult``. The four-way table reads hc's
sections (never the pass/fail line):

    Expected None, Actual None -> pass      missing, None  -> regression
    None, extras               -> new_ambiguity   missing, extras -> changed

``expected == []`` that now parses is new_ambiguity with
``label = "now_parses"``; every other label is None. Error statuses give
``error`` with ``error_reason`` = the status; ``timed_out=True`` turns an
``error_no_output`` into ``"timeout"``.

``AssertionResult`` (frozen dataclass)::

    classification: str
    label: Optional[str]
    missing: tuple[Optional[tuple[tuple[str, str], ...]], ...]
        # each printed unmatched expected parse, as the CORPUS parse it matches
        # (matched by morphs, or by re-rendering against the raw lines when the
        # printed columns are unreadable); None if it matches none and is unreadable
    unexpected: tuple[hc_output.Analysis, ...]   # hc's unmatched actual parses
    error_reason: Optional[str]

``assertion_to_line(index, wordform, expected, result, flags=None,
timed_out=False) -> dict`` -- data-model 6.5::

    {"index", "wordform",
     "parse": {parsed, analysis_count, outcome, analyses, position, flags,
               parse_time_ms},     # same keys and order as the parse line
     "assertion": {"classification", "label", "missing", "unexpected",
                   "error_reason"}}

``parse.analyses`` is the unmatched actual parses (``analysis_to_dict``):
``[]`` on a pass; null on an error. ``analysis_count`` = hc's actual parse
count: len(expected) on a pass, len(expected) - len(missing) + len(unexpected)
on a failure, 0 on an error. ``outcome`` = ``parsed`` if analysis_count > 0,
else ``not_parsed``; on an error it is the error status. ``parse_time_ms`` is
null (tests print no time). ``missing`` / ``unexpected`` are lists of
``[{"form", "gloss"}, ...]`` (null for an unreadable one).

``tally_classifications(assertions) -> dict``: every CLASSIFICATIONS key,
zeros included; items are AssertionResults or assertion lines.

``reconcile_test_counters(assertions, counters) -> list[CounterDivergence]``
with ``TEST_COUNTER_RECONCILIATION`` (data-model 6.6; "invalid_segment" means
an error whose reason is invalid_segment -- hc never sees not_expressible):

    tests  == pass + regression + new_ambiguity + changed + invalid_segment
    passed == pass;  failed == regression + new_ambiguity + changed
    error  == invalid_segment

No label, bucket or constant in classify.py uses the word "fixed" (FR-033).
"""

from __future__ import annotations

import importlib
import json

import pytest


def cls():
    return importlib.import_module("flextoolsmcp.server.sandbox.classify")


def hco():
    return importlib.import_module("flextoolsmcp.server.sandbox.hc_output")


BANNER = [
    'Reading configuration file "hc-config.xml"... done.',
    "Compiling rules... done.",
    "Sena Fake loaded.",
    "",
]

# Byte-faithful fixture blocks (ParseCommand.cs / Extensions.WriteParse).
FIXTURES = {
    "parsed": [
        'Parsing "membaca"',
        "Parse 1",
        "Morphs: mem baca",
        "Gloss:  ACT read",
        "Parse time: 12ms",
        "",
    ],
    "not_parsed": ['Parsing "xyz"', "No valid parses.", "Parse time: 0ms", ""],
    "invalid_segment": [
        'Parsing "q#"',
        "The word contains an invalid segment at position 2.",
        "",
    ],
    # Header printed, then hc died: no terminator.
    "error_no_output": ['Parsing "boom"'],
}

PARSE_KEYS = [
    "parsed",
    "analysis_count",
    "outcome",
    "analyses",
    "position",
    "flags",
    "parse_time_ms",
]


def result_for(outcome: str):
    """A WordResult for this outcome, from a fixture when hc prints one."""
    m = hco()
    if outcome in FIXTURES:
        blocks = list(m.iter_blocks(BANNER + FIXTURES[outcome]))
        assert len(blocks) == 1
        return m.parse_block(blocks[0])
    return m.placeholder_result("w", outcome)


# ---------------------------------------------------------------------------
# Every outcome produces a correct line (FR-018)
# ---------------------------------------------------------------------------

EXPECTED = {
    # outcome: (parsed, analysis_count, analyses-is-list, position, parse_time_ms)
    "parsed": (True, 1, True, None, 12),
    "not_parsed": (False, 0, True, None, 0),
    "invalid_segment": (False, 0, False, 2, None),
    "not_expressible": (False, 0, False, None, None),
    "error_no_output": (False, 0, False, None, None),
    "not_reached": (False, 0, False, None, None),
}


def test_expected_table_covers_the_whole_enum():
    assert tuple(EXPECTED) == hco().OUTCOMES


@pytest.mark.parametrize("outcome", list(EXPECTED))
def test_every_outcome_produces_a_correct_line(outcome):
    c = cls()
    result = result_for(outcome)
    assert result.outcome == outcome
    line = c.word_result_to_line(7, "sent-word", result)
    assert list(line) == ["index", "wordform", "parse"]
    assert line["index"] == 7
    assert line["wordform"] == "sent-word"
    parse = line["parse"]
    assert list(parse) == PARSE_KEYS
    parsed, count, is_list, position, ms = EXPECTED[outcome]
    assert parse["parsed"] is parsed
    assert parse["outcome"] == outcome
    assert parse["analysis_count"] == count
    if is_list:
        assert isinstance(parse["analyses"], list)
        assert len(parse["analyses"]) == count
    else:
        assert parse["analyses"] is None
    assert parse["position"] == position
    assert parse["flags"] == []
    assert parse["parse_time_ms"] == ms
    json.dumps(line)  # serialisable as one results.jsonl line


def test_parsed_is_true_only_for_parsed():
    c = cls()
    for outcome in EXPECTED:
        line = c.word_result_to_line(0, "w", result_for(outcome))
        assert line["parse"]["parsed"] is (outcome == "parsed")


def test_parsed_line_matches_data_model_example():
    c = cls()
    line = c.word_result_to_line(0, "membaca", result_for("parsed"))
    assert line["parse"]["analyses"] == [
        {
            "signature": None,
            "rendered_morphs": ["mem", "baca"],
            "morphs": [
                {"form": "mem", "gloss": "ACT"},
                {"form": "baca", "gloss": "read"},
            ],
            "readable": True,
            "raw": None,
        }
    ]


def test_flags_are_carried():
    c = cls()
    line = c.word_result_to_line(
        3, "-an", result_for("not_parsed"), flags=["leading_dash_unverified"]
    )
    assert line["parse"]["flags"] == ["leading_dash_unverified"]


def test_unreadable_analysis_line_keeps_raw_and_nulls_morphs():
    c, m = cls(), hco()
    lines = [
        'Parsing "mpl"',
        "Parse 1",
        "Morphs: m   ",
        "Gloss:  A PL",
        "Parse 2",
        "Morphs: mem baca",
        "Gloss:  ACT read",
        "Parse time: 1ms",
        "",
    ]
    result = m.parse_block(next(iter(m.iter_blocks(lines))))
    line = c.word_result_to_line(0, "mpl", result)
    parse = line["parse"]
    assert parse["parsed"] is True  # unreadable still counts as parsed (R-08)
    assert parse["analysis_count"] == 2
    first, second = parse["analyses"]
    assert first == {
        "signature": None,
        "rendered_morphs": None,
        "morphs": None,
        "readable": False,
        "raw": ["Morphs: m   ", "Gloss:  A PL"],
    }
    assert second["readable"] is True and second["raw"] is None


def test_question_mark_gloss_is_kept_verbatim():
    c, m = cls(), hco()
    lines = [
        'Parsing "baca"',
        "Parse 1",
        "Morphs: baca",
        "Gloss:  ?   ",
        "Parse time: 0ms",
        "",
    ]
    result = m.parse_block(next(iter(m.iter_blocks(lines))))
    analysis = c.word_result_to_line(0, "baca", result)["parse"]["analyses"][0]
    assert analysis["morphs"] == [{"form": "baca", "gloss": "?"}]
    assert analysis["rendered_morphs"] == ["baca"]


def test_analysis_to_dict_direct():
    c, m = cls(), hco()
    analysis = m.read_columns("Morphs: mem baca", "Gloss:  ACT read")
    assert c.analysis_to_dict(analysis)["morphs"][1] == {
        "form": "baca",
        "gloss": "read",
    }


# ---------------------------------------------------------------------------
# Tally and counter reconciliation (FR-017, R-06)
# ---------------------------------------------------------------------------


def _results(*outcomes):
    return [result_for(o) for o in outcomes]


def test_tally_counts_every_outcome_including_zeros():
    c, m = cls(), hco()
    tally = c.tally_outcomes(
        _results("parsed", "parsed", "invalid_segment", "not_reached")
    )
    assert list(tally) == list(m.OUTCOMES)
    assert tally == {
        "parsed": 2,
        "not_parsed": 0,
        "invalid_segment": 1,
        "not_expressible": 0,
        "error_no_output": 0,
        "not_reached": 1,
    }


def test_tally_accepts_results_jsonl_lines():
    c = cls()
    results = _results("parsed", "not_parsed")
    lines = [c.word_result_to_line(i, "w", r) for i, r in enumerate(results)]
    assert c.tally_outcomes(lines) == c.tally_outcomes(results)


def test_reconciliation_table():
    c = cls()
    assert c.PARSE_COUNTER_RECONCILIATION == (
        ("parses", ("parsed", "not_parsed", "invalid_segment")),
        ("successful", ("parsed",)),
        ("failed", ("not_parsed",)),
        ("error", ("invalid_segment",)),
    )


def test_counters_that_agree_give_no_divergence():
    c, m = cls(), hco()
    results = _results(
        "parsed", "parsed", "not_parsed", "invalid_segment", "not_expressible"
    )
    counters = m.ParseCounters(parses=4, successful=2, failed=1, error=1)
    assert c.reconcile_parse_counters(results, counters) == []


def test_mismatch_gives_divergences_and_neither_side_is_overwritten():
    c, m = cls(), hco()
    results = _results("parsed", "not_parsed", "invalid_segment")
    counters = m.ParseCounters(parses=3, successful=3, failed=0, error=0)
    before = [(r.word, r.outcome) for r in results]
    divergences = c.reconcile_parse_counters(results, counters)
    by_counter = {d.counter: d for d in divergences}
    assert set(by_counter) == {"successful", "failed", "error"}
    assert (by_counter["successful"].hc, by_counter["successful"].per_word) == (3, 1)
    assert by_counter["successful"].outcomes == ("parsed",)
    assert (by_counter["failed"].hc, by_counter["failed"].per_word) == (0, 1)
    assert (by_counter["error"].hc, by_counter["error"].per_word) == (0, 1)
    for d in divergences:
        assert d.counter in d.text
        assert str(d.hc) in d.text and str(d.per_word) in d.text
        assert d.text.isascii()
    # Neither side corrected.
    assert counters == m.ParseCounters(parses=3, successful=3, failed=0, error=0)
    assert [(r.word, r.outcome) for r in results] == before
    assert c.tally_outcomes(results)["parsed"] == 1


def test_total_mismatch_is_a_divergence():
    c, m = cls(), hco()
    results = _results("parsed")
    counters = m.ParseCounters(parses=2, successful=1, failed=0, error=0)
    divergences = c.reconcile_parse_counters(results, counters)
    assert [(d.counter, d.hc, d.per_word) for d in divergences] == [("parses", 2, 1)]


def test_mismatch_fixture_end_to_end_through_the_stream():
    c, m = cls(), hco()
    lines = (
        BANNER
        + FIXTURES["parsed"]
        + FIXTURES["not_parsed"]
        + ["# of parses: 2, successful: 0, failed: 2, error: 0", ""]
    )
    stream = m.read_parse_stream(lines, ["membaca", "xyz"], exit_code=0)
    divergences = c.reconcile_parse_counters(stream.results, stream.counters)
    assert [(d.counter, d.hc, d.per_word) for d in divergences] == [
        ("successful", 0, 1),
        ("failed", 2, 1),
    ]


# ===========================================================================
# Test mode (T064): assertion classification (FR-031..FR-033, SC-005)
# ===========================================================================


def _u16(text):
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def _write_parse(parse):
    """Extensions.WriteParse's two lines for (form, gloss) pairs."""
    out = []
    for prefix, pick in (("Morphs: ", 0), ("Gloss:  ", 1)):
        cols = []
        for morph in parse:
            width = max(_u16(morph[0]), _u16(morph[1]))
            if width > 0:
                cols.append(morph[pick] + " " * (width - _u16(morph[pick])))
        out.append(prefix + " ".join(cols))
    return out


def _test_lines(word, missing=None, extras=None, passed=False):
    """TestCommand.Run's block (F-8): only UNMATCHED parses are printed."""
    out = ['Testing "%s"' % word]
    if passed:
        return out + ["Test passed.", ""]
    out += ["Test failed.", "Expected parses:"]
    if not missing:
        out.append("None")
    for parse in missing or []:
        out += _write_parse(parse)
    out.append("Actual parses:")
    if not extras:
        out.append("None")
    for parse in extras or []:
        out += _write_parse([(f, g or "?") for f, g in parse])
    return out + [""]


def _test_result(lines):
    m = hco()
    blocks = list(m.iter_blocks(BANNER + lines))
    assert len(blocks) == 1
    return m.parse_test_block(blocks[0])


MEM = [("mem", "ACT"), ("baca", "read")]
ALT = [("me", "X"), ("mbaca", "Y")]


def as_corpus(*parses):
    """Corpus form (data-model 5): lists of {form, gloss} dicts."""
    return [[{"form": f, "gloss": g} for f, g in p] for p in parses]


def test_classification_constants():
    c = cls()
    assert c.CLASSIFICATIONS == (
        "pass",
        "regression",
        "new_ambiguity",
        "changed",
        "error",
    )
    assert (
        c.CLASS_PASS,
        c.CLASS_REGRESSION,
        c.CLASS_NEW_AMBIGUITY,
        c.CLASS_CHANGED,
        c.CLASS_ERROR,
    ) == c.CLASSIFICATIONS
    assert c.LABEL_NOW_PARSES == "now_parses"
    assert c.ERROR_REASONS == (
        "invalid_segment",
        "not_expressible",
        "error_no_output",
        "not_reached",
        "timeout",
    )


# The four-way table (R-10), from F-8 fixtures: (expected, missing, extras).
FOUR_WAY = {
    "pass": ([MEM], None, None),
    "regression": ([MEM, ALT], [ALT], None),
    "new_ambiguity": ([MEM], None, [ALT]),
    "changed": ([MEM], [MEM], [ALT]),
}


@pytest.mark.parametrize("classification", list(FOUR_WAY))
def test_four_way_table(classification):
    c = cls()
    expected, missing, extras = FOUR_WAY[classification]
    lines = _test_lines(
        "membaca", missing=missing, extras=extras, passed=classification == "pass"
    )
    a = c.classify_assertion(as_corpus(*expected), _test_result(lines))
    assert a.classification == classification
    assert a.label is None
    assert a.error_reason is None
    assert list(a.missing) == [tuple(p) for p in (missing or [])]
    assert [u.morphs for u in a.unexpected] == [tuple(p) for p in (extras or [])]


def test_pair_form_expectations_are_accepted():
    c = cls()
    result = _test_result(_test_lines("membaca", missing=[ALT]))
    a = c.classify_assertion([MEM, ALT], result)
    assert a.classification == "regression"
    assert list(a.missing) == [tuple(ALT)]


def test_expected_no_parse_that_now_parses_is_new_ambiguity_now_parses():
    c = cls()
    result = _test_result(_test_lines("xyz", extras=[[("xy", "A"), ("z", "B")]]))
    a = c.classify_assertion([], result)
    assert a.classification == "new_ambiguity"
    assert a.label == "now_parses"
    assert a.missing == ()


def test_expected_no_parse_still_no_parse_is_pass():
    c = cls()
    a = c.classify_assertion([], _test_result(_test_lines("xyz", passed=True)))
    assert (a.classification, a.label) == ("pass", None)


def test_new_ambiguity_with_expectations_has_no_label():
    c = cls()
    result = _test_result(_test_lines("membaca", extras=[ALT]))
    assert c.classify_assertion(as_corpus(MEM), result).label is None


def test_question_mark_gloss_expectation_round_trips():
    c = cls()
    # Seeded from an empty gloss: the expectation is baca:? and hc prints `?`.
    result = _test_result(_test_lines("baca", missing=[[("baca", "?")]]))
    a = c.classify_assertion(as_corpus([("baca", "read")], [("baca", "?")]), result)
    assert a.classification == "regression"
    assert list(a.missing) == [(("baca", "?"),)]


def test_missing_matched_by_rendering_when_columns_unreadable():
    c = cls()
    odd = [("m", "A"), ("", "PL")]  # prints unreadably (empty form)
    result = _test_result(_test_lines("mpl", missing=[odd]))
    assert result.expected[0].readable is False
    a = c.classify_assertion([MEM, odd], result)
    assert a.classification == "regression"
    assert list(a.missing) == [tuple(odd)]


def test_unmatched_unreadable_missing_is_none():
    c = cls()
    odd = [("m", "A"), ("", "PL")]
    result = _test_result(_test_lines("mpl", missing=[odd]))
    a = c.classify_assertion([MEM], result)  # the corpus does not hold `odd`
    assert list(a.missing) == [None]


def test_duplicate_expectations_are_matched_once_each():
    c = cls()
    result = _test_result(_test_lines("membaca", missing=[MEM, MEM]))
    a = c.classify_assertion([MEM, MEM, ALT], result)
    assert list(a.missing) == [tuple(MEM), tuple(MEM)]


@pytest.mark.parametrize(
    "status", ["invalid_segment", "not_expressible", "error_no_output", "not_reached"]
)
def test_errors_are_error_with_reason(status):
    c, m = cls(), hco()
    if status == "invalid_segment":
        result = _test_result(
            [
                'Testing "q#"',
                "The word contains an invalid segment at position 2.",
                "",
            ]
        )
    else:
        result = m.placeholder_test_result("w", status)
    a = c.classify_assertion([MEM], result)
    assert (a.classification, a.error_reason, a.label) == ("error", status, None)
    assert a.missing == () and a.unexpected == ()


def test_timeout_reason_for_the_in_flight_word():
    c, m = cls(), hco()
    in_flight = m.placeholder_test_result("w", "error_no_output")
    a = c.classify_assertion([MEM], in_flight, timed_out=True)
    assert (a.classification, a.error_reason) == ("error", "timeout")
    later = m.placeholder_test_result("v", "not_reached")
    assert (
        c.classify_assertion([MEM], later, timed_out=True).error_reason == "not_reached"
    )


def test_sc005_one_regression_one_new_ambiguity():
    c = cls()
    corpus = [
        ("membaca", as_corpus(MEM), _test_lines("membaca", passed=True)),
        ("baca", as_corpus([("baca", "read")]), _test_lines("baca", passed=True)),
        (
            "dibaca",
            as_corpus([("di", "PASS"), ("baca", "read")]),
            _test_lines("dibaca", missing=[[("di", "PASS"), ("baca", "read")]]),
        ),
        (
            "bacaan",
            as_corpus([("baca", "read"), ("an", "NMLZ")]),
            _test_lines("bacaan", extras=[[("bacaan", "reading")]]),
        ),
        ("xyz", [], _test_lines("xyz", passed=True)),
    ]
    got = {
        word: c.classify_assertion(expected, _test_result(lines))
        for word, expected, lines in corpus
    }
    assert {w: a.classification for w, a in got.items()} == {
        "membaca": "pass",
        "baca": "pass",
        "dibaca": "regression",
        "bacaan": "new_ambiguity",
        "xyz": "pass",
    }
    assert list(got["dibaca"].missing) == [(("di", "PASS"), ("baca", "read"))]
    assert got["dibaca"].unexpected == ()
    assert got["bacaan"].missing == ()
    assert [u.morphs for u in got["bacaan"].unexpected] == [(("bacaan", "reading"),)]


# -- buckets (FR-032) ---------------------------------------------------------


def test_bucket_mapping():
    c = cls()
    assert (
        c.BUCKET_BROKEN,
        c.BUCKET_CHANGED,
        c.BUCKET_UNCHANGED,
        c.BUCKET_NOT_COMPARED,
    ) == ("broken", "changed", "unchanged", "not_compared")
    assert c.CLASSIFICATION_BUCKETS == {
        "pass": "unchanged",
        "regression": "broken",
        "new_ambiguity": "changed",
        "changed": "changed",
        "error": "not_compared",
    }
    for classification, bucket in c.CLASSIFICATION_BUCKETS.items():
        assert c.bucket_for(classification) == bucket
    # new_ambiguity is never a pass or unchanged.
    assert c.bucket_for("new_ambiguity") != "unchanged"
    with pytest.raises(KeyError):
        c.bucket_for("fixed")


# -- the word "fixed" is never used (FR-033) -----------------------------------


def test_text_scan_finds_fixed_nowhere():
    import re
    from pathlib import Path

    c = cls()
    source = Path(c.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\bfixed\b", source, re.I), "classify.py must not say 'fixed'"
    values = (
        list(c.CLASSIFICATIONS)
        + [c.LABEL_NOW_PARSES]
        + list(c.ERROR_REASONS)
        + list(c.CLASSIFICATION_BUCKETS.values())
    )
    assert not any("fixed" in v.lower() for v in values)
    # Nor in any line it writes.
    for classification, (expected, missing, extras) in FOUR_WAY.items():
        lines = _test_lines(
            "w", missing=missing, extras=extras, passed=classification == "pass"
        )
        line = c.assertion_to_line(0, "w", as_corpus(*expected), _test_result(lines))
        assert "fixed" not in json.dumps(line).lower()
    now = c.assertion_to_line(
        0, "w", [], _test_result(_test_lines("w", extras=[[("w", "X")]]))
    )
    assert "fixed" not in json.dumps(now).lower()
    assert now["assertion"]["label"] == "now_parses"


# -- the assertion line (data-model 6.5) --------------------------------------

ASSERTION_KEYS = ["classification", "label", "missing", "unexpected", "error_reason"]


def test_assertion_line_on_a_pass():
    c = cls()
    result = _test_result(_test_lines("membaca", passed=True))
    line = c.assertion_to_line(4, "membaca", as_corpus(MEM, ALT), result)
    assert list(line) == ["index", "wordform", "parse", "assertion"]
    assert (line["index"], line["wordform"]) == (4, "membaca")
    parse = line["parse"]
    assert list(parse) == PARSE_KEYS
    assert parse["analyses"] == []
    assert parse["analysis_count"] == 2  # = the number of expected parses
    assert (parse["parsed"], parse["outcome"]) == (True, "parsed")
    assert parse["position"] is None and parse["parse_time_ms"] is None
    assert list(line["assertion"]) == ASSERTION_KEYS
    assert line["assertion"] == {
        "classification": "pass",
        "label": None,
        "missing": [],
        "unexpected": [],
        "error_reason": None,
    }
    json.dumps(line)


def test_assertion_line_on_a_changed():
    c = cls()
    result = _test_result(_test_lines("membaca", missing=[MEM], extras=[ALT]))
    line = c.assertion_to_line(0, "membaca", as_corpus(MEM, [("x", "Y")]), result)
    parse = line["parse"]
    # hc found 1 of 2 expected parses plus 1 extra: 2 actual parses.
    assert parse["analysis_count"] == 2
    assert (parse["parsed"], parse["outcome"]) == (True, "parsed")
    assert [a["morphs"] for a in parse["analyses"]] == [
        [{"form": "me", "gloss": "X"}, {"form": "mbaca", "gloss": "Y"}]
    ]
    assertion = line["assertion"]
    assert assertion["classification"] == "changed"
    assert assertion["missing"] == [
        [{"form": "mem", "gloss": "ACT"}, {"form": "baca", "gloss": "read"}]
    ]
    assert assertion["unexpected"] == [
        [{"form": "me", "gloss": "X"}, {"form": "mbaca", "gloss": "Y"}]
    ]


def test_assertion_line_regression_to_no_parse():
    c = cls()
    result = _test_result(_test_lines("membaca", missing=[MEM]))
    line = c.assertion_to_line(0, "membaca", as_corpus(MEM), result)
    parse = line["parse"]
    assert parse["analysis_count"] == 0
    assert (parse["parsed"], parse["outcome"], parse["analyses"]) == (
        False,
        "not_parsed",
        [],
    )
    assert line["assertion"]["classification"] == "regression"


def test_assertion_line_expected_no_parse_pass_is_not_parsed():
    c = cls()
    line = c.assertion_to_line(
        0, "xyz", [], _test_result(_test_lines("xyz", passed=True))
    )
    assert (line["parse"]["parsed"], line["parse"]["outcome"]) == (False, "not_parsed")
    assert line["parse"]["analysis_count"] == 0


def test_assertion_line_unreadable_unexpected_is_null_with_raw_in_analyses():
    c = cls()
    odd = [("m", "A"), ("", "PL")]
    result = _test_result(_test_lines("mpl", extras=[odd]))
    line = c.assertion_to_line(0, "mpl", as_corpus(MEM), result)
    assert line["assertion"]["unexpected"] == [None]
    assert line["parse"]["analyses"][0]["readable"] is False
    assert line["parse"]["analyses"][0]["raw"] == _write_parse(odd)


@pytest.mark.parametrize(
    "status", ["invalid_segment", "not_expressible", "error_no_output", "not_reached"]
)
def test_assertion_line_on_errors(status):
    c, m = cls(), hco()
    if status == "invalid_segment":
        result = m.TestResult("q#", "invalid_segment", (), (), 2)
    else:
        result = m.placeholder_test_result("q#", status)
    line = c.assertion_to_line(1, "q#", as_corpus(MEM), result, flags=["x"])
    parse = line["parse"]
    assert (parse["parsed"], parse["analysis_count"], parse["outcome"]) == (
        False,
        0,
        status,
    )
    assert parse["analyses"] is None
    assert parse["position"] == (2 if status == "invalid_segment" else None)
    assert parse["flags"] == ["x"]
    assert line["assertion"]["classification"] == "error"
    assert line["assertion"]["error_reason"] == status


def test_assertion_line_timeout():
    c, m = cls(), hco()
    result = m.placeholder_test_result("w", "error_no_output")
    line = c.assertion_to_line(0, "w", as_corpus(MEM), result, timed_out=True)
    assert line["assertion"]["error_reason"] == "timeout"
    assert line["parse"]["outcome"] == "error_no_output"


def test_tally_classifications():
    c, m = cls(), hco()
    items = [
        c.classify_assertion(
            as_corpus(MEM), _test_result(_test_lines("a", passed=True))
        ),
        c.classify_assertion(
            as_corpus(MEM), _test_result(_test_lines("b", missing=[MEM]))
        ),
        c.classify_assertion(
            as_corpus(MEM), m.placeholder_test_result("c", "not_reached")
        ),
    ]
    tally = c.tally_classifications(items)
    assert list(tally) == list(c.CLASSIFICATIONS)
    assert tally == {
        "pass": 1,
        "regression": 1,
        "new_ambiguity": 0,
        "changed": 0,
        "error": 1,
    }
    lines = [
        c.assertion_to_line(
            0, "a", as_corpus(MEM), _test_result(_test_lines("a", passed=True))
        )
    ]
    assert c.tally_classifications(lines)["pass"] == 1
