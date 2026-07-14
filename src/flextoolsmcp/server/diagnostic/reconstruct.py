#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Slice reconstruction (spec sections 3, 5) + rotation stitching (resolved
Q3) + `MAX_REPORT_OPS` summarize-not-drop (spec section 5).

Pipeline (§3, §5, resolved Q3): resolve the target `op_id`/`seq` list from
`operations.jsonl` FIRST, then read the session log
`logs/YYYY-MM-DD/session_<id>.log` (and its rotations `.log.1/.2/.3`) and
extract each matching `=== Operation #N Start/End (op_id) ===` block,
joining the JSONL `error_code`/`outcome`/`code_sha256` by `op_id`/`seq`.

Default boundary = the turn (§5): reuses
`op_telemetry.group_records_by_intent()` UNCHANGED (decision E7 -- the
grouping key stays `user_intent`, never `(user_intent, user_request)`).

Rotation stitching is JSONL-driven, not file-boundary-driven (resolved Q3):
a `RotatingFileHandler` never splits a single log CALL, but a whole
operation BLOCK (many log calls between Start and End) can straddle a
rotation boundary if rotation fires mid-operation. The fix is to
concatenate the rotation files in true chronological order (oldest ->
newest: `.log.3`, `.log.2`, `.log.1`, `.log`) into one virtual stream before
block-parsing -- this reconstructs the real call order regardless of where
the physical file boundary fell. If a requested op's Start marker cannot be
found anywhere in the available rotation files, it has already been
recycled past `backupCount` and MUST be surfaced as an explicit
"history truncated by rotation" marker (no silent caps rule) -- never
silently omitted.

Pure functions over data (JSONL record lists, in-memory log text) plus one
filesystem-touching helper (`_rotation_file_candidates` / reading files) --
no network, no subprocess. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard this
module lives under.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..handlers.op_telemetry import group_records_by_intent
except ImportError:
    from server.handlers.op_telemetry import group_records_by_intent

# ---------------------------------------------------------------------------
# Spec section 5: safety cap on an LLM-sized slice. Excess ops are
# SUMMARIZED, not silently dropped ("no silent caps" rule).
# ---------------------------------------------------------------------------
MAX_REPORT_OPS: int = 12

_START_RE = re.compile(r"=== Operation #(\d+) Start \(([^)]+)\) ===")
_END_RE = re.compile(r"=== Operation #(\d+) End \(([^)]+)\) ===")
_TOOL_CALL_RE = re.compile(r"\[TOOL CALL\]\s+(\S+)")
_TOOL_ARGS_RE = re.compile(r"\[TOOL ARGS\]\s+(\S+):\s*(.*)$")

_SESSION_HEADER_START_MARK = "=== Session Environment ==="
_SESSION_HEADER_END_MARK = "=== End Session Environment ==="

# `_make_file_handler()` (server/kernel.py) formats every line as
# "%(asctime)s | %(levelname)-7s | %(message)s". Strip that prefix so
# downstream (render.py) works with clean message content, not raw
# logging-formatter noise.
_LOG_PREFIX_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| \S+\s*\| (.*)$"
)


def _strip_log_prefix(line: str) -> str:
    m = _LOG_PREFIX_RE.match(line)
    return m.group(1) if m else line


# ---------------------------------------------------------------------------
# Structured slice result.
# ---------------------------------------------------------------------------
@dataclass
class SliceOp:
    """One reconstructed operation within a report slice."""

    op_id: str
    seq: int
    jsonl: Dict[str, Any]
    log_lines: List[str] = field(default_factory=list)
    discovery_calls: List[Dict[str, Optional[str]]] = field(default_factory=list)
    found_in_log: bool = True


@dataclass
class ReportSlice:
    """The full reconstructed slice the renderer (render.py) consumes."""

    turn_records: List[Dict[str, Any]] = field(default_factory=list)
    ops: List[SliceOp] = field(default_factory=list)
    truncated_summary: List[Dict[str, Any]] = field(default_factory=list)
    rotation_truncated: List[str] = field(default_factory=list)
    boundary: str = "turn"  # "turn" | "explicit"
    session_header_lines: List[str] = field(default_factory=list)
    # CP2 carryover (P2) fix: mismatched `=== Operation #N End (op_id) ===`
    # markers encountered while parsing (see parse_log_text docstring) --
    # surfaced here instead of being silently absorbed into a truncated
    # block. Each entry: {"expected": op_id, "found": op_id}.
    end_mismatches: List[Dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 1: resolve the target op_id/seq list from JSONL (§3, §5).
# ---------------------------------------------------------------------------
def resolve_slice_records(
    all_records: List[Dict[str, Any]],
    *,
    op_ids: Optional[List[str]] = None,
    anchor_op_id: Optional[str] = None,
    steps_back: Optional[int] = None,
    include_from_op_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Resolve the ordered JSONL records that make up a report slice.

    - `op_ids`: explicit list of op_ids to include verbatim (in JSONL
      chronological order), bypassing turn-boundary logic entirely.
    - Otherwise, locate the turn (§5, E7 -- `group_records_by_intent`,
      reused UNCHANGED) containing `anchor_op_id` (defaults to the most
      recent record overall when not given):
        - `include_from_op_id` set -> slice from that op through turn end.
        - `steps_back` set -> slice from `steps_back` ops before the anchor
          through turn end.
        - neither set -> the WHOLE turn (the default boundary).
    """
    if op_ids:
        wanted = set(op_ids)
        return [r for r in all_records if r.get("op_id") in wanted]

    if not all_records:
        return []

    groups = group_records_by_intent(all_records)

    anchor_id = anchor_op_id if anchor_op_id is not None else all_records[-1].get("op_id")

    target_group: Optional[List[Dict[str, Any]]] = None
    anchor_idx = 0
    for grp in groups:
        for i, r in enumerate(grp):
            if r.get("op_id") == anchor_id:
                target_group = grp
                anchor_idx = i
                break
        if target_group is not None:
            break

    if target_group is None:
        return []

    if include_from_op_id is not None:
        start_idx = next(
            (i for i, r in enumerate(target_group) if r.get("op_id") == include_from_op_id),
            0,
        )
        return target_group[start_idx:]

    if steps_back is not None:
        start_idx = max(0, anchor_idx - steps_back)
        return target_group[start_idx:]

    return target_group


# ---------------------------------------------------------------------------
# Step 2: MAX_REPORT_OPS summarize-not-drop (§5).
# ---------------------------------------------------------------------------
def _summarize_op(record: Dict[str, Any]) -> Dict[str, Any]:
    intent = (record.get("user_intent") or "").strip()
    one_line = (
        f"{record.get('outcome', '?')} "
        f"({record.get('error_code') or 'no error'})"
        + (f" -- {intent[:80]}" if intent else "")
    )
    return {
        "op_id": record.get("op_id", ""),
        "seq": record.get("seq"),
        "outcome": record.get("outcome", ""),
        "error_code": record.get("error_code", ""),
        "one_line": one_line,
    }


def apply_max_report_ops(
    records: List[Dict[str, Any]],
    cap: int = MAX_REPORT_OPS,
) -> "tuple[List[Dict[str, Any]], List[Dict[str, Any]]]":
    """Bound `records` to at most `cap` entries.

    When the slice exceeds the cap, the OLDEST excess records are
    summarized (op_id, outcome, error_code, one-line) into
    `truncated_summary` -- never silently dropped -- and the most recent
    `cap` records (closest to the failure/resolution) are kept in full.

    Returns (kept_records, truncated_summary).
    """
    if cap <= 0 or len(records) <= cap:
        return records, []
    excess = records[:-cap]
    kept = records[-cap:]
    return kept, [_summarize_op(r) for r in excess]


# ---------------------------------------------------------------------------
# Step 3: rotation-aware session-log reading + block parsing (resolved Q3).
# ---------------------------------------------------------------------------
def rotation_file_candidates(session_log_path: Path) -> List[Path]:
    """Return existing rotation files for `session_log_path`, OLDEST first:
    `.log.3`, `.log.2`, `.log.1`, then the current `.log` (matches
    `RotatingFileHandler(backupCount=3)` naming; see server/kernel.py).
    """
    candidates: List[Path] = []
    for suffix in (3, 2, 1):
        candidate = Path(str(session_log_path) + f".{suffix}")
        if candidate.exists():
            candidates.append(candidate)
    if session_log_path.exists():
        candidates.append(session_log_path)
    return candidates


def _read_concatenated(paths: List[Path]) -> str:
    """Read and concatenate files in the given (chronological) order."""
    parts: List[str] = []
    for p in paths:
        try:
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return "\n".join(parts)


def parse_log_text(text: str) -> Dict[str, Any]:
    """Parse a (possibly rotation-concatenated) session-log text blob into:

      {"blocks": {op_id: {"seq": int, "lines": [...], "discovery_lines": [...]}},
       "session_header_lines": [...],
       "end_mismatches": [{"expected": op_id, "found": op_id}, ...]}

    `lines` are the full Start..End block content (prefix-stripped).
    `discovery_lines` are the `[TOOL CALL]` / `[TOOL ARGS]` lines that
    appeared between the PREVIOUS block's End marker (or start of stream)
    and this block's Start marker -- i.e. the discovery/interpretation
    calls that led up to this operation (spec section 7, item 3).

    CP2 carryover (P2) fix: a `=== Operation #N End (op_id) ===` marker
    whose `op_id` does NOT match the currently open block used to reset
    `current_op_id`/`current_lines` unconditionally, regardless of the
    mismatch. Because subsequent lines are only appended when
    `current_op_id is not None`, that reset silently swallowed every line
    between the bogus mismatched End and the block's REAL End marker (if
    any) -- they landed nowhere (not attributed to the block, and not
    `[TOOL CALL]`/`[TOOL ARGS]` discovery lines either). Per the "no silent
    caps/drops" rule, a mismatch must be SURFACED, not used to truncate: the
    open block now stays open (lines keep accumulating) and the mismatch is
    recorded both on the block itself (`end_mismatches` key) and in the
    top-level `end_mismatches` list so callers/rendering can flag it.
    """
    blocks: Dict[str, Dict[str, Any]] = {}
    pending_tool_lines: List[str] = []
    current_op_id: Optional[str] = None
    current_lines: List[str] = []
    session_header_lines: List[str] = []
    end_mismatches: List[Dict[str, str]] = []
    in_session_header = False

    for raw_line in text.splitlines():
        line = _strip_log_prefix(raw_line)

        if _SESSION_HEADER_START_MARK in line:
            in_session_header = True
            session_header_lines = [line]
            continue
        if in_session_header:
            session_header_lines.append(line)
            if _SESSION_HEADER_END_MARK in line:
                in_session_header = False
            continue

        m_start = _START_RE.search(line)
        m_end = _END_RE.search(line)

        if m_start:
            seq = int(m_start.group(1))
            op_id = m_start.group(2)
            current_op_id = op_id
            current_lines = [line]
            blocks[op_id] = {
                "seq": seq,
                "lines": current_lines,
                "discovery_lines": pending_tool_lines,
            }
            pending_tool_lines = []
            continue

        if m_end:
            end_op_id = m_end.group(2)
            if current_op_id is not None:
                current_lines.append(line)
                if end_op_id == current_op_id:
                    blocks[current_op_id]["lines"] = current_lines
                    current_op_id = None
                    current_lines = []
                else:
                    # Mismatch: surface it, but keep the block OPEN so later
                    # lines (up to the real End, if it ever appears) are not
                    # dropped on the floor.
                    blocks[current_op_id].setdefault("end_mismatches", []).append(end_op_id)
                    end_mismatches.append({"expected": current_op_id, "found": end_op_id})
            continue

        if current_op_id is not None:
            current_lines.append(line)
        elif "[TOOL CALL]" in line or "[TOOL ARGS]" in line:
            pending_tool_lines.append(line)

    return {
        "blocks": blocks,
        "session_header_lines": session_header_lines,
        "end_mismatches": end_mismatches,
    }


def stitch_and_extract_blocks(session_log_path: Path) -> Dict[str, Any]:
    """Concatenate rotation files (oldest -> newest) and parse the joined
    stream. This is the JSONL-DRIVEN stitching primitive: callers already
    know WHICH op_ids they want from JSONL (step 1); this just makes sure
    the block content is available regardless of which physical rotation
    file it landed in.
    """
    candidates = rotation_file_candidates(session_log_path)
    text = _read_concatenated(candidates)
    return parse_log_text(text)


def _extract_discovery_calls(lines: List[str]) -> List[Dict[str, Optional[str]]]:
    """Pair up `[TOOL CALL]` / `[TOOL ARGS]` lines into structured dicts."""
    calls: List[Dict[str, Optional[str]]] = []
    for line in lines:
        m_call = _TOOL_CALL_RE.search(line)
        if m_call:
            calls.append({"tool": m_call.group(1), "args": None})
            continue
        m_args = _TOOL_ARGS_RE.search(line)
        if m_args and calls:
            calls[-1]["args"] = m_args.group(2)
    return calls


# ---------------------------------------------------------------------------
# Top-level orchestrator.
# ---------------------------------------------------------------------------
def reconstruct_slice(
    all_jsonl_records: List[Dict[str, Any]],
    session_log_path: Path,
    *,
    op_ids: Optional[List[str]] = None,
    anchor_op_id: Optional[str] = None,
    steps_back: Optional[int] = None,
    include_from_op_id: Optional[str] = None,
    max_report_ops: int = MAX_REPORT_OPS,
) -> ReportSlice:
    """Reconstruct a full report slice (spec sections 3, 5) from JSONL
    records + the (rotation-stitched) session log.

    1. Resolve the target op_id list from JSONL (turn boundary by default,
       or an explicit selection / steps_back / include_from_op_id).
    2. Bound it to `max_report_ops`, summarizing any excess (oldest first).
    3. Stitch the session log across rotation files and extract each
       matching Start/End block, joined by op_id.
    4. Flag any resolved op_id whose block could not be found anywhere in
       the available rotation files as `rotation_truncated` (recycled past
       `backupCount`) -- never silently omitted.
    """
    selected = resolve_slice_records(
        all_jsonl_records,
        op_ids=op_ids,
        anchor_op_id=anchor_op_id,
        steps_back=steps_back,
        include_from_op_id=include_from_op_id,
    )

    kept_records, truncated_summary = apply_max_report_ops(selected, cap=max_report_ops)

    parsed = stitch_and_extract_blocks(session_log_path)
    blocks = parsed["blocks"]
    session_header_lines = parsed["session_header_lines"]
    end_mismatches = parsed.get("end_mismatches", [])

    ops: List[SliceOp] = []
    rotation_truncated: List[str] = []
    for rec in kept_records:
        op_id = rec.get("op_id", "")
        block = blocks.get(op_id)
        if block is None:
            rotation_truncated.append(op_id)
            ops.append(
                SliceOp(
                    op_id=op_id,
                    seq=rec.get("seq", 0),
                    jsonl=rec,
                    log_lines=[],
                    discovery_calls=[],
                    found_in_log=False,
                )
            )
            continue
        discovery_calls = _extract_discovery_calls(block.get("discovery_lines", []))
        ops.append(
            SliceOp(
                op_id=op_id,
                seq=rec.get("seq", block.get("seq", 0)),
                jsonl=rec,
                log_lines=block.get("lines", []),
                discovery_calls=discovery_calls,
                found_in_log=True,
            )
        )

    boundary = (
        "explicit"
        if (op_ids or steps_back is not None or include_from_op_id is not None)
        else "turn"
    )

    return ReportSlice(
        turn_records=selected,
        ops=ops,
        truncated_summary=truncated_summary,
        rotation_truncated=rotation_truncated,
        boundary=boundary,
        session_header_lines=session_header_lines,
        end_mismatches=end_mismatches,
    )
