#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Execution handler functions for FlexToolsMCP.

These handlers manage module and operation execution:
- start_module: Interactive wizard to create FlexTools modules
- run_module: Execute code against a FieldWorks project. Accepts both
  lightweight ad-hoc snippets (bare code, no Main) and full FlexTools
  modules (Main + docs + FlexToolsModule binding) in the same `code`
  parameter. The earlier separate run_operation tool was consolidated
  into this one.
- get_operation_logs: View execution logs and pattern recommendations
"""

import json
import asyncio
import sys
import subprocess
import tempfile
from datetime import datetime
import os
import ast
import hashlib
import heapq
import time
import itertools
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from mcp.types import TextContent

from ._import_helper import (
    safe_import_kernel_deps,
    safe_import_session_state,
    safe_import_logging_helpers,
)

# Import async subprocess helper with fallback
try:
    from ..subprocess_helpers import run_script_async
except ImportError:
    from server.subprocess_helpers import run_script_async

# Import kernel dependencies with fallback
json_response, session_state, get_log_dir, get_api_index = safe_import_kernel_deps()
_, get_operations_logger = safe_import_logging_helpers()
SessionState = safe_import_session_state()

try:
    from ..kernel import get_pattern_tracker, get_project_write_lock
except ImportError:
    from server.kernel import get_pattern_tracker, get_project_write_lock

# Skeleton storage closet (issue #24): persist helper defs from successful ops.
try:
    from .. import skeleton_storage
except ImportError:
    from server import skeleton_storage

# Import validators with fallback
try:
    from ..validators import (
        detect_cud_operations, detect_polymorphic_error, detect_undefined_variables,
        detect_missing_operations_imports, detect_wrong_library_imports, format_cud_warning,
        certify_script_readonly, get_unprotected_write_guidance, detect_casting_needs, validate_server_state,
        detect_unknown_attribute_error, detect_invalid_project_chains,
        detect_partial_module_structure, detect_undiscovered_entities,
        detect_candidate_entities, extract_python_did_you_mean,
        detect_overload_resolution_error,
        _collect_all_imported_names, _accessor_to_ops_map,
        annotate_properties_with_casting, build_casting_notes,
    )
except ImportError:
    from server.validators import (
        detect_cud_operations, detect_polymorphic_error, detect_undefined_variables,
        detect_missing_operations_imports, detect_wrong_library_imports, format_cud_warning,
        certify_script_readonly, get_unprotected_write_guidance, detect_casting_needs, validate_server_state,
        detect_unknown_attribute_error, detect_invalid_project_chains,
        detect_partial_module_structure, detect_undiscovered_entities,
        detect_candidate_entities, extract_python_did_you_mean,
        detect_overload_resolution_error,
        _collect_all_imported_names, _accessor_to_ops_map,
        annotate_properties_with_casting, build_casting_notes,
    )

# Import response utilities and HeadlessReport with fallback
try:
    from ...response_utils import build_response_with_context, error_response
    from ..headless_report import HeadlessReport
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response
    from server.headless_report import HeadlessReport

# Import response field constants
from ..response_keys import (
    KEY_STATUS, KEY_ERROR, KEY_MESSAGE, KEY_NEEDS_INPUT, KEY_COMPLETE,
    KEY_MODULE_NAME, KEY_SYNOPSIS, KEY_API_TARGET, KEY_INCLUDE_DRY_RUN,
    KEY_MODIFIES_DB, KEY_QUESTIONS, KEY_QUESTION, KEY_EXAMPLE, KEY_PROVIDED,
    KEY_SESSION, KEY_SUMMARY, KEY_WARNINGS, KEY_RAW_OUTPUT, KEY_STDERR,
    KEY_EXIT_CODE, KEY_WRITE_CERTIFICATION, KEY_IS_CERTIFIED_READONLY,
    KEY_MUTATING_CALLS_DETECTED, KEY_CASTING_ISSUES, KEY_SEVERITY,
    KEY_HAS_CASTING_ISSUES, KEY_WHY, KEY_APPLIES_TO, KEY_HOW_TO_FIX,
    KEY_SUGGESTIONS, KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED,
    KEY_MESSAGES, KEY_TEMPLATE, KEY_CONFIDENCE, KEY_NEXT_STEPS,
    KEY_AUTO_FIXES_APPLIED, KEY_AUTO_FIX_NOTE,
    KEY_AUTO_DISCOVERED, KEY_INLINE_DISCOVERY, KEY_DISCOVERY_NOTE,
    KEY_DIAGNOSTIC_REPORT,
    KEY_DISCOVERY_REDIRECT, KEY_CAPABILITY_SUGGESTIONS, KEY_EXECUTED,
)

# Issue #46: auto-fix config
try:
    from ...config import config_get, AUTO_FIX_ENABLED_KEY, AUTO_FIX_ENABLED_DEFAULT
except (ImportError, ValueError):
    from config import config_get, AUTO_FIX_ENABLED_KEY, AUTO_FIX_ENABLED_DEFAULT

# Issue #50: structured JSONL telemetry (one line per op, alongside prose .log)
try:
    from .op_telemetry import _stash_op_start, _write_jsonl_line, compute_jsonl_statistics
except ImportError:
    from server.handlers.op_telemetry import _stash_op_start, _write_jsonl_line, compute_jsonl_statistics

# Diagnostic-report CP2: precision casting-recurrence signature (deferred
# cycle-2 QC P1). Pure function, no transmission -- see
# server/diagnostic/__init__.py for the no-transmission guard this import
# reaches into (one-way: execution.py -> diagnostic, never the reverse).
try:
    from ..diagnostic.triggers import compute_casting_signature
except ImportError:
    from server.diagnostic.triggers import compute_casting_signature

# Diagnostic-report CP3: success-close advisory attach (spec sections 6.2,
# 6.5, 10). One-way dependency (execution.py -> handlers.diagnostic_report),
# fail-open by contract -- see build_advisory_for_success_close()'s docstring.
try:
    from .diagnostic_report import build_advisory_for_success_close
except ImportError:
    from server.handlers.diagnostic_report import build_advisory_for_success_close

# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
# Error codes (execution-specific)
ERROR_PROJECT_NAME_REQUIRED = "project_name_required"
ERROR_CASTING_ISSUES = "casting_issues_detected"
ERROR_API_DISCOVERY_REQUIRED = "api_discovery_required"
ERROR_UNDEFINED_VARIABLES = "undefined_variables"
ERROR_MISSING_IMPORTS = "missing_imports"
ERROR_WRONG_LIBRARY = "wrong_library_imports"
ERROR_UNPROTECTED_CODE = "unprotected_code"


def _validate_api_mode(api_mode: str) -> Tuple[bool, str]:
    """Validate that the requested API mode libraries are properly installed.

    Args:
        api_mode: One of 'flexlibs_stable', 'flexicon', 'liblcm'

    Returns:
        (is_valid, error_message)
    """
    if api_mode == "flexicon":
        try:
            import flexicon  # type: ignore
            # Check version is available (flexicon uses 'version' not '__version__')
            if not hasattr(flexicon, 'version') and not hasattr(flexicon, '__version__'):
                return False, "flexicon missing version info"
            return True, ""
        except ImportError as e:
            return False, f"flexicon not found: {e}"

    elif api_mode == "flexlibs_stable":
        try:
            import flexlibs  # type: ignore
            return True, ""
        except ImportError as e:
            return False, f"flexlibs not found: {e}"

    elif api_mode == "liblcm":
        # LibLCM is optional, validated at runtime
        return True, ""

    return False, f"Unknown API mode: {api_mode}"


def _get_casting_helpers_code(injection_tier: str = "full", helpers_needed: Optional[set] = None) -> str:
    """Generate casting helpers code based on injection tier.

    Uses HELPER_FUNCTION_DEFS from constants to avoid duplication.

    Args:
        injection_tier: 'none' | 'minimal' | 'full'
        helpers_needed: Set of helper names for 'minimal' tier

    Returns:
        Python code string with helper definitions (or empty if tier='none')
    """
    try:
        from ...casting_helpers import HELPER_FUNCTION_DEFS
    except ImportError:
        from casting_helpers import HELPER_FUNCTION_DEFS

    if injection_tier == "none":
        return ""

    if injection_tier == "minimal" and helpers_needed:
        # Only import what's needed
        helper_names = ", ".join(sorted(helpers_needed))
        return f"""
# Auto-injected: Minimal casting helpers for polymorphic types (three-tier strategy, tier 2)
try:
    from casting_helpers import {helper_names}
except ImportError:
    # Fallback: Define only needed helpers if module not available
{HELPER_FUNCTION_DEFS}
"""

    # Full injection (tier='full' or defensive fallback)
    return f"""
# Auto-injected: Safe casting helpers for polymorphic types (three-tier strategy, tier 3 - full)
try:
    from casting_helpers import safe_get_property, smart_cast, cast_or_default, get_headword, get_lexeme_form
except ImportError:
    # Fallback: Define all helpers if module not available
{HELPER_FUNCTION_DEFS}
"""


def _get_api_mode_imports(api_mode: str, helpers_needed: Optional[set] = None, injection_tier: str = "full") -> str:
    """Generate imports and namespace dict for a given API mode.

    Args:
        api_mode: One of 'flexlibs_stable', 'flexicon', 'liblcm'
        helpers_needed: Optional set of specific helper names to inject (e.g., {'get_headword'})
        injection_tier: 'none' | 'minimal' | 'full'
            - none: Don't inject casting helpers (code pre-flighted, safe)
            - minimal: Only inject helpers in helpers_needed set
            - full: Inject full suite of helpers (defensive mode)

    Returns:
        imports_code: Python code string with imports and helpers

    Raises:
        ValueError: If API mode is invalid or required libraries are not installed
    """
    if helpers_needed is None:
        helpers_needed = set()

    # Gate #1: Validate API mode is valid
    is_valid, error_msg = _validate_api_mode(api_mode)
    if not is_valid:
        raise ValueError(f"API mode validation failed: {error_msg}")

    # Base imports per API mode
    BASE_IMPORTS = {
        "flexlibs_stable": "from flexlibs import FLExInitialize, FLExCleanup, FLExProject",
        "flexicon": "from flexicon import FLExInitialize, FLExCleanup, FLExProject",
        "liblcm": """import clr
clr.AddReference('SIL.LCModel')
from SIL.LCModel import *
from SIL.LCModel.Core.WritingSystems import *

def FLExInitialize():
    \"\"\"Initialize LibLCM backend.\"\"\"
    pass

def FLExCleanup():
    \"\"\"Cleanup LibLCM backend.\"\"\"
    pass

class FLExProject:
    \"\"\"Wrapper for direct LibLCM project access.\"\"\"
    def __init__(self):
        self._backend = None
        self._cache = None

    def OpenProject(self, projectName, writeEnabled=False):
        \"\"\"Open project using LibLCM directly.\"\"\"
        try:
            from SIL.LCModel import LcmCache
            self._cache = LcmCache.CreateCacheForNewLcmProject(projectName, "en", "en", "en",
                                                               writeSystemType=LcmWriteSystemType.kDefault)
            self._backend = self._cache.ServiceLocator
        except Exception as e:
            raise RuntimeError(f"Failed to open LibLCM project: {e}")

    def CloseProject(self):
        \"\"\"Close project.\"\"\"
        if self._cache:
            self._cache.Dispose()

    def __getattr__(self, name):
        \"\"\"Delegate unknown attributes to backend.\"\"\"
        if self._backend:
            return getattr(self._backend, name)
        raise AttributeError(f"Project not initialized: {name}")
""",
    }

    if api_mode not in BASE_IMPORTS:
        raise ValueError(f"Unknown API mode: {api_mode}")

    # Get base imports and append casting helpers (single shared logic)
    imports = BASE_IMPORTS[api_mode]
    casting_helpers = _get_casting_helpers_code(injection_tier, helpers_needed)
    imports += casting_helpers

    return imports


# ---------------------------------------------------------------------------
# Operation logging: per-call traceable block in the .log file.
# Each handle_run_module invocation produces a self-contained block bookended
# by `=== Operation #N Start (op-id) ===` / `=== Operation #N End ===` so a
# user pasting a slice of the log can be cross-referenced to the response
# returned to the LLM (which carries the same op_id).
# ---------------------------------------------------------------------------

_op_counter = itertools.count(1)


def _next_op_id() -> Tuple[int, str]:
    """Return (sequence_number, short_id) for the next operation.

    The short id is timestamp-based so it stays unique across server restarts,
    which is important when correlating a .log block with a stale response in
    a bug report. The sequence number is for human-skimmable ordering within
    a single session.
    """
    seq = next(_op_counter)
    # 9-char timestamp suffix (HHMMSS + ms) is short enough to grep, long enough
    # to be unique across the rare same-second double-call.
    ts = time.strftime("%H%M%S") + f"{int(time.time() * 1000) % 1000:03d}"
    return seq, f"op-{ts}-{seq:03d}"


def _code_fingerprint(code: str) -> Dict[str, Any]:
    """Compute a short digest for change-detection between near-identical attempts.

    Returns the first 12 hex chars of SHA256 plus byte/line counts -- enough to
    eyeball "is this the same code with a one-line tweak" across consecutive
    operations without diffing 50-line code blocks.
    """
    raw = code.encode("utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()[:12]
    return {
        "sha256_short": digest,
        "bytes": len(raw),
        "lines": code.count("\n") + (0 if code.endswith("\n") else 1),
    }


def _classify_code_source(code: str, code_tree: Optional[ast.AST]) -> str:
    """Identify whether `code` is a bare snippet, partial module, or full module.

    Item 8 in the logging plan: when the runner accepts both shapes, the .log
    should record which one it just executed so a "module saves but snippet
    doesn't" issue is visible without re-reading the code.
    """
    if code_tree is None:
        return "unknown"
    if not isinstance(code_tree, ast.Module):
        return "unknown"
    has_main = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "Main"
        for n in code_tree.body
    )
    has_binding = any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "FlexToolsModule" for t in n.targets)
        for n in code_tree.body
    )
    if has_main and has_binding:
        return "full_module"
    if has_main:
        return "partial_module"
    return "bare_snippet"


def _log_operation_start(
    op_id: str,
    seq: int,
    project_name: str,
    write_enabled: bool,
    code: str,
    source_kind: str,
    casting_check: Optional[Dict[str, Any]] = None,
    injection_tier: Optional[str] = None,
    helpers_needed: Optional[set] = None,
    user_intent: Optional[str] = None,
    user_request: Optional[str] = None,
) -> None:
    """Emit the opening block of a per-operation log entry.

    Logged unconditionally as the *first* thing in handle_run_module so even
    operations rejected by pre-flight validators still appear in the log --
    the user explicitly wants every attempted call to be visible.

    `user_intent` (issue #18) is a one-line paraphrase of the human request,
    supplied by the LLM. We log it (or "(not provided)") so post-mortem
    readers know what the op was TRYING to accomplish without scrolling back
    through the conversation.

    `user_request` (diagnostic-report feature, spec section 4) is the
    VERBATIM human request text -- Claude's compression-free source, not a
    paraphrase. It is optional and, when absent, falls back to `user_intent`
    for both the logged line and the stashed/JSONL value (same "(not
    provided)" idiom already used for user_intent alone).
    """
    logger = get_operations_logger()
    fp = _code_fingerprint(code)
    logger.info(f"=== Operation #{seq} Start ({op_id}) ===")
    logger.info(f"Project:         {project_name}")
    logger.info(f"Write enabled:   {write_enabled}")
    logger.info(f"Source kind:     {source_kind}")
    intent_display = (user_intent or "").strip() or "(not provided)"
    logger.info(f"User intent:     {intent_display}")
    # Effective user_request: explicit value if given, else fall back to
    # user_intent (spec section 4: "absent user_request falls back to
    # user_intent, same as user_intent already falls back to '(not provided)'").
    effective_user_request = (user_request or "").strip() or (user_intent or "").strip()
    request_display = effective_user_request or "(not provided)"
    logger.info(f"User request:    {request_display}")
    logger.info(
        f"Code fingerprint: sha256={fp['sha256_short']} bytes={fp['bytes']} lines={fp['lines']}"
    )

    # Issue #50: stash metadata so the close functions can emit a JSONL line
    # without receiving these fields as extra parameters.  The stash is drained
    # (pop) exactly once, by whichever close function runs first.
    _raw_bytes = code.encode("utf-8", errors="replace")
    _full_sha256 = hashlib.sha256(_raw_bytes).hexdigest()
    _stash_op_start(
        op_id=op_id,
        project=project_name,
        write_enabled=write_enabled,
        source_kind=source_kind,
        user_intent=user_intent,
        user_request=effective_user_request,
        code_sha256=_full_sha256,
        code_bytes=fp["bytes"],
        code_lines=fp["lines"],
    )

    if casting_check is not None:
        issue_count = len(casting_check.get("casting_issues") or [])
        tier = injection_tier or casting_check.get("injection_tier", "?")
        helpers = sorted(helpers_needed) if helpers_needed else sorted(
            casting_check.get("helpers_needed") or []
        )
        logger.info(
            f"Preflight casting: issues={issue_count} tier={tier} helpers={helpers or '[]'}"
        )
        # Per-issue detail (DEBUG) so the .log captures WHY the helper was injected.
        for issue in (casting_check.get("casting_issues") or [])[:10]:
            logger.debug(
                f"  casting: line={issue.get('line')} property={issue.get('property')} "
                f"pattern={issue.get('pattern','')[:80]!r}"
            )

    logger.debug("Code:")
    for code_line in code.split("\n"):
        logger.debug(code_line)


def _classify_message_level(m: Dict[str, Any]) -> str:
    """Return one of "INFO", "WARNING", "ERROR", or "OTHER" for a raw
    runner message dict. Accepts both the string `type` shape and the older
    int `msgType` shape so legacy payloads still classify correctly."""
    INT_TO_LABEL = {0: "INFO", 1: "WARNING", 2: "ERROR", 3: "BLANK"}
    raw = m.get("type", m.get("msgType"))
    if isinstance(raw, int):
        label = INT_TO_LABEL.get(raw, "")
    else:
        label = (raw or "").upper()
    return label if label in ("INFO", "WARNING", "ERROR") else "OTHER"


def _cap_info_messages(
    messages: List[Dict[str, Any]],
    cap: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Cap the number of report.Info entries returned to the LLM (issue #25).

    A single run_module call can emit hundreds of info messages -- 785 in
    one of Dennis's sessions -- which floods the response context with no
    semantic gain. We keep the first ``cap // 2`` info messages and the
    last ``cap // 2`` and drop the middle, leaving a synthetic INFO marker
    in between so the LLM can see how many were elided.

    - Warnings and errors are NEVER capped: they always pass through intact,
      preserving their original positions relative to the surviving infos.
    - Pass ``cap == 0`` to disable the cap (returns ``messages`` unchanged).
    - When the info count is at-or-below ``cap``, messages are returned as-is.

    Returns ``(capped_messages, info_stats)`` where info_stats is::

        {
            "original_info_count": <int>,
            "kept_info_count":     <int>,
            "truncated":           <bool>,
            "cap":                 <int>,
        }

    The caller logs info_stats on the op-Start block and (optionally)
    attaches it to the response payload so the LLM can see whether output
    was trimmed.
    """
    if not messages:
        return messages, {
            "original_info_count": 0,
            "kept_info_count": 0,
            "truncated": False,
            "cap": cap,
        }

    # Index every entry so we can preserve original order on reassembly.
    info_indices = [
        i for i, m in enumerate(messages)
        if _classify_message_level(m) == "INFO"
    ]
    original_info_count = len(info_indices)

    # cap == 0 means "no cap" -- pass through.
    # Likewise when we're already under the cap.
    if cap <= 0 or original_info_count <= cap:
        return messages, {
            "original_info_count": original_info_count,
            "kept_info_count": original_info_count,
            "truncated": False,
            "cap": cap,
        }

    head_count = cap // 2
    tail_count = cap - head_count  # honors odd cap values
    keep_head = set(info_indices[:head_count])
    keep_tail = set(info_indices[-tail_count:]) if tail_count else set()
    drop_indices = set(info_indices[head_count:-tail_count]) if tail_count \
        else set(info_indices[head_count:])
    dropped_count = len(drop_indices)

    # Truncation marker -- inserted at the position of the first dropped info
    # so its location in the timeline matches reality.
    first_drop_pos = min(drop_indices) if drop_indices else None
    marker = {
        "type": "INFO",
        "message": (
            f"... [{dropped_count} additional info messages truncated; "
            f"pass max_info_messages=0 to disable cap] ..."
        ),
        "ref": None,
    }

    capped: List[Dict[str, Any]] = []
    inserted_marker = False
    for i, m in enumerate(messages):
        if i in drop_indices:
            if not inserted_marker and i == first_drop_pos:
                capped.append(marker)
                inserted_marker = True
            continue
        capped.append(m)

    return capped, {
        "original_info_count": original_info_count,
        "kept_info_count": head_count + tail_count,
        "truncated": True,
        "cap": cap,
    }


def _log_report_messages(messages: List[Dict[str, Any]], include_info: bool) -> None:
    """Spill captured report.* messages into the log.

    User wants: warnings/errors logged always, info logged only on failure
    (to keep success-path .log noise low while preserving debugging context
    when something breaks). The runner's SimpleReporter encodes the level as
    the string "INFO" / "WARNING" / "ERROR" / "BLANK" / "DEBUG" in the `type`
    field; older payloads may use the int "msgType" instead, so we accept both.
    """
    if not messages:
        return
    logger = get_operations_logger()
    INT_TO_LABEL = {0: "INFO", 1: "WARNING", 2: "ERROR", 3: "BLANK"}

    logged_any = False
    for m in messages:
        raw_type = m.get("type", m.get("msgType"))
        if isinstance(raw_type, int):
            label = INT_TO_LABEL.get(raw_type)
        else:
            label = (raw_type or "").upper() or None
        if label not in ("INFO", "WARNING", "ERROR"):
            continue
        if label == "INFO" and not include_info:
            continue
        text = m.get("message", m.get("msg", m.get("text", ""))) or ""
        ref = m.get("ref")
        if not logged_any:
            logger.debug("Report messages:")
            logged_any = True
        suffix = f"  ref={ref}" if ref else ""
        # Route warnings/errors to their matching log levels so the existing
        # errors_only filter in handle_get_operation_logs catches them; INFO
        # replays on failure stay at DEBUG -- they're context, not a fault.
        if label == "ERROR":
            logger.error(f"  report.Error: {text}{suffix}")
        elif label == "WARNING":
            logger.warning(f"  report.Warning: {text}{suffix}")
        else:
            logger.debug(f"  report.Info: {text}{suffix}")


def _log_operation_end_success(
    op_id: str,
    seq: int,
    duration_s: float,
    info_count: int,
    warning_count: int,
    error_count: int,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Close a successful operation block."""
    logger = get_operations_logger()
    # Always replay warnings/errors even when overall result was success --
    # report.Warning() doesn't fail the run but the user wants visibility.
    _log_report_messages(messages or [], include_info=False)
    logger.info("[OK] Operation completed successfully")
    logger.info(f"Messages:        {info_count} info, {warning_count} warnings, {error_count} errors")
    logger.info(f"Duration:        {duration_s:.3f}s")
    logger.info(f"=== Operation #{seq} End ({op_id}) ===")

    # Issue #50: emit JSONL line (same code path as prose .log -- cannot diverge)
    _write_jsonl_line(
        op_id=op_id,
        seq=seq,
        outcome="ok",
        duration_s=duration_s,
        error_code=None,
        preflight_gate=None,
        info_count=info_count,
        warning_count=warning_count,
        error_count=error_count,
        assistance_triggered=False,
        log_dir_fn=get_log_dir,
    )


def _log_operation_failure(
    op_id: Optional[str] = None,
    seq: Optional[int] = None,
    duration_s: Optional[float] = None,
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    stderr: Optional[str] = None,
    info_count: int = 0,
    warning_count: int = 0,
    error_count: int = 0,
    messages: Optional[List[Dict[str, Any]]] = None,
    traceback_text: Optional[str] = None,
    polymorphic_hint: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit the [FAIL] / Messages / Operation End block with diagnostic detail.

    On failure we dump *everything* useful for reconstruction:
    - [FAIL] marker, error type, first error line at ERROR (the operation
      genuinely failed; this should surface in standard error filters)
    - polymorphic resolve_property hint at ERROR (it's part of the failure)
    - full traceback at DEBUG (long but only present on failures)
    - stderr tail at DEBUG (subprocess noise)
    - all captured report.* messages including Info (context before the crash)
    - Messages/Duration tally + Operation End marker at INFO (bookkeeping)

    op_id/seq/duration are optional because some early-exception paths in the
    handler don't have them yet -- losing the close marker is still better
    than no log at all.
    """
    logger = get_operations_logger()
    logger.error("[FAIL] Operation failed")
    if error_type:
        logger.error(f"Error type:      {error_type}")
    if error:
        first_line = error.strip().splitlines()[0] if error.strip() else ""
        if len(first_line) > 500:
            first_line = first_line[:500] + "..."
        logger.error(f"Error:           {first_line}")
    if polymorphic_hint and polymorphic_hint.get("is_polymorphic_error"):
        # Issue #22: with #21's inlined rewrite, the preflight casting
        # validator usually catches these BEFORE subprocess launch and
        # returns the rewrite in casting_issues[*].rewrite. By the time we
        # reach this runtime path, the validator missed it -- so point at
        # the inlined-rewrite field for next-attempt recovery, not at an
        # extra resolve_property hop. Logged at INFO because the hint is a
        # recovery breadcrumb, not a failure marker (those are at ERROR via #17).
        logger.info(
            f"Polymorphic hint: object={polymorphic_hint.get('object_type')} "
            f"property={polymorphic_hint.get('property_name')} "
            f"-> resubmit; preflight should now emit casting_issues[*].rewrite "
            f"and casting_issues[*].imports_needed"
        )
    if traceback_text:
        logger.debug("Traceback:")
        for tb_line in traceback_text.rstrip().splitlines():
            logger.debug(f"  {tb_line}")
    if stderr:
        for line in stderr.strip().splitlines()[:20]:
            logger.debug(f"stderr: {line}")
    # On failure, include the info messages too -- they're the context that
    # ran before the break.
    _log_report_messages(messages or [], include_info=True)
    logger.info(f"Messages:        {info_count} info, {warning_count} warnings, {error_count} errors")
    if duration_s is not None:
        logger.info(f"Duration:        {duration_s:.3f}s")
    if seq is not None and op_id is not None:
        logger.info(f"=== Operation #{seq} End ({op_id}) ===")
    else:
        logger.info("=== Operation End ===")

    # Issue #50: emit JSONL line.
    # Timeout is distinguished from generic runtime_fail by error_type:
    #   "TimeoutExpired" -> subprocess.TimeoutExpired catch block
    #   "Timeout"        -> result["timeout"] True path (async runner)
    # Any other error_type maps to "runtime_fail".
    if op_id is not None and seq is not None:
        _is_timeout = (error_type or "").lower() in ("timeout", "timeoutexpired")
        _outcome = "timeout" if _is_timeout else "runtime_fail"
        _write_jsonl_line(
            op_id=op_id,
            seq=seq,
            outcome=_outcome,
            duration_s=duration_s,
            error_code=error_type or "runtime_error",
            preflight_gate=None,
            info_count=info_count,
            warning_count=warning_count,
            error_count=error_count,
            assistance_triggered=False,
            log_dir_fn=get_log_dir,
        )


def _log_preflight_reject(
    op_id: str,
    seq: int,
    duration_s: float,
    reason_code: str,
    detail: str,
    *,
    casting_signature: Optional[str] = None,
) -> None:
    """Close an operation that was rejected by a pre-flight validator.

    Pre-flight rejects never reach the subprocess so they have no traceback /
    stderr / report messages -- just the validator reason. We still emit the
    block so the user sees that the LLM tried something and was blocked.

    The [REJECT] marker, reason code, and detail lines are emitted at WARNING
    because the LLM's submission was blocked (worth surfacing in default-level
    filters); Duration and the Operation End marker stay at INFO as bookkeeping.

    `casting_signature` (diagnostic-report CP2): only meaningful -- and only
    ever passed -- on a `"casting_issues_detected"` reason_code close. See
    `op_telemetry._write_jsonl_line`'s docstring for why this thread exists
    (precision fix for the CP1 casting-recurrence fallback).
    """
    logger = get_operations_logger()
    logger.warning("[REJECT] Pre-flight validation blocked execution")
    logger.warning(f"Reason code:     {reason_code}")
    if detail:
        # Detail can be a multi-line `suggestion` from validators -- keep it.
        for line in detail.strip().splitlines()[:30]:
            logger.warning(f"  {line}")
    logger.info(f"Duration:        {duration_s:.3f}s")
    logger.info(f"=== Operation #{seq} End ({op_id}) ===")

    # Issue #50: emit JSONL line (written here, NOT at each of the ~12 call
    # sites, so prose .log and JSONL can never diverge).
    _write_jsonl_line(
        op_id=op_id,
        seq=seq,
        outcome="preflight_reject",
        duration_s=duration_s,
        error_code=reason_code,
        preflight_gate=reason_code,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=get_log_dir,
        casting_signature=casting_signature,
    )


def _log_discovery_redirect(
    op_id: str,
    seq: int,
    duration_s: float,
    reason: str,
    detail: str,
) -> None:
    """Close an operation that was gently redirected for discovery (issue #80).

    A discovery redirect is NEITHER a success (the code did not run) NOR a
    reject (it is not an error -- the workflow simply needs a discovery step
    first). It gets its own [REDIRECT] .log block and a JSONL line with
    outcome ``"discovery_redirect"`` so telemetry does not miscount it as a
    preflight_reject in the green-rate / rejects-by-code stats. A redirect that
    is later followed by an ``ok`` in the same intent-group still contributes to
    turns-to-green; one that is never resubmitted reads as abandoned -- both
    honest.
    """
    logger = get_operations_logger()
    if logger is not None:
        logger.info("[REDIRECT] Gentle discovery redirect (code not executed)")
        logger.info(f"Reason:          {reason}")
        if detail:
            for line in detail.strip().splitlines()[:20]:
                logger.info(f"  {line}")
        logger.info(f"Duration:        {duration_s:.3f}s")
        logger.info(f"=== Operation #{seq} End ({op_id}) ===")
    _write_jsonl_line(
        op_id=op_id,
        seq=seq,
        outcome="discovery_redirect",
        duration_s=duration_s,
        error_code=None,
        preflight_gate=reason,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=get_log_dir,
    )


def _graceful_discovery_redirect(
    *,
    op_id: str,
    seq: int,
    duration_s: float,
    reason: str,
    message: str,
    undiscovered: List[str],
    inline: Dict[str, Any],
    capability_suggestions: List[Dict[str, Any]],
    code_size_bytes: int,
) -> list[TextContent]:
    """Build a status:"ok" advisory that redirects to discovery WITHOUT erroring.

    Issue #80: on a READ-ONLY run, a turn-1/turn-2 attempt to run code before
    the relevant APIs were discovered should nudge, not fail. The MCP still
    PREFERS proactive discovery -- so this payload tells the model to apply the
    inlined docs / capability suggestions and resubmit -- but it is not dressed
    as an error. ``executed`` is False and ``discovery_redirect.needs_resubmit``
    is True so a client cannot mistake it for a completed run.
    """
    _log_discovery_redirect(op_id, seq, duration_s, reason, f"undiscovered={undiscovered}")

    prefer_tools = [
        "flextools_get_object_api(object_type='...')",
        "flextools_search_by_capability(query='...')",
        "flextools_start(task='...')",
    ]
    data: Dict[str, Any] = {
        KEY_STATUS: "ok",
        KEY_EXECUTED: False,
        "op_id": op_id,
        KEY_MESSAGE: message,
        "hint": (
            "This is a workflow redirect, NOT an error -- your code was not run. "
            "Apply the method/property shapes in _inline_discovery (and "
            "capability_suggestions, if present), then resubmit the same run_module "
            "call. Proactive discovery is still preferred: calling get_object_api / "
            "search_by_capability first avoids this hop entirely."
        ),
        KEY_DISCOVERY_REDIRECT: {
            "needs_resubmit": True,
            "reason": reason,
            "undiscovered": undiscovered,
            "prefer_tools": prefer_tools,
        },
        "session": session_state.summary(),
    }
    if inline:
        data[KEY_INLINE_DISCOVERY] = inline
    if capability_suggestions:
        data[KEY_CAPABILITY_SUGGESTIONS] = capability_suggestions

    data = build_response_with_context(data, include_session=True)
    return [TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))]


def _attach_assistance_if_loop(
    response: list[TextContent],
    error_code: str,
    code_size_bytes: int,
) -> list[TextContent]:
    """Record a failure signal on the session, run the retry-loop detector,
    and attach a top-level ``_assistance`` block to the response payload
    when a stuck-loop or size-oscillation pattern is detected (issue #28).

    Always returns the (possibly-mutated) response list so callers can use it
    as a transparent wrapper:

        return _attach_assistance_if_loop(
            error_response("casting_issues_detected", ...),
            error_code="casting_issues_detected",
            code_size_bytes=len(code.encode("utf-8")),
        )

    The function is safe to call with response lists whose payload is already
    JSON (the usual case from error_response()) or with a plain dict-bearing
    list (the unit-test path). If JSON parsing fails for any reason, the
    response is returned unchanged -- the detector should never break a
    response that would otherwise have shipped fine.
    """
    # 1. Record the signal so future calls in this session can see it.
    session_state.record_op_signal(
        error_code=error_code, code_size_bytes=code_size_bytes
    )

    # 2. Run the detector. None means no pattern fired.
    pattern = session_state.detect_retry_loop_pattern()
    if pattern is None:
        return response

    # 3. Mutate the response payload to inject _assistance.
    if not response:
        return response
    first = response[0]
    text = getattr(first, "text", None)
    if text is None and isinstance(first, dict):
        text = first.get("text")
    if not isinstance(text, str):
        return response
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return response
    if not isinstance(data, dict):
        return response

    data["_assistance"] = {
        "pattern_detected": pattern["pattern_detected"],
        "message": pattern["message"],
        "error_code": pattern.get("error_code"),
    }
    # Include the diagnostic counters when available.
    if "occurrences" in pattern:
        data["_assistance"]["occurrences"] = pattern["occurrences"]
    if "window_seconds" in pattern:
        data["_assistance"]["window_seconds"] = pattern["window_seconds"]
    if "code_sizes" in pattern:
        data["_assistance"]["code_sizes"] = pattern["code_sizes"]

    new_text = json.dumps(data, indent=2, ensure_ascii=False)
    # Update the underlying object in place so callers don't need to swap refs.
    if hasattr(first, "text"):
        try:
            first.text = new_text
        except Exception:
            # TextContent is a pydantic model in modern MCP; fall back to
            # replacing the entry in the list.
            return [TextContent(type="text", text=new_text)] + response[1:]
        return response
    if isinstance(first, dict):
        first["text"] = new_text
        return response
    return response


_OPEN_PROJECT_PREFIX = "Failed to open project"
# Network-share letters that FieldWorks sometimes stores in stale paths.
# Listed in the project's settings hint when the drive isn't currently mounted.
# Issue #23 follow-up: widen the flagged-drive set. Original list (U:..Z:)
# missed common SIL mapping letters like D:, E:, F:. We now flag every
# non-C: letter -- the cross-check still verifies the drive actually
# doesn't exist before raising project_drive_unavailable, so this just
# means we DETECT more offline-share cases. C: is excluded (it's the OS
# drive and is always present on Windows).
_DRIVE_LETTERS_TO_FLAG = tuple(
    f"{chr(c)}:" for c in range(ord("A"), ord("Z") + 1) if chr(c) != "C"
)


def _extract_attempted_path(error_msg: str) -> Optional[str]:
    """Pull the path out of a .NET 'Could not find a part of the path' error.

    The full message shape from the runner is roughly:
        Failed to open project 'X': System.IO.DirectoryNotFoundException:
        Could not find a part of the path 'V:\\fau-iya-flex\\SharedSettings'.
    """
    import re as _re

    match = _re.search(r"Could not find a part of the path '([^']+)'", error_msg)
    if match:
        return match.group(1)
    return None


def _diagnose_project_open_error(
    execution_result: Dict[str, Any], project_name: str
) -> Optional[Dict[str, Any]]:
    """Recognize known project-open failure modes and return a structured payload.

    Issue #23: path-resolution failures (.NET DirectoryNotFoundException) should
    cross-check against the safe-enumeration list and surface project_path_mismatch
    / project_drive_unavailable diagnostics so the user isn't left guessing.

    Issue #27: "in use by another program" should hint at closing the FieldWorks
    GUI (the most common cause).

    Returns None if the error doesn't match a recognized open-time failure
    pattern. Otherwise returns a dict the caller merges into execution_result.
    """
    raw_error = execution_result.get("error") or ""
    if not isinstance(raw_error, str):
        return None
    if not raw_error.startswith(_OPEN_PROJECT_PREFIX):
        # Only diagnose open-time failures; runtime errors flow through the
        # polymorphic / attribute hint paths.
        return None

    # ----- Issue #27: project locked by another process. ------------------
    # The real LCM class is LcmFileLockedException (NOT LcmCacheLockedException;
    # the latter doesn't exist in LCM 11). flexicon catches it in
    # FLExProject.py and re-raises as FP_FileLockedError, whose message
    # contains "This project is in use by another program." We match all
    # three so we catch the error whether it surfaced from the wrapper or
    # raw LCM.
    locked_markers = (
        "in use by another program",
        "LcmFileLockedException",
        "FP_FileLockedError",
        "currently in use",
    )
    if any(marker.lower() in raw_error.lower() for marker in locked_markers):
        return {
            "error_code": "project_locked",
            "message": (
                f"Project '{project_name}' is currently locked by another process."
            ),
            "hint": (
                "Most common cause: FieldWorks GUI is open with this project. "
                "Close FieldWorks and retry. Other causes: another MCP session "
                "has the project open, or a stuck `.fwdata.lock` file sibling "
                "to the project's `.fwdata`. Delete it only when sure no FW "
                "process is running."
            ),
            "attempted_path": None,
        }

    # ----- Issue #23: path-resolution failure. ----------------------------
    path_failed_markers = (
        "Could not find a part of the path",
        "DirectoryNotFoundException",
    )
    if any(marker in raw_error for marker in path_failed_markers):
        attempted_path = _extract_attempted_path(raw_error)

        # Cross-check against the safe-enumeration list.
        try:
            from ..project_discovery import list_projects, get_last_directory
        except (ImportError, ValueError):
            from server.project_discovery import list_projects, get_last_directory
        try:
            discovered_names, _src = list_projects()
            discovered_dir = get_last_directory()
        except Exception as disc_exc:
            # If project discovery itself fails here, the eventual error
            # message will claim "no nearby projects" for the wrong reason.
            # Log so the operator can tell the two failure modes apart.
            get_operations_logger().warning(
                f"path_failed diagnostic: list_projects() failed: {disc_exc}"
            )
            discovered_names, discovered_dir = [], None

        # Drive-letter heuristic: if the attempted path lives on an unusual
        # network-share letter (U:..Z:) that doesn't currently exist on this
        # machine, surface project_drive_unavailable as a separate code so
        # the user can immediately see "your share is probably down".
        if attempted_path:
            upper_path = attempted_path[:2].upper()
            if (
                upper_path in _DRIVE_LETTERS_TO_FLAG
                and not os.path.exists(upper_path + os.sep)
            ):
                return {
                    "error_code": "project_drive_unavailable",
                    "message": (
                        f"Project '{project_name}' references drive {upper_path} "
                        f"({attempted_path}), but that drive is not currently "
                        f"reachable from this machine."
                    ),
                    "hint": (
                        "The drive is likely an offline network share. Reconnect "
                        "the share (or remap the drive letter) and retry. If the "
                        "project really lives elsewhere, check "
                        "flextools_list_projects for the canonical location."
                    ),
                    "attempted_path": attempted_path,
                }

        # Path-mismatch case: we know where the project actually lives.
        if project_name in (discovered_names or []) and discovered_dir:
            return {
                "error_code": "project_path_mismatch",
                "message": (
                    f"Project '{project_name}' was found in {discovered_dir} "
                    f"but FieldWorks tried to open it at "
                    f"{attempted_path or '(path not parsed from error)'}."
                ),
                "discovered_at": str(discovered_dir),
                "attempted_path": attempted_path,
                "hint": (
                    # Issue #23 follow-up: "Restart FieldWorks" was misleading
                    # -- FW reads the projects-dir path on every call, so a
                    # restart doesn't help. The actual config file is
                    # ProjectsDir.txt under %ProgramData%\SIL\FieldWorks 9.
                    "Check `%ProgramData%\\SIL\\FieldWorks 9\\ProjectsDir.txt` "
                    "-- if it points at a moved/unavailable location, update it. "
                    "Or use flextools_list_projects to confirm the canonical "
                    "location."
                ),
            }

        # Fall-through: path-not-found and the project isn't in the discovered
        # list. Re-use resolve_or_explain so the LLM gets normalized
        # suggestions instead of a bare "directory not found" string.
        try:
            from ..project_discovery import resolve_or_explain
        except (ImportError, ValueError):
            from server.project_discovery import resolve_or_explain
        _resolved, payload = resolve_or_explain(project_name)
        if payload is not None:
            payload = dict(payload)  # don't mutate the shared dict
            payload["attempted_path"] = attempted_path
            return payload
        return {
            "error_code": "project_not_found",
            "message": (
                f"Could not open project '{project_name}': the path "
                f"{attempted_path or '(unparsed)'} does not exist, and the "
                f"safe-enumeration list also did not contain this name."
            ),
            "attempted_path": attempted_path,
            "hint": (
                "Call flextools_list_projects to see what's actually available, "
                "then retry with the canonical name."
            ),
        }

    return None


def _inline_discovery_docs(
    entity_names: List[str], api_index: Any, limit: int = 3
) -> Dict[str, Any]:
    """Return get_object_api-like documentation for entities, inlined into a rejection.

    Issue #20 / Issue #29: when the discovery / undiscovered-entity gates fire,
    pull each listed entity straight out of the loaded flexicon index so the
    LLM doesn't have to make a second tool call to learn the method shapes.

    Args:
        entity_names: Entity names to look up (e.g. "SegmentOperations", "LexEntryOperations").
        api_index: The loaded APIIndex; may be None on cold start.
        limit: Max number of entities to inline (avoid bloating the payload).

    Returns:
        Dict keyed by entity name with a compact api-doc shape. Empty dict if
        no entities matched or the index has not been loaded yet.
    """
    if not entity_names or api_index is None:
        return {}
    flexicon = getattr(api_index, "flexicon", None) or {}
    entities = flexicon.get("entities") or {}
    # Issue #48: reuse the same casting-annotation path as get_object_api so the
    # inlined discovery docs carry byte-identical cast guidance.
    try:
        api_index.ensure_casting_index_loaded()
    except Exception:
        pass
    casting_index = getattr(api_index, "casting_index", None)
    inlined: Dict[str, Any] = {}
    for name in entity_names[:limit]:
        entity = entities.get(name)
        # Try the accessor <-> ops-class swap so 'POS' resolves to 'POSOperations'
        # (and vice-versa) when the assistant used the other form in code.
        if entity is None and not name.endswith("Operations"):
            entity = entities.get(name + "Operations")
            if entity is not None:
                name = name + "Operations"
        if entity is None and name.endswith("Operations"):
            short = name[: -len("Operations")]
            entity = entities.get(short)
            if entity is not None:
                name = short
        if entity is None:
            continue
        # Compact shape: methods/properties with name + signature/return_type,
        # capped so the payload stays under ~2KB per entity.
        methods = entity.get("methods", []) or []
        properties = entity.get("properties", []) or []
        method_caps = []
        for m in methods[:30]:
            method_caps.append({
                "name": m.get("name"),
                "signature": m.get("signature") or m.get("python_signature"),
                "summary": (m.get("description") or m.get("docstring") or "")[:160],
                "is_mutating": m.get("is_mutating", False),
            })
        prop_caps = []
        for p in properties[:20]:
            prop_caps.append({
                "name": p.get("name"),
                "return_type": p.get("return_type"),
                "summary": (p.get("description") or "")[:120],
            })
        casting_notes = None
        if casting_index:
            prop_caps, annotated_count = annotate_properties_with_casting(
                prop_caps, casting_index
            )
            casting_notes = build_casting_notes(annotated_count)
        entity_doc = {
            "category": entity.get("category"),
            "namespace": entity.get("namespace"),
            "import_statement": entity.get("import_statement"),
            "methods": method_caps,
            "method_count_total": len(methods),
            "properties": prop_caps,
            "property_count_total": len(properties),
            "note": (
                "Inlined for single-round-trip recovery. For the full surface, "
                f"call flextools_get_object_api(object_type='{name}')."
            ),
        }
        if casting_notes:
            entity_doc["casting_notes"] = casting_notes
        inlined[name] = entity_doc
    return inlined


def _build_capability_query(
    code_tree: Optional[ast.AST],
    undiscovered: List[str],
    user_intent: Optional[str],
) -> str:
    """Build a free-text query for the capability-search injection (issue #80).

    Blends the human's paraphrased intent (when supplied) with the undiscovered
    entity names and any guessed method names pulled off the AST. The intent is
    the strongest signal for "what were they trying to do", so it leads; entity
    and method tokens sharpen it toward the right API surface.
    """
    parts: List[str] = []
    if user_intent:
        parts.append(user_intent.strip())
    # Strip the noisy "Operations" suffix so "LexSenseOperations" contributes
    # the useful token "LexSense".
    for name in undiscovered[:5]:
        parts.append(name[: -len("Operations")] if name.endswith("Operations") else name)
    # Guessed method names: attribute accesses / calls rooted at project.* or an
    # Operations class give a strong capability hint (e.g. GetSensePartOfSpeech).
    if code_tree is not None:
        method_tokens: List[str] = []
        for node in ast.walk(code_tree):
            if isinstance(node, ast.Attribute) and node.attr and node.attr[:1].isupper():
                method_tokens.append(node.attr)
        # De-dupe, keep order, cap.
        seen: set = set()
        for tok in method_tokens:
            if tok not in seen:
                seen.add(tok)
                parts.append(tok)
            if len(seen) >= 6:
                break
    return " ".join(p for p in parts if p).strip()


def _search_capability_inline(query: str, api_index: Any, limit: int = 5) -> List[Dict[str, Any]]:
    """Lightweight keyword capability-search over the flexicon index (issue #80).

    A self-contained scorer -- deliberately NOT the full handle_search_by_capability
    machinery (that is coupled to `args`, semantic search, and worked-example
    augmentation). This returns just enough for a redirect nudge: the top method
    hits with their entity, signature, summary, and import statement so the model
    can find the RIGHT method for a guessed/nonexistent one in the same round-trip.

    Fail-open: returns [] on any error or empty query -- capability suggestions
    are an additive nudge, never load-bearing.
    """
    if not query or api_index is None:
        return []
    try:
        flexicon = getattr(api_index, "flexicon", None) or {}
        entities = flexicon.get("entities") or {}
        if not entities:
            return []
        terms = {t for t in query.lower().split() if len(t) > 2}
        if not terms:
            return []
        scored: List[Tuple[int, Dict[str, Any]]] = []
        for entity_name, entity in entities.items():
            for method in entity.get("methods", []) or []:
                mname = method.get("name") or ""
                if not mname:
                    continue
                name_lower = mname.lower()
                summary = (method.get("description") or method.get("docstring") or "")
                summary_lower = summary.lower()
                score = 0
                for term in terms:
                    if term in name_lower:
                        score += 3
                    elif term in summary_lower:
                        score += 1
                if score > 0:
                    scored.append((score, {
                        "entity": entity_name,
                        "name": mname,
                        "signature": method.get("signature") or method.get("python_signature"),
                        "summary": summary[:160],
                        "import_statement": entity.get("import_statement"),
                        "is_mutating": method.get("is_mutating", False),
                    }))
        top = heapq.nlargest(limit, scored, key=lambda pair: pair[0])
        return [row for _score, row in top]
    except Exception:
        return []


# Issue #47: max entities auto-discovered per READ-ONLY run.
_AUTO_DISCOVER_CAP = 5


def _resolve_for_auto_discovery(
    entity_names: List[str],
    api_idx: Any,
) -> List[str]:
    """Filter entity_names to those that qualify for auto-discovery (#47).

    Resolve criterion (all three must hold):
    1. Entity name is a key in the ACTIVE api_mode entity table (flexicon
       entities dict from the loaded index -- NOT a union across modes).
    2. For accessor-form names (not ending in 'Operations'), the name must
       resolve via _accessor_to_ops_map to a SINGLE non-ambiguous result that
       is also a key in the entity table.
    3. Entities that match ONLY via the naive f'{name}Operations' fallback
       (i.e., _accessor_to_ops_map did NOT return a result for this name)
       are REJECTED -- the fallback is known to produce wrong class names for
       most project accessors.

    Returns only the entities that pass all three criteria, preserving order,
    capped at _AUTO_DISCOVER_CAP.

    Write isolation: this function never touches session_state directly.
    The caller records qualifying names in auto_discovered_apis (not
    validated_apis) after this function returns.
    """
    if not entity_names or api_idx is None:
        return []

    flexicon = getattr(api_idx, "flexicon", None) or {}
    entities = flexicon.get("entities") or {}
    if not entities:
        return []

    accessor_map = _accessor_to_ops_map(api_idx)  # accessor -> OpsClass (index-derived)

    qualifying: List[str] = []
    for name in entity_names:
        if len(qualifying) >= _AUTO_DISCOVER_CAP:
            break

        # An entity that already ends in 'Operations' just needs to be in the table.
        if name.endswith("Operations"):
            if name in entities:
                qualifying.append(name)
            continue

        # Accessor form: MUST resolve via the index-derived map (not the naive fallback).
        # If the accessor is NOT in accessor_map, we cannot safely infer the ops class.
        if name not in accessor_map:
            # Explicitly rejected: naive fallback is not allowed.
            continue

        ops_class = accessor_map[name]
        # The resolved ops class must also be in the entity table.
        if ops_class in entities:
            qualifying.append(ops_class)  # Store canonical ops class name for inline docs

    return qualifying


def _entities_used_in_session(session_state_obj) -> List[str]:
    """Best-effort: collect entity names this session has touched.

    Issue #24 skeleton capture wants a list of entity names so a future
    ``find_skeletons(entity_names=['ILexSense'])`` query can surface the
    helper. We blend ``validated_apis`` (entities the assistant called
    get_object_api on) with the entity-half of ``discovered_apis`` keys
    (``Entity.Method`` form). De-duplicated, order-stable.
    """
    seen: set = set()
    out: List[str] = []
    try:
        for v in session_state_obj.validated_apis:
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        for api_key in session_state_obj.discovered_apis:
            if "." in api_key:
                head = api_key.split(".", 1)[0]
                if head and head not in seen:
                    seen.add(head)
                    out.append(head)
    except Exception:
        # Defensive: session_state could be missing fields in odd code paths.
        return []
    return out


def _capture_skeletons_after_success(
    code: str,
    op_id: str,
    duration_s: float,
) -> None:
    """Persist top-level def helpers from a successful op to the closet.

    Wrapped in try/except so capture failure never breaks the op. The op
    has already succeeded by the time we reach here.
    """
    try:
        # user_intent: issue #18 may eventually add this to RunModuleInput.
        # Until then it's always None; the field exists in the schema so the
        # tool already supports future intent passing without re-wiring.
        user_intent = None

        skeleton_storage.capture_from_code(
            code,
            entities_used=_entities_used_in_session(session_state),
            user_intent=user_intent,
            op_id=op_id,
            session_id=getattr(session_state, "session_id", "") or "",
            duration_ms=int(duration_s * 1000),
        )
    except Exception:
        # Belt-and-suspenders: capture_from_code already swallows, but the
        # session_state access above could raise in a corrupted state.
        pass


def _run_validator(validator_func, code: str, check_key: str, error_code: str, **validator_kwargs) -> Optional[list[TextContent]]:
    """Run a single validator and return error response if validation fails.

    Reduces code duplication in handle_run_module by centralizing validator pattern.

    Args:
        validator_func: The validator function to call (e.g., detect_cud_operations)
        code: The code to validate
        check_key: The key in validator result to check (e.g., 'has_cud_operations')
        error_code: The error code to return if validation fails
        **validator_kwargs: Additional keyword args to pass to validator_func

    Returns:
        Error response list if validation fails, None if validation passes
    """
    check_result = validator_func(code, **validator_kwargs)
    if check_result.get(check_key):
        return error_response(
            error_code,
            check_result.get("suggestion", "Validation failed"),
            **check_result.get("extras", {})
        )
    return None


async def handle_start_module(args: dict) -> list[TextContent]:
    """Interactive wizard to start creating a new FlexTools module."""
    import platform

    # Gather environment info
    env_info = {
        "python_version": "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro),
        "python_implementation": platform.python_implementation(),
        "platform": platform.system(),
        "can_use_modern_python": sys.version_info >= (3, 6),
    }

    # Check what parameters were provided
    provided = {k: v for k, v in args.items() if v is not None}

    # Define required and optional questions
    required_questions = []
    optional_questions = []

    if "module_name" not in provided:
        required_questions.append({
            "field": "module_name",
            "question": "What should the module be named?",
            "type": "string",
            "example": "Export Custom Data"
        })

    if "synopsis" not in provided:
        required_questions.append({
            "field": "synopsis",
            "question": "Provide a short description of what the module does:",
            "type": "string",
            "example": "Exports custom field data to a file"
        })

    if "api_target" not in provided:
        required_questions.append({
            "field": "api_target",
            "question": "Which API should the module target?",
            "type": "choice",
            "options": [
                {
                    "value": "flexicon",
                    "label": "Flexicon (Recommended)",
                    "description": "Modern Python wrappers with 99% documentation coverage and examples. Best for new modules. Use api_mode='flexicon' in searches."
                },
                {
                    "value": "flexlibs_stable",
                    "label": "FlexLibs Stable + LibLCM fallback",
                    "description": "Legacy Python wrappers (~40 functions) with LibLCM fallback for advanced features. Use api_mode='flexlibs_stable' in searches."
                },
                {
                    "value": "liblcm",
                    "label": "Pure LibLCM",
                    "description": "Direct C# API access via pythonnet. Maximum flexibility but requires .NET knowledge. Use api_mode='liblcm' in searches."
                }
            ],
            "recommended": "flexicon"
        })

    if "modifies_db" not in provided:
        required_questions.append({
            "field": "modifies_db",
            "question": "Will this module modify the FieldWorks database?",
            "type": "boolean",
            "hint": "Set to True if the module creates, updates, or deletes entries, senses, or other data."
        })

    if "domain" not in provided:
        required_questions.append({
            "field": "domain",
            "question": "What is the primary domain this module works with?",
            "type": "choice",
            "options": [
                {"value": "lexicon", "label": "Lexicon", "description": "Entries, senses, definitions, glosses"},
                {"value": "grammar", "label": "Grammar", "description": "Parts of speech, morphology, inflection"},
                {"value": "texts", "label": "Texts", "description": "Interlinear texts, discourse analysis"},
                {"value": "media", "label": "Media", "description": "Pictures, audio files, linked files"},
                {"value": "general", "label": "General", "description": "Project-wide operations, multiple domains"}
            ]
        })

    if args.get("modifies_db") and "include_dry_run" not in provided:
        required_questions.append({
            "field": "include_dry_run",
            "question": "Include a DRY_RUN safety mode? (Recommended for write operations)",
            "type": "boolean",
            "hint": "DRY_RUN mode shows what would happen without making changes. Useful for testing.",
            "recommended": True
        })

    # Optional question - only ask if no required questions remain
    if "test_project" not in provided:
        optional_questions.append({
            "field": "test_project",
            "question": "Do you have a FieldWorks test project to verify the script against?",
            "type": "string",
            "hint": "Provide the project name (e.g., 'Sena 3') or path. This helps verify the script works before running on production data.",
            "optional": True,
            "example": "Sena 3"
        })

    # If we have required questions, return them along with optional ones
    if required_questions:
        questions = required_questions + optional_questions
        return json_response({
            KEY_STATUS: KEY_NEEDS_INPUT,
            "environment": env_info,
            KEY_PROVIDED: provided,
            "required_questions": required_questions,
            "optional_questions": optional_questions,
            KEY_QUESTIONS: questions,
            "instructions": "Please ask the user these questions and call start_module again with the answers. Optional questions can be skipped."
        })

    # All questions answered - generate the template
    module_name = args["module_name"]
    synopsis = args["synopsis"]
    api_target = args["api_target"]
    modifies_db = args["modifies_db"]
    domain = args.get("domain", "general")
    include_dry_run = args.get("include_dry_run", False)
    test_project = args.get("test_project")

    # Build imports
    imports = ["from flextoolslib import *"]

    # Build helper code
    helpers = []
    if include_dry_run:
        helpers.append("""
#----------------------------------------------------------------
# Configuration

DRY_RUN = True  # Set to False to actually make changes
""")

    # Build main function body
    main_body_lines = []

    if modifies_db and include_dry_run:
        main_body_lines.append("""    if not modifyAllowed and not DRY_RUN:
        report.Error("This module requires write access.")
        return

    if DRY_RUN:
        report.Warning("DRY RUN mode - no changes will be made")
""")
    elif modifies_db:
        main_body_lines.append("""    if not modifyAllowed:
        report.Error("This module requires write access.")
        return
""")

    main_body_lines.append("""
    report.Info("Starting...")

    # TODO: Implement module logic

    report.Info("Done.")
""")

    # Combine main body
    main_body = "".join(main_body_lines)

    # Generate final template
    template = """#
#   {module_name}
#    - A FlexTools Module -
#
#   {synopsis}
#
#   API Target: {api_target}
#   Platforms: Python .NET and IronPython
#

{imports}
{helpers}
#----------------------------------------------------------------
# Documentation that the user sees:

docs = {{FTM_Name        : "{module_name}",
        FTM_Version     : 1,
        FTM_ModifiesDB  : {modifies_db},
        FTM_Synopsis    : "{synopsis}",
        FTM_Description :
\"\"\"
{synopsis}

<additional details here>
\"\"\" }}

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    \"\"\"
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    \"\"\"
{main_body}

#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
""".format(
        module_name=module_name,
        synopsis=synopsis,
        api_target=api_target,
        imports="\n".join(imports),
        helpers="".join(helpers),
        modifies_db=modifies_db,
        main_body=main_body
    )

    # API-specific notes and search guidance
    api_notes = {
        "flexicon": {
            "search_mode": "flexicon",
            "tips": [
                "Use project.Senses.GetAll() to iterate senses",
                "Use project.CustomFields.GetValue/SetValue for custom fields",
                "Use project.Media.* for file operations",
                "Full documentation at 99% coverage with examples"
            ],
            "search_reminder": "Use api_mode='flexicon' when calling search_by_capability"
        },
        "flexlibs_stable": {
            "search_mode": "flexlibs_stable",
            "tips": [
                "Use project.LexiconAllEntries() to iterate entries",
                "More limited API (~40 functions)",
                "LibLCM fallback available for advanced features",
                "Compatible with older FlexTools installations"
            ],
            "search_reminder": "Use api_mode='flexlibs_stable' when calling search_by_capability (includes LibLCM fallback)"
        },
        "liblcm": {
            "search_mode": "liblcm",
            "tips": [
                "Direct access to C# LibLCM API via pythonnet",
                "Requires understanding of .NET and LibLCM architecture",
                "Most powerful but also most complex",
                "Use ILexEntry, ILexSense, etc. interface types"
            ],
            "search_reminder": "Use api_mode='liblcm' when calling search_by_capability"
        }
    }

    # Build next steps based on configuration
    next_steps = [
        "Save the template to your FlexTools Modules folder",
        "Replace TODO comments with your implementation",
    ]

    if include_dry_run:
        next_steps.append("Test with DRY_RUN=True first to verify behavior without making changes")

    if test_project:
        next_steps.append("Run the module against '{}' to verify it works correctly".format(test_project))
        next_steps.append("Check the FlexTools report output for any errors or warnings")
    else:
        next_steps.append("IMPORTANT: Test on a backup/sample project before running on production data")

    next_steps.append("Use search_by_capability to find specific API methods you need")

    # Build configuration output
    config = {
        "module_name": module_name,
        "synopsis": synopsis,
        "api_target": api_target,
        "modifies_db": modifies_db,
        "domain": domain,
        "include_dry_run": include_dry_run
    }
    if test_project:
        config["test_project"] = test_project

    api_info = api_notes.get(api_target, {})

    return json_response({
        KEY_STATUS: KEY_COMPLETE,
        "environment": env_info,
        "configuration": config,
        KEY_TEMPLATE: template,
        "api_guidance": {
            "mode": api_target,
            "search_mode": api_info.get("search_mode", api_target),
            "search_reminder": api_info.get("search_reminder", ""),
            "tips": api_info.get("tips", [])
        },
        KEY_NEXT_STEPS: next_steps,
        "testing_reminder": "Always test FlexTools modules on a backup or sample project first!" if not test_project else None
    })


# ---------------------------------------------------------------------------
# Issue #46: Safe auto-fix engine
# ---------------------------------------------------------------------------

_AUTO_FIX_CAP = 5  # Maximum auto-fixes per run before falling back to rejection


def _try_auto_fix_casting(
    code: str,
    issues: List[Dict[str, Any]],
    api_idx: Any,
    code_tree: Optional[ast.AST],
) -> Optional[Dict[str, Any]]:
    """Attempt safe casting rewrites when all safety conditions are met.

    Domain safety rules (HARD -- do not relax):
    - cast_interface must be non-null and unambiguous (exactly one target).
    - severity must be "error".
    - rewrite must be non-null.
    - Cap at _AUTO_FIX_CAP total fixes.

    Returns a dict with:
      - patched_code: str  (the rewritten source)
      - fixes: list of fix records
    Or None if any condition is not met (caller falls back to rejection).
    """
    fixable = [
        i for i in issues
        if i.get("severity") == "error"
        and i.get("cast_interface") and isinstance(i.get("cast_interface"), str)
        and i.get("rewrite")
        and i.get("line") is not None
    ]
    # ALL fixable issues must qualify; if any error-severity issue is not
    # fixable (null rewrite / ambiguous target), fall back to full rejection.
    error_issues = [i for i in issues if i.get("severity") == "error"]
    if len(fixable) != len(error_issues):
        return None
    if not fixable:
        return None
    if len(fixable) > _AUTO_FIX_CAP:
        return None

    # Apply fixes BOTTOM-UP (highest line number first) to preserve offsets.
    fixable_sorted = sorted(fixable, key=lambda i: i["line"], reverse=True)
    lines = code.splitlines(keepends=True)
    fix_records = []

    # Guard: detect two issues sharing the same (line, found_at) -- applying
    # the second replace() would operate on already-patched text, producing a
    # silent mis-patch.  Reject the entire batch when a collision is found.
    _seen_line_found_at: set = set()
    for issue in fixable_sorted:
        _key = (issue["line"], issue.get("found_at") or issue.get("property"))
        if _key in _seen_line_found_at:
            return None  # Collision: two issues share (line, found_at) -> bail
        _seen_line_found_at.add(_key)

    for issue in fixable_sorted:
        line_idx = issue["line"] - 1  # AST line numbers are 1-based
        if line_idx < 0 or line_idx >= len(lines):
            return None  # Line out of range -> bail
        orig_line = lines[line_idx]
        found_at = issue.get("found_at") or issue.get("property")
        rewrite = issue["rewrite"]
        if not found_at or found_at not in orig_line:
            return None  # Can't locate the expression -> bail
        new_line = orig_line.replace(found_at, rewrite, 1)
        if new_line == orig_line:
            return None  # Replace was a no-op -> bail
        lines[line_idx] = new_line
        fix_records.append({
            "kind": "casting",
            "line": issue["line"],
            "original": found_at,
            "replacement": rewrite,
            "cast_interface": issue["cast_interface"],
        })

    patched = "".join(lines)

    # Prepend deduplicated imports.
    imports_needed: List[str] = []
    seen_imports: set = set()
    for issue in fixable:
        for imp in (issue.get("imports_needed") or []):
            if imp not in seen_imports:
                seen_imports.add(imp)
                imports_needed.append(imp)

    if imports_needed:
        existing = _collect_all_imported_names(patched) or set()
        new_imports = []
        for imp_stmt in imports_needed:
            # Extract the imported name from "from X import Y"
            parts = imp_stmt.split()
            imported_name = parts[-1] if parts else ""
            if imported_name and imported_name not in existing:
                new_imports.append(imp_stmt)
        if new_imports:
            patched = "\n".join(new_imports) + "\n" + patched

    return {"patched_code": patched, "fixes": fix_records}


def _try_auto_fix_typos(
    code: str,
    issues: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Attempt safe typo correction when all safety conditions are met.

    Domain safety rules (HARD -- do not relax):
    - match_ratio >= 0.9
    - Exactly ONE did_you_mean candidate.
    - lineno must be present in the issue dict.
    - Cap at _AUTO_FIX_CAP total fixes.

    Returns a dict with:
      - patched_code: str
      - fixes: list of fix records
    Or None if any condition is not met (caller falls back to rejection).
    """
    fixable = [
        i for i in issues
        if i.get("match_ratio", 0.0) >= 0.9
        and len(i.get("did_you_mean") or []) == 1
        and i.get("lineno") is not None
        and i.get("typo_attr")
    ]
    # ALL issues must be fixable; partial fix = full rejection
    if len(fixable) != len(issues):
        return None
    if not fixable:
        return None
    if len(fixable) > _AUTO_FIX_CAP:
        return None

    # Apply BOTTOM-UP by line number.
    fixable_sorted = sorted(fixable, key=lambda i: i["lineno"], reverse=True)
    lines = code.splitlines(keepends=True)
    fix_records = []

    for issue in fixable_sorted:
        line_idx = issue["lineno"] - 1
        if line_idx < 0 or line_idx >= len(lines):
            return None
        orig_line = lines[line_idx]
        typo = issue["typo_attr"]
        correction = issue["did_you_mean"][0]
        if typo not in orig_line:
            return None
        new_line = orig_line.replace(typo, correction, 1)
        if new_line == orig_line:
            return None
        lines[line_idx] = new_line
        fix_records.append({
            "kind": "typo",
            "line": issue["lineno"],
            "col": issue.get("col_offset"),
            "original": typo,
            "replacement": correction,
            "match_ratio": issue["match_ratio"],
        })

    patched = "".join(lines)
    return {"patched_code": patched, "fixes": fix_records}


def _build_auto_fix_note(fix_records: List[Dict[str, Any]], source_hint: str = "<submitted code>") -> str:
    """Build an actionable note referencing each fix by kind and line number.

    IMPORTANT: Always warn the user to update their SOURCE FILE -- only the
    executed copy was patched in memory.
    """
    lines_out = [
        f"[AUTO-FIX] {len(fix_records)} safe rewrite(s) were applied to the "
        f"in-memory copy of your code before execution:",
        "",
    ]
    for rec in fix_records:
        kind = rec.get("kind", "fix")
        line_no = rec.get("line", "?")
        orig = rec.get("original", "?")
        replacement = rec.get("replacement", "?")
        if kind == "casting":
            lines_out.append(
                f"  Line {line_no} [CASTING]: '{orig}' -> '{replacement}' "
                f"(cast to {rec.get('cast_interface', '?')})"
            )
        elif kind == "typo":
            ratio_pct = int(rec.get("match_ratio", 0) * 100)
            lines_out.append(
                f"  Line {line_no} [TYPO]: '{orig}' -> '{replacement}' "
                f"({ratio_pct}% match)"
            )
        else:
            lines_out.append(f"  Line {line_no} [{kind.upper()}]: '{orig}' -> '{replacement}'")

    lines_out.extend([
        "",
        f"[ACTION REQUIRED] The fixes were applied only to the executed copy.",
        f"  Source: {source_hint}",
        f"  Update your source file at the line numbers listed above or you will",
        f"  see this auto-fix note every time you run this code.",
    ])
    return "\n".join(lines_out)


def _validate_patched_code(
    patched_code: str,
    api_idx: Any,
    casting_index: Any,
) -> bool:
    """Re-parse and re-run the full preflight chain on patched code.

    Returns True only if the patched code:
    1. Parses cleanly (no SyntaxError).
    2. Passes detect_casting_needs with zero NEW casting issues.
    3. Passes detect_invalid_project_chains with no new typo issues.

    Any failure returns False (caller falls back to original rejection payload).
    """
    try:
        patched_tree = ast.parse(patched_code)
    except SyntaxError:
        return False

    # Re-run casting check on patched code
    patched_casting = detect_casting_needs(patched_code, casting_index, patched_tree)
    if patched_casting.get("has_casting_issues"):
        return False

    # Re-run typo check on patched code
    patched_typo = detect_invalid_project_chains(patched_tree, api_idx)
    if patched_typo.get("has_invalid"):
        return False

    return True


async def handle_run_module(args: dict) -> list[TextContent]:
    """Execute code (snippet or full module) against a FieldWorks project.

    Accepts:
    - Minimal snippets: entries = project.LexEntry.GetAll()
    - Full modules: def Main(project, report, modifyAllowed): ...
    - Anything in between

    If code defines Main(), it will be called. Otherwise, code runs as-is.
    """
    # Get code from parameter (unified interface)
    code = args.get("code")
    if not code:
        # Fallback for backwards compatibility (shouldn't happen)
        code = args.get("module_code") or args.get("operations", "")

    # Use session state as fallback for project and write settings.
    # An explicit None from args also falls back to session state, so the value
    # passed to the subprocess is always a proper bool (not None).
    project_name = args.get("project_name") or session_state.get_project()
    write_enabled_arg = args.get("write_enabled")
    write_enabled = bool(write_enabled_arg if write_enabled_arg is not None else session_state.is_write_enabled())
    # #14 Phase 1: undoable session variable, ignored by flexicon when write=False.
    undoable = session_state.is_undoable() and write_enabled
    api_mode = session_state.get_mode()
    # user_intent (issue #18) is optional LLM-provided context paraphrasing
    # the human's actual request. Logged on the Start block; never required.
    user_intent = args.get("user_intent")
    # user_request (diagnostic-report feature, spec section 4): optional
    # per-op VERBATIM override. Falls back to the turn-level value captured
    # by flextools_start (session_state.get_user_request()) when this op
    # didn't pass its own; _log_operation_start further falls back to
    # user_intent when both are empty.
    user_request = args.get("user_request") or session_state.get_user_request()
    # max_info_messages (issue #25): cap the number of report.Info messages
    # returned to the LLM. Default 100 (first 50 + last 50 + truncation marker).
    # 0 disables the cap. Warnings/errors are NEVER capped regardless.
    max_info_messages = int(args.get("max_info_messages", 100))
    # Issue #28: precompute code size for the retry-loop / size-oscillation
    # detector. Same byte count used at every rejection / runtime-failure site.
    _code_size_bytes = len(code.encode("utf-8", errors="replace")) if code else 0
    # Issue #46: resolve effective auto_fix flag.
    # Write runs ALWAYS skip auto-fix regardless of any flag (hard constraint).
    _auto_fix_arg = args.get("auto_fix")  # None means use config default
    _config_auto_fix = bool(config_get(AUTO_FIX_ENABLED_KEY, AUTO_FIX_ENABLED_DEFAULT))
    effective_auto_fix = bool(_auto_fix_arg if _auto_fix_arg is not None else _config_auto_fix)
    # Write runs: force off unconditionally (hard constraint).
    effective_auto_fix = effective_auto_fix and (not write_enabled)
    # Accumulator for auto-fix records; populated when auto-fix succeeds.
    _auto_fixes_applied: Optional[List[Dict[str, Any]]] = None
    _auto_fix_note: Optional[str] = None
    # Issue #80: provenance. 'existing' code (from disk / pasted by the human)
    # skips the two API-DISCOVERY gates -- verifying every API the model didn't
    # author is expensive LLM work we don't need. This is a COST lever ONLY:
    # write-safety (checked earlier, unconditionally) and casting injection are
    # never affected, so a mislabeled 'existing' can at worst run un-discovered
    # (possibly hallucinated) APIs that fail loudly at runtime -- it can never
    # relax a safety gate.
    source_provenance = args.get("source", "authored")
    _provenance_existing = source_provenance == "existing"

    # Validate project_name is available BEFORE assigning an op_id -- without
    # both code and project the call isn't really an "operation" worth logging
    # as a full Start/End block. But we still WARN so the .log records what
    # the LLM tried and why we bounced it -- otherwise these pre-op rejects
    # leave no trace and a "user keeps hitting project_name_required" debug
    # has no .log evidence.
    if not project_name:
        get_operations_logger().warning(
            "[PRE-OP REJECT] project_name_required: no project_name in args or session"
        )
        return error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or provide it directly.",
            session=session_state.summary()
        )

    # Fuzzy resolution: autocorrect case/whitespace-only typos, return an
    # error with suggestions for bigger mismatches. Runs BEFORE the op_id
    # block so unresolvable names don't pollute the operation log.
    try:
        from ..project_discovery import resolve_or_explain
    except (ImportError, ValueError):
        from server.project_discovery import resolve_or_explain
    resolved, _resolve_err = resolve_or_explain(project_name)
    if _resolve_err:
        get_operations_logger().warning(
            f"[PRE-OP REJECT] {_resolve_err['error_code']}: "
            f"project_name={project_name!r} reason={_resolve_err.get('reason')!r}"
        )
        return error_response(
            _resolve_err["error_code"],
            _resolve_err["message"],
            suggestions=_resolve_err["suggestions"],
            reason=_resolve_err["reason"],
            hint=_resolve_err["hint"],
            session=session_state.summary(),
        )
    if resolved and resolved != project_name:
        # Update session so subsequent calls (and the op log) use the canonical name.
        session_state.project_name = resolved
        project_name = resolved

    # === Operation logging begins here ===
    # Every code-bearing call gets an op_id and a Start block, regardless of
    # whether it later passes pre-flight. The user wants ALL attempted ops
    # visible in the .log so a "what did the LLM try" reconstruction is possible.
    seq, op_id = _next_op_id()
    t_start = time.monotonic()

    # Parse AST early; we need it to classify the source kind on the Start line.
    code_tree: Optional[ast.AST]
    try:
        code_tree = ast.parse(code)
        source_kind = _classify_code_source(code, code_tree)
    except SyntaxError as syn_exc:
        code_tree = None
        source_kind = "parse_failed"
        _log_operation_start(
            op_id, seq, project_name, write_enabled, code, source_kind,
            user_intent=user_intent,
            user_request=user_request,
        )
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "syntax_error",
            f"line {syn_exc.lineno}: {syn_exc.msg}",
        )
        return _attach_assistance_if_loop(
            error_response(
                "syntax_error",
                f"Invalid Python syntax at line {syn_exc.lineno}: {syn_exc.msg}",
                line_number=syn_exc.lineno,
                guidance="Check your Python code for syntax errors (missing colons, unmatched parentheses, etc.)",
                op_id=op_id,
            ),
            error_code="syntax_error",
            code_size_bytes=_code_size_bytes,
        )

    # Canonical Operation Start block (with source_kind). Casting details are
    # appended as their own line after the casting validator runs.
    _log_operation_start(
        op_id, seq, project_name, write_enabled, code, source_kind,
        user_intent=user_intent,
        user_request=user_request,
    )

    # === PREFLIGHT: Validate server state before attempting execution ===
    server_health = validate_server_state()
    if not server_health["is_healthy"]:
        error_details = []
        for severity, message in server_health["issues"]:
            if severity == "error":
                error_details.append(f"[{severity.upper()}] {message}")
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "server_state_error",
            "Server initialization incomplete:\n" + "\n".join(error_details),
        )
        return _attach_assistance_if_loop(
            error_response(
                "server_state_error",
                "Server initialization incomplete. Cannot execute code:\n" + "\n".join(error_details),
                server_state=server_health,
                hint="The server may not have started correctly. Check the server logs and try restarting.",
                op_id=op_id,
            ),
            error_code="server_state_error",
            code_size_bytes=_code_size_bytes,
        )

    # Partial-module structural check: when code defines `Main` but lacks the
    # `docs` dict and/or `FlexToolsModule = FlexToolsModuleClass(...)` binding,
    # nudge the AI toward `get_module_template` instead of letting a half-
    # scaffolded "module" silently work in the runner but fail when saved as a
    # real FlexTools file. Bare snippets without `def Main` are unaffected.
    # Escape hatch: pass skip_module_check=True to run as-is.
    if not args.get("skip_module_check", False):
        partial_check = detect_partial_module_structure(code, code_tree)
        if partial_check["is_partial_module"]:
            _log_preflight_reject(
                op_id, seq, time.monotonic() - t_start,
                "partial_module_structure",
                f"missing_elements={partial_check.get('missing_elements')}",
            )
            return _attach_assistance_if_loop(
                error_response(
                    "partial_module_structure",
                    partial_check["suggestion"],
                    missing_elements=partial_check["missing_elements"],
                    next_steps=[
                        "1. Call flextools_get_module_template(flavor='flexicon') to fetch the canonical scaffold",
                        "2. Copy the missing pieces (docs dict, FlexToolsModule binding) into your code",
                        "3. Re-run flextools_run_module()",
                        "Alternative: drop the `def Main:` wrapper to run the body as a bare snippet",
                        "Override: pass skip_module_check=True to run the partial code as-is",
                    ],
                    op_id=op_id,
                ),
                error_code="partial_module_structure",
                code_size_bytes=_code_size_bytes,
            )

    # Check for unprotected mutations - HARD BLOCK if found
    cud_info = detect_cud_operations(code)
    cert = certify_script_readonly(code, get_api_index(), code_tree)

    # CRITICAL: Refuse unprotected code unconditionally
    if not cert["is_certified_readonly"]:
        guidance = get_unprotected_write_guidance(cert)
        mutating = [m for m in cert.get("mutating_calls", []) if m.get("is_mutating")]
        unprotected_lcm = cert.get("unprotected_liblcm_calls", []) or []
        raw_lcm = cert.get("raw_lcm_patterns", []) or []
        # Mirror the casting-reject pattern: an INFO summary + per-issue DEBUG
        # lines so the .log captures WHY writeability failed, not just that it
        # did. Without this the detail field only carries the first 5 method
        # names and the actual line numbers / contexts are lost.
        op_logger = get_operations_logger()
        # Issue #44: a raw `set_String` / collection write surfaces in
        # unprotected_lcm but NOT in the flexicon-index `mutating` list, which
        # made the old line read `mutating=0 ... raw_lcm=1` -- self-contradictory
        # (a raw write IS a mutation). Report the true total and keep the
        # per-source breakdown so the count and the raw_lcm flag agree.
        total_mutations = len(mutating) + len(unprotected_lcm)
        op_logger.info(
            f"Preflight writeability: mutating={total_mutations} "
            f"(flexicon={len(mutating)} unprotected_lcm={len(unprotected_lcm)} "
            f"raw_lcm={len(raw_lcm)}) (rejected)"
        )
        for m in mutating[:10]:
            op_logger.debug(
                f"  writeability: class={m.get('class')} method={m.get('method')} "
                f"source={m.get('source')}"
            )
        for c in unprotected_lcm[:10]:
            op_logger.debug(
                f"  writeability: line={c.get('line')} method={c.get('method')} "
                f"context={(c.get('context') or '')[:80]!r}"
            )
        for p in raw_lcm[:10]:
            op_logger.debug(
                f"  writeability: line={p.get('line')} method={p.get('method')} "
                f"context={(p.get('context') or '')[:80]!r}"
            )
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "unprotected_writes",
            f"mutating_calls={[m.get('method') for m in mutating[:5]]}",
        )
        return _attach_assistance_if_loop(
            [TextContent(type="text", text=json.dumps(guidance, indent=2))],
            error_code="unprotected_writes",
            code_size_bytes=_code_size_bytes,
        )

    # Check for polymorphic casting issues - detect and suggest fixes BEFORE running
    # This catches errors like: sense.Owner.HeadWord (ICmObject doesn't have HeadWord)
    api_idx = get_api_index()
    casting_index = api_idx.casting_index if api_idx else None
    casting_check = detect_casting_needs(code, casting_index, code_tree)
    if casting_check["has_casting_issues"]:
        # Format issues with clear fixes for all 3 API flavors
        issues = casting_check["casting_issues"]
        # Log the casting findings before rejecting so the .log captures the WHY.
        get_operations_logger().info(
            f"Preflight casting: issues={len(issues)} (rejected)"
        )
        for issue in issues[:10]:
            get_operations_logger().debug(
                f"  casting: line={issue.get('line')} property={issue.get('property')} "
                f"pattern={issue.get('pattern','')[:80]!r}"
            )

        # Issue #46: attempt safe auto-fix for read-only runs.
        if effective_auto_fix:
            _af_result = _try_auto_fix_casting(code, issues, api_idx, code_tree)
            if _af_result is not None:
                _patched = _af_result["patched_code"]
                _fix_records = _af_result["fixes"]
                if _validate_patched_code(_patched, api_idx, casting_index):
                    # Telemetry: log both original and patched sha256
                    _orig_sha = hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()[:12]
                    _patched_sha = hashlib.sha256(_patched.encode("utf-8", errors="replace")).hexdigest()[:12]
                    get_operations_logger().info(
                        f"[AUTO-FIX] casting: applied {len(_fix_records)} rewrite(s). "
                        f"original_sha256={_orig_sha} patched_sha256={_patched_sha}"
                    )
                    # Record success signal so the retry-loop detector resets.
                    # (None error_code = success, resets the loop counter.)
                    session_state.record_op_signal(error_code=None, code_size_bytes=_code_size_bytes)
                    # Replace code + tree with patched version and continue preflight
                    code = _patched
                    code_tree = ast.parse(code)
                    casting_check = detect_casting_needs(code, casting_index, code_tree)
                    # CP2 fix: re-derive `issues` from the post-fix casting_check so
                    # the still-has-issues branch below (signature, enrichment,
                    # how_to_fix, error_response) reflects only the RESIDUAL issues,
                    # not the stale pre-fix set captured at line 2077.
                    issues = casting_check["casting_issues"]
                    _auto_fixes_applied = _fix_records
                    _auto_fix_note = _build_auto_fix_note(_fix_records, source_hint="<submitted code>")
                    # Proceed to rest of preflight with patched code
                else:
                    get_operations_logger().info(
                        "[AUTO-FIX] casting: patch did not pass re-preflight; falling back to rejection"
                    )

        # If still has issues after auto-fix attempt (or auto-fix disabled/failed)
        if casting_check["has_casting_issues"]:
            # Diagnostic-report CP2: thread a real per-issue signature (built
            # from property + missing-interface + cast-interface) into the
            # JSONL record instead of leaving casting_signature blank. Without
            # this, two UNRELATED casting issues in the same turn (e.g. a bad
            # Gloss access, then later an unrelated bad Definition access)
            # both fall through to the bare "casting_issues_detected" code and
            # collapse into a single false recurrence.
            _casting_sig = compute_casting_signature(issues)
            _log_preflight_reject(
                op_id, seq, time.monotonic() - t_start,
                "casting_issues_detected",
                f"{len(issues)} polymorphic property access issue(s) require casting.",
                casting_signature=_casting_sig,
            )
            # Issue #21: each issue carries an inline rewrite + imports_needed so
            # the LLM doesn't need to call flextools_resolve_property to recover.
            # Issue #22: retarget the hint at the inlined rewrite, not the tool.
            has_any_rewrite = any(i.get("rewrite") for i in issues)
            first_rewrite = next(
                (i for i in issues if i.get("rewrite")), None
            )
            if has_any_rewrite and first_rewrite is not None:
                how_to_fix = [
                    f"1. Apply the inlined rewrite at line {first_rewrite['line']}: "
                    f"`{first_rewrite['rewrite']}`",
                    "2. Add the imports listed in casting_issues[*].imports_needed",
                    "3. Re-run your code",
                ]
                hint_msg = (
                    "Each entry in casting_issues carries `rewrite` (the cast-wrapped "
                    "expression) and `imports_needed` (the SIL.LCModel imports to add). "
                    "Apply them line-by-line and re-run."
                )
            else:
                # Fall back to the old guidance when the AST-rewrite path didn't
                # produce anything (e.g. chained receivers).
                how_to_fix = [
                    "1. Call flextools_resolve_property(property_name='{}', context_entity='{}') to get the exact casting solution".format(
                        issues[0]["property"],
                        issues[0].get("context_entity", "ICmObject"),
                    ),
                    "2. Apply the suggested cast from the tool response",
                    "3. Re-run your code",
                ]
                hint_msg = (
                    "No automatic rewrite was emitted (likely because the property "
                    "is accessed via a chained or call-rooted receiver). Use "
                    "flextools_resolve_property to resolve manually."
                )
            # Issue #54: enrich each casting issue with the #54-spec detail keys.
            # correct_cast_expression is the ready-to-paste rewrite (issue #21
            # already computes it as `rewrite`; we alias here rather than duplicate).
            # base_type / concrete_type are derived from the existing keys.
            for _ci in issues:
                if "correct_cast_expression" not in _ci:
                    _ci["correct_cast_expression"] = _ci.get("rewrite")
                if "base_type" not in _ci:
                    _missing = _ci.get("missing_on")
                    _ci["base_type"] = _missing[0] if isinstance(_missing, list) and _missing else None
                if "concrete_type" not in _ci:
                    _ci["concrete_type"] = _ci.get("cast_interface")

            # Issue #28: wrap the rejection with the retry-loop detector so
            # repeated casting failures surface _assistance hints.
            return _attach_assistance_if_loop(
                error_response(
                    "casting_issues_detected",
                    f"Found {len(issues)} polymorphic property access issue(s) that require casting.",
                    severity=casting_check["severity"],
                    casting_issues=issues,  # canonical key matching validator output
                    issues=issues,           # back-compat alias
                    general_guidance={
                        "why": "In C# (LibLCM), base interface types like ICmObject don't expose all properties. You must cast to concrete types (ILexEntry, IMultiString, etc.) to access them.",
                        "applies_to": "All 3 API flavors (flexlibs_stable, flexicon, liblcm) - this is a C# type system issue, not wrapper-specific",
                        "how_to_fix": how_to_fix,
                    },
                    hint=hint_msg,
                    next_steps=hint_msg,
                    op_id=op_id,
                ),
                error_code="casting_issues_detected",
                code_size_bytes=_code_size_bytes,
            )

    # Issue #47 accumulators: populated when read-only auto-discovery fires.
    _auto_discovered_entities: Optional[List[str]] = None
    _auto_discovery_inline: Optional[Dict[str, Any]] = None
    _discovery_note: Optional[str] = None

    # Require API discovery before executing code
    skip_api_check = args.get("skip_api_check", False)
    if skip_api_check:
        # Audit the escape hatch so it shows up in operations logs.
        # Bypassing discovery is a real foot-gun; make every use visible.
        _skip_msg = (
            "skip_api_check=True passed -- bypassing api_discovery_required and "
            "undiscovered_entity gates. This is an escape hatch; prefer calling "
            "flextools_get_object_api for each entity used."
        )
        if not write_enabled:
            # Issue #47: on read-only runs auto-discovery supersedes skip_api_check.
            _skip_msg += (
                " On READ-ONLY runs, skip_api_check is superseded by auto-discovery "
                "(#47): undiscovered entities that qualify will be auto-granted without "
                "requiring this flag."
            )
        get_operations_logger().warning(_skip_msg)

    # Issue #80: provenance-driven gate skip. 'existing' code (from disk / pasted
    # by the human) skips BOTH api-discovery gates -- re-verifying APIs the model
    # didn't author is expensive LLM work we don't need. This is a COST lever
    # only: write-safety (checked earlier, unconditionally) and casting injection
    # are unaffected, so it can never relax a safety gate.
    if _provenance_existing:
        get_operations_logger().info(
            "[DISCOVERY] source='existing' -- skipping api_discovery_required and "
            "undiscovered_entity gates (issue #80). Write-safety + casting already "
            "ran and are unaffected by provenance."
        )
    _skip_discovery_gates = skip_api_check or _provenance_existing

    if not _skip_discovery_gates and len(session_state.get_discovered_apis()) == 0:
        if write_enabled:
            # WRITE path: hard gate -- discovery is required before any write.
            # Write isolation is non-negotiable; issue #80 leaves this unchanged.
            _log_preflight_reject(
                op_id, seq, time.monotonic() - t_start,
                "api_discovery_required",
                "No APIs discovered yet -- call start() / get_object_api() / search_by_capability() first.",
            )
            # Issue #29: inline get_object_api for the top entities we can spot in
            # the submitted code, so the LLM gets the real method shapes in the
            # rejection itself and can recover in one round-trip instead of three.
            candidates = detect_candidate_entities(code_tree, api_idx, limit=3)
            inline = _inline_discovery_docs(candidates, api_idx) if candidates else {}
            if inline:
                message = (
                    "Discovery required before a WRITE run, but I ran get_object_api "
                    "for the entities I detected in your code -- see _inline_discovery. "
                    "Use these method/property shapes and resubmit.\n\n"
                    "(You can also call start(task='...'), get_object_api(object_type='...'), "
                    "or search_by_capability(query='...') for additional entities.)"
                )
            else:
                message = (
                    "No APIs have been discovered yet. Before running WRITE code, you "
                    "MUST use one of these tools first:\n"
                    "1. start(task='...') - discovers relevant APIs automatically\n"
                    "2. get_object_api(object_type='...') - get API for specific object\n"
                    "3. search_by_capability(query='...') - search for APIs by description\n\n"
                    "This prevents using incorrect/hallucinated method names."
                )
            extras: Dict[str, Any] = {
                "hint": (
                    "Apply the method/property shapes from _inline_discovery and resubmit."
                    if inline else
                    "Call get_object_api() for each object/operation you use "
                    "(FLExProject, LexEntryOperations, etc.), then write code using "
                    "those discovered APIs."
                ),
                "session": session_state.summary(),
                "op_id": op_id,
                "detected_candidates": candidates,
            }
            if inline:
                extras["_inline_discovery"] = inline
            # Issue #28: wrap the rejection with the retry-loop detector so
            # repeated api_discovery_required failures surface _assistance hints.
            return _attach_assistance_if_loop(
                error_response(
                    "api_discovery_required",
                    message,
                    **extras,
                ),
                error_code="api_discovery_required",
                code_size_bytes=_code_size_bytes,
            )
        else:
            # READ-ONLY (issue #80): a turn-1 zero-discovery run is no longer a
            # hard error. Fall through to the per-entity gate below, which
            # auto-discovers qualifying entities (and executes) or emits a
            # graceful discovery redirect for the residual -- a gentle nudge,
            # not a failure.
            get_operations_logger().info(
                "[DISCOVERY] read-only run, zero prior discovery -- deferring to "
                "per-entity auto-discovery/redirect instead of a hard reject (issue #80)."
            )

    # Per-entity gate: even after some discovery has happened, reject code that
    # references Operations classes / project accessors the assistant never
    # validated via get_object_api. This is what catches the post-Op-1 drift
    # where the assistant pivots to POSOperations / project.Senses without
    # discovering them.
    #
    # Issue #47: on READ-ONLY runs, entities that pass the resolve criterion
    # (active api_mode table + unambiguous accessor-to-ops mapping) are
    # auto-discovered (added to auto_discovered_apis, NOT validated_apis) and
    # we fall through to execution instead of rejecting.  On WRITE runs the
    # hard gate fires unconditionally -- write isolation is non-negotiable.
    if not _skip_discovery_gates:
        undiscovered_check = detect_undiscovered_entities(code_tree, session_state, api_idx)
        if undiscovered_check["has_undiscovered"]:
            undiscovered_list: List[str] = undiscovered_check.get("undiscovered") or []

            if not write_enabled:
                # READ-ONLY path: attempt auto-discovery for qualifying entities.
                # Filter to entities not already auto-discovered this session
                # (count==1: second read run should NOT re-fire).
                new_undiscovered = [
                    e for e in undiscovered_list
                    if not session_state.was_auto_discovered(e)
                ]
                qualifying = _resolve_for_auto_discovery(new_undiscovered, api_idx)

                # Also filter previously-auto-discovered entities -- they are
                # already in auto_discovered_apis so satisfy the count==1 rule.
                # The entity is considered "satisfied for this read run" if it
                # was auto-discovered in a prior run OR qualifies now.
                # Intentionally sticky for the session (count==1, issue #47):
                # once an entity was auto-discovered on a prior read run it is
                # considered satisfied for ALL subsequent read runs in this
                # session, even if the index changes between runs.  Not
                # re-qualified because re-qualification would violate the
                # single-fire contract and could silently reopen a write gate
                # for an entity whose docs the user has already seen.
                previously_auto = [
                    e for e in undiscovered_list
                    if session_state.was_auto_discovered(e)
                ]
                # Entities that cannot be auto-discovered (not in entity table /
                # accessor-map miss / cap exceeded) still need human discovery.
                auto_granted = set(qualifying) | set(previously_auto)
                still_undiscovered = [e for e in undiscovered_list if e not in auto_granted]

                if not still_undiscovered:
                    # All undiscovered entities were either already auto-discovered
                    # or qualify for auto-discovery now.  Grant them, build inline
                    # docs, and fall through.
                    for entity in qualifying:
                        session_state.record_auto_discovered_api(entity)
                    if qualifying:
                        _auto_discovered_entities = qualifying
                        _auto_discovery_inline = _inline_discovery_docs(
                            qualifying, api_idx, limit=_AUTO_DISCOVER_CAP
                        )
                        _discovery_note = (
                            f"Auto-discovered {len(qualifying)} entity/entities on this "
                            f"READ-ONLY run: {', '.join(qualifying)}. "
                            f"These entities will re-trigger the undiscovered_entity gate "
                            f"on the first WRITE run (write-gate isolation, issue #47). "
                            f"Call flextools_get_object_api to promote them to validated_apis."
                        )
                        get_operations_logger().info(
                            f"[AUTO-DISCOVER] read-only: granted {qualifying} (cap={_AUTO_DISCOVER_CAP})"
                        )
                    # Fall through to execution (no rejection).
                else:
                    # Issue #80: some entities cannot be auto-discovered, but on a
                    # READ-ONLY run this is a GENTLE REDIRECT, not an error. There is
                    # no DB-safety risk; we simply couldn't resolve the API shapes
                    # ourselves. Inline what docs we can, add capability-search hits
                    # for any guessed methods, and ask the model to apply + resubmit.
                    # (Grant the entities we DID resolve so a resubmit doesn't re-fire
                    #  the gate for those.)
                    for entity in qualifying:
                        session_state.record_auto_discovered_api(entity)
                    inline = _inline_discovery_docs(
                        list(dict.fromkeys(
                            still_undiscovered
                            + (undiscovered_check.get("imported_undiscovered") or [])
                        )),
                        api_idx,
                    )
                    cap_query = _build_capability_query(
                        code_tree, still_undiscovered, user_intent
                    )
                    capability_suggestions = _search_capability_inline(cap_query, api_idx)
                    return _graceful_discovery_redirect(
                        op_id=op_id,
                        seq=seq,
                        duration_s=time.monotonic() - t_start,
                        reason="undiscovered_entity",
                        message=(
                            "I couldn't auto-resolve every API your code uses "
                            f"({', '.join(still_undiscovered)}), so I looked up what I "
                            "could -- see _inline_discovery"
                            + (" and capability_suggestions" if capability_suggestions else "")
                            + ". Apply those shapes and resubmit. Your code was NOT run "
                            "(this is a workflow redirect, not an error). Calling "
                            "get_object_api / search_by_capability first avoids this hop."
                        ),
                        undiscovered=still_undiscovered,
                        inline=inline,
                        capability_suggestions=capability_suggestions,
                        code_size_bytes=_code_size_bytes,
                    )
            else:
                # WRITE path: hard gate -- no auto-discovery, no exceptions.
                # This also fires for entities that were only auto-discovered on a
                # prior read run (they are NOT in validated_apis by design).
                _log_preflight_reject(
                    op_id, seq, time.monotonic() - t_start,
                    "undiscovered_entity",
                    f"undiscovered={undiscovered_list}",
                )
                # Issue #20: inline get_object_api docs when the undiscovered
                # entity is explicitly imported from flexicon. Single round-trip
                # recovery -- the LLM sees the rejection AND the method/property
                # shapes in the same payload, no second tool call needed.
                extras: Dict[str, Any] = {
                    "undiscovered": undiscovered_list,
                    "imported_undiscovered": undiscovered_check.get("imported_undiscovered", []),
                    "hint": "Call flextools_get_object_api for each listed entity, then re-run.",
                    "session": session_state.summary(),
                    "op_id": op_id,
                }
                inline = _inline_discovery_docs(
                    undiscovered_check.get("imported_undiscovered") or [],
                    api_idx,
                )
                if inline:
                    extras["_inline_discovery"] = inline
                # Issue #28: wrap the rejection with the retry-loop detector so
                # repeated undiscovered_entity failures surface _assistance hints.
                return _attach_assistance_if_loop(
                    error_response(
                        "undiscovered_entity",
                        undiscovered_check["suggestion"],
                        **extras,
                    ),
                    error_code="undiscovered_entity",
                    code_size_bytes=_code_size_bytes,
                )

    # Note: Output mechanism check removed - both print() and report.Info() work in unified runner
    # The SimpleReporter provides both mechanisms transparently

    # Check for undefined variables that indicate hallucinated/internal names
    # Pass pre-parsed AST to avoid re-parsing
    undefined_check = detect_undefined_variables(code, code_tree)
    if undefined_check["has_undefined"]:
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "undefined_variables",
            f"undefined_vars={undefined_check.get('undefined_vars')}",
        )
        return _attach_assistance_if_loop(
            error_response(
                "undefined_variables",
                undefined_check["suggestion"],
                undefined_vars=undefined_check["undefined_vars"],
                guidance="All variables must be either: (1) imported from a module, (2) defined in your code, or (3) provided by FlexTools (project, report, modifyAllowed). Do not use internal MCP variable names.",
                op_id=op_id,
            ),
            error_code="undefined_variables",
            code_size_bytes=_code_size_bytes,
        )

    # Check for missing Operations class imports
    missing_ops_check = detect_missing_operations_imports(code, api_mode)
    if missing_ops_check["has_missing"]:
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "missing_imports",
            f"missing_imports={missing_ops_check.get('missing_imports')} api_mode={api_mode}",
        )
        return _attach_assistance_if_loop(
            error_response(
                "missing_imports",
                missing_ops_check["suggestion"],
                missing_imports=missing_ops_check["missing_imports"],
                api_mode=api_mode,
                guidance="Add the import statement shown above to the top of your code.",
                op_id=op_id,
            ),
            error_code="missing_imports",
            code_size_bytes=_code_size_bytes,
        )

    # Check for wrong library imports
    wrong_imports_check = detect_wrong_library_imports(code, api_mode)
    if wrong_imports_check["has_wrong_imports"]:
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "wrong_library_imports",
            f"wrong_imports={wrong_imports_check.get('wrong_imports')} api_mode={api_mode}",
        )
        # Issue #54: populate affected_symbols -- the specific names imported
        # from the wrong library module(s).  Parse from the code AST so the LLM
        # sees exactly which symbols need to be re-imported under the right module.
        _affected_symbols: List[str] = []
        if code_tree:
            _wrong_mods = set(wrong_imports_check.get("wrong_imports") or [])
            for _node in ast.walk(code_tree):
                if isinstance(_node, ast.ImportFrom):
                    _mod = _node.module or ""
                    if any(_mod == wm or _mod.startswith(wm + ".") for wm in _wrong_mods):
                        _affected_symbols.extend(
                            alias.name for alias in _node.names
                        )
        return _attach_assistance_if_loop(
            error_response(
                "wrong_library_imports",
                wrong_imports_check["suggestion"],
                wrong_imports=wrong_imports_check["wrong_imports"],
                api_mode=api_mode,
                affected_symbols=_affected_symbols or None,
                guidance=f"Ensure all imports match your selected API mode. You selected '{api_mode}' mode.",
                op_id=op_id,
            ),
            error_code="wrong_library_imports",
            code_size_bytes=_code_size_bytes,
        )

    # Pre-flight: catch project.<accessor>/<method> typos before subprocess launch.
    # Conservative: only rejects when difflib finds a high-confidence match
    # (cutoff 0.7) -- unrecognized names with no close match are passed through
    # to runtime so we don't block valid direct-project methods we don't index.
    chain_check = detect_invalid_project_chains(code_tree, api_idx)
    if chain_check["has_invalid"]:
        # Issue #46: attempt safe typo auto-fix for read-only runs.
        if effective_auto_fix:
            _af_typo = _try_auto_fix_typos(code, chain_check["issues"])
            if _af_typo is not None:
                _patched_typo = _af_typo["patched_code"]
                _typo_fix_records = _af_typo["fixes"]
                if _validate_patched_code(_patched_typo, api_idx, casting_index):
                    _orig_sha_t = hashlib.sha256(code.encode("utf-8", errors="replace")).hexdigest()[:12]
                    _patched_sha_t = hashlib.sha256(_patched_typo.encode("utf-8", errors="replace")).hexdigest()[:12]
                    get_operations_logger().info(
                        f"[AUTO-FIX] typo: applied {len(_typo_fix_records)} correction(s). "
                        f"original_sha256={_orig_sha_t} patched_sha256={_patched_sha_t}"
                    )
                    session_state.record_op_signal(error_code=None, code_size_bytes=_code_size_bytes)
                    code = _patched_typo
                    code_tree = ast.parse(code)
                    chain_check = detect_invalid_project_chains(code_tree, api_idx)
                    # Merge with any prior casting auto-fixes for the final note
                    _merged_fixes: List[Dict[str, Any]] = (
                        (_auto_fixes_applied + _typo_fix_records)
                        if _auto_fixes_applied is not None
                        else _typo_fix_records
                    )
                    _auto_fixes_applied = _merged_fixes
                    _auto_fix_note = _build_auto_fix_note(_merged_fixes, source_hint="<submitted code>")
                else:
                    get_operations_logger().info(
                        "[AUTO-FIX] typo: patch did not pass re-preflight; falling back to rejection"
                    )

        if chain_check["has_invalid"]:
            _log_preflight_reject(
                op_id, seq, time.monotonic() - t_start,
                "invalid_api_chain",
                f"issues={chain_check.get('issues')}",
            )
            return _attach_assistance_if_loop(
                error_response(
                    "invalid_api_chain",
                    chain_check["suggestion"],
                    issues=chain_check["issues"],
                    guidance="Replace each flagged expression with the suggested correct name and re-run.",
                    op_id=op_id,
                ),
                error_code="invalid_api_chain",
                code_size_bytes=_code_size_bytes,
            )

    timeout_seconds = args.get("timeout_seconds", 300)

    # Determine three-tier injection strategy based on pre-flight results
    # Tier 1 (none): No casting issues → Skip helper injection (lightweight)
    # Tier 2 (minimal): Issues found but handled → Inject only needed helpers (balanced)
    # Tier 3 (full): Defensive mode → Inject full suite (heavy but safest)
    injection_tier = casting_check.get("injection_tier", "full")  # Default to full for safety
    helpers_needed = casting_check.get("helpers_needed", set())  # Set of specific helpers

    # Operation Start was logged at the top of handle_run_module; now that
    # pre-flight has passed, append the casting/injection telemetry and an
    # explicit "preflight passed" marker so a failure later in the subprocess
    # can be told apart from a failure that never made it past validation.
    logger = get_operations_logger()
    if (casting_check.get("casting_issues") or []) or injection_tier != "none" or helpers_needed:
        logger.info(
            f"Preflight casting: issues={len(casting_check.get('casting_issues') or [])} "
            f"tier={injection_tier} helpers={sorted(helpers_needed) if helpers_needed else '[]'}"
        )
        for issue in (casting_check.get("casting_issues") or [])[:10]:
            logger.debug(
                f"  casting: line={issue.get('line')} property={issue.get('property')} "
                f"pattern={issue.get('pattern','')[:80]!r}"
            )
    logger.info(f"Preflight:       passed (tier={injection_tier})")

    # Build warnings
    warnings = []
    if write_enabled:
        warnings.extend([
            "*** WRITE MODE ENABLED ***",
            "Changes WILL be made to the database!",
            "Make sure you have a backup of your project!",
            ""
        ])
    else:
        warnings.extend([
            "Running in READ-ONLY mode (dry-run)",
            "No changes will be made to the database.",
            "Set write_enabled=True to enable modifications.",
            ""
        ])

    # Create the runner script that will be executed in a subprocess
    # (Large script template - hardcoded imports to avoid placeholder/indentation issues)
    runner_script = '''# -*- coding: utf-8 -*-
"""FlexTools Module Runner - Generated by FlexToolsMCP"""
import sys
import json
import os
import traceback
import types

# Reconfigure stdout/stderr to UTF-8 BEFORE any print() runs.
# Without this, messages containing non-cp1252 characters (Yi, IPA, tones, ...)
# raise UnicodeEncodeError mid-print, killing the result-marker output and
# producing a silent failure. Must run before SimpleReporter prints anything.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    # reconfigure is Python 3.7+; fall back for older runtimes / detached streams.
    import codecs
    if getattr(sys.stdout, "buffer", None):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")
    if getattr(sys.stderr, "buffer", None):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, errors="replace")

# Create fake flextoolslib module
flextoolslib = types.ModuleType('flextoolslib')

# FlexTools module documentation keys
flextoolslib.FTM_Name = "FTM_Name"
flextoolslib.FTM_Version = "FTM_Version"
flextoolslib.FTM_ModifiesDB = "FTM_ModifiesDB"
flextoolslib.FTM_Synopsis = "FTM_Synopsis"
flextoolslib.FTM_Description = "FTM_Description"
flextoolslib.FTM_Help = "FTM_Help"

# Minimal FlexToolsModuleClass
class FlexToolsModuleClass:
    def __init__(self, runFunction=None, docs=None, configuration=None):
        self.runFunction = runFunction
        self.docs = docs or {}
        self.configuration = configuration or []

    def Run(self, project, report, modifyAllowed=False):
        if self.runFunction:
            self.runFunction(project, report, modifyAllowed)

    def Help(self):
        return self.docs.get(flextoolslib.FTM_Description, "")

flextoolslib.FlexToolsModuleClass = FlexToolsModuleClass
sys.modules['flextoolslib'] = flextoolslib

# Simple Reporter Class - mimics FLExTools FTReporter
# Outputs to console AND collects messages for structured response
class SimpleReporter:
    INFO = 0
    WARNING = 1
    ERROR = 2
    BLANK = 3
    TYPE_NAMES = ["INFO", "WARNING", "ERROR", "BLANK"]
    MAX_MESSAGES = 10000  # Prevent unbounded memory growth from verbose operations

    def __init__(self, max_messages=None):
        self.messages = []
        self.messageCounts = [0, 0, 0, 0]
        self.max_messages = max_messages or self.MAX_MESSAGES
        self.dropped_message_count = 0

    def _report(self, msg_type, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)

        # Enforce message buffer limit (keep most recent messages)
        if len(self.messages) < self.max_messages:
            self.messages.append({
                "type": self.TYPE_NAMES[msg_type],
                "message": msg,
                "ref": ref
            })
        else:
            # Buffer full - drop oldest message and track it
            self.messages.pop(0)
            self.messages.append({
                "type": self.TYPE_NAMES[msg_type],
                "message": msg,
                "ref": ref
            })
            self.dropped_message_count += 1

        self.messageCounts[msg_type] += 1

        # Print to console for immediate feedback (transparent reporting)
        if msg_type == self.INFO:
            print("[INFO] {}".format(msg))
        elif msg_type == self.WARNING:
            print("[WARN] {}".format(msg))
        elif msg_type == self.ERROR:
            print("[ERROR] {}".format(msg))
        elif msg_type == self.BLANK:
            print()

        # Print reference if provided
        if ref:
            print("       {}".format(ref))

    def Info(self, msg, ref=None):
        self._report(self.INFO, msg, ref)

    def Warning(self, msg, ref=None):
        self._report(self.WARNING, msg, ref)

    def Error(self, msg, ref=None):
        self._report(self.ERROR, msg, ref)

    def Blank(self):
        self._report(self.BLANK, "", None)

    def Debug(self, msg, ref=None):
        """Debug messages (only printed if DEBUG env var set)"""
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)

        # Enforce message buffer limit for debug messages too
        if len(self.messages) < self.max_messages:
            self.messages.append({
                "type": "DEBUG",
                "message": msg,
                "ref": ref
            })
        else:
            # Buffer full - drop oldest message
            self.messages.pop(0)
            self.messages.append({
                "type": "DEBUG",
                "message": msg,
                "ref": ref
            })
            self.dropped_message_count += 1

        import os
        if os.getenv("DEBUG"):
            print("[DEBUG] {}".format(msg))
            if ref:
                print("        {}".format(ref))

    def ProgressStart(self, max_val, msg=None):
        pass

    def ProgressUpdate(self, value):
        pass

    def ProgressStop(self):
        pass

    def FileURL(self, fname):
        import pathlib
        return pathlib.Path(os.path.abspath(fname)).as_uri()

    def Result(self, data):
        """Issue #35: return structured data from a user script.

        Serializes `data` as JSON and stores it for inclusion in the response
        envelope under `result_data`. Multiple calls overwrite (last-wins).
        Size cap: 1 MB serialized. Raises ValueError if exceeded.
        """
        try:
            payload = json.dumps(data, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("report.Result: data is not JSON-serializable: {}".format(exc))
        _MAX_RESULT_BYTES = 1 * 1024 * 1024  # 1 MB
        if len(payload.encode("utf-8")) > _MAX_RESULT_BYTES:
            raise ValueError(
                "report.Result: payload exceeds 1 MB limit ({} bytes). "
                "Consider writing to a file for very large outputs.".format(len(payload.encode("utf-8")))
            )
        print("===FLEXTOOLS_USER_RESULT===")
        print(payload)


def run_module():
    result = {
        "success": False,
        "project": PROJECT_NAME,
        "write_enabled": WRITE_ENABLED,
        "messages": [],
        "summary": {},
        "error": None
    }

    project = None

    try:
        # API Mode-specific imports
        from flexicon import FLExInitialize, FLExCleanup, FLExProject

        FLExInitialize()

        # Open project
        project = FLExProject()
        try:
            project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED, undoable=UNDOABLE)
        except Exception as e:
            result["error"] = "Failed to open project '{}': {}".format(PROJECT_NAME, str(e))
            return result

        # Create reporter
        report = SimpleReporter()

        # FLEx uses '***' as placeholder for empty/unset multilingual string values
        FLEX_EMPTY_PLACEHOLDER = "***"

        def is_empty_multistring(text):
            if text is None:
                return True
            if not isinstance(text, str):
                text = str(text)
            text = text.strip()
            return text == "" or text == FLEX_EMPTY_PLACEHOLDER

        def find_writing_system(project, query):
            """
            Find a writing system by name, tag, or partial match.

            Args:
                project: FLExProject instance
                query: String to search for (e.g., "pyn", "Pinyin", "zh-CN")

            Returns:
                Writing system handle if found, None otherwise
                Also searches display names and language tags

            Usage:
                ws_handle = find_writing_system(project, "pyn")
                if ws_handle:
                    text = project.WritingSystems.GetDisplayName(ws_handle)
                    print(f"Found: {text}")
            """
            try:
                query_lower = query.lower()
                all_ws = list(project.WritingSystems.GetAll())

                # Search for exact match first
                for ws in all_ws:
                    try:
                        display_name = project.WritingSystems.GetDisplayName(ws)
                        language_tag = project.WritingSystems.GetLanguageTag(ws)

                        if (query_lower == display_name.lower() or
                            query_lower == language_tag.lower()):
                            return ws
                    except:
                        pass

                # Then search for substring match
                for ws in all_ws:
                    try:
                        display_name = project.WritingSystems.GetDisplayName(ws)
                        language_tag = project.WritingSystems.GetLanguageTag(ws)

                        if (query_lower in display_name.lower() or
                            query_lower in language_tag.lower()):
                            return ws
                    except:
                        pass

                return None
            except Exception as e:
                return None

        def list_writing_systems(project):
            """
            List all available writing systems with their names and tags.

            Returns:
                List of dicts with 'name' and 'tag' keys

            Usage:
                for ws_info in list_writing_systems(project):
                    print(f"{ws_info['name']} ({ws_info['tag']})")
            """
            try:
                all_ws = list(project.WritingSystems.GetAll())
                result = []

                for ws in all_ws:
                    try:
                        display_name = project.WritingSystems.GetDisplayName(ws)
                        language_tag = project.WritingSystems.GetLanguageTag(ws)
                        result.append({
                            'name': display_name,
                            'tag': language_tag
                        })
                    except:
                        pass

                return result
            except Exception as e:
                return []

        # Execute the module code in a namespace
        # Expose both `write_enabled` and `modifyAllowed` so top-level code can
        # call its own helper (e.g. `MyMain(project, report, write_enabled)`)
        # without a NameError. The standard FLExTools entry point still receives
        # WRITE_ENABLED as the third positional argument when `Main` is detected.
        module_namespace = {
            "__name__": "__flextools_module__",
            "__file__": "module.py",
            "is_empty_multistring": is_empty_multistring,
            "FLEX_EMPTY_PLACEHOLDER": FLEX_EMPTY_PLACEHOLDER,
            "find_writing_system": find_writing_system,
            "list_writing_systems": list_writing_systems,
            "project": project,
            "report": report,
            "write_enabled": WRITE_ENABLED,
            "modifyAllowed": WRITE_ENABLED,
        }

        # Execute the module code to define Main and FlexToolsModule, or run bare code
        exec(MODULE_CODE, module_namespace)

        # Find and call Main function, or accept bare code
        if "Main" in module_namespace:
            module_namespace["Main"](project, report, WRITE_ENABLED)
        elif "FlexToolsModule" in module_namespace:
            module_namespace["FlexToolsModule"].Run(project, report, WRITE_ENABLED)
        # else: bare code already executed at line 978 during exec(MODULE_CODE, module_namespace)

        # Issue #16: log LCM UndoableActionCount so callers can verify that
        # bulk-mutation loops committed the expected number of actions. If the
        # count is much lower than expected, the UoW likely hit an undocumented
        # cap and the caller should re-run on the residual set.
        if WRITE_ENABLED:
            try:
                ah = project.project.ActionHandlerAccessor
                lcm_action_count = getattr(ah, "UndoableActionCount", None)
                if lcm_action_count is not None:
                    result["lcm_undoable_action_count"] = int(lcm_action_count)
            except Exception:
                pass

        # Collect results
        result["success"] = True
        result["messages"] = report.messages
        result["summary"] = {
            "info_count": report.messageCounts[SimpleReporter.INFO],
            "warning_count": report.messageCounts[SimpleReporter.WARNING],
            "error_count": report.messageCounts[SimpleReporter.ERROR],
            "total_messages": len(report.messages)
        }
        # Include buffer overflow warning if messages were dropped
        if report.dropped_message_count > 0:
            result["summary"]["dropped_messages"] = report.dropped_message_count
            result["summary"]["note"] = "Output exceeded maximum buffer size. Most recent {} messages retained.".format(report.max_messages)

    except Exception as e:
        error_msg = str(e)
        if error_msg.startswith("RESULTS:"):
            result["success"] = True
            result["output"] = error_msg[8:].strip()
        else:
            result["error"] = "Execution error: {}\\n{}".format(error_msg, traceback.format_exc())

    finally:
        if project:
            try:
                project.CloseProject()
            except:
                pass
        try:
            FLExCleanup()
        except:
            pass

    return result


if __name__ == "__main__":
    result = run_module()
    print("===FLEXTOOLS_RESULT_JSON===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''

    # Escape the code for embedding in the script
    escaped_code = repr(code)

    # Note: API mode imports are now hardcoded in the template (flexicon)

    # Create the complete script with configuration
    full_script = '''# Configuration
PROJECT_NAME = {project_name}
WRITE_ENABLED = {write_enabled}
UNDOABLE = {undoable}
MODULE_CODE = {code}

{runner_script}
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
        undoable=repr(undoable),
        code=escaped_code,
        runner_script=runner_script
    )

    # Write to temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(full_script)
            temp_script_path = f.name
    except Exception as e:
        err_msg = "Failed to create temporary script: {}".format(str(e))
        _log_operation_failure(
            op_id=op_id, seq=seq, duration_s=time.monotonic() - t_start,
            error=err_msg, error_type=type(e).__name__,
        )
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": err_msg,
            "warnings": warnings,
            "op_id": op_id,
        }, indent=2))]

    try:
        # Determine if we need the write lock
        # Use index-based certification as primary, regex-based as fallback
        # Only lock if: write_enabled=True AND script is NOT certified readonly
        is_mutating_script = (not cert["is_certified_readonly"]) or cud_info["is_cud"]
        needs_lock = write_enabled and is_mutating_script

        # Issue #33: fail fast if a .fwdata.lock file exists AND we intend to mutate.
        # Read-only probes are allowed through to LCM, which permits shared-project
        # access when FLEx has the database open in shared mode. Only an exclusive
        # write would actually collide, so we gate the pre-flight on write intent
        # and let LCM arbitrate the rest (LcmFileLockedException is caught downstream).
        if needs_lock:
            try:
                from ..project_discovery import check_project_locked
            except (ImportError, ValueError):
                from server.project_discovery import check_project_locked
            _lock_path = check_project_locked(project_name)
            if _lock_path is not None:
                _lock_msg = (
                    f"Project '{project_name}' is locked by FieldWorks (found "
                    f"{_lock_path.name}) and this script requests write access. "
                    f"Close FieldWorks or run the script read-only, then retry."
                )
                _log_preflight_reject(op_id, seq, time.monotonic() - t_start, "project_locked", _lock_msg)
                return _attach_assistance_if_loop(
                    error_response(
                        "project_locked",
                        _lock_msg,
                        guidance="Close FieldWorks (or delete the .lock file only if no FW process is running), then retry. Read-only operations do not require closing FieldWorks.",
                        op_id=op_id,
                    ),
                    error_code="project_locked",
                    code_size_bytes=_code_size_bytes,
                )

        if needs_lock:
            # Serialize CUD operations on same project to prevent database corruption
            write_lock = get_project_write_lock(project_name)
            async with write_lock:
                result = await run_script_async(
                    temp_script_path,
                    timeout_seconds=timeout_seconds
                )
        else:
            # No lock needed: read-only or metadata-only operations
            result = await run_script_async(
                temp_script_path,
                timeout_seconds=timeout_seconds
            )

        stdout = result["stdout"]
        stderr = result["stderr"]

        # Handle timeout case
        if result["timeout"]:
            err_msg = f"Execution timeout: script exceeded {timeout_seconds} seconds"
            _log_operation_failure(
                op_id=op_id, seq=seq, duration_s=time.monotonic() - t_start,
                error=err_msg, error_type="Timeout", stderr=stderr,
            )
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": err_msg,
                "warnings": warnings,
                "op_id": op_id,
            }, indent=2))]

        # Issue #35: extract user result payload (report.Result) before the main envelope.
        _user_result_sentinel = "===FLEXTOOLS_USER_RESULT==="
        _user_result_data = None
        if _user_result_sentinel in stdout:
            _ur_start = stdout.index(_user_result_sentinel) + len(_user_result_sentinel)
            _ur_end = stdout.find("===FLEXTOOLS_RESULT_JSON===", _ur_start)
            _ur_raw = (stdout[_ur_start:_ur_end] if _ur_end != -1 else stdout[_ur_start:]).strip()
            try:
                _user_result_data = json.loads(_ur_raw)
            except json.JSONDecodeError:
                _user_result_data = _ur_raw

        # Parse the JSON result from stdout
        if "===FLEXTOOLS_RESULT_JSON===" in stdout:
            json_start = stdout.index("===FLEXTOOLS_RESULT_JSON===") + len("===FLEXTOOLS_RESULT_JSON===")
            json_str = stdout[json_start:].strip()
            try:
                execution_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                execution_result = {
                    "success": False,
                    "error": "Failed to parse result JSON: {}".format(str(e)),
                    "error_type": "JSONDecodeError",
                    "raw_output": stdout
                }
        else:
            execution_result = {
                "success": False,
                "error": "No result marker found in output",
                "error_type": "NoResultMarker",
                "raw_output": stdout,
                "stderr": stderr
            }

        # Issue #35: attach user-returned structured payload if present.
        if _user_result_data is not None:
            execution_result["result_data"] = _user_result_data

        # Add warnings, metadata, and optionally the full module code for learning
        execution_result["warnings"] = warnings
        execution_result["exit_code"] = result["returncode"]
        if stderr and not execution_result.get("error"):
            execution_result["stderr"] = stderr
        if args.get("show_code", True):
            execution_result["code"] = code

        # Include write certification result
        execution_result["write_certification"] = {
            "is_certified_readonly": cert["is_certified_readonly"],
            "confidence": cert["confidence"],
            "mutating_calls_detected": [m for m in cert["mutating_calls"] if m.get("is_mutating")],
        }

        # Issues #23 + #27: when the subprocess failed inside OpenProject
        # (path missing, share offline, project locked), enrich the response
        # with a structured diagnostic that points at the actual fix instead
        # of the bare .NET exception string.
        if execution_result.get("error"):
            open_diag = _diagnose_project_open_error(execution_result, project_name)
            if open_diag is not None:
                execution_result["error_code"] = open_diag["error_code"]
                execution_result["help"] = open_diag.get("hint")
                # Promote the diagnosis fields (message override, attempted_path,
                # discovered_at, hint) onto the response payload.
                for key, value in open_diag.items():
                    if key == "error_code":
                        continue
                    if key == "message":
                        # Replace the raw .NET-exception "error" string with the
                        # human-readable diagnosis. Keep the original under
                        # raw_error so debugging info isn't lost.
                        execution_result["raw_error"] = execution_result["error"]
                        execution_result["error"] = value
                        continue
                    execution_result[key] = value

        # Detect polymorphic attribute errors and suggest resolve_property
        if execution_result.get("error") and "has no attribute" in execution_result.get("error", ""):
            _rt_casting_index = api_idx.casting_index if api_idx else None
            polymorphic_info = detect_polymorphic_error(execution_result["error"], _rt_casting_index)
            # Issue #39: Python's own "Did you mean: 'X'?" suffix is authoritative
            # about what exists on the live object, so for a typo it beats any
            # statically-guessed cast. Only trust the polymorphic (cast) path when
            # it produced a CONCRETE rewrite -- otherwise prefer the name
            # suggestion so the LLM self-corrects in one round-trip instead of
            # being told to "resubmit" for a preflight that can't catch a raw-LCM
            # attribute typo.
            native_did_you_mean = extract_python_did_you_mean(execution_result["error"])
            if polymorphic_info["is_polymorphic_error"] and polymorphic_info.get("rewrite"):
                execution_result["polymorphic_error_detected"] = True
                execution_result["error_type"] = "PolymorphicAttributeError"
                execution_result["object_type"] = polymorphic_info["object_type"]
                execution_result["property_name"] = polymorphic_info["property_name"]
                execution_result["help"] = polymorphic_info["suggestion"]
                # Issue #36: attach rewrite + imports so runtime errors carry the
                # same self-healing payload as pre-flight casting rejections.
                execution_result["rewrite"] = polymorphic_info["rewrite"]
                execution_result["imports_needed"] = polymorphic_info["imports_needed"]
            else:
                # Try wrapper-API name suggestions (project.LexEntries -> project.LexEntry,
                # GetPOS -> GetPartOfSpeech, etc.)
                hint = detect_unknown_attribute_error(execution_result["error"], get_api_index())
                if hint.get("has_suggestion"):
                    execution_result["did_you_mean"] = hint["did_you_mean"]
                    execution_result["help"] = hint["suggestion"]
                elif native_did_you_mean:
                    # Issue #39: surface Python's native suggestion for typos on
                    # any object type (e.g. ILexDb.EntriesOC -> Entries) that our
                    # index-based suggester doesn't cover.
                    execution_result["did_you_mean"] = [native_did_you_mean]
                    execution_result["help"] = (
                        f"'{polymorphic_info.get('property_name')}' does not exist on "
                        f"'{polymorphic_info.get('object_type')}'. Python suggests "
                        f"'{native_did_you_mean}'. Replace it and re-run."
                    )
                elif polymorphic_info["is_polymorphic_error"]:
                    # No concrete rewrite and no name suggestion: fall back to the
                    # resolve_property hint for manual casting.
                    execution_result["polymorphic_error_detected"] = True
                    execution_result["error_type"] = "PolymorphicAttributeError"
                    execution_result["object_type"] = polymorphic_info["object_type"]
                    execution_result["property_name"] = polymorphic_info["property_name"]
                    execution_result["help"] = polymorphic_info["suggestion"]

        # Issue #75: detect pythonnet overload-resolution failures ("No method
        # matches given arguments"). Distinct failure class from the
        # PolymorphicAttributeError gate above (#39/#48) -- this fires when the
        # method genuinely exists but pythonnet can't match the call's
        # argument shape to any of its overloads, not when an attribute is
        # missing. Observed at IFwMetaDataCache.GetFields and
        # IPartOfSpeechFactory.Create.
        elif execution_result.get("error") and "No method matches given arguments" in execution_result.get("error", ""):
            overload_info = detect_overload_resolution_error(execution_result["error"], api_idx)
            if overload_info.get("is_overload_error"):
                execution_result["overload_error_detected"] = True
                execution_result["error_type"] = "OverloadResolutionError"
                execution_result["method_name"] = overload_info.get("method_name")
                execution_result["given_arg_types"] = overload_info.get("given_arg_types")
                execution_result["candidate_overloads"] = overload_info.get("candidates")
                execution_result["help"] = overload_info.get("suggestion")

        # Record API usage patterns for learning
        from ..kernel import get_pattern_tracker
        tracker = get_pattern_tracker()
        if tracker:
            error_msg = execution_result.get("error")
            error_type = execution_result.get("error_type")
            tracker.record_operation(code, execution_result.get("success", False), error_msg, error_type)

        # Extract message counts from execution result
        summary = execution_result.get("summary", {})
        info_count = summary.get("info_count", 0)
        warning_count = summary.get("warning_count", 0)
        error_count = summary.get("error_count", 0)

        # Attach op_id so the LLM can echo it back in a bug report; the
        # matching block in the .log file is keyed off the same id.
        execution_result["op_id"] = op_id

        # Extract structured failure detail before logging so the .log block
        # has full reconstruction info: traceback, report messages, hint.
        # NOTE: report_messages is the FULL list (no cap) so .log post-mortems
        # can replay every Info message; the cap below only trims the response
        # payload returned to the LLM.
        report_messages = execution_result.get("messages") or []

        # Cap report.Info messages in the LLM-facing response (issue #25).
        # Errors/warnings always survive intact -- this only trims info noise.
        capped_messages, info_stats = _cap_info_messages(
            report_messages, max_info_messages
        )
        execution_result["messages"] = capped_messages
        # Surface the cap state on the operation block so post-mortems can
        # see what the LLM actually saw vs. what the runner produced.
        _logger_for_cap = get_operations_logger()
        if info_stats["truncated"] and _logger_for_cap:
            _logger_for_cap.info(
                f"Info-cap:        {info_stats['cap']} "
                f"(truncated from {info_stats['original_info_count']} "
                f"to {info_stats['kept_info_count']})"
            )
        elif _logger_for_cap and info_stats["original_info_count"] > 0:
            _logger_for_cap.info(
                f"Info-cap:        {info_stats['cap']} "
                f"(no truncation; {info_stats['original_info_count']} info messages)"
            )
        if info_stats["truncated"]:
            # Surface the truncation in the response summary so the LLM knows
            # not all info messages were returned.
            summary = execution_result.setdefault("summary", {})
            summary["info_truncated"] = True
            summary["info_returned"] = info_stats["kept_info_count"]
            summary["info_original"] = info_stats["original_info_count"]
            summary["info_cap"] = info_stats["cap"]
        # The runner stuffs `traceback.format_exc()` into the `error` field
        # using a "Execution error: <msg>\n<traceback>" shape. Split it back
        # out so the .log can show the traceback as DEBUG without polluting
        # the single-line INFO summary.
        raw_error = execution_result.get("error") or ""
        traceback_text: Optional[str] = None
        if isinstance(raw_error, str) and "\n" in raw_error:
            first_nl = raw_error.find("\n")
            traceback_text = raw_error[first_nl + 1 :].strip() or None

        polymorphic_hint = None
        if execution_result.get("polymorphic_error_detected"):
            polymorphic_hint = {
                "is_polymorphic_error": True,
                "object_type": execution_result.get("object_type"),
                "property_name": execution_result.get("property_name"),
                # Issue #36: include cast rewrite so runtime errors are self-healing
                "rewrite": execution_result.get("rewrite"),
                "imports_needed": execution_result.get("imports_needed") or [],
            }

        duration_s = time.monotonic() - t_start

        # Log operation completion with rich formatting
        code_size_bytes = len(code.encode("utf-8", errors="replace"))
        if execution_result.get("success"):
            _log_operation_end_success(
                op_id=op_id, seq=seq, duration_s=duration_s,
                info_count=info_count,
                warning_count=warning_count,
                error_count=error_count,
                messages=report_messages,
            )
            # #14 Phase 2: record a local checkpoint when this run actually
            # mutated state under undoable=True. The actual Undo execution
            # happens later in a subprocess, but the LLM-facing record of
            # "what's reversible from this session" lives here.
            if write_enabled and undoable:
                session_state.undo_checkpoints.append({
                    "op_id": op_id,
                    "seq": seq,
                    "timestamp": datetime.now().isoformat(),
                    "project_name": project_name,
                    "info_count": info_count,
                    "warning_count": warning_count,
                    "error_count": error_count,
                })
            # Issue #28: a successful op resets the retry-loop detector --
            # by definition we've broken whatever loop we were stuck in.
            session_state.reset_op_signals()
            # Issue #24: capture top-level helper defs from successful ops
            # into the skeleton closet so they survive across sessions.
            # Best-effort; failures here MUST NOT fail the op.
            _capture_skeletons_after_success(code, op_id, duration_s)
            # Issue #46: attach auto-fix metadata when rewrites were applied.
            # Both fields are written atomically via this helper so neither can
            # be committed to the response without the other being set.
            def _commit_auto_fix_to_result(fixes: List[Dict[str, Any]], note: str) -> None:
                """Atomically attach auto-fix fields to execution_result."""
                assert note is not None, "_auto_fix_note must not be None when committing fixes"
                execution_result[KEY_AUTO_FIXES_APPLIED] = fixes
                execution_result[KEY_AUTO_FIX_NOTE] = note

            if _auto_fixes_applied:
                assert _auto_fix_note is not None, (
                    "_auto_fix_note must be set whenever _auto_fixes_applied is set"
                )
                _commit_auto_fix_to_result(_auto_fixes_applied, _auto_fix_note)
            # Issue #47: attach auto-discovery metadata when read-only auto-
            # discovery fired.  All three fields are written atomically.
            if _auto_discovered_entities:
                execution_result[KEY_AUTO_DISCOVERED] = _auto_discovered_entities
                if _auto_discovery_inline:
                    execution_result[KEY_INLINE_DISCOVERY] = _auto_discovery_inline
                if _discovery_note:
                    execution_result[KEY_DISCOVERY_NOTE] = _discovery_note
            # Diagnostic-report CP3 (spec sections 6.2, 6.5, 10): this success
            # close may be the "workaround taken" resolution of an earlier
            # same-turn reportable failure. build_advisory_for_success_close()
            # is FAIL-OPEN by contract -- it never raises -- so no try/except
            # is needed here; a None return means "nothing to attach".
            _diagnostic_advisory = build_advisory_for_success_close(op_id)
            if _diagnostic_advisory:
                execution_result[KEY_DIAGNOSTIC_REPORT] = _diagnostic_advisory
        else:
            _log_operation_failure(
                op_id=op_id, seq=seq, duration_s=duration_s,
                error=execution_result.get("error"),
                error_type=execution_result.get("error_type"),
                stderr=execution_result.get("stderr") or stderr,
                info_count=info_count,
                warning_count=warning_count,
                error_count=error_count,
                messages=report_messages,
                traceback_text=traceback_text,
                polymorphic_hint=polymorphic_hint,
            )
            # Issue #28: record a runtime-failure signal. Use the structured
            # error_type when available; fall back to a generic bucket.
            runtime_error_code = execution_result.get("error_type") or "runtime_error"
            return _attach_assistance_if_loop(
                [TextContent(type="text", text=json.dumps(execution_result, indent=2, ensure_ascii=False))],
                error_code=runtime_error_code,
                code_size_bytes=code_size_bytes,
            )

        return [TextContent(type="text", text=json.dumps(execution_result, indent=2, ensure_ascii=False))]

    except subprocess.TimeoutExpired:
        err_msg = "Execution timed out after {} seconds".format(timeout_seconds)
        _log_operation_failure(
            op_id=op_id, seq=seq, duration_s=time.monotonic() - t_start,
            error=err_msg, error_type="TimeoutExpired",
        )
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": err_msg,
            "warnings": warnings,
            "op_id": op_id,
        }, indent=2))]

    except Exception as e:
        import traceback as _tb
        err_msg = "Subprocess execution error: {}".format(str(e))
        _log_operation_failure(
            op_id=op_id, seq=seq, duration_s=time.monotonic() - t_start,
            error=err_msg, error_type=type(e).__name__,
            traceback_text=_tb.format_exc(),
        )
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": err_msg,
            "warnings": warnings,
            "op_id": op_id,
        }, indent=2))]

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except:
            pass


async def handle_get_operation_logs(args: dict) -> list[TextContent]:
    """View operation logs and pattern recommendations."""
    log_lines = args.get("log_lines", 50)
    include_patterns = args.get("include_patterns", True)
    errors_only = args.get("errors_only", False)

    result = {
        "log_file": str(get_log_dir() / "operations.log"),
        "patterns_file": str(get_log_dir() / "patterns.json"),
        "recent_logs": [],
        "recommendations": None
    }

    # Read recent log entries
    log_file = get_log_dir() / "operations.log"
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Filter to errors only if requested
            if errors_only:
                lines = [l for l in lines if '| ERROR' in l or '| FAIL' in l or '[FAIL]' in l]

            # Get last N lines
            recent = lines[-log_lines:] if len(lines) > log_lines else lines
            result["recent_logs"] = [line.rstrip() for line in recent]
            result["total_log_lines"] = len(lines)
        except Exception as e:
            result["log_error"] = str(e)
    else:
        result["recent_logs"] = ["(No logs yet - run some operations first)"]

    # Include pattern analysis
    if include_patterns:
        tracker = get_pattern_tracker()
        if tracker:
            tracker.load()
            recommendations = tracker.get_recommendations()

            result["recommendations"] = {
                "preferred_patterns": recommendations.get("preferred_patterns", [])[:10],
                "patterns_to_avoid": recommendations.get("patterns_to_avoid", [])[:10],
                "common_errors_needing_fix": recommendations.get("common_errors_needing_fix", [])[:10]
            }

            # Add summary statistics
            api_patterns = tracker.patterns.get("api_patterns", {})
            total_operations = sum(
                p["success_count"] + p["failure_count"]
                for p in api_patterns.values()
            )
            total_successes = sum(p["success_count"] for p in api_patterns.values())
            total_failures = sum(p["failure_count"] for p in api_patterns.values())

            # Issue #50: merge JSONL-derived aggregates into the statistics block
            jsonl_stats = compute_jsonl_statistics(get_log_dir())
            result["statistics"] = {
                "total_operations": total_operations,
                "total_successes": total_successes,
                "total_failures": total_failures,
                "success_rate": round(total_successes / total_operations * 100, 1) if total_operations > 0 else 0,
                "unique_api_patterns": len(api_patterns),
                "unique_error_patterns": len(tracker.patterns.get("error_patterns", {})),
                # Structured telemetry aggregates (issue #50)
                "first_pass_green_rate": jsonl_stats.get("first_pass_green_rate"),
                "turns_to_green_median": jsonl_stats.get("turns_to_green_median"),
                "rejects_by_error_code": jsonl_stats.get("rejects_by_error_code", []),
            }
        else:
            result["recommendations"] = {}
            jsonl_stats = compute_jsonl_statistics(get_log_dir())
            result["statistics"] = {
                "first_pass_green_rate": jsonl_stats.get("first_pass_green_rate"),
                "turns_to_green_median": jsonl_stats.get("turns_to_green_median"),
                "rejects_by_error_code": jsonl_stats.get("rejects_by_error_code", []),
            }

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
