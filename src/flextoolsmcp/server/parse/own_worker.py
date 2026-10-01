#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"Is this our own worker?" -- shared by every write gate that probes project
access before writing (issue #223).

`write_ladder.probe_write_access` is pure filesystem: it answers
`held_by_other` for ANY Python process holding the project's fwdata lock,
including this server's own idle parse/measurement worker. Filing
(`handlers/parse/filing.py`, `_held_by_own_read_worker` before this module existed)
already told the two apart for its own writable open; `run_module`
(`handlers/execution.py`) did not, which is the bug #223 reports -- the
server's own idle worker was reported to the caller as a foreign process to
kill.

This module is the ONE place that answers "is the holder one of ours, and
which worker is it", so the two call sites (filing's preview gate and
`run_module`'s write gate) cannot drift apart on the answer, per issue #223's
explicit ask to share detection rather than duplicate it.

#223's follow-up made the worker release the project as soon as its queue
goes idle (`parse/worker_main.py`'s `ParseWorker._release_if_idle`), instead
of holding it for the rest of the idle timeout. #235 adds a `run_end`
wire message so a server-paced batch (one word at a time) does not look
idle between words. That shrank the window this
module exists to cover -- a foreign-looking `held_by_other` that is
actually us -- from up to 600s down to a live-parse collision or a ~50ms
race, but did not remove it; see `handlers/execution.py`'s
`_release_own_worker_or_refuse` docstring for the two remaining cases.
"""

from typing import Any, Callable, Dict, Optional, Tuple

#: The verdict filing's plan uses when the probed holder turns out to be our
#: own SHARED_ROLE read worker (contracts/tools.md row 8, FR-030). Kept here
#: as the canonical spelling; `handlers/parse/filing.py` re-exports it for callers
#: that already import it from there.
HELD_BY_OWN_READ_WORKER = "held_by_mcp_read_worker"


def busy_own_worker_run_note(run_ids: list) -> str:
    """` (run <id>)` for a refusal message, or `""` if no run id is known.

    Shared so the two busy-own-worker refusals (`handlers/execution.py`'s
    `_release_own_worker_or_refuse`, `handlers/parse/runs.py`'s
    `handle_flextools_parse_release`) format the run reference identically
    (#223 QC P2 -- the two messages had drifted into near-duplicates).
    """
    return f" (run {run_ids[0]})" if run_ids else ""


def busy_own_worker_guidance(next_action: str) -> str:
    """"Wait or cancel, then <next_action>." -- the remedy text every
    busy-own-worker refusal gives (#223 QC P2), parameterized only by what
    the caller should do once the run is out of the way (resubmit a write,
    retry `flextools_parse_release`, ...). Used for both `guidance` and
    `remedy` at each call site: the two fields have always carried the same
    text here, so there is nothing role-specific for them to diverge on.
    """
    return (
        "Wait for the run to finish (flextools_parse_status), or cancel "
        f"it with flextools_parse_cancel(run_id=...), then {next_action}."
    )


def own_worker_role(runner: Optional[Any], project_name: str, decision: Any) -> Optional[str]:
    """Which of this project's own workers (any role) holds the probed lock?

    `None` if the probe did not refuse (nothing to explain), there is no
    runner at all (so no worker of ours could exist), or the holder PID
    does not match any worker this server started for `project_name` --
    a genuine foreign holder.

    Checks every role the pool tracks (`SHARED_ROLE`, `MEASUREMENT_ROLE`),
    not just the shared read worker: the bounded measurement worker can
    also hold the lock briefly, and a caller that only checked
    `SHARED_ROLE` would misreport it as foreign too.
    """
    if runner is None or decision is None or decision.refusal is None:
        return None
    return own_holder_role(runner, project_name, getattr(decision, "access", None))


def own_holder_role(runner: Optional[Any], project_name: str, access: Any) -> Optional[str]:
    """`own_worker_role` for a bare `ProjectAccess` probe, with no write
    decision around it -- the post-hoc FP_FileLockedError diagnosis
    (`handlers/execution.py`'s `_diagnose_project_open_error`, issue #315)
    has only the probe."""
    if runner is None:
        return None
    holder_pid = getattr(getattr(access, "holder", None), "pid", None)
    if holder_pid is None:
        return None
    return runner.own_worker_role_for_pid(project_name, holder_pid)


# ---------------------------------------------------------------------------
# The shared "our worker holds it -- release, coexist, or refuse?" core
# ---------------------------------------------------------------------------

#: `settle_own_worker_hold` outcomes.
NOT_OURS = "not_ours"
BUSY = "busy"
COEXISTS = "coexists"
RELEASED = "released"


async def settle_own_worker_hold(
    runner: Optional[Any],
    project_name: str,
    decision: Any,
    reprobe: Callable[[str], Any],
) -> Tuple[str, Optional[str], Any]:
    """Decide what a refusing probe means when the holder may be ours.

    Issue #315: factored out of `handlers/execution.py`'s
    `_release_own_worker_or_refuse` so filing's confirmed gate
    (`handlers/parse/filing.py` row 11) answers the same way for EVERY
    role, not just `SHARED_ROLE` -- the foreign-holder refusal text now
    asserts the holder is not one of ours, which must be true wherever it
    is emitted.

    Returns `(outcome, role, decision)`:
      * NOT_OURS  -- no worker of ours holds it; `decision` unchanged.
      * BUSY      -- ours, running a parse; `decision` unchanged. Never
                     released (a live run is never torn down).
      * COEXISTS  -- ours, idle or not, on a SHARED project: a writable open
                     coexists with it (#223 second repro), so nothing is
                     released; the caller clears the refusal itself.
      * RELEASED  -- ours and idle: released atomically
                     (`release_worker_if_idle`, #223 QC P1) and re-probed
                     with `reprobe`; any holder left in the new `decision`
                     is genuine. If the re-probe raises, the decision as it
                     stood before is returned.

    `reprobe` is the caller's own `write_ladder.probe_write_access`, passed
    in so this module stays import-free and each caller's module binding
    (and its tests' monkeypatching) is used unchanged.
    """
    role = own_worker_role(runner, project_name, decision)
    if role is None:
        return NOT_OURS, None, decision
    if runner.worker_busy(project_name, role=role):
        return BUSY, role, decision
    if bool(decision.refusal.get("sharing_enabled")):
        return COEXISTS, role, decision
    if await runner.release_worker_if_idle(project_name, role=role):
        try:
            return RELEASED, role, reprobe(project_name)
        except Exception:
            return RELEASED, role, decision
    # Became busy between the check and the atomic release.
    return BUSY, role, decision


def busy_own_worker_next_steps(next_action: str) -> list:
    """Numbered `next_steps` for a busy-own-worker refusal (issue #315),
    formatted like the foreign-holder ones (`project_access.
    build_access_next_steps`)."""
    steps = [
        "Check the run with flextools_parse_status(run_id=...).",
        "Wait for it to finish, or cancel it with "
        "flextools_parse_cancel(run_id=...).",
        f"Then {next_action}.",
    ]
    return [f"{i}. {text}" for i, text in enumerate(steps, 1)]


def busy_own_worker_refusal(
    runner: Any, project_name: str, role: str, decision: Any, next_action: str,
    *, message_suffix: str = "",
) -> Tuple[str, Dict[str, Any]]:
    """`(message, detail_fields)` for a `project_locked` refusal because our
    own worker is busy -- shared by run_module's write gate and filing's
    confirmed gate (issue #315) so the two cannot drift. The caller passes
    both to `error_response("project_locked", message, **fields)`.
    """
    run_note = busy_own_worker_run_note(runner.active_run_ids(project_name, role=role))
    guidance = busy_own_worker_guidance(next_action)
    message = (
        f"Project '{project_name}' is held by this server's own parse "
        f"worker, which is busy running a parse{run_note}. This is NOT "
        f"a foreign process -- do not end it.{message_suffix} {guidance}"
    )
    fields = {
        "guidance": guidance,
        "remedy": guidance,
        "lock_file_path": decision.refusal.get("lock_file_path"),
        "verdict": decision.verdict,
        "sharing_enabled": decision.refusal.get("sharing_enabled"),
        "holder_pid": decision.refusal.get("holder_pid"),
        "holder_process": "this server's own parse worker",
        "next_steps": busy_own_worker_next_steps(next_action),
    }
    return message, fields


def own_worker_lock_diagnosis(
    runner: Any, project_name: str, role: str
) -> Dict[str, Any]:
    """Diagnosis fields for an FP_FileLockedError whose holder is our own
    worker (issue #315), the run-time sibling of the write gate's refusal.

    The write gate releases an idle worker itself (`settle_own_worker_hold`);
    this path is a read-only diagnosis of a run that already failed, so it
    releases nothing and points the model at `flextools_parse_release`
    instead. A busy worker gets the same wait-or-cancel text as
    `busy_own_worker_refusal`.
    """
    if runner.worker_busy(project_name, role=role):
        run_note = busy_own_worker_run_note(runner.active_run_ids(project_name, role=role))
        guidance = busy_own_worker_guidance("retry the run")
        message = (
            f"Project '{project_name}' is locked by this server's own parse "
            f"worker, which is busy running a parse{run_note}. This is NOT a "
            f"foreign process -- do not end it."
        )
        next_steps = busy_own_worker_next_steps("retry the run")
    else:
        guidance = (
            "Call flextools_parse_release(project_name=...) to release it, "
            "then retry the run."
        )
        message = (
            f"Project '{project_name}' is locked by this server's own idle "
            "parse worker. This is NOT a foreign process -- do not end it."
        )
        next_steps = [
            f"1. Call flextools_parse_release(project_name='{project_name}').",
            "2. Then retry the run.",
        ]
    return {
        "message": message,
        "hint": f"{message} {guidance}",
        "remedy": guidance,
        "holder_process": "this server's own parse worker",
        "next_steps": next_steps,
    }
