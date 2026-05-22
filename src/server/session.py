#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session state management for FlexToolsMCP.

Tracks session-wide settings, API discovery/validation, and operation history
with undo/redo stack support (Feature 3).
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any

# Setup logging
logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for operation detail extraction (5-10x faster than re-compiling)
_STATUS_PATTERN = re.compile(r"\[(OK|WARN|ERROR|INFO)\]\s+(.+)", re.MULTILINE)
_NAME_PATTERN = re.compile(r"'([^']+)'")
_HVO_PATTERN = re.compile(r"hvo=(\d+)")


@dataclass
class OperationRecord:
    """Records details of a single operation for history and undo."""
    timestamp: datetime
    tool: str                    # tool name, currently always 'run_module'
    args_summary: str           # Human-readable summary of tool arguments
    script_code: str            # Full script code that was executed
    script_output: str          # Captured stdout/stderr from execution
    success: bool               # Whether operation succeeded
    undoable: bool              # Can be undone via FLEx ActionHandler
    project: str = ""           # Project name at execution time
    extracted_details: Dict[str, Any] = field(default_factory=dict)  # Parsed from output


@dataclass
class SessionState:
    """Tracks session-wide settings to ensure consistency across tool calls.

    Set by the 'start' tool and respected by all other tools unless overridden.
    Also tracks operation history and undo/redo stacks (Feature 3).
    """
    session_id: str = ""                   # Session ID (timestamp format: YYYYMMDD-HHMMSS)
    api_mode: str = "flexlibs2"            # API mode: flexlibs2, flexlibs_stable, liblcm
    output_type: str = "auto"              # Output type: auto, operation, module
    project_name: str = ""                 # FLEx project name (empty = prompt user)
    write_enabled: bool = False            # Write access: False = read-only/dry-run
    undoable: bool = False                 # #14: open project with undoable=True (LCM persistent undo)
    initialized: bool = False
    discovered_apis: set = field(default_factory=set)        # APIs discovered via search_by_capability
    validated_apis: set = field(default_factory=set)         # APIs validated via get_object_api
    api_versions: dict = field(default_factory=dict)         # Track active API versions: {api_name: version}

    # Feature 3: Session History and Undo/Redo
    operations_history: List[OperationRecord] = field(default_factory=list)  # Full audit trail
    undo_stack: List[OperationRecord] = field(default_factory=list)          # Undoable operations
    redo_stack: List[OperationRecord] = field(default_factory=list)          # Popped undo entries

    # #14 Phase 2: LCM UndoStack checkpoint IDs recorded after each run_module.
    # Local tracking; actual Undo execution happens in subprocess.
    # Entries: {"op_id": str, "undo_text": str, "timestamp": str}
    undo_checkpoints: List[Dict[str, Any]] = field(default_factory=list)

    def configure(self, **kwargs) -> None:
        """Configure session settings (called by start tool)."""
        if "api_mode" in kwargs:
            self.api_mode = kwargs["api_mode"]
        if "output_type" in kwargs:
            self.output_type = kwargs["output_type"]
        if "project_name" in kwargs:
            self.project_name = kwargs["project_name"]
        if "write_enabled" in kwargs:
            self.write_enabled = kwargs["write_enabled"]
        if "undoable" in kwargs:
            self.undoable = kwargs["undoable"]
        if "api_versions" in kwargs:
            self.api_versions = kwargs["api_versions"]
        self.initialized = True
        mode_info = f"mode={self.api_mode}, output={self.output_type}"
        mode_info += f", project={self.project_name or '(prompt)'}"
        mode_info += f", write={self.write_enabled}, undoable={self.undoable}"
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
        """Clear discovered APIs (for new session)."""
        self.discovered_apis = set()
        self.validated_apis = set()

    def record_validated_api(self, entity: str) -> None:
        """Record an API that was validated via get_object_api."""
        self.validated_apis.add(entity)

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

    def summary(self) -> dict:
        """Return session state summary for tool responses."""
        result = {
            "api_mode": self.api_mode,
            "output_type": self.output_type,
            "project_name": self.project_name or "(not set)",
            "write_enabled": self.write_enabled,
            "undoable": self.undoable,
            "initialized": self.initialized,
            "discovered_api_count": len(self.discovered_apis)
        }
        return result

    # ===== Feature 3: Session History and Undo/Redo =====

    def record_operation(
        self,
        tool: str,
        args_summary: str,
        script_code: str,
        script_output: str,
        success: bool,
        undoable: bool = False,
        project: str = ""
    ) -> None:
        """Record an operation in the session history and undo stack.

        Called after successful execution of run_module.

        Args:
            tool: Tool name (currently always 'run_module')
            args_summary: Human-readable summary of arguments
            script_code: Full script code that was executed
            script_output: Captured stdout from execution
            success: Whether operation succeeded
            undoable: Whether operation can be undone (detected from script_output)
            project: Project name at execution time
        """
        record = OperationRecord(
            timestamp=datetime.now(),
            tool=tool,
            args_summary=args_summary,
            script_code=script_code,
            script_output=script_output,
            success=success,
            undoable=undoable,
            project=project or self.project_name
        )

        # Extract operation details from output (e.g., "[OK] Created entry 'water' (hvo=12345)")
        record.extracted_details = self._extract_operation_details(script_output)

        # Add to history
        self.operations_history.append(record)

        # Add to undo stack if undoable
        if undoable and success:
            self.undo_stack.append(record)
            # Clear redo stack when new operation is performed
            self.redo_stack.clear()

        logger.info(
            f"Recorded operation: {tool} (success={success}, undoable={undoable})"
        )

    def can_undo(self) -> bool:
        """Check if an undo operation is available."""
        return len(self.undo_stack) > 0

    def can_redo(self) -> bool:
        """Check if a redo operation is available."""
        return len(self.redo_stack) > 0

    def pop_undo(self) -> Optional[OperationRecord]:
        """Pop the most recent undoable operation from the undo stack.

        Pushes it onto the redo stack for potential redo.

        Returns:
            The operation record that was popped, or None if no undo available.
        """
        if not self.can_undo():
            return None

        record = self.undo_stack.pop()
        self.redo_stack.append(record)
        logger.info(f"Popped undo: {record.tool} at {record.timestamp}")
        return record

    def pop_redo(self) -> Optional[OperationRecord]:
        """Pop the most recent redo operation from the redo stack.

        Pushes it back onto the undo stack.

        Returns:
            The operation record that was popped, or None if no redo available.
        """
        if not self.can_redo():
            return None

        record = self.redo_stack.pop()
        self.undo_stack.append(record)
        logger.info(f"Popped redo: {record.tool} at {record.timestamp}")
        return record

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
            Dictionary with history stats and availability of undo/redo.
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
            "undoable_count": len(self.undo_stack),
            "can_undo": self.can_undo(),
            "can_redo": self.can_redo(),
            "undo_stack_depth": len(self.undo_stack),
            "redo_stack_depth": len(self.redo_stack),
        }

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
                "undoable": op.undoable,
                "project": op.project,
                "extracted_details": op.extracted_details,
            }
            for op in self.operations_history
        ]
