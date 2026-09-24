#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Session project adoption helpers (issues #168, #174)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def adopt_resolved_project(
    session_state: Any,
    resolved: str,
    *,
    log_context: str,
) -> str:
    """Unconditionally adopt a resolved project name into the session.

    When the session already had a different project, logs ``[PROJECT-ADOPTED]``
    (issue #169 guardrail) and queues a ``project_adopted_notice`` block for the
    next tool response envelope (issue #174). First adoption from an empty session
    emits neither.

    Returns the canonical ``resolved`` name (also written to ``project_name``).
    """
    prev = getattr(session_state, "project_name", "") or ""
    if prev and resolved != prev:
        try:
            from .server.kernel import get_operations_logger
        except (ImportError, ValueError):
            from server.kernel import get_operations_logger
        adopt_logger = get_operations_logger()
        if adopt_logger:
            adopt_logger.info(
                f"[PROJECT-ADOPTED] {log_context}: session project "
                f"changed '{prev}' -> '{resolved}'"
            )
        session_state.project_adopted_notice = {
            "previous_project": prev,
            "project": resolved,
            "message": (
                f"Session project is now '{resolved}' (was '{prev}'). "
                f"Unqualified calls target '{resolved}' until you change it again."
            ),
        }
    session_state.project_name = resolved
    return resolved


def consume_project_adopted_notice(session_state: Any) -> Optional[Dict[str, Any]]:
    """Return and clear a queued ``project_adopted_notice``, if any."""
    notice = getattr(session_state, "project_adopted_notice", None)
    if notice:
        session_state.project_adopted_notice = None
    return notice
