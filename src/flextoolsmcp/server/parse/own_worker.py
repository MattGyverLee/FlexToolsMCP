#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
"Is this our own worker?" -- shared by every write gate that probes project
access before writing (issue #223).

`write_ladder.probe_write_access` is pure filesystem: it answers
`held_by_other` for ANY Python process holding the project's fwdata lock,
including this server's own idle parse/measurement worker. Filing
(`handlers/parse.py`, `_held_by_own_read_worker` before this module existed)
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

from typing import Any, Optional

#: The verdict filing's plan uses when the probed holder turns out to be our
#: own SHARED_ROLE read worker (contracts/tools.md row 8, FR-030). Kept here
#: as the canonical spelling; `handlers/parse.py` re-exports it for callers
#: that already import it from there.
HELD_BY_OWN_READ_WORKER = "held_by_mcp_read_worker"


def busy_own_worker_run_note(run_ids: list) -> str:
    """` (run <id>)` for a refusal message, or `""` if no run id is known.

    Shared so the two busy-own-worker refusals (`handlers/execution.py`'s
    `_release_own_worker_or_refuse`, `handlers/parse.py`'s
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
    holder = getattr(getattr(decision, "access", None), "holder", None)
    holder_pid = getattr(holder, "pid", None)
    if holder_pid is None:
        return None
    return runner.own_worker_role_for_pid(project_name, holder_pid)
