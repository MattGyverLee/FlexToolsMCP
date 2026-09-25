#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #245: non-exported flexicon classes must not advertise broken top-level imports."""

import importlib.util
import json
import unittest
from pathlib import Path

from flextoolsmcp.flexicon_analyzer import extract_flexicon_top_level_exports_from_init


def _shipped_flexicon_index_path() -> Path | None:
    python_dir = (
        Path(__file__).parent.parent / "src" / "flextoolsmcp" / "index" / "python"
    )
    if not python_dir.is_dir():
        return None
    candidates = sorted(python_dir.glob("flexicon_api_v*.json"))
    return candidates[-1] if candidates else None


class TestExtractFlexiconTopLevelExports(unittest.TestCase):
    def test_parses_installed_flexicon_init_without_importing(self):
        spec = importlib.util.find_spec("flexicon")
        if not spec or not spec.origin:
            self.skipTest("flexicon package not installed")
        exports = extract_flexicon_top_level_exports_from_init(Path(spec.origin))
        self.assertIn("LexEntryOperations", exports)
        self.assertNotIn("MSACollection", exports)
        self.assertNotIn("BaseOperations", exports)


class TestBuildEntityImportNonExports(unittest.TestCase):
    def setUp(self):
        from flextoolsmcp.server.handlers import api as api_mod

        self.api = api_mod
        self.api._flexicon_top_level_exports.cache_clear()

    def test_msa_collection_uses_deep_module_import(self):
        idx_path = _shipped_flexicon_index_path()
        if idx_path is None:
            self.skipTest("shipped flexicon index missing")
        with open(idx_path, encoding="utf-8") as f:
            entity = json.load(f)["entities"]["MSACollection"]
        line = self.api._build_entity_import(
            "flexicon", "MSACollection", entity.get("namespace", ""), entity,
        )
        self.assertEqual(
            line,
            "from flexicon.code.Lexicon.msa_collection import MSACollection",
        )
        self.assertNotEqual(line, "from flexicon import MSACollection")

    def test_base_operations_uses_deep_module_import(self):
        idx_path = _shipped_flexicon_index_path()
        if idx_path is None:
            self.skipTest("shipped flexicon index missing")
        with open(idx_path, encoding="utf-8") as f:
            entity = json.load(f)["entities"]["BaseOperations"]
        line = self.api._build_entity_import(
            "flexicon", "BaseOperations", entity.get("namespace", ""), entity,
        )
        self.assertEqual(
            line,
            "from flexicon.code.BaseOperations import BaseOperations",
        )

    def test_top_level_export_still_top_level_when_no_facade_path(self):
        entity = {
            "namespace": "flexicon.code.Lexicon.LexEntryOperations",
            "top_level_importable": True,
        }
        line = self.api._build_entity_import(
            "flexicon", "LexEntryOperations", entity["namespace"], entity,
        )
        self.assertEqual(line, "from flexicon import LexEntryOperations")


if __name__ == "__main__":
    unittest.main()
