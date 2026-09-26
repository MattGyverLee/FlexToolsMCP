#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The write ladder's shared rungs (parser-check CP4, FR-002, R-07).

EXTRACTED FROM `handle_run_module`, NOT COPIED. Until CP4 the confirmation,
access-gate and backup rungs lived inline in `handlers/execution.py`, which
was fine while `run_module` was the only thing that wrote. Filing
(`flextools_parse_text(apply=true)`) must walk the same rungs, and FR-002 --
with constitution Principle VI -- forbids a parallel copy of a safety path. So
the rungs live here and both handlers call them:

  * `probe_write_access(project)` -- the access probe and the decision it
    implies: the `project_locked` refusal for `open_exclusive` /
    `held_by_other`, or the advisory for `open_shared` / `stale_lock`;
  * `backup_intent(project, ...)` -- the backup's outcome, PREDICTED, never
    performed. `run_module` states it in its confirmation preview; filing
    states it in its mutation plan so a human confirms knowing whether a
    recovery point will exist (FR-007);
  * `take_backup(project, ...)` -- the best-effort pre-write backup itself.
    It never raises and never refuses (constitution Principle I).

WHAT STAYS WITH EACH CALLER, on purpose:

  * The rung ORDER. `run_module` confirms, then gates on access, then backs
    up; filing does the same (contracts/tools.md section 1). The order is
    the caller's control flow, and it is tested there.
  * The serialisation rung, `get_project_write_lock`. It is an in-process
    asyncio lock; holding it for an hours-long filing job would block every
    `run_module` write on that project for hours, and filing does not need
    it because its writes run in their own worker process (R-07, R-09).
  * Logging and message wording, which name what the caller is doing.

TEST SEAMS PRESERVED. `run_module`'s standing tests patch
`project_access.probe_project_access`, `project_discovery.find_lock_file`
and `execution.perform_pre_write_backup`, and reassign `execution.session_state`.
So every leaf here is looked up at CALL time (module attributes, not names
bound at import), and the backup function, the session state and the config
reader are passed in by the caller rather than imported here. The extraction
is proven by those tests passing with no modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from . import project_access as _project_access
from . import project_discovery as _project_discovery

try:
    from ..config import (
        BACKUP_BEFORE_WRITE_KEY,
        BACKUP_BEFORE_WRITE_DEFAULT,
        config_get as _default_config_get,
    )
except (ImportError, ValueError):
    from config import (  # type: ignore[no-redef]
        BACKUP_BEFORE_WRITE_KEY,
        BACKUP_BEFORE_WRITE_DEFAULT,
        config_get as _default_config_get,
    )

__all__ = [
    "PEER_BACKUP_CAVEAT",
    "RUN_MODULE_BACKUP_KEY",
    "FILING_BACKUP_KEY",
    "AccessDecision",
    "BackupIntent",
    "probe_write_access",
    "backup_intent",
    "take_backup",
]

#: Issue #93 CP4 (T4.2): backup honesty. With FieldWorks attached as a live
#: peer, the .fwdata on disk lags FLEx's unsaved in-memory state, so a file
#: copy is a floor -- the oldest state we could restore to -- not a snapshot
#: of what you see in the UI right now.
PEER_BACKUP_CAVEAT = (
    " NOTE: FieldWorks currently has this project open, so the .fwdata on "
    "disk lags FLEx's unsaved in-memory state. This copy is a floor to fall "
    "back to, not a snapshot of what the FLEx UI is showing."
)

#: The session keys a backup is recorded under. SEPARATE, so a backup taken
#: by `run_module` earlier in the session never satisfies filing (FR-008).
RUN_MODULE_BACKUP_KEY = "backed_up_projects"
FILING_BACKUP_KEY = "filing_backed_up_projects"

#: The verdicts a write cannot survive. Everything else proceeds (#93 CP4).
REFUSING_VERDICTS = ("open_exclusive", "held_by_other")


# ---------------------------------------------------------------------------
# Rung: the access probe and what it decides
# ---------------------------------------------------------------------------


@dataclass
class AccessDecision:
    """One access probe, and the write decision it implies.

    `refusal` is set only for the two verdicts a write cannot survive, and
    carries `project_locked`'s detail fields in `run_module`'s order; the
    caller writes the message. `advisory` is `run_module`'s `shared_mode`
    block for `open_shared` / `stale_lock`. `access` is the raw
    `ProjectAccess` (None when the caller did not probe).
    """

    project_name: str
    access: Any
    verdict: Optional[str]
    refusal: Optional[Dict[str, Any]] = None
    advisory: Optional[Dict[str, Any]] = None

    @property
    def live_peer(self) -> bool:
        """FieldWorks holds the project with sharing on: we write as a peer."""
        return self.verdict == "open_shared"


def _holder_fields(access: Any) -> Dict[str, Any]:
    holder = getattr(access, "holder", None)
    return {
        "holder_pid": holder.pid if holder else None,
        "holder_process": holder.process_name if holder else None,
    }


def probe_write_access(project_name: str) -> AccessDecision:
    """Probe the project's access state and decide the write gate.

    The probe is pure filesystem -- the `.fwdata.lock` JSON plus the
    project's sharing setting -- and never opens a project, so it is safe to
    run before confirmation (#93 CP4 T4.1).

      free           -> proceed
      open_shared    -> proceed, with the shared-mode advisory
      stale_lock     -> proceed; LCM treats a stale lock as acquirable
      open_exclusive -> refuse (`project_locked`)
      held_by_other  -> refuse (`project_locked`)
      unknown        -> proceed for `run_module` (#118); filing refuses it
                        itself with `project_drive_unavailable` (a disclosed
                        divergence, contracts/tools.md row 11)
    """
    access = _project_access.probe_project_access(project_name)
    verdict = getattr(access, "verdict", None)
    decision = AccessDecision(project_name=project_name, access=access, verdict=verdict)

    if verdict in REFUSING_VERDICTS:
        lock_path = _project_discovery.find_lock_file(project_name)
        remedy = _project_access.build_access_remedy(access)
        holder = _holder_fields(access)
        decision.refusal = {
            "guidance": (
                remedy
                or "Close FieldWorks, then retry. Read-only operations "
                   "do not require closing FieldWorks."
            ),
            "lock_file_path": str(lock_path) if lock_path else None,
            "verdict": verdict,
            "sharing_enabled": access.sharing_enabled,
            "holder_pid": holder["holder_pid"],
            "holder_process": holder["holder_process"],
            "remedy": remedy,
        }
    elif verdict == "open_shared":
        decision.advisory = {
            "verdict": "open_shared",
            "sharing_enabled": True,
            **_holder_fields(access),
            "note": (
                "FieldWorks has this project open with sharing enabled, "
                "so this run attached as a non-master LCM peer and wrote "
                "through the shared commit log. The change should be "
                "visible in the FLEx UI. Custom-field and writing-system "
                "changes are NOT safe from a peer and are not covered by "
                "this path."
            ),
        }
    elif verdict == "stale_lock":
        decision.advisory = {
            "verdict": "stale_lock",
            "sharing_enabled": access.sharing_enabled,
            **_holder_fields(access),
            "note": (
                "A .fwdata.lock file is present but the process that "
                "claimed it is no longer running, so the lock is stale. "
                "Proceeding: LCM treats a stale lock as acquirable. This "
                "server never deletes lock files."
            ),
        }
    return decision


# ---------------------------------------------------------------------------
# Rung: the pre-write backup -- predicted, then taken
# ---------------------------------------------------------------------------


@dataclass
class BackupIntent:
    """The backup's outcome, predicted before anything is written.

    `outcome` is one of `will_be_taken`, `not_expected` or
    `disabled_by_configuration` (data-model section 5). `reason` says why it
    is not `will_be_taken`.
    """

    outcome: str
    reason: Optional[str] = None
    peer_caveat: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def would_run(self) -> bool:
        return self.outcome == "will_be_taken"


def _was_backed_up(session_state: Any, project_name: str, session_key: str) -> bool:
    if session_key == RUN_MODULE_BACKUP_KEY:
        return bool(session_state.was_backed_up(project_name))
    return project_name in (getattr(session_state, session_key, None) or set())


def _record_backup(session_state: Any, project_name: str, session_key: str) -> None:
    if session_key == RUN_MODULE_BACKUP_KEY:
        session_state.record_backup(project_name)
        return
    recorded = getattr(session_state, session_key, None)
    if recorded is None:
        recorded = set()
        setattr(session_state, session_key, recorded)
    recorded.add(project_name)


def backup_intent(
    project_name: str,
    *,
    session_state: Any,
    backup_before_write: Optional[bool] = None,
    config_get: Optional[Callable[..., Any]] = None,
    session_key: str = RUN_MODULE_BACKUP_KEY,
    once_per_session: bool = True,
    predict_skips: bool = False,
    live_peer: bool = False,
) -> BackupIntent:
    """Predict the backup rung's outcome. Performs nothing.

    `run_module`'s semantics are the defaults, unchanged: the per-call
    `backup_before_write` wins over the config kill switch, and a project
    already backed up this session under `session_key` gets no new backup.

    `predict_skips=True` additionally asks the two filesystem questions the
    backup itself asks (is there a .fwdata; is there room) through
    `backup.predict_backup_skip`, so a plan's "not expected, because the disk
    is too full" is the same test the backup will apply (FR-007).
    """
    reader = config_get or _default_config_get
    enabled = (
        backup_before_write
        if backup_before_write is not None
        else bool(reader(BACKUP_BEFORE_WRITE_KEY, BACKUP_BEFORE_WRITE_DEFAULT))
    )
    caveat = PEER_BACKUP_CAVEAT.strip() if live_peer else None
    if not enabled:
        return BackupIntent(outcome="disabled_by_configuration", reason="backup_before_write=false")
    if once_per_session and _was_backed_up(session_state, project_name, session_key):
        return BackupIntent(outcome="not_expected", reason="already_backed_up_this_session")
    if predict_skips:
        from .backup import predict_backup_skip

        skip = predict_backup_skip(project_name)
        if skip is not None:
            return BackupIntent(outcome="not_expected", reason=skip)
    return BackupIntent(outcome="will_be_taken", peer_caveat=caveat)


def take_backup(
    project_name: str,
    *,
    session_state: Any,
    backup_before_write: Optional[bool] = None,
    live_peer: bool = False,
    perform: Optional[Callable[..., Dict[str, Any]]] = None,
    session_key: str = RUN_MODULE_BACKUP_KEY,
    once_per_session: bool = True,
) -> Optional[Dict[str, Any]]:
    """Take the best-effort pre-write backup. Never raises, never refuses.

    Returns `perform_pre_write_backup`'s result dict, or None when no backup
    was attempted because one was already taken this session under
    `session_key` (`run_module`'s once-per-(session, project) rule; filing
    passes `once_per_session=False` and backs up before every run).

    `perform` is the backup function to call. `run_module` passes its own
    module-level `perform_pre_write_backup` so the name its tests patch is
    the one that runs.
    """
    if once_per_session and _was_backed_up(session_state, project_name, session_key):
        return None
    if perform is None:
        from .backup import perform_pre_write_backup as perform
    try:
        result = perform(project_name, backup_before_write=backup_before_write)
    except Exception as exc:  # noqa: BLE001 -- best-effort; must never raise
        result = {"path": None, "created": False, "skipped_reason": f"backup_failed: {exc}"}
    if result.get("created"):
        if live_peer:
            result["note"] = PEER_BACKUP_CAVEAT.strip()
        _record_backup(session_state, project_name, session_key)
    return result
