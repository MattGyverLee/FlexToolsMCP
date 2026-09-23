#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The five batch signals (parser-check CP3, US5; FR-035..FR-037).

  * All five ship, and each carries its false-positive explanation IN THE
    OUTPUT -- asserted on the emitted parse_log response, not on a
    docstring (FR-036, T081).
  * The count distribution is a comparison instrument: 0 severity values,
    0 verdict wording, 0 scalar scores (FR-037, T082).
  * Computed from the typed structured result; a run that did not record a
    field says the signal is not computable rather than guessing (FR-035).

Run with:
    python -m pytest tests/test_signals_batch_signals.py -q
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.signals.batch_signals import (  # noqa: E402
    FALSE_POSITIVE_NOTES,
    SIGNAL_IDS,
    batch_signals,
)
from fixtures.signals_runs import (  # noqa: E402
    find_report,
    line,
    parser_analysis,
    summary_response,
    walk,
    write_run,
)


def _lines():
    return [
        # Two analyses, two different roots, two stem categories.
        line(0, "bisa", [
            parser_analysis("b1", kinds=["stem"], entries=["root-A"], cats=["v"]),
            parser_analysis("b2", kinds=["stem"], entries=["root-B"], cats=["n"]),
        ]),
        # A root analysed as affixes alone.
        line(1, "meng", [parser_analysis("m", kinds=["affix", "affix"])]),
        # Three analyses, same root.
        line(2, "makan", [parser_analysis(f"k{i}", kinds=["stem"], entries=["root-C"])
                          for i in range(3)]),
        line(3, "ya", [parser_analysis("y", kinds=["stem"])]),
        line(4, "tidak", []),
    ]


@pytest.fixture
def record_dir(tmp_path):
    class NoPool:
        async def get(self, name):
            raise AssertionError("reached a worker")

        def peek(self, name):
            raise AssertionError("reached a worker")

        async def aclose(self):
            pass

    parse_handler.set_runner(ParseRunner(pool=NoPool(), record_dir=tmp_path / "runs"))
    yield tmp_path / "runs"
    parse_handler.set_runner(None)
    parse_handler.reset_drill_down()


def _by_id(signals):
    return {s["signal_id"]: s for s in signals}


# ---------------------------------------------------------------------------
# T081 -- five signals, each with its false alarm in the output
# ---------------------------------------------------------------------------


def test_exactly_five_signals_ship():
    assert [s["signal_id"] for s in batch_signals(_lines())] == list(SIGNAL_IDS)
    assert len(SIGNAL_IDS) == 5


def test_every_signal_prints_its_false_positive_note_in_the_emitted_response(record_dir):
    record = write_run(record_dir, _lines())
    signals = find_report(summary_response(record.run_id))["signals"]
    assert len(signals) == 5
    for signal in signals:
        note = signal["false_positive_note"]
        assert note == FALSE_POSITIVE_NOTES[signal["signal_id"]]
        assert len(note) > 40, "a false-positive note must actually explain"


def test_each_signal_finds_its_word():
    s = _by_id(batch_signals(_lines()))
    assert [o["wordform"] for o in s["analyses_per_word"]["observations"]] == ["makan", "bisa"]
    assert [o["wordform"] for o in s["root_entry_disagreement"]["observations"]] == ["bisa"]
    assert [o["wordform"] for o in s["root_as_affix_stack"]["observations"]] == ["meng"]
    assert s["incompatible_categories"]["observations"] == [
        {"wordform": "bisa", "categories": ["n", "v"]}
    ]


def test_a_run_without_the_typed_fields_is_not_computable_not_guessed():
    old = [line(0, "w", [{"signature": [["f", "m", None]], "rendered_morphs": ["w"],
                          "category_labels": ["v"], "has_guessed_form": False}])]
    s = _by_id(batch_signals(old))
    for signal_id in ("root_entry_disagreement", "root_as_affix_stack", "incompatible_categories"):
        assert s[signal_id]["computable"] is False
        assert s[signal_id]["observations"] == []
        assert s[signal_id]["false_positive_note"]


# ---------------------------------------------------------------------------
# T082 -- the distribution is an instrument, not a verdict
# ---------------------------------------------------------------------------

VERDICT_WORDS = ("good", "bad", "worse", "better", "healthy", "unhealthy", "broken",
                 "problem", "defect", "wrong", "pass", "fail", "ok")
SCORE_KEYS = ("severity", "score", "verdict", "grade", "rating", "health", "level")


def _distribution(signals):
    return _by_id(signals)["analysis_count_distribution"]


def test_the_distribution_is_a_histogram_beside_its_baseline():
    baseline = [line(i, f"w{i}", [parser_analysis(f"a{i}")]) for i in range(3)]
    dist = _distribution(batch_signals(_lines(), baseline_results=baseline))
    assert dist["has_baseline"] is True
    rows = {r["analysis_count"]: r for r in dist["observations"]}
    assert rows[1] == {"analysis_count": 1, "words": 2, "baseline_words": 3}
    assert rows[3] == {"analysis_count": 3, "words": 1, "baseline_words": 0}


def test_the_distribution_carries_no_severity_score_or_verdict(record_dir):
    record = write_run(record_dir, _lines())
    dist = _distribution(find_report(summary_response(record.run_id))["signals"])
    for _, key, value in walk(dist):
        assert str(key).lower() not in SCORE_KEYS
        if isinstance(value, float):
            raise AssertionError(f"scalar score {key}={value}")
    wording = " ".join(v for _, _, v in walk(dist) if isinstance(v, str)).lower()
    for word in VERDICT_WORDS:
        assert not re.search(rf"\b{word}\b", wording), word
    assert set(dist) == {"signal_id", "observations", "false_positive_note", "has_baseline"}


def test_no_signal_carries_a_severity(record_dir):
    record = write_run(record_dir, _lines())
    for signal in find_report(summary_response(record.run_id))["signals"]:
        for _, key, _ in walk(signal):
            assert str(key).lower() not in SCORE_KEYS
