#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for issue #256: FLExProject lp/lexDB instance attribute discovery."""

import json
import textwrap
import unittest
from pathlib import Path


class TestExtractInstanceAttributes(unittest.TestCase):
    def test_openproject_assignments(self):
        from flextoolsmcp.flexicon_analyzer import _extract_instance_attributes
        import ast

        source = textwrap.dedent(
            """
            class FLExProject:
                def OpenProject(self, projectName):
                    self.project = FLExLCM.OpenProject(projectName, ui, progress)
                    self.lp = self.project.LangProject
                    self.lexDB = self.lp.LexDbOA
                    self.writeEnabled = writeEnabled
            """
        )
        class_node = ast.parse(source).body[0]
        attrs = _extract_instance_attributes(class_node, "FLExProject")
        by_name = {row["name"]: row for row in attrs}
        self.assertIn("lp", by_name)
        self.assertIn("lexDB", by_name)
        self.assertEqual(by_name["lp"]["type"], "LangProject")
        self.assertEqual(by_name["lexDB"]["type"], "ILexDb")
        self.assertEqual(by_name["lp"]["kind"], "instance_attr")
        self.assertEqual(by_name["lp"]["access_path"], "project.lp")
        self.assertEqual(by_name["lp"]["defined_in"], "OpenProject")


class TestPaginateEntitySurfacesInstanceAttributes(unittest.TestCase):
    def test_instance_attributes_copied_to_result(self):
        from flextoolsmcp.server.handlers.api import paginate_entity

        entity = {
            "category": "general",
            "summary": "Project facade",
            "source_file": "FLExProject.py",
            "methods": [],
            "properties": [],
            "instance_attributes": [
                {
                    "name": "lp",
                    "type": "LangProject",
                    "kind": "instance_attr",
                    "description": "Lang project root",
                    "access_path": "project.lp",
                    "defined_in": "OpenProject",
                }
            ],
        }
        result = paginate_entity(
            entity,
            summary_only=True,
            method_filter="",
            limit=50,
            offset=0,
            object_type="FLExProject",
        )
        self.assertIn("instance_attributes", result)
        self.assertEqual(result["instance_attributes"][0]["name"], "lp")
        self.assertEqual(result["instance_attributes"][0]["access_path"], "project.lp")


class TestShippedIndexHasLpLexDB(unittest.TestCase):
    def test_flexproject_index_includes_instance_attributes(self):
        python_dir = (
            Path(__file__).parent.parent / "src" / "flextoolsmcp" / "index" / "python"
        )
        candidates = sorted(python_dir.glob("flexicon_api_v*.json"))
        self.assertTrue(candidates, "expected a shipped flexicon_api index")
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
        entity = data["entities"]["FLExProject"]
        attrs = {row["name"]: row for row in entity.get("instance_attributes", [])}
        self.assertIn("lp", attrs)
        self.assertIn("lexDB", attrs)


if __name__ == "__main__":
    unittest.main()
