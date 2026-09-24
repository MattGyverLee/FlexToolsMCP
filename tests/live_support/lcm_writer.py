#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run one LCM snippet against a `CP4-Scratch-` copy, in its own process
(parser-check CP4 live support: seeding and breaking scenario data).

The snippet runs with these names bound:

    project   the open FLExProject          cache   its LcmCache
    lp        the LanguageProject           out     a dict; returned as JSON
    service(Iface) -> the ServiceLocator's implementation of `Iface`
    clr, System, SIL (the SIL.LCModel namespace module)

With `write=True` the project is opened writable and the snippet runs inside
ONE `NonUndoableUnitOfWorkHelper.Do`, then the project is saved and closed.
Refuses any project not named `CP4-Scratch-...` (FR-037).

    from lcm_writer import run_lcm
    result = run_lcm("CP4-Scratch-...", SNIPPET, write=True)
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[2]
sys.path.insert(0, str(_HERE.parent))

from make_disposable import require_disposable  # noqa: E402

_RUNNER = r'''
import json, sys, traceback
sys.path.insert(0, sys.argv[3])
name, write = sys.argv[1], sys.argv[2] == "1"
snippet = sys.stdin.read()
from flexicon import FLExInitialize, FLExCleanup, FLExProject
from flextoolsmcp.server.filing.worker_filing import filing_ui_kwargs
FLExInitialize()
project = FLExProject()
out = {}
try:
    # Writable: flexicon's per-operation mode (undoable left at its default),
    # so no session-long task is open and the snippet's own unit of work is
    # the only one -- `undoable=False` would nest it ("Nested tasks").
    kwargs = {} if write else {"undoable": False}
    project.OpenProject(projectName=name, writeEnabled=write,
                        **kwargs, **filing_ui_kwargs(FLExProject))
    import clr, System
    import SIL.LCModel as SIL_LCModel
    cache = project.project
    lp = cache.LanguageProject
    def service(iface):
        return cache.ServiceLocator.GetService(clr.GetClrType(iface))
    env = dict(project=project, cache=cache, lp=lp, out=out, service=service,
               clr=clr, System=System, SIL=SIL_LCModel)
    if write:
        from SIL.LCModel.Infrastructure import NonUndoableUnitOfWorkHelper
        def _body():
            exec(snippet, env)
        NonUndoableUnitOfWorkHelper.Do(cache.ActionHandlerAccessor, System.Action(_body))
    else:
        exec(snippet, env)
except Exception as exc:
    out["error"] = f"{type(exc).__name__}: {exc}"
    out["traceback"] = traceback.format_exc()[-3000:]
    clr_stack = getattr(exc, "StackTrace", None)
    if clr_stack:
        out["clr_stack"] = str(clr_stack)[-2000:]
finally:
    try:
        project.CloseProject()
    except Exception as exc:
        out["close_error"] = f"{type(exc).__name__}: {exc}"
    FLExCleanup()
print("LCMOUT " + json.dumps(out, default=str))
'''


def run_lcm(project_name: str, snippet: str, *, write: bool = False, timeout: int = 900) -> dict:
    require_disposable(project_name)
    done = subprocess.run(
        [sys.executable, "-c", _RUNNER, project_name, "1" if write else "0", str(REPO / "src")],
        input=textwrap.dedent(snippet), capture_output=True, text=True, encoding="utf-8",
        timeout=timeout,
    )
    lines = [ln[7:] for ln in done.stdout.splitlines() if ln.startswith("LCMOUT ")]
    if not lines:
        return {"error": f"no result (rc={done.returncode})", "stderr": done.stderr[-3000:]}
    return json.loads(lines[-1])
