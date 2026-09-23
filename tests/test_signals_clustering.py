#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clustering and the capped drill-down (parser-check CP3, US5; FR-047, FR-048,
SC-016, D-5).

  * Keyed by shared root entry first, category pair otherwise.
  * Representatives by highest analysis count, ties in word-list order,
    capped at three; the heuristic is stated in the output.
  * The drill-down cap is a user-chosen figure within 10-20 and is honoured
    across a session.
  * 0 bulk auto-traces, however many words look suspect -- asserted with
    four hundred of them through the real handler, whose worker pool fails
    the test if anything reaches it.

Run with:
    python -m pytest tests/test_signals_clustering.py -q
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.models import ParseLogInput  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.signals.clustering import (  # noqa: E402
    HEURISTIC_NOTE,
    DrillDownBudget,
    cluster_words,
)
from fixtures.signals_runs import find_report, line, parser_analysis, summary_response, write_run  # noqa: E402


def _suspect(word, order, count, roots=(), cats=()):
    return {"wordform": word, "order": order, "analysis_count": count,
            "roots": list(roots), "categories": list(cats)}


def test_shared_root_entry_is_the_first_key():
    out = cluster_words([
        _suspect("a", 0, 2, roots=["R1"], cats=["n", "v"]),
        _suspect("b", 1, 3, roots=["R1"], cats=["n", "v"]),
        _suspect("c", 2, 2, roots=["R2"], cats=["n", "v"]),
    ])
    first, second = out["clusters"]
    assert (first["key_kind"], first["key"], first["members"]) == ("root_entry", "R1", ["a", "b"])
    # c shares no root with anyone: it falls to its category pair.
    assert (second["key_kind"], second["key"], second["members"]) == ("category_pair", "n/v", ["c"])


def test_representatives_most_analyses_first_ties_in_word_order_capped_at_three():
    suspects = [_suspect(w, i, n, roots=["R"]) for i, (w, n) in
                enumerate([("p", 2), ("q", 5), ("r", 3), ("s", 5), ("t", 3)])]
    [cluster] = cluster_words(suspects)["clusters"]
    assert cluster["representatives"] == ["q", "s", "r"]


def test_the_heuristic_is_stated_in_the_output():
    out = cluster_words([_suspect("a", 0, 2)])
    assert out["heuristic_note"] == HEURISTIC_NOTE
    assert "heuristic" in HEURISTIC_NOTE and "three" in HEURISTIC_NOTE


@pytest.mark.parametrize("cap", [9, 21, 0, -1, True, 12.5])
def test_the_cap_must_be_chosen_within_10_to_20(cap):
    with pytest.raises(ValueError):
        DrillDownBudget(cap)


def test_the_schema_enforces_the_same_range():
    ParseLogInput(run_id="x", drill_down_cap=10)
    ParseLogInput(run_id="x", drill_down_cap=20)
    for bad in (9, 21):
        with pytest.raises(Exception):
            ParseLogInput(run_id="x", drill_down_cap=bad)


def test_the_cap_is_honoured_across_reports_in_a_session():
    budget = DrillDownBudget(10)
    many = [_suspect(f"w{i}", i, 2, roots=[f"R{i // 2}"]) for i in range(40)]
    first = cluster_words(many, budget)
    second = cluster_words(many, budget)
    covered = [w for c in first["clusters"] + second["clusters"]
               for w in c["within_drill_down_budget"]]
    assert len(set(covered)) == 10
    assert budget.remaining == 0


# ---------------------------------------------------------------------------
# Four hundred suspect words, through the real handler
# ---------------------------------------------------------------------------


class _NoPool:
    """Anything that reaches a worker -- a trace included -- fails the test."""

    async def get(self, name):
        raise AssertionError("the report reached a worker: a trace was attempted")

    def peek(self, name):
        raise AssertionError("the report reached a worker: a trace was attempted")

    async def aclose(self):
        pass


@pytest.fixture
def record_dir(tmp_path):
    parse_handler.set_runner(ParseRunner(pool=_NoPool(), record_dir=tmp_path / "runs"))
    parse_handler.reset_drill_down()
    yield tmp_path / "runs"
    parse_handler.set_runner(None)
    parse_handler.reset_drill_down()


def _four_hundred():
    # 400 over-generated words, 20 loose roots of 20 words each.
    return [
        line(i, f"kata{i}", [
            parser_analysis(f"{i}a", kinds=["stem"], entries=[f"root-{i % 20}"]),
            parser_analysis(f"{i}b", kinds=["stem"], entries=[f"root-{i % 20}"]),
        ])
        for i in range(400)
    ]


def test_four_hundred_suspects_are_clustered_not_traced(record_dir):
    record = write_run(record_dir, _four_hundred())
    clusters = find_report(summary_response(record.run_id, drill_down_cap=15))["clusters"]
    assert clusters["suspect_words"] == 400
    assert clusters["auto_trace"] is False
    assert len(clusters["clusters"]) == 20
    for cluster in clusters["clusters"]:
        assert 1 <= len(cluster["representatives"]) <= 3
    covered = {w for c in clusters["clusters"] for w in c["within_drill_down_budget"]}
    assert len(covered) == 15
    assert clusters["drill_down_budget"] == {"cap": 15, "used": 15, "remaining": 0}
    # No trace exists: the report wrote none and reached no worker.
    assert not record.traces_dir.exists() or not any(record.traces_dir.iterdir())


def test_a_session_cannot_be_walked_past_its_cap(record_dir):
    def covered(clusters):
        return {w for c in clusters["clusters"] for w in c["within_drill_down_budget"]}

    record = write_run(record_dir, _four_hundred())
    first = find_report(summary_response(record.run_id, drill_down_cap=10))["clusters"]
    # Asking again, even naming a bigger cap, reads the session's budget:
    # the same ten words stay covered, and not one more.
    again = find_report(summary_response(record.run_id, drill_down_cap=20))["clusters"]
    assert again["drill_down_budget"]["cap"] == 10
    assert again["drill_down_budget"]["remaining"] == 0
    assert covered(again) == covered(first)
    assert len(covered(first)) == 10
