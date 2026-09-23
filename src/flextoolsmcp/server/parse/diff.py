#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparing two runs: did my grammar edit help? (parser-check CP3, US4;
FR-012, FR-030..FR-034; data-model.md section 7.)

BUCKETS ARE EXACTLY `fixed | broken | changed | unchanged` (FR-030), and
every word is classified on its SIGNATURE SET (`signature.compare_word`),
never on its analysis count. A word identity change (FR-032) is reported
beside the buckets, in `identity_changes`, because it is neither a change in
how the word parses nor "unchanged".

COMPARABILITY FIRST (FR-012). Two runs whose fingerprints differ refuse with
`parse_scope_mismatch` naming the differing fields, unless forced; a forced
comparison covers the INTERSECTION of the two word lists only and says so.
The fingerprint says nothing about the grammar (D-3), so a grammar edit
between the runs -- the thing being measured -- never causes a refusal.

SHARED MODE (FR-034). If FieldWorks has the project open, an edit the user
just made may not be on disk yet, and the second run may have parsed the
grammar as it was before the edit. The comparison cannot tell. So when
`project_access.probe_project_access` reports `open_shared` or
`open_exclusive`, the result carries `staleness: "shared_mode_unverifiable"`,
the save-or-close note, and a `no_change` verdict is downgraded to
`no_change_unverifiable`. NO SAFE READ-BACK INTERVAL IS PROMISED: FieldWorks
writes on its own schedule and there is no interval after which the file is
known to be current.

READ-ONLY, AND IT NEVER TOUCHES THE ENGINE (FR-024). Everything here reads
two run directories. The access probe reads a lock file's metadata; it opens
no project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .fingerprint import (
    ScopeFingerprint,
    check_comparable,
    restrict_to_intersection,
)
from .record import RunRecord
from .signature import (
    FALLBACK_AMBIGUITY_NOTE,
    IDENTITY_CHANGE_NOTE,
    PROVISIONAL_NOTE,
    SignatureMode,
    compare_word,
    signature_mode,
    signatures_of,
)

__all__ = [
    "BUCKETS",
    "SHARED_MODE_STALENESS",
    "SHARED_MODE_NOTE",
    "RunNotComparable",
    "RunComparison",
    "compare_runs",
    "shared_mode_active",
]

#: Verbatim from contracts/tools.md section 1.
BUCKETS = ("fixed", "broken", "changed", "unchanged")

#: Verbatim from contracts/tools.md section 1 (FR-034).
SHARED_MODE_STALENESS = "shared_mode_unverifiable"
NO_CHANGE = "no_change"
NO_CHANGE_UNVERIFIABLE = "no_change_unverifiable"

#: The access verdicts that mean FieldWorks may hold unsaved edits.
_SHARED_VERDICTS = ("open_shared", "open_exclusive")

#: The save-or-close note (FR-034). Deliberately promises no interval.
SHARED_MODE_NOTE = (
    "FieldWorks has this project open, so a grammar edit you just made may not "
    "have been written to disk yet, and the later run may have parsed the "
    "grammar as it was before the edit. This comparison cannot tell the "
    "difference. Save your work in FieldWorks, or close the project there, and "
    "then parse again to get a comparison that reflects the edit."
)


class RunNotComparable(Exception):
    """A run cannot be compared at all (not a batch, or no fingerprint)."""


@dataclass
class RunComparison:
    """The comparison, ready to render (data-model.md section 7)."""

    baseline_run_id: str
    current_run_id: str
    mode: str
    buckets: Dict[str, List[Dict[str, Any]]]
    identity_changes: List[Dict[str, Any]]
    not_compared: List[Dict[str, Any]]
    verdict: str
    notes: List[str] = field(default_factory=list)
    forced: bool = False
    differing_fields: List[str] = field(default_factory=list)
    staleness: Optional[str] = None
    provisional_words: int = 0

    def to_dict(self) -> Dict[str, Any]:
        counts = {name: len(self.buckets[name]) for name in BUCKETS}
        data: Dict[str, Any] = {
            "baseline_run_id": self.baseline_run_id,
            "current_run_id": self.current_run_id,
            "verdict": self.verdict,
            "comparison_mode": self.mode,
            "counts": counts,
            "buckets": {name: self.buckets[name] for name in BUCKETS},
            "identity_changes": self.identity_changes,
            "identity_change_count": len(self.identity_changes),
            "not_compared": self.not_compared,
            "provisional_words": self.provisional_words,
            "notes": self.notes,
        }
        if self.forced:
            data["forced"] = True
            data["differing_fields"] = self.differing_fields
        if self.staleness is not None:
            data["staleness"] = self.staleness
        return data


def shared_mode_active(access: Any) -> bool:
    """True when the access probe says FieldWorks has the project open."""
    return getattr(access, "verdict", None) in _SHARED_VERDICTS


def _fingerprint(record: RunRecord) -> ScopeFingerprint:
    meta = record.read_meta()
    if meta is None or not meta.scope_fingerprint:
        raise RunNotComparable(
            f"Run {record.run_id} has no scope fingerprint -- it is not a batch "
            f"run, so there is no scope to compare it on. Compare two runs made "
            f"with flextools_parse_text."
        )
    return ScopeFingerprint.from_dict(meta.scope_fingerprint)


def _lines_by_word(record: RunRecord) -> Dict[str, Dict[str, Any]]:
    """Result lines keyed by wordform. A word seen twice keeps its last line."""
    lines: Dict[str, Dict[str, Any]] = {}
    for line in record.iter_results():
        word = line.get("wordform")
        if isinstance(word, str):
            lines[word] = line
    return lines


def _word_order(record: RunRecord, lines: Dict[str, Dict[str, Any]]) -> List[str]:
    words = record.read_words()
    return words if words is not None else list(lines)


def compare_runs(
    baseline: RunRecord,
    current: RunRecord,
    *,
    force: bool = False,
    access: Any = None,
    mode: Optional[str] = None,
) -> RunComparison:
    """Compare `current` against `baseline`. Read-only; touches no engine.

    Raises:
        fingerprint.ScopeMismatch: the fingerprints differ and `force` is
            False (`parse_scope_mismatch`, FR-012).
        RunNotComparable: either run is not a batch run.
    """
    mode = mode or signature_mode()
    comparability = check_comparable(_fingerprint(baseline), _fingerprint(current), force=force)

    before_lines = _lines_by_word(baseline)
    after_lines = _lines_by_word(current)
    before_words = _word_order(baseline, before_lines)
    after_words = _word_order(current, after_lines)

    notes: List[str] = []
    if comparability.forced:
        words = restrict_to_intersection(before_words, after_words)
        notes.append(comparability.note)
    else:
        words = list(before_words)
        for word in after_words:
            if word not in before_lines and word not in words:
                words.append(word)

    buckets: Dict[str, List[Dict[str, Any]]] = {name: [] for name in BUCKETS}
    identity_changes: List[Dict[str, Any]] = []
    not_compared: List[Dict[str, Any]] = []
    provisional = 0

    for word in words:
        before = signatures_of(before_lines.get(word))
        after = signatures_of(after_lines.get(word))
        if before is None or after is None:
            # A word one run never completed (killed, errored) is not a
            # regression and not a fix: nothing is known about it on that
            # side. Reported, never bucketed.
            missing = [
                name for name, sigs in (("baseline", before), ("current", after))
                if sigs is None
            ]
            not_compared.append({
                "wordform": word,
                "reason": f"no completed result in the {' and '.join(missing)} run",
            })
            continue
        outcome = compare_word(word, before, after, mode)
        if outcome.provisional:
            provisional += 1
        if outcome.identity_change:
            entry = outcome.to_dict()
            entry["note"] = IDENTITY_CHANGE_NOTE
            identity_changes.append(entry)
        else:
            buckets[outcome.bucket].append(outcome.to_dict())

    moved = any(buckets[name] for name in ("fixed", "broken", "changed")) or identity_changes
    verdict = "changes_found" if moved else NO_CHANGE

    staleness = None
    if shared_mode_active(access):
        staleness = SHARED_MODE_STALENESS
        notes.append(SHARED_MODE_NOTE)
        if verdict == NO_CHANGE:
            verdict = NO_CHANGE_UNVERIFIABLE

    if mode == SignatureMode.RENDERED_FALLBACK:
        notes.append(FALLBACK_AMBIGUITY_NOTE)
    if provisional:
        notes.append(PROVISIONAL_NOTE)

    return RunComparison(
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        mode=mode,
        buckets=buckets,
        identity_changes=identity_changes,
        not_compared=not_compared,
        verdict=verdict,
        notes=notes,
        forced=comparability.forced,
        differing_fields=list(comparability.differing_fields),
        staleness=staleness,
        provisional_words=provisional,
    )
