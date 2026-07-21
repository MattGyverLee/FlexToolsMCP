#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #40: preflight casting gate over-rejects safe read-only
property access.

Covers the four fixes called for in the issue:
  1. Whitelist universally-safe members: Guid, Hvo, ClassID, ClassName, and
     the Best*Alternative accessor family.
  2. Do NOT flag arguments passed INTO flexlibs2/flexicon Operations methods
     (e.g. seg_ops.IsLabel(seg)).
  3. Track local casts -- a property accessed on a variable already assigned
     from IWfiAnalysis(...)/ISegment(...) etc. must not re-trigger the gate.
  4. When a cast genuinely is required, emit the concrete rewrite +
     imports_needed instead of a bare reject.

Also covers the widened Best*Alternative whitelist (this session): the
original fix only enumerated BestAnalysisAlternative/BestVernacularAlternative;
LibLCM ships two more siblings (BestAnalysisVernacularAlternative /
BestVernacularAnalysisAlternative), plus a pattern-based fallback for any
future Best*Alternative accessor.
"""

import unittest

from server.validators import detect_casting_needs, _is_multistring_value_member


# Minimal stand-in casting_index. CategoryRA/SenseRA/MorphRA are properties
# that genuinely require a cast when the receiver is untyped -- used to prove
# the whitelist fixes don't over-relax the gate for properties that actually
# need one.
FAKE_CASTING_INDEX = {
    "properties": {
        "CategoryRA": {
            "defined_on": ["IWfiAnalysis"],
            "requires_cast_from": ["ICmObject"],
        },
        "SenseRA": {
            "defined_on": ["IWfiAnalysis"],
            "requires_cast_from": ["ICmObject"],
        },
    },
    "polymorphic_collections": {},
}


class TestAlwaysSafeMembers(unittest.TestCase):
    """Fix 1a: Guid/Hvo/ClassID/ClassName never need a cast."""

    def _flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    def test_guid_not_flagged(self):
        code = "def f(obj):\n    return obj.Guid\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("Guid", self._flagged(result))

    def test_hvo_not_flagged(self):
        code = "def f(obj):\n    return obj.Hvo\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("Hvo", self._flagged(result))

    def test_classid_not_flagged(self):
        code = "def f(obj):\n    return obj.ClassID\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("ClassID", self._flagged(result))

    def test_classname_not_flagged(self):
        code = "def f(obj):\n    return obj.ClassName\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("ClassName", self._flagged(result))

    def test_chained_always_safe_member_not_flagged(self):
        """`entry.LexemeFormOA.Guid`-shaped chains: Guid at the tail must not
        flag even though LexemeFormOA (a different, real casting concern)
        may legitimately flag earlier in the chain."""
        code = "def f(entry):\n    return entry.LexemeFormOA.Guid\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("Guid", self._flagged(result))


class TestBestAlternativeWhitelist(unittest.TestCase):
    """Fix 1b: the Best*Alternative multistring-value accessor family."""

    def _flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    def test_best_analysis_alternative_not_flagged(self):
        code = "def f(ms):\n    return ms.BestAnalysisAlternative.Text\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("BestAnalysisAlternative", self._flagged(result))

    def test_best_vernacular_alternative_not_flagged(self):
        code = "def f(ms):\n    return ms.BestVernacularAlternative.Text\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("BestVernacularAlternative", self._flagged(result))

    def test_best_analysis_vernacular_alternative_not_flagged(self):
        """LibLCM sibling not in the original two-name enumeration."""
        code = "def f(ms):\n    return ms.BestAnalysisVernacularAlternative.Text\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("BestAnalysisVernacularAlternative", self._flagged(result))

    def test_best_vernacular_analysis_alternative_not_flagged(self):
        """LibLCM sibling not in the original two-name enumeration."""
        code = "def f(ms):\n    return ms.BestVernacularAnalysisAlternative.Text\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("BestVernacularAnalysisAlternative", self._flagged(result))

    def test_pattern_fallback_catches_unenumerated_sibling(self):
        """_is_multistring_value_member() must recognize any Best*Alternative
        shape via the startswith/endswith fallback, not just the enumerated
        set -- future LibLCM additions shouldn't need a code change here."""
        self.assertTrue(_is_multistring_value_member("BestSomeHypotheticalAlternative"))
        self.assertFalse(_is_multistring_value_member("BestGuess"))
        self.assertFalse(_is_multistring_value_member("AlternativeBest"))


class TestOperationsArgumentsNotFlagged(unittest.TestCase):
    """Fix 2: arguments passed INTO flexlibs2/flexicon Operations methods
    must not be misread as polymorphic property access."""

    def _flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    def test_operations_method_call_not_flagged(self):
        """seg_ops.IsLabel(seg) -- IsLabel is a method call on an Operations
        alias, not a property access requiring a cast."""
        code = (
            "from flexicon import SegmentOperations\n"
            "def f(project, seg):\n"
            "    seg_ops = SegmentOperations(project)\n"
            "    return seg_ops.IsLabel(seg)\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn("IsLabel", self._flagged(result))


class TestLocalCastTracking(unittest.TestCase):
    """Fix 3: a property accessed on a variable already assigned from
    IWfiAnalysis(...)/ISegment(...) etc. must not re-trigger the gate."""

    def _flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    def test_already_cast_var_not_reflagged(self):
        """wa = IWfiAnalysis(ana); wa.CategoryRA -- must not flag, the cast
        on the prior line already satisfies CategoryRA's defined_on."""
        code = (
            "from SIL.LCModel import IWfiAnalysis\n"
            "def f(ana):\n"
            "    wa = IWfiAnalysis(ana)\n"
            "    return wa.CategoryRA\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertNotIn(
            "CategoryRA", self._flagged(result),
            f"CategoryRA must not re-flag after IWfiAnalysis(ana) cast; "
            f"got: {result['casting_issues']}"
        )

    def test_uncast_var_still_flags(self):
        """Bare `ana.CategoryRA` (no cast in sight) must still flag -- this
        is the safety guarantee that proves fix 3 isn't over-relaxing."""
        code = "def f(ana):\n    return ana.CategoryRA\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertIn("CategoryRA", self._flagged(result))

    def test_wrong_cast_still_flags(self):
        """Casting to an interface that does NOT define the property must
        still flag -- local-cast tracking must not blindly trust any cast."""
        code = (
            "from SIL.LCModel import ISegment\n"
            "def f(ana):\n"
            "    seg = ISegment(ana)\n"
            "    return seg.CategoryRA\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        self.assertIn("CategoryRA", self._flagged(result))


class TestConcreteRewriteOnGenuineCast(unittest.TestCase):
    """Fix 4: when a cast genuinely is required, the issue payload must carry
    a concrete rewrite + imports_needed, not a bare reject."""

    def test_genuine_cast_issue_has_rewrite_and_imports(self):
        code = "def f(ana):\n    return ana.SenseRA\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        issues = [i for i in result["casting_issues"] if i["property"] == "SenseRA"]
        self.assertTrue(issues, f"Expected a SenseRA issue, got: {result['casting_issues']}")
        issue = issues[0]
        self.assertIn("rewrite", issue)
        self.assertIn("imports_needed", issue)
        self.assertIsNotNone(
            issue["rewrite"],
            "Genuine cast issue must carry a concrete rewrite, not a bare reject."
        )
        self.assertEqual(issue["rewrite"], "IWfiAnalysis(ana).SenseRA")
        self.assertIn("IWfiAnalysis", issue["imports_needed"][0])


if __name__ == "__main__":
    unittest.main()
