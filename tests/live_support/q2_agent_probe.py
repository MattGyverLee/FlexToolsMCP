#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Q2: is the HermitCrab parser agent present, and resolvable by GUID?
(parser-check CP4, T004; parent SPEC 12.7 / 17.10.)

READ ONLY. Opens a `CP4-Scratch-` copy with `writeEnabled=False` and reports:

  * the production probe's verdict (`preflight_reads.agent_facts`, i.e.
    `parser_probe.probe_hc_agent` on `LangProject.DefaultParserAgent`);
  * every agent the language project owns (`AnalyzingAgentsOC`), with GUID,
    name and whether it is human -- and whether the HermitCrab agent's GUID
    (`CmAgentTags.kguidAgentHermitCrabParser`, read from the installed
    assembly) is among them;
  * how many analysis evaluations that agent already holds, i.e. whether
    this project has ever been parsed with HermitCrab.

    python tests/live_support/q2_agent_probe.py CP4-Scratch-<...>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2] / "src"))
sys.path.insert(0, str(_HERE.parent))

from make_disposable import require_disposable  # noqa: E402


def _text(multi) -> str:
    try:
        return str(multi.BestAnalysisAlternative.Text)
    except Exception:  # noqa: BLE001
        return ""


def probe(project_name: str) -> dict:
    require_disposable(project_name)

    from flexicon import FLExCleanup, FLExInitialize, FLExProject

    from flextoolsmcp.server.filing.preflight_reads import agent_facts
    from flextoolsmcp.server.parse.worker_main import headless_ui_kwargs

    FLExInitialize()
    project = FLExProject()
    try:
        project.OpenProject(
            projectName=project_name, writeEnabled=False, undoable=False,
            **headless_ui_kwargs(FLExProject),
        )
        from SIL.LCModel import CmAgentTags  # type: ignore[import-not-found]

        hc_guid = str(CmAgentTags.kguidAgentHermitCrabParser).lower()
        lp = project.lp
        agents = []
        hc_agent = None
        for agent in list(lp.AnalyzingAgentsOC):
            guid = str(agent.Guid).lower()
            agents.append({"guid": guid, "name": _text(agent.Name), "human": bool(agent.Human)})
            if guid == hc_guid:
                hc_agent = agent
        evaluations = None
        if hc_agent is not None:
            try:
                evaluations = int(hc_agent.EvaluationsRC.Count)
            except Exception:  # noqa: BLE001 -- older models own them elsewhere
                evaluations = None
        try:
            active_parser = str(project.project.LanguageProject.MorphologicalDataOA.ActiveParser)
        except Exception:  # noqa: BLE001
            active_parser = None
        return {
            "project": project_name,
            "active_parser": active_parser,
            "hc_agent_guid": hc_guid,
            "hc_agent_in_repository": hc_agent is not None,
            "hc_agent_evaluation_count": evaluations,
            "probe": agent_facts(project, active_parser),
            "agents": agents,
        }
    finally:
        try:
            project.CloseProject()
        finally:
            FLExCleanup()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: q2_agent_probe.py <CP4-Scratch-project>", file=sys.stderr)
        return 2
    print(json.dumps(probe(argv[0]), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
