#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Direct unit tests for detect_getall_unsafe_idiom() (getall-contract SPEC
Level 3, specs/getall-contract/SPEC.md / tasks.md).

CYCLE-4 REVERSAL: flexicon 4.3.0 standardized GetAll() docstrings and
upgraded `EnumerableWrapper` (flexicon/code/BaseOperations.py, commit
205d5a9) to a genuine, safe behavioral collection -- it caches the
materialized list on first access, so `len()`, subscript/slice, and repeat
iteration are all safe directly on the result. The flexicon-mode
container-shape taxonomy (a/b/c) and this detector's flexicon-mode advisory
are therefore obsolete. The detector's scope is INVERTED here: it is now
SILENT in flexicon mode and fires ONLY in `flexlibs_stable` mode, against a
conservative, hand-curated allowlist of FLExProject methods documented as
raw one-shot iterators/generators (`STABLE_ONE_SHOT_METHODS` in
server/validators.py). See that module's HISTORY/LIMITATION comments for
the full rationale and membership sourcing.
"""

import ast
import unittest

from server.validators import detect_getall_unsafe_idiom


def _run(code: str, api_mode: str = "flexlibs_stable"):
    return detect_getall_unsafe_idiom(ast.parse(code), api_mode, None)


class TestStableModeUnsafeIdioms(unittest.TestCase):
    """flexlibs_stable mode: raw one-shot iterator/generator methods --
    len()/subscript/truthiness/double-consume are all unsafe."""

    def test_len_on_tracked_variable_is_flagged(self):
        code = (
            "entries = project.LexiconAllEntries()\n"
            "report.Info(str(len(entries)))\n"
        )
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])
        self.assertEqual(result["issues"][0]["shape"], "c")
        self.assertIn("len()", result["issues"][0]["idioms"])
        self.assertIn("list(", result["issues"][0]["suggestion"])

    def test_len_on_inline_call_is_flagged(self):
        code = "report.Info(str(len(project.LexiconAllEntries())))\n"
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])
        self.assertIn("len()", result["issues"][0]["idioms"])

    def test_subscript_on_tracked_variable_is_flagged(self):
        code = (
            "texts = project.TextsGetAll()\n"
            "first = texts[0]\n"
        )
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])
        self.assertIn("subscript/slice", result["issues"][0]["idioms"])

    def test_subscript_on_inline_call_is_flagged(self):
        code = "first = project.ObjectsIn(ITextRepository)[0]\n"
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])
        self.assertEqual(result["issues"][0]["entity"], "ObjectsIn")

    def test_truthiness_if_not_is_flagged(self):
        code = (
            "entries = project.LexiconAllEntries()\n"
            "if not entries:\n"
            "    report.Info('none')\n"
        )
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])
        self.assertIn("truthiness", result["issues"][0]["idioms"])

    def test_truthiness_bare_if_is_flagged(self):
        code = (
            "entries = project.LexiconAllEntries()\n"
            "if entries:\n"
            "    report.Info('some')\n"
        )
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])
        self.assertIn("truthiness", result["issues"][0]["idioms"])

    def test_double_consume_repeated_for_loop_is_flagged(self):
        code = (
            "entries = project.ReversalEntries('en')\n"
            "for e in entries:\n"
            "    pass\n"
            "for e in entries:\n"
            "    pass\n"
        )
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])
        self.assertIn("double-consume (repeated iteration)", result["issues"][0]["idioms"])

    def test_lexicon_all_entries_sorted_is_covered(self):
        code = (
            "entries = project.LexiconAllEntriesSorted()\n"
            "report.Info(str(len(entries)))\n"
        )
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])

    def test_get_lexical_relation_types_is_covered(self):
        code = (
            "types = project.GetLexicalRelationTypes()\n"
            "report.Info(str(len(types)))\n"
        )
        result = _run(code)
        self.assertTrue(result["has_unsafe_idiom"])


class TestNoFalsePositives(unittest.TestCase):
    """SPEC §7: no false positive on plain single-pass iteration/next()."""

    def test_plain_single_for_loop_is_silent(self):
        code = (
            "for e in project.LexiconAllEntries():\n"
            "    report.Info(str(e))\n"
        )
        result = _run(code)
        self.assertFalse(result["has_unsafe_idiom"])

    def test_single_pass_next_is_silent(self):
        code = (
            "it = project.LexiconAllEntries()\n"
            "first = next(iter(it))\n"
        )
        result = _run(code)
        self.assertFalse(result["has_unsafe_idiom"])

    def test_unrelated_len_call_is_silent(self):
        code = (
            "names = ['a', 'b']\n"
            "report.Info(str(len(names)))\n"
        )
        result = _run(code)
        self.assertFalse(result["has_unsafe_idiom"])

    def test_known_safe_stable_methods_are_not_in_allowlist(self):
        """GetAllSemanticDomains (real list) / GetAllVernacularWSs (set) are
        confirmed-safe by their flexlibs docstrings/return types and are
        deliberately excluded from STABLE_ONE_SHOT_METHODS."""
        code = (
            "domains = project.GetAllSemanticDomains()\n"
            "report.Info(str(len(domains)))\n"
            "wss = project.GetAllVernacularWSs()\n"
            "report.Info(str(len(wss)))\n"
        )
        result = _run(code)
        self.assertFalse(result["has_unsafe_idiom"])


class TestFlexiconModeAlwaysSilent(unittest.TestCase):
    """CYCLE-4 REVERSAL (SPEC scope inversion): flexicon mode is now ALWAYS
    silent, regardless of idiom or entity -- flexicon 4.3.0's
    EnumerableWrapper.GetAll() genuinely supports these operations safely."""

    def test_len_on_flexicon_getall_is_silent(self):
        code = (
            "segs = SegmentOperations(project).GetAll()\n"
            "report.Info(str(len(segs)))\n"
        )
        result = _run(code, api_mode="flexicon")
        self.assertFalse(result["has_unsafe_idiom"])

    def test_subscript_on_flexicon_getall_is_silent(self):
        code = "text = project.Texts.GetAll()[0]\n"
        result = _run(code, api_mode="flexicon")
        self.assertFalse(result["has_unsafe_idiom"])

    def test_double_consume_on_flexicon_getall_is_silent(self):
        code = (
            "segs = SegmentOperations(project).GetAll()\n"
            "for s in segs:\n"
            "    pass\n"
            "for s in segs:\n"
            "    pass\n"
        )
        result = _run(code, api_mode="flexicon")
        self.assertFalse(result["has_unsafe_idiom"])

    def test_liblcm_mode_is_always_silent(self):
        code = (
            "entries = project.LexiconAllEntries()\n"
            "report.Info(str(len(entries)))\n"
        )
        result = _run(code, api_mode="liblcm")
        self.assertFalse(result["has_unsafe_idiom"])


class TestGracefulDegradation(unittest.TestCase):
    """No crash / no false positive when inputs are missing or unresolvable."""

    def test_none_code_tree_is_silent(self):
        result = detect_getall_unsafe_idiom(None, "flexlibs_stable", None)
        self.assertFalse(result["has_unsafe_idiom"])

    def test_none_api_index_is_silent_but_still_detects(self):
        """api_index is unused by the stable-mode allowlist path, so a
        missing index must NOT suppress detection (unlike the removed
        flexicon-mode index-driven resolution)."""
        code = (
            "entries = project.LexiconAllEntries()\n"
            "report.Info(str(len(entries)))\n"
        )
        result = detect_getall_unsafe_idiom(ast.parse(code), "flexlibs_stable", None)
        self.assertTrue(result["has_unsafe_idiom"])

    def test_unknown_method_is_silent(self):
        code = (
            "widgets = project.GetAllWidgets()\n"
            "report.Info(str(len(widgets)))\n"
        )
        result = _run(code)
        self.assertFalse(result["has_unsafe_idiom"])

    def test_non_project_receiver_is_silent(self):
        """STABLE_ONE_SHOT_METHODS only matches the `project.<method>(...)`
        calling convention; an unrelated receiver must not match."""
        code = (
            "entries = other_thing.LexiconAllEntries()\n"
            "report.Info(str(len(entries)))\n"
        )
        result = _run(code)
        self.assertFalse(result["has_unsafe_idiom"])


if __name__ == "__main__":
    unittest.main()
