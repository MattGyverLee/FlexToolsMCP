#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #314: models wrote `from helpers import is_empty_multistring`.

The run_module description listed the injected helper globals as
"Helpers: is_empty_multistring, ...", which weak models read as a module
name, so their scripts died with "No module named 'helpers'". Two fixes:

- the description now says the names are injected globals, not importable;
- the runner registers a `helpers` shim in sys.modules so the import works
  anyway and resolves to the same injected objects.

The shim test pulls the real `if "helpers" not in sys.modules:` block out
of execution.py's `runner_script` template (as
test_is_empty_multistring_defensive.py does for the helper itself) so it
cannot drift from what ships.
"""

import ast
import types
import unittest
from pathlib import Path

EXECUTION_PY = (
    Path(__file__).resolve().parents[1]
    / "src" / "flextoolsmcp" / "server" / "handlers" / "execution.py"
)
TOOL_DEFINITIONS_PY = EXECUTION_PY.parents[1] / "tool_definitions.py"
HELPER_NAMES = (
    "is_empty_multistring", "FLEX_EMPTY_PLACEHOLDER",
    "find_writing_system", "list_writing_systems",
)


def _runner_script_source():
    tree = ast.parse(EXECUTION_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "runner_script"
            and isinstance(node.value, ast.Constant)
        ):
            return node.value.value
    raise AssertionError("runner_script template not found in execution.py")


def _shim_block():
    source = _runner_script_source()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.If)
            and "helpers" in ast.get_source_segment(source, node.test)
            and "sys.modules" in ast.get_source_segment(source, node.test)
        ):
            return ast.get_source_segment(source, node)
    raise AssertionError("helpers shim block not found in runner_script")


def _run_shim(existing_modules):
    fake_sys = types.SimpleNamespace(modules=dict(existing_modules))
    module_namespace = {name: object() for name in HELPER_NAMES}
    exec(_shim_block(), {
        "sys": fake_sys, "types": types, "module_namespace": module_namespace,
    })
    return fake_sys.modules, module_namespace


class HelpersShimTests(unittest.TestCase):
    def test_shim_exposes_the_injected_objects(self):
        modules, namespace = _run_shim({})
        shim = modules["helpers"]
        for name in HELPER_NAMES:
            self.assertIs(getattr(shim, name), namespace[name])

    def test_shim_does_not_replace_a_real_helpers_module(self):
        real = types.ModuleType("helpers")
        modules, _ = _run_shim({"helpers": real})
        self.assertIs(modules["helpers"], real)

    def test_runner_script_compiles(self):
        compile(_runner_script_source(), "runner_script", "exec")


class RunModuleDescriptionTests(unittest.TestCase):
    def test_description_says_not_to_import_helpers(self):
        desc = TOOL_DEFINITIONS_PY.read_text(encoding="utf-8")
        self.assertNotIn("Helpers:", desc)
        self.assertIn("do NOT import", desc)
        for name in HELPER_NAMES:
            self.assertIn(name, desc)


if __name__ == "__main__":
    unittest.main()
