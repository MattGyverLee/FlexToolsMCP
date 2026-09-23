#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Projections -- computed, reported, acted on by nothing (parser-check CP3,
US5; FR-050, SC-015).

  * The deletion projection over one segment-referenced and one
    unreferenced candidate returns EXACTLY ONE; a bare no-opinion
    projection over the same fixture returns two and fails (T086).
  * The duplicate projection counts filings that would duplicate an
    existing meaning-only record; no part of the write ladder ships -- no
    confirmation, no filing path (T087).

Run with:
    python -m pytest tests/test_signals_projections.py -q
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from flextoolsmcp.server.signals import projections  # noqa: E402
from flextoolsmcp.server.signals.projections import (  # noqa: E402
    deletion_projection,
    duplicate_projection,
)
from fixtures.signals_runs import line, parser_analysis, stored  # noqa: E402

PROJECTIONS_SOURCE = Path(projections.__file__)


def _sc015_fixture():
    """Two parser-created, no-opinion analyses: one a text uses, one it does not."""
    return [
        line(0, "rumah", [parser_analysis("r")], [
            stored("in-text", opinion="noopinion", parser_evaluated=True, in_segment=True),
            stored("unused", opinion="noopinion", parser_evaluated=True, in_segment=False),
        ]),
    ]


def _bare_no_opinion(results):
    """The WRONG projection: drops the segment conjunct."""
    return [
        r for l in results for r in l["parse"]["human_analyses"]
        if r["parser_evaluated"] and r["opinion"] == "noopinion"
    ]


# ---------------------------------------------------------------------------
# T086
# ---------------------------------------------------------------------------


def test_the_deletion_projection_returns_exactly_one():
    out = deletion_projection(_sc015_fixture())
    assert out["count"] == 1
    assert [c["analysis_guid"] for c in out["candidates"]] == ["unused"]


def test_a_bare_no_opinion_projection_returns_two_and_so_fails():
    bare = _bare_no_opinion(_sc015_fixture())
    assert len(bare) == 2
    assert len(bare) != deletion_projection(_sc015_fixture())["count"]


def test_all_three_conjuncts_are_required():
    results = [line(0, "w", [parser_analysis("w")], [
        stored("human-made", opinion="noopinion", parser_evaluated=False, in_segment=False),
        stored("approved", opinion="approves", parser_evaluated=True, in_segment=False),
        stored("in-text", opinion="noopinion", parser_evaluated=True, in_segment=True),
        stored("candidate", opinion="noopinion", parser_evaluated=True, in_segment=False),
    ])]
    assert [c["analysis_guid"] for c in deletion_projection(results)["candidates"]] == ["candidate"]


def test_unknown_segment_use_is_never_counted_as_unreferenced():
    results = [line(0, "w", [parser_analysis("w")], [
        stored("unknown", opinion="noopinion", parser_evaluated=True, in_segment=None),
    ])]
    out = deletion_projection(results)
    assert out["count"] == 0
    assert out["segment_use_unknown"] == 1


# ---------------------------------------------------------------------------
# T087
# ---------------------------------------------------------------------------


def test_the_duplicate_projection_counts_filings_over_meaning_only_records():
    results = [
        line(0, "rumah", [parser_analysis("r", glosses=["house"])],
             [stored("m1", bundles=0, gloss="house")]),
        line(1, "makan", [parser_analysis("x"), parser_analysis("y")],
             [stored("m2", bundles=0, gloss="eat")]),  # no basis: no pairing
    ]
    out = duplicate_projection(results)
    assert out["count"] == 1
    assert out["would_duplicate"][0]["existing_meaning_only_record"] == "m1"


def test_both_projections_are_information_acted_on_by_nothing():
    for out in (deletion_projection(_sc015_fixture()), duplicate_projection(_sc015_fixture())):
        assert out["acted_on"] is False
        for key in ("confirm", "confirmation", "confirm_token", "apply", "file", "filing",
                    "write_enabled", "next_step"):
            assert key not in out


def test_no_part_of_the_write_ladder_ships():
    """The module defines no confirm/apply/file function and makes no write call."""
    tree = ast.parse(PROJECTIONS_SOURCE.read_text(encoding="utf-8"))
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for name in defined:
        assert not any(w in name.lower() for w in ("confirm", "apply", "file", "execute", "delete_")), name
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    for call in calls:
        assert not call.startswith(("Delete", "Create", "Set", "Add", "Remove", "ProcessParse")), call
