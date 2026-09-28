#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 7 US5 (FR-032): extract_patterns points at the local-recipe
store instead of the skeleton closet, and carries params into the index.
"""

import importlib


def _import_extract():
    try:
        return importlib.import_module("flextoolsmcp.extract_patterns")
    except ImportError:
        return importlib.import_module("extract_patterns")


def test_mined_notes_point_at_local_recipes(tmp_path):
    mod = _import_extract()

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    import json

    op_id = "op-mine-notes-001"
    ops_line = {
        "op_id": op_id,
        "outcome": "ok",
        "user_intent": "List entries with glosses",
        "code_sha256": "abc123",
    }
    (log_dir / "operations.jsonl").write_text(
        json.dumps(ops_line) + "\n", encoding="utf-8"
    )
    mined = mod.mine_operations_log(log_dir)
    assert mined["candidate_count"] >= 1
    for cand in mined["candidates"].values():
        notes = (cand.get("notes") or "").lower()
        assert "skeleton closet" not in notes, (
            f"mined notes still say 'skeleton closet': {cand.get('notes')!r}"
        )
    blob = json.dumps(mined).lower()
    assert "local recipe" in blob or "local_recipe" in blob or "recipes.jsonl" in blob


def test_mine_help_points_at_local_recipes():
    # The module's main() wires --mine-operations-log; its help text must
    # not point at the skeleton closet.
    import subprocess
    import sys
    from pathlib import Path

    proc = subprocess.run(
        [sys.executable, "-m", "flextoolsmcp.extract_patterns",
         "--mine-operations-log", "--help"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
    )
    if proc.returncode == 0:
        assert "skeleton" not in proc.stdout.lower(), (
            f"--mine-operations-log help still mentions skeletons: {proc.stdout!r}"
        )


def test_index_recipes_carry_params():
    mod = _import_extract()
    from pathlib import Path

    from flextoolsmcp.file_utils import get_index_dir
    from flextoolsmcp.server.versioning import find_latest_versioned_api_file

    flexicon_path = find_latest_versioned_api_file(
        get_index_dir() / "python", "flexicon_api"
    )
    assert flexicon_path is not None
    result = mod.extract_patterns(Path(str(flexicon_path)))
    assert "recipes" in result
    assert result["recipes"], "index carries no recipes"
    for rid, recipe in result["recipes"].items():
        assert "params" in recipe, f"{rid} has no params in the index"
        assert isinstance(recipe["params"], list)
