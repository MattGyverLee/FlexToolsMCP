#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sandbox result lines, assertion classification and counter reconciliation
(parser-check CP5; re-plan T102/T103; data-model 6.4-6.6, R-10, R-14;
FR-017..FR-019, FR-031..FR-033, SC-005).

The sandbox worker (`parse/worker_main.py --sandbox`) returns each word as a
structured `parse` dict (contracts/sandbox-worker.md section 4): an outcome
and, for a parse, analyses whose morphs are already shaped the way Try A
Word shapes them. Nothing here reads printed text any more.

Parse mode: a worker parse becomes the `results.jsonl` sandbox line -- CP3's
line shape with additive keys.
  * `parsed` is true ONLY for outcome `parsed`.
  * `analyses` is a list only for `parsed` / `not_parsed`. For every other
    outcome it is null, so `record.HostCounters` never counts a word the
    engine produced nothing for as a zero-parse word (FR-018).
  * Each analysis has `signature: null` and `rendered_morphs` = its FORMS
    (R-14); `morphs` carries the worker's morph dicts (form, gloss and the
    shaping flags) for sandbox-to-sandbox diffs.
  * The worker's `error` outcome (the engine threw) is recorded as
    `error_no_output`, the closed enum's member for "nothing came back",
    with the exception text kept as `error_message`.
  * `position` is 1-based, as it was when hc printed it; the worker's is
    0-based (`InvalidShapeException.Position`).

Test mode: a worker parse plus the corpus assertion's expected parses
becomes R-10's four-way classification, comparing the two as SETS of
ordered `(form, gloss)` sequences (FR-031..FR-033): an expected parse the
engine did not return is missing, a returned parse no assertion expected is
unexpected. A word expected to give no parse that now parses is
`new_ambiguity` labelled `now_parses` (FR-033); this module never calls a
word repaired. Classifications map onto the diff buckets (FR-032):
regression -> broken, new_ambiguity and changed -> changed, pass ->
unchanged, error -> not_compared.

Counters (data-model 6.6, `engine_counters`): with no hc process left to
print an independent count, the client keeps a running tally as it
classifies and reconciles it against the recorded lines at the end. A
mismatch is never corrected on either side; it becomes a
`CounterDivergence` whose `text` goes into the run's `counter_divergences`.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "OUTCOME_PARSED",
    "OUTCOME_NOT_PARSED",
    "OUTCOME_INVALID_SEGMENT",
    "OUTCOME_NOT_EXPRESSIBLE",
    "OUTCOME_ERROR_NO_OUTPUT",
    "OUTCOME_NOT_REACHED",
    "OUTCOMES",
    "ParseCounters",
    "TestCounters",
    "PARSE_COUNTER_RECONCILIATION",
    "TEST_COUNTER_RECONCILIATION",
    "CounterDivergence",
    "analysis_to_dict",
    "worker_parse_to_line",
    "placeholder_line",
    "outcome_of_worker_parse",
    "tally_outcomes",
    "parse_counters_from",
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
    "test_counters_from",
    "reconcile_test_counters",
]

# ---------------------------------------------------------------------------
# Outcomes (data-model 6.4, the closed enum, in its order)
# ---------------------------------------------------------------------------

OUTCOME_PARSED = "parsed"
OUTCOME_NOT_PARSED = "not_parsed"
OUTCOME_INVALID_SEGMENT = "invalid_segment"
OUTCOME_NOT_EXPRESSIBLE = "not_expressible"
OUTCOME_ERROR_NO_OUTPUT = "error_no_output"
OUTCOME_NOT_REACHED = "not_reached"
OUTCOMES: Tuple[str, ...] = (
    OUTCOME_PARSED,
    OUTCOME_NOT_PARSED,
    OUTCOME_INVALID_SEGMENT,
    OUTCOME_NOT_EXPRESSIBLE,
    OUTCOME_ERROR_NO_OUTPUT,
    OUTCOME_NOT_REACHED,
)

#: The worker's own outcome vocabulary -> the line's (section 4 -> 6.4).
_WORKER_OUTCOMES = {
    "parsed": OUTCOME_PARSED,
    "not_parsed": OUTCOME_NOT_PARSED,
    "invalid_segment": OUTCOME_INVALID_SEGMENT,
    "error": OUTCOME_ERROR_NO_OUTPUT,
}

_LISTED_OUTCOMES = (OUTCOME_PARSED, OUTCOME_NOT_PARSED)


@dataclass(frozen=True)
class ParseCounters:
    """The client's running parse tally (data-model 6.6 `engine_counters`)."""

    parses: int = 0
    successful: int = 0
    failed: int = 0
    error: int = 0

    def to_dict(self) -> dict:
        return {"parses": self.parses, "successful": self.successful,
                "failed": self.failed, "error": self.error}


@dataclass(frozen=True)
class TestCounters:
    """The client's running test tally (data-model 6.6 `engine_counters`)."""

    __test__ = False  # not a pytest class

    tests: int = 0
    passed: int = 0
    failed: int = 0
    error: int = 0

    def to_dict(self) -> dict:
        return {"tests": self.tests, "passed": self.passed,
                "failed": self.failed, "error": self.error}


# ---------------------------------------------------------------------------
# Parse mode
# ---------------------------------------------------------------------------

# Each counter -> the per-word outcomes whose total it must equal.
PARSE_COUNTER_RECONCILIATION: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("parses", (OUTCOME_PARSED, OUTCOME_NOT_PARSED, OUTCOME_INVALID_SEGMENT)),
    ("successful", (OUTCOME_PARSED,)),
    ("failed", (OUTCOME_NOT_PARSED,)),
    ("error", (OUTCOME_INVALID_SEGMENT,)),
)


def _nfc(text: Any) -> str:
    return unicodedata.normalize("NFC", str(text))


def _morph_dict(morph: Mapping[str, Any]) -> dict:
    return {
        "form": morph.get("form"),
        "gloss": morph.get("gloss"),
        "guessed": bool(morph.get("guessed", False)),
        "is_circumfix": bool(morph.get("is_circumfix", False)),
        "user_added": bool(morph.get("user_added", False)),
    }


def analysis_to_dict(analysis: Mapping[str, Any]) -> dict:
    """One worker analysis as the line's analysis (data-model 6.4)."""
    morphs = [_morph_dict(m) for m in analysis.get("morphs") or []]
    return {
        "signature": None,
        "rendered_morphs": [m["form"] for m in morphs],
        "morphs": morphs,
        "guessed": any(m["guessed"] for m in morphs),
        "readable": True,
        "raw": None,
    }


def _parse_section(
    outcome: str,
    analyses: Optional[Sequence[Mapping[str, Any]]],
    analysis_count: int,
    position: Optional[int],
    flags: Optional[Sequence[str]],
    parse_time_ms: Optional[int],
    error_message: Optional[str] = None,
) -> dict:
    section = {
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
    if error_message is not None:
        section["error_message"] = error_message
    return section


def outcome_of_worker_parse(parse: Optional[Mapping[str, Any]]) -> str:
    """The line outcome for a worker parse; `error_no_output` when absent."""
    if not isinstance(parse, Mapping):
        return OUTCOME_ERROR_NO_OUTPUT
    return _WORKER_OUTCOMES.get(str(parse.get("outcome")), OUTCOME_ERROR_NO_OUTPUT)


def _position_1_based(parse: Mapping[str, Any]) -> Optional[int]:
    position = parse.get("position")
    if isinstance(position, int) and not isinstance(position, bool):
        return position + 1
    return None


def worker_parse_to_line(
    index: int,
    wordform: str,
    parse: Optional[Mapping[str, Any]],
    flags: Optional[Sequence[str]] = None,
) -> dict:
    """The data-model 6.4 line for one worker parse. `wordform` is the SENT word."""
    outcome = outcome_of_worker_parse(parse)
    parse = parse if isinstance(parse, Mapping) else {}
    analyses = list(parse.get("analyses") or [])
    listed = outcome in _LISTED_OUTCOMES
    return {
        "index": index,
        "wordform": wordform,
        "parse": _parse_section(
            outcome,
            analyses if listed else None,
            len(analyses) if listed else 0,
            _position_1_based(parse) if outcome == OUTCOME_INVALID_SEGMENT else None,
            flags,
            parse.get("parse_time_ms") if outcome != OUTCOME_INVALID_SEGMENT else None,
            parse.get("error_message") if outcome == OUTCOME_ERROR_NO_OUTPUT else None,
        ),
    }


def placeholder_line(index: int, wordform: str, outcome: str,
                     flags: Optional[Sequence[str]] = None) -> dict:
    """A line for a word the engine never answered (timeout, crash, cancel)."""
    if outcome not in OUTCOMES or outcome in _LISTED_OUTCOMES:
        raise ValueError("not a placeholder outcome: %r" % (outcome,))
    return {"index": index, "wordform": wordform,
            "parse": _parse_section(outcome, None, 0, None, flags, None)}


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


def parse_counters_from(tally: Mapping[str, int]) -> ParseCounters:
    """The counters a parse-outcome tally implies (the running tally's shape)."""
    return ParseCounters(
        parses=tally.get(OUTCOME_PARSED, 0) + tally.get(OUTCOME_NOT_PARSED, 0)
        + tally.get(OUTCOME_INVALID_SEGMENT, 0),
        successful=tally.get(OUTCOME_PARSED, 0),
        failed=tally.get(OUTCOME_NOT_PARSED, 0),
        error=tally.get(OUTCOME_INVALID_SEGMENT, 0),
    )


@dataclass(frozen=True)
class CounterDivergence:
    """A counter and the per-word tally disagree; both values kept."""

    counter: str
    reported: int
    per_word: int
    outcomes: Tuple[str, ...]
    command: str = "the running parse tally"

    @property
    def text(self) -> str:
        return (
            "%s reports %s=%d but the per-word results give %s=%d; "
            "neither is preferred"
            % (
                self.command,
                self.counter,
                self.reported,
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
    """Divergences in table order; [] means the tally and the lines agree."""
    return _reconcile(
        tally_outcomes(results), counters, PARSE_COUNTER_RECONCILIATION,
        "the running parse tally",
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
    """One corpus word's classification with its missing and unexpected parses.

    `missing` holds expected parses as pairs, in corpus order; `unexpected`
    holds the worker's own analysis dicts, in the order it returned them.
    """

    classification: str
    label: Optional[str]
    missing: Tuple[Pairs, ...]
    unexpected: Tuple[Mapping[str, Any], ...]
    error_reason: Optional[str]


def _as_pairs(parse: Iterable[Any]) -> Pairs:
    """A parse ({form, gloss} dicts or (form, gloss) pairs) as NFC pairs."""
    pairs = []
    for morph in parse:
        if isinstance(morph, Mapping):
            pairs.append((_nfc(morph["form"]), _nfc(morph["gloss"])))
        else:
            pairs.append((_nfc(morph[0]), _nfc(morph[1])))
    return tuple(pairs)


def _pairs_to_dicts(pairs: Sequence[Tuple[str, str]]) -> List[dict]:
    return [{"form": f, "gloss": g} for f, g in pairs]


def classify_assertion(
    expected: Sequence[Iterable[Any]],
    parse: Optional[Mapping[str, Any]],
    timed_out: bool = False,
    outcome: Optional[str] = None,
) -> AssertionResult:
    """R-10's four-way table from the returned analyses, or error with a reason.

    `outcome` overrides the worker's (a placeholder: not reached, timed out).
    """
    outcome = outcome or outcome_of_worker_parse(parse)
    if outcome not in _LISTED_OUTCOMES:
        reason = outcome
        if timed_out and reason == OUTCOME_ERROR_NO_OUTPUT:
            reason = ERROR_REASON_TIMEOUT
        return AssertionResult(CLASS_ERROR, None, (), (), reason)

    expected_pairs: List[Pairs] = []
    for item in expected:
        pairs = _as_pairs(item)
        if pairs not in expected_pairs:
            expected_pairs.append(pairs)

    actual: List[Tuple[Pairs, Mapping[str, Any]]] = []
    seen: set = set()
    for analysis in (parse or {}).get("analyses") or []:
        pairs = _as_pairs(analysis.get("morphs") or [])
        if pairs not in seen:
            seen.add(pairs)
            actual.append((pairs, analysis))

    expected_set = set(expected_pairs)
    missing = tuple(p for p in expected_pairs if p not in seen)
    unexpected = tuple(a for pairs, a in actual if pairs not in expected_set)
    if not missing and not unexpected:
        return AssertionResult(CLASS_PASS, None, (), (), None)
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
    parse: Optional[Mapping[str, Any]],
    flags: Optional[Sequence[str]] = None,
    timed_out: bool = False,
    outcome: Optional[str] = None,
) -> dict:
    """The data-model 6.5 assertion line. `wordform` is the SENT word.

    `parse.analyses` holds the UNMATCHED actual parses (`[]` on a pass), and
    `analysis_count` the number of distinct parses the engine returned.
    """
    assertion = classify_assertion(expected, parse, timed_out=timed_out, outcome=outcome)
    if assertion.classification == CLASS_ERROR:
        worker = parse if isinstance(parse, Mapping) else {}
        position = (_position_1_based(worker)
                    if assertion.error_reason == OUTCOME_INVALID_SEGMENT else None)
        section = _parse_section(assertion.error_reason if assertion.error_reason
                                 in OUTCOMES else OUTCOME_ERROR_NO_OUTPUT,
                                 None, 0, position, flags, None)
    else:
        distinct = {_as_pairs(a.get("morphs") or [])
                    for a in (parse or {}).get("analyses") or []}
        count = len(distinct)
        section = _parse_section(
            OUTCOME_PARSED if count else OUTCOME_NOT_PARSED,
            assertion.unexpected, count, None, flags,
            (parse or {}).get("parse_time_ms"),
        )
    return {
        "index": index,
        "wordform": wordform,
        "parse": section,
        "assertion": {
            "classification": assertion.classification,
            "label": assertion.label,
            "missing": [_pairs_to_dicts(p) for p in assertion.missing],
            "unexpected": [
                _pairs_to_dicts(_as_pairs(a.get("morphs") or []))
                for a in assertion.unexpected
            ],
            "error_reason": assertion.error_reason,
        },
    }


# ---------------------------------------------------------------------------
# Test mode: tallies and reconciliation (data-model 6.6)
# ---------------------------------------------------------------------------

# Each counter -> the classifications whose total it must equal. "error"
# counts only the invalid-segment errors: a not-expressible word is decided
# before dispatch, and the engine never sees it.
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


def _test_tally(items: Sequence[Any]) -> dict:
    tally = dict(tally_classifications(items))
    tally[OUTCOME_INVALID_SEGMENT] = sum(
        1
        for item in items
        if _classification_of(item) == (CLASS_ERROR, OUTCOME_INVALID_SEGMENT)
    )
    return tally


def test_counters_from(tally: Mapping[str, int]) -> TestCounters:
    """The counters a classification tally implies (the running tally's shape)."""
    failed = (tally.get(CLASS_REGRESSION, 0) + tally.get(CLASS_NEW_AMBIGUITY, 0)
              + tally.get(CLASS_CHANGED, 0))
    error = tally.get(OUTCOME_INVALID_SEGMENT, 0)
    passed = tally.get(CLASS_PASS, 0)
    return TestCounters(tests=passed + failed + error, passed=passed, failed=failed, error=error)


test_counters_from.__test__ = False  # not a pytest function


def reconcile_test_counters(
    assertions: Iterable[Any], counters: TestCounters
) -> List[CounterDivergence]:
    """Divergences in table order; [] means the tally and the assertions agree."""
    items = list(assertions)
    return _reconcile(_test_tally(items), counters, TEST_COUNTER_RECONCILIATION,
                      "the running test tally")
