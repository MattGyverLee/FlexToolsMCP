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

import contextlib
import json
import sys
import subprocess
import tempfile
import os
import ast
import hashlib
import heapq
import time
import itertools
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
    from ..kernel import (
        get_pattern_tracker,
        get_project_write_lock,
        should_skip_discovery_gates,
        discovery_gate_skip_note,
        is_stateless_client_mode,
    )
except ImportError:
    from server.kernel import (
        get_pattern_tracker,
        get_project_write_lock,
        should_skip_discovery_gates,
        discovery_gate_skip_note,
        is_stateless_client_mode,
    )

# Skeleton storage closet (issue #24): persist helper defs from successful ops.
try:
    from .. import skeleton_storage
except ImportError:
    from server import skeleton_storage

try:
    from ..constants import EXECUTION_API_MODE
except ImportError:
    from server.constants import EXECUTION_API_MODE

# Import validators with fallback
try:
    from ..validators import (
        detect_cud_operations, detect_polymorphic_error, detect_flexicon_internal_attribute_error,
        detect_class_id_constant_error,
        detect_undefined_variables,
        detect_missing_operations_imports, detect_wrong_library_imports,
        certify_script_readonly, get_unprotected_write_guidance, detect_casting_needs, validate_server_state,
        detect_unknown_attribute_error, detect_invalid_project_chains,
        detect_partial_module_structure, detect_top_level_main_invocation,
        detect_undiscovered_entities,
        detect_candidate_entities, extract_python_did_you_mean,
        detect_overload_resolution_error, detect_getall_unsafe_idiom,
        detect_interface_attribute_typos,
        _collect_all_imported_names, _accessor_to_ops_map,
        annotate_properties_with_casting, build_casting_notes,
        build_writeability_payload, build_write_certification_payload,
        compute_is_mutating_script, detect_nested_unit_of_work,
        detect_hvo_literal_args,
        detect_deprecated_members, build_deprecated_member_rejection,
        detect_raw_addcustomfield_risk,
    )
except ImportError:
    from server.validators import (
        detect_cud_operations, detect_polymorphic_error, detect_flexicon_internal_attribute_error,
        detect_class_id_constant_error,
        detect_undefined_variables,
        detect_missing_operations_imports, detect_wrong_library_imports, certify_script_readonly, get_unprotected_write_guidance, detect_casting_needs, validate_server_state,
        detect_unknown_attribute_error, detect_invalid_project_chains,
        detect_partial_module_structure, detect_top_level_main_invocation,
        detect_undiscovered_entities,
        detect_candidate_entities, extract_python_did_you_mean,
        detect_overload_resolution_error, detect_getall_unsafe_idiom,
        detect_interface_attribute_typos,
        _collect_all_imported_names, _accessor_to_ops_map,
        annotate_properties_with_casting, build_casting_notes,
        build_writeability_payload, build_write_certification_payload,
        compute_is_mutating_script, detect_nested_unit_of_work,
        detect_hvo_literal_args,
        detect_deprecated_members, build_deprecated_member_rejection,
        detect_raw_addcustomfield_risk,
    )

# The write ladder's shared rungs (parser-check CP4, R-07): the access gate,
# the backup intent and the backup itself, extracted from handle_run_module
# so filing walks the same code. Reached as module attributes so the leaves
# stay patchable. The peer caveat (issue #93 CP4 T4.2) moved with them.
try:
    from .. import write_ladder
    from ..write_ladder import PEER_BACKUP_CAVEAT as _PEER_BACKUP_CAVEAT
except ImportError:
    from server import write_ladder
    from server.write_ladder import PEER_BACKUP_CAVEAT as _PEER_BACKUP_CAVEAT


# Issue #55 (Rung 2): automatic pre-write backup.
try:
    from ..backup import perform_pre_write_backup
except ImportError:
    from server.backup import perform_pre_write_backup

# Import response utilities and HeadlessReport with fallback
try:
    from ...response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

# Import response field constants
from ..response_keys import (
    KEY_STATUS, KEY_MESSAGE, KEY_NEEDS_INPUT, KEY_COMPLETE,
    KEY_QUESTIONS, KEY_PROVIDED,
    KEY_TEMPLATE, KEY_NEXT_STEPS,
    KEY_AUTO_FIXES_APPLIED, KEY_AUTO_FIX_NOTE,
    KEY_AUTO_DISCOVERED, KEY_INLINE_DISCOVERY, KEY_DISCOVERY_NOTE,
    KEY_DIAGNOSTIC_REPORT,
    KEY_DISCOVERY_REDIRECT, KEY_CAPABILITY_SUGGESTIONS, KEY_EXECUTED,
)


def _finalize_run_module_response(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp TOOL-CONTRACT envelope keys on run_module JSON payloads (issue #119).

    Preflight rejections already go through ``error_response`` / discovery
    redirects through ``build_response_with_context``; the subprocess execution
    path returned the raw runner dict without ``_contract`` or ``status``.
    """
    if KEY_STATUS not in payload:
        if payload.get("success") is False:
            payload[KEY_STATUS] = "error"
        else:
            payload[KEY_STATUS] = "ok"
    return build_response_with_context(payload, include_session=True)


def build_effect_check_payload(
    execution_result: Dict[str, Any],
    *,
    write_enabled: bool,
    is_mutating_script: bool,
) -> Optional[Dict[str, Any]]:
    """Issue #143: surface silent no-op writes on mutating runs.

    When preflight already classified the script as mutating but LCM recorded
    zero undoable actions, attach an advisory ``effect_check`` block so callers
    can distinguish success-with-no-exception from success-with-no-mutation.
    """
    if not write_enabled or not is_mutating_script:
        return None
    if not execution_result.get("success"):
        return None
    count = execution_result.get("lcm_undoable_action_count")
    if count is None:
        return None
    try:
        count_int = int(count)
    except (TypeError, ValueError):
        return None
    if count_int != 0:
        return None
    return {
        "signal": "lcm_undoable_action_count",
        "lcm_undoable_action_count": 0,
        "verdict": "no_observable_effect",
        "note": (
            "Preflight classified this run as mutating, but LCM recorded zero "
            "undoable actions. The script reported success without raising, so "
            "a wrapper no-op or wrong collection target may have done nothing."
        ),
    }


# Issue #46: auto-fix config
try:
    from ...config import config_get, AUTO_FIX_ENABLED_KEY, AUTO_FIX_ENABLED_DEFAULT
except (ImportError, ValueError):
    from config import config_get, AUTO_FIX_ENABLED_KEY, AUTO_FIX_ENABLED_DEFAULT

# Issue #55: write-path safety ladder config knob (confirmation). The backup
# knob is read by write_ladder.backup_intent (CP4, R-07).
try:
    from ...config import (
        REQUIRE_WRITE_CONFIRMATION_KEY, REQUIRE_WRITE_CONFIRMATION_DEFAULT,
    )
except (ImportError, ValueError):
    from config import (
        REQUIRE_WRITE_CONFIRMATION_KEY, REQUIRE_WRITE_CONFIRMATION_DEFAULT,
    )

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


# Issue #53: cap the inlined project list so a projects-directory with
# hundreds of entries doesn't bloat every rejection payload.
_AVAILABLE_PROJECTS_CAP = 15


def _available_projects_payload() -> Dict[str, Any]:
    """Build the self-healing `available_projects` block for cold run_module
    rejections (project_not_open / project_name_required -- issue #53).

    Uses the SAME safe enumeration flextools_list_projects uses
    (project_discovery.list_projects) -- directory scan + .fwdata existence
    check only, never opens a project or loads the LCM cache. Capped at
    _AVAILABLE_PROJECTS_CAP names + a total_count so the model can recover
    in one turn without the payload growing unbounded on large projects
    directories.

    NEVER auto-selects a project -- this is purely informational so the
    caller can choose and pass one to project_name explicitly.
    """
    try:
        from ..project_discovery import list_projects
    except ImportError:
        from server.project_discovery import list_projects
    try:
        names, _source = list_projects()
    except Exception:
        # Discovery itself is best-effort here; never let it break the
        # rejection response the caller actually needs.
        names = []
    return {
        "available_projects": names[:_AVAILABLE_PROJECTS_CAP],
        "total_count": len(names),
    }


# ---------------------------------------------------------------------------
# Retired: three-tier casting-helper injection ([#163](https://github.com/MattGyverLee/FlexToolsMCP/issues/163)).
#
# Runner-side injection died at commit d3e55d4 (2026-04-07) when the last call to
# `_get_api_mode_imports` was removed. The restore-vs-retire decision is **retire**:
# preflight casting detection, auto-fix rewrite, and runtime polymorphic hints
# already cover the supported path; the helpers swallow errors in ways that
# contradict the write-path safety guarantee.
#
# `_get_api_mode_imports` / `_get_casting_helpers_code` were deleted here. Archaeology:
# `specs/parser-check-cp2b/reviews/casting-injection-archivist.md`.
#
# `_validate_api_mode` remains for direct probes/tests (#146, #164). It is not
# wired into the runner import seam (`api_mode` is advisory; execution is flexicon-only).
# ---------------------------------------------------------------------------


def _probe_undoable_capability() -> bool:
    """Best-effort preflight probe for flexicon's "per-operation-uow" mode.

    Mirrors the OpenProject-time probe in the generated runner template
    (issue #144): the one-line ``getattr(..., frozenset())`` form flexicon's
    own docstring prescribes for this consumer. Used here only to choose
    which variant of the nested_unit_of_work rejection message to show --
    the actual OpenProject() call happens in the subprocess, not here, so
    this is advisory (e.g. a mismatched flexicon install between the server
    process and the subprocess's venv would only affect message wording,
    never the gate's correctness -- the gate itself is unconditional
    regardless of mode, see the module comment above detect_nested_unit_of_work).
    """
    try:
        import flexicon  # type: ignore
    except Exception:  # noqa: BLE001 -- see below; do not narrow to ImportError
        # Deliberately broad. `import flexicon` runs
        # FLExGlobals.InitialiseFWGlobals() at import time, which raises a
        # BARE Exception ("64bit FieldWorks 9 not found") on any host without
        # a FieldWorks install -- a headless CI runner, or a Windows box with
        # pyflexicon installed but no FLEx. That is not an ImportError, so an
        # `except ImportError` here lets it escape and takes down a caller
        # that only wanted to pick message wording. Same reasoning as
        # tests/test_issue84_project_lexsense_accessor.py::_require_live_flexicon.
        return False
    _caps = getattr(flexicon, "CAPABILITIES", frozenset())
    return "per-operation-uow" in _caps


def _validate_api_mode(api_mode: str) -> Tuple[bool, str]:
    """Validate that the requested API mode libraries are properly installed.

    Args:
        api_mode: One of 'flexlibs_stable', 'flexicon', 'liblcm'

    Returns:
        (is_valid, error_message)
    """
    # Both probes below catch the broad Exception on purpose. flexicon and
    # flexlibs each run FLExGlobals.InitialiseFWGlobals() at import time,
    # which raises a bare Exception ("64bit FieldWorks 9 not found") rather
    # than ImportError when FieldWorks is absent. An installed-but-
    # uninitializable library is exactly the "this mode is unusable here"
    # case this function exists to report, so it must come back as a clean
    # (False, reason) and never as a traceback out of a validation call.
    if api_mode == "flexicon":
        try:
            import flexicon  # type: ignore
        except ImportError as e:
            return False, f"flexicon not found: {e}"
        except Exception as e:  # noqa: BLE001 -- non-ImportError: no FieldWorks
            return False, f"flexicon installed but not initializable: {e}"
        # Issue #146: do not treat version/__version__ as a capability proxy.
        # Old builds can expose version while lacking every token this runner
        # assumes; flexicon.CAPABILITIES is the supported probe surface.
        if getattr(flexicon, "CAPABILITIES", None) is None:
            return False, (
                "flexicon missing CAPABILITIES (upgrade pyflexicon; "
                "version attributes are not a capability probe)"
            )
        return True, ""

    elif api_mode == "flexlibs_stable":
        try:
            import flexlibs  # type: ignore  # noqa: F401  # availability probe
            return True, ""
        except ImportError as e:
            return False, f"flexlibs not found: {e}"
        except Exception as e:  # noqa: BLE001 -- non-ImportError: no FieldWorks
            return False, f"flexlibs installed but not initializable: {e}"

    elif api_mode == "liblcm":
        # LibLCM is optional, validated at runtime
        return True, ""

    return False, f"Unknown API mode: {api_mode}"


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
    user_intent: Optional[str] = None,
    user_request: Optional[str] = None,
    session_id: Optional[str] = None,
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

    `session_id` (issue #62): the stable session-identity anchor from
    `SessionState.configure()`. Stashed alongside the other per-op metadata
    so the JSONL record carries a grouping key that does not change when the
    LLM edits its `user_intent` string mid-session (see
    `op_telemetry.group_records_by_session`).
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
        session_id=session_id,
    )

    if casting_check is not None:
        # Reached by no caller today -- all three call sites omit
        # `casting_check` -- but kept because the shape is right and the
        # caller that wants it is a one-line change. What is NOT kept is the
        # injection tier: nothing injects, so nothing may report a tier.
        logger.info(
            f"Preflight casting: "
            f"issues={len(casting_check.get('casting_issues') or [])}"
        )
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
    set(info_indices[:head_count])
    set(info_indices[-tail_count:]) if tail_count else set()
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




def _require_jsonl_log_dir(log_dir_fn: Optional[Any]) -> Any:
    """Issue #109: refuse silent fallback to the production log directory."""
    if log_dir_fn is None:
        raise TypeError(
            "log_dir_fn is required for JSONL telemetry closes (issue #109). "
            "Pass get_log_dir at production call sites or a tmp-path callable in tests."
        )
    return log_dir_fn

def _log_operation_end_success(
    op_id: str,
    seq: int,
    duration_s: float,
    info_count: int,
    warning_count: int,
    error_count: int,
    messages: Optional[List[Dict[str, Any]]] = None,
    *,
    log_dir_fn: Optional[Any] = None,
) -> None:
    """Close a successful operation block.

    `log_dir_fn` (issue #74): overridable JSONL log-dir resolver, threaded
    through to `_write_jsonl_line` so tests can inject a tmp path instead of
    silently writing synthetic rows into the real `operations.jsonl`. Defaults
    to `None`, which resolves to the module-level `get_log_dir` AT CALL TIME
    (not baked into the signature) so tests that monkeypatch
    `execution.get_log_dir` directly (the pre-existing pattern) keep working
    unchanged alongside tests that pass `log_dir_fn` explicitly.
    """
    log_dir_fn = _require_jsonl_log_dir(log_dir_fn)
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
        log_dir_fn=log_dir_fn,
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
    *,
    log_dir_fn: Optional[Any] = None,
) -> None:
    """Emit the [FAIL] / Messages / Operation End block with diagnostic detail.

    `log_dir_fn` (issue #74): overridable JSONL log-dir resolver, see
    `_log_operation_end_success` for rationale (None default, resolved at
    call time so monkeypatching `execution.get_log_dir` still works).

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
    log_dir_fn = _require_jsonl_log_dir(log_dir_fn)
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
        # Issue #122: preflight is stateless -- identical code resubmitted after
        # a runtime polymorphic miss does NOT gain new casting_issues. Log the
        # actionable hint at ERROR so it survives error-level log filters (#122).
        obj = polymorphic_hint.get("object_type")
        prop = polymorphic_hint.get("property_name")
        guidance = polymorphic_hint.get("help") or polymorphic_hint.get("suggestion")
        if guidance:
            logger.error(
                f"Polymorphic guidance ({obj}.{prop}): {guidance}"
            )
        elif polymorphic_hint.get("rewrite"):
            logger.error(
                f"Polymorphic guidance ({obj}.{prop}): apply rewrite "
                f"{polymorphic_hint.get('rewrite')}"
            )
        else:
            logger.error(
                f"Polymorphic guidance ({obj}.{prop}): cast before accessing "
                f"'{prop}' or call flextools_resolve_property."
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
            log_dir_fn=log_dir_fn,
        )


def _log_writeability_reject(
    cert: Dict[str, Any],
    mutating: List[Dict[str, Any]],
) -> None:
    """Emit the per-issue DEBUG breakdown for an `unprotected_writes` reject.

    Mirrors the casting-reject pattern: an INFO summary plus per-issue DEBUG
    lines so the .log captures WHY writeability failed, not just that it did.
    Without this the reject's `detail` field only carries the first 5 method
    names and the actual line numbers / contexts are lost.

    Issue #82: this is DIAGNOSTIC-ONLY -- it describes a rejection the gate has
    already decided. It must never be able to take down the response it is
    describing, so every failure mode degrades the log instead:

    - The three lists it reads have *different* element shapes.
      `mutating_calls` and `unprotected_liblcm_calls` hold dicts, but
      `raw_lcm_patterns` holds plain formatted strings (`"CREATE (Create())"`)
      extended from `detect_cud_operations()["operations"]`. A copy-pasted
      `p.get("line")` over the string list raised AttributeError here and
      replaced the caller's `unprotected_mutations_detected` guidance with a
      bare `'str' object has no attribute 'get'`.
    - The blanket try/except makes that structural: a future shape drift in any
      of the three lists costs a log line, not the tool result.
    - `get_operations_logger()` is `Optional` and returns None before kernel
      init, which was a second latent path to the same symptom (an opaque
      `'NoneType' object has no attribute 'info'` in place of the guidance).
      No logger simply means no diagnostics to write.
    """
    op_logger = get_operations_logger()
    if op_logger is None:
        return
    try:
        unprotected_lcm = cert.get("unprotected_liblcm_calls", []) or []
        raw_lcm = cert.get("raw_lcm_patterns", []) or []
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
        # Strings, not dicts -- see the shape note in the docstring.
        for p in raw_lcm[:10]:
            op_logger.debug(f"  writeability: raw_lcm_pattern={p!r}")
    except Exception as log_exc:
        # The fallback line is itself best-effort -- if the log backend is the
        # thing that broke, reporting that must not raise either.
        with contextlib.suppress(Exception):
            op_logger.debug(f"  writeability: per-issue logging failed: {log_exc!r}")


def _log_preflight_reject(
    op_id: str,
    seq: int,
    duration_s: float,
    reason_code: str,
    detail: str,
    *,
    casting_signature: Optional[str] = None,
    log_dir_fn: Optional[Any] = None,
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

    `log_dir_fn` (issue #74): overridable JSONL log-dir resolver, threaded
    through to `_write_jsonl_line` so tests calling `_log_preflight_reject`
    directly can inject a tmp path instead of silently writing synthetic
    `test-op-*` rows into the real `operations.jsonl`. Defaults to `None`,
    resolved to the module-level `get_log_dir` AT CALL TIME (not baked into
    the signature) -- existing callers, including tests that monkeypatch
    `execution.get_log_dir` directly, are unaffected.
    """
    log_dir_fn = _require_jsonl_log_dir(log_dir_fn)
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
        log_dir_fn=log_dir_fn,
        casting_signature=casting_signature,
    )


def _log_discovery_redirect(
    op_id: str,
    seq: int,
    duration_s: float,
    reason: str,
    detail: str,
    *,
    log_dir_fn: Optional[Any] = None,
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

    `log_dir_fn` (issue #74): overridable JSONL log-dir resolver, see
    `_log_operation_end_success` for rationale (None default, resolved at
    call time so monkeypatching `execution.get_log_dir` still works).
    """
    log_dir_fn = _require_jsonl_log_dir(log_dir_fn)
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
        log_dir_fn=log_dir_fn,
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
    _log_discovery_redirect(op_id, seq, duration_s, reason, f"undiscovered={undiscovered}", log_dir_fn=get_log_dir)

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
        diag: Dict[str, Any] = {
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

        # Issue #93 CP3 (T3.1-T3.4): sharpen the generic hint above with the
        # CP2 access probe when we can. probe_project_access() is pure
        # filesystem (the .fwdata.lock JSON + SharedSettings\LexiconSettings
        # .plsx) and never opens a project, so it is safe to call from this
        # read-only diagnosis -- but it touches the registry (via
        # get_projects_directory()) and the filesystem, both of which can
        # raise or be unresolvable in ways we haven't enumerated. A
        # diagnosis must never turn a lock error into a crash, so any
        # failure here -- import, probe, or diagnosis -- degrades silently
        # back to the generic hint set above.
        try:
            try:
                from ..project_access import (
                    build_access_remedy,
                    build_lock_diagnosis,
                    probe_project_access,
                )
            except (ImportError, ValueError):
                from server.project_access import (
                    build_access_remedy,
                    build_lock_diagnosis,
                    probe_project_access,
                )
            access = probe_project_access(project_name)
            specific_hint = build_lock_diagnosis(access)
            if specific_hint is not None:
                # build_lock_diagnosis() only returns non-None for
                # "open_exclusive", "held_by_other", and "stale_lock" --
                # "free" / "open_shared" (and anything unrecognized) fall
                # through and keep the generic dict built above.
                holder = access.holder
                extra: Dict[str, Any] = {
                    "hint": specific_hint,
                    "verdict": access.verdict,
                    "sharing_enabled": access.sharing_enabled,
                    "holder_pid": holder.pid if holder else None,
                    "holder_process": holder.process_name if holder else None,
                    # remedy mirrors build_access_remedy()'s own semantics
                    # (only non-None for the two verdicts that block a
                    # WRITE), which is narrower than "hint" on purpose: for
                    # stale_lock there is genuinely nothing the user must
                    # DO, just information that the lock has already been
                    # vacated.
                    "remedy": build_access_remedy(access),
                }
                # Single atomic update so a failure in the block above (e.g.
                # build_access_remedy() raising) can never leave `diag` with
                # some CP3 keys set (verdict/hint/...) but no `remedy` --
                # a third payload shape neither the generic nor CP3 path
                # intends. See specs/shared-mode-access/reviews/cycle5-qc.md
                # P1-1.
                diag.update(extra)
        except Exception as exc:
            _diag_logger = get_operations_logger()
            if _diag_logger is not None:
                _diag_logger.debug(f"CP3 lock diagnosis unavailable: {exc!r}")

        return diag

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


def _api_discovery_required_copy(
    session_state: Any,
    *,
    has_inline_discovery: bool,
) -> Dict[str, Any]:
    """User-facing copy for the write-only api_discovery_required gate (#244).

    Read-only runs may auto-discover entities (issue #47) without adding them to
    ``discovered_apis``. The first WRITE run then hits the zero-discovery gate
    with a misleading "No APIs discovered yet" unless we name the auto-grants.
    """
    auto = sorted(getattr(session_state, "auto_discovered_apis", None) or [])
    auto_joined = ", ".join(auto)

    if auto:
        log_summary = (
            f"Write blocked: auto-discovered but not validated via get_object_api: "
            f"{auto_joined}"
        )
        auto_paragraph = (
            f"During earlier read-only runs, {len(auto)} entit"
            f"{'y was' if len(auto) == 1 else 'ies were'} auto-discovered "
            f"({auto_joined}) — that does not satisfy the write gate. Call "
            f"flextools_get_object_api(object_type=...) for each entity you use "
            f"before resubmitting WRITE code.\n\n"
        )
    else:
        log_summary = (
            "No APIs discovered yet -- call start() / get_object_api() / "
            "search_by_capability() first."
        )
        auto_paragraph = ""

    if has_inline_discovery:
        message = (
            "Discovery required before a WRITE run, but I ran get_object_api "
            "for the entities I detected in your code -- see _inline_discovery. "
            "Use these method/property shapes and resubmit.\n\n"
        )
        if auto_paragraph:
            message += auto_paragraph
        message += (
            "(You can also call start(task='...'), get_object_api(object_type='...'), "
            "or search_by_capability(query='...') for additional entities.)"
        )
        hint = "Apply the method/property shapes from _inline_discovery and resubmit."
        if auto:
            hint += (
                f" Also validate auto-discovered entities via get_object_api: "
                f"{auto_joined}."
            )
    elif auto:
        message = (
            "No APIs have been validated yet for a WRITE run.\n\n"
            + auto_paragraph
            + "Before running WRITE code, you MUST validate APIs explicitly:\n"
            "1. get_object_api(object_type='...') — required for each Operations entity\n"
            "2. start(task='...') — discovers relevant APIs automatically\n"
            "3. search_by_capability(query='...') — search for APIs by description\n\n"
            "Auto-discovery on read-only runs is intentionally separate from validated "
            "discovery; this prevents using incorrect/hallucinated method names on writes."
        )
        hint = (
            f"Call flextools_get_object_api for the auto-discovered entities: "
            f"{auto_joined}."
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
        hint = (
            "Call get_object_api() for each object/operation you use "
            "(FLExProject, LexEntryOperations, etc.), then write code using "
            "those discovered APIs."
        )

    return {
        "message": message,
        "hint": hint,
        "log_summary": log_summary,
        "auto_discovered_pending_validation": auto,
    }


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


# ---------------------------------------------------------------------------
# Issue #49: validate_only mode -- full preflight without execution.
# ---------------------------------------------------------------------------

def _log_validate_only_close(
    op_id: str,
    seq: int,
    duration_s: float,
    status: str,
    fault_gates: List[str],
) -> None:
    """Close a validate_only operation with its own [VALIDATE] log block.

    Deliberately NOT `_log_preflight_reject`: a validate_only call that comes
    back `validation_failed` is the caller opting into red (asking "what's
    wrong?"), not backtracking from a real attempt, so it must NOT be counted
    as a preflight reject in green-rate statistics. Emits telemetry with
    outcome="validate_only" instead, which the JSONL green-rate/reject
    aggregates in op_telemetry.py already ignore.
    """
    logger = get_operations_logger()
    logger.info(f"[VALIDATE] validate_only close: status={status}")
    if fault_gates:
        logger.info(f"  failing_gates={fault_gates}")
    logger.info(f"Duration:        {duration_s:.3f}s")
    logger.info(f"=== Operation #{seq} End ({op_id}) ===")

    _write_jsonl_line(
        op_id=op_id,
        seq=seq,
        outcome="validate_only",
        duration_s=duration_s,
        error_code=None,
        preflight_gate=",".join(fault_gates) if fault_gates else None,
        info_count=0,
        warning_count=0,
        error_count=0,
        assistance_triggered=False,
        log_dir_fn=get_log_dir,
    )


def _detect_casting_needs_compat(
    code: str,
    casting_index: Optional[Dict[str, Any]],
    code_tree: Optional[ast.AST],
    api_idx: Any,
) -> Dict[str, Any]:
    """Issue #121: call `detect_casting_needs` with its new optional
    `api_index` param, but ONLY when there's actually an index to give it.

    Several existing tests monkeypatch `execution_mod.detect_casting_needs`
    with hand-written 3-positional-arg stubs `(code, casting_index, tree)`
    that don't accept a 4th argument at all -- see
    tests/test_issue40_casting_severity.py, tests/test_issue49_validate_only.py,
    tests/test_diagnostic_report_reconstruction.py. Every one of those tests
    also stubs `get_api_index()` to return None, so `api_idx` is None at
    every one of their call sites. Omitting the `api_index` keyword entirely
    when `api_idx` is None keeps those stubs' arity satisfied without
    touching six test files, while still passing it through in the real
    (non-test) path where callers actually hold an APIIndex -- functionally
    identical either way, since `detect_casting_needs`'s own default for
    that parameter is also None.
    """
    if api_idx is not None:
        return detect_casting_needs(code, casting_index, code_tree, api_index=api_idx)
    return detect_casting_needs(code, casting_index, code_tree)


def _has_error_severity_casting_issue(issues: List[Dict[str, Any]]) -> bool:
    """Issue #40 B-1 / #49 B-5: True if ANY casting issue is 'error' severity.

    Shared predicate for the read-only warning-tier downgrade. A
    known-pattern hit (or a genuine attribute typo merged in by
    handle_run_module) is 'error'; an index-derived lookup with no
    corroborating known pattern is 'warning'. handle_run_module (the real
    gate) and _build_validate_only_checks (the dry-run preview) BOTH call
    this -- do not reimplement the severity check at either call site, or
    the two will drift apart again (issue #49 B-5).
    """
    return any((i.get("severity") == "error") for i in issues)


def _compute_casting_decision(
    code: str,
    casting_index: Optional[Dict[str, Any]],
    code_tree: Optional[ast.AST],
    api_idx: Any,
) -> Dict[str, Any]:
    """Issue #39/#40 P1-2 (cycle 5): the SINGLE shared casting-decision
    pipeline. Cycle 4's `handle_run_module` folded
    `detect_interface_attribute_typos` into `casting_issues` and forced
    `severity="error"` at its own call site; `_build_validate_only_checks`'s
    Gate 5 (and the Tier-1 eval runner's own Gate 5) never called
    `detect_interface_attribute_typos` at all. Only the has-error PREDICATE
    (`_has_error_severity_casting_issue`) was shared -- sharing the
    predicate but not the inputs is exactly what produced the P1-2 false
    reassurance (`validate_only` said `passed: True` for code
    `run_module` hard-rejects). Every caller that needs a casting
    verdict -- `handle_run_module`, `_handle_validate_only`'s Gate 5, and
    `tests/evals/preflight_runner.py`'s Gate 5 -- MUST go through this
    function instead of calling `detect_casting_needs` +
    `detect_interface_attribute_typos` separately.

    Returns the same shape as `detect_casting_needs()`, with `casting_issues`
    /`has_casting_issues`/`severity` updated to include any merged-in typo
    issues, plus one new key:
      - has_error_severity: bool -- the shared predicate's verdict, so
        callers never re-derive it (and can't drift) either.
    """
    casting_check = _detect_casting_needs_compat(code, casting_index, code_tree, api_idx)
    typo_check = detect_interface_attribute_typos(code_tree, api_idx)
    if typo_check["has_typos"]:
        # Issue #39: a pure attribute typo (e.g. ILexDb.EntriesOC) doesn't
        # exist on ANY interface, so detect_casting_needs' casting_index
        # lookup silently misses it -- merge it into the same
        # casting_issues list/reject path so it can't slip through as a
        # "warning"-tier issue eligible for the read-only downgrade below.
        casting_check["casting_issues"] = (
            casting_check.get("casting_issues") or []
        ) + typo_check["issues"]
        casting_check["has_casting_issues"] = True
        casting_check["severity"] = "error"
    casting_check["has_error_severity"] = _has_error_severity_casting_issue(
        casting_check.get("casting_issues") or []
    )
    return casting_check


def _build_validate_only_checks(
    *,
    code: str,
    code_tree: Optional[ast.AST],
    syntax_error: Optional[SyntaxError],
    api_idx: Any,
    session_state_obj: Any,
    write_enabled: bool,
    api_mode: str,
    skip_api_check: bool,
    provenance_existing: bool,
    skip_module_check: bool,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run gates 1-11 (production order) WITHOUT short-circuiting, except that
    a syntax failure blocks every AST-dependent gate after it (per spec).

    Side-effect free: does NOT call session_state_obj.record_auto_discovered_api
    or any other mutating method -- discovery gates REPORT here, they never
    mark entities as discovered (issue #49).

    Returns (checks, writeability) where `checks` is the ordered per-gate list
    and `writeability` is the shared #49/#55 builder payload.
    """
    checks: List[Dict[str, Any]] = []

    # --- Gate 1: syntax ---
    if syntax_error is not None:
        checks.append({
            "gate": "syntax",
            "passed": False,
            "issues": [{"line": syntax_error.lineno, "message": syntax_error.msg}],
        })
        # AST-dependent gates 2-11 cannot run without a parse tree.
        writeability = {
            "is_mutating_script": False,
            "mutations_detected": [],
            "would_require": {"write_enabled": False, "project_lock": False},
        }
        return checks, writeability
    checks.append({"gate": "syntax", "passed": True})

    # --- Gate 2: server_state ---
    server_health = validate_server_state()
    if not server_health["is_healthy"]:
        errors = [msg for sev, msg in server_health["issues"] if sev == "error"]
        checks.append({"gate": "server_state", "passed": False, "issues": errors})
    else:
        checks.append({"gate": "server_state", "passed": True})

    # --- Gate 3: partial_module_structure ---
    if not skip_module_check:
        partial_check = detect_partial_module_structure(code, code_tree)
        if partial_check["is_partial_module"]:
            checks.append({
                "gate": "partial_module_structure",
                "passed": False,
                "issues": [partial_check["suggestion"]],
                "missing_elements": partial_check.get("missing_elements"),
            })
        else:
            checks.append({"gate": "partial_module_structure", "passed": True})
    else:
        checks.append({"gate": "partial_module_structure", "passed": True, "note": "skipped (skip_module_check=True)"})

    # --- Gate 3a: top_level_main_invocation (issue #279) ---
    top_level_main_check = detect_top_level_main_invocation(code, code_tree)
    if top_level_main_check["has_top_level_main_call"]:
        if write_enabled:
            checks.append({
                "gate": "top_level_main_invocation",
                "passed": False,
                "issues": [top_level_main_check["message"]],
                "call_lines": top_level_main_check["call_lines"],
            })
        else:
            checks.append({
                "gate": "top_level_main_invocation",
                "passed": True,
                "advisory": top_level_main_check["message"],
                "call_lines": top_level_main_check["call_lines"],
            })
    else:
        checks.append({"gate": "top_level_main_invocation", "passed": True})

    # --- Gate 3b: deprecated_member (curated_deprecations.py) ---
    # Same detector + message builder handle_run_module uses; hard-rejects
    # there on read-only and write-enabled runs alike.
    deprecated_check = detect_deprecated_members(code, code_tree)
    if deprecated_check["has_deprecated"]:
        rejection = build_deprecated_member_rejection(deprecated_check)
        checks.append({
            "gate": "deprecated_member",
            "passed": False,
            "issues": deprecated_check["findings"],
            "message": rejection["message"],
            "next_steps": rejection["next_steps"],
        })
    else:
        checks.append({"gate": "deprecated_member", "passed": True})

    # --- Gate 4: unprotected_writes (also feeds the writeability builder) ---
    cud_info = detect_cud_operations(code)
    cert = certify_script_readonly(code, api_idx, code_tree)
    if not cert["is_certified_readonly"]:
        guidance = get_unprotected_write_guidance(cert)
        checks.append({
            "gate": "unprotected_writes",
            "passed": False,
            "issues": guidance.get("mutations_found", []),
            "guidance": guidance,
        })
    else:
        checks.append({"gate": "unprotected_writes", "passed": True})

    # --- Gate 5: casting ---
    # Issue #39/#40 P1-2 (cycle 5): route through the SAME shared pipeline
    # handle_run_module uses (_compute_casting_decision), not just the same
    # PREDICATE. Cycle 4 shared only `_has_error_severity_casting_issue` and
    # never called detect_interface_attribute_typos here at all, so a pure
    # attribute typo (e.g. ILexDb.EntriesOC) was invisible to validate_only
    # even though it hard-rejects in the real run_module call -- a false
    # "passed: True" reassurance for the whole #39 typo class.
    casting_index = getattr(api_idx, "casting_index", None) if api_idx else None
    casting_check = _compute_casting_decision(code, casting_index, code_tree, api_idx)
    if casting_check["has_casting_issues"]:
        issues = casting_check["casting_issues"]
        # Issue #49 B-5: this verdict must agree with what handle_run_module
        # would actually do for the same code and write_enabled value -- a
        # dry-run validator that disagrees with the real gate teaches users
        # to ignore it (issue #40). Reuse the SAME predicate result the real
        # gate uses (see _has_error_severity_casting_issue, computed once
        # inside _compute_casting_decision) rather than keying on
        # has_casting_issues alone. Issues are still fully reported either
        # way; only the pass/fail verdict is affected.
        _has_error = casting_check["has_error_severity"]
        _downgraded = (not write_enabled) and not _has_error
        check_entry = {
            "gate": "casting",
            "passed": _downgraded,
            "issues": issues,
            "severity": casting_check.get("severity"),
        }
        if _downgraded:
            check_entry["note"] = (
                "read-only run; only warning-tier casting issues -- "
                "run_module would proceed without rejecting (issue #40 B-1)"
            )
        checks.append(check_entry)
    else:
        checks.append({"gate": "casting", "passed": True})

    # --- Gates 6+7: API discovery (REPORT ONLY -- no session mutation) ---
    _skip_discovery_gates = should_skip_discovery_gates(
        skip_api_check=skip_api_check,
        provenance_existing=provenance_existing,
    )
    if _skip_discovery_gates:
        _skip_note = discovery_gate_skip_note(
            skip_api_check=skip_api_check,
            provenance_existing=provenance_existing,
        )
        checks.append({"gate": "api_discovery_required", "passed": True, "note": _skip_note})
        checks.append({"gate": "undiscovered_entity", "passed": True, "note": _skip_note})
    else:
        no_prior_discovery = len(session_state_obj.get_discovered_apis()) == 0
        if no_prior_discovery and write_enabled:
            discovery_copy = _api_discovery_required_copy(
                session_state_obj, has_inline_discovery=False
            )
            checks.append({
                "gate": "api_discovery_required",
                "passed": False,
                "issues": [discovery_copy["log_summary"]],
            })
        else:
            checks.append({"gate": "api_discovery_required", "passed": True})

        undiscovered_check = detect_undiscovered_entities(code_tree, session_state_obj, api_idx)
        if undiscovered_check["has_undiscovered"]:
            checks.append({
                "gate": "undiscovered_entity",
                "passed": False,
                "issues": undiscovered_check.get("undiscovered") or [],
            })
        else:
            checks.append({"gate": "undiscovered_entity", "passed": True})

    # --- Gate 8: undefined_variables ---
    undefined_check = detect_undefined_variables(code, code_tree)
    if undefined_check["has_undefined"]:
        checks.append({
            "gate": "undefined_variables",
            "passed": False,
            "issues": undefined_check.get("undefined_vars") or [],
        })
    else:
        checks.append({"gate": "undefined_variables", "passed": True})

    # --- Gate 9: missing_imports ---
    missing_ops_check = detect_missing_operations_imports(code, api_mode)
    if missing_ops_check["has_missing"]:
        checks.append({
            "gate": "missing_imports",
            "passed": False,
            "issues": missing_ops_check.get("missing_imports") or [],
        })
    else:
        checks.append({"gate": "missing_imports", "passed": True})

    # --- Gate 10: wrong_library_imports ---
    wrong_imports_check = detect_wrong_library_imports(code, api_mode)
    if wrong_imports_check["has_wrong_imports"]:
        checks.append({
            "gate": "wrong_library_imports",
            "passed": False,
            "issues": wrong_imports_check.get("wrong_imports") or [],
        })
    else:
        checks.append({"gate": "wrong_library_imports", "passed": True})

    # --- Gate 11: invalid_api_chain ---
    chain_check = detect_invalid_project_chains(code_tree, api_idx)
    if chain_check["has_invalid"]:
        checks.append({
            "gate": "invalid_api_chain",
            "passed": False,
            "issues": chain_check.get("issues") or [],
        })
    else:
        checks.append({"gate": "invalid_api_chain", "passed": True})

    writeability = build_writeability_payload(code, api_idx, code_tree, cud_info=cud_info, cert=cert)
    return checks, writeability


async def _handle_validate_only(
    *,
    args: dict,
    code: str,
    project_name: str,
    write_enabled: bool,
    api_mode: str,
    op_id: str,
    seq: int,
    t_start: float,
) -> list[TextContent]:
    """Issue #49: run the 11-gate preflight + a read-only lock probe, then STOP.

    Never opens the project, never spawns the subprocess. Reports ALL faults
    in one response (no short-circuit except syntax_error, which blocks the
    AST-dependent gates after it).
    """
    try:
        code_tree: Optional[ast.AST] = ast.parse(code)
        syntax_error: Optional[SyntaxError] = None
    except SyntaxError as e:
        code_tree = None
        syntax_error = e

    api_idx = get_api_index()
    checks, writeability = _build_validate_only_checks(
        code=code,
        code_tree=code_tree,
        syntax_error=syntax_error,
        api_idx=api_idx,
        session_state_obj=session_state,
        write_enabled=write_enabled,
        api_mode=api_mode,
        skip_api_check=bool(args.get("skip_api_check", False)),
        provenance_existing=(args.get("source", "authored") == "existing"),
        skip_module_check=bool(args.get("skip_module_check", False)),
    )

    # READ-ONLY project-lock probe -- never opens the project, just checks
    # for a stale/live .fwdata.lock file next to it.
    try:
        from ..project_discovery import find_lock_file
    except (ImportError, ValueError):
        from server.project_discovery import find_lock_file
    try:
        _lock_path = find_lock_file(project_name) if project_name else None
    except Exception:
        _lock_path = None
    project_lock: Dict[str, Any] = {"locked": _lock_path is not None}
    if _lock_path is not None:
        project_lock["lock_file"] = str(_lock_path)

    # Issue #93 sweep follow-up (see specs/shared-mode-access/reviews/
    # cycle5-qc.md P1-2): `locked` above is bare .fwdata.lock existence,
    # the exact false positive CP3 exists to remove (a stale lock, or a
    # live open_shared holder, both leave a lock file on disk without
    # actually blocking a write). Additively enrich with the CP2 access
    # probe so callers can distinguish "a lock file exists" from "a write
    # would actually be refused", without changing what `locked` itself
    # means. Same defensive try/except + debug-log pattern as the CP3 fix
    # above: this is a read-only preflight report, never allowed to crash
    # on a probe failure.
    try:
        try:
            from ..project_access import probe_project_access
        except (ImportError, ValueError):
            from server.project_access import probe_project_access
        _access = probe_project_access(project_name) if project_name else None
        if _access is not None:
            project_lock["sharing_enabled"] = _access.sharing_enabled
            project_lock["probed"] = _access.probed
            project_lock["verdict"] = _access.verdict
            if _access.probed:
                # The one refusing set (pattern audit sweep 3): a copied
                # literal here could drift from the write ladder's.
                project_lock["blocking"] = _access.verdict in write_ladder.REFUSING_VERDICTS
            else:
                # Issue #118: projects directory unresolvable -- never assert
                # blocking:false; LCM remains the backstop at open time.
                project_lock["blocking"] = None
            project_lock["lock_note"] = (
                "locked reflects bare .fwdata.lock file existence on disk; "
                "blocking reflects whether the access probe would refuse a write."
            )
    except Exception as exc:
        _lock_logger = get_operations_logger()
        if _lock_logger is not None:
            _lock_logger.debug(
                f"validate_only project_lock probe unavailable: {exc!r}"
            )

    all_passed = all(c.get("passed", False) for c in checks)
    status = "validated" if all_passed else "validation_failed"
    fault_gates = [c["gate"] for c in checks if not c.get("passed", False)]

    duration_s = time.monotonic() - t_start
    _log_validate_only_close(op_id, seq, duration_s, status, fault_gates)

    data: Dict[str, Any] = {
        KEY_STATUS: status,
        "validate_only": True,
        "checks": checks,
        "writeability": writeability,
        "project_lock": project_lock,
        "op_id": op_id,
        "session": session_state.summary(),
    }
    data = build_response_with_context(data, include_session=True)
    return [TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))]


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
        "[ACTION REQUIRED] The fixes were applied only to the executed copy.",
        f"  Source: {source_hint}",
        "  Update your source file at the line numbers listed above or you will",
        "  see this auto-fix note every time you run this code.",
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

    # Re-run casting check on patched code. Issue #121: give it api_idx too
    # (via the compat wrapper) so an auto-fix that still leaves a Rule
    # A/B-detectable polymorphic-dataflow issue behind is caught here,
    # instead of only by the caller's OWN post-fix re-check.
    patched_casting = _detect_casting_needs_compat(patched_code, casting_index, patched_tree, api_idx)
    if patched_casting.get("has_casting_issues"):
        return False

    # Re-run typo check on patched code
    patched_typo = detect_invalid_project_chains(patched_tree, api_idx)
    if patched_typo.get("has_invalid"):
        return False

    return True


def _invalidate_sandbox_cache_after_write(project_name: str) -> None:
    """Invalidate the project's sandbox config cache (CP5 FR-026).

    The import is lazy (this module imports nothing from the sandbox at load
    time) and every failure -- an import error included -- is logged, never
    raised: a cache must never break run_module.
    """
    try:
        from ..sandbox.cache import invalidate

        invalidate(project_name)
    except Exception as exc:  # noqa: BLE001 -- must never break run_module
        op_logger = get_operations_logger()
        if op_logger is not None:
            with contextlib.suppress(Exception):
                op_logger.warning(
                    f"[SANDBOX] could not invalidate the config cache for "
                    f"'{project_name}' after a write run: {exc}"
                )


async def _release_own_worker_or_refuse(project_name: str, decision, *, op_id: Optional[str] = None):
    """Own idle parse worker -> release it and re-probe; own busy one ->
    refuse, naming it plainly. Neither ours -> unchanged (issue #223).

    `write_ladder.probe_write_access` is pure filesystem: it cannot tell
    this server's own parse worker (`flextools_try_word` /
    `flextools_parse_text`'s shared read worker, or the bounded measurement
    worker) apart from a genuinely foreign Python process holding the same
    `.fwdata.lock`. Both report as `held_by_other`. Mirrors filing's own
    handling of this (`handlers/parse.py:_held_by_own_read_worker` and the
    release around L1700), generalized to any of the pool's roles and
    shared through `parse/own_worker.py` so the two write gates cannot
    answer "is this ours?" differently.

    Called only from the point where a refusal would actually be issued
    (after `run_module`'s confirmation gate), never from the earlier probe
    used to build the confirmation preview -- releasing there would tear
    down a warm worker under an unconfirmed, maybe-never-submitted call.

    STILL NEEDED AFTER THE #223 SCOPE CHANGE (the worker now releases the
    project itself the instant its queue goes idle --
    `parse/worker_main.py`'s `ParseWorker._release_if_idle` -- rather than
    holding it for the rest of `DEFAULT_IDLE_TIMEOUT_SECONDS`). Two gaps
    that self-release does not close on its own:
      (1) the busy case -- a write landing WHILE a parse is genuinely
          running still needs this function's refusal, which is now this
          function's PRIMARY remaining job rather than a secondary one;
      (2) a small race window between a result going out and the worker's
          own next idle check (`_POLL_INTERVAL_SECONDS`, 50ms) -- a write
          landing in that window still sees `held_by_other` and still
          needs the idle-release branch below on non-shared projects, just
          for a far smaller window than the up-to-600s gap this originally
          closed.
      (3) on shared projects, an idle own worker is left running and the
          write proceeds anyway (L-0 coexistence, mirroring filing's gate) --
          the probe's `held_by_other` is cleared without a release.

    Returns `(refusal_response, decision)`:
      * own worker, busy   -> `(refusal_response, decision)` (unchanged
        decision; caller returns the refusal as-is).
      * own worker, idle   -> `(None, new_decision)`, released and
        re-probed. Any holder remaining in `new_decision` is genuine.
      * not our worker     -> `(None, decision)`, unchanged.

    THE CHECK AND THE RELEASE ARE NOW ONE ATOMIC CALL (#223 QC P1): a
    separate `worker_busy()` check followed by a separate `release_worker()`
    left a real `await` gap (worker teardown) between "found idle" and
    "popped from the pool", long enough for a run that had just registered
    itself to grab this same worker and have it torn down mid-parse.
    `release_worker_if_idle` re-checks busyness under the pool's own lock
    at the moment of the pop, closing that gap (see
    `WorkerPool.release_if_idle`'s docstring for why registration order
    makes that sufficient rather than just narrower).
    """
    try:
        from ..parse.own_worker import (
            HELD_BY_OWN_READ_WORKER,
            own_worker_role,
            busy_own_worker_guidance,
            busy_own_worker_run_note,
        )
    except (ImportError, ValueError):
        from server.parse.own_worker import (
            HELD_BY_OWN_READ_WORKER,
            own_worker_role,
            busy_own_worker_guidance,
            busy_own_worker_run_note,
        )
    try:
        from .parse import peek_runner
    except (ImportError, ValueError):
        from server.handlers.parse import peek_runner

    runner = peek_runner()
    if runner is None:
        return None, decision

    role = own_worker_role(runner, project_name, decision)
    if role is None:
        return None, decision

    if runner.worker_busy(project_name, role=role):
        run_ids = runner.active_run_ids(project_name, role=role)
        run_note = busy_own_worker_run_note(run_ids)
        guidance = busy_own_worker_guidance("resubmit the write")
        refusal = error_response(
            "project_locked",
            f"Project '{project_name}' is held by this server's own parse "
            f"worker, which is busy running a parse{run_note}. This is NOT "
            f"a foreign process -- do not end it. {guidance}",
            guidance=guidance,
            remedy=guidance,
            lock_file_path=decision.refusal.get("lock_file_path"),
            verdict=decision.verdict,
            sharing_enabled=decision.refusal.get("sharing_enabled"),
            holder_pid=decision.refusal.get("holder_pid"),
            holder_process="this server's own parse worker",
            op_id=op_id,
        )
        return refusal, decision

    sharing = bool(decision.refusal.get("sharing_enabled"))
    if sharing:
        # Mirror filing's confirmed gate (handlers/parse.py row 11): on a
        # shared project our read worker coexists with a writable open, so
        # do not release it first -- the probe's `held_by_other` is our own
        # worker, not a foreign collision (issue #223, second repro).
        return None, write_ladder.AccessDecision(
            project_name=project_name,
            access=decision.access,
            verdict=HELD_BY_OWN_READ_WORKER,
            refusal=None,
        )

    if await runner.release_worker_if_idle(project_name, role=role):
        try:
            return None, write_ladder.probe_write_access(project_name)
        except Exception:
            # A re-probe failure here should read as "still refused with
            # the original detail", not crash the write gate: fall back
            # to the decision as it stood before the release attempt.
            return None, decision

    run_ids = runner.active_run_ids(project_name, role=role)
    run_note = busy_own_worker_run_note(run_ids)
    guidance = busy_own_worker_guidance("resubmit the write")
    refusal = error_response(
        "project_locked",
        f"Project '{project_name}' is held by this server's own parse "
        f"worker, which is busy running a parse{run_note}. This is NOT "
        f"a foreign process -- do not end it. {guidance}",
        guidance=guidance,
        remedy=guidance,
        lock_file_path=decision.refusal.get("lock_file_path"),
        verdict=decision.verdict,
        sharing_enabled=decision.refusal.get("sharing_enabled"),
        holder_pid=decision.refusal.get("holder_pid"),
        holder_process="this server's own parse worker",
        op_id=op_id,
    )
    return refusal, decision


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
    # Issue #40 B-1: populated when the casting gate is downgraded to a
    # non-blocking advisory (read-only run, no issue at "error" severity).
    # Surfaced in the response `warnings` list instead of rejecting.
    _casting_readonly_warnings: Optional[List[Dict[str, Any]]] = None
    # Issue #279: module-level Main(...) when def Main exists (read-only advisory).
    _top_level_main_readonly_warning: Optional[str] = None
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
            session=session_state.summary(),
            **_available_projects_payload(),
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
    if resolved:
        try:
            from ...project_adoption import adopt_resolved_project
        except ImportError:
            from project_adoption import adopt_resolved_project
        project_name = adopt_resolved_project(
            session_state,
            resolved,
            log_context="flextools_run_module",
        )

    # === Operation logging begins here ===
    # Every code-bearing call gets an op_id and a Start block, regardless of
    # whether it later passes pre-flight. The user wants ALL attempted ops
    # visible in the .log so a "what did the LLM try" reconstruction is possible.
    seq, op_id = _next_op_id()
    t_start = time.monotonic()

    # Issue #49: validate_only mode -- run the 11-gate preflight (plus a
    # read-only project-lock probe) and STOP. Diverted here, before the
    # normal ast.parse()/SyntaxError early-return below, because validate_only
    # must surface a syntax failure as a `checks[]` entry (gate 1) rather than
    # the standard syntax_error rejection -- and must never open the project
    # or spawn the subprocess.
    if args.get("validate_only", False):
        _log_operation_start(
            op_id, seq, project_name, write_enabled, code, "validate_only",
            user_intent=user_intent,
            user_request=user_request,
        )
        return await _handle_validate_only(
            args=args,
            code=code,
            project_name=project_name,
            write_enabled=write_enabled,
            api_mode=api_mode,
            op_id=op_id,
            seq=seq,
            t_start=t_start,
        )

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
            session_id=getattr(session_state, "session_id", "") or "",
        )
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "syntax_error",
            f"line {syn_exc.lineno}: {syn_exc.msg}",
        log_dir_fn=get_log_dir,
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
        session_id=getattr(session_state, "session_id", "") or "",
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
        log_dir_fn=get_log_dir,
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
            log_dir_fn=get_log_dir,
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

    # Issue #279: reject write runs that call Main at module level when Main
    # is also defined -- the runner calls Main again after exec().
    top_level_main_check = detect_top_level_main_invocation(code, code_tree)
    if top_level_main_check["has_top_level_main_call"]:
        if write_enabled:
            _log_preflight_reject(
                op_id, seq, time.monotonic() - t_start,
                "top_level_main_invocation",
                f"call_lines={top_level_main_check['call_lines']}",
            log_dir_fn=get_log_dir,
            )
            return _attach_assistance_if_loop(
                error_response(
                    "top_level_main_invocation",
                    top_level_main_check["message"],
                    call_lines=top_level_main_check["call_lines"],
                    next_steps=[
                        "1. Remove the module-level Main(project, report, modifyAllowed) call",
                        "2. Keep only the def Main(...) definition -- flextools_run_module invokes it",
                        "3. Re-run flextools_run_module()",
                    ],
                    op_id=op_id,
                ),
                error_code="top_level_main_invocation",
                code_size_bytes=_code_size_bytes,
            )
        _top_level_main_readonly_warning = top_level_main_check["message"]

    # Deprecated-member check (curated_deprecations.py): HARD BLOCK on both
    # read-only and write-enabled runs. A curated-deprecated member exists in
    # the API but does not do what its name says -- e.g.
    # ILexEntry.DoNotUseForParsing has no effect on either FLEx parser, so a
    # read answers the wrong question and a write silently changes nothing
    # the parser sees. Runs before the write-safety gates so an unguarded
    # SetDoNotUseForParsing is told "wrong field", not "add a guard".
    # Not bypassable by skip_module_check / source='existing'.
    deprecated_check = detect_deprecated_members(code, code_tree)
    if deprecated_check["has_deprecated"]:
        rejection = build_deprecated_member_rejection(deprecated_check)
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "deprecated_member",
            f"findings={[f.get('expr') for f in deprecated_check['findings'][:5]]}",
        log_dir_fn=get_log_dir,
        )
        return _attach_assistance_if_loop(
            error_response(
                "deprecated_member",
                rejection["message"],
                findings=deprecated_check["findings"],
                deprecations=list(deprecated_check["deprecations"].values()),
                replacement_example=rejection["replacement_example"],
                next_steps=rejection["next_steps"],
                op_id=op_id,
            ),
            error_code="deprecated_member",
            code_size_bytes=_code_size_bytes,
        )

    # Nested-UnitOfWork check (issue #92 follow-up, re-derived for issue
    # #144): a script that opens its OWN raw UnitOfWork --
    # UndoableUnitOfWorkHelper/NonUndoableUnitOfWorkHelper or a bare
    # IActionHandler.BeginUndoTask()/BeginNonUndoableTask() -- always risks
    # nesting inside a task the runner or flexicon already has open;
    # liblcm rolls back the already-open task first, discarding writes,
    # before it throws. The gate stays construct-based and UNCONDITIONAL --
    # a script cannot know at the call site whether it is executing inside
    # flexicon's own per-operation wrapper -- but WHAT it is nesting into
    # depends on the OpenProject()-time capability probe (issue #144):
    #   - Legacy (no "per-operation-uow" in CAPABILITIES): OpenProject()
    #     opens ONE non-undoable UnitOfWork for the whole session (opened
    #     once at OpenProject(), closed once at CloseProject()); a raw
    #     helper nests inside THAT. Under the declared pyflexicon floor
    #     this branch is unreachable; it remains as defence-in-depth for
    #     unsupported installs and is surfaced on the run_module response
    #     (issue #153) so the degradation is never silent.
    #   - Capable builds (undoable=True chosen): OpenProject() opens no
    #     session-long envelope; instead flexicon wraps EACH mutating call
    #     in its own named unit of work (FLExProject.py), and a raw helper
    #     executing while one of those is open nests inside IT instead.
    # Only meaningful when write_enabled: in both modes, a read-only run
    # opens no UnitOfWork at all, so there is nothing to nest into. An
    # `if modifyAllowed:` guard does NOT fix this -- the nesting collision
    # happens regardless of guard state once the code actually executes --
    # so this fires unconditionally on the construct, not just on
    # unprotected occurrences of it (see detect_cud_operations below for
    # the separate protected-vs-unprotected write-safety concern).
    if write_enabled:
        nested_uow_check = detect_nested_unit_of_work(code, code_tree)
        if nested_uow_check["has_nested_uow_risk"]:
            constructs = nested_uow_check["constructs"]
            _log_preflight_reject(
                op_id, seq, time.monotonic() - t_start,
                "nested_unit_of_work",
                f"constructs={[c.get('construct') for c in constructs[:5]]}",
            log_dir_fn=get_log_dir,
            )
            _is_per_op_uow = _probe_undoable_capability()
            if _is_per_op_uow:
                _nested_uow_message = (
                    "Code opens its own raw liblcm UnitOfWork. flexicon already "
                    "wraps each mutation in its own named unit of work; a raw "
                    "helper call executing while one of those is open nests "
                    "inside it and will discard that operation's writes before "
                    "the error is raised."
                )
            else:
                _nested_uow_message = (
                    "Code opens its own raw liblcm UnitOfWork, which nests inside "
                    "the runner's already-open non-undoable task and will discard "
                    "this run's writes."
                )
            return _attach_assistance_if_loop(
                error_response(
                    "nested_unit_of_work",
                    _nested_uow_message,
                    constructs=constructs,
                    next_steps=[
                        "1. Drop the UndoableUnitOfWorkHelper/NonUndoableUnitOfWorkHelper "
                        "wrapper (or the raw BeginUndoTask/BeginNonUndoableTask call) -- "
                        "there is already a unit of work open around this mutation "
                        "(the runner's session task, or flexicon's own per-operation "
                        "task, depending on the flexicon build).",
                        "2. Just perform the mutation directly (guarded by "
                        "`if modifyAllowed:` as usual); it will be captured by that "
                        "already-open unit of work.",
                        "3. If you need FLEx Ctrl+Z grouping for this specific change, "
                        "use `project.UndoableOperation(label)` / `project.Transaction(label)` "
                        "instead of the raw liblcm helper -- those join an already-open "
                        "UnitOfWork instead of nesting a second one.",
                        "4. Re-run flextools_run_module()",
                    ],
                    op_id=op_id,
                ),
                error_code="nested_unit_of_work",
                code_size_bytes=_code_size_bytes,
            )

    # Check for unprotected mutations - HARD BLOCK if found
    cud_info = detect_cud_operations(code)
    cert = certify_script_readonly(code, get_api_index(), code_tree)

    # CRITICAL: Refuse unprotected code unconditionally
    if not cert["is_certified_readonly"]:
        guidance = get_unprotected_write_guidance(cert)
        mutating = [m for m in cert.get("mutating_calls", []) if m.get("is_mutating")]
        _log_writeability_reject(cert, mutating)
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "unprotected_writes",
            f"mutating_calls={[m.get('method') for m in mutating[:5]]}",
        log_dir_fn=get_log_dir,
        )
        # Issue #95: return the structured TOOL-CONTRACT rejection (status,
        # error_code, _contract, message) with the same fix guidance the log
        # already records -- not a legacy ad-hoc dict whose ``error`` string
        # collides with the nested deprecated shape.
        return _attach_assistance_if_loop(
            error_response(
                "unprotected_writes",
                guidance["message"],
                mutations_found=guidance.get("mutations_found"),
                why=guidance.get("why"),
                fix_pattern=guidance.get("fix_pattern"),
                templates_to_review=guidance.get("templates_to_review"),
                next_steps=guidance.get("next_steps"),
                mutating_calls=mutating[:20],
                op_id=op_id,
            ),
            error_code="unprotected_writes",
            code_size_bytes=_code_size_bytes,
        )

    # Issue #103: hvo instability. An hvo is a session-scoped handle --
    # liblcm renumbers it on every cache load (DomainDataByFlid.cs:40-44:
    # "valid for one session, but may not be the same integer for another
    # session for the 'same' object"; field evidence: 2440/2440 entry hvos
    # changed across two consecutive read-only run_module calls, 0/2440
    # guids changed). A bare integer literal reaching an `*_or_hvo`
    # parameter (or project.Object(<int>)) can only have been copied from a
    # PRIOR call's output or the FLEx UI -- there is no reason to hand-type
    # one from a live object read this run. That is exactly the stale-hvo
    # silent-wrong-target scenario the issue documents.
    #
    # Read-only runs: WARNING only (surfaced in the `warnings` list below,
    # not a rejection) -- a stray literal in exploratory/read code cannot
    # corrupt anything.
    # Write-enabled runs: HARD BLOCK. A wrong-target WRITE is precisely the
    # silent-corruption scenario #103 documents (the reporter's own
    # near-miss was a write script using stale hvo literals as targets), and
    # this preflight already hard-blocks write-shaped risk unconditionally
    # elsewhere (unprotected_writes above, nested_unit_of_work before it) --
    # a warning-only response written into the same *_or_hvo parameter this
    # call has already accepted a write through fails the same way a
    # missing modifyAllowed guard would. Blocking here is consistent with
    # that existing posture rather than a new architecture.
    hvo_literal_check = detect_hvo_literal_args(code, code_tree, get_api_index())
    addcustomfield_check = detect_raw_addcustomfield_risk(code, code_tree)
    if addcustomfield_check["has_raw_addcustomfield_risk"] and write_enabled:
        findings = addcustomfield_check["findings"]
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "raw_addcustomfield_write_risk",
            f"findings={[f.get('detail') for f in findings[:5]]}",
        log_dir_fn=get_log_dir,
        )
        return _attach_assistance_if_loop(
            error_response(
                "raw_addcustomfield_write_risk",
                "Raw IFwMetaDataCacheManaged.AddCustomField bypasses flexicon's "
                "schema guards. Fields created this way may never persist correctly "
                "and can corrupt the project on the next FLEx UI open; the "
                "fieldWs=0 + IUndoStackManager.Save() pattern can hang until the "
                "run_module timeout (issue #70).",
                findings=findings,
                next_steps=[
                    "1. Create the custom field in FLEx (Tools > Configure > "
                    "Custom Fields) before running population scripts.",
                    "2. Or use project.CustomFields.CreateField(...) when your "
                    "runner transaction mode allows schema mutations.",
                    "3. Do not call raw AddCustomField on IFwMetaDataCacheManaged "
                    "or usm.Save() to flush schema experiments.",
                    "4. Re-run flextools_run_module() with the supported path.",
                ],
                op_id=op_id,
            ),
            error_code="raw_addcustomfield_write_risk",
            code_size_bytes=_code_size_bytes,
        )

    if hvo_literal_check["has_hvo_literal_risk"] and write_enabled:
        findings = hvo_literal_check["findings"]
        _log_preflight_reject(
            op_id, seq, time.monotonic() - t_start,
            "hvo_literal_write_risk",
            f"findings={[f.get('detail') for f in findings[:5]]}",
        log_dir_fn=get_log_dir,
        )
        return _attach_assistance_if_loop(
            error_response(
                "hvo_literal_write_risk",
                "An integer literal is being passed to an hvo-accepting "
                "parameter in a WRITE-enabled run. hvos are session-scoped "
                "handles -- liblcm renumbers them on every cache load, so a "
                "literal copied from a prior call's output (or typed from "
                "the FLEx UI) may now resolve to a different, real object. "
                "A write against it would silently target the wrong entry.",
                findings=findings,
                next_steps=[
                    "1. Replace the integer literal with the GUID string "
                    "captured for that object (e.g. from a prior GetGuid() "
                    "call or report output).",
                    "2. Re-resolve the live object THIS run via "
                    "project.Object(guid_str) -- accepts str/System.Guid, "
                    "not just int/hvo (see FLExProject.Object).",
                    "3. Pass the re-resolved object (or its CURRENT .Hvo, "
                    "read this same run) to the *_or_hvo parameter instead "
                    "of the literal.",
                    "4. Re-run flextools_run_module()",
                ],
                op_id=op_id,
            ),
            error_code="hvo_literal_write_risk",
            code_size_bytes=_code_size_bytes,
        )

    # Check for polymorphic casting issues - detect and suggest fixes BEFORE running
    # This catches errors like: sense.Owner.HeadWord (ICmObject doesn't have HeadWord)
    # Issue #39/#40 P1-2 (cycle 5): routes through the single shared
    # _compute_casting_decision pipeline (detect_casting_needs +
    # detect_interface_attribute_typos merge + severity="error" forcing +
    # the has-error predicate) -- see that function's docstring. Every
    # caller of a casting verdict (this function, _handle_validate_only's
    # Gate 5, and the eval runner's Gate 5) MUST go through it so none of
    # them can drift from what the others decide.
    api_idx = get_api_index()
    casting_index = api_idx.casting_index if api_idx else None
    casting_check = _compute_casting_decision(code, casting_index, code_tree, api_idx)

    if casting_check["has_casting_issues"]:
        issues = casting_check["casting_issues"]
        # Issue #40 B-1: gate-local read-only severity downgrade. Per-issue
        # severity already exists in the data (a known-pattern hit, or a
        # genuine attribute typo merged in above, is "error"; an index-
        # derived lookup with no corroborating known pattern is "warning").
        # If NO issue here is "error", a read-only run does not reject --
        # the run proceeds and the issues are surfaced as non-blocking
        # advisories instead. A wrong guess in read-only code raises a
        # TypeError at runtime (one iteration, no data risk); it cannot
        # corrupt anything. Any "error"-severity issue still hard-rejects,
        # and EVERY write-enabled run still hard-rejects at every severity,
        # exactly as before. This downgrade is GATE-LOCAL to the casting
        # gate's warning tier -- no other preflight gate (unprotected_writes,
        # hvo_literal_write_risk, nested_unit_of_work) is touched by it.
        # has_error_severity was computed once inside _compute_casting_decision
        # (issue #39/#40 P1-2, cycle 5) via the shared
        # _has_error_severity_casting_issue predicate, also consumed by
        # _build_validate_only_checks's Gate 5 (issue #49 B-5) so the
        # dry-run validator can never drift from this real decision again.
        if (not write_enabled) and not casting_check["has_error_severity"]:
            get_operations_logger().info(
                f"Preflight casting: issues={len(issues)} severity=warning "
                "(read-only run) -- proceeding without rejecting (issue #40 B-1)."
            )
            for issue in issues[:10]:
                get_operations_logger().debug(
                    f"  casting[warn]: line={issue.get('line')} property={issue.get('property')} "
                    f"pattern={issue.get('pattern','')[:80]!r}"
                )
            _casting_readonly_warnings = issues
            # Issue #28: record a SUCCESS signal so the retry-loop detector
            # resets -- the loops it was catching here were largely this
            # gate's own false rejects, and a run that proceeds is a genuine
            # success by the detector's own documented contract
            # (record_op_signal docstring: "On success: pass error_code=None").
            session_state.record_op_signal(error_code=None, code_size_bytes=_code_size_bytes)
        else:
            # Format issues with clear fixes for all 3 API flavors
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
                        # Issue #121: api_idx via the compat wrapper -- this
                        # direct re-run bypasses _compute_casting_decision
                        # entirely (see its own docstring), so typo-merge and
                        # has_error_severity are NOT recomputed here; that
                        # was already true before this change and is out of
                        # scope for issue #121 to fix.
                        casting_check = _detect_casting_needs_compat(code, casting_index, code_tree, api_idx)
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
                log_dir_fn=get_log_dir,
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
    if is_stateless_client_mode() and not skip_api_check and not _provenance_existing:
        get_operations_logger().info(
            "[DISCOVERY] FLEXTOOLS_STATELESS=1 -- skipping api_discovery_required and "
            "undiscovered_entity gates (issue #142). Write-safety + casting already "
            "ran and are unaffected."
        )
    _skip_discovery_gates = should_skip_discovery_gates(
        skip_api_check=skip_api_check,
        provenance_existing=_provenance_existing,
    )

    if not _skip_discovery_gates and len(session_state.get_discovered_apis()) == 0:
        if write_enabled:
            # WRITE path: hard gate -- discovery is required before any write.
            # Write isolation is non-negotiable; issue #80 leaves this unchanged.
            # Issue #29: inline get_object_api for the top entities we can spot in
            # the submitted code, so the LLM gets the real method shapes in the
            # rejection itself and can recover in one round-trip instead of three.
            candidates = detect_candidate_entities(code_tree, api_idx, limit=3)
            inline = _inline_discovery_docs(candidates, api_idx) if candidates else {}
            discovery_copy = _api_discovery_required_copy(
                session_state, has_inline_discovery=bool(inline)
            )
            _log_preflight_reject(
                op_id, seq, time.monotonic() - t_start,
                "api_discovery_required",
                discovery_copy["log_summary"],
            log_dir_fn=get_log_dir,
            )
            message = discovery_copy["message"]
            extras: Dict[str, Any] = {
                "hint": discovery_copy["hint"],
                "session": session_state.summary(),
                "op_id": op_id,
                "detected_candidates": candidates,
                "auto_discovered_pending_validation": discovery_copy[
                    "auto_discovered_pending_validation"
                ],
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
                log_dir_fn=get_log_dir,
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
        log_dir_fn=get_log_dir,
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
        log_dir_fn=get_log_dir,
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
        log_dir_fn=get_log_dir,
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
            log_dir_fn=get_log_dir,
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

    # getall-contract SPEC §6 Level 3 (cycle-4 reversal): non-blocking
    # advisory (never rejects) for unsafe len()/subscript/truthiness/
    # double-consume idioms on a raw one-shot FLExProject iterator/generator
    # result. flexlibs_stable-only -- flexicon 4.3.0's EnumerableWrapper is a
    # genuine safe behavioral collection, so this is silent in flexicon mode.
    getall_check = detect_getall_unsafe_idiom(code_tree, api_mode, api_idx)

    timeout_seconds = args.get("timeout_seconds", 300)

    # Operation Start was logged at the top of handle_run_module; now that
    # pre-flight has passed, append the casting telemetry and an explicit
    # "preflight passed" marker so a failure later in the subprocess can be
    # told apart from a failure that never made it past validation.
    #
    # NO INJECTION TIER IS REPORTED, because nothing is injected. This used
    # to read `Preflight: passed (tier=full)` while injecting nothing -- a
    # log line that answered the reader's question with something untrue.
    # The casting DETECTION below is real and stays: `casting_issues` is
    # what pre-flight actually found.
    logger = get_operations_logger()
    casting_issues = casting_check.get("casting_issues") or []
    if casting_issues:
        logger.info(f"Preflight casting: issues={len(casting_issues)}")
        for issue in casting_issues[:10]:
            logger.debug(
                f"  casting: line={issue.get('line')} property={issue.get('property')} "
                f"pattern={issue.get('pattern','')[:80]!r}"
            )
    logger.info("Preflight:       passed")

    # Build warnings
    warnings = []
    if api_mode != EXECUTION_API_MODE:
        warnings.append(
            f"[api_mode] Session api_mode is {api_mode!r}, but flextools_run_module "
            f"executes with {EXECUTION_API_MODE!r} imports. Write flexicon-compatible "
            "code for execution; use your selected mode when searching APIs and "
            "matching imports in preflight."
        )
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

    if getall_check["has_unsafe_idiom"]:
        for issue in getall_check["issues"]:
            warnings.append(f"[GetAll() container contract] {issue['suggestion']}")
        warnings.append("")

    # Issue #103: reaching this point with hvo_literal_check risk set means
    # write_enabled was False (a write-enabled run with this risk already
    # hard-blocked above with error_code='hvo_literal_write_risk') --
    # surface it as a non-blocking advisory instead.
    if hvo_literal_check["has_hvo_literal_risk"]:
        warnings.append(
            "[hvo stability] An integer literal is being passed to an "
            "hvo-accepting parameter. hvos are session-scoped -- liblcm "
            "renumbers them on every cache load, so a literal copied from a "
            "prior call's output may now resolve to a DIFFERENT object. "
            "Carry the GUID instead and re-resolve with "
            "project.Object(guid_str)."
        )
        for finding in hvo_literal_check["findings"]:
            warnings.append(f"  line {finding['line']}: {finding['detail']}")
        warnings.append("")

    if addcustomfield_check["has_raw_addcustomfield_risk"]:
        warnings.append(
            "[raw AddCustomField] Raw IFwMetaDataCacheManaged.AddCustomField "
            "bypasses flexicon schema guards (issue #70). WRITE-enabled runs "
            "with this pattern are rejected at preflight."
        )
        for finding in addcustomfield_check["findings"]:
            warnings.append(f"  line {finding['line']}: {finding['detail']}")
        warnings.append("")

    # Issue #40 B-1: casting issues downgraded from a hard reject to a
    # non-blocking advisory (read-only run, no issue at "error" severity --
    # see the gate-local downgrade above). Still surfaced here so the caller
    # sees them even though preflight let the run proceed.
    if _top_level_main_readonly_warning:
        warnings.append(
            "[double Main execution] " + _top_level_main_readonly_warning
        )
        warnings.append("")

    if _casting_readonly_warnings:
        warnings.append(
            f"[casting] {len(_casting_readonly_warnings)} polymorphic property "
            "access issue(s) were detected but did NOT block this READ-ONLY "
            "run (index-derived guess, not a known casting pattern or "
            "attribute typo). A wrong guess raises a TypeError at runtime -- "
            "it cannot corrupt data. Set write_enabled=True and these WILL "
            "be rejected."
        )
        for issue in _casting_readonly_warnings[:10]:
            warnings.append(
                f"  line {issue.get('line')}: {issue.get('property')} -- "
                f"{issue.get('fix', '')}"
            )
        warnings.append("")

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


def _maybe_refresh_from_disk(project):
    # Issue #147: a foreign FLEx save while this runner holds the project open
    # leaves the in-memory cache stale; reconcile before CloseProject() commits.
    if not WRITE_ENABLED or project is None:
        return
    try:
        import flexicon

        if "refresh-from-disk" not in getattr(flexicon, "CAPABILITIES", ()):
            return
        refresh = getattr(project, "RefreshFromDisk", None)
        if callable(refresh):
            refresh()
    except Exception:
        pass


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

    # Create reporter early: setup steps below (the ui= fallback check) need
    # somewhere visible to report a degraded-but-working state, and the
    # OpenProject failure path also benefits from returning any such warning.
    report = SimpleReporter()

    try:
        # API Mode-specific imports
        from flexicon import FLExInitialize, FLExCleanup, FLExProject

        # Issue #96 (A-8) / #148: inject HeadlessLcmUI when flexicon advertises
        # ui-injection. flexicon >=4.8 defaults ui=None to HeadlessLcmUI
        # (flexicon #285); the pre-4.8 hazard was WinForms FwLcmUI modal dialogs
        # in a headless subprocess (flexicon #238). Probe CAPABILITIES instead of
        # importing flexicon.code.headless_ui (internal path; top-level export
        # since 4.8.0).
        import flexicon as _flexicon_pkg
        _UI_CAPS = getattr(_flexicon_pkg, "CAPABILITIES", frozenset())
        if "ui-injection" in _UI_CAPS:
            try:
                from flexicon import HeadlessLcmUI
                _lcm_ui = HeadlessLcmUI()
            except ImportError:
                _lcm_ui = None
                report.Warning(
                    "flexicon advertises ui-injection but HeadlessLcmUI is not "
                    "importable from the top-level flexicon package; OpenProject "
                    "will omit ui= and use flexicon's default LcmUI."
                )
        else:
            _lcm_ui = None
            report.Warning(
                "This flexicon build does not advertise ui-injection in "
                "CAPABILITIES; OpenProject will omit ui= and use flexicon's "
                "default LcmUI."
            )

        FLExInitialize()

        # Issue #159: the `ui=` kwarg only exists on flexicon builds >=4.4.0
        # (OpenProject(..., ui=None)); on older builds passing it -- even as
        # ui=None -- raises TypeError and kills the session's very first
        # operation ("got an unexpected keyword argument 'ui'"). Probe the
        # INSTALLED signature in THIS process, not in the server process: the
        # subprocess venv can hold a different flexicon than the server's, so
        # a server-side probe could approve a kwarg that fails here. Broad
        # except so any introspection failure (uninspectable method, no
        # flexicon) degrades to omitting `ui=` -- matching this repo's
        # graceful-degrade-with-visible-warning convention for flexicon skew.
        try:
            import inspect
            _openproject_accepts_ui = "ui" in inspect.signature(FLExProject.OpenProject).parameters
        except Exception:
            _openproject_accepts_ui = False

        # Open project
        project = FLExProject()
        try:
            # Issue #144: CP1 / issue #92's premise (undoable=True opens no
            # envelope and every mutating call raises) is false on flexicon
            # builds that advertise the "per-operation-uow" capability: under
            # undoable=True, OpenProject() itself opens no session-long task
            # BECAUSE each mutation opens its own named task instead
            # (FLExProject.py's `writeEnabled and self._undoable` branch) --
            # nothing raises. Probe for that capability using the exact
            # one-line form flexicon's own docstring prescribes for this
            # consumer (flexicon/__init__.py).
            #
            # When CAPABILITIES is missing or lacks the token, _undoable is
            # False -- byte-identical to the old hardcoded behaviour. Under
            # the declared pyflexicon floor that branch is unreachable; it
            # remains as defence-in-depth for unsupported installs. Issue
            # #153: surface the resolved mode on the result so a silent
            # non-undoable degradation cannot hide behind a successful run.
            import flexicon
            _CAPS = getattr(flexicon, "CAPABILITIES", frozenset())
            _undoable = "per-operation-uow" in _CAPS
            # Issue #153: machine-readable mode flags. timestamps_updated
            # tracks DateModified stamping, which rides the same undoable
            # path (absent under the legacy session envelope).
            result["undoable"] = _undoable
            result["timestamps_updated"] = _undoable
            if not _undoable:
                report.Warning(
                    "OpenProject chose undoable=False: this flexicon build "
                    "does not advertise CAPABILITIES 'per-operation-uow'. "
                    "DateModified will not be stamped and mid-operation "
                    "exceptions will not roll back. Supported installs "
                    "(the declared pyflexicon floor) always advertise this "
                    "capability; this fallback is defence-in-depth for "
                    "unsupported installs (issue #153)."
                )
            if _openproject_accepts_ui:
                project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED, undoable=_undoable, ui=_lcm_ui)
            else:
                report.Warning(
                    "this flexicon build's OpenProject() does not accept the "
                    "ui= argument; opening with this build's default LCM UI "
                    "instead (issue #159)."
                )
                project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED, undoable=_undoable)
        except Exception as e:
            result["error"] = "Failed to open project '{}': {}".format(PROJECT_NAME, str(e))
            result["messages"] = report.messages
            result["summary"] = {
                "info_count": report.messageCounts[SimpleReporter.INFO],
                "warning_count": report.messageCounts[SimpleReporter.WARNING],
                "error_count": report.messageCounts[SimpleReporter.ERROR],
                "total_messages": len(report.messages)
            }
            return result

        # FLEx uses '***' as placeholder for empty/unset multilingual string values
        FLEX_EMPTY_PLACEHOLDER = "***"

        def is_empty_multistring(text):
            """Return True if `text` represents an empty/unset FLEx multistring.

            Accepts EITHER an already-resolved Python str (e.g. from a
            flexicon Operations method like GetGloss()/GetDefinition()) OR a
            raw LCM multistring/tsstring object obtained via direct C# field
            access (e.g. `sense.Gloss`, `form.Form`). A non-str input is
            resolved to text via, in order: `.Text` (ITsString), then
            `.BestAnalysisAlternative.Text`, then
            `.BestVernacularAlternative.Text` (IMultiUnicode / IMultiString).
            Each resolution attempt is independently guarded so it can never
            raise; if none of them yields a str, this falls back to
            str(text) rather than raising, because this helper is injected
            into user scripts and must never be the thing that crashes them.

            True for None, "" , or "***" (after resolution and whitespace
            stripping).
            """
            if text is None:
                return True
            if not isinstance(text, str):
                resolved = None
                try:
                    candidate = text.Text
                    if isinstance(candidate, str):
                        resolved = candidate
                except Exception:
                    pass
                if resolved is None:
                    try:
                        candidate = text.BestAnalysisAlternative.Text
                        if isinstance(candidate, str):
                            resolved = candidate
                    except Exception:
                        pass
                if resolved is None:
                    try:
                        candidate = text.BestVernacularAlternative.Text
                        if isinstance(candidate, str):
                            resolved = candidate
                    except Exception:
                        pass
                text = resolved if resolved is not None else str(text)
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

        # CP1 (issue #92): reaching this line without an exception does NOT
        # mean the write happened -- code that catches its own exceptions and
        # reports via report.Error() previously still yielded
        # result["success"] = True unconditionally. Reflect reality: any
        # reported error demotes the run to a failure.
        if result["summary"]["error_count"] > 0:
            result["success"] = False
            result["error_type"] = "ReportedError"
            result["error"] = (
                "Operation reported {} error(s) via report.Error(); see "
                "messages for details.".format(result["summary"]["error_count"])
            )
        else:
            result["success"] = True

    except Exception as e:
        error_msg = str(e)
        if error_msg.startswith("RESULTS:"):
            result["success"] = True
            result["output"] = error_msg[8:].strip()
        else:
            result["error"] = "Execution error: {}\\n{}".format(error_msg, traceback.format_exc())

    finally:
        # Issue #96 (A-7): CloseProject() is where the write actually commits
        # (EndNonUndoableTask() -> UnitOfWorkService.Save() -> Dispose()).
        # A bare `except: pass` here used to swallow a commit failure while
        # `result["success"]` had already been set True above -- silent
        # data loss reported as success. Capture the failure and demote the
        # run instead of discarding it. Preserve any prior error/messages
        # rather than clobbering them, since a teardown failure can follow
        # either a successful or an already-failed script body.
        if project:
            try:
                _maybe_refresh_from_disk(project)
                project.CloseProject()
            except Exception as e:
                _teardown_msg = "{}: {}".format(type(e).__name__, str(e))
                _teardown_tb = traceback.format_exc()
                if result.get("error"):
                    result["error"] = (
                        "{}\\n\\nAdditionally, project teardown failed (writes "
                        "may not have been committed): {}\\n{}"
                    ).format(result["error"], _teardown_msg, _teardown_tb)
                else:
                    result["error"] = (
                        "Project teardown failed after script execution "
                        "(writes may not have been committed): {}\\n{}"
                    ).format(_teardown_msg, _teardown_tb)
                result["success"] = False
                result["error_type"] = "TeardownError"
                result["teardown_error"] = {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": _teardown_tb,
                }
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
MODULE_CODE = {code}

{runner_script}
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
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
        log_dir_fn=get_log_dir,
        )
        return json_response(_finalize_run_module_response({
            "success": False,
            "error": err_msg,
            "warnings": warnings,
            "op_id": op_id,
        }))

    try:
        # Determine if we need the write lock. Issue #93 escalation: this
        # MUST call the same compute_is_mutating_script() that
        # build_writeability_payload() uses for the confirmation preview
        # (below) -- the two used to be independently (re)computed inline
        # here with a narrower formula, `(not cert['is_certified_readonly'])
        # or cud_info['is_cud']`, which is blind to GUARDED mutations found
        # only via the index (cert['protected_calls'] /
        # 'protected_liblcm_calls'), e.g. `if modifyAllowed:
        # project.CustomFields.CreateField(...)`. That gap let a live schema
        # mutation run with confirmed=False and no lock at all.
        is_mutating_script = compute_is_mutating_script(cert, cud_info)
        needs_lock = write_enabled and is_mutating_script

        # Issue #93 CP4 (T4.1): probe the project's real access state ONCE,
        # here, ahead of the confirmation gate. The probe is pure filesystem
        # (the .fwdata.lock JSON + SharedSettings\LexiconSettings.plsx) and
        # never opens a project, so it is safe this early -- and both the
        # confirmation preview's backup note (T4.2) and the lock gate below
        # need its verdict. Ordering is deliberate: an unconfirmed run against
        # an exclusively-held project still gets confirmation_required first,
        # exactly as before. Only computed under write intent; read-only runs
        # have never been gated and still are not (T4.3).
        # Parser-check CP4 (R-07): the probe AND the write decision it implies
        # (the project_locked refusal fields, the shared-mode advisory) come
        # from write_ladder.probe_write_access, the one implementation filing
        # shares. The refusal itself is still issued below, after the
        # confirmation gate -- the rung order is this handler's, not the
        # ladder's.
        _decision = None
        _probe_access = needs_lock or (not write_enabled)
        if _probe_access:
            _decision = write_ladder.probe_write_access(project_name)
        _access = _decision.access if _decision is not None else None
        _live_fw_peer = _decision is not None and _decision.live_peer
        _shared_mode_read_back = None
        if (not write_enabled) and _access is not None and _access.verdict == "open_shared":
            _shared_mode_read_back = {
                "verdict": "open_shared",
                "sharing_enabled": True,
                "holder_pid": _access.holder.pid if _access.holder else None,
                "holder_process": _access.holder.process_name if _access.holder else None,
                "note": (
                    "This read was opened as a fresh non-master peer while FLEx is "
                    "the shared-mode master. A fresh read-only session shows the "
                    "last master flush and may read pre-write state even when a peer "
                    "write already committed to the shared commit log. Do not treat "
                    "this read-back as proof a write was lost, and do not retry a "
                    "write solely based on this result."
                ),
            }

        # Issue #55 (Rung 3): enforce `confirmed` on mutating writes. Runs
        # BEFORE the project-lock probe / subprocess launch below so an
        # unconfirmed mutating run executes NOTHING -- no lock taken, no
        # subprocess spawned. Reuses the SAME writeability builder as #49's
        # validate_only so the two payloads can never drift apart.
        if needs_lock:
            _require_confirmation = bool(
                config_get(REQUIRE_WRITE_CONFIRMATION_KEY, REQUIRE_WRITE_CONFIRMATION_DEFAULT)
            )
            if _require_confirmation and not args.get("confirmed", False):
                _writeability = build_writeability_payload(
                    code, api_idx, code_tree, cud_info=cud_info, cert=cert
                )
                _backup_would_run = write_ladder.backup_intent(
                    project_name,
                    session_state=session_state,
                    backup_before_write=args.get("backup_before_write"),
                    config_get=config_get,
                ).would_run
                _mutation_count = len(_writeability["mutations_detected"])
                if _mutation_count > 0:
                    # Normal case: mutations_detected enumerates the hit(s).
                    _confirm_msg = (
                        f"This run would mutate the database ({_mutation_count} "
                        "mutation(s) detected) but confirmed=False. Review "
                        "`mutations_detected`, then resubmit the SAME call with "
                        "confirmed=True to execute."
                    )
                else:
                    # Issue #93 findings (a)/(d): is_mutating_script can fire from
                    # detect_cud_operations()'s line-blind signal even when no
                    # line-aware detector (Flexicon-wrapper or raw-LibLCM) could
                    # pin down and enumerate the specific call -- never claim a
                    # count of "0 mutation(s) detected" while still refusing the
                    # run as mutating; that is self-contradictory and sends the
                    # user to review an empty list.
                    _confirm_msg = (
                        "This run was flagged as mutating the database, but the "
                        "specific call(s) could not be individually enumerated "
                        "(`mutations_detected` is empty), and confirmed=False. "
                        "Review the script for write operations, then resubmit "
                        "the SAME call with confirmed=True to execute."
                    )
                _log_preflight_reject(
                    op_id, seq, time.monotonic() - t_start,
                    "confirmation_required",
                    f"mutations={_mutation_count}",
                log_dir_fn=get_log_dir,
                )
                return _attach_assistance_if_loop(
                    error_response(
                        "confirmation_required",
                        _confirm_msg,
                        writeability=_writeability,
                        mutations_detected=_writeability["mutations_detected"],
                        backup={
                            "intent": bool(_backup_would_run),
                            "note": (
                                (
                                    "A pre-write backup will be taken on the CONFIRMED "
                                    "execution, not on this preview."
                                    if _backup_would_run else
                                    "No new backup will be taken (already backed up this "
                                    "session for this project, or backup_before_write=False)."
                                )
                                + (_PEER_BACKUP_CAVEAT if (_backup_would_run and _live_fw_peer) else "")
                            ),
                        },
                        op_id=op_id,
                    ),
                    error_code="confirmation_required",
                    code_size_bytes=_code_size_bytes,
                )

        # Issue #93 CP4 (T4.1): write gate, driven by the access probe rather
        # than by the bare existence of a .fwdata.lock file.
        #
        # Issue #33 originally refused any write whenever a lock file existed.
        # That was an over-correction: with projectSharing="true" in the
        # project's SharedSettings\LexiconSettings.plsx, LCM promotes the
        # backend to SharedXMLBackendProvider (LcmCache.cs:211-226) and our
        # process attaches as a non-master peer that reads and writes through
        # the shared commit log -- which is the whole point, since the change
        # then shows up live in the FLEx UI. Refuse only the two verdicts a
        # write genuinely cannot survive:
        #
        #   free           -> proceed (unchanged)
        #   open_shared    -> proceed, with a shared_mode advisory on the result
        #   stale_lock     -> proceed; the claimed PID is dead and LCM treats a
        #                     stale lock as acquirable
        #   open_exclusive -> refuse; the user can fix this in FLEx in seconds
        #   held_by_other  -> refuse; a live non-FieldWorks holder is a real
        #                     collision
        #
        # Read-only runs never reach here (needs_lock is False), so exploring a
        # project while FLEx has it open keeps working regardless of verdict.
        _shared_mode = None
        if needs_lock and _decision is not None and _access is not None:
            if _decision.refusal is not None:
                # Issue #223: this is the point where a refusal is actually
                # issued (after confirmation, never at the earlier preview
                # probe), so releasing our own idle worker here cannot tear
                # one down under an unconfirmed call. Any holder left in the
                # re-probed decision below is genuine.
                _own_worker_refusal, _decision = await _release_own_worker_or_refuse(
                    project_name, _decision, op_id=op_id
                )
                if _own_worker_refusal is not None:
                    _refusal = _decision.refusal
                    _log_preflight_reject(
                        op_id, seq, time.monotonic() - t_start, "project_locked",
                        f"verdict={_decision.verdict} own_worker=busy "
                        f"holder_pid={_refusal.get('holder_pid')}",
                    log_dir_fn=get_log_dir,
                    )
                    return _attach_assistance_if_loop(
                        _own_worker_refusal,
                        error_code="project_locked",
                        code_size_bytes=_code_size_bytes,
                    )
            if _decision.refusal is not None:
                _refusal = _decision.refusal
                _lock_msg = (
                    f"Project '{project_name}' is held for exclusive access "
                    f"(verdict: {_decision.verdict}) and this script requests "
                    f"write access."
                )
                _log_preflight_reject(
                    op_id, seq, time.monotonic() - t_start, "project_locked",
                    f"verdict={_decision.verdict} sharing_enabled={_refusal['sharing_enabled']} "
                    f"holder_pid={_refusal['holder_pid']} "
                    f"holder_process={_refusal['holder_process']}",
                log_dir_fn=get_log_dir,
                )
                return _attach_assistance_if_loop(
                    error_response(
                        "project_locked",
                        _lock_msg,
                        **_refusal,
                        op_id=op_id,
                    ),
                    error_code="project_locked",
                    code_size_bytes=_code_size_bytes,
                )

            _shared_mode = _decision.advisory
            if _decision.verdict == "open_shared":
                get_operations_logger().info(
                    f"[SHARED] '{project_name}' open_shared (holder PID "
                    f"{_shared_mode['holder_pid']}); proceeding with the write "
                    "as a non-master peer."
                )
            elif _decision.verdict == "stale_lock":
                get_operations_logger().warning(
                    f"[SHARED] '{project_name}' stale_lock (dead PID "
                    f"{_shared_mode['holder_pid']}); proceeding with the write."
                )

        # Issue #55 (Rung 2): automatic pre-write backup, once per (session,
        # project). Runs AFTER the lock probe (so we don't back up a project
        # FieldWorks currently has locked) and BEFORE the subprocess launch.
        #
        # Issue #99: gate on write_enabled, not needs_lock. Preflight can miss
        # a mutating script (needs_lock=False) while write_enabled=True still
        # executes code that commits LCM actions -- the documented safety net
        # must not depend on static analysis being complete.
        #
        # The rung itself is write_ladder.take_backup (CP4, R-07), which applies
        # the once-per-(session, project) rule; this module's
        # perform_pre_write_backup is passed in so the name the ladder tests
        # patch is the one that runs.
        _backup_result: Optional[Dict[str, Any]] = None
        if write_enabled:
            _backup_result = write_ladder.take_backup(
                project_name,
                session_state=session_state,
                backup_before_write=args.get("backup_before_write"),
                live_peer=_live_fw_peer,
                perform=perform_pre_write_backup,
            )
        if _backup_result is not None:
            _bk_logger = get_operations_logger()
            if _backup_result.get("created"):
                _bk_logger.info(f"[BACKUP] '{project_name}' -> {_backup_result['path']}")
            elif _backup_result.get("skipped_reason") == "insufficient_disk_space":
                _bk_logger.warning(
                    f"[BACKUP] SKIPPED for '{project_name}': insufficient free disk space "
                    "(need >= 2x project size). Proceeding with the write WITHOUT a backup."
                )
            elif _backup_result.get("skipped_reason") not in (None, "backup_before_write=false"):
                _bk_logger.warning(
                    f"[BACKUP] SKIPPED for '{project_name}': {_backup_result.get('skipped_reason')}"
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
            log_dir_fn=get_log_dir,
            )
            return json_response(_finalize_run_module_response({
                "success": False,
                "error": err_msg,
                "warnings": warnings,
                "op_id": op_id,
            }))

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
        # Issue #55 (Rung 2) + #99: surface backup outcome on every write_enabled
        # execution so a silent skip is visible in the tool response.
        if write_enabled:
            if _backup_result is not None:
                execution_result["backup"] = _backup_result
            elif session_state.was_backed_up(project_name):
                execution_result["backup"] = {
                    "created": False,
                    "path": None,
                    "skipped_reason": "already_backed_up_this_session",
                }
            else:
                execution_result["backup"] = {
                    "created": False,
                    "path": None,
                    "skipped_reason": "backup_not_attempted",
                }
        # Issue #93 CP4 (T4.1): tell the caller the write went through a live
        # FLEx peer / over a stale lock rather than against an idle project.
        if _shared_mode is not None:
            execution_result["shared_mode"] = _shared_mode
        if _shared_mode_read_back is not None:
            execution_result["shared_mode_read_back"] = _shared_mode_read_back

        # CP5 FR-026: a write-enabled run that completed without error may have
        # changed the grammar, so the project's sandbox config cache is
        # invalidated. Trigger = write_enabled AND an error-free completion
        # (success True, no error). A read-only run never invalidates. A run
        # that errored (or timed out, which returned above) does not either:
        # the cache key includes the .fwdata mtime, so any partial write that
        # was saved still misses the cache on the next lookup. The helper is
        # lazy and guarded -- a sandbox failure can never break run_module.
        if write_enabled and execution_result.get("success") is True                 and not execution_result.get("error"):
            _invalidate_sandbox_cache_after_write(project_name)

        # Include write certification result (issue #131: surface guarded hits too)
        execution_result["write_certification"] = build_write_certification_payload(
            cert, cud_info
        )

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
            # Issue #12 (seth-logs sub-gap): a kclsid* class-id constant access is
            # a distinct, unrecoverable-by-rename failure -- pythonnet never
            # projects those constants. Check it first so we emit the ClassName/
            # ClassID guidance instead of a generic "no attribute" resolve hint
            # that can't actually fix it.
            class_id_info = detect_class_id_constant_error(execution_result["error"])
            if class_id_info.get("is_class_id_error"):
                execution_result["class_id_constant_detected"] = True
                execution_result["error_type"] = "ClassIdConstantError"
                execution_result["object_type"] = class_id_info["object_type"]
                execution_result["constant_name"] = class_id_info["constant_name"]
                execution_result["help"] = class_id_info["suggestion"]
                # Fall through skipped: the polymorphic/name-suggestion paths below
                # have nothing useful to add for a constant that doesn't exist.
                _skip_generic_attr_paths = True
            else:
                _skip_generic_attr_paths = False
            wrapper_internal = detect_flexicon_internal_attribute_error(
                execution_result["error"]
            )
            if wrapper_internal.get("is_wrapper_internal"):
                execution_result["wrapper_internal_error_detected"] = True
                execution_result["error_type"] = "WrapperInternalError"
                execution_result["object_type"] = wrapper_internal["object_type"]
                execution_result["property_name"] = wrapper_internal["property_name"]
                execution_result["help"] = wrapper_internal["suggestion"]
                execution_result["raising_frame"] = wrapper_internal.get("raising_frame")
                _skip_generic_attr_paths = True
            polymorphic_info = detect_polymorphic_error(execution_result["error"], _rt_casting_index)
            # Issue #39: Python's own "Did you mean: 'X'?" suffix is authoritative
            # about what exists on the live object, so for a typo it beats any
            # statically-guessed cast. Only trust the polymorphic (cast) path when
            # it produced a CONCRETE rewrite -- otherwise prefer the name
            # suggestion so the LLM self-corrects in one round-trip instead of
            # being told to "resubmit" for a preflight that can't catch a raw-LCM
            # attribute typo.
            native_did_you_mean = extract_python_did_you_mean(execution_result["error"])
            if _skip_generic_attr_paths:
                pass  # kclsid class-id constant handled above; nothing to add.
            elif polymorphic_info["is_polymorphic_error"] and polymorphic_info.get("rewrite"):
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
                    # No concrete rewrite and no name suggestion: hand the model the
                    # fix directly (#122) rather than deferring to a stateless resubmit.
                    execution_result["polymorphic_error_detected"] = True
                    execution_result["error_type"] = "PolymorphicAttributeError"
                    execution_result["object_type"] = polymorphic_info["object_type"]
                    execution_result["property_name"] = polymorphic_info["property_name"]
                    execution_result["help"] = polymorphic_info["suggestion"]
                    if polymorphic_info.get("cast_candidates"):
                        execution_result["cast_candidates"] = polymorphic_info["cast_candidates"]

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
                "help": execution_result.get("help"),
                "suggestion": execution_result.get("help"),
                "cast_candidates": execution_result.get("cast_candidates") or [],
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
            log_dir_fn=get_log_dir,
            )
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
            _effect_check = build_effect_check_payload(
                execution_result,
                write_enabled=write_enabled,
                is_mutating_script=is_mutating_script,
            )
            if _effect_check is not None:
                execution_result["effect_check"] = _effect_check
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
            log_dir_fn=get_log_dir,
            )
            # Issue #28: record a runtime-failure signal. Use the structured
            # error_type when available; fall back to a generic bucket.
            runtime_error_code = execution_result.get("error_type") or "runtime_error"
            return _attach_assistance_if_loop(
                json_response(
                    _finalize_run_module_response(execution_result),
                    ensure_ascii=False,
                ),
                error_code=runtime_error_code,
                code_size_bytes=code_size_bytes,
            )

        return json_response(
            _finalize_run_module_response(execution_result),
            ensure_ascii=False,
        )

    except subprocess.TimeoutExpired:
        err_msg = "Execution timed out after {} seconds".format(timeout_seconds)
        _log_operation_failure(
            op_id=op_id, seq=seq, duration_s=time.monotonic() - t_start,
            error=err_msg, error_type="TimeoutExpired",
        log_dir_fn=get_log_dir,
        )
        return json_response(_finalize_run_module_response({
            "success": False,
            "error": err_msg,
            "warnings": warnings,
            "op_id": op_id,
        }))

    except Exception as e:
        import traceback as _tb
        err_msg = "Subprocess execution error: {}".format(str(e))
        _log_operation_failure(
            op_id=op_id, seq=seq, duration_s=time.monotonic() - t_start,
            error=err_msg, error_type=type(e).__name__,
            traceback_text=_tb.format_exc(),
        log_dir_fn=get_log_dir,
        )
        return json_response(_finalize_run_module_response({
            "success": False,
            "error": err_msg,
            "warnings": warnings,
            "op_id": op_id,
        }))

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# T030 (parser-check CP1, D11): subprocess seam for first-party scan modules.
#
# This is intentionally a SEPARATE, much smaller path alongside
# `handle_run_module`, not a refactor of it. `handle_run_module`'s ~1800
# lines of write-lock negotiation, backup, AST-based casting injection and
# CUD preflight all exist to make arbitrary LLM-authored `code` TEXT safe to
# splice into `MODULE_CODE = {code}` and run. A scan module is a fixed,
# first-party file already living on disk (`server/scan/<name>.py`,
# T001/T019/T034/T035) that this seam merely IMPORTS -- none of that
# caller-supplied-text risk surface applies, so none of that machinery is
# reused here.
#
# What IS reused, per research.md D11 and cycle10-programmer-t029.md:
#   - `run_script_async` (subprocess_helpers.py) for the actual launch --
#     the SAME plain-CPython, `sys.executable`, `env=None` path generated
#     modules already use. No second execution mechanism.
#   - The `===FLEXTOOLS_USER_RESULT===` / `===FLEXTOOLS_RESULT_JSON===`
#     sentinel-pair convention (see `report.Result` on `SimpleReporter`
#     above, and the parsing block near "Issue #35" in `handle_run_module`)
#     for the return channel. Findings travel over the USER_RESULT sentinel;
#     the RESULT_JSON sentinel carries the run envelope (success/error/
#     messages), exactly as it does for `handle_run_module`.
#
# CP1 boundary: the scan module this seam launches must stay READ_ONLY_SAFE
# (reads grammar objects, opens no HCParser, parses no word) -- T026 asserts
# that statically/dynamically over `server/scan/**`; this seam has no
# opinion on what the imported function does and enforces nothing itself
# beyond passing `write_enabled` through unchanged.
# ---------------------------------------------------------------------------

def _build_scan_script(
    module_import_path: str,
    function_name: str,
    project_name: str,
    write_enabled: bool,
) -> str:
    """Build the standalone runner script for the T030 scan seam.

    Unlike `handle_run_module`'s `full_script` (which splices caller-supplied
    `code` TEXT into `MODULE_CODE = {code}` and `exec()`s it), this script's
    "module code" is a fixed, literal import + call -- never caller-supplied
    text -- so none of `handle_run_module`'s AST-parse/casting-injection/CUD
    preflight chain applies or is needed (research.md D11).

    The header (this function's own `.format()`) only substitutes four
    plain repr()'d config values as module-level globals; the harness body
    below is a STATIC string with no further interpolation, so it needs no
    brace-escaping and can be read/audited like ordinary Python.
    """
    header = (
        "# -*- coding: utf-8 -*-\n"
        '"""Scan module runner - Generated by FlexToolsMCP (T030 seam)."""\n'
        "PROJECT_NAME = {}\n"
        "WRITE_ENABLED = {}\n"
        "MODULE_IMPORT_PATH = {}\n"
        "FUNCTION_NAME = {}\n"
    ).format(
        repr(project_name),
        repr(bool(write_enabled)),
        repr(module_import_path),
        repr(function_name),
    )

    body = '''
import sys
import json
import importlib
import traceback

# Reconfigure stdout/stderr to UTF-8 BEFORE any print() runs, same as the
# handle_run_module runner (grammar/gloss text can contain non-cp1252
# characters that would otherwise raise UnicodeEncodeError mid-print and
# kill the sentinel output, producing a silent "no findings" failure).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    import codecs
    if getattr(sys.stdout, "buffer", None):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")
    if getattr(sys.stderr, "buffer", None):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, errors="replace")


class SimpleReporter:
    """Minimal reporter for the scan seam.

    Only `Result(...)` is required by the fixed "module code" (`report.Result
    (run_grammar_scan(project))`), but Info/Warning/Error are provided for
    parity with handle_run_module's SimpleReporter in case a scan module
    logs through a passed-in reporter in a later phase.
    """

    def __init__(self):
        self.messages = []

    def _log(self, level, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)
        self.messages.append({"type": level, "message": msg, "ref": ref})
        print("[{}] {}".format(level, msg))

    def Info(self, msg, ref=None):
        self._log("INFO", msg, ref)

    def Warning(self, msg, ref=None):
        self._log("WARNING", msg, ref)

    def Error(self, msg, ref=None):
        self._log("ERROR", msg, ref)

    def Result(self, data):
        """Same wire format as handle_run_module's SimpleReporter.Result:
        print the ===FLEXTOOLS_USER_RESULT=== sentinel, then a JSON blob.
        This is the ONLY findings channel -- do not add a second one."""
        payload = json.dumps(data, ensure_ascii=False)
        print("===FLEXTOOLS_USER_RESULT===")
        print(payload)


def _maybe_refresh_from_disk(project):
    if not WRITE_ENABLED or project is None:
        return
    try:
        import flexicon

        if "refresh-from-disk" not in getattr(flexicon, "CAPABILITIES", ()):
            return
        refresh = getattr(project, "RefreshFromDisk", None)
        if callable(refresh):
            refresh()
    except Exception:
        pass


def run_scan():
    result = {
        "success": False,
        "project": PROJECT_NAME,
        "write_enabled": WRITE_ENABLED,
        "messages": [],
        "error": None,
        "error_type": None,
    }
    project = None
    report = SimpleReporter()

    try:
        from flexicon import FLExInitialize, FLExCleanup, FLExProject

        # Same headless-UI wiring as handle_run_module's runner (#96 / #148).
        import flexicon as _flexicon_pkg
        _UI_CAPS = getattr(_flexicon_pkg, "CAPABILITIES", frozenset())
        if "ui-injection" in _UI_CAPS:
            try:
                from flexicon import HeadlessLcmUI
                _lcm_ui = HeadlessLcmUI()
            except ImportError:
                _lcm_ui = None
                report.Warning(
                    "flexicon advertises ui-injection but HeadlessLcmUI is not "
                    "importable from the top-level flexicon package; OpenProject "
                    "will omit ui= and use flexicon's default LcmUI."
                )
        else:
            _lcm_ui = None
            report.Warning(
                "This flexicon build does not advertise ui-injection in "
                "CAPABILITIES; OpenProject will omit ui= and use flexicon's "
                "default LcmUI."
            )

        FLExInitialize()
        project = FLExProject()

        # Issue #159: `ui=` only exists on flexicon >=4.4.0 OpenProject();
        # a stray older build (mismatched venv) rejects it with TypeError.
        # Probe the INSTALLED signature here, in this subprocess -- a
        # server-side probe could approve a kwarg a different venv rejects.
        try:
            import inspect
            _openproject_accepts_ui = "ui" in inspect.signature(FLExProject.OpenProject).parameters
        except Exception:
            _openproject_accepts_ui = False

        try:
            # undoable=False: see handle_run_module's runner for why (issue
            # #92 -- undoable=True skips BeginNonUndoableTask() and opens no
            # UnitOfWork). CP1 scans never write, but the same OpenProject
            # convention is reused here for consistency, not novelty.
            if _openproject_accepts_ui:
                project.OpenProject(
                    projectName=PROJECT_NAME,
                    writeEnabled=WRITE_ENABLED,
                    undoable=False,
                    ui=_lcm_ui,
                )
            else:
                report.Warning(
                    "this flexicon build's OpenProject() does not accept the "
                    "ui= argument; opening with this build's default LCM UI "
                    "instead (issue #159)."
                )
                project.OpenProject(
                    projectName=PROJECT_NAME,
                    writeEnabled=WRITE_ENABLED,
                    undoable=False,
                )
        except Exception as e:
            result["error"] = "Failed to open project '{}': {}".format(PROJECT_NAME, str(e))
            result["error_type"] = "ProjectOpenError"
            result["messages"] = report.messages
            return result

        try:
            scan_mod = importlib.import_module(MODULE_IMPORT_PATH)
        except Exception as e:
            result["error"] = "Failed to import scan module '{}': {}".format(MODULE_IMPORT_PATH, str(e))
            result["error_type"] = "ScanModuleImportError"
            result["messages"] = report.messages
            return result

        try:
            scan_fn = getattr(scan_mod, FUNCTION_NAME)
        except AttributeError as e:
            result["error"] = "Scan module '{}' has no attribute '{}': {}".format(
                MODULE_IMPORT_PATH, FUNCTION_NAME, str(e)
            )
            result["error_type"] = "ScanFunctionNotFound"
            result["messages"] = report.messages
            return result

        findings = scan_fn(project)
        report.Result(findings)

        result["messages"] = report.messages
        result["success"] = True

    except Exception as e:
        result["error"] = "Scan execution error: {}\\n{}".format(str(e), traceback.format_exc())
        result["error_type"] = type(e).__name__
        result["messages"] = report.messages

    finally:
        if project is not None:
            try:
                _maybe_refresh_from_disk(project)
                project.CloseProject()
            except Exception as e:
                _teardown_msg = "{}: {}".format(type(e).__name__, str(e))
                if result.get("error"):
                    result["error"] = "{}\\n\\nAdditionally, project teardown failed: {}".format(
                        result["error"], _teardown_msg
                    )
                else:
                    result["error"] = "Project teardown failed after scan execution: {}".format(_teardown_msg)
                result["error_type"] = result["error_type"] or "TeardownError"
                result["success"] = False
        try:
            FLExCleanup()
        except Exception:
            pass

    return result


if __name__ == "__main__":
    _result = run_scan()
    print("===FLEXTOOLS_RESULT_JSON===")
    print(json.dumps(_result, indent=2, ensure_ascii=False))
'''

    return header + body


async def run_scan_module(
    module_import_path: str,
    function_name: str,
    project_name: str,
    write_enabled: bool = False,
    timeout_seconds: int = 300,
) -> Dict[str, Any]:
    """T030 seam: run a first-party scan module against a named FLEx project
    in a subprocess, and return its findings.

    Launches through the exact same `run_script_async` path generated
    modules already use (`subprocess_helpers.run_script_async`, plain
    CPython via `sys.executable`) -- this is not a second execution
    mechanism. The "module code" run in the subprocess is a fixed, literal
    `from <module_import_path> import <function_name>; report.Result(
    <function_name>(project))`, never caller-supplied text, so none of
    `handle_run_module`'s preflight/casting-injection chain applies.

    `server/scan/grammar_scan_module.py` (T019/T034/T035) does not exist
    yet at the time this seam is built; nothing here hard-codes its
    presence -- callers simply pass whatever `module_import_path` /
    `function_name` they want, and a missing module surfaces as a clear
    `ScanModuleImportError`, not a silent empty-findings result.

    Args:
        module_import_path: dotted import path of the scan module, e.g.
            "flextoolsmcp.server.scan.grammar_scan_module".
        function_name: name of the callable in that module taking a single
            `project` argument and returning JSON-serializable findings.
        project_name: FieldWorks project to open (opened ONLY in the
            subprocess -- the MCP server process itself never opens a
            project; see CP1 boundary in T030's task brief).
        write_enabled: passed through to `OpenProject(writeEnabled=...)`.
            CP1 scans are READ_ONLY_SAFE and should always pass False; the
            flag exists so this seam is not CP1-specific.
        timeout_seconds: forwarded to `run_script_async`.

    Returns:
        A dict that ALWAYS distinguishes "the scan never ran" from "the scan
        ran and found nothing":
          - `ran`: False means the subprocess never produced a parseable
            result envelope at all (crash, timeout, garbled/truncated
            output) -- there is no reliable signal about what happened
            inside the scan. `ran`: True means the envelope was parsed
            (whether or not the scan itself succeeded).
          - `success`: True only when the scan completed, reported no
            internal error, AND called `report.Result(...)` with a
            findings payload (`findings` set, possibly to an empty
            list/dict -- that IS a valid "no findings" result, distinct
            from `findings=None`).
          - `findings`: the JSON-decoded payload from `report.Result(...)`,
            or None if it was never produced.
          - `error` / `error_type`: set whenever `ran` or `success` is
            False. `error_type` values: "Timeout", "NoResultMarker"
            (subprocess produced no ===FLEXTOOLS_RESULT_JSON=== marker at
            all -- crashed before printing it, or was killed), "JSONDecode
            Error" (marker present but unparseable), "ProjectOpenError",
            "ScanModuleImportError", "ScanFunctionNotFound",
            "MissingFindingsPayload" (scan reported success but never
            called `report.Result(...)`), "TeardownError", or the scan
            function's own raised exception type name.
          - `returncode`, `stderr`, `messages`: diagnostic passthrough.
    """
    script_text = _build_scan_script(
        module_import_path=module_import_path,
        function_name=function_name,
        project_name=project_name,
        write_enabled=write_enabled,
    )

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script_text)
            temp_script_path = f.name
    except Exception as e:
        return {
            "ran": False,
            "success": False,
            "findings": None,
            "error": "Failed to create temporary scan script: {}".format(e),
            "error_type": type(e).__name__,
        }

    try:
        proc_result = await run_script_async(temp_script_path, timeout_seconds=timeout_seconds)
    finally:
        try:
            os.unlink(temp_script_path)
        except Exception:
            pass

    stdout = proc_result["stdout"]
    stderr = proc_result["stderr"]

    if proc_result["timeout"]:
        return {
            "ran": False,
            "success": False,
            "findings": None,
            "error": "Scan subprocess timed out after {} seconds".format(timeout_seconds),
            "error_type": "Timeout",
            "returncode": proc_result["returncode"],
            "stderr": stderr,
        }

    # Reuses the SAME sentinel-pair convention `handle_run_module` reads
    # (see the "Issue #35" block above) -- do not invent a second result
    # channel. Findings ride the USER_RESULT sentinel; the run envelope
    # (success/error/messages) rides RESULT_JSON, exactly as for a generated
    # module.
    _user_result_sentinel = "===FLEXTOOLS_USER_RESULT==="
    findings = None
    findings_raw = None
    if _user_result_sentinel in stdout:
        _ur_start = stdout.index(_user_result_sentinel) + len(_user_result_sentinel)
        _ur_end = stdout.find("===FLEXTOOLS_RESULT_JSON===", _ur_start)
        _ur_raw = (stdout[_ur_start:_ur_end] if _ur_end != -1 else stdout[_ur_start:]).strip()
        try:
            findings = json.loads(_ur_raw)
        except json.JSONDecodeError:
            findings_raw = _ur_raw

    envelope = None
    if "===FLEXTOOLS_RESULT_JSON===" in stdout:
        json_start = stdout.index("===FLEXTOOLS_RESULT_JSON===") + len("===FLEXTOOLS_RESULT_JSON===")
        json_str = stdout[json_start:].strip()
        try:
            envelope = json.loads(json_str)
        except json.JSONDecodeError as e:
            return {
                "ran": False,
                "success": False,
                "findings": None,
                "error": "Failed to parse scan result envelope: {}".format(e),
                "error_type": "JSONDecodeError",
                "returncode": proc_result["returncode"],
                "raw_stdout": stdout,
                "stderr": stderr,
            }

    if envelope is None:
        # "Scan never ran" (or never finished): no RESULT_JSON marker at
        # all, distinguishable from a marker that reports zero findings.
        return {
            "ran": False,
            "success": False,
            "findings": None,
            "error": (
                "Scan subprocess produced no result marker "
                "(===FLEXTOOLS_RESULT_JSON=== not found in stdout); the "
                "scan did not complete."
            ),
            "error_type": "NoResultMarker",
            "returncode": proc_result["returncode"],
            "raw_stdout": stdout,
            "stderr": stderr,
        }

    if not envelope.get("success"):
        return {
            "ran": True,
            "success": False,
            "findings": None,
            "error": envelope.get("error") or "Scan reported failure with no error detail.",
            "error_type": envelope.get("error_type") or "ScanFailed",
            "returncode": proc_result["returncode"],
            "messages": envelope.get("messages", []),
            "stderr": stderr,
        }

    if findings is None and findings_raw is None:
        # Scan completed and reported success but never called
        # report.Result(...) -- the findings channel itself is missing.
        # This is a bug in the scan module, not "zero findings" (which
        # would show up as findings=[] or findings={} here).
        return {
            "ran": True,
            "success": False,
            "findings": None,
            "error": (
                "Scan '{}' completed successfully but never called "
                "report.Result(...); no findings payload was produced."
            ).format(function_name),
            "error_type": "MissingFindingsPayload",
            "returncode": proc_result["returncode"],
            "messages": envelope.get("messages", []),
            "stderr": stderr,
        }

    return {
        "ran": True,
        "success": True,
        "findings": findings if findings is not None else findings_raw,
        "error": None,
        "error_type": None,
        "returncode": proc_result["returncode"],
        "messages": envelope.get("messages", []),
        "stderr": stderr if stderr else None,
    }


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
                lines = [line for line in lines if '| ERROR' in line or '| FAIL' in line or '[FAIL]' in line]

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
