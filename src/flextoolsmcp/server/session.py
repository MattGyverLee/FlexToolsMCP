#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session state management for FlexToolsMCP.

Tracks session-wide settings, API discovery/validation, and operation history
(Feature 3).
"""

import re
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any, Deque, Tuple


# Setup logging
logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for operation detail extraction (5-10x faster than re-compiling)
_STATUS_PATTERN = re.compile(r"\[(OK|WARN|ERROR|INFO)\]\s+(.+)", re.MULTILINE)
_NAME_PATTERN = re.compile(r"'([^']+)'")
_HVO_PATTERN = re.compile(r"hvo=(\d+)")


# Issue #28: tailored next-step hints per error class. Keep the strings short --
# they ride on every rejection response once the detector trips, and the LLM has
# to actually read them. The default fallback covers any error_code not in the map.
_ASSISTANCE_HINTS_BY_ERROR_CODE = {
    "casting_issues_detected": (
        # Issue #28 follow-up: #21 inlines the cast rewrite directly into
        # the rejection payload at casting_issues[*].rewrite (and
        # imports_needed). After 5 retry loops, the LLM needs to read what
        # the rejection already provided, not chase another tool call.
        "the inlined rewrite in casting_issues[*].rewrite is the right "
        "fix. If that field is null (chained or call-rooted receiver), "
        "call flextools_resolve_property with the property name and "
        "context entity -- but otherwise apply what's already in the "
        "rejection."
    ),
    "undiscovered_entity": (
        "the Operations class hasn't been discovered for this session. "
        "Call flextools_get_object_api on the entity (e.g. LexEntry, "
        "POS) before referencing it again."
    ),
    "project_not_open": (
        # Issue #53: the rejection payload now inlines available_projects
        # (from the same safe enumeration flextools_list_projects uses) --
        # pick directly from that list instead of making a separate call.
        "pick one of available_projects in this payload and pass it as "
        "project_name to flextools_start (or directly to flextools_run_module)."
    ),
    "project_name_required": (
        # Issue #53: same self-healing payload -- available_projects is
        # already attached to this rejection.
        "pick one of available_projects in this payload and pass it as "
        "project_name."
    ),
    "syntax_error": (
        "the Python is malformed. Read the line number in the error and "
        "fix the syntax -- don't resubmit substantially-similar code."
    ),
    "server_state_error": (
        "the server didn't initialize cleanly. Call flextools_health "
        "(verbose=True for project-lock/pythonnet detail) for a diagnostic "
        "snapshot instead of reading server logs -- retrying won't help."
    ),
    "partial_module_structure": (
        "call flextools_get_module_template to get the full "
        "Main/docs/FlexToolsModule scaffold, OR drop the def Main "
        "wrapper entirely and submit the body as a bare snippet."
    ),
}


def _assistance_message_for_error(
    error_code: Optional[str],
    count: int = 5,
    oscillating: bool = False,
) -> str:
    """Compose a human-readable assistance message for a detected retry pattern.

    Pulls a tailored hint from _ASSISTANCE_HINTS_BY_ERROR_CODE; falls back to
    a generic prompt for unknown error codes.
    """
    hint = _ASSISTANCE_HINTS_BY_ERROR_CODE.get(
        error_code or "",
        "the same error keeps firing. Stop iterating: call "
        "flextools_find_examples for a worked pattern, or "
        "flextools_search_by_capability to discover the right API."
    )
    if oscillating:
        prefix = (
            f"You've alternated between two code shapes {count} times and "
            f"all of them failed with {error_code!r}: "
        )
    else:
        prefix = f"You've hit {error_code!r} {count} times in a row: "
    return prefix + hint


@dataclass
class OperationRecord:
    """Records details of a single operation for history."""
    timestamp: datetime
    tool: str                    # tool name, currently always 'run_module'
    args_summary: str           # Human-readable summary of tool arguments
    script_code: str            # Full script code that was executed
    script_output: str          # Captured stdout/stderr from execution
    success: bool               # Whether operation succeeded
    project: str = ""           # Project name at execution time
    extracted_details: Dict[str, Any] = field(default_factory=dict)  # Parsed from output


@dataclass
class SessionState:
    """Tracks session-wide settings to ensure consistency across tool calls.

    Set by the 'start' tool and respected by all other tools unless overridden.
    Also tracks operation history (Feature 3).
    """
    session_id: str = ""                   # Session ID (uuid4 hex, stamped on configure())
    api_mode: str = "flexicon"            # API mode: flexicon, flexlibs_stable, liblcm
    output_type: str = "auto"              # Output type: auto, operation, module
    project_name: str = ""                 # FLEx project name (empty = prompt user)
    write_enabled: bool = False            # Write access: False = read-only/dry-run
    # Diagnostic-report feature (spec section 4): verbatim human request text for
    # the current turn, set by flextools_start. run_module falls back to this when
    # its own per-op user_request override is absent. Reset (not inherited) on every
    # configure() call because flextools_start marks a new turn boundary.
    user_request: str = ""
    initialized: bool = False
    discovered_apis: set = field(default_factory=set)        # APIs discovered via search_by_capability
    validated_apis: set = field(default_factory=set)         # APIs validated via get_object_api
    # Issue #47: auto-discovered entities on read-only runs.  Kept SEPARATE from
    # validated_apis so the write gate (detect_undiscovered_entities reads
    # validated_apis only) never sees auto-granted entities.
    auto_discovered_apis: set = field(default_factory=set)   # Auto-granted on READ-ONLY runs only
    api_versions: dict = field(default_factory=dict)         # Track active API versions: {api_name: version}

    # Feature 3: Session History
    operations_history: List[OperationRecord] = field(default_factory=list)  # Full audit trail

    # Issue #55 (Rung 2): projects for which a pre-write backup has already
    # been taken THIS session. Ensures the backup fires exactly once per
    # (session, project) instead of on every mutating run.
    backed_up_projects: set = field(default_factory=set)

    # Issue #53: count of cold-start auto-initializations performed this
    # session (a READ_ONLY_SAFE tool -- or run_module with an explicit
    # project_name -- called with no prior flextools_start). The happy path
    # is exactly 0 or 1 per conversation. A count > 1 means the session was
    # observed uninitialized MORE THAN ONCE, which -- since nothing in this
    # codebase intentionally resets `initialized` back to False mid-session
    # -- signals the underlying session-loss bug (#10/#42) is biting, not
    # that cold-start tolerance is working as designed. record_auto_init()
    # logs at WARNING starting on the second occurrence; #53 must not mask
    # #10 by silently absorbing repeat auto-inits.
    auto_init_count: int = 0

    def record_auto_init(self) -> int:
        """Record a cold-start auto-initialization and return the new count.

        Call this exactly once per auto-init event (never for an explicit
        flextools_start call). Logs INFO for the first occurrence and
        WARNING for every subsequent one within the same session -- see
        the auto_init_count docstring for why repeats are suspicious.
        """
        self.auto_init_count += 1
        if self.auto_init_count > 1:
            logger.warning(
                f"[AUTO-INIT-REPEAT] Session auto-initialized {self.auto_init_count} "
                f"times this conversation -- this usually means the session was lost "
                f"between calls (see issues #10/#42), not that cold-start tolerance "
                f"is working as designed."
            )
        else:
            logger.info("[AUTO-INIT] Session auto-initialized (flexicon, read-only).")
        return self.auto_init_count

    # Issue #28: Retry-loop / size-oscillation detector. Each entry is
    # (timestamp, error_code, code_size_bytes); only the last 5 ops are
    # retained. error_code is None for successful ops -- a success resets
    # the loop detector (logically: we cleared the bad pattern).
    recent_op_signals: Deque[Tuple[datetime, Optional[str], int]] = field(
        default_factory=lambda: deque(maxlen=5)
    )

    def configure(self, **kwargs) -> None:
        """Configure session settings (called by start tool).

        Session identity rules (issue #42 + P0 fix):

        A new session boundary is crossed -- and discovery state wiped -- only
        when ONE of the following is true:
          (a) An explicit ``session_id`` kwarg is passed AND it differs from
              the currently stored session_id.
          (b) ``project_name`` kwarg is passed and is non-empty AND it differs
              from the currently stored project_name (project change).
          (c) ``new_session=True`` is passed as an explicit override signal.

        In all other cases (including the production re-start path where
        admin.py calls configure() with NO session_id kwarg for the SAME
        project) this is treated as a *continuation* of the current session
        and discovery state is preserved.

        A uuid4 fallback is used ONLY for the genuine first-configure case
        where no session identity anchor exists yet (self.session_id is empty
        and no kwarg provides one).

        Within the same session discovery is preserved -- the count==1
        requirement for auto-discovered entities (#47) depends on this.
        """
        explicit_session_id = kwargs.pop("session_id", None)
        new_session_flag = kwargs.pop("new_session", False)
        incoming_project = kwargs.get("project_name", None)

        # Detect which kind of session boundary we have.
        if explicit_session_id is not None:
            # Caller supplied an explicit token (test path or future callers).
            incoming_session_id = explicit_session_id
            is_new_session = (incoming_session_id != self.session_id)
        elif new_session_flag:
            # Explicit override signal -- always a new session.
            incoming_session_id = uuid.uuid4().hex
            is_new_session = True
        elif not self.session_id:
            # First configure ever -- mint a uuid anchored to project if given.
            anchor = incoming_project or uuid.uuid4().hex
            incoming_session_id = f"auto-{anchor[:32]}"
            is_new_session = True
        elif (
            incoming_project
            and incoming_project != self.project_name
        ):
            # Project changed -- this IS a new logical session.
            incoming_session_id = f"auto-{incoming_project[:32]}"
            is_new_session = True
        else:
            # No session_id kwarg, same project (or no project yet) --
            # continue current session; do NOT mint a new uuid.
            incoming_session_id = self.session_id
            is_new_session = False

        if is_new_session:
            logger.info(
                f"New session detected (old={self.session_id!r} -> new={incoming_session_id!r}); "
                f"clearing discovery state."
            )
            self.clear_discovered_apis()
        self.session_id = incoming_session_id

        # Warn on unrecognised kwargs to surface typos (e.g. write_enbled=True).
        _known_kwargs = {
            "api_mode", "output_type", "project_name", "write_enabled",
            "api_versions", "user_request",
        }
        _unknown = set(kwargs) - _known_kwargs
        if _unknown:
            logger.warning(
                f"configure() received unrecognised kwargs (possible typo?): "
                f"{sorted(_unknown)!r} -- ignored."
            )

        if "api_mode" in kwargs:
            self.api_mode = kwargs["api_mode"]
        if "output_type" in kwargs:
            self.output_type = kwargs["output_type"]
        if "project_name" in kwargs:
            self.project_name = kwargs["project_name"]
        if "write_enabled" in kwargs:
            self.write_enabled = kwargs["write_enabled"]
        if "api_versions" in kwargs:
            self.api_versions = kwargs["api_versions"]
        if "user_request" in kwargs:
            # Turn-level field: always reset to whatever this configure() call
            # provided (including ""), never inherited from the prior turn.
            self.user_request = kwargs["user_request"] or ""
        self.initialized = True
        mode_info = f"mode={self.api_mode}, output={self.output_type}"
        mode_info += f", project={self.project_name or '(prompt)'}"
        mode_info += f", write={self.write_enabled}"
        mode_info += f", session_id={self.session_id[:8]}..."
        if self.api_versions:
            versions_str = ", ".join(f"{k}={v}" for k, v in sorted(self.api_versions.items()))
            mode_info += f", versions={{{versions_str}}}"
        logger.info(f"Session configured: {mode_info}")

    def record_discovered_api(self, entity: str, method: str) -> None:
        """Record an API that was discovered via get_object_api or search_by_capability."""
        api_key = f"{entity}.{method}" if entity else method
        self.discovered_apis.add(api_key)

    def get_discovered_apis(self) -> set:
        """Get the set of discovered API methods."""
        return self.discovered_apis

    def was_api_discovered(self, entity: str, method: str) -> bool:
        """Check if a specific API was discovered."""
        api_key = f"{entity}.{method}" if entity else method
        # Also check just the method name for flexibility
        return api_key in self.discovered_apis or method in self.discovered_apis

    def clear_discovered_apis(self) -> None:
        """Clear discovered APIs (for new session boundary).

        Called from configure() when a new session_id is detected. Also clears
        auto_discovered_apis (#47) because auto-grants are session-scoped.
        """
        self.discovered_apis = set()
        self.validated_apis = set()
        self.auto_discovered_apis = set()
        # Issue #55 (Rung 2): a new session boundary means "no backup taken
        # yet" for any project -- the prior session's backup is still on disk,
        # but this session hasn't verified it applies to the current state.
        self.backed_up_projects = set()

    def record_validated_api(self, entity: str) -> None:
        """Record an API that was validated via get_object_api."""
        self.validated_apis.add(entity)

    # --- Issue #47: auto-discovery set (read-only runs only) ---

    def record_auto_discovered_api(self, entity: str) -> None:
        """Record an entity auto-discovered on a READ-ONLY run.

        Kept SEPARATE from validated_apis so the write gate continues to
        re-trigger for these entities on the first WRITE run.
        """
        self.auto_discovered_apis.add(entity)

    def was_auto_discovered(self, entity: str) -> bool:
        """Return True if entity was already auto-discovered this session."""
        return entity in self.auto_discovered_apis

    def get_unvalidated_apis(self) -> set:
        """Get APIs discovered but not yet validated via get_object_api."""
        return self.discovered_apis - self.validated_apis

    def get_mode(self) -> str:
        """Get the current session API mode."""
        return self.api_mode

    def get_output_type(self) -> str:
        """Get the current session output type."""
        return self.output_type

    def get_project(self) -> str:
        """Get the current session project name (empty if not set)."""
        return self.project_name

    def is_write_enabled(self) -> bool:
        """Get whether write access is enabled for the session."""
        return self.write_enabled

    def get_user_request(self) -> str:
        """Get the turn-level verbatim user_request set by flextools_start.

        Diagnostic-report feature (spec section 4). Empty string if never set
        or if the current turn's flextools_start call omitted it.
        """
        return self.user_request

    # --- Issue #55 (Rung 2): per-(session, project) backup tracking ---

    def was_backed_up(self, project_name: str) -> bool:
        """Return True if a pre-write backup already ran this session for project_name."""
        return project_name in self.backed_up_projects

    def record_backup(self, project_name: str) -> None:
        """Mark project_name as backed-up for the remainder of this session."""
        self.backed_up_projects.add(project_name)

    def summary(self) -> dict:
        """Return session state summary for tool responses."""
        result = {
            "api_mode": self.api_mode,
            "output_type": self.output_type,
            "project_name": self.project_name or "(not set)",
            "write_enabled": self.write_enabled,
            "initialized": self.initialized,
            "discovered_api_count": len(self.discovered_apis)
        }
        return result

    # ===== Feature 3: Session History =====

    @staticmethod
    def _extract_operation_details(script_output: str) -> Dict[str, Any]:
        """Parse script output to extract operation details.

        Looks for patterns like:
        - "[OK] Created entry 'water' (hvo=12345)"
        - "[OK] Updated sense 1 of 'water'"
        - "[OK] Deleted entry with hvo=12345"

        Args:
            script_output: Captured stdout from script execution

        Returns:
            Dictionary with extracted details (operation_type, entity_name, hvo, etc.)
        """
        details = {}

        # Use pre-compiled patterns (module-level constants, 5-10x faster)
        match = _STATUS_PATTERN.search(script_output)
        if match:
            details["status"] = match.group(1)
            details["message"] = match.group(2).strip()

        # Try to detect Create/Update/Delete from message
        message = details.get("message", "").lower()
        if "creat" in message:
            details["operation_type"] = "CREATE"
        elif "updat" in message or "modif" in message or "chang" in message:
            details["operation_type"] = "UPDATE"
        elif "delet" in message or "remov" in message:
            details["operation_type"] = "DELETE"
        else:
            details["operation_type"] = "READ"

        # Extract entity name from quotes (using pre-compiled pattern)
        name_match = _NAME_PATTERN.search(details.get("message", ""))
        if name_match:
            details["entity_name"] = name_match.group(1)

        # Extract hvo (handle value, FLEx unique ID) (using pre-compiled pattern)
        hvo_match = _HVO_PATTERN.search(details.get("message", ""))
        if hvo_match:
            details["hvo"] = int(hvo_match.group(1))

        return details

    def get_history_summary(self) -> dict:
        """Get a summary of the operation history for the session.

        Returns:
            Dictionary with history stats (totals by operation type).
        """
        # Single-pass iteration: count operation types in O(n) instead of O(4n)
        create_count = update_count = delete_count = 0
        for op in self.operations_history:
            op_type = op.extracted_details.get("operation_type")
            if op_type == "CREATE":
                create_count += 1
            elif op_type == "UPDATE":
                update_count += 1
            elif op_type == "DELETE":
                delete_count += 1

        return {
            "total_operations": len(self.operations_history),
            "create_count": create_count,
            "update_count": update_count,
            "delete_count": delete_count,
        }

    # ===== Issue #28: Retry-loop / size-oscillation detection =====

    def record_op_signal(
        self,
        error_code: Optional[str],
        code_size_bytes: int,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Append a one-tuple signal for the retry-loop detector.

        Call this AFTER every run_module attempt (success OR failure):
          - On failure: pass the rejection or runtime error_code.
          - On success: pass error_code=None, which acts as a reset for the
            detector (a working op breaks the pattern by definition).

        Maintaining a fixed-size deque keeps the per-session footprint
        bounded at maxlen=5 entries.
        """
        self.recent_op_signals.append(
            (timestamp or datetime.now(), error_code, code_size_bytes)
        )

    def reset_op_signals(self) -> None:
        """Drop all retry-loop signals (e.g., after a successful op)."""
        self.recent_op_signals.clear()

    def detect_retry_loop_pattern(self) -> Optional[Dict[str, Any]]:
        """Inspect the last 5 op signals for stuck-in-a-loop patterns.

        Two patterns trigger detection:

        1. ``same_error_retry_loop``: 4+ consecutive ops with identical
           non-None ``error_code`` within a 5-minute window. The LLM is
           hammering the same failure mode.

        2. ``size_oscillation``: 4 consecutive ops with code_size deltas
           alternating sign (up/down/up/down or down/up/down/up) and all
           4 prior + current failing. The LLM is bouncing between two
           shapes hoping one will work.

        Returns the detected pattern dict (with ``pattern_detected`` and a
        tailored ``message``) or None if no pattern matches. Caller is
        responsible for surfacing the result; this function never mutates
        state.
        """
        signals = list(self.recent_op_signals)
        # Need at least 5 entries to evaluate "4 prior + current".
        if len(signals) < 5:
            return None

        last5 = signals[-5:]
        # All five must be failures for either pattern to fire.
        if any(s[1] is None for s in last5):
            return None

        # --- Pattern 1: same error 4+ times in <5min ---
        error_codes = [s[1] for s in last5]
        if all(ec == error_codes[-1] for ec in error_codes):
            time_span = (last5[-1][0] - last5[0][0]).total_seconds()
            if time_span < 300:  # 5 minutes
                return {
                    "pattern_detected": "same_error_retry_loop",
                    "message": _assistance_message_for_error(error_codes[-1], count=5),
                    "error_code": error_codes[-1],
                    "occurrences": 5,
                    "window_seconds": int(time_span),
                }

        # --- Pattern 2: size oscillation across 5 consecutive failures ---
        sizes = [s[2] for s in last5]
        deltas = [sizes[i + 1] - sizes[i] for i in range(4)]
        # Need all deltas non-zero and alternating in sign.
        if all(d != 0 for d in deltas):
            signs = [1 if d > 0 else -1 for d in deltas]
            if signs == [1, -1, 1, -1] or signs == [-1, 1, -1, 1]:
                return {
                    "pattern_detected": "size_oscillation",
                    "message": _assistance_message_for_error(
                        error_codes[-1], count=5, oscillating=True
                    ),
                    "error_code": error_codes[-1],
                    "code_sizes": sizes,
                }

        return None

    def export_history(self) -> List[Dict[str, Any]]:
        """Export full operation history as list of dictionaries.

        Useful for get_session_history tool response.

        Returns:
            List of operation records with all details.
        """
        return [
            {
                "timestamp": op.timestamp.isoformat(),
                "tool": op.tool,
                "args_summary": op.args_summary,
                "success": op.success,
                "project": op.project,
                "extracted_details": op.extracted_details,
            }
            for op in self.operations_history
        ]
