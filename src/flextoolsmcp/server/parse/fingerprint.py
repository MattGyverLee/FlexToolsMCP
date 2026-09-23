#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The scope fingerprint: may these two runs be compared?
(parser-check CP3, US1; FR-010, FR-011, FR-012, D-3.)

EXACTLY EIGHT FIELDS, transcribed from data-model.md section 3 in its order:
scope_kind, scope_value, text_ids, word_count, limit, truncated, engine,
vernacular_ws. Each one is in because a difference in it makes two runs
describe different things: a text added to a genre, a truncated run against a
full one, two engines, two writing systems.

NOTHING DESCRIBING THE GRAMMAR IS IN IT, and that is the most important line
in this module (FR-011, D-3). The edit-then-compare loop exists to measure a
grammar change; a fingerprint that folded in grammar state would refuse every
comparison the user actually wants. The grammar load-error baseline (FR-023)
is stored BESIDE the fingerprint in the run record, keyed to it, never inside
it. `build_fingerprint` takes a resolved scope and an engine name and nothing
else, so there is no parameter through which grammar state could arrive.

`word_count` is the de-duplicated count BEFORE any limit, so a truncated run
over a corpus is recognisably that corpus -- the `limit` and `truncated`
fields then say why the two are still not comparable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, List, Optional, Tuple

from ..response_models import ParseScopeMismatchDetail


#: Stated in the output of a forced comparison (FR-012).
FORCED_INTERSECTION_NOTE = (
    "These runs do not describe the same scope. The comparison was forced, "
    "so it covers only the intersection -- words present in both runs. Words "
    "in only one run are not reported as fixed or broken."
)


@dataclass(frozen=True)
class ScopeFingerprint:
    """The durable description of a resolved scope (data-model.md s.3)."""

    scope_kind: str
    scope_value: Any
    text_ids: Tuple[int, ...]
    word_count: int
    limit: Optional[int]
    truncated: bool
    engine: str
    vernacular_ws: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["text_ids"] = list(self.text_ids)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScopeFingerprint":
        """Read a fingerprint back from `meta.json`. Extra keys are refused:
        a fingerprint carrying a field this code does not know was written by
        something that disagrees with it about comparability."""
        extra = set(data) - set(FINGERPRINT_FIELDS)
        if extra:
            raise ValueError(f"Unknown fingerprint field(s): {sorted(extra)}")
        return cls(
            scope_kind=data["scope_kind"],
            scope_value=_freeze(data.get("scope_value")),
            text_ids=tuple(sorted(int(t) for t in data.get("text_ids") or ())),
            word_count=int(data["word_count"]),
            limit=data.get("limit"),
            truncated=bool(data["truncated"]),
            engine=data["engine"],
            vernacular_ws=data["vernacular_ws"],
        )


FINGERPRINT_FIELDS: Tuple[str, ...] = tuple(f.name for f in fields(ScopeFingerprint))


def _freeze(value: Any) -> Any:
    """Lists become tuples so the frozen dataclass stays hashable/comparable."""
    return tuple(value) if isinstance(value, list) else value


def build_fingerprint(resolved: Any, engine: str) -> ScopeFingerprint:
    """The fingerprint of a `ResolvedScope`, recorded with the engine at
    submission. Takes nothing that describes the grammar (FR-011)."""
    return ScopeFingerprint(
        scope_kind=resolved.scope_kind,
        scope_value=_freeze(resolved.scope_value),
        text_ids=tuple(sorted(int(t) for t in resolved.text_ids)),
        word_count=int(resolved.count_before_limit),
        limit=resolved.limit,
        truncated=bool(resolved.truncated),
        engine=str(engine),
        vernacular_ws=str(resolved.vernacular_ws),
    )


def differing_fields(baseline: ScopeFingerprint, current: ScopeFingerprint) -> List[str]:
    """Names of the fields that differ, in fingerprint order."""
    return [
        name for name in FINGERPRINT_FIELDS
        if getattr(baseline, name) != getattr(current, name)
    ]


class ScopeMismatch(Exception):
    """Two runs that do not describe the same scope (``parse_scope_mismatch``).

    ``detail`` is validated and in contract field order, ``error_code`` first.
    """

    def __init__(self, detail: Dict[str, Any]):
        super().__init__(detail.get("hint"))
        self.detail = detail


@dataclass(frozen=True)
class Comparability:
    """The outcome of `check_comparable` when it does not refuse."""

    comparable: bool
    forced: bool
    differing_fields: List[str]
    note: Optional[str]


def check_comparable(
    baseline: ScopeFingerprint,
    current: ScopeFingerprint,
    *,
    force: bool = False,
) -> Comparability:
    """May ``current`` be compared against ``baseline``? (FR-012)

    Identical fingerprints: yes. Differing ones: refuse with
    `parse_scope_mismatch` naming the differing fields -- unless ``force``,
    in which case the comparison proceeds on the intersection only and the
    returned note says so. The caller restricts the word sets with
    `restrict_to_intersection`; this function only decides.
    """
    differing = differing_fields(baseline, current)
    if not differing:
        return Comparability(True, False, [], None)
    if force:
        return Comparability(True, True, differing, FORCED_INTERSECTION_NOTE)

    detail = ParseScopeMismatchDetail(
        baseline_fingerprint=baseline.to_dict(),
        current_fingerprint=current.to_dict(),
        differing_fields=differing,
        hint=(
            f"These runs do not describe the same scope ({', '.join(differing)} "
            f"differ), so a difference between them could be a corpus change "
            f"rather than a grammar change. Re-run with the baseline's scope, "
            f"or force the comparison to compare only the words both runs share."
        ),
    )
    raise ScopeMismatch(detail.model_dump())


def restrict_to_intersection(baseline_words: List[str], current_words: List[str]) -> List[str]:
    """Words present in both runs, in the baseline's order."""
    current = set(current_words)
    return [word for word in baseline_words if word in current]
