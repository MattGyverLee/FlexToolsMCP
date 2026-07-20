#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tier-2 eval harness SKELETON (issue #51).

Tier 2 drives ~15 task prompts (tests/evals/tasks/*.yaml -- intent only, no
code) against a REAL assistant session connected to a running FlexToolsMCP
server, against a real (test/sample) FieldWorks project, and records
turns-to-green per task in the same JSONL schema as production telemetry
(see `flextoolsmcp.server.handlers.op_telemetry`) so existing report tooling
(`scripts/green_report.py`-style aggregation) can render the results.

THIS MODULE IS A SKELETON, NOT A WORKING RUNNER. It documents the contract
(what "driving a session" means, what gets recorded, what "success" means)
so a human -- or a future automation pass -- can fill in the actual LLM/agent
driving loop. No live LLM call is wired here on purpose:

- Cost control: Tier 2 is manual, pre-release, and NEVER CI-required
  (opt-in via `FLEXTOOLSMCP_LIVE_EVALS=1`). Wiring a real LLM call into this
  file would risk it accidentally running in CI or burning API budget on
  every local `pytest` invocation.
- Tier 2 requires a real FieldWorks project + a real running MCP server;
  neither is available in a bare CI checkout (mirrors the `requires_flex`
  marker used elsewhere in this repo for the same reason).

See RELEASING.md's "Eval harness" section for the pre-release checklist step
this skeleton backs.

--------------------------------------------------------------------------
Contract a real Tier-2 driver must satisfy
--------------------------------------------------------------------------

1. Load each `tests/evals/tasks/*.yaml` entry:
     task: <human-language intent, no code>
     project: <FieldWorks project name the task should run against>
     max_turns: <int -- give up and record "not green" after this many turns>
     success_check: <human-readable description of what "green" means for
                      this task -- a real driver evaluates this against the
                      session transcript / tool outputs, e.g. via an LLM
                      grader or a hand-written checker>

2. For each task, drive an assistant session (Claude Agent SDK, or any
   agent loop) connected to the FlexToolsMCP server with the task's `project`
   already configured, and the task's `task` string as the user's opening
   message. Let the assistant call MCP tools (get_object_api,
   search_by_capability, run_module, ...) turn by turn.

3. After each assistant turn that calls `run_module`, inspect the tool
   response's `status` field:
     - "ok" (and not a graceful discovery_redirect, see
       docs/TOOL-CONTRACT.md's "Graceful discovery redirect" section) that
       satisfies `success_check` -> the task is GREEN. Stop driving; record
       turns_to_green = the 1-based turn number of this call.
     - "error" -> keep driving (up to max_turns) unless the assistant gives
       up / repeats the same failure (loop detection is a driver
       responsibility, not modeled here).
     - Reaching max_turns without a green close -> record NOT green.

4. Emit exactly one JSONL record per task, using the SAME field names as
   `op_telemetry._write_jsonl_line()` writes for a real op, so
   green_report.py-style tooling doesn't need a second schema:

     {
       "ts": "...",                    # ISO8601 UTC
       "task_id": "<corpus file stem>",
       "task": "<the task prompt>",
       "project": "<FieldWorks project name>",
       "outcome": "ok" | "not_green",  # green vs gave-up-after-max-turns
       "turns_to_green": <int or null>,
       "max_turns": <int>,
       "error_code": "<last error_code seen, if not_green>",
       "notes": "<free-text -- what actually happened, for a human reviewer>",
     }

   (Tier 2 records intentionally add `task_id` / `task` / `turns_to_green`
   / `max_turns` on top of the Tier-1/production JSONL fields -- these are
   Tier-2-specific and absent from real op_telemetry records; a
   green_report.py-style reader should treat unknown keys as informational,
   same forward-compat posture as the rest of this codebase's response
   envelopes.)

5. Aggregate across all tasks: N/15 green, median turns-to-green (over
   green tasks), and paste those headline numbers into CHANGELOG.md per the
   RELEASING.md pre-release checklist -- e.g. "eval: 13/15 tasks green,
   median 1 turn, was 11/15".

--------------------------------------------------------------------------
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

TASKS_DIR = Path(__file__).parent / "tasks"

# The env var that gates Tier 2 from ever running unintentionally (issue #51
# acceptance criterion: "opt-in via FLEXTOOLSMCP_LIVE_EVALS=1").
LIVE_EVALS_ENV_VAR = "FLEXTOOLSMCP_LIVE_EVALS"


@dataclass
class Tier2TaskResult:
    """One row of the Tier-2 output JSONL. See module docstring, step 4."""

    ts: str
    task_id: str
    task: str
    project: str
    outcome: str  # "ok" | "not_green"
    turns_to_green: Optional[int]
    max_turns: int
    error_code: Optional[str] = None
    notes: str = ""


def load_tasks() -> List[Dict[str, Any]]:
    """Load every tests/evals/tasks/*.yaml entry.

    Returns a list of dicts with keys: task, project, max_turns,
    success_check, plus `_task_id` (the file stem, for JSONL records).
    """
    import yaml

    tasks = []
    for path in sorted(TASKS_DIR.glob("*.yaml")):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data["_task_id"] = path.stem
        tasks.append(data)
    return tasks


def live_evals_enabled() -> bool:
    """True only when the operator has explicitly opted in.

    Tier 2 must NEVER run just because pytest happened to collect this
    module -- there is deliberately no test_*.py wrapper around this
    skeleton for that reason (see module docstring). This helper exists so
    a future real driver (or a manual CLI invocation) has one canonical
    place to check the opt-in flag.
    """
    return os.environ.get(LIVE_EVALS_ENV_VAR) == "1"


def run_task_skeleton(task_entry: Dict[str, Any]) -> Tier2TaskResult:
    """Placeholder for "drive one task against a real assistant session".

    NOT IMPLEMENTED: raises NotImplementedError unconditionally. A real
    driver replaces this function's body with the Claude Agent SDK (or
    equivalent) session loop described in the module docstring, steps 2-3.
    """
    raise NotImplementedError(
        "tier2_runner_skeleton.run_task_skeleton is a documented contract, "
        "not a working implementation -- see this module's docstring for "
        "what a real driver must do (drive an assistant session against a "
        "live FlexToolsMCP server + a real FieldWorks project, evaluate "
        "success_check, and return a Tier2TaskResult)."
    )


def write_jsonl(results: List[Tier2TaskResult], out_path: Path) -> None:
    """Append Tier-2 results as JSONL, one record per task (step 4)."""
    with open(out_path, "a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def summarize(results: List[Tier2TaskResult]) -> str:
    """Headline numbers for CHANGELOG.md (step 5), e.g.:

    'eval: 13/15 tasks green, median 1 turn, was 11/15'
    (the '(was N/M)' comparison against the prior run is left to the human
    pasting this into CHANGELOG.md -- this function only computes the
    current run's numbers.)
    """
    total = len(results)
    green = [r for r in results if r.outcome == "ok" and r.turns_to_green is not None]
    if not green:
        return f"eval: 0/{total} tasks green"
    turns = sorted(r.turns_to_green for r in green)
    median = turns[len(turns) // 2] if len(turns) % 2 else (
        turns[len(turns) // 2 - 1] + turns[len(turns) // 2]
    ) / 2
    return f"eval: {len(green)}/{total} tasks green, median {median} turn(s)"


def main() -> int:
    if not live_evals_enabled():
        print(
            f"Tier 2 is opt-in. Set {LIVE_EVALS_ENV_VAR}=1 to acknowledge you "
            "intend to run live LLM evals against a real FieldWorks project. "
            "This skeleton has no LLM wired in yet -- see the module "
            "docstring for the contract a real driver must implement.",
            file=sys.stderr,
        )
        return 1

    tasks = load_tasks()
    print(f"Loaded {len(tasks)} Tier-2 tasks from {TASKS_DIR}.", file=sys.stderr)
    print(
        "run_task_skeleton() is unimplemented -- see tier2_runner_skeleton.py's "
        "module docstring for the contract to fill in.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
