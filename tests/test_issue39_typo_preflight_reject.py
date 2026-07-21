#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #39: preflight must upgrade high-confidence "did you mean"
attribute typos on a statically-typed receiver (ILexDb.EntriesOC -> Entries,
FLExProject-cast.InflectionFeature -> InflectionFeatures) to a preflight
FAILURE, instead of letting the code execute and crash inside an already-open
LCM transaction.

Before this fix, this class of typo was only caught by Python's native
runtime "Did you mean" AttributeError suffix -- AFTER the code crashed. The
runtime hint even told the AI "resubmit; preflight should now catch it," but
that was false: detect_casting_needs' casting_index lookup only recognizes
properties that genuinely require a cast (exist elsewhere, not on the base
type) -- a pure typo like `EntriesOC` doesn't exist ANYWHERE, so the lookup
silently missed it and preflight passed again on resubmit.
"""

import ast
import unittest

from server.validators import detect_interface_attribute_typos, _interface_member_names


class FakeAPIIndex:
    """Minimal stand-in for the real APIIndex -- just enough entity/property/
    method shape for detect_interface_attribute_typos to walk."""

    liblcm = {
        "entities": {
            "ILexDb": {
                "properties": [
                    {"name": "Entries"},
                    {"name": "AppendixesOC"},
                    {"name": "ExtendedNoteTypesOA"},
                ],
                "methods": [],
                "interfaces": ["ICmObject"],
            },
            "ICmObject": {
                "properties": [{"name": "Guid"}, {"name": "Hvo"}],
                "methods": [],
                "interfaces": [],
            },
            "IWfiAnalysis": {
                "properties": [{"name": "CategoryRA"}, {"name": "SenseRA"}],
                "methods": [],
                "interfaces": ["ICmObject"],
            },
        }
    }
    flexicon = {
        "entities": {
            "FLExProject": {
                "properties": [
                    {"name": "InflectionFeatures"},
                    {"name": "LexEntry"},
                ],
                "methods": [],
                "interfaces": [],
            },
        }
    }
    flexlibs_stable = {}


class TestInterfaceAttributeTypoDetection(unittest.TestCase):
    def _run(self, code):
        tree = ast.parse(code)
        return detect_interface_attribute_typos(tree, FakeAPIIndex())

    def test_ilexdb_entriesoc_typo_detected_with_rewrite(self):
        """ILexDb(x).EntriesOC -- high-confidence match to 'Entries'."""
        code = (
            "from SIL.LCModel import ILexDb\n"
            "def f(x):\n"
            "    lexdb = ILexDb(x)\n"
            "    return lexdb.EntriesOC\n"
        )
        result = self._run(code)
        self.assertTrue(result["has_typos"], result)
        issue = result["issues"][0]
        self.assertEqual(issue["property"], "EntriesOC")
        self.assertEqual(issue["object_type"], "ILexDb")
        self.assertIn("Entries", issue["did_you_mean"])
        self.assertEqual(issue["rewrite"], "lexdb.Entries")
        self.assertEqual(issue["imports_needed"], [])
        self.assertEqual(issue["severity"], "error")

    def test_inline_cast_typo_detected(self):
        """Inline cast form: ILexDb(x).EntriesOC (no separate alias line)."""
        code = (
            "from SIL.LCModel import ILexDb\n"
            "def f(x):\n"
            "    return ILexDb(x).EntriesOC\n"
        )
        result = self._run(code)
        self.assertTrue(result["has_typos"], result)
        self.assertEqual(result["issues"][0]["rewrite"], "ILexDb(x).Entries")

    def test_ilexdb_alias_extendednotetypesoa_typo(self):
        """A second cast-alias-rooted typo shape, distinct property, to prove
        the detector isn't hardcoded to a single name pair.

        Note: the issue's other headline example (`project.InflectionFeature`
        -> `project.InflectionFeatures`) is a `project.<accessor>` chain, not
        a cast-alias-rooted interface access -- that shape is already caught
        by the pre-existing `detect_invalid_project_chains` gate
        (`invalid_api_chain`), which this function deliberately does not
        duplicate (it only handles receivers with a statically-known LibLCM/
        flexicon *interface* cast, e.g. `ILexDb(x)` / `fp = ISomeIface(x)`).
        """
        code = (
            "from SIL.LCModel import ILexDb\n"
            "def f(x):\n"
            "    lexdb = ILexDb(x)\n"
            "    return lexdb.ExtendedNoteTypeOA\n"
        )
        result = self._run(code)
        self.assertTrue(result["has_typos"], result)
        issue = result["issues"][0]
        self.assertEqual(issue["property"], "ExtendedNoteTypeOA")
        self.assertIn("ExtendedNoteTypesOA", issue["did_you_mean"])
        self.assertEqual(issue["rewrite"], "lexdb.ExtendedNoteTypesOA")

    def test_valid_property_not_flagged(self):
        """A genuinely correct property must never be flagged."""
        code = (
            "from SIL.LCModel import ILexDb\n"
            "def f(x):\n"
            "    lexdb = ILexDb(x)\n"
            "    return lexdb.Entries\n"
        )
        result = self._run(code)
        self.assertFalse(result["has_typos"], result)

    def test_untyped_receiver_not_flagged(self):
        """No cast in scope -> no interface to check against -> leave for
        runtime rather than guess wrong."""
        code = "def f(lexdb):\n    return lexdb.EntriesOC\n"
        result = self._run(code)
        self.assertFalse(result["has_typos"], result)

    def test_unknown_interface_not_flagged(self):
        """A cast to an interface we don't have in the index -- can't check,
        so don't guess."""
        code = (
            "def f(x):\n"
            "    obj = ISomeUnindexedInterface(x)\n"
            "    return obj.WhoKnowsOC\n"
        )
        result = self._run(code)
        self.assertFalse(result["has_typos"], result)

    def test_always_safe_members_not_flagged_even_when_typed(self):
        """Guid/Hvo etc. are whitelisted regardless of receiver type."""
        code = (
            "from SIL.LCModel import ILexDb\n"
            "def f(x):\n"
            "    lexdb = ILexDb(x)\n"
            "    return lexdb.Guid\n"
        )
        result = self._run(code)
        self.assertFalse(result["has_typos"], result)

    def test_no_confident_match_left_for_runtime(self):
        """A name with no close match to any real member is NOT rejected --
        conservative posture matches detect_invalid_project_chains."""
        code = (
            "from SIL.LCModel import ILexDb\n"
            "def f(x):\n"
            "    lexdb = ILexDb(x)\n"
            "    return lexdb.ZzzCompletelyUnrelatedName\n"
        )
        result = self._run(code)
        self.assertFalse(result["has_typos"], result)

    def test_interface_member_names_includes_one_hop_parent(self):
        """_interface_member_names pulls in one hop of parent interfaces so
        inherited members (Guid on ICmObject) don't false-positive on a
        derived interface even without the explicit whitelist."""
        members = _interface_member_names("ILexDb", FakeAPIIndex())
        self.assertIn("Entries", members)
        self.assertIn("Guid", members)  # inherited from ICmObject


class TestNoNewImportsForTypoFix(unittest.TestCase):
    """A typo fix never needs a new import -- it's the same interface, just
    the correct member name."""

    def test_imports_needed_is_empty(self):
        code = (
            "from SIL.LCModel import ILexDb\n"
            "def f(x):\n"
            "    lexdb = ILexDb(x)\n"
            "    return lexdb.EntriesOC\n"
        )
        tree = ast.parse(code)
        result = detect_interface_attribute_typos(tree, FakeAPIIndex())
        self.assertEqual(result["issues"][0]["imports_needed"], [])


if __name__ == "__main__":
    unittest.main()
