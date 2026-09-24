#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #163: three-tier casting-helper injection is formally retired, not restored."""

import ast
import unittest
from pathlib import Path


class TestIssue163CastingInjectionRetired(unittest.TestCase):
    def test_injection_helpers_removed_from_execution_module(self):
        from server.handlers import execution as execution_mod

        self.assertFalse(
            hasattr(execution_mod, "_get_api_mode_imports"),
            "_get_api_mode_imports should be removed (retire, not restore)",
        )
        self.assertFalse(
            hasattr(execution_mod, "_get_casting_helpers_code"),
            "_get_casting_helpers_code should be removed (retire, not restore)",
        )
        # Direct validation helper kept for tests / future api_mode probes.
        self.assertTrue(callable(getattr(execution_mod, "_validate_api_mode", None)))

    def test_runner_template_does_not_import_casting_helpers(self):
        execution_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "flextoolsmcp"
            / "server"
            / "handlers"
            / "execution.py"
        )
        source = execution_path.read_text(encoding="utf-8")
        module_tree = ast.parse(source, filename=str(execution_path))

        runner_literal = None
        for node in ast.walk(module_tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "runner_script"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                runner_literal = node.value.value
                break

        self.assertIsNotNone(runner_literal, "runner_script literal not found in execution.py")
        self.assertNotIn(
            "casting_helpers",
            runner_literal,
            "generated runner must not inject casting_helpers",
        )
        self.assertNotIn("API_MODE_IMPORTS", runner_literal)
        self.assertIn("from flexicon import", runner_literal)


if __name__ == "__main__":
    unittest.main()
