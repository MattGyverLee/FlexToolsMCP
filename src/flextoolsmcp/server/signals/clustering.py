#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clustering suspect words, and the capped drill-down (parser-check CP3, US5;
FR-047, FR-048, SC-016, D-5; data-model.md section 12).

FOUR HUNDRED SUSPECT WORDS ARE NOT FOUR HUNDRED TRACES. A loose rule
over-generates across every word it touches, so four hundred words that look
wrong are usually a handful of rules. The report groups them and recommends
one to three words per group to trace -- never the four hundred (FR-048).

THE KEY (D-5): a shared root entry first -- one loose rule attached to one
entry is the shape this is built to catch -- and the category pair where no
root entry is shared, which catches the rule that is not entry-specific.

THE REPRESENTATIVES (D-5): highest analysis count first, ties broken by the
word list's existing order, CAPPED AT THREE. The most over-generated word
exercises most of the suspect rule chain in one trace. It is a heuristic, and
the output says so: a representative that does not reproduce the problem
costs one wasted trace, which is why the cap is three rather than one.

NOTHING HERE TRACES ANYTHING. Clustering recommends; a trace is always a
separate call a person makes for one word. The session drill-down budget
(`DrillDownBudget`) is a user-chosen figure in 10-20 that bounds how many
words the session's reports recommend in total, and there is no bulk-trace
path to bound -- `auto_trace` is always False (FR-047, SC-016).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

__all__ = [
    "DRILL_DOWN_CAP_RANGE",
    "REPRESENTATIVE_CAP",
    "HEURISTIC_NOTE",
    "DrillDownBudget",
    "suspect_words",
    "cluster_words",
]

#: The user-chosen per-session cap must fall in this range (FR-047).
DRILL_DOWN_CAP_RANGE = (10, 20)

#: Representatives per cluster (D-5).
REPRESENTATIVE_CAP = 3

#: Members listed per cluster; a four-hundred-word cluster is summarised.
MEMBERS_SHOWN = 20

HEURISTIC_NOTE = (
    "Clusters are a heuristic: words are grouped by a shared root entry, or by "
    "category pair where no root entry is shared, on the guess that they share "
    "one loose rule. Representatives are the words with the most analyses "
    "(ties in word-list order), at most three per cluster; a representative "
    "that does not reproduce the problem costs one wasted trace. Nothing is "
    "traced automatically -- trace a representative with flextools_try_word."
)


class DrillDownBudget:
    """A session's drill-down cap: a user-chosen figure in 10-20 (FR-047).

    Counts distinct words recommended for tracing across the session. A word
    recommended twice counts once. Once spent, reports still cluster and
    summarise, and recommend nothing further.
    """

    def __init__(self, cap: int) -> None:
        low, high = DRILL_DOWN_CAP_RANGE
        if not isinstance(cap, int) or isinstance(cap, bool) or not low <= cap <= high:
            raise ValueError(f"drill-down cap must be an integer from {low} to {high}, got {cap!r}")
        self.cap = cap
        self._spent: List[str] = []

    @property
    def remaining(self) -> int:
        return self.cap - len(self._spent)

    @property
    def spent(self) -> List[str]:
        return list(self._spent)

    def take(self, wordform: str) -> bool:
        """Spend one unit on `wordform`; True if it is (now) within budget."""
        if wordform in self._spent:
            return True
        if self.remaining <= 0:
            return False
        self._spent.append(wordform)
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {"cap": self.cap, "used": len(self._spent), "remaining": self.remaining}


def _roots(analysis: Dict[str, Any]) -> List[str]:
    kinds = analysis.get("morph_kinds") or []
    entries = analysis.get("entry_guids") or []
    return [e for e, k in zip(entries, kinds) if k == "stem" and e]


def _categories(analysis: Dict[str, Any]) -> List[str]:
    kinds = analysis.get("morph_kinds") or []
    labels = analysis.get("category_labels") or []
    return [c for c, k in zip(labels, kinds) if k == "stem" and c]


def suspect_words(
    results: Iterable[Dict[str, Any]], signals: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Words that look over-generated: named by any per-word signal.

    Each suspect carries its run position, analysis count, root entries and
    stem categories -- everything clustering keys on.
    """
    named = set()
    for signal in signals:
        for observation in signal.get("observations") or []:
            if "wordform" in observation:
                named.add(observation["wordform"])
    suspects = []
    for order, line in enumerate(results):
        wordform = line.get("wordform")
        if wordform not in named:
            continue
        analyses = list((line.get("parse") or {}).get("analyses") or [])
        suspects.append(
            {
                "wordform": wordform,
                "order": line.get("index", order),
                "analysis_count": len(analyses),
                "roots": sorted({r for a in analyses for r in _roots(a)}),
                "categories": sorted({c for a in analyses for c in _categories(a)}),
            }
        )
    return suspects


def _representatives(members: List[Dict[str, Any]]) -> List[str]:
    ranked = sorted(members, key=lambda m: (-m["analysis_count"], m["order"]))
    return [m["wordform"] for m in ranked[:REPRESENTATIVE_CAP]]


def cluster_words(
    suspects: Sequence[Dict[str, Any]], budget: Optional[DrillDownBudget] = None
) -> Dict[str, Any]:
    """Group suspects (D-5) and recommend representatives within the budget."""
    ordered = sorted(suspects, key=lambda s: s["order"])

    # Root entry first: a root shared by at least two suspects forms a cluster.
    by_root: Dict[str, List[Dict[str, Any]]] = {}
    for suspect in ordered:
        for root in suspect["roots"]:
            by_root.setdefault(root, []).append(suspect)
    shared_roots = {r: m for r, m in by_root.items() if len(m) > 1}

    clusters: List[Dict[str, Any]] = []
    placed = set()
    # Biggest shared root first, so a word is placed with its largest group.
    for root, members in sorted(
        shared_roots.items(), key=lambda kv: (-len(kv[1]), kv[1][0]["order"])
    ):
        members = [m for m in members if m["wordform"] not in placed]
        if len(members) < 2:
            continue
        placed.update(m["wordform"] for m in members)
        clusters.append({"key_kind": "root_entry", "key": root, "members": members})

    # Category pair where no root entry is shared.
    by_pair: Dict[str, List[Dict[str, Any]]] = {}
    for suspect in ordered:
        if suspect["wordform"] in placed:
            continue
        key = "/".join(suspect["categories"]) if suspect["categories"] else ""
        by_pair.setdefault(key, []).append(suspect)
    for key, members in by_pair.items():
        clusters.append(
            {"key_kind": "category_pair" if key else "no_shared_key", "key": key or None,
             "members": members}
        )

    out_clusters = []
    for cluster in clusters:
        representatives = _representatives(cluster["members"])
        entry = {
            "key_kind": cluster["key_kind"],
            "key": cluster["key"],
            "size": len(cluster["members"]),
            # The first MEMBERS_SHOWN only; `size` is the whole cluster.
            "members": [m["wordform"] for m in cluster["members"][:MEMBERS_SHOWN]],
            # FR-048: one to three per cluster, always shown.
            "representatives": representatives,
        }
        if budget is not None:
            # The subset the session's cap still covers (FR-047).
            entry["within_drill_down_budget"] = [w for w in representatives if budget.take(w)]
        out_clusters.append(entry)

    result: Dict[str, Any] = {
        "suspect_words": len(ordered),
        "clusters": out_clusters,
        "representatives_total": sum(len(c["representatives"]) for c in out_clusters),
        "auto_trace": False,
        "heuristic_note": HEURISTIC_NOTE,
    }
    if budget is not None:
        result["drill_down_budget"] = budget.to_dict()
    else:
        low, high = DRILL_DOWN_CAP_RANGE
        result["drill_down_budget"] = None
        result["drill_down_note"] = (
            f"No drill-down cap has been chosen for this session. Choose one from "
            f"{low} to {high} (drill_down_cap) and the report marks which "
            f"representatives the session's cap still covers. At most {high} "
            f"words are traced in a session either way, one call per word."
        )
    return result
