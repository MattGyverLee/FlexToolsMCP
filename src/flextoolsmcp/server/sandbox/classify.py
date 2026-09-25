#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sandbox result lines, assertion classification and counter reconciliation
(parser-check CP5, T047 and T070; data-model 6.4-6.6, research F-8, R-06,
R-08, R-10, R-14; FR-017..FR-019, FR-031..FR-033, SC-005).

Parse mode: an `hc_output.WordResult` becomes the `results.jsonl` sandbox
line -- CP3's line shape with additive keys -- and the per-word tally is
compared with hc's `stats -p` counters.

Line decisions:
  * `parsed` is true ONLY for outcome `parsed`; an unreadable analysis still
    counts (R-08).
  * `analyses` is a list only for `parsed` / `not_parsed`. For every other
    outcome it is null, so `record.HostCounters` never counts a word hc
    produced nothing for as a zero-parse word (FR-018).
  * Each analysis has `signature: null` and `rendered_morphs` = its FORMS
    (R-14); `morphs` carries (form, gloss) for sandbox-to-sandbox diffs.
    Unreadable: `morphs` and `rendered_morphs` null, `raw` the two lines.
  * `parse_time_ms` is CP3's key, from hc's `Parse time:` line when printed.

Test mode: an `hc_output.TestResult` plus the corpus assertion's expected
parses becomes an assertion classification (R-10's four-way table, read from
hc's Expected/Actual sections, never from its pass/fail line) and the
assertion line of data-model 6.5. A word expected to give no parse that now
parses is `new_ambiguity` labelled `now_parses` (FR-033); this module never
calls a word repaired or anything like it. Classifications map onto the diff
buckets (FR-032): regression -> broken, new_ambiguity and changed ->
changed, pass -> unchanged, error -> not_compared.

Counter reconciliation never corrects either side: a mismatch becomes a
`CounterDivergence` whose `text` goes into the run's `counter_divergences`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import hc_output
from .hc_output import (
    OUTCOME_ERROR_NO_OUTPUT,
    OUTCOME_INVALID_SEGMENT,
    OUTCOME_NOT_EXPRESSIBLE,
    OUTCOME_NOT_PARSED,
    OUTCOME_NOT_REACHED,
    OUTCOME_PARSED,
    OUTCOMES,
    TEST_FAILED,
    TEST_PASSED,
    Analysis,
    ParseCounters,
    TestCounters,
    TestResult,
    WordResult,
)

__all__ = [
    "PARSE_COUNTER_RECONCILIATION",
    "TEST_COUNTER_RECONCILIATION",
    "CounterDivergence",
    "analysis_to_dict",
    "word_result_to_line",
    "tally_outcomes",
    "reconcile_parse_counters",
    "CLASS_PASS",
    "CLASS_REGRESSION",
    "CLASS_NEW_AMBIGUITY",
    "CLASS_CHANGED",
    "CLASS_ERROR",
    "CLASSIFICATIONS",
    "LABEL_NOW_PARSES",
    "ERROR_REASON_TIMEOUT",
    "ERROR_REASONS",
    "BUCKET_BROKEN",
    "BUCKET_CHANGED",
    "BUCKET_UNCHANGED",
    "BUCKET_NOT_COMPARED",
    "CLASSIFICATION_BUCKETS",
    "bucket_for",
    "AssertionResult",
    "classify_assertion",
    "assertion_to_line",
    "tally_classifications",
    "reconcile_test_counters",
]

# ---------------------------------------------------------------------------
# Parse mode
# ---------------------------------------------------------------------------

# hc's `stats -p` counter -> the per-word outcomes whose total it must equal.
PARSE_COUNTER_RECONCILIATION: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("parses", (OUTCOME_PARSED, OUTCOME_NOT_PARSED, OUTCOME_INVALID_SEGMENT)),
    ("successful", (OUTCOME_PARSED,)),
    ("failed", (OUTCOME_NOT_PARSED,)),
    ("error", (OUTCOME_INVALID_SEGMENT,)),
)

_LISTED_OUTCOMES = (OUTCOME_PARSED, OUTCOME_NOT_PARSED)


def _pairs_to_dicts(pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    return [{"form": f, "gloss": g} for f, g in pairs]


def analysis_to_dict(analysis: Analysis) -> dict:
    morphs = analysis.morphs
    return {
        "signature": None,
        "rendered_morphs": None if morphs is None else [f for f, _ in morphs],
        "morphs": None if morphs is None else _pairs_to_dicts(morphs),
        "readable": analysis.readable,
        "raw": None if analysis.raw is None else list(analysis.raw),
    }


def _parse_section(
    outcome: str,
    analyses: Optional[Sequence[Analysis]],
    analysis_count: int,
    position: Optional[int],
    flags: Optional[Sequence[str]],
    parse_time_ms: Optional[int],
) -> dict:
    return {
        "parsed": outcome == OUTCOME_PARSED,
        "analysis_count": analysis_count,
        "outcome": outcome,
        "analyses": (
            None if analyses is None else [analysis_to_dict(a) for a in analyses]
        ),
        "position": position,
        "flags": list(flags or []),
        "parse_time_ms": parse_time_ms,
    }


def word_result_to_line(
    index: int,
    wordform: str,
    result: WordResult,
    flags: Optional[Sequence[str]] = None,
) -> dict:
    """The data-model 6.4 line. `wordform` is the SENT word."""
    listed = result.outcome in _LISTED_OUTCOMES
    return {
        "index": index,
        "wordform": wordform,
        "parse": _parse_section(
            result.outcome,
            result.analyses if listed else None,
            len(result.analyses),
            result.position,
            flags,
            result.parse_time_ms,
        ),
    }


def _outcome_of(item: Any) -> str:
    if isinstance(item, Mapping):
        return item["parse"]["outcome"]
    return item.outcome


def tally_outcomes(results: Iterable[Any]) -> dict:
    """Counts for every outcome (zeros included), in `OUTCOMES` order."""
    tally = {outcome: 0 for outcome in OUTCOMES}
    for item in results:
        tally[_outcome_of(item)] += 1
    return tally


@dataclass(frozen=True)
class CounterDivergence:
    """hc's counter and the per-word tally disagree; both values kept."""

    counter: str
    hc: int
    per_word: int
    outcomes: Tuple[str, ...]
    command: str = "stats -p"

    @property
    def text(self) -> str:
        return (
            "hc %s reports %s=%d but the per-word results give %s=%d; "
            "neither is preferred"
            % (
                self.command,
                self.counter,
                self.hc,
                "+".join(self.outcomes),
                self.per_word,
            )
        )


def _reconcile(
    tally: Mapping[str, int],
    counters: Any,
    table: Sequence[Tuple[str, Tuple[str, ...]]],
    command: str,
) -> List[CounterDivergence]:
    divergences = []
    for counter, keys in table:
        per_word = sum(tally[k] for k in keys)
        reported = getattr(counters, counter)
        if per_word != reported:
            divergences.append(
                CounterDivergence(counter, reported, per_word, keys, command)
            )
    return divergences


def reconcile_parse_counters(
    results: Iterable[Any], counters: ParseCounters
) -> List[CounterDivergence]:
    """Divergences in table order; [] means hc and the per-word results agree."""
    return _reconcile(
        tally_outcomes(results), counters, PARSE_COUNTER_RECONCILIATION, "stats -p"
    )


# ---------------------------------------------------------------------------
# Test mode: classification (R-10, FR-031..FR-033)
# ---------------------------------------------------------------------------

CLASS_PASS = "pass"
CLASS_REGRESSION = "regression"
CLASS_NEW_AMBIGUITY = "new_ambiguity"
CLASS_CHANGED = "changed"
CLASS_ERROR = "error"
CLASSIFICATIONS: Tuple[str, ...] = (
    CLASS_PASS,
    CLASS_REGRESSION,
    CLASS_NEW_AMBIGUITY,
    CLASS_CHANGED,
    CLASS_ERROR,
)

LABEL_NOW_PARSES = "now_parses"

ERROR_REASON_TIMEOUT = "timeout"
ERROR_REASONS: Tuple[str, ...] = (
    OUTCOME_INVALID_SEGMENT,
    OUTCOME_NOT_EXPRESSIBLE,
    OUTCOME_ERROR_NO_OUTPUT,
    OUTCOME_NOT_REACHED,
    ERROR_REASON_TIMEOUT,
)
_ERROR_STATUSES = (
    OUTCOME_INVALID_SEGMENT,
    OUTCOME_NOT_EXPRESSIBLE,
    OUTCOME_ERROR_NO_OUTPUT,
    OUTCOME_NOT_REACHED,
)

BUCKET_BROKEN = "broken"
BUCKET_CHANGED = "changed"
BUCKET_UNCHANGED = "unchanged"
BUCKET_NOT_COMPARED = "not_compared"
CLASSIFICATION_BUCKETS = {
    CLASS_PASS: BUCKET_UNCHANGED,
    CLASS_REGRESSION: BUCKET_BROKEN,
    CLASS_NEW_AMBIGUITY: BUCKET_CHANGED,
    CLASS_CHANGED: BUCKET_CHANGED,
    CLASS_ERROR: BUCKET_NOT_COMPARED,
}


def bucket_for(classification: str) -> str:
    """The diff bucket for a classification (KeyError for an unknown one)."""
    return CLASSIFICATION_BUCKETS[classification]


Pairs = Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class AssertionResult:
    """One corpus word's classification with its missing and unexpected parses."""

    classification: str
    label: Optional[str]
    missing: Tuple[Optional[Pairs], ...]
    unexpected: Tuple[Analysis, ...]
    error_reason: Optional[str]


def _as_pairs(parse: Iterable[Any]) -> Pairs:
    """A corpus parse ({form, gloss} dicts or (form, gloss) pairs) as pairs."""
    pairs = []
    for morph in parse:
        if isinstance(morph, Mapping):
            pairs.append((morph["form"], morph["gloss"]))
        else:
            pairs.append((morph[0], morph[1]))
    return tuple(pairs)


def _printed_as(analysis: Analysis, pairs: Pairs) -> bool:
    """Would hc print this corpus parse as `analysis`? (WriteParse, F-7)."""
    if analysis.readable:
        kept = tuple(
            p for p in pairs if max(hc_output.u16len(p[0]), hc_output.u16len(p[1])) > 0
        )
        return analysis.morphs == kept
    rendered = hc_output.render_parse(pairs)
    return tuple(line.rstrip(" ") for line in rendered) == tuple(
        line.rstrip(" ") for line in analysis.raw
    )


def _match_missing(
    printed: Sequence[Analysis], expected: Sequence[Pairs]
) -> Tuple[Optional[Pairs], ...]:
    """Each printed unmatched expected parse as the corpus parse it is."""
    pool = list(expected)
    missing: List[Optional[Pairs]] = []
    for analysis in printed:
        for i, pairs in enumerate(pool):
            if _printed_as(analysis, pairs):
                missing.append(pairs)
                del pool[i]
                break
        else:
            missing.append(analysis.morphs)  # None when unreadable
    return tuple(missing)


def classify_assertion(
    expected: Sequence[Iterable[Any]],
    result: TestResult,
    timed_out: bool = False,
) -> AssertionResult:
    """R-10's four-way table from hc's sections (F-8), or error with a reason."""
    if result.status in _ERROR_STATUSES:
        reason = result.status
        if timed_out and reason == OUTCOME_ERROR_NO_OUTPUT:
            reason = ERROR_REASON_TIMEOUT
        return AssertionResult(CLASS_ERROR, None, (), (), reason)
    if result.status == TEST_PASSED:
        return AssertionResult(CLASS_PASS, None, (), (), None)
    if result.status != TEST_FAILED:
        raise ValueError("unknown test status: %r" % (result.status,))

    expected_pairs = [_as_pairs(p) for p in expected]
    missing = _match_missing(result.expected, expected_pairs)
    unexpected = tuple(result.actual)
    if missing and unexpected:
        classification = CLASS_CHANGED
    elif missing:
        classification = CLASS_REGRESSION
    else:
        classification = CLASS_NEW_AMBIGUITY
    label = (
        LABEL_NOW_PARSES
        if classification == CLASS_NEW_AMBIGUITY and not expected_pairs
        else None
    )
    return AssertionResult(classification, label, missing, unexpected, None)


def assertion_to_line(
    index: int,
    wordform: str,
    expected: Sequence[Iterable[Any]],
    result: TestResult,
    flags: Optional[Sequence[str]] = None,
    timed_out: bool = False,
) -> dict:
    """The data-model 6.5 assertion line. `wordform` is the SENT word."""
    assertion = classify_assertion(expected, result, timed_out=timed_out)
    if assertion.classification == CLASS_ERROR:
        parse = _parse_section(result.status, None, 0, result.position, flags, None)
    else:
        # hc's actual parse count: the matched expectations plus the extras.
        count = len(expected) - len(assertion.missing) + len(assertion.unexpected)
        outcome = OUTCOME_PARSED if count > 0 else OUTCOME_NOT_PARSED
        parse = _parse_section(outcome, assertion.unexpected, count, None, flags, None)
    return {
        "index": index,
        "wordform": wordform,
        "parse": parse,
        "assertion": {
            "classification": assertion.classification,
            "label": assertion.label,
            "missing": [
                None if p is None else _pairs_to_dicts(p) for p in assertion.missing
            ],
            "unexpected": [
                None if a.morphs is None else _pairs_to_dicts(a.morphs)
                for a in assertion.unexpected
            ],
            "error_reason": assertion.error_reason,
        },
    }


# ---------------------------------------------------------------------------
# Test mode: tallies and `stats -t` reconciliation (data-model 6.6)
# ---------------------------------------------------------------------------

# hc's `stats -t` counter -> the classifications whose total it must equal.
# "invalid_segment" means an error whose reason is invalid_segment: hc counts
# only those as errors, since it never sees a not-expressible word.
TEST_COUNTER_RECONCILIATION: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "tests",
        (
            CLASS_PASS,
            CLASS_REGRESSION,
            CLASS_NEW_AMBIGUITY,
            CLASS_CHANGED,
            OUTCOME_INVALID_SEGMENT,
        ),
    ),
    ("passed", (CLASS_PASS,)),
    ("failed", (CLASS_REGRESSION, CLASS_NEW_AMBIGUITY, CLASS_CHANGED)),
    ("error", (OUTCOME_INVALID_SEGMENT,)),
)


def _classification_of(item: Any) -> Tuple[str, Optional[str]]:
    if isinstance(item, Mapping):
        assertion = item["assertion"]
        return assertion["classification"], assertion.get("error_reason")
    return item.classification, item.error_reason


def tally_classifications(assertions: Iterable[Any]) -> dict:
    """Counts for every classification (zeros included), in order."""
    tally = {c: 0 for c in CLASSIFICATIONS}
    for item in assertions:
        tally[_classification_of(item)[0]] += 1
    return tally


def reconcile_test_counters(
    assertions: Iterable[Any], counters: TestCounters
) -> List[CounterDivergence]:
    """Divergences in table order; [] means hc and the assertions agree."""
    items = list(assertions)
    tally = dict(tally_classifications(items))
    tally[OUTCOME_INVALID_SEGMENT] = sum(
        1
        for item in items
        if _classification_of(item) == (CLASS_ERROR, OUTCOME_INVALID_SEGMENT)
    )
    return _reconcile(tally, counters, TEST_COUNTER_RECONCILIATION, "stats -t")
