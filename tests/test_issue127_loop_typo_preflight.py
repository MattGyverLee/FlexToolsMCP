#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #127: loop-bound variables inherit element_type for typo preflight."""

import ast
import unittest

from server.validators import detect_interface_attribute_typos


class _FakeAPIIndex:
    """Minimal index: project.LexEntry.GetSenses -> ILexSense elements."""

    def __init__(self, *, get_senses_polymorphic: bool = False):
        self.flexicon = {
            "entities": {
                "FLExProject": {
                    "properties": [
                        {"name": "LexEntry", "return_type": "LexEntryOperations"},
                    ],
                    "methods": [],
                },
                "LexEntryOperations": {
                    "methods": [
                        {
                            "name": "GetSenses",
                            "is_mutating": False,
                            "element_type": "ILexSense",
                            "polymorphic": get_senses_polymorphic,
                        },
                        {
                            "name": "GetComplexFormComponents",
                            "is_mutating": False,
                            "element_type": "ICmObject",
                            "polymorphic": True,
                        },
                    ]
                },
            }
        }
        self.liblcm = {
            "entities": {
                "ILexSense": {
                    "properties": [{"name": "Gloss"}],
                    "methods": [],
                    "interfaces": ["ICmObject"],
                },
                "ICmObject": {
                    "properties": [{"name": "Guid"}],
                    "methods": [],
                    "interfaces": [],
                },
            }
        }
        self.flexlibs_stable = {}


class TestIssue127LoopTypoPreflight(unittest.TestCase):
    def _run(self, code: str, api_index: _FakeAPIIndex):
        return detect_interface_attribute_typos(ast.parse(code), api_index)

    def test_loop_variable_typo_detected_without_explicit_cast(self):
        code = (
            "def f(entry):\n"
            "    for s in project.LexEntry.GetSenses(entry):\n"
            "        print(s.Glosss)\n"
        )
        result = self._run(code, _FakeAPIIndex())
        self.assertTrue(result["has_typos"], result)
        self.assertEqual(result["issues"][0]["typo_attr"], "Glosss")
        self.assertIn("Gloss", result["issues"][0]["did_you_mean"])

    def test_explicit_cast_still_catches_same_typo(self):
        code = (
            "from SIL.LCModel import ILexSense\n"
            "def f(x):\n"
            "    s = ILexSense(x)\n"
            "    print(s.Glosss)\n"
        )
        result = self._run(code, _FakeAPIIndex())
        self.assertTrue(result["has_typos"], result)

    def test_polymorphic_loop_binding_does_not_typo_check(self):
        """Weak ICmObject element types must not produce false typo positives."""
        code = (
            "def f(entry):\n"
            "    for c in project.LexEntry.GetComplexFormComponents(entry):\n"
            "        print(c.Glosss)\n"
        )
        result = self._run(code, _FakeAPIIndex())
        self.assertFalse(result["has_typos"], result)


if __name__ == "__main__":
    unittest.main()
