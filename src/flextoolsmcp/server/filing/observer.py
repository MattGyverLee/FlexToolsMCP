#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A filing run's bookkeeping (parser-check CP4, FR-028, FR-032..FR-034,
FR-041; data-model section 7).

THE RUNNER RUNS THE RUN; THIS KEEPS ITS RECORD. `ParseRunner` is the one run
mechanism (FR-026) and must not learn what filing means -- `server/parse/`
never imports the write spine. So a filing run carries an observer, and the
runner calls it at four points:

  * `initial_section()` -- the record's `filing` section as the run starts:
    the confirmed plan and its id, the backup outcome or the no-recovery
    warning, Send/Receive, the access verdict, zeroed counts, projected
    deletions, `state: "filing"`;
  * `on_result()` -- per word: the classifier's outcome folded into the
    counts, `filed_words` in filing order, actual deletions, in-use approvals
    recorded, human disapprovals overwritten;
  * `finish()` -- the terminal `state`, whether the filed words were
    persisted, and the fixed wording (FR-033, FR-034);
  * `on_terminal()` -- releases the project's claim, in the very transition
    that makes the run terminal (FR-028); `after_terminal()` then recycles the
    shared read worker, whose cache predates the filing (R-09).

NOTHING HERE LABELS AN ANALYSIS TACIT, UNREVIEWED OR AUTO-APPROVED (FR-033).
Approvals recorded on analyses in use in a text are counted under
`in_use_approvals_recorded` and worded as recorded-for-anything-in-use.
"""

from __future__ import annotations

import contextlib
from typing import Any, Dict, Optional

from . import claims, wording
from .classify import add_counts, empty_counts

__all__ = ["FilingObserver"]


class FilingObserver:
    """The observer one filing run is started with."""

    def __init__(
        self,
        *,
        project_name: str,
        plan: Dict[str, Any],
        plan_id: str,
        backup: Dict[str, Any],
        no_recovery_warning: Optional[str],
        send_receive: Any,
        access_verdict: Optional[str],
        recycle_read_worker: bool = True,
        claim_token: Optional[str] = None,
    ) -> None:
        #: The provisional id the handler took the claim under; rebound to the
        #: run's real id in `on_start`.
        self.claim_token = claim_token
        self.project_name = project_name
        self.plan = plan
        self.plan_id = plan_id
        self.backup = backup
        self.no_recovery_warning = no_recovery_warning
        self.send_receive = send_receive
        self.access_verdict = access_verdict
        self.recycle_read_worker = recycle_read_worker
        self._released = False

    # -- the four hooks ----------------------------------------------------

    def initial_section(self) -> Dict[str, Any]:
        projection = self.plan.get("deletion_projection") or {}
        return {
            "requested": True,
            "confirmed_plan": self.plan,
            "plan_id": self.plan_id,
            "backup": self.backup,
            "no_recovery_warning": self.no_recovery_warning,
            "send_receive": self.send_receive,
            "access_verdict": self.access_verdict,
            "state": "filing",
            "counts": empty_counts(),
            "projected_deletions": int(projection.get("upper_bound") or 0),
            "actual_deletions": 0,
            "in_use_approvals_recorded": 0,
            "in_use_approvals_note": wording.in_use_approvals_sentence(0),
            "disapprovals_overwritten": [],
            "filed_words": [],
            "persisted": None,
            "divergences": [wording.LOWERCASE_DIVERGENCE, wording.DECLINED_DIVERGENCE],
        }

    def on_start(self, handle: Any) -> None:
        """Rebind the claim to the run's id; point it at the live progress."""
        if self.claim_token:
            claims.rebind(self.project_name, self.claim_token, handle.run_id)
        claims.attach_progress(self.project_name, handle.run_id, lambda: handle.words_completed)

    def on_result(self, handle: Any, entry: Dict[str, Any]) -> None:
        section = handle.filing
        outcome = ((entry.get("parse") or {}).get("filing")) or {}
        if not outcome or section is None:
            return
        add_counts(section["counts"], outcome.get("counts") or {})
        if outcome.get("outcome") == "filed":
            section["filed_words"].append(entry.get("wordform"))
        section["actual_deletions"] += len(outcome.get("deleted") or [])
        recorded = int(outcome.get("in_use_approvals_recorded") or 0)
        section["in_use_approvals_recorded"] += recorded
        section["in_use_approvals_note"] = wording.in_use_approvals_sentence(
            section["in_use_approvals_recorded"]
        )
        for guid in outcome.get("overwritten") or []:
            section["disapprovals_overwritten"].append(
                {"wordform": entry.get("wordform"), "analysis_guid": guid,
                 "prior_user_opinion": "disapproves",
                 "capture": "filing/deletions.jsonl"}
            )

    def finish(self, handle: Any, *, state: str, persisted: bool,
               error: Optional[str] = None) -> None:
        section = handle.filing
        if section is None:
            return
        section["state"] = state
        section["persisted"] = bool(persisted)
        if error:
            section["persist_error"] = error
        if state == "cancelled":
            section["cancel_note"] = wording.CANCEL_NOTE
        if state in ("crashed", "failed", "refused_midrun"):
            recovery = (
                f"The backup taken before this run is at {self.backup.get('path')}."
                if (self.backup or {}).get("path")
                else (self.no_recovery_warning or "No backup was recorded for this run.")
            )
            section["stop_note"] = (
                f"This run stopped ({state}). Words listed in filed_words were filed "
                f"and, where persisted is true, saved; filing cannot be undone. "
                f"{recovery}"
            )

    def on_terminal(self, handle: Any) -> None:
        """Release the claim (idempotent). FR-028: on EVERY terminal state."""
        if self._released:
            return
        self._released = True
        claims.release(self.project_name, handle.run_id)

    async def after_terminal(self, handle: Any, runner: Any) -> None:
        """Recycle the shared read worker: its cache predates the filing (R-09).

        A worker something is running on is not killed -- a single word a
        user is waiting for is not lost to tidy a cache -- but it is marked
        stale, and the next filing preflight read recycles it first.
        """
        if not self.recycle_read_worker:
            return
        from ..parse.worker_client import SHARED_ROLE

        if runner.read_worker_busy(self.project_name):
            runner.mark_read_worker_stale(self.project_name)
            return
        with contextlib.suppress(Exception):
            await runner.release_worker(self.project_name, role=SHARED_ROLE)
