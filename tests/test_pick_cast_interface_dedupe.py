#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3: _pick_cast_interface treats duplicate defined_on labels as one interface."""

import unittest

from server.validators import _pick_cast_interface, detect_casting_needs


class TestPickCastInterfaceDedupe(unittest.TestCase):
    def test_descriptive_duplicate_available_on_resolves(self):
        picked = _pick_cast_interface(
            "Gloss",
            ["ILexSense", "ILexSense (raw LCM)"],
            casting_index=None,
        )
        self.assertEqual(picked, "ILexSense")

    def test_descriptive_duplicate_in_casting_index_resolves(self):
        index = {
            "properties": {
                "Gloss": {
                    "defined_on": ["ILexSense", "ILexSense (raw LCM)"],
                    "requires_cast_from": ["ICmObject"],
                }
            }
        }
        picked = _pick_cast_interface(
            "Gloss",
            [],
            casting_index=index,
            receiver_name="unrecognized_receiver_zz",
        )
        self.assertEqual(picked, "ILexSense")

    def test_detect_casting_needs_emits_rewrite_not_ambiguous_one_of(self):
        index = {
            "properties": {
                "ExampleProp": {
                    "defined_on": ["ILexSense", "ILexSense (raw LCM)"],
                    "requires_cast_from": ["ICmObject"],
                }
            },
            "polymorphic_collections": {},
        }
        code = "def f(obj):\n    x = obj.ExampleProp\n"
        result = detect_casting_needs(code, index)
        issues = [i for i in result["casting_issues"] if i["property"] == "ExampleProp"]
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertIsNotNone(issue.get("cast_interface"))
        self.assertNotIn("one of:", issue.get("fix", ""))


if __name__ == "__main__":
    unittest.main()
