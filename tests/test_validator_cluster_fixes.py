#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the validator-cluster bug fixes (issues #39, #40, #41, #44).

#40 -- casting gate over-rejects safe read-only property access
#41 -- import scanner false-rejects parenthesized multi-line imports
#39 -- surface Python's native "Did you mean" for attribute typos
#44 -- writeability count consistency (raw set_String counts as a mutation)
"""

import unittest

from server.validators import (
    detect_casting_needs,
    detect_missing_operations_imports,
    extract_python_did_you_mean,
    certify_script_readonly,
    _collect_all_imported_names,
)


class TestIssue40CastingOverRejection(unittest.TestCase):
    """The advanced casting heuristic must stop flagging safe access."""

    INDEX = {
        "properties": {
            "Hvo": {"defined_on": ["ICmObject"], "requires_cast_from": ["object"]},
            "Guid": {"defined_on": ["ICmObject"], "requires_cast_from": ["object"]},
            "IsLabel": {"defined_on": ["ISegment"], "requires_cast_from": ["ICmObject"]},
            "CategoryRA": {
                # Descriptive form -- the raw `in defined_on` check used to miss
                # this even after an explicit cast.
                "defined_on": ["IWfiAnalysis (raw LCM)"],
                "requires_cast_from": ["ICmObject"],
            },
        },
        "polymorphic_collections": {},
    }

    def _flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    def test_universally_safe_members_not_flagged(self):
        """Guid / Hvo live on ICmObject -- never need a cast."""
        code = (
            "def f(obj):\n"
            "    a = obj.Hvo\n"
            "    b = obj.Guid\n"
            "    return a, b\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("Hvo", flagged)
        self.assertNotIn("Guid", flagged)

    def test_method_call_on_operations_alias_not_flagged(self):
        """`segOps.IsLabel(seg)` is a wrapper method, not property access."""
        code = (
            "from flexicon import SegmentOperations\n"
            "def f(project, seg):\n"
            "    segOps = SegmentOperations(project)\n"
            "    return segOps.IsLabel(seg)\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("IsLabel", flagged)

    def test_cast_alias_with_descriptive_defined_on_not_flagged(self):
        """`wa = IWfiAnalysis(ana); wa.CategoryRA` -- the cast satisfies it
        even when defined_on carries a descriptive '(raw LCM)' qualifier."""
        code = (
            "from SIL.LCModel import IWfiAnalysis\n"
            "def f(ana):\n"
            "    wa = IWfiAnalysis(ana)\n"
            "    return wa.CategoryRA\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("CategoryRA", flagged)

    def test_bare_untyped_property_still_flags(self):
        """Safety guard: an untyped receiver accessing a cast-requiring,
        non-whitelisted property must still flag."""
        code = (
            "def f(obj):\n"
            "    return obj.IsLabel\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertIn("IsLabel", flagged)


class TestIssue41ParenthesizedImports(unittest.TestCase):
    """The missing-imports gate must see parenthesized / multi-line imports."""

    def test_parenthesized_multiline_import_satisfies_gate(self):
        code = (
            "from flexicon import (\n"
            "    SegmentOperations,\n"
            "    WordformOperations,\n"
            ")\n"
            "def f(project):\n"
            "    SegmentOperations(project)\n"
            "    WordformOperations(project)\n"
        )
        result = detect_missing_operations_imports(code, "flexicon")
        self.assertFalse(
            result["has_missing"],
            f"Parenthesized import should satisfy the gate; got: {result}"
        )

    def test_aliased_import_collected(self):
        names = _collect_all_imported_names(
            "from flexicon import LexEntryOperations as LEO\n"
        )
        self.assertIsNotNone(names)
        self.assertIn("LexEntryOperations", names)
        self.assertIn("LEO", names)

    def test_genuinely_missing_import_still_flagged(self):
        code = (
            "def f(project):\n"
            "    SegmentOperations(project)\n"
        )
        result = detect_missing_operations_imports(code, "flexicon")
        self.assertTrue(result["has_missing"])
        self.assertIn("SegmentOperations", result["missing_imports"])

    def test_unparsable_code_falls_back_to_regex(self):
        # Single-line import on otherwise-unparsable code still parses names.
        self.assertIsNone(_collect_all_imported_names("def f(:\n  pass\n"))


class TestIssue39NativeDidYouMean(unittest.TestCase):
    """Python's native AttributeError suggestion must be extractable."""

    def test_extracts_suggestion(self):
        msg = (
            "AttributeError: 'ILexDb' object has no attribute 'EntriesOC'. "
            "Did you mean: 'Entries'?"
        )
        self.assertEqual(extract_python_did_you_mean(msg), "Entries")

    def test_returns_none_without_suggestion(self):
        msg = "AttributeError: 'ILexDb' object has no attribute 'EntriesOC'."
        self.assertIsNone(extract_python_did_you_mean(msg))

    def test_handles_empty(self):
        self.assertIsNone(extract_python_did_you_mean(""))


class TestIssue44WriteabilityCount(unittest.TestCase):
    """A raw set_String write must surface as an (unprotected) mutation so the
    rejecting handler's mutating total is non-zero and self-consistent."""

    def test_raw_set_string_counts_as_mutation(self):
        code = (
            "def f(seg, en_h, tss):\n"
            "    seg.FreeTranslation.set_String(en_h, tss)\n"
        )
        cert = certify_script_readonly(code, api_index=None)
        unprotected = cert.get("unprotected_liblcm_calls", [])
        mutating = [m for m in cert.get("mutating_calls", []) if m.get("is_mutating")]
        total = len(mutating) + len(unprotected)
        self.assertFalse(cert["is_certified_readonly"])
        self.assertGreater(
            total, 0,
            "raw set_String must contribute to the total mutation count "
            "(issue #44: no more mutating=0 alongside raw_lcm=1)"
        )


class TestIssue40DomainRuling(unittest.TestCase):
    """Issue #40 domain-constrained whitelist additions and conditional guards.

    (a) project.* -- never flag; it's a Python wrapper, not C# navigation.
    (a) BestAnalysisAlternative / BestVernacularAlternative / Text -- always
        safe (IMultiString/IMultiUnicode value members).
    (b) Conditional members (LexemeFormOA, AnalysesRS, Wordform, Form,
        FreeTranslation) -- skipped only when cast_alias proves safe type;
        still flagged for untyped receivers.
    (c) SenseRA / MorphRA / CategoryRA still flag with a valid rewrite.
    """

    # Casting index that covers all members tested below.
    INDEX = {
        "properties": {
            "LexemeFormOA": {
                "defined_on": ["ILexEntry"],
                "requires_cast_from": ["ICmObject"],
            },
            "AnalysesRS": {
                "defined_on": ["ISegment"],
                "requires_cast_from": ["ICmObject"],
            },
            "Wordform": {
                "defined_on": ["IWfiAnalysis", "IWfiGloss"],
                "requires_cast_from": ["ICmObject"],
            },
            "Form": {
                "defined_on": ["IMoForm"],
                "requires_cast_from": ["ICmObject"],
            },
            "FreeTranslation": {
                "defined_on": ["ISegment"],
                "requires_cast_from": ["ICmObject"],
            },
            "BestAnalysisAlternative": {
                "defined_on": ["IMultiString"],
                "requires_cast_from": ["ICmObject"],
            },
            "BestVernacularAlternative": {
                "defined_on": ["IMultiString"],
                "requires_cast_from": ["ICmObject"],
            },
            "SenseRA": {
                "defined_on": ["IChkSense", "IWfiMorphBundle"],
                "requires_cast_from": ["ICmObject"],
            },
            "MorphRA": {
                "defined_on": ["IWfiMorphBundle"],
                "requires_cast_from": ["ICmObject"],
            },
            "CategoryRA": {
                "defined_on": ["IWfiAnalysis (raw LCM)"],
                "requires_cast_from": ["ICmObject"],
            },
        },
        "polymorphic_collections": {},
    }

    def _flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    # --- (a) project.* never flags ---

    def test_project_receiver_never_flags(self):
        """project.X is a Python wrapper call; casting gate must never fire."""
        code = (
            "def f():\n"
            "    x = project.LexEntry\n"
            "    y = project.LexSense\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("LexEntry", flagged)
        self.assertNotIn("LexSense", flagged)

    def test_project_lexemeformoa_not_flagged(self):
        """project.LexemeFormOA must not flag -- receiver is project."""
        code = "lf = project.LexemeFormOA\n"
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("LexemeFormOA", flagged)

    # --- (a) Best* and Text always safe ---

    def test_best_analysis_alternative_not_flagged(self):
        """BestAnalysisAlternative is unconditionally whitelisted."""
        code = (
            "def f(sense):\n"
            "    return sense.Gloss.BestAnalysisAlternative.Text\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("BestAnalysisAlternative", flagged)

    def test_best_vernacular_alternative_not_flagged(self):
        """BestVernacularAlternative is unconditionally whitelisted."""
        code = (
            "def f(entry):\n"
            "    return entry.LexemeFormOA.Form.BestVernacularAlternative.Text\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("BestVernacularAlternative", flagged)

    def test_text_accessor_not_flagged(self):
        """Chained .Text off a Best* accessor is not flagged."""
        code = (
            "def f(ms):\n"
            "    return ms.BestAnalysisAlternative.Text\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("Text", flagged)

    # --- (b) Conditional members: safe when cast_alias proves type ---

    def test_lexemeformoa_safe_when_cast_alias_proves_ilexentry(self):
        """LexemeFormOA must not flag when cast_alias proves ILexEntry."""
        code = (
            "from SIL.LCModel import ILexEntry\n"
            "def f(entry):\n"
            "    e = ILexEntry(entry)\n"
            "    return e.LexemeFormOA\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("LexemeFormOA", flagged)

    def test_lexemeformoa_flags_when_untyped(self):
        """LexemeFormOA must still flag when receiver has no cast_alias."""
        code = (
            "def f(obj):\n"
            "    return obj.LexemeFormOA\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertIn("LexemeFormOA", flagged)

    def test_analysesr_safe_when_cast_alias_proves_isegment(self):
        """AnalysesRS must not flag when receiver is ISegment cast_alias."""
        code = (
            "from SIL.LCModel import ISegment\n"
            "def f(seg):\n"
            "    s = ISegment(seg)\n"
            "    return s.AnalysesRS\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("AnalysesRS", flagged)

    def test_analysesr_flags_when_untyped(self):
        """AnalysesRS must still flag when receiver has no cast_alias."""
        code = (
            "def f(obj):\n"
            "    return obj.AnalysesRS\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertIn("AnalysesRS", flagged)

    def test_form_safe_when_cast_alias_proves_imoform(self):
        """Form must not flag when receiver is IMoForm cast_alias."""
        code = (
            "from SIL.LCModel import IMoForm\n"
            "def f(mf):\n"
            "    morph = IMoForm(mf)\n"
            "    return morph.Form\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("Form", flagged)

    def test_freetranslation_safe_when_cast_alias_proves_isegment(self):
        """FreeTranslation must not flag when receiver is ISegment cast_alias."""
        code = (
            "from SIL.LCModel import ISegment\n"
            "def f(seg):\n"
            "    s = ISegment(seg)\n"
            "    return s.FreeTranslation\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("FreeTranslation", flagged)

    # --- (c) Genuinely polymorphic members still flag with valid rewrite ---

    def test_sensera_still_flags_untyped(self):
        """SenseRA is genuinely polymorphic (IChkSense + IWfiMorphBundle);
        must still flag on an untyped receiver and emit a cast_interface."""
        code = (
            "def f(obj):\n"
            "    return obj.SenseRA\n"
        )
        result = detect_casting_needs(code, self.INDEX)
        flagged = self._flagged(result)
        self.assertIn("SenseRA", flagged,
            "SenseRA is genuinely polymorphic and must still flag")
        # Verify the issue dict has a usable cast_interface or rewrite hint.
        sense_issue = next(
            (i for i in result["casting_issues"] if i["property"] == "SenseRA"), None
        )
        self.assertIsNotNone(sense_issue)
        assert sense_issue is not None  # Pyright type narrowing
        # At least one of cast_interface or fix must be non-empty.
        has_guidance = bool(sense_issue.get("cast_interface")) or bool(sense_issue.get("fix"))
        self.assertTrue(has_guidance,
            "SenseRA issue must carry cast_interface or fix guidance")

    def test_morphra_still_flags_untyped(self):
        """MorphRA is genuinely polymorphic; must still flag."""
        code = (
            "def f(obj):\n"
            "    return obj.MorphRA\n"
        )
        result = detect_casting_needs(code, self.INDEX)
        flagged = self._flagged(result)
        self.assertIn("MorphRA", flagged,
            "MorphRA must still flag on an untyped receiver")

    def test_categoryra_still_flags_untyped(self):
        """CategoryRA is genuinely polymorphic; must still flag on untyped."""
        code = (
            "def f(obj):\n"
            "    return obj.CategoryRA\n"
        )
        result = detect_casting_needs(code, self.INDEX)
        flagged = self._flagged(result)
        self.assertIn("CategoryRA", flagged,
            "CategoryRA must still flag on an untyped receiver")

    def test_categoryra_suppressed_when_cast_to_iwfianalysis(self):
        """CategoryRA must NOT flag when receiver is IWfiAnalysis cast_alias."""
        code = (
            "from SIL.LCModel import IWfiAnalysis\n"
            "def f(ana):\n"
            "    wa = IWfiAnalysis(ana)\n"
            "    return wa.CategoryRA\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("CategoryRA", flagged)


if __name__ == "__main__":
    unittest.main()
