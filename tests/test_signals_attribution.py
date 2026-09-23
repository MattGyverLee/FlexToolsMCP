#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rule attribution (parser-check CP3, US5; FR-049; SPEC 9.2).

  * Attribution is a side-by-side comparison of one word's competing rule
    chains, recovered from the trace's successful paths.
  * The candidate is the rule in every should-not-have-parsed chain and in
    none of the others -- and without that judgement no candidate is named.
  * The engine's pre-parse morph filter is NOT an attribution mechanism:
    its only use is narrowing a candidate set by subtraction, which names
    nothing.

Run with:
    python -m pytest tests/test_signals_attribution.py -q
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.signals import attribution  # noqa: E402
from flextoolsmcp.server.signals.attribution import (  # noqa: E402
    METHOD,
    compare_chains,
    narrow_by_subtraction,
    rule_chains,
)


def _path(root, rules, surface):
    """One synthesis path, nested as FwXmlTraceManager nests it."""
    inner = f'<ParseCompleteTrace success="true"><Result>{surface}</Result></ParseCompleteTrace>'
    for rule in reversed(rules):
        inner = (f'<MorphologicalRuleSynthesisTrace><MorphologicalRule id="1" type="affix">'
                 f'{rule}</MorphologicalRule>{inner}</MorphologicalRuleSynthesisTrace>')
    return (f"<LexLookupTrace><Stratum>s</Stratum><WordSynthesisTrace>"
            f"<Allomorph id='1'><Form>{root}</Form></Allomorph>{inner}"
            f"</WordSynthesisTrace></LexLookupTrace>")


TRACE = (
    "<Wordform form='membeli'><WordAnalysisTrace><InputWord>membeli</InputWord>"
    + _path("beli", ["meN-"], "membeli")
    + _path("bel", ["meN-", "-i loose"], "membeli")
    + _path("be", ["meN-", "-li loose", "-i loose"], "membeli")
    # A failed path contributes no chain.
    + "<LexLookupTrace><WordSynthesisTrace><Allomorph id='1'><Form>x</Form></Allomorph>"
      "<ParseCompleteTrace success='false'><Result>x</Result></ParseCompleteTrace>"
      "</WordSynthesisTrace></LexLookupTrace>"
    + "</WordAnalysisTrace></Wordform>"
)


def test_chains_are_read_root_to_surface_from_successful_paths_only():
    chains = rule_chains(TRACE)
    assert chains == [
        {"root": "beli", "rules": ["meN-"], "surface": "membeli"},
        {"root": "bel", "rules": ["meN-", "-i loose"], "surface": "membeli"},
        {"root": "be", "rules": ["meN-", "-li loose", "-i loose"], "surface": "membeli"},
    ]


def test_an_unreadable_trace_yields_no_chains_not_guessed_ones():
    assert rule_chains("<not a trace") is None


def test_the_comparison_is_side_by_side():
    out = compare_chains(rule_chains(TRACE))
    assert out["method"] == METHOD == "side_by_side_rule_chains"
    assert [c["position"] for c in out["chains"]] == [0, 1, 2]
    assert out["rules_in_every_chain"] == ["meN-"]
    assert out["chains"][2]["rules_only_in_this_chain"] == ["-li loose"]


def test_the_candidate_is_in_every_suspect_chain_and_no_other():
    out = compare_chains(rule_chains(TRACE), suspect=[1, 2])
    assert out["candidate_rules"] == ["-i loose"]


def test_without_a_judgement_no_candidate_is_named():
    out = compare_chains(rule_chains(TRACE))
    assert out["candidate_rules"] is None


def test_the_morph_filter_is_not_an_attribution_mechanism():
    out = compare_chains(rule_chains(TRACE), suspect=[2])
    assert out["morph_filter_used_for_attribution"] is False
    assert "pre-parse filter" in out["morph_filter_note"]


def test_subtraction_narrows_and_names_nothing():
    isolated = {"root": "be", "rules": ["meN-", "-i loose"], "surface": "membeli"}
    out = narrow_by_subtraction(["-li loose", "-i loose", "meN-"], isolated)
    assert out["method"] == "subtraction"
    assert out["candidates_after"] == ["-i loose", "meN-"]
    assert out["removed"] == ["-li loose"]
    assert out["names_the_rule"] is False


def test_attribution_never_calls_the_selected_morphs_trace():
    """No engine call at all: the module only reads trace XML it is given."""
    tree = ast.parse(Path(attribution.__file__).read_text(encoding="utf-8"))
    calls = {n.func.attr for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {"TraceWordXml", "ParseWord", "ParseWordXml", "selectTraceMorphs"}
