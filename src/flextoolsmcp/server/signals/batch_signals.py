#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The five batch signals (parser-check CP3, US5; FR-035..FR-037; SPEC 9.1;
data-model.md section 10).

EVERY SIGNAL CARRIES ITS FALSE ALARM, IN THE OUTPUT (FR-036). Ambiguity is
normal in many languages; a high count, two root entries, or two categories
for one surface form is each sometimes exactly right. So the legitimate
reason a signal may be a false alarm is a field of the signal itself
(`false_positive_note`), not a paragraph in documentation the reader of a
report never sees. A signal cannot be emitted without it.

THE DISTRIBUTION IS AN INSTRUMENT, NOT A JUDGEMENT (FR-037). It is a
histogram, optionally beside a baseline run's histogram. It carries no
severity, no scalar score and no wording that grades the grammar: its only
use is comparison, where a rightward shift after an edit is evidence that
something got looser.

COMPUTED FROM THE TYPED STRUCTURED RESULT (FR-035, R-11). Every input is a
field the worker read off the parser's `ParseAnalysis` objects -- the
signature, `entry_guids`, `morph_kinds`, `category_labels` -- never from the
parser's XML document form, which is a rendering. A run recorded before the
worker read a field reports the signal as not computable, saying which field
is missing, rather than computing it from something weaker.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

__all__ = ["SIGNAL_IDS", "FALSE_POSITIVE_NOTES", "batch_signals", "count_distribution"]

#: The five, in the order SPEC 9.1 lists them.
SIGNAL_IDS = (
    "analyses_per_word",
    "root_entry_disagreement",
    "root_as_affix_stack",
    "incompatible_categories",
    "analysis_count_distribution",
)

FALSE_POSITIVE_NOTES: Dict[str, str] = {
    "analyses_per_word": (
        "A word with many analyses may be genuinely ambiguous: productive "
        "ambiguity is normal in many languages, so a high count is not by "
        "itself a sign the grammar is wrong. Use this list to decide what to "
        "look at first."
    ),
    "root_entry_disagreement": (
        "Two analyses rooted in different entries may be real root homographs "
        "-- two unrelated words that happen to share a surface form -- rather "
        "than a loose affix rule exposing a spurious root."
    ),
    "root_as_affix_stack": (
        "An analysis built from affixes alone may be a real zero-derivation "
        "or a cliticization the grammar models that way, rather than a rule "
        "loose enough to synthesize a word with no root."
    ),
    "incompatible_categories": (
        "One surface form in two categories may be a genuine cross-category "
        "homograph. The grammar is not necessarily missing a derivation to "
        "license the difference."
    ),
    "analysis_count_distribution": (
        "This distribution does not say whether any count is right. It is for "
        "comparison: re-run after a grammar edit and compare the two. A "
        "rightward shift is evidence something got looser -- though a changed "
        "word list shifts it too, so compare runs over the same scope."
    ),
}


def _analyses(line: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list((line.get("parse") or {}).get("analyses") or [])


def _has(analyses: Iterable[Dict[str, Any]], key: str) -> bool:
    return all(key in a for a in analyses)


def _roots(analysis: Dict[str, Any]) -> List[Optional[str]]:
    """The entry GUIDs of the analysis's stem morphs."""
    kinds = analysis.get("morph_kinds") or []
    entries = analysis.get("entry_guids") or []
    return [e for e, k in zip(entries, kinds, strict=False) if k == "stem"]


def _stem_categories(analysis: Dict[str, Any]) -> tuple:
    kinds = analysis.get("morph_kinds") or []
    labels = analysis.get("category_labels") or []
    return tuple(
        label for label, k in zip(labels, kinds, strict=False) if k == "stem" and label
    )


def _signal(signal_id: str, observations: List[Dict[str, Any]], **extra: Any) -> Dict[str, Any]:
    out = {
        "signal_id": signal_id,
        "observations": observations,
        "false_positive_note": FALSE_POSITIVE_NOTES[signal_id],
    }
    out.update(extra)
    return out


def _not_computable(signal_id: str, missing: str) -> Dict[str, Any]:
    return _signal(
        signal_id,
        [],
        computable=False,
        note=(
            f"Not computable for this run: its results do not record "
            f"'{missing}', which this signal is computed from. Re-run the batch "
            f"to record it."
        ),
    )


def count_distribution(lines: Iterable[Dict[str, Any]]) -> Dict[int, int]:
    """Analysis count -> how many words had that many. Parsed lines only."""
    histogram: Counter = Counter()
    for line in lines:
        parse = line.get("parse")
        if not parse or "analyses" not in parse:
            continue
        histogram[len(parse.get("analyses") or [])] += 1
    return dict(sorted(histogram.items()))


def batch_signals(
    results: Iterable[Dict[str, Any]],
    baseline_results: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """All five signals over one batch's `results.jsonl` lines."""
    lines = [
        line
        for line in results
        if (line.get("parse") or {}).get("analyses") is not None
    ]
    all_analyses = [a for line in lines for a in _analyses(line)]
    signals: List[Dict[str, Any]] = []

    # 1. Analyses per word -- a worklist, most analyses first, ties in run order.
    per_word = [
        {
            "wordform": line.get("wordform"),
            "index": line.get("index"),
            "analysis_count": len(_analyses(line)),
        }
        for line in lines
        if len(_analyses(line)) > 1
    ]
    per_word.sort(key=lambda o: (-o["analysis_count"], o["index"] if o["index"] is not None else 0))
    signals.append(_signal("analyses_per_word", per_word))

    # 2. Root-entry disagreement.
    if not (_has(all_analyses, "entry_guids") and _has(all_analyses, "morph_kinds")):
        signals.append(_not_computable("root_entry_disagreement", "entry_guids"))
    else:
        observations = []
        for line in lines:
            roots = sorted({r for a in _analyses(line) for r in _roots(a) if r})
            if len(roots) > 1:
                observations.append(
                    {"wordform": line.get("wordform"), "root_entry_guids": roots}
                )
        signals.append(_signal("root_entry_disagreement", observations))

    # 3. A root analysed as a stack of affixes.
    if not _has(all_analyses, "morph_kinds"):
        signals.append(_not_computable("root_as_affix_stack", "morph_kinds"))
    else:
        observations = []
        for line in lines:
            for position, a in enumerate(_analyses(line)):
                kinds = a.get("morph_kinds") or []
                if kinds and all(k == "affix" for k in kinds):
                    observations.append(
                        {
                            "wordform": line.get("wordform"),
                            "analysis_position": position,
                            "rendered_morphs": list(a.get("rendered_morphs") or []),
                        }
                    )
        signals.append(_signal("root_as_affix_stack", observations))

    # 4. The same surface form in incompatible categories.
    if not _has(all_analyses, "morph_kinds"):
        signals.append(_not_computable("incompatible_categories", "morph_kinds"))
    else:
        observations = []
        for line in lines:
            categories = sorted(
                {c for a in _analyses(line) for c in _stem_categories(a)}
            )
            if len(categories) > 1:
                observations.append(
                    {"wordform": line.get("wordform"), "categories": categories}
                )
        signals.append(_signal("incompatible_categories", observations))

    # 5. The distribution -- beside the baseline's when one is given.
    # One row per analysis count; the baseline's column only when given.
    current = count_distribution(lines)
    baseline = count_distribution(baseline_results) if baseline_results is not None else None
    counts = sorted(set(current) | set(baseline or {}))
    rows = []
    for count in counts:
        row = {"analysis_count": count, "words": current.get(count, 0)}
        if baseline is not None:
            row["baseline_words"] = baseline.get(count, 0)
        rows.append(row)
    signals.append(
        _signal("analysis_count_distribution", rows, has_baseline=baseline is not None)
    )
    return signals
