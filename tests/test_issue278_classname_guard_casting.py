#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #278: ClassName-guarded branches must satisfy the casting preflight."""

import json
import unittest
from pathlib import Path

from flextoolsmcp.server.validators import detect_casting_needs


def _load_casting_index():
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "flextoolsmcp"
        / "index"
        / "casting_index_liblcm-v11.0.0.json"
    )
    if not path.is_file():
        return None
    return json.loads(path.read_text())


class _FakeAPIIndex:
    def __init__(self, entities):
        self.flexicon = {"entities": entities}


class TestIssue278ClassNameGuardCasting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.casting_index = _load_casting_index()

    def setUp(self):
        if self.casting_index is None:
            self.skipTest("shipped casting_index_liblcm-v11.0.0.json not found")

    def test_property_access_inside_classname_eq_guard_not_flagged(self):
        code = (
            "for msa in project.LexEntry.GetAllMorphoSyntaxAnalyses(entry):\n"
            '    if msa.ClassName == "MoStemMsa":\n'
            "        pos = msa.PartOfSpeechRA\n"
        )
        api_index = _FakeAPIIndex(
            {
                "LexEntryOperations": {
                    "methods": [
                        {
                            "name": "GetAllMorphoSyntaxAnalyses",
                            "element_type": "IMoMorphSynAnalysis",
                            "polymorphic": True,
                        }
                    ]
                }
            }
        )
        result = detect_casting_needs(
            code, self.casting_index, api_index=api_index
        )
        self.assertFalse(
            result["casting_issues"],
            f"expected ClassName guard to satisfy PartOfSpeechRA; got {result['casting_issues']}",
        )

    def test_property_access_inside_classname_in_guard_not_flagged(self):
        code = (
            "for form in entry.Allomorphs:\n"
            '    if form.ClassName in ("MoStemAllomorph", "MoAffixAllomorph"):\n'
            "        env = form.PhoneEnvRC\n"
        )
        result = detect_casting_needs(code, self.casting_index)
        flagged = {i["property"] for i in result["casting_issues"]}
        self.assertNotIn(
            "PhoneEnvRC",
            flagged,
            f"ClassName in (...) guard should narrow form; issues={result['casting_issues']}",
        )

    def test_inline_cast_inside_guard_still_clean(self):
        code = (
            "msa = sense.MorphoSyntaxAnalysisRA\n"
            'if msa.ClassName == "MoStemMsa":\n'
            "    pos = IMoStemMsa(msa).PartOfSpeechRA\n"
        )
        result = detect_casting_needs(code, self.casting_index)
        flagged = {i["property"] for i in result["casting_issues"]}
        self.assertNotIn("PartOfSpeechRA", flagged, result["casting_issues"])

    def test_classname_guard_does_not_leak_across_else(self):
        code = (
            "for msa in project.LexEntry.GetAllMorphoSyntaxAnalyses(entry):\n"
            '    if msa.ClassName == "MoStemMsa":\n'
            "        pos = msa.PartOfSpeechRA\n"
            "    else:\n"
            "        other = msa.PartOfSpeechRA\n"
        )
        api_index = _FakeAPIIndex(
            {
                "LexEntryOperations": {
                    "methods": [
                        {
                            "name": "GetAllMorphoSyntaxAnalyses",
                            "element_type": "IMoMorphSynAnalysis",
                            "polymorphic": True,
                        }
                    ]
                }
            }
        )
        result = detect_casting_needs(
            code, self.casting_index, api_index=api_index
        )
        flagged_lines = {
            (i["line"], i["property"]) for i in result["casting_issues"]
        }
        self.assertNotIn((3, "PartOfSpeechRA"), flagged_lines, flagged_lines)
        self.assertIn((5, "PartOfSpeechRA"), flagged_lines, flagged_lines)


if __name__ == "__main__":
    unittest.main()
