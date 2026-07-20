#!/usr/bin/env python3
"""green_report.py -- first-pass-green metric report for FlexToolsMCP (issue #50).

STDLIB ONLY (json, argparse, statistics).

Usage
-----
  python scripts/green_report.py [JSONL_FILE ...]
      --previous PREV_FILE     compare reject counts to an older JSONL file
      --json                   emit JSON to stdout instead of ASCII table
      --top N                  show top N reject codes (default 10)

The report reads one or more operations.jsonl files (current + rotated),
groups operations into intent-sessions, and computes:

  first_pass_green_rate  - fraction of intent-groups whose FIRST op is "ok"
  turns_to_green         - median + p90 ops until first "ok" per group
  abandoned              - intent-groups that never reached "ok"
  rejects_by_error_code  - counts per error_code, with optional trend
  retry_loop_trips       - ops where assistance_triggered == true

Session-grouping (#62)
----------------------
Records sharing the same non-empty `session_id` (a stable identity anchor,
NOT the free-text `user_intent` label) form one group. Records with no
`session_id` (older JSONL) fall back to the legacy rule: consecutive records
sharing the same non-empty user_intent form one group; a missing/blank
user_intent is always a standalone group of 1.

Malformed lines (not valid JSON) are skipped and counted.

Output -- ASCII only (no emoji, no Unicode bullets): Windows-safe.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_jsonl(paths: List[Path]) -> Tuple[List[Dict[str, Any]], int]:
    """Load records from a list of JSONL files. Returns (records, skipped_count)."""
    records: List[Dict[str, Any]] = []
    skipped = 0
    for path in paths:
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
                    except (json.JSONDecodeError, ValueError):
                        skipped += 1
        except OSError as exc:
            print(f"[WARN] Could not read {path}: {exc}", file=sys.stderr)
    return records, skipped


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def _group_records(records: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Group records into attempt-sessions keyed by stable `session_id` (#62).

    `session_id` (stamped by `SessionState.configure()` and threaded into the
    JSONL record at op-start time) is the grouping key, NOT `user_intent`.
    `user_intent` is a natural-language label the LLM can rewrite between
    calls, so grouping by it (the old behavior) produced two failure modes:

      - One authoring session split across an intent-string edit became two
        groups (inflated group count, understated turns-to-green).
      - Two unrelated scripts sharing a generic intent string (e.g. both say
        "fix the bug") merged into one group (inflated turns-to-green).

    Rules:
    1. Records sharing a non-empty `session_id` are grouped together (not
       required to be consecutive), in first-appearance order.
    2. Records with no `session_id` (JSONL written before this field existed,
       or any other code path lacking session identity) fall back to the
       legacy rule: consecutive records sharing the same non-empty
       `user_intent` form one group; an empty `user_intent` is always a
       standalone group of 1.

    This mirrors `op_telemetry.group_records_by_session()` field-for-field so
    the in-server stats block and this CLI report agree (#66).
    """
    groups: List[List[Dict[str, Any]]] = []
    session_group_index: Dict[str, int] = {}
    legacy_intent: Optional[str] = None
    legacy_group: Optional[List[Dict[str, Any]]] = None

    for r in records:
        sid = (r.get("session_id") or "").strip()
        if sid:
            if legacy_group:
                groups.append(legacy_group)
            legacy_group = None
            legacy_intent = None

            idx = session_group_index.get(sid)
            if idx is None:
                groups.append([])
                idx = len(groups) - 1
                session_group_index[sid] = idx
            groups[idx].append(r)
            continue

        # Legacy fallback: no session_id on this record.
        intent = (r.get("user_intent") or "").strip()
        if intent:
            if legacy_group is not None and intent == legacy_intent:
                legacy_group.append(r)
            else:
                if legacy_group:
                    groups.append(legacy_group)
                legacy_group = [r]
                legacy_intent = intent
        else:
            # No intent: flush ongoing legacy group, add standalone
            if legacy_group:
                groups.append(legacy_group)
                legacy_group = None
                legacy_intent = None
            groups.append([r])

    if legacy_group:
        groups.append(legacy_group)

    return groups


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------

def compute_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute all report metrics from a flat list of JSONL records."""
    groups = _group_records(records)

    first_pass_green = 0
    turns_list: List[int] = []
    abandoned = 0
    total_groups = len(groups)

    for grp in groups:
        first_outcome = (grp[0].get("outcome") or "")
        if first_outcome == "ok":
            first_pass_green += 1
            turns_list.append(1)
        else:
            ok_idx = next(
                (i for i, r in enumerate(grp) if r.get("outcome") == "ok"), None
            )
            if ok_idx is not None:
                turns_list.append(ok_idx + 1)
            else:
                abandoned += 1

    first_pass_green_rate = (
        round(first_pass_green / total_groups, 4) if total_groups else None
    )

    turns_median: Optional[float] = None
    turns_p90: Optional[float] = None
    if turns_list:
        turns_median = statistics.median(turns_list)
        sorted_turns = sorted(turns_list)
        p90_idx = int(len(sorted_turns) * 0.9)
        turns_p90 = float(sorted_turns[min(p90_idx, len(sorted_turns) - 1)])

    # Reject counts
    reject_counts: Dict[str, int] = {}
    for r in records:
        if r.get("outcome") in ("preflight_reject", "runtime_fail", "timeout"):
            code = (r.get("error_code") or "unknown").strip() or "unknown"
            reject_counts[code] = reject_counts.get(code, 0) + 1

    # Retry loop trips
    retry_loop_trips = sum(
        1 for r in records if r.get("assistance_triggered") is True
    )

    return {
        "total_records": len(records),
        "total_groups": total_groups,
        "first_pass_green": first_pass_green,
        "first_pass_green_rate": first_pass_green_rate,
        "turns_to_green_median": turns_median,
        "turns_to_green_p90": turns_p90,
        "abandoned_groups": abandoned,
        "retry_loop_trips": retry_loop_trips,
        "rejects_by_error_code": dict(
            sorted(reject_counts.items(), key=lambda x: x[1], reverse=True)
        ),
    }


def compute_trend(current: Dict[str, int], previous: Dict[str, int]) -> Dict[str, int]:
    """Compute delta = current[code] - previous[code] for each reject code."""
    all_codes = set(current) | set(previous)
    return {c: current.get(c, 0) - previous.get(c, 0) for c in all_codes}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _pct(rate: Optional[float]) -> str:
    if rate is None:
        return "N/A"
    return f"{rate * 100:.1f}%"


def render_ascii(
    metrics: Dict[str, Any],
    trend: Optional[Dict[str, int]],
    top_n: int,
    skipped: int,
    prev_paths: Optional[List[Path]],
) -> str:
    lines: List[str] = []
    sep = "-" * 60
    lines.append(sep)
    lines.append("  FlexToolsMCP First-Pass-Green Report")
    lines.append(sep)
    lines.append(f"  Total records    : {metrics['total_records']}"
                 + (f"  (skipped malformed: {skipped})" if skipped else ""))
    lines.append(f"  Intent groups    : {metrics['total_groups']}")
    lines.append(f"  Abandoned groups : {metrics['abandoned_groups']}")
    lines.append(f"  Retry-loop trips : {metrics['retry_loop_trips']}")
    lines.append(sep)
    lines.append(
        f"  First-pass green : {_pct(metrics['first_pass_green_rate'])}"
        f"  ({metrics['first_pass_green']}/{metrics['total_groups']} groups)"
    )
    lines.append(
        "  NOTE: 'green'/'ok' means the op executed without preflight-reject or"
    )
    lines.append(
        "        crash -- NOT that its output is domain-correct. A dry/read-only"
    )
    lines.append(
        "        run can be green while producing logically wrong results."
    )
    ttg_med = metrics["turns_to_green_median"]
    ttg_p90 = metrics["turns_to_green_p90"]
    lines.append(
        f"  Turns to green   : median={ttg_med if ttg_med is not None else 'N/A'}"
        f"  p90={ttg_p90 if ttg_p90 is not None else 'N/A'}"
    )
    lines.append(sep)
    lines.append("  Rejects by error code" + (f" (top {top_n})" if top_n else "") + ":")
    if trend is not None and prev_paths:
        baseline = ", ".join(str(p) for p in prev_paths)
        lines.append(f"  Compared to: {baseline}")
    lines.append(
        f"  {'ERROR CODE':<35} {'COUNT':>6}"
        + (f"  {'TREND':>7}" if trend is not None else "")
    )
    lines.append("  " + "-" * (43 + (9 if trend is not None else 0)))

    rejects = metrics["rejects_by_error_code"]
    shown = 0
    for code, count in sorted(rejects.items(), key=lambda x: x[1], reverse=True):
        if top_n and shown >= top_n:
            break
        trend_str = ""
        if trend is not None:
            delta = trend.get(code, 0)
            trend_str = f"  {'+' if delta > 0 else ''}{delta:>6}"
        lines.append(f"  {code:<35} {count:>6}{trend_str}")
        shown += 1

    if not rejects:
        lines.append("  (no rejects recorded)")

    lines.append(sep)
    return "\n".join(lines)


def render_json_output(
    metrics: Dict[str, Any],
    trend: Optional[Dict[str, int]],
    skipped: int,
) -> str:
    out: Dict[str, Any] = dict(metrics)
    out["skipped_malformed_lines"] = skipped
    if trend is not None:
        out["reject_trend_vs_previous"] = trend
    return json.dumps(out, indent=2)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="First-pass-green metric report for FlexToolsMCP operations."
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="JSONL_FILE",
        help="operations.jsonl file(s) to analyse (default: operations.jsonl + .1 in cwd)",
    )
    parser.add_argument(
        "--previous",
        metavar="PREV_FILE",
        help="older JSONL file to compute reject-count trends against",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="emit JSON instead of ASCII table",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="number of top reject codes to show (default: 10)",
    )
    args = parser.parse_args(argv)

    # Resolve input files
    if args.files:
        input_paths = [Path(f) for f in args.files]
    else:
        input_paths = [Path("operations.jsonl"), Path("operations.jsonl.1")]

    records, skipped = load_jsonl(input_paths)
    metrics = compute_metrics(records)

    trend: Optional[Dict[str, int]] = None
    prev_paths = None
    if args.previous:
        prev_paths = [Path(args.previous)]
        prev_records, _ = load_jsonl(prev_paths)
        prev_metrics = compute_metrics(prev_records)
        trend = compute_trend(
            metrics["rejects_by_error_code"],
            prev_metrics["rejects_by_error_code"],
        )

    if args.json_output:
        print(render_json_output(metrics, trend, skipped))
    else:
        print(render_ascii(metrics, trend, args.top, skipped, prev_paths))

    return 0


if __name__ == "__main__":
    sys.exit(main())
