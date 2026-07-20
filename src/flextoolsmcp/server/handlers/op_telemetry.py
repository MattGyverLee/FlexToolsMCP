"""Structured per-operation telemetry for FlexToolsMCP (issue #50).

Each call to handle_run_module emits exactly ONE JSONL line to
operations.jsonl once the operation closes (success / failure / reject).
The prose operations.log and the JSONL file are always written from the
same code path (the three close functions), so they can never diverge.

Lifecycle of the per-op-id stash
---------------------------------
_OP_STASH: dict[op_id -> dict]  (module-level, bounded to _STASH_MAX)

1. _stash_op_start(op_id, ...)  is called at _log_operation_start time.
   It stores the fields that the close functions don't receive: project,
   write_enabled, source_kind, user_intent, user_request, code_sha256,
   code_bytes, code_lines, and timestamps.

2. Each close function (success / failure / reject) calls
   _write_jsonl_line(op_id, ...) which pops the stash entry (drain),
   merges the outcome fields, and appends one JSONL line.

3. If a stash entry is never drained (server crash, interrupted ops) it
   ages out when the stash exceeds _STASH_MAX via the FIFO eviction below.
   Evicted entries are silently dropped -- a missing JSONL line is
   preferable to a memory leak.

Rotation
--------
operations.jsonl rotates at _ROTATION_LINES lines.  The current file is
renamed to operations.jsonl.1 (overwriting an older .1 if present) and a
fresh file is opened.  The report accepts a list of files so historical
data in .1 is still counted.
"""

import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------
_ROTATION_LINES: int = 10_000   # rotate when this many lines exist
_STASH_MAX: int = 512            # evict oldest entry when exceeded (FIFO)


# ---------------------------------------------------------------------------
# Per-op-id stash (module-level singleton)
# ---------------------------------------------------------------------------
_OP_STASH: Dict[str, Dict[str, Any]] = {}      # op_id -> metadata dict
_OP_STASH_ORDER: Deque[str] = deque()          # insertion order for O(1) FIFO eviction


def _stash_op_start(
    op_id: str,
    project: str,
    write_enabled: bool,
    source_kind: str,
    user_intent: Optional[str],
    code_sha256: str,
    code_bytes: int,
    code_lines: int,
    user_request: Optional[str] = None,
) -> None:
    """Store per-op metadata at operation-start time so close functions can read it.

    This is the ONLY writer to _OP_STASH.  Every close function is the only
    drainer.  The dict entry is popped (not just read) in _write_jsonl_line
    so memory is released exactly once per operation, even if somehow a close
    function is called twice (idempotent on second call -- no double-write).

    `user_request` (diagnostic-report feature, spec section 4): verbatim
    human request text. Callers are expected to have already applied the
    user_intent fallback (see execution._log_operation_start) before
    stashing, so the value here is the EFFECTIVE one that should round-trip
    into the JSONL record -- not necessarily the raw per-op argument.
    """
    global _OP_STASH, _OP_STASH_ORDER

    # Evict oldest when at capacity (deque.popleft is O(1))
    while len(_OP_STASH_ORDER) >= _STASH_MAX:
        oldest = _OP_STASH_ORDER.popleft()
        _OP_STASH.pop(oldest, None)

    _OP_STASH[op_id] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "project": project,
        "write_enabled": write_enabled,
        "source_kind": source_kind,
        "user_intent": user_intent or "",
        "user_request": (user_request or "").strip() or (user_intent or "").strip(),
        "code_sha256": code_sha256,
        "code_bytes": code_bytes,
        "code_lines": code_lines,
    }
    _OP_STASH_ORDER.append(op_id)


# ---------------------------------------------------------------------------
# JSONL file helpers
# ---------------------------------------------------------------------------

def _get_jsonl_path(log_dir: Path) -> Path:
    return log_dir / "operations.jsonl"


def _rotate_if_needed(jsonl_path: Path) -> None:
    """Rotate jsonl_path -> jsonl_path.1 when line count exceeds _ROTATION_LINES."""
    if not jsonl_path.exists():
        return
    try:
        # Count newlines in fixed-size binary chunks instead of decoding the
        # whole file into memory. Stops early once the threshold is crossed.
        count = 0
        with open(jsonl_path, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)  # 1 MiB
                if not chunk:
                    break
                count += chunk.count(b"\n")
                if count >= _ROTATION_LINES:
                    break
        if count < _ROTATION_LINES:
            return
        rotated = Path(str(jsonl_path) + ".1")
        jsonl_path.replace(rotated)
    except OSError:
        pass  # best-effort rotation; never crash the operation path


def _write_jsonl_line(
    op_id: str,
    seq: int,
    outcome: str,                     # "ok" | "preflight_reject" | "runtime_fail" | "timeout"
    duration_s: Optional[float],
    error_code: Optional[str],
    preflight_gate: Optional[str],
    info_count: int,
    warning_count: int,
    error_count: int,
    assistance_triggered: bool,
    *,
    log_dir_fn: Any,                  # callable -> Path, injected for testability
    casting_signature: Optional[str] = None,
) -> None:
    """Pop the stash for op_id and append one JSONL line to operations.jsonl.

    Design invariant: this function is called EXACTLY ONCE per op_id, from
    one of the three close functions.  The stash pop() means a second call
    with the same op_id is a no-op (no stash entry -> base record only, no
    double write -- but this should never happen in normal operation).

    `casting_signature` (diagnostic-report CP2, precision fix for the
    deferred cycle-2 QC P1): an optional per-op signature computed from the
    ACTUAL `casting_issues` list detected at preflight time
    (`diagnostic.triggers.compute_casting_signature()`), passed only by
    `_log_preflight_reject()` on a `casting_issues_detected` close.  Stored
    verbatim (empty string when absent) so `diagnostic.triggers.
    casting_recurrence_signature()` can key recurrence on the real failing
    property/interface instead of the coarse "any repeat this turn"
    fallback.  Older JSONL records written before this field existed simply
    lack the key on load -- `dict.get("casting_signature")` returns None,
    which the recurrence helper already treats as "fall through to the next
    tier" (backward compatible, no schema migration needed).
    """
    stash = _OP_STASH.pop(op_id, {})
    try:
        _OP_STASH_ORDER.remove(op_id)
    except ValueError:
        pass  # already evicted or never inserted (unit-test path)

    record: Dict[str, Any] = {
        "ts": stash.get("ts") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "op_id": op_id,
        "seq": seq,
        "project": stash.get("project", ""),
        "write_enabled": stash.get("write_enabled", False),
        "source_kind": stash.get("source_kind", ""),
        "user_intent": stash.get("user_intent", ""),
        "user_request": stash.get("user_request", ""),
        "code_sha256": stash.get("code_sha256", ""),
        "code_bytes": stash.get("code_bytes", 0),
        "code_lines": stash.get("code_lines", 0),
        "outcome": outcome,
        "error_code": error_code or "",
        "preflight_gate": preflight_gate or "",
        "casting_signature": casting_signature or "",
        "duration_s": round(duration_s, 4) if duration_s is not None else None,
        "auto_fixes_applied": 0,      # placeholder; set by caller when available
        "auto_discovered": [],        # placeholder; set by caller when available
        "assistance_triggered": assistance_triggered,
        "info_count": info_count,
        "warning_count": warning_count,
        "error_count": error_count,
    }

    try:
        log_dir = log_dir_fn()
        jsonl_path = _get_jsonl_path(log_dir)
        _rotate_if_needed(jsonl_path)
        with open(jsonl_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # telemetry must never crash the main operation path


# ---------------------------------------------------------------------------
# Public aggregation helpers (used by handle_get_operation_logs)
# ---------------------------------------------------------------------------

def _load_jsonl_records(log_dir: Path) -> List[Dict[str, Any]]:
    """Read all JSONL records from current + rotated files.  Skips malformed lines."""
    records: List[Dict[str, Any]] = []
    # Newest first so we can cap cheaply; caller can reverse if needed
    candidates = [
        log_dir / "operations.jsonl",
        log_dir / "operations.jsonl.1",
    ]
    for path in reversed(candidates):  # read oldest first -> chronological
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # tolerate malformed lines
        except OSError:
            pass
    return records


def group_records_by_intent(records: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Group consecutive records sharing the same user_intent into "attempt
    session" / turn groups.

    Each group ends when `user_intent` changes or is empty (an empty-intent
    record is always its own standalone group of 1). This is the exact turn
    boundary used by `compute_jsonl_statistics()`'s green-rate / turns-to-green
    analytics; the diagnostic-report feature (spec section 5) reuses it
    UNCHANGED so report slice boundaries match those shipped analytics
    (decision E7: the grouping key stays `user_intent`, NOT the pair of
    `(user_intent, user_request)` -- `user_request` is carried as payload
    only and never redefines the slice boundary).
    """
    groups: List[List[Dict[str, Any]]] = []
    current_intent: Optional[str] = None
    current_group: List[Dict[str, Any]] = []

    for r in records:
        intent = (r.get("user_intent") or "").strip()
        if not intent:
            # No intent -> standalone group of 1
            if current_group:
                groups.append(current_group)
                current_group = []
                current_intent = None
            groups.append([r])
        elif intent != current_intent:
            if current_group:
                groups.append(current_group)
            current_group = [r]
            current_intent = intent
        else:
            current_group.append(r)

    if current_group:
        groups.append(current_group)

    return groups


def compute_jsonl_statistics(log_dir: Path) -> Dict[str, Any]:
    """Compute aggregates for the get_operation_logs statistics block.

    Returns a dict with:
      first_pass_green_rate  - float 0-1 or None (no data)
      turns_to_green_median  - float or None
      turns_to_green_p90     - float or None
      rejects_by_error_code  - list[{error_code, count}] top-5

    The turns-to-green metric set (median + p90) is kept field-for-field
    consistent with scripts/green_report.py so the in-server stats block and
    the CLI report agree on names and values for the same JSONL input (#66).
    """
    records = _load_jsonl_records(log_dir)
    if not records:
        return {
            "first_pass_green_rate": None,
            "turns_to_green_median": None,
            "turns_to_green_p90": None,
            "rejects_by_error_code": [],
        }

    # --- rejects_by_error_code ---
    reject_counts: Dict[str, int] = {}
    for r in records:
        if r.get("outcome") in ("preflight_reject", "runtime_fail", "timeout"):
            code = r.get("error_code") or "unknown"
            reject_counts[code] = reject_counts.get(code, 0) + 1

    top5 = sorted(reject_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    rejects_by_error_code = [{"error_code": k, "count": v} for k, v in top5]

    # --- intent grouping for green-rate / turns-to-green ---
    groups = group_records_by_intent(records)

    if not groups:
        return {
            "first_pass_green_rate": None,
            "turns_to_green_median": None,
            "turns_to_green_p90": None,
            "rejects_by_error_code": rejects_by_error_code,
        }

    first_pass_green = 0
    turns_list: List[int] = []
    abandoned = 0

    for grp in groups:
        first_outcome = grp[0].get("outcome")
        if first_outcome == "ok":
            first_pass_green += 1
            turns_list.append(1)
        else:
            # Find first ok in the group
            ok_idx = next((i for i, r in enumerate(grp) if r.get("outcome") == "ok"), None)
            if ok_idx is not None:
                turns_list.append(ok_idx + 1)
            else:
                abandoned += 1

    total_groups = len(groups)
    first_pass_green_rate = round(first_pass_green / total_groups, 4) if total_groups else None

    if turns_list:
        sorted_turns = sorted(turns_list)
        n = len(sorted_turns)
        mid = n // 2
        median = sorted_turns[mid] if n % 2 else (sorted_turns[mid - 1] + sorted_turns[mid]) / 2
        turns_to_green_median = float(median)
        # p90 uses the same index formula as scripts/green_report.py (#66).
        p90_idx = int(n * 0.9)
        turns_to_green_p90 = float(sorted_turns[min(p90_idx, n - 1)])
    else:
        turns_to_green_median = None
        turns_to_green_p90 = None

    return {
        "first_pass_green_rate": first_pass_green_rate,
        "turns_to_green_median": turns_to_green_median,
        "turns_to_green_p90": turns_to_green_p90,
        "rejects_by_error_code": rejects_by_error_code,
        "abandoned_groups": abandoned,
    }
