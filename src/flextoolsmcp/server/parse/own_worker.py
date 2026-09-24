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
"""

from typing import Any, Optional

#: The verdict filing's plan uses when the probed holder turns out to be our
#: own SHARED_ROLE read worker (contracts/tools.md row 8, FR-030). Kept here
#: as the canonical spelling; `handlers/parse.py` re-exports it for callers
#: that already import it from there.
HELD_BY_OWN_READ_WORKER = "held_by_mcp_read_worker"


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
