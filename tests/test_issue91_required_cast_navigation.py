#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #91: required_cast downcast edges in the navigation graph."""

import json
from pathlib import Path

from server.handlers.discovery import find_path_bfs, generate_code_from_path


NAV_GRAPH_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "flextoolsmcp"
    / "index"
    / "navigation_graph_liblcm-v11.0.0.json"
)


def _load_graph():
    data = json.loads(NAV_GRAPH_PATH.read_text(encoding="utf-8"))
    return data["graph"]


class TestRequiredCastNavigationGraph:
    def test_shipped_graph_schema_and_downcast_edges(self):
        data = json.loads(NAV_GRAPH_PATH.read_text(encoding="utf-8"))
        assert data["_schema"] == "navigation-graph/1.1"
        msa_edges = data["graph"].get("IMoMorphSynAnalysis", [])
        assert (
            "IMoStemMsa",
            "cast_to_concrete",
            "required_cast",
        ) in [tuple(e) for e in msa_edges]

    def test_bfs_lexsense_to_symfeatval(self):
        graph = _load_graph()
        steps = find_path_bfs(graph, "ILexSense", "IFsSymFeatVal")
        assert steps, "expected a path after required_cast edges"
        assert any(s.get("type") == "required_cast" for s in steps)

    def test_generate_code_emits_cast_to_concrete(self):
        graph = _load_graph()
        steps = find_path_bfs(graph, "ILexSense", "IFsSymFeatVal")
        code = generate_code_from_path(steps)
        assert "cast_to_concrete" in code
