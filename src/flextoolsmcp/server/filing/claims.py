#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The filing claim: one filing job per project, and nothing else blocked
(parser-check CP4, FR-026..FR-028, R-11).

A CLAIM, NOT A LOCK. Two filers writing the parser's opinions into one project
is the one genuinely incoherent case (US4), so a second filing request against
a project that already has a job running is refused -- with the running job's
`run_id`, `started_at`, `words_completed` and a hint pointing at
`flextools_parse_status`. It blocks no run-reading tool (FR-027), and on a
project with sharing ON no read-only parse or single-word try either. On a
project with sharing OFF, reads wait for the job (`reads_refused`), because
there the filing job is the project's only possible opener (L-0). It takes
none of the project-wide locks `tests/test_parse_no_edit_blocking.py` forbids
in the parse area. It is a dictionary in this process.

WHY IN MEMORY. A lock file on disk survives the crash of the process that took
it, which is exactly the wrong direction for FR-028 ("the refusal clears when
the job reaches any terminal state, including a crash of the process that ran
it"). An in-process registry cannot outlive the server: a worker crash ends
the run (the runner releases the claim in its terminal transition), and a
server crash takes the registry with it. What a server crash DOES leave is a
run record still saying `filing`; `sweep_orphaned_filing_runs` marks those
`crashed` at startup, beside the existing stale-lock sweep, and repeats the
backup pointer or the no-recovery warning so the record says how to recover.

CHECKED FIRST. The handler looks the claim up as its first statement after
resolving the project, before the engine check, the scope, the preview, the
backup or any parse -- which is what keeps the refusal under a second
(SC-006): nothing heavy runs first.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional

__all__ = [
    "READS_REFUSED_ON_NON_SHARED_DURING_FILING",
    "FilingClaim",
    "acquire",
    "rebind",
    "reads_refused",
    "release",
    "lookup",
    "clear",
    "active_projects",
    "in_progress_hint",
    "sweep_orphaned_filing_runs",
    "TERMINAL_FILING_STATES",
]

#: A filing run's `filing.state` values that mean the run is over (data-model
#: section 7). `filing` is the only live one.
TERMINAL_FILING_STATES = frozenset(
    {"completed", "cancelled", "refused_midrun", "crashed", "failed"}
)


#: FR-027 as amended after L-0 (2026-09-24; research R-10, M-1 settled).
#: On a project with sharing OFF the filing job is the project's only opener:
#: LCM's read-only open takes the project lock, and a second writable open
#: then fails with FP_FileLockedError (evidence/l0-coexistence.json). So a
#: filing job on such a project releases the shared read worker first, and
#: read requests for that project are refused with `parser_filing_in_progress`
#: while the job runs. Projects with sharing ON are not restricted: the two
#: opens coexist there (evidence/s4d-midrun-and-shared-read.json). Kept as a
#: named constant so the rule is greppable; it is not a tuning knob -- turning
#: it off would only turn the refusal into a failed open.
READS_REFUSED_ON_NON_SHARED_DURING_FILING = True


@dataclass
class FilingClaim:
    """Who is filing into a project right now."""

    project: str
    run_id: str
    started_at: str
    #: Read live from the run handle, so the refusal's `words_completed` is
    #: current rather than a number captured when the claim was taken.
    progress: Optional[Callable[[], int]] = None
    #: The project has sharing on (read off its setting, not the lock verdict).
    #: FR-027: reads are refused during the job only when this is False.
    shared: bool = False

    @property
    def words_completed(self) -> int:
        if self.progress is None:
            return 0
        try:
            return int(self.progress())
        except Exception:  # noqa: BLE001 -- a progress read never fails a refusal
            return 0


_claims: dict[str, FilingClaim] = {}
_mutex = threading.Lock()


def _key(project: str) -> str:
    # FieldWorks project names are directory names on a case-insensitive
    # filesystem: "Demo" and "demo" are one project.
    return (project or "").casefold()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def lookup(project: str) -> Optional[FilingClaim]:
    """The claim held on this project, or None."""
    with _mutex:
        return _claims.get(_key(project))


def acquire(
    project: str,
    run_id: str,
    *,
    started_at: Optional[str] = None,
    progress: Optional[Callable[[], int]] = None,
    shared: bool = False,
) -> Optional[FilingClaim]:
    """Take the claim. Returns None if another job already holds it.

    Check-and-set under one mutex, so two confirmed requests racing past the
    handler's first lookup cannot both start a job.
    """
    with _mutex:
        existing = _claims.get(_key(project))
        if existing is not None and existing.run_id != run_id:
            return None
        claim = FilingClaim(project=project, run_id=run_id,
                            started_at=started_at or _now_iso(), progress=progress,
                            shared=shared)
        _claims[_key(project)] = claim
        return claim


def rebind(project: str, token: str, run_id: str) -> bool:
    """Move a claim taken under a provisional token onto the run's real id.

    The handler takes the claim BEFORE the run exists (FR-003: every rung
    completes first, and the claim is the last), under a token; the run's
    observer rebinds it the moment the run's id is minted.
    """
    with _mutex:
        claim = _claims.get(_key(project))
        if claim is None or claim.run_id != token:
            return False
        claim.run_id = run_id
        return True


def reads_refused(project: str) -> Optional[FilingClaim]:
    """The claim a read-only request on `project` is refused for, or None.

    Only on a project with sharing off (FR-027 as amended after L-0).
    """
    if not READS_REFUSED_ON_NON_SHARED_DURING_FILING:
        return None
    claim = lookup(project)
    if claim is None or claim.shared:
        return None
    return claim


def attach_progress(project: str, run_id: str, progress: Callable[[], int]) -> None:
    """Point a held claim at its run's live progress counter."""
    with _mutex:
        claim = _claims.get(_key(project))
        if claim is not None and claim.run_id == run_id:
            claim.progress = progress


def release(project: str, run_id: Optional[str] = None) -> bool:
    """Drop the claim. With `run_id`, only if that run still holds it.

    The runner calls this in its terminal transition for every filing run --
    success, refusal, cancellation, worker crash -- in a `finally`.
    """
    with _mutex:
        existing = _claims.get(_key(project))
        if existing is None:
            return False
        if run_id is not None and existing.run_id != run_id:
            return False
        del _claims[_key(project)]
        return True


def clear() -> None:
    """Forget every claim. Tests only; a new server process starts empty."""
    with _mutex:
        _claims.clear()


def active_projects() -> List[str]:
    with _mutex:
        return [claim.project for claim in _claims.values()]


def in_progress_hint(claim: FilingClaim) -> str:
    """The refusal's `hint`: watch the running job, do not start another.

    Whether reads are blocked depends on the project: on a non-shared project
    the filing worker is its only opener (L-0), so reads wait for the run.
    Saying otherwise there was a false promise (found live, CP4 S6).
    """
    if claim.shared or not READS_REFUSED_ON_NON_SHARED_DURING_FILING:
        reads = "Read-only parses and single-word tries are not blocked by it."
    else:
        reads = ("This project is not shared, so read-only parses and single-word "
                 "tries wait for it too: the filing job is the project's only opener "
                 "until it ends.")
    return (
        f"A filing job ({claim.run_id}) has been running on this project since "
        f"{claim.started_at}. Watch it with "
        f"flextools_parse_status(run_id='{claim.run_id}') rather than starting "
        f"a second one; a new filing request is accepted as soon as it ends. "
        + reads
    )


# ---------------------------------------------------------------------------
# The server-crash case (FR-028): records left saying `filing`
# ---------------------------------------------------------------------------


def sweep_orphaned_filing_runs(record_dir: Optional[Path] = None) -> List[str]:
    """Mark filing runs a dead server left non-terminal as `crashed`.

    Called once at startup, beside `sweep_stale_locks()`. A run record whose
    `filing.state` is still `filing` belongs to a job no process is executing
    any more: the in-memory claim died with the server, and this makes the
    record agree. The words filed before the crash stay filed -- nothing here
    touches a project -- and the record is told so, with the backup pointer or
    the no-recovery warning repeated where a reader of the record will see it.

    Returns the swept run ids. Never raises: a sweep that failed must not stop
    the server from starting.
    """
    from ..parse.record import RunRecord, list_run_ids
    from ..parse.stages import RunStage, is_terminal

    swept: List[str] = []
    try:
        run_ids = list_run_ids(record_dir)
    except Exception:  # noqa: BLE001
        return swept
    for run_id in run_ids:
        try:
            record = RunRecord(run_id, record_dir=record_dir)
            meta = record.read_meta()
            filing = dict(meta.filing or {}) if meta is not None else {}
            if not filing or filing.get("state") in TERMINAL_FILING_STATES:
                continue
            filing["state"] = "crashed"
            recovery = (
                f"The backup taken before this run is at {filing['backup']['path']}."
                if (filing.get("backup") or {}).get("path")
                else (filing.get("no_recovery_warning") or "No backup was recorded for this run.")
            )
            filing["crash_note"] = (
                "The server process ended while this filing run was going. Words "
                "filed before that stay filed (see filed_words); filing cannot be "
                "undone. " + recovery
            )
            updates = {"filing": filing}
            stage = RunStage(meta.stage) if meta.stage in RunStage._value2member_map_ else None
            if stage is None or not is_terminal(stage):
                updates["failure"] = {
                    "message": filing["crash_note"],
                    "stage_at_failure": meta.stage,
                    "error_type": "ServerCrashed",
                    "next_step": None,
                    "error_code": None,
                    "detail": None,
                }
                record.set_stage(RunStage.FAILED, **updates)
            else:
                record.set_stage(stage, **updates)
            swept.append(run_id)
        except Exception:  # noqa: BLE001 -- one unreadable record never stops the sweep
            continue
    return swept
