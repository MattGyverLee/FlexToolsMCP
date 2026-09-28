#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Operation logging for the parse path (issue #167, parser-check CP6).

The run_module path (issue #50, `op_telemetry.py`) writes one JSONL line per
op to `operations.jsonl` once the operation closes. The parse tools
(`flextools_try_word`, `flextools_parse_text`, `flextools_parse_status`,
`flextools_parse_log`, `flextools_parse_diff`, `flextools_parse_cancel`,
`flextools_parse_release`, `flextools_parse_sandbox`, and
`flextools_grammar_health`) emitted no operation logging at all before this
module -- this closes that gap by reusing the SAME file, rotation, and
error-swallowing machinery (`op_telemetry.append_jsonl_record`), rather than
inventing a parallel format.

Design
------
Unlike run_module (which has a start phase and a separate close phase, and
therefore needs the `_OP_STASH` dict to carry fields between them), a parse
tool call is a single request/response round trip handled entirely inside
one `call_tool()` invocation in `server.py`. So there is no stash here: the
hook point (`log_parse_op`) is called exactly once, after the tool's
response envelope already exists, and it derives every field from that
response and the original call arguments -- never from a stash, a config
default, or an "intended" value.

One record per call. Fields:
    ts            -- UTC timestamp, "%Y-%m-%dT%H:%M:%SZ"
    kind          -- always "parse" (lets `compute_jsonl_statistics`
                     distinguish these from run_module's "kind": "run_module"
                     records sharing the same operations.jsonl file)
    tool          -- the MCP tool name, e.g. "flextools_parse_text"
    project       -- from the response body's "project" key when present,
                     else the "project_name" argument the caller passed,
                     else "" (never invented)
    run_id        -- the response body's "run_id" key, when present and
                     non-null; else "" (never invented -- a call that never
                     reached a run, e.g. a validation error, legitimately
                     has none)
    outcome       -- the response body's own "status" string verbatim (e.g.
                     "ok", "error", "refused", "proposed, unverified") when
                     present; "error" if absent but an error_code was found;
                     otherwise "unknown". This is deliberately NOT collapsed
                     to a binary ok/error -- collapsing "refused" into
                     "error" would assert something the response did not
                     say (the caution this issue opens with: never report a
                     value nothing acts on / that could be untrue).
    error_code    -- the response body's "error_code" (or, for the
                     deprecated nested shape, "error"."code"); "" when there
                     is none
    duration_s    -- wall-clock seconds the call took, timed by the caller
                     (server.py's `call_tool`) around the dispatch, rounded
                     to 4 decimals
    words_total / words_completed
                  -- ONLY for `flextools_parse_text` and
                     `flextools_parse_sandbox`, and ONLY when the response
                     body actually carries that integer field (or, for
                     parse_text's no-run "scope yielded no words" path,
                     `scope.words_resolved` as the total). No other tool
                     gets word-count fields, and neither field is ever
                     synthesized when the response does not carry it.

Every value above is read back from the actual tool response or the actual
call arguments. There is no configured/intended value fed into this record;
a field whose source value is missing or not the expected type is omitted
rather than guessed.

Failure mode: `log_parse_op` never raises. Any exception while parsing the
response or writing the file is caught and reported at DEBUG on this
module's own logger; the caller's tool response is unaffected either way.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# The parse-path tools this hook covers (parser-check CP2b/CP3/CP4/CP5,
# issue #223, and CP1's grammar_health). Kept as a frozenset (not imported
# from dispatch.py's TOOL_* constants) so this module has no import-time
# dependency on dispatch.py -- it is called FROM server.py, which already
# imports dispatch, and importing it back would risk a cycle for no benefit.
PARSE_TOOL_NAMES = frozenset({
    "flextools_try_word",
    "flextools_parse_status",
    "flextools_parse_text",
    "flextools_parse_log",
    "flextools_parse_diff",
    "flextools_parse_cancel",
    "flextools_parse_sandbox",
    "flextools_parse_release",
    "flextools_grammar_health",
})

# Only these two tools' responses ever carry word counts worth recording.
_WORD_COUNT_TOOLS = frozenset({"flextools_parse_text", "flextools_parse_sandbox"})


def _get_log_dir():
    """Resolve `get_log_dir` with the repo's dual package/script import mode."""
    try:
        from ..kernel import get_log_dir
    except ImportError:
        from server.kernel import get_log_dir
    return get_log_dir()


def _extract_response_dict(result: Any) -> Optional[Dict[str, Any]]:
    """Best-effort parse of a tool's `List[TextContent]` return into a dict.

    Mirrors the parsing `server.py`'s `call_tool` already does for its own
    prose [TOOL OK]/[TOOL ERROR] log line, so the two agree on what the
    response "says". Returns None for anything that isn't one JSON object
    (empty result, non-JSON text, a bare list/scalar) -- callers then simply
    omit the fields that dict would have supplied.
    """
    if not result:
        return None
    try:
        first = result[0]
        text = getattr(first, "text", None)
        if text is None and isinstance(first, dict):
            text = first.get("text")
        if not text:
            return None
        parsed = json.loads(text)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _derive_error_code(parsed: Dict[str, Any]) -> str:
    """Same precedence server.py's own [TOOL ERROR] parsing uses."""
    err_code = parsed.get("error_code")
    if err_code:
        return str(err_code)
    nested = parsed.get("error")
    if isinstance(nested, dict):
        code = nested.get("code")
        if code:
            return str(code)
    elif nested:
        return str(nested)
    return ""


def _derive_outcome(parsed: Dict[str, Any], error_code: str) -> str:
    status = parsed.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    if error_code:
        return "error"
    return "unknown"


def _derive_project(parsed: Dict[str, Any], arguments: Dict[str, Any]) -> str:
    project = parsed.get("project")
    if isinstance(project, str) and project:
        return project
    project = arguments.get("project_name")
    if isinstance(project, str) and project:
        return project
    return ""


def _derive_run_id(parsed: Dict[str, Any]) -> str:
    run_id = parsed.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id
    return ""


def _derive_word_counts(tool_name: str, parsed: Dict[str, Any]) -> Dict[str, int]:
    if tool_name not in _WORD_COUNT_TOOLS:
        return {}
    fields: Dict[str, int] = {}

    words_total = parsed.get("words_total")
    if not isinstance(words_total, int):
        scope = parsed.get("scope")
        if isinstance(scope, dict):
            candidate = scope.get("words_resolved")
            if isinstance(candidate, int):
                words_total = candidate
    if isinstance(words_total, int):
        fields["words_total"] = words_total

    words_completed = parsed.get("words_completed")
    if isinstance(words_completed, int):
        fields["words_completed"] = words_completed

    return fields


def log_parse_op(
    tool_name: str,
    arguments: Dict[str, Any],
    result: List[Any],
    duration_s: Optional[float],
) -> None:
    """Append one JSONL record for a closed parse-tool call.

    Args:
        tool_name: the MCP tool name (checked against `PARSE_TOOL_NAMES`;
            anything else is a silent no-op so this can be called
            unconditionally from the dispatch site).
        arguments: the raw arguments dict the tool was called with.
        result: the tool's `List[TextContent]` (or test-double equivalent)
            return value, AFTER any error handling has already turned an
            exception into an error envelope -- this only reads what the
            caller ended up sending back.
        duration_s: wall-clock seconds the call took, or None if the caller
            could not time it (never guessed).

    Never raises. Any failure is caught and logged at DEBUG.
    """
    if tool_name not in PARSE_TOOL_NAMES:
        return
    try:
        _log_parse_op_unguarded(tool_name, arguments or {}, result, duration_s)
    except Exception:  # noqa: BLE001 -- telemetry must never break the call
        logger.debug("parse telemetry logging failed for %s", tool_name, exc_info=True)


def _log_parse_op_unguarded(
    tool_name: str,
    arguments: Dict[str, Any],
    result: List[Any],
    duration_s: Optional[float],
) -> None:
    from .op_telemetry import append_jsonl_record

    parsed = _extract_response_dict(result) or {}
    error_code = _derive_error_code(parsed)

    record: Dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": "parse",
        "tool": tool_name,
        "project": _derive_project(parsed, arguments),
        "run_id": _derive_run_id(parsed),
        "outcome": _derive_outcome(parsed, error_code),
        "error_code": error_code,
        "duration_s": round(duration_s, 4) if duration_s is not None else None,
    }
    record.update(_derive_word_counts(tool_name, parsed))

    append_jsonl_record(record, log_dir_fn=_get_log_dir)
