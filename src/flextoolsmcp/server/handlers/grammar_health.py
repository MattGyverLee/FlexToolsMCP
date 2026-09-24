#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_grammar_health: pure-LCM static grammar scan (parser-check CP1, T020).

Authority: specs/parser-check/contracts/flextools_grammar_health.md (response
shape, forbidden-response rules, `checks_skipped` semantics, the
`next_step: null` rule and the error table), SPEC.md 9.5.2-9.5.5, 9.5.7 and
3.1, research.md D1 + D11.

This module is pure COMPOSITION, in the same sense `diagnostic_health.py` is:
it introduces no LCM reading of its own. The ten SPEC 9.5.4 rows live in
`server/scan/grammar_scan_module.py`; this handler only

  1. resolves the project name (falling back to the session, as every other
     project-touching tool does),
  2. hands the scan to the T030 subprocess seam
     (`handlers/execution.run_scan_module`), and
  3. turns the raw, plain-data result into the contract's response --
     ordering findings by the 9.5.4 row order, capping `objects[]` at
     `limit`, and validating through the closed `GrammarHealthFinding` /
     `FoundObject` models.

CP1 boundary (research D1, asserted by tests/test_cp1_boundary.py and
tests/test_grammar_health.py::TestCP1BoundaryOnTheHandler):

  - The MCP server process NEVER opens a FieldWorks project and never opens
    an LCM cache. The scan runs in the generated-module subprocess; this
    handler only reads the JSON that comes back over the
    `===FLEXTOOLS_USER_RESULT===` sentinel.
  - No parser is constructed, no word is parsed, no grammar is loaded.
  - `check_active_parser` is deliberately NOT called. Per the contract's
    error table, `parser_engine_mismatch` is "Never" for this tool: it runs
    no parser and reads no engine-specific object, so refusing on engine
    would be a gate the spec does not ask for (SPEC 10.2 names only
    `try_word`, `parse_text` and `parse_sandbox` as callers of that helper).

Response discipline (SPEC 9.5.3, 9.5.7, research D7): no scalar score at any
nesting level, no ordering by magnitude, no total, no verdict wording. The
first two are structural here -- `GrammarHealthFinding` is `extra="forbid"`
so a score cannot be attached, and `_assemble_findings` has exactly one
sort, on `spec_row`, which never sees `count` at all.
"""

from typing import Any, Dict, List, Optional, Tuple

from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps
from ..models import FoundObject, GrammarHealthFinding

try:
    from ...response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

# json_response / session_state come from the shared kernel helper; the other
# two returned slots are unused here and intentionally discarded.
json_response, session_state, _get_log_dir, _get_api_index = safe_import_kernel_deps()


# ---------------------------------------------------------------------------
# Scan wiring. The subprocess seam is addressed by NAME, not by import of the
# scan module itself -- importing `grammar_scan_module` into this process
# would put a module whose whole job is reading LCM objects in the one
# process that must never hold a project open. `run_scan_module` passes these
# two strings through to the generated runner, which imports them in the
# child (research D11: the child is a plain CPython process started from
# `sys.executable`, so a first-party import resolves there unconditionally).
# ---------------------------------------------------------------------------

SCAN_MODULE_IMPORT_PATH = "flextoolsmcp.server.scan.grammar_scan_module"
SCAN_FUNCTION_NAME = "run_grammar_scan"

# Matches GrammarHealthInput.limit's own default (server/models.py) and the
# scan module's DEFAULT_OBJECT_CAP. Kept as a named constant so the three
# stay visibly tied together rather than three loose 20s.
DEFAULT_OBJECT_LIMIT = 20

# The scan opens the project read-only and walks grammar objects only; 300s
# is `run_scan_module`'s own default and is generous for a pure-LCM pass.
SCAN_TIMEOUT_SECONDS = 300


# ---------------------------------------------------------------------------
# Pure assembly seam (tests/test_grammar_health.py drives this directly).
# ---------------------------------------------------------------------------

def _row_order_key(raw: Dict[str, Any]) -> Tuple[int, int]:
    """Sort key implementing the SPEC 9.5.4 row order, and nothing else.

    `count` is deliberately absent from this key. The 9.5.4 order is
    "highest measured yield first", fixed at authoring time -- so a run
    whose magnitudes are permuted must come back in byte-identical order
    (SPEC 9.5.7 / research D7: "the first finding is the worst one" is the
    exact inference a scalar score would smuggle back in).

    `spec_row: null` marks the three 9.5.1 causes PanGloss does not cover;
    they sort last, as a fixed position rather than a magnitude-dependent
    one.
    """
    row = raw.get("spec_row")
    if row is None:
        return (1, 0)
    return (0, int(row))


def _assemble_findings(
    raw_findings: List[Dict[str, Any]],
    limit: int = DEFAULT_OBJECT_LIMIT,
) -> List[GrammarHealthFinding]:
    """Turn the scan's plain dicts into ordered, capped, closed models.

    The scan module cannot build these models itself: `scan/__init__.py`
    forbids it from importing `flextoolsmcp.server.*`, so it returns plain
    data only. This is the seam where that plain data becomes the contract's
    response.

    Args:
        raw_findings: per-check dicts as emitted by `run_grammar_scan`
            (`check_id`, `spec_row`, `count`, `measured`, `evidence_basis`,
            `objects`).
        limit: per-check cap on `objects[]` (SPEC S7: responses summarise,
            never inline the full set). `count` is untouched by the cap --
            it always reports the true number of objects found, never
            `len(objects)`.

    Returns:
        `GrammarHealthFinding`s in SPEC 9.5.4 row order.

    Raises:
        pydantic.ValidationError: if a raw finding carries a field the closed
            model does not declare (including any severity proxy). Loud by
            design -- data-model.md's "a typo'd field fails loudly rather
            than silently vanishing".
    """
    if not raw_findings:
        return []

    effective_limit = max(0, int(limit))

    # `sorted` is stable, so rows that share a spec_row (3a/3b, 7a/7b) keep
    # the order the scan emitted them in -- no tie-break on count is needed
    # or wanted.
    ordered = sorted(raw_findings, key=_row_order_key)

    assembled: List[GrammarHealthFinding] = []
    for raw in ordered:
        raw_objects = raw.get("objects") or []
        # Slice only -- no re-sort. objects[] order is scan order.
        capped = [
            obj if isinstance(obj, FoundObject) else FoundObject(**obj)
            for obj in raw_objects[:effective_limit]
        ]
        fields = {k: v for k, v in raw.items() if k != "objects"}
        assembled.append(GrammarHealthFinding(objects=capped, **fields))
    return assembled


def _select_requested(
    check_ids: Optional[List[str]],
    checks_run: List[str],
    checks_skipped: List[Dict[str, str]],
    raw_findings: List[Dict[str, Any]],
) -> Tuple[List[str], List[Dict[str, str]], List[Dict[str, Any]]]:
    """Apply `GrammarHealthInput.checks` to a completed scan result.

    `run_grammar_scan(project)` takes exactly one argument -- the seam's
    fixed "module code" calls it with the project and nothing else -- so the
    restriction is applied here, on the way out, rather than pushed into the
    scan. The scan is a single pure-LCM pass whose cost is dominated by
    opening the project, so filtering after the fact costs nothing a
    per-check argument would have saved.

    `None` (the default) means "all implemented checks" and is returned
    untouched.
    """
    if check_ids is None:
        return checks_run, checks_skipped, raw_findings

    wanted = set(check_ids)
    return (
        [cid for cid in checks_run if cid in wanted],
        [entry for entry in checks_skipped if entry.get("check_id") in wanted],
        [f for f in raw_findings if f.get("check_id") in wanted],
    )


# ---------------------------------------------------------------------------
# Tool entry point.
# ---------------------------------------------------------------------------

async def handle_flextools_grammar_health(args: dict) -> List[TextContent]:
    """Run the SPEC 9.5.4 grammar scan and return its findings.

    Read-only: the project is opened `writeEnabled=False` in the subprocess
    and left untouched. Nothing here opens a project, a cache, or a parser in
    the MCP server process.

    Args:
        args: validated `GrammarHealthInput` dump -- `project_name`
            (optional; falls back to the session), `checks` (optional
            restriction to named check_ids), `limit` (per-check `objects[]`
            cap, default 20).

    Returns:
        The contract response (`checks_run`, `checks_skipped`, `findings`,
        `next_step: null`), or a reused project/runtime error envelope.
    """
    # Imported here rather than at module scope: `handlers/execution.py` is a
    # heavy module, and this keeps the import graph of the grammar-health
    # handler (and of anything that only wants `_assemble_findings`) small.
    try:
        from .execution import (
            _available_projects_payload,
            _diagnose_project_open_error,
            run_scan_module,
        )
    except (ImportError, ValueError):
        from server.handlers.execution import (
            _available_projects_payload,
            _diagnose_project_open_error,
            run_scan_module,
        )

    project_name = args.get("project_name") or session_state.get_project()
    check_ids = args.get("checks")
    limit = args.get("limit")
    if limit is None:
        limit = DEFAULT_OBJECT_LIMIT

    if not project_name:
        return error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or provide it directly.",
            session=session_state.summary(),
            **_available_projects_payload(),
        )

    # Fuzzy resolution, same precedent as handle_run_module: autocorrect
    # case/whitespace-only typos, and return project_not_found (with
    # suggestions) for anything bigger -- unchanged from the existing
    # contract, per this tool's error table.
    try:
        from ..project_discovery import resolve_or_explain
    except (ImportError, ValueError):
        from server.project_discovery import resolve_or_explain
    resolved, resolve_err = resolve_or_explain(project_name)
    if resolve_err:
        return error_response(
            resolve_err["error_code"],
            resolve_err["message"],
            suggestions=resolve_err["suggestions"],
            reason=resolve_err["reason"],
            hint=resolve_err["hint"],
            session=session_state.summary(),
        )
    if resolved:
        try:
            from ...project_adoption import adopt_resolved_project
        except ImportError:
            from project_adoption import adopt_resolved_project
        project_name = adopt_resolved_project(
            session_state,
            resolved,
            log_context="flextools_grammar_health",
        )

    scan_result = await run_scan_module(
        module_import_path=SCAN_MODULE_IMPORT_PATH,
        function_name=SCAN_FUNCTION_NAME,
        project_name=project_name,
        write_enabled=False,
        timeout_seconds=SCAN_TIMEOUT_SECONDS,
    )

    if not scan_result.get("success"):
        return _scan_failure_response(
            scan_result, project_name, _diagnose_project_open_error
        )

    payload = scan_result.get("findings")
    if not isinstance(payload, dict):
        # `run_scan_module` already separates "never ran" from "ran and found
        # nothing"; this is the remaining shape failure -- the scan returned
        # something that is not the {checks_run, checks_skipped, findings}
        # envelope. Surfaced, never coerced into an empty result: a silently
        # empty response reads as "your grammar is clean", which is the SPEC
        # 8.4 failure applied to our own surface.
        return error_response(
            "runtime_error",
            (
                "The grammar scan returned an unexpected payload shape "
                "(expected an object with checks_run / checks_skipped / findings, "
                "got {}).".format(type(payload).__name__)
            ),
            error_type="MalformedScanPayload",
            stderr=scan_result.get("stderr"),
            exit_code=scan_result.get("returncode"),
        )

    checks_run, checks_skipped, raw_findings = _select_requested(
        check_ids,
        list(payload.get("checks_run") or []),
        # Passed through faithfully rather than hardcoded empty: every
        # T016-gated sub-check came back CONFIRMED (research D9), so the list
        # ships empty today, but a check that later has to be skipped must be
        # NAMED here, never silently omitted (contract, `checks_skipped`).
        list(payload.get("checks_skipped") or []),
        list(payload.get("findings") or []),
    )

    try:
        findings = _assemble_findings(raw_findings, limit=limit)
    except Exception as exc:
        return error_response(
            "runtime_error",
            "The grammar scan produced a finding this server could not validate: {}".format(exc),
            error_type=type(exc).__name__,
            stderr=scan_result.get("stderr"),
            exit_code=scan_result.get("returncode"),
        )

    result: Dict[str, Any] = {
        "status": "ok",
        "project": project_name,
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "findings": [f.model_dump() for f in findings],
        # Always null on a direct call. The conditional *proposal* of this
        # scan lives on the parse tools (SPEC 9.5.5) and those ship at CP2,
        # so at CP1 nothing proposes it.
        "next_step": None,
    }

    result = build_response_with_context(result)
    return json_response(result)


def _scan_failure_response(
    scan_result: Dict[str, Any],
    project_name: str,
    diagnose_project_open_error,
) -> List[TextContent]:
    """Map a failed `run_scan_module` result onto an existing error code.

    Project-open failures are routed through `handle_run_module`'s own
    `_diagnose_project_open_error`, so `project_not_found`, `project_locked`,
    `project_drive_unavailable` and `project_path_mismatch` are reused
    UNCHANGED -- same codes, same detail keys, same hints, one implementation.
    Everything else (timeout, missing sentinel, scan-module import failure,
    an exception inside a check) surfaces as the existing `runtime_error`
    code; this tool introduces no new error code.
    """
    raw_error = scan_result.get("error") or "The grammar scan did not complete."
    error_type = scan_result.get("error_type") or "ScanFailed"

    diagnosis = diagnose_project_open_error({"error": raw_error}, project_name)
    if diagnosis:
        detail = dict(diagnosis)
        code = detail.pop("error_code")
        message = detail.pop("message", raw_error)
        return error_response(code, message, **detail)

    return error_response(
        "runtime_error",
        raw_error,
        error_type=error_type,
        stderr=scan_result.get("stderr"),
        exit_code=scan_result.get("returncode"),
    )
