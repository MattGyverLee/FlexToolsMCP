#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`flextools_prepare_report` tool handler + the shared report-bundle
orchestration used by BOTH that explicit tool and the run_module
success-close auto-offer advisory (spec sections 5, 6.5, 9, 10) -- CP3.

This module is a HANDLER (it does local file I/O: reads operations.jsonl /
the session log, and writes exactly one local report file per prepared
bundle), so it is deliberately NOT inside `server/diagnostic/` (that
package stays pure-function / read-only-on-local-files). It is, however,
explicitly in scope for the two-layer no-transmission guard (spec section
8.1/12) -- see `tests/test_diagnostic_no_transmission.py`, which scans this
module alongside the whole `server/diagnostic/` tree. Nothing here invokes
`subprocess`, `gh`, `smtplib`, `webbrowser`, an HTTP client, or a raw
socket; `server.diagnostic.transports` builds transport STRINGS only.

Pipeline (mirrors CP1/CP2's building blocks):
    load JSONL records + resolve session log path
        -> reconstruct.reconstruct_slice(...)          (sections 3, 5)
        -> pick the anchor record (the reportable failure, or best-effort
           fallback) for signature/title/summary
        -> [auto-offer path only] offered_store dedupe gate BEFORE writing
        -> render.render_report(...)                    (section 7)
        -> write ~/.flextoolsmcp/reports/report_<ts>.md  (THE only side
           effect that is not a read -- one local file write per call that
           doesn't early-return via the offer gate)
        -> transports.build_transports(...)              (section 9)
        -> sensitivity.likely_contains_lexical_data(...)  (section 9, Q4)
"""

import hashlib
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ._import_helper import safe_import_kernel_deps

json_response, session_state, get_log_dir, get_api_index = safe_import_kernel_deps()

try:
    from ..kernel import get_operations_logger, get_current_session_log_path
except ImportError:
    from server.kernel import get_operations_logger, get_current_session_log_path

try:
    from ...response_utils import error_response, build_response_with_context
except (ImportError, ValueError):
    from response_utils import error_response, build_response_with_context

try:
    from ...config import (
        config_get,
        REPORT_OFFERS_ENABLED_KEY, REPORT_OFFERS_ENABLED_DEFAULT,
        REPORT_REPO_KEY, REPORT_REPO_DEFAULT,
        REPORT_EMAIL_KEY, REPORT_EMAIL_DEFAULT,
    )
except (ImportError, ValueError):
    from config import (
        config_get,
        REPORT_OFFERS_ENABLED_KEY, REPORT_OFFERS_ENABLED_DEFAULT,
        REPORT_REPO_KEY, REPORT_REPO_DEFAULT,
        REPORT_EMAIL_KEY, REPORT_EMAIL_DEFAULT,
    )

try:
    from .op_telemetry import _load_jsonl_records, group_records_by_intent
except ImportError:
    from server.handlers.op_telemetry import _load_jsonl_records, group_records_by_intent

# One-way dependency: handlers/diagnostic_report.py -> diagnostic/* (never
# the reverse), matching the existing execution.py -> diagnostic.triggers
# precedent (see execution.py's CP2 import comment).
try:
    from ..diagnostic import reconstruct, render, sensitivity, transports as transports_mod
    from ..diagnostic import signature as signature_mod
    from ..diagnostic import triggers, offered_store
except ImportError:
    from server.diagnostic import reconstruct, render, sensitivity, transports as transports_mod
    from server.diagnostic import signature as signature_mod
    from server.diagnostic import triggers, offered_store


# Best-effort v1 heuristic (documented limitation, same spirit as CP1's
# casting_recurrence_signature fallback): pull a "failing symbol" out of the
# anchor op's raw log lines so runtime_fail signatures are more specific
# than "(exception class, '')" when a traceback attribute-error is present.
_ATTR_ERROR_RE = re.compile(r"has no attribute ['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]")


def _extract_failing_symbol(anchor_op: Optional[Any]) -> str:
    if anchor_op is None:
        return ""
    for line in getattr(anchor_op, "log_lines", []) or []:
        m = _ATTR_ERROR_RE.search(line)
        if m:
            return m.group(1)
    return ""


def _pick_anchor_record(turn_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pick the record to anchor signature/title/summary on: the (most
    recent) reportable failure in the slice (spec section 6.1/6.2 workaround
    signal), falling back to the last non-`ok` record, falling back to the
    last record overall (e.g. an all-green slice explicitly requested via
    flextools_prepare_report)."""
    if not turn_records:
        return {}
    reportable = triggers.find_reportable_closes(turn_records)
    if reportable:
        return reportable[-1]
    non_ok = [r for r in turn_records if r.get("outcome") != "ok"]
    if non_ok:
        return non_ok[-1]
    return turn_records[-1]


def _compute_signature_for(anchor_record: Dict[str, Any], failing_symbol: str) -> str:
    sig = signature_mod.compute_signature(anchor_record, failing_symbol=failing_symbol)
    if sig:
        return sig
    # Fallback for a slice with no reportable/failing record at all (e.g. an
    # explicit flextools_prepare_report call against an all-green turn) --
    # still needs a stable, deterministic, non-empty signature.
    op_id = anchor_record.get("op_id", "")
    error_code = anchor_record.get("error_code", "")
    raw = f"adhoc\x1f{op_id}\x1f{error_code}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:16]


def _build_title(anchor_record: Dict[str, Any]) -> str:
    code = anchor_record.get("error_code") or anchor_record.get("outcome") or "issue"
    intent = (anchor_record.get("user_intent") or "").strip()
    title = f"[auto-report] {code}"
    if intent:
        title = f"{title}: {intent}"
    return title[:200]


def _build_summary(anchor_record: Dict[str, Any]) -> str:
    lines = [
        f"Outcome: {anchor_record.get('outcome', '') or '(unknown)'}",
        f"Error code: {anchor_record.get('error_code', '') or '(none)'}",
    ]
    intent = (anchor_record.get("user_intent") or "").strip()
    if intent:
        lines.append(f"User intent: {intent}")
    request = (anchor_record.get("user_request") or "").strip()
    if request and request != intent:
        lines.append(f"User request: {request}")
    return "\n".join(lines)


def _default_reports_dir() -> Path:
    return offered_store.get_reports_dir()


def prepare_report_bundle(
    all_jsonl_records: List[Dict[str, Any]],
    session_log_path: Path,
    *,
    op_ids: Optional[List[str]] = None,
    anchor_op_id: Optional[str] = None,
    steps_back: Optional[int] = None,
    include_from_op_id: Optional[str] = None,
    repo: Optional[str] = None,
    email: Optional[str] = None,
    gh_available_fn: Optional[Callable[[], bool]] = None,
    reports_dir_fn: Optional[Callable[[], Path]] = None,
    max_report_ops: Optional[int] = None,
    offer_gate: Optional[Callable[[str], bool]] = None,
) -> Optional[Dict[str, Any]]:
    """Shared orchestration: reconstruct -> [gate] -> render -> write ->
    transports -> sensitivity. Returns None (no file written, no transports
    built) when `offer_gate` is provided and rejects the computed
    signature -- used by the auto-offer path (execution.py) so a
    dedupe-suppressed signature never causes a file write. The explicit
    `flextools_prepare_report` tool passes `offer_gate=None` so it always
    produces a bundle (spec section 5: explicit requests bypass dedupe).

    Exactly ONE local file write happens per call that does not early-return
    via `offer_gate` (spec section 8.1/12 dynamic no-transmission test).
    """
    reconstruct_kwargs: Dict[str, Any] = {}
    if max_report_ops is not None:
        reconstruct_kwargs["max_report_ops"] = max_report_ops

    slice_obj = reconstruct.reconstruct_slice(
        all_jsonl_records,
        Path(session_log_path),
        op_ids=op_ids,
        anchor_op_id=anchor_op_id,
        steps_back=steps_back,
        include_from_op_id=include_from_op_id,
        **reconstruct_kwargs,
    )

    anchor_record = _pick_anchor_record(slice_obj.turn_records)
    anchor_op = next(
        (op for op in slice_obj.ops if op.op_id == anchor_record.get("op_id")), None
    )
    failing_symbol = _extract_failing_symbol(anchor_op)
    sig = _compute_signature_for(anchor_record, failing_symbol)

    if offer_gate is not None and not offer_gate(sig):
        return None

    title = _build_title(anchor_record)
    summary = _build_summary(anchor_record)
    rendered = render.render_report(slice_obj)

    reports_dir_fn = reports_dir_fn or _default_reports_dir
    reports_dir = Path(reports_dir_fn())
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}{int(time.time_ns() % 1_000_000):06d}Z"
    report_path = reports_dir / f"report_{ts}.md"
    # THE one local file write. Writing transmits nothing (spec section 8.4).
    report_path.write_text(rendered, encoding="utf-8")

    likely_lexical = sensitivity.likely_contains_lexical_data(slice_obj)

    resolved_repo = repo if repo is not None else config_get(REPORT_REPO_KEY, REPORT_REPO_DEFAULT)
    resolved_email = email if email is not None else config_get(REPORT_EMAIL_KEY, REPORT_EMAIL_DEFAULT)

    built_transports = transports_mod.build_transports(
        title=title,
        summary=summary,
        report_path=report_path,
        repo=resolved_repo,
        email=resolved_email,
        gh_available_fn=gh_available_fn,
    )

    return {
        "signature": sig,
        "title": title,
        "summary": summary,
        "report_path": str(report_path),
        "report_markdown": rendered,
        "transports": built_transports,
        "likely_contains_lexical_data": likely_lexical,
        "error_code": anchor_record.get("error_code", ""),
        "boundary": slice_obj.boundary,
        "rotation_truncated": slice_obj.rotation_truncated,
        "truncated_summary": slice_obj.truncated_summary,
        "end_mismatches": slice_obj.end_mismatches,
    }


def build_advisory_for_success_close(op_id: str) -> Optional[Dict[str, Any]]:
    """CP3 item 4: called from execution.py's success-close path.

    FAIL-OPEN CONTRACT: this function must NEVER raise -- any exception
    anywhere in the pipeline is caught, logged, and turned into `None` so a
    diagnostic-report bug can never break the run_module success path
    (mirrors the CP1 offered.json fail-open discipline).

    Finds the turn containing the just-closed (`ok`) op `op_id`; if that
    turn contains an earlier reportable failure (spec section 6.1) -- i.e.
    the workaround-taken signal from section 6.2 -- and the underlying
    signature is not dedupe-suppressed (section 6.3/6.4, honoring
    report_offers_enabled), builds a full report bundle and records the
    offer. Returns None (nothing attached) in every other case.
    """
    try:
        if not bool(config_get(REPORT_OFFERS_ENABLED_KEY, REPORT_OFFERS_ENABLED_DEFAULT)):
            return None

        log_dir = get_log_dir()
        all_records = _load_jsonl_records(log_dir)
        if not all_records:
            return None

        groups = group_records_by_intent(all_records)
        turn = next(
            (g for g in groups if any(r.get("op_id") == op_id for r in g)), None
        )
        if not turn:
            return None
        if not triggers.find_reportable_closes(turn):
            return None

        session_log_path = get_current_session_log_path()
        if session_log_path is None:
            return None

        bundle = prepare_report_bundle(
            all_records,
            session_log_path,
            anchor_op_id=op_id,
            offer_gate=offered_store.should_offer,
        )
        if bundle is None:
            return None

        offered_store.record_offer(bundle["signature"], bundle.get("error_code", ""))

        return {
            "signature": bundle["signature"],
            "title": bundle["title"],
            "summary": bundle["summary"],
            "report_path": bundle["report_path"],
            "transports": bundle["transports"],
            "likely_contains_lexical_data": bundle["likely_contains_lexical_data"],
            "error_code": bundle.get("error_code", ""),
        }
    except Exception:
        try:
            logger = get_operations_logger()
            if logger:
                logger.warning(
                    f"[diagnostic-report] advisory build failed for op_id={op_id!r}; "
                    f"failing open (no advisory attached)",
                    exc_info=True,
                )
        except Exception:
            pass
        return None


async def handle_prepare_report(args) -> list:
    """`flextools_prepare_report` tool handler (spec section 10)."""
    args = args if isinstance(args, dict) else args.model_dump()
    op_id = args.get("op_id")
    op_ids = args.get("op_ids")
    steps_back = args.get("steps_back")
    include_from_op_id = args.get("include_from_op_id")

    try:
        log_dir = get_log_dir()
        all_records = _load_jsonl_records(log_dir)
    except Exception as exc:
        return error_response(
            "server_state_error",
            f"Failed to load operations.jsonl: {exc}",
        )

    if not all_records:
        return error_response(
            "server_state_error",
            "No operations recorded yet -- run flextools_run_module at least once "
            "before requesting a diagnostic report.",
        )

    session_log_path = get_current_session_log_path()
    if session_log_path is None:
        return error_response(
            "server_state_error",
            "No active session log found -- call flextools_start first.",
        )

    try:
        bundle = prepare_report_bundle(
            all_records,
            session_log_path,
            op_ids=op_ids,
            anchor_op_id=op_id,
            steps_back=steps_back,
            include_from_op_id=include_from_op_id,
        )
    except Exception as exc:
        logger = get_operations_logger()
        if logger:
            logger.error(f"[diagnostic-report] prepare_report failed: {exc}", exc_info=True)
        return error_response("server_state_error", f"Failed to prepare report: {exc}")

    if bundle is None:  # defensive; offer_gate is None on this path
        return error_response("server_state_error", "Failed to prepare report.")

    data = build_response_with_context({"status": "ok", **bundle})
    return json_response(data)
