#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report rendering (spec section 7): render the seven-part bundle from a
reconstructed `reconstruct.ReportSlice`.

    1. Header        -- MCP/flexicon/liblcm/FieldWorks/OS/Python versions +
                         report schema version.
    2. Request        -- verbatim `user_request` (primary) + `flextools_start`
                         args for the turn.
    3. Interpretation -- `user_intent` paraphrase + ordered discovery
                         [TOOL CALL]/[TOOL ARGS] + preflight casting decisions.
    4. What was tried  -- code per op (source_kind / write flag), plus
                         MAX_REPORT_OPS summarize-not-drop + rotation-
                         truncation markers.
    5. The error       -- report.Error/Warning lines + joined error_code /
                         preflight_gate / outcome.
    6. The resolution  -- the green follow-up op, or an abandoned note.
    7. Structured JSONL appendix -- raw slice lines (incl. user_request /
                         user_intent).

Rendering only -- no file writing, no transport (that is CP3). The final
step applies `normalize.normalize_report_text()` to the ENTIRE rendered
body (spec section 8.3 / decision E2) before returning it.

No I/O, no network. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard this
module lives under.
"""

import json
from typing import Dict, List, Optional

try:
    from . import normalize
    from .reconstruct import ReportSlice, SliceOp
except ImportError:
    from server.diagnostic import normalize
    from server.diagnostic.reconstruct import ReportSlice, SliceOp

DEFAULT_SCHEMA_VERSION = "1"

_CODE_STOP_MARKERS = (
    "Report messages:",
    "[OK]",
    "[FAIL]",
    "[REJECT]",
    "Messages:",
    "=== Operation",
)


def _find_tool_call(ops: List[SliceOp], tool_name: str) -> Optional[Dict[str, Optional[str]]]:
    for op in ops:
        for call in op.discovery_calls:
            if call.get("tool") == tool_name:
                return call
    return None


def _is_code_stop_marker(line: str) -> bool:
    """Boundary-anchored stop-marker check (CP2 carryover P2 fix).

    The previous implementation used `marker in line` (an unanchored
    substring test), which could stop a code block early when a marker
    string legitimately appeared INSIDE a code line -- e.g. a print/string
    literal containing the substring "Messages:" (`report.Info("Log
    Messages: done")`) would falsely trip the same test that is meant to
    detect the real `Messages:        N info, ...` summary line the logger
    emits after the block. Every genuine stop line is emitted by the logger
    at column 0 of the (prefix-stripped) log line, so anchoring on
    ``stripped-line startswith marker`` keeps the real stop cases working
    while no longer matching a marker that merely appears mid-line.
    """
    stripped = line.strip()
    return any(stripped.startswith(marker) for marker in _CODE_STOP_MARKERS)


def _extract_code_block(log_lines: List[str]) -> List[str]:
    """Pull the `Code:` ... block out of a reconstructed operation's raw
    log lines (spec section 3.2: `Code:` + code lines at DEBUG)."""
    start_idx = None
    for i, line in enumerate(log_lines):
        if line.strip() == "Code:":
            start_idx = i
            break
    if start_idx is None:
        return []
    code_lines: List[str] = []
    for line in log_lines[start_idx + 1:]:
        if _is_code_stop_marker(line):
            break
        code_lines.append(line)
    return code_lines


def _render_header(slice_obj: ReportSlice, schema_version: str) -> str:
    lines = ["## 1. Header", ""]
    if slice_obj.session_header_lines:
        lines.extend(slice_obj.session_header_lines)
    else:
        lines.append(
            "(session environment block not available in this log slice -- "
            "possibly recycled by rotation)"
        )
    lines.append(f"Report schema version: {schema_version}")
    return "\n".join(lines)


def _render_request(slice_obj: ReportSlice) -> str:
    lines = ["## 2. Request", ""]
    first_op = slice_obj.ops[0] if slice_obj.ops else None
    user_request = (first_op.jsonl.get("user_request") if first_op else "") or "(not provided)"
    lines.append(f"**User request (verbatim):** {user_request}")
    start_call = _find_tool_call(slice_obj.ops, "flextools_start")
    if start_call is not None:
        lines.append("")
        lines.append(f"`flextools_start` args: {start_call.get('args') or '(not captured)'}")
    return "\n".join(lines)


def _render_interpretation(slice_obj: ReportSlice) -> str:
    lines = ["## 3. Interpretation", ""]
    first_op = slice_obj.ops[0] if slice_obj.ops else None
    user_intent = (first_op.jsonl.get("user_intent") if first_op else "") or "(not provided)"
    lines.append(f"**User intent (paraphrase):** {user_intent}")
    lines.append("")
    lines.append("**Discovery sequence:**")
    any_calls = False
    for op in slice_obj.ops:
        for call in op.discovery_calls:
            any_calls = True
            lines.append(f"- [TOOL CALL] {call['tool']}")
            if call.get("args"):
                lines.append(f"  [TOOL ARGS] {call['args']}")
    if not any_calls:
        lines.append("(no discovery calls captured in this slice)")
    lines.append("")
    lines.append("**Preflight casting decisions:**")
    any_casting = False
    for op in slice_obj.ops:
        for line in op.log_lines:
            if "Preflight casting:" in line:
                any_casting = True
                lines.append(f"- ({op.op_id}) {line.strip()}")
    if not any_casting:
        lines.append("(none)")
    return "\n".join(lines)


def _render_what_was_tried(slice_obj: ReportSlice) -> str:
    lines = ["## 4. What was tried", ""]
    for op in slice_obj.ops:
        rec = op.jsonl
        lines.append(f"### Op {op.op_id} (seq {op.seq})")
        lines.append(f"- source_kind: {rec.get('source_kind', '')}")
        lines.append(f"- write_enabled: {rec.get('write_enabled', False)}")
        if not op.found_in_log:
            lines.append(
                "- (log block not available -- recycled by rotation; see "
                "history-truncated note below)"
            )
            lines.append("")
            continue
        code_lines = _extract_code_block(op.log_lines)
        if code_lines:
            lines.append("```python")
            lines.extend(code_lines)
            lines.append("```")
        else:
            lines.append("(no code lines captured for this op)")
        lines.append("")

    if slice_obj.truncated_summary:
        lines.append("### Earlier ops in this turn (summarized, not dropped)")
        for s in slice_obj.truncated_summary:
            lines.append(f"- {s['op_id']} (seq {s['seq']}): {s['one_line']}")
        lines.append("")

    if slice_obj.rotation_truncated:
        lines.append(
            "**History truncated by rotation:** the following op_id(s) were "
            "requested but their log block has already been recycled past "
            "the rotation backupCount and could not be recovered: "
            + ", ".join(slice_obj.rotation_truncated)
        )

    if slice_obj.end_mismatches:
        lines.append(
            "**Log parse warning -- mismatched End marker(s):** the session "
            "log contained an `=== Operation End ===` marker whose op_id did "
            "not match the currently open block (possible rotation/"
            "interleaving artifact). The affected block was kept open rather "
            "than truncated, but the boundary may be imprecise: "
            + "; ".join(
                f"expected {m['expected']}, found {m['found']}"
                for m in slice_obj.end_mismatches
            )
        )

    return "\n".join(lines)


def _render_error(slice_obj: ReportSlice) -> str:
    lines = ["## 5. The error", ""]
    any_failure = False
    for op in slice_obj.ops:
        rec = op.jsonl
        outcome = rec.get("outcome", "")
        if outcome == "ok":
            continue
        any_failure = True
        error_code = rec.get("error_code", "") or "(none)"
        preflight_gate = rec.get("preflight_gate", "") or "(none)"
        lines.append(
            f"### Op {op.op_id}: outcome={outcome} error_code={error_code} "
            f"preflight_gate={preflight_gate}"
        )
        for line in op.log_lines:
            stripped = line.strip()
            if (
                "report.Error:" in line
                or "report.Warning:" in line
                or stripped.startswith("Error:")
                or stripped.startswith("Error type:")
            ):
                lines.append(f"- {stripped}")
    if not any_failure:
        lines.append("(no failing ops in this slice)")
    return "\n".join(lines)


def _render_resolution(slice_obj: ReportSlice) -> str:
    lines = ["## 6. The resolution", ""]
    green_ops = [op for op in slice_obj.ops if op.jsonl.get("outcome") == "ok"]
    if green_ops:
        last_ok = green_ops[-1]
        lines.append(
            f"Resolved: op {last_ok.op_id} (seq {last_ok.seq}) closed `ok`."
        )
    else:
        lines.append(
            "Not resolved in this slice: no green (`ok`) close was captured -- "
            "the turn appears to have been abandoned."
        )
    return "\n".join(lines)


def _render_appendix(slice_obj: ReportSlice) -> str:
    lines = ["## 7. Structured JSONL appendix", "", "```jsonl"]
    for rec in slice_obj.turn_records:
        lines.append(json.dumps(rec, ensure_ascii=False, sort_keys=True))
    lines.append("```")
    return "\n".join(lines)


def render_report(
    slice_obj: ReportSlice,
    *,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
) -> str:
    """Render the full seven-part markdown bundle (spec section 7) from a
    reconstructed `ReportSlice`, then apply path-scoped machine-hygiene
    normalization (section 8.3 / E2) to the assembled body.

    Rendering only: this function performs no file I/O and no transport --
    it returns a markdown string for the caller (a later checkpoint) to
    write to `~/.flextoolsmcp/reports/report_<ts>.md`.
    """
    sections = [
        _render_header(slice_obj, schema_version),
        _render_request(slice_obj),
        _render_interpretation(slice_obj),
        _render_what_was_tried(slice_obj),
        _render_error(slice_obj),
        _render_resolution(slice_obj),
        _render_appendix(slice_obj),
    ]
    body = "\n\n".join(sections)
    return normalize.normalize_report_text(body)
