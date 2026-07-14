#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic-report trigger predicate (spec section 6.1) and inferred
workaround-taken signal (spec section 6.2).

Operates ONLY on the closed-op JSONL record dict shape produced by
`flextoolsmcp.server.handlers.op_telemetry` -- no session-log parsing, no
network, no subprocess. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard this
module lives under.

Trigger predicate (6.1) -- fire when ANY of:
  1. outcome == "runtime_fail"            (ANY exception class; excludes
                                             outcome == "timeout")
  2. error_code == "invalid_api_chain"
  3. error_code == "casting_issues_detected" AND the same casting signature
     recurs within the same turn (recurrence-after-cast; a first-time
     casting hint that resolves cleanly does NOT fire)

Explicitly non-reportable error_codes are listed in NON_REPORTABLE_CODES and
always return False regardless of outcome, matching spec section 6.1's
closed list (discovery-flow codes, authoring mistakes, unprotected_writes,
partial_module_structure, project/infra codes, server_state_error).
"""

import hashlib
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Section 6.1: explicitly NON-reportable error_codes.
# ---------------------------------------------------------------------------
NON_REPORTABLE_CODES: frozenset = frozenset(
    {
        # Discovery-flow codes
        "undiscovered_entity",
        "api_discovery_required",
        # Authoring mistakes
        "syntax_error",
        "missing_imports",
        "undefined_variables",
        "wrong_library_imports",
        # Write-safety gate
        "unprotected_writes",
        # Structural half-conversion
        "partial_module_structure",
        # Project / infra codes
        "project_locked",
        "project_drive_unavailable",
        "project_path_mismatch",
        "project_not_found",
        # Server bring-up
        "server_state_error",
    }
)

# error_code stamped on a preflight_reject/runtime_fail close whose recurrence
# (not first occurrence) within a turn indicates a real coverage gap.
_CASTING_CODE = "casting_issues_detected"
_INVALID_CHAIN_CODE = "invalid_api_chain"


def compute_casting_signature(issues: List[Dict[str, Any]]) -> str:
    """Build a deterministic casting signature from a preflight
    `detect_casting_needs()` issues list (`server/validators.py`).

    CP2 precision fix for the deferred cycle-2 QC P1 (`triggers.py:62-77`):
    the CP1 v1 fallback in `casting_recurrence_signature()` treated ANY two
    `casting_issues_detected` closes in the same turn as a recurrence
    whenever neither carried a per-issue signature (both `casting_signature`
    and `preflight_gate` were blank/identical -- `preflight_gate` is always
    stamped with the literal string `"casting_issues_detected"`, so it never
    actually discriminated). That meant two UNRELATED casting issues (e.g.
    a bad `Gloss` access on one line and an unrelated bad `Definition`
    access reached on a later attempt) collapsed into a single "recurrence".

    This function is called at the ACTUAL preflight-reject call site
    (`handlers/execution.py`) with the real `casting_issues` list detected
    for that op, and its result is threaded into the JSONL
    `casting_signature` field (see `op_telemetry._write_jsonl_line`). Once
    populated, `casting_recurrence_signature()` above prefers this real
    value over the coarse fallback, so recurrence is keyed on the actual
    failing property + missing-interface combination: two closes only count
    as a recurrence when they name the SAME property/interface pair, not
    merely "some casting issue happened again this turn".

    Deterministic and order-independent (sorted before hashing) so the same
    underlying set of issues always yields the same signature regardless of
    detection order within a single preflight pass.
    """
    if not issues:
        return ""
    parts = []
    for issue in issues:
        prop = (issue.get("property") or "").strip()
        missing_on = issue.get("missing_on") or []
        if isinstance(missing_on, (list, tuple, set)):
            missing_key = ",".join(sorted(str(m) for m in missing_on))
        else:
            missing_key = str(missing_on)
        cast_iface = (issue.get("cast_interface") or "").strip()
        parts.append(f"{prop}|{missing_key}|{cast_iface}")
    parts.sort()
    joined = ";".join(parts)
    return hashlib.sha256(joined.encode("utf-8", errors="replace")).hexdigest()[:16]


def casting_recurrence_signature(record: Dict[str, Any]) -> str:
    """Best-effort per-record casting signature for recurrence detection.

    Prefers an explicit `casting_signature` field (a future telemetry
    enhancement that threads the specific property/pattern through the
    JSONL record). Falls back to `preflight_gate`, and finally to a fixed
    marker -- meaning, in the absence of a more specific signal, ANY repeat
    `casting_issues_detected` close within the same turn counts as a
    recurrence. This is a deliberately coarse v1 heuristic; refine once
    per-issue casting signatures are threaded into the JSONL schema (CP2/CP3).
    """
    return (
        record.get("casting_signature")
        or record.get("preflight_gate")
        or _CASTING_CODE
    )


def detect_casting_recurrence(turn_records: List[Dict[str, Any]]) -> Set[str]:
    """Return the set of op_ids within `turn_records` (an ordered, same-turn
    sequence) whose `casting_issues_detected` close is a RECURRENCE of an
    earlier one in the same turn -- i.e. NOT the first occurrence of that
    signature (spec section 6.1.3).

    `turn_records` should already be scoped to one turn (see
    `op_telemetry.group_records_by_intent`); recurrence is evaluated only
    within the given sequence, never across turns.
    """
    seen_signatures: Set[str] = set()
    recurring_op_ids: Set[str] = set()
    for rec in turn_records:
        if (rec.get("error_code") or "") != _CASTING_CODE:
            continue
        sig = casting_recurrence_signature(rec)
        if sig in seen_signatures:
            recurring_op_ids.add(rec.get("op_id", ""))
        else:
            seen_signatures.add(sig)
    return recurring_op_ids


def is_reportable_close(
    record: Dict[str, Any],
    *,
    recurring_op_ids: Optional[Set[str]] = None,
) -> bool:
    """Section 6.1 trigger predicate for a single closed-op JSONL record.

    `recurring_op_ids` is the output of `detect_casting_recurrence()` run
    over the same-turn sequence this record belongs to; pass it explicitly
    (or use `find_reportable_closes()` below to compute it automatically).
    """
    error_code = (record.get("error_code") or "").strip()
    outcome = record.get("outcome")

    # Closed, explicit non-reportable list always wins first (defensive --
    # also already implied by the outcome/error_code checks below).
    if error_code in NON_REPORTABLE_CODES:
        return False

    if outcome == "timeout":
        return False

    if outcome == "runtime_fail":
        # ANY exception class. Per spec section 6.1, on a runtime failure
        # error_code is stamped with the concrete exception class name
        # (e.g. "PolymorphicAttributeError"), not the literal string
        # "runtime_error" -- match on outcome, never on a fixed code string.
        return True

    if error_code == _INVALID_CHAIN_CODE:
        return True

    if error_code == _CASTING_CODE:
        recurring = recurring_op_ids or set()
        return record.get("op_id", "") in recurring

    return False


def find_reportable_closes(turn_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convenience wrapper: compute casting recurrence over `turn_records`
    and return the subset that satisfies `is_reportable_close()`.
    """
    recurring = detect_casting_recurrence(turn_records)
    return [
        rec
        for rec in turn_records
        if is_reportable_close(rec, recurring_op_ids=recurring)
    ]


def infer_workaround(turn_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Section 6.2: inferred "workaround taken" signal.

    No explicit "LibLCM workaround taken" signal exists in the code today.
    Infer it: within `turn_records` (an ordered, same-turn sequence -- see
    `op_telemetry.group_records_by_intent`), a reportable failure (6.1)
    followed LATER in the same sequence by a close with outcome == "ok" is
    the workaround signal.

    Returns the list of failing records (in original order) for which a
    later same-turn "ok" close exists. An empty list means either no
    reportable failure occurred, or none was followed by a green close
    (abandoned turn).
    """
    recurring = detect_casting_recurrence(turn_records)
    n = len(turn_records)
    result: List[Dict[str, Any]] = []
    for i, rec in enumerate(turn_records):
        if not is_reportable_close(rec, recurring_op_ids=recurring):
            continue
        if any(turn_records[j].get("outcome") == "ok" for j in range(i + 1, n)):
            result.append(rec)
    return result
