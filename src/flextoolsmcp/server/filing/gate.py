#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The refuse-to-file gate (parser-check CP4, FR-020..FR-024, FR-039; R-05, R-12;
data-model section 4).

FLEx's grammar loader says nothing to its caller when an edit breaks a lexical
entry: the entry simply stops reaching the parser. Filing then deletes every
analysis that entry used to license, with no error anywhere in the chain. So
filing refuses -- `grammar_load_unclean` -- when:

  * `morpher_null`: the parser could not be built at all (FR-020). No
    baseline can make that acceptable;
  * `new_load_errors`: this load logged errors the baseline did not (FR-021);
  * `eligible_forms_dropped`: fewer entries' forms can reach the grammar than
    in the baseline (FR-039) -- the loader drops them WITHOUT logging, which
    is the case a load-error diff alone would pass (D-1).

THE BASELINE IS THE MCP'S OWN (FR-023). It is the load-error set -- and, from
CP4, the eligible-entry set -- recorded by the newest READ-ONLY batch run of
the same project and scope, found by `created_at` (not by directory name or
mtime: CP3's R-03 class). FLEx's own `HCLoadErrors.xml` is never a prior
state; the worker reads that file only right after its OWN load, and only if
its mtime says that load wrote it.

ONLY A READ-ONLY RUN RE-BASELINES. That is the documented and only way past a
`new_load_errors` or `eligible_forms_dropped` refusal: run a read-only
`flextools_parse_text` of the same scope, and its errors become pre-existing
(FR-021). A filing run is never a baseline -- a filing run refused mid-run
loaded the very grammar the gate refused, and letting it re-baseline would
whitewash that grammar. (A narrowing of research R-12, recorded in the
implementation's decisions.)

WITH NO BASELINE, every error is pre-existing (FR-022): warned about, counted
in the plan, not blocking, `baseline_source: "absent"`. That errors which were
already there are benign is a working hypothesis, and the standing says so.

UNKNOWN IS NEVER CLEAN. A load whose error file could not be read cannot be
shown to have introduced no new errors, so it refuses as `new_load_errors`
with the unreadable file as its one unaccounted-for error. Likewise an
eligibility read that failed, against a baseline that has one.

THE SAME COMPARISON RUNS THREE TIMES (FR-024, R-05): at the preview, again on
the confirmed call, and inside the filing worker on EVERY grammar load of the
job -- against the confirmed call's own load, `baseline_source: "this_run"`.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from . import wording

__all__ = [
    "Baseline",
    "GateStanding",
    "find_baseline",
    "evaluate",
    "reference_from",
]

_RE_BASELINE = (
    "The only way past this is to run a read-only flextools_parse_text of the same "
    "scope (without apply), which re-baselines: its load errors and eligible forms "
    "then count as pre-existing. There is no override."
)


@dataclass
class Baseline:
    """What the gate compares THIS load against."""

    run_id: Optional[str]
    created_at: Optional[str]
    errors: List[Dict[str, Any]]
    #: `[{entry_guid, headword}]`, or None for a pre-CP4 baseline.
    eligible: Optional[List[Dict[str, Any]]]
    #: Where it came from: "prior_run:<id>", or "this_run" at job time.
    source: str = ""
    record: Any = None

    def __post_init__(self) -> None:
        if not self.source:
            self.source = f"prior_run:{self.run_id}" if self.run_id else "absent"

    def lines(self) -> Optional[Iterator[Dict[str, Any]]]:
        """The baseline run's result lines (for the duplicate disclosure)."""
        if self.record is None:
            return None
        return self.record.iter_results()


def _canonical(error: Dict[str, Any]) -> str:
    """One load error as a comparable key. `Hvo` is already dropped (CP3)."""
    return json.dumps({k: v for k, v in sorted(error.items()) if k != "Hvo"},
                      sort_keys=True, ensure_ascii=True)


@dataclass
class GateStanding:
    """data-model section 4, plus what a refusal needs."""

    status: str
    signal: Optional[str]
    load_error_count: int
    pre_existing_error_count: int
    new_errors: List[Dict[str, Any]]
    resolved_error_count: int
    eligible_count: Optional[int]
    baseline_eligible_count: Optional[int]
    dropped_entries: List[Dict[str, Any]]
    baseline_source: str
    baseline_error_count: int = 0
    log_path: Optional[str] = None
    eligibility_note: Optional[str] = None
    load_note: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def refused(self) -> bool:
        return self.status == "refused"

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "status": self.status,
            "signal": self.signal,
            "load_error_count": self.load_error_count,
            "pre_existing_error_count": self.pre_existing_error_count,
            "new_errors": list(self.new_errors),
            "resolved_error_count": self.resolved_error_count,
            "eligible_count": self.eligible_count,
            "baseline_eligible_count": self.baseline_eligible_count,
            "dropped_entries": list(self.dropped_entries),
            "baseline_source": self.baseline_source,
            "hypothesis_note": wording.HYPOTHESIS_NOTE,
        }
        if self.eligibility_note:
            out["eligibility_note"] = self.eligibility_note
        if self.load_note:
            out["load_note"] = self.load_note
        return out

    def refusal_detail(self) -> Dict[str, Any]:
        """`grammar_load_unclean`'s detail, in the contract's order."""
        return {
            "signal": self.signal,
            "new_error_count": len(self.new_errors),
            "baseline_error_count": self.baseline_error_count,
            "baseline_source": self.baseline_source,
            "log_path": self.log_path,
            "new_errors": list(self.new_errors),
            "dropped_entries": list(self.dropped_entries),
            "baseline_eligible_count": self.baseline_eligible_count,
            "eligible_count": self.eligible_count,
        }

    def message(self) -> str:
        """The refusal's words (data-model section 8's register)."""
        if self.signal == "morpher_null":
            return (
                "Filing refused: the parser could not be built from this grammar "
                "(a probe parse returned nothing), so every word would be filed as "
                "unparseable and its unused, unapproved analyses deleted. Fix the "
                "grammar and try again; there is no override. Nothing was written."
            )
        if self.signal == "eligible_forms_dropped":
            names = ", ".join(repr(e.get("headword") or e.get("entry_guid"))
                              for e in self.dropped_entries[:10])
            more = "" if len(self.dropped_entries) <= 10 else f" and {len(self.dropped_entries) - 10} more"
            which = (f" No longer eligible: {names}{more}." if self.dropped_entries
                     else " This load's eligible forms could not be read, so the "
                          "comparison could not be made.")
            return (
                f"Filing refused: fewer lexical forms can reach the grammar than in "
                f"the baseline ({self.baseline_source}) -- the loader drops such "
                f"entries without logging any error, and filing would then delete "
                f"the analyses they used to license.{which} {_RE_BASELINE} Nothing "
                f"was written."
            )
        count = len(self.new_errors)
        return (
            f"Filing refused: this grammar load has {count} load error(s) that the "
            f"baseline ({self.baseline_source}, {self.baseline_error_count} error(s)) "
            f"did not -- an edit may have broken entries the parser can no longer "
            f"see, and filing would delete the analyses they licensed. "
            f"{_RE_BASELINE} Nothing was written."
        )


def evaluate(current: Dict[str, Any], baseline: Optional[Baseline]) -> GateStanding:
    """Compare this load (the worker's `filing_gate` answer) with a baseline."""
    load = current.get("load") or {}
    eligible_now = current.get("eligible") or {}
    source = baseline.source if baseline is not None else "absent"
    log_path = load.get("source")

    base_errors = list(baseline.errors) if baseline is not None else []
    captured = bool(load.get("captured"))
    errors_now = list(load.get("errors") or []) if captured else []

    now_eligible = list(eligible_now.get("entries") or []) if eligible_now.get("known") else None
    base_eligible = baseline.eligible if baseline is not None else None

    standing = GateStanding(
        status="clean", signal=None,
        load_error_count=len(errors_now),
        pre_existing_error_count=0,
        new_errors=[],
        resolved_error_count=0,
        eligible_count=len(now_eligible) if now_eligible is not None else None,
        baseline_eligible_count=len(base_eligible) if base_eligible is not None else None,
        dropped_entries=[],
        baseline_source=source,
        baseline_error_count=len(base_errors),
        log_path=log_path,
    )

    # FR-020 -- first, and unconditionally. A probe that did not say whether
    # the parser was built is not a probe that said it was (unknown refuses).
    if current.get("morpher_null") is not False:
        standing.status, standing.signal = "refused", "morpher_null"
        return standing

    # FR-021 / FR-022 / FR-023 -- the load-error diff, as a MULTISET.
    if not captured:
        standing.status, standing.signal = "refused", "new_load_errors"
        standing.new_errors = [{
            "type": "UnreadableLoadErrors",
            "reason": load.get("reason") or "this grammar load's error file could not be read",
        }]
        standing.load_note = (
            "This load's errors could not be read, so it cannot be shown to have "
            "introduced none. FLEx's own load-error file is never used in its place."
        )
        return standing
    if baseline is None:
        standing.pre_existing_error_count = len(errors_now)
    else:
        now_counts = Counter(_canonical(e) for e in errors_now)
        base_counts = Counter(_canonical(e) for e in base_errors)
        new_keys = now_counts - base_counts
        standing.resolved_error_count = sum((base_counts - now_counts).values())
        remaining = dict(new_keys)
        for error in errors_now:
            key = _canonical(error)
            if remaining.get(key):
                standing.new_errors.append(dict(error))
                remaining[key] -= 1
        standing.pre_existing_error_count = len(errors_now) - len(standing.new_errors)
        if standing.new_errors:
            standing.status, standing.signal = "refused", "new_load_errors"
            return standing

    # FR-039 / D-1 -- the eligibility diff.
    if base_eligible is None:
        standing.eligibility_note = (
            "There is no eligibility baseline for this scope yet (the baseline run "
            "predates CP4, or none exists), so only load errors were compared. A "
            "read-only parse of the scope records one."
        )
    elif now_eligible is None:
        standing.status, standing.signal = "refused", "eligible_forms_dropped"
        return standing
    else:
        now_guids = {e.get("entry_guid") for e in now_eligible}
        dropped = [dict(e) for e in base_eligible if e.get("entry_guid") not in now_guids]
        if dropped:
            standing.dropped_entries = dropped
            standing.status, standing.signal = "refused", "eligible_forms_dropped"
            return standing

    if standing.load_error_count:
        standing.status = "pre_existing_errors"
    return standing


def reference_from(current: Dict[str, Any]) -> Baseline:
    """The confirmed call's own load, as the job-time reference (FR-024, R-05)."""
    load = current.get("load") or {}
    eligible = current.get("eligible") or {}
    return Baseline(
        run_id=None, created_at=None,
        errors=list(load.get("errors") or []),
        eligible=list(eligible.get("entries") or []) if eligible.get("known") else None,
        source="this_run",
    )


def find_baseline(
    project_name: str, scope_key: str, *, record_dir: Optional[Path] = None
) -> Optional[Baseline]:
    """The newest READ-ONLY batch run of this project and scope with a captured baseline.

    Newest by `created_at` (CP3's R-03 class: never by name or mtime). A
    filing run is never a baseline (module docstring).
    """
    from ..parse.record import RunRecord, list_run_ids

    best: Optional[Baseline] = None
    for run_id in list_run_ids(record_dir):
        try:
            record = RunRecord(run_id, record_dir=record_dir)
            meta = record.read_meta()
        except Exception:  # noqa: BLE001 -- one unreadable record never hides the rest
            continue
        if meta is None or meta.filing:
            continue
        if (meta.project_name or "").casefold() != (project_name or "").casefold():
            continue
        baseline = meta.load_error_baseline or {}
        if not baseline.get("captured") or baseline.get("scope_fingerprint_key") != scope_key:
            continue
        if best is not None and (meta.created_at or "") <= (best.created_at or ""):
            continue
        eligible = baseline.get("eligible_entries")
        best = Baseline(
            run_id=run_id, created_at=meta.created_at,
            errors=list(baseline.get("errors") or []),
            eligible=list(eligible) if isinstance(eligible, list) else None,
            record=record,
        )
    return best
