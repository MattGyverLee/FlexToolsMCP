#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Completeness tiers (parser-check CP3, US5; FR-038, FR-039).

  * All four tiers: none, meaning_only, sketched, fully_linked.
  * Derived from the public per-bundle completeness flag (as the recorded
    `complete_bundle_count`) plus the bundle count -- and from nothing else.
  * The host's internal fully-formed predicate is NOT reimplemented: the
    tier module reads no morph, MSA or sense of any bundle, and a record
    carrying only the two counts is enough to tier it.

Run with:
    python -m pytest tests/test_signals_tiers.py -q
"""

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.signals.tiers import TIERS, tier_of, unlinked_count, word_tier  # noqa: E402

TIERS_SOURCE = REPO_ROOT / "src" / "flextoolsmcp" / "server" / "signals" / "tiers.py"


def _record(bundles, complete):
    return {"bundle_count": bundles, "complete_bundle_count": complete}


def test_the_four_tiers_verbatim_in_order():
    assert TIERS == ("none", "meaning_only", "sketched", "fully_linked")


@pytest.mark.parametrize(
    "bundles, complete, tier",
    [
        (0, 0, "meaning_only"),
        (3, 1, "sketched"),
        (3, 0, "sketched"),
        (3, 3, "fully_linked"),
        (1, 1, "fully_linked"),
    ],
)
def test_tier_from_bundle_count_and_the_public_flag(bundles, complete, tier):
    assert tier_of(_record(bundles, complete)) == tier


def test_no_human_analysis_is_tier_none():
    assert word_tier([]) == "none"


def test_a_word_reaches_the_furthest_tier_of_its_analyses():
    assert word_tier([_record(0, 0), _record(2, 1)]) == "sketched"
    assert word_tier([_record(2, 1), _record(2, 2), _record(0, 0)]) == "fully_linked"


def test_the_sketched_count_is_the_bundles_whose_flag_is_false():
    assert unlinked_count(_record(5, 2)) == 3
    assert unlinked_count(_record(2, 2)) == 0


def test_the_two_counts_are_all_the_tier_needs():
    """Bundle internals present or not, the tier is the same."""
    bare = _record(2, 1)
    rich = dict(bare, signature=[["f", None, None], ["f2", "m2", None]],
                rendered_morphs=["a", "b"])
    assert tier_of(bare) == tier_of(rich) == "sketched"


def test_the_host_predicate_is_not_reimplemented():
    """tiers.py reads only the two recorded counts -- no bundle internals."""
    tree = ast.parse(TIERS_SOURCE.read_text(encoding="utf-8"))
    keys = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert keys == {"bundle_count", "complete_bundle_count"}
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for member in ("MorphRA", "MsaRA", "SenseRA", "IsFullyFormed", "MorphBundlesOS"):
        assert member not in names
