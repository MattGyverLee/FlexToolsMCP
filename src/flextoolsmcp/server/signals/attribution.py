#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rule attribution by side-by-side comparison of competing rule chains
(parser-check CP3, US5; FR-049; SPEC 9.2).

THE METHOD. One word, N accepted analyses. Each accepted analysis has a rule
chain -- `root -> rule1 -> rule2 -> ... -> surface` -- recoverable from the
word's trace. Lay the chains side by side; a rule that appears in every chain
that should not have parsed, and in none that should, is the overgeneration
candidate. This comparison does not exist in the engine; it is net-new, and
it is what this module is.

WHERE THE CHAINS COME FROM. The trace (`FwXmlTraceManager.cs`) nests each
synthesis step inside the one before: a `WordSynthesisTrace` names the root
allomorph, each applied rule is a `MorphologicalRuleSynthesisTrace` whose
`MorphologicalRule` child carries the rule name, and a successful path ends
in `ParseCompleteTrace success="true"` whose `Result` is the surface. A
chain is therefore the rule elements on the path from a successful
`ParseCompleteTrace` up to its `WordSynthesisTrace`. Nothing else is read,
and a trace that cannot be read yields no chains -- never guessed ones.

WHAT THE PRE-PARSE MORPH FILTER IS NOT. The engine's selected-morphs trace
(`selectTraceMorphs`, `HCParser.cs:186-200`) restricts the search BEFORE
parsing. It does not attribute an already-produced analysis to a rule, and
nothing here treats it as if it did. Its one legitimate use is by
SUBTRACTION: re-run a suspect analysis with its own morphs selected, and the
chain that survives is that analysis's derivation in isolation.
`narrow_by_subtraction` takes such a chain and removes from the candidate set
every rule the isolated derivation does not use. That narrows; it still does
not name the rule -- only the side-by-side comparison does.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Sequence

__all__ = [
    "METHOD",
    "MORPH_FILTER_NOTE",
    "rule_chains",
    "compare_chains",
    "narrow_by_subtraction",
]

METHOD = "side_by_side_rule_chains"

MORPH_FILTER_NOTE = (
    "The selected-morphs trace is a pre-parse filter: it narrows the search "
    "before parsing and does not attribute an analysis to a rule. It is used "
    "here only to narrow the candidate rules by subtraction."
)


def rule_chains(trace_xml: str) -> Optional[List[Dict[str, Any]]]:
    """The rule chain of every successful path in a trace, or None if unreadable."""
    try:
        root = ET.fromstring(trace_xml)
    except ET.ParseError:
        return None
    parent = {child: node for node in root.iter() for child in node}
    chains: List[Dict[str, Any]] = []
    for complete in root.iter("ParseCompleteTrace"):
        if (complete.get("success") or "").lower() != "true":
            continue
        surface = (complete.findtext("Result") or "").strip()
        rules: List[str] = []
        root_form: Optional[str] = None
        node = parent.get(complete)
        while node is not None:
            if node.tag == "MorphologicalRuleSynthesisTrace":
                rule = node.find("MorphologicalRule")
                if rule is not None and (rule.text or "").strip():
                    rules.append(rule.text.strip())
            elif node.tag == "WordSynthesisTrace":
                allomorph = node.find("Allomorph")
                if allomorph is not None:
                    root_form = (allomorph.findtext("Form") or "").strip() or None
                break
            node = parent.get(node)
        rules.reverse()  # walked leaf-to-root; the chain reads root-to-surface
        chains.append({"root": root_form, "rules": rules, "surface": surface})
    return chains


def compare_chains(
    chains: Sequence[Dict[str, Any]], suspect: Optional[Iterable[int]] = None
) -> Dict[str, Any]:
    """Lay one word's chains side by side (FR-049).

    `suspect` is the positions of the chains a person judged should not have
    parsed. With it, the candidates are the rules in EVERY suspect chain and
    in NO other. Without it the comparison still reports what every chain
    shares and what each chain alone uses -- the facts a person needs to
    make that judgement -- and names no candidate, because naming one would
    require the judgement it has not been given.
    """
    rule_sets = [set(c.get("rules") or []) for c in chains]
    shared = set.intersection(*rule_sets) if rule_sets else set()
    side_by_side = []
    for position, chain in enumerate(chains):
        others = set().union(*(s for i, s in enumerate(rule_sets) if i != position))
        side_by_side.append(
            {
                "position": position,
                "root": chain.get("root"),
                "rules": list(chain.get("rules") or []),
                "surface": chain.get("surface"),
                "rules_only_in_this_chain": sorted(rule_sets[position] - others),
            }
        )
    out: Dict[str, Any] = {
        "method": METHOD,
        "chains": side_by_side,
        "rules_in_every_chain": sorted(shared),
        "morph_filter_used_for_attribution": False,
        "morph_filter_note": MORPH_FILTER_NOTE,
    }
    if suspect is None:
        out["candidate_rules"] = None
        out["note"] = (
            "Say which of these analyses should not have parsed, and the "
            "comparison names the rules found in all of those chains and in "
            "none of the others."
        )
        return out
    bad = sorted(set(suspect))
    good = [i for i in range(len(chains)) if i not in bad]
    if not bad:
        out["candidate_rules"] = []
        return out
    in_all_bad = set.intersection(*(rule_sets[i] for i in bad))
    in_any_good = set().union(*(rule_sets[i] for i in good)) if good else set()
    out["suspect_positions"] = bad
    out["candidate_rules"] = sorted(in_all_bad - in_any_good)
    return out


def narrow_by_subtraction(
    candidate_rules: Iterable[str], isolated_chain: Dict[str, Any]
) -> Dict[str, Any]:
    """Remove candidates the suspect's isolated derivation does not use.

    `isolated_chain` is the chain that survived a selected-morphs re-run of
    the suspect analysis. A rule absent from it cannot be what licensed that
    analysis, so it leaves the candidate set. This narrows by subtraction
    and names nothing (SPEC 9.2).
    """
    used = set(isolated_chain.get("rules") or [])
    before = list(candidate_rules)
    kept = [r for r in before if r in used]
    return {
        "method": "subtraction",
        "candidates_before": before,
        "candidates_after": kept,
        "removed": [r for r in before if r not in used],
        "names_the_rule": False,
        "morph_filter_note": MORPH_FILTER_NOTE,
    }
