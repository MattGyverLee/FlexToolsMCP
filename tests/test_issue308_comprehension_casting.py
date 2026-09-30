#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #308: casting preflight on flexicon facade calls inside comprehensions.

Field evidence (session_165926, ~28 rejections): Rule B (issue #121) flagged
`project.LexEntry.GetHeadword(c)` inside a comprehension even when the model
had guarded it with `c.ClassName == "LexEntry"`, and every rejection carried
`rewrite: None` plus a `pattern` cut off at 80 characters of the line.

Covers:
  - expression-level ClassName guards (IfExp body, comprehension filter,
    short-circuit `and`) satisfy Rule B, like the `if` statement #278 fixed;
  - a guard on one arm of a one-line conditional does not clear the other arm;
  - comprehension targets are tracked: every generator binds, and a
    comprehension that rebinds a name shadows an outer polymorphic loop var;
  - the unguarded case still fires, with a paste-ready rewrite that itself
    passes preflight and a `pattern` that is the flagged call.
"""

import unittest

from flextoolsmcp.server.validators import detect_casting_needs


CASTING_INDEX = {
    "properties": {
        "HeadWord": {
            "defined_on": ["ILexEntry", "ISenseOrEntry"],
            "requires_cast_from": ["ICmObject"],
        },
    },
    "polymorphic_collections": {
        "ComponentLexemesRS": {"base_type": "ICmObject"},
    },
    "class_name_mapping": {
        "LexEntry": "ILexEntry",
        "LexSense": "ILexSense",
    },
}


class _FakeAPIIndex:
    def __init__(self):
        self.flexicon = {
            "entities": {
                "FLExProject": {
                    "properties": [
                        {"name": "LexEntry", "return_type": "LexEntryOperations"},
                        {"name": "Senses", "return_type": "LexSenseOperations"},
                    ],
                    "methods": [],
                },
                "LexEntryOperations": {
                    "methods": [
                        {
                            "name": "GetAll",
                            "element_type": "ILexEntry",
                            "polymorphic": False,
                        },
                        {"name": "GetHeadword"},
                        {
                            "name": "GetComplexFormComponents",
                            "element_type": "ICmObject",
                            "polymorphic": True,
                        },
                    ]
                },
                "LexSenseOperations": {"methods": [{"name": "GetGloss"}]},
            }
        }


def _issues(code):
    return detect_casting_needs(code, CASTING_INDEX, api_index=_FakeAPIIndex())[
        "casting_issues"
    ]


LOOP = "for e in project.LexEntry.GetAll():\n"
COMPS = "project.LexEntry.GetComplexFormComponents(e)"


class TestExpressionGuardsSatisfyRuleB(unittest.TestCase):
    def test_ifexp_guard_in_comprehension_not_flagged(self):
        # Verbatim shape of the session_165926 op #45 rejection.
        code = LOOP + (
            "    report.Info(f\"components={[(project.LexEntry.GetHeadword(c) "
            "if c.ClassName == 'LexEntry' else c.ClassName) for c in "
            + COMPS + "]}\")\n"
        )
        self.assertEqual(_issues(code), [])

    def test_comprehension_filter_guard_not_flagged(self):
        code = LOOP + (
            "    heads = [project.LexEntry.GetHeadword(c) for c in " + COMPS
            + " if c.ClassName == \"LexEntry\"]\n"
        )
        self.assertEqual(_issues(code), [])

    def test_generator_and_set_and_dict_filters_not_flagged(self):
        for opener, elt, closer in (
            ("(", "project.LexEntry.GetHeadword(c)", ")"),
            ("{", "project.LexEntry.GetHeadword(c)", "}"),
            ("{", "c.Hvo: project.LexEntry.GetHeadword(c)", "}"),
        ):
            code = LOOP + (
                f"    x = {opener}{elt} for c in {COMPS} "
                f"if c.ClassName == 'LexEntry'{closer}\n"
            )
            with self.subTest(code=code):
                self.assertEqual(_issues(code), [])

    def test_and_short_circuit_guard_not_flagged(self):
        code = LOOP + (
            "    for c in " + COMPS + ":\n"
            "        if c.ClassName == 'LexEntry' and project.LexEntry.GetHeadword(c):\n"
            "            pass\n"
        )
        self.assertEqual(_issues(code), [])

    def test_and_in_if_statement_test_narrows_body(self):
        code = LOOP + (
            "    for c in " + COMPS + ":\n"
            "        if c.ClassName == 'LexEntry' and e is not None:\n"
            "            hw = project.LexEntry.GetHeadword(c)\n"
        )
        self.assertEqual(_issues(code), [])

    def test_guard_on_one_arm_does_not_clear_the_other(self):
        code = LOOP + (
            "    x = [project.LexEntry.GetHeadword(c) if c.ClassName == 'LexEntry' "
            "else project.LexEntry.GetHeadword(c) for c in " + COMPS + "]\n"
        )
        self.assertEqual(len(_issues(code)), 1, _issues(code))


class TestComprehensionTargetsTracked(unittest.TestCase):
    def test_issue_snippet_not_flagged(self):
        code = (
            "heads = [project.LexEntry.GetHeadword(c) "
            "for c in project.LexiconAllEntries()]\n"
        )
        self.assertEqual(_issues(code), [])

    def test_comprehension_target_shadows_outer_polymorphic_loop_var(self):
        code = LOOP + (
            "    for c in " + COMPS + ":\n"
            "        heads = [project.LexEntry.GetHeadword(c) "
            "for c in project.LexiconAllEntries()]\n"
        )
        self.assertEqual(_issues(code), [])

    def test_nested_for_loop_rebinding_shadows_outer(self):
        code = LOOP + (
            "    for c in " + COMPS + ":\n"
            "        for c in project.LexiconAllEntries():\n"
            "            hw = project.LexEntry.GetHeadword(c)\n"
        )
        self.assertEqual(_issues(code), [])

    def test_second_generator_is_bound(self):
        code = (
            "x = [project.LexEntry.GetHeadword(c) for e in project.LexEntry.GetAll() "
            "for c in project.LexEntry.GetComplexFormComponents(e)]\n"
        )
        self.assertEqual(
            [i["property"] for i in _issues(code)], ["GetHeadword"], _issues(code)
        )

    def test_polymorphic_collection_in_comprehension_is_bound(self):
        code = (
            "for ref in refs:\n"
            "    x = [project.LexEntry.GetHeadword(c) for c in ref.ComponentLexemesRS]\n"
        )
        self.assertEqual(
            [i["property"] for i in _issues(code)], ["GetHeadword"], _issues(code)
        )


class TestUnguardedStillFiresWithRewrite(unittest.TestCase):
    # Verbatim shape of the session_165926 op #44 rejection.
    CODE = LOOP + (
        "    report.Info(f\"components={[project.LexEntry.GetHeadword(c) for c in "
        + COMPS + "]}\")\n"
    )

    def test_true_positive_still_fires_with_rewrite(self):
        issues = _issues(self.CODE)
        self.assertEqual(len(issues), 1, issues)
        issue = issues[0]
        self.assertEqual(issue["property"], "GetHeadword")
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["pattern"], "project.LexEntry.GetHeadword(c)")
        self.assertEqual(
            issue["rewrite"],
            '(project.LexEntry.GetHeadword(c) if c.ClassName == "LexEntry" else None)',
        )
        # No single cast exists for a mixed collection: auto-fix stays off.
        self.assertIsNone(issue["cast_interface"])

    def test_applying_the_rewrite_passes_preflight(self):
        issue = _issues(self.CODE)[0]
        patched = self.CODE.replace(issue["pattern"], issue["rewrite"], 1)
        self.assertEqual(_issues(patched), [])

    def test_for_loop_statement_also_gets_rewrite(self):
        code = LOOP + (
            "    for c in " + COMPS + ":\n"
            "        comps.append(project.LexEntry.GetHeadword(c))\n"
        )
        issues = _issues(code)
        self.assertEqual(len(issues), 1, issues)
        self.assertTrue(issues[0]["rewrite"])


if __name__ == "__main__":
    unittest.main()
