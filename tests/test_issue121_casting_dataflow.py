#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #121 (part 2 of 2): loop-target dataflow in
`detect_casting_needs`.

Covers:
  - Rule B (the headline case): a polymorphically-bound loop variable passed
    as an ARGUMENT to a type-specific Operations method.
  - Rule A: a polymorphically-bound loop variable used as the RECEIVER of an
    attribute access not defined on its (weak) element type -- flags, but
    (remediation round, defect 3) never proposes a single cast_interface/
    rewrite; teaches a ClassName-branch dispatch instead.
  - Graceful degradation: no `element_type` in the index, or no `api_index`
    at all, changes NOTHING versus pre-#121 behavior.
  - Negative control: a NON-polymorphic (concrete, confirmed) element_type
    binding is treated as safe for properties defined on it -- same as an
    explicit cast alias.
  - Remediation-round regressions (defects 1-4, see the fix commit):
    (1) Rule B must not flag when element_type already EQUALS the expected
    interface; (2) Rule B must respect an intervening explicit cast, and
    the loop-target line-range binding must not survive a reassignment;
    (3) Rule A must never suggest a single cast for a confirmed-polymorphic
    receiver (the "IXOrY union interface" tier was removed -- it wasn't a
    real, castable interface); (4) variable SPELLING must never override
    PROVEN polymorphism in `_pick_cast_interface`'s receiver-name tie-break.

Modeled on `tests/evals/preflight_runner.py`'s `_FakeAPIIndex` and
`tests/test_issue103_hvo_stability.py`'s `_FakeApiIndex` (both minimal,
hand-built api indexes rather than the full generated one).
"""

import unittest

from server.validators import detect_casting_needs


# ---------------------------------------------------------------------------
# Fake casting_index -- shape matches the real build_casting_index.py output
# closely enough to drive detect_casting_needs' advanced (index-driven) loop
# and the new Rule B class_name_mapping lookup.
# ---------------------------------------------------------------------------
FAKE_CASTING_INDEX = {
    "properties": {
        "HeadWord": {
            "defined_on": ["ILexEntry", "ISenseOrEntry"],
            "requires_cast_from": ["ICmObject"],
        },
        "LexemeFormOA": {
            "defined_on": ["ILexEntry"],
            "requires_cast_from": ["ICmObject"],
        },
    },
    "polymorphic_collections": {},
    # Issue #121 Rule B: bare LCM class name -> interface. Real shape
    # confirmed against index/casting_index_liblcm-v11.0.0.json.
    "class_name_mapping": {
        "LexEntry": "ILexEntry",
        "LexSense": "ILexSense",
    },
}


class _FakeAPIIndex:
    """Minimal api_index exposing only what `detect_casting_needs` reads:
    `.flexicon["entities"][<Ops>]["properties"|"methods"]`.
    """

    def __init__(self, extra_methods=None):
        lex_entry_methods = [
            # Mirrors the real (now-fixed, post index-side remediation)
            # index: GetAll's elements are confirmed ILexEntry, not
            # polymorphic.
            {
                "name": "GetAll",
                "is_mutating": False,
                "element_type": "ILexEntry",
                "polymorphic": False,
            },
            {"name": "GetHeadword", "is_mutating": False},
            {
                "name": "GetComplexFormComponents",
                "is_mutating": False,
                "element_type": "ICmObject",
                "polymorphic": True,
            },
            # Remediation round defect 1 repro: an EXACT-match element_type
            # that the (buggy, at time of report) index still marked
            # polymorphic=True -- element_type IS ALREADY ILexSense, which
            # is exactly what class_name_mapping["LexSense"] says too, so
            # this must be treated as zero cast risk regardless of the
            # (possibly stale/overbroad) polymorphic flag.
            {
                "name": "GetSenses",
                "is_mutating": False,
                "element_type": "ILexSense",
                "polymorphic": True,
            },
            # A method with NO element_type annotation at all -- models an
            # un-annotated (today's real, pre-#121-index) method record.
            {"name": "GetSomeUnannotatedThing", "is_mutating": False},
        ]
        if extra_methods:
            lex_entry_methods.extend(extra_methods)
        self.flexicon = {
            "entities": {
                "FLExProject": {
                    "properties": [
                        {"name": "LexEntry", "return_type": "LexEntryOperations"},
                        {"name": "Senses", "return_type": "LexSenseOperations"},
                    ],
                    "methods": [],
                },
                "LexEntryOperations": {"methods": lex_entry_methods},
                "LexSenseOperations": {
                    "methods": [
                        {"name": "GetGloss", "is_mutating": False},
                    ]
                },
            }
        }


def _flagged(result):
    return {issue["property"] for issue in result["casting_issues"]}


HEADLINE_REPRO = (
    "for c in project.LexEntry.GetComplexFormComponents(entry):\n"
    "    project.LexEntry.GetHeadword(c)\n"
)


class TestRuleBArgumentPosition(unittest.TestCase):
    """Rule B: a polymorphically-bound loop var passed as an ARGUMENT to a
    type-specific Operations method (the shape Rule A can't catch -- the
    var is never the receiver of an attribute access)."""

    def test_headline_repro_flags_error_with_classname_fix(self):
        api_index = _FakeAPIIndex()
        result = detect_casting_needs(
            HEADLINE_REPRO, FAKE_CASTING_INDEX, api_index=api_index
        )
        issues = result["casting_issues"]
        self.assertTrue(issues, f"expected Rule B to fire; got: {result}")
        self.assertTrue(
            any(i.get("severity") == "error" for i in issues),
            f"expected an 'error'-severity issue; got: {issues}",
        )
        self.assertTrue(
            any("ClassName" in (i.get("fix") or "") for i in issues),
            f"expected the fix text to teach ClassName branching "
            f"(flexicon's own GetComplexFormComponents docstring "
            f"convention); got: {issues}",
        )

    def test_no_element_type_in_index_changes_nothing(self):
        """A loop over a method with NO element_type annotation must
        produce the SAME result as calling detect_casting_needs without
        api_index at all -- the degrade-gracefully case."""
        api_index = _FakeAPIIndex()
        code = (
            "for x in project.LexEntry.GetSomeUnannotatedThing(entry):\n"
            "    project.LexEntry.GetHeadword(x)\n"
        )
        with_index = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        without_index = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=None)
        self.assertEqual(
            with_index["casting_issues"], without_index["casting_issues"],
            "an un-annotated method must not change behavior vs. no api_index at all",
        )
        # And specifically: no Rule B issue on GetHeadword(x).
        self.assertNotIn("GetHeadword", _flagged(with_index))

    def test_api_index_none_changes_nothing_vs_today(self):
        """api_index=None (the default) must be byte-for-byte identical to
        calling detect_casting_needs with the old 3-arg signature."""
        result_explicit_none = detect_casting_needs(
            HEADLINE_REPRO, FAKE_CASTING_INDEX, api_index=None
        )
        result_omitted = detect_casting_needs(HEADLINE_REPRO, FAKE_CASTING_INDEX)
        self.assertEqual(result_explicit_none, result_omitted)
        # And no Rule B issue at all without an api_index.
        self.assertEqual(result_omitted["casting_issues"], [])


class TestRuleADirectReceiver(unittest.TestCase):
    """Rule A: `c.HeadWord` where `c` is a polymorphically-bound loop var.
    The property was already flagged before issue #121 (ambiguous,
    cast_interface=None); the fix is that it now resolves a usable
    cast_interface/rewrite instead of giving up.
    """

    def test_direct_attribute_access_never_proposes_a_single_cast(self):
        """Remediation for defect 3 (originally reported by the domain/
        pattern-audit review): `ISenseOrEntry` is NOT implemented by either
        `LexEntry` or `LexSense` in the real LibLCM index -- only by the
        dedicated wrapper struct `SenseOrEntry` -- so `ISenseOrEntry(c)`
        would throw for every real element. A confirmed-polymorphic
        receiver must never get cast_interface/rewrite; the ONLY correct
        remedy is a ClassName-branch dispatch, matching Rule B's own fix
        text and flexicon's GetComplexFormComponents docstring.
        """
        api_index = _FakeAPIIndex()
        code = (
            "for c in project.LexEntry.GetComplexFormComponents(entry):\n"
            "    h = c.HeadWord\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        issues = [i for i in result["casting_issues"] if i["property"] == "HeadWord"]
        self.assertTrue(issues, f"expected HeadWord to be flagged; got: {result}")
        issue = issues[0]
        self.assertIsNone(
            issue["cast_interface"],
            f"a confirmed-polymorphic receiver must never resolve a single "
            f"cast_interface (no LCM interface is safe for every branch); "
            f"got: {issue}",
        )
        self.assertIsNone(
            issue["rewrite"],
            f"no cast_interface means no single-site rewrite either; got: {issue}",
        )
        self.assertIn(
            "ClassName", issue["fix"],
            f"fix text must teach ClassName-branch dispatch instead; got: {issue}",
        )

    def test_receiver_spelling_does_not_override_proven_polymorphism(self):
        """Remediation for defect 4: renaming the loop variable from `c` to
        `sense` (which coincidentally matches `_RECEIVER_NAME_TO_INTERFACE`)
        must NOT change the answer -- proven dataflow beats spelling. Before
        the fix this resolved cast_interface="ILexSense" purely because of
        the variable's name.
        """
        api_index = _FakeAPIIndex()
        code = (
            "for sense in project.LexEntry.GetComplexFormComponents(entry):\n"
            "    g = sense.Gloss\n"
        )
        # HeadWord's defined_on doesn't include Gloss; use a property that's
        # actually declared so the flag fires through the same path.
        index = {
            "properties": {
                **FAKE_CASTING_INDEX["properties"],
                "Gloss": {
                    "defined_on": ["ILexSense", "ISenseOrEntry"],
                    "requires_cast_from": ["ICmObject"],
                },
            },
            "polymorphic_collections": {},
            "class_name_mapping": FAKE_CASTING_INDEX["class_name_mapping"],
        }
        result = detect_casting_needs(code, index, api_index=api_index)
        issues = [i for i in result["casting_issues"] if i["property"] == "Gloss"]
        self.assertTrue(issues, f"expected Gloss to be flagged; got: {result}")
        issue = issues[0]
        self.assertIsNone(
            issue["cast_interface"],
            f"variable spelling ('sense' -> ILexSense) must not override "
            f"proven polymorphism; got: {issue}",
        )
        self.assertIsNone(issue["rewrite"])


class TestNegativeControlNonPolymorphic(unittest.TestCase):
    """A loop var bound to a NON-polymorphic (confirmed concrete)
    element_type must be treated as safe for properties defined on it --
    the exact same treatment as an explicit cast alias."""

    def test_confirmed_concrete_element_type_suppresses_flag(self):
        api_index = _FakeAPIIndex(
            extra_methods=[
                {
                    "name": "GetAllConfirmedLexEntries",
                    "is_mutating": False,
                    "element_type": "ILexEntry",
                    "polymorphic": False,
                },
            ]
        )
        code = (
            "for e in project.LexEntry.GetAllConfirmedLexEntries():\n"
            "    h = e.HeadWord\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        self.assertNotIn(
            "HeadWord", _flagged(result),
            f"a confirmed non-polymorphic ILexEntry binding must satisfy "
            f"HeadWord's defined_on (['ILexEntry', 'ISenseOrEntry']), same "
            f"as an explicit cast alias would; got: {result['casting_issues']}",
        )

    def test_polymorphic_binding_is_not_accidentally_suppressed(self):
        """Sanity companion: the SAME shape but polymorphic=True must still
        flag (Rule A), proving the negative control above isn't just
        "nothing ever flags after a loop binds"."""
        api_index = _FakeAPIIndex()
        code = (
            "for c in project.LexEntry.GetComplexFormComponents(entry):\n"
            "    h = c.HeadWord\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        self.assertIn("HeadWord", _flagged(result))


class TestRemediationRoundDefects(unittest.TestCase):
    """Regression tests for the four confirmed defects raised in the
    remediation round (domain expert + pattern-audit sweep), using the
    verbatim failing inputs from that report.
    """

    def test_defect1_element_type_equal_to_expected_is_not_flagged(self):
        """`for s in project.LexEntry.GetSenses(entry): project.Senses.
        GetGloss(s)` -- GetSenses.element_type == "ILexSense" ==
        class_name_mapping["LexSense"]. Zero cast risk; Rule B must not
        fire even though the (possibly stale/overbroad) index still marks
        the method `polymorphic: True`.
        """
        api_index = _FakeAPIIndex()
        code = (
            "for s in project.LexEntry.GetSenses(entry):\n"
            "    g = project.Senses.GetGloss(s)\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        self.assertEqual(
            result["casting_issues"], [],
            f"element_type == expected_iface must never be flagged by "
            f"Rule B; got: {result['casting_issues']}",
        )

    def test_defect2_intervening_cast_is_respected(self):
        """The EXACT remedy Rule B's own fix text teaches must not itself
        get flagged: an intervening `c = ILexEntry(c)` after a ClassName
        check proves the type at the call site, overriding the (coarser)
        loop-range binding.
        """
        api_index = _FakeAPIIndex()
        code = (
            "for c in project.LexEntry.GetComplexFormComponents(entry):\n"
            "    if c.ClassName == \"LexEntry\":\n"
            "        c = ILexEntry(c)\n"
            "        project.LexEntry.GetHeadword(c)\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        self.assertEqual(
            result["casting_issues"], [],
            f"an intervening explicit cast must suppress Rule B; "
            f"got: {result['casting_issues']}",
        )

    def test_defect2_headline_repro_still_fires_without_the_cast(self):
        """Companion sanity check: remove the intervening cast and Rule B
        must still fire -- defect 2's fix must not have silently disabled
        the rule entirely."""
        api_index = _FakeAPIIndex()
        result = detect_casting_needs(
            HEADLINE_REPRO, FAKE_CASTING_INDEX, api_index=api_index
        )
        self.assertTrue(result["casting_issues"])

    def test_defect3_union_interface_never_proposed(self):
        """`ISenseOrEntry` is implemented ONLY by the dedicated wrapper
        struct `SenseOrEntry` in the real LibLCM index -- never by
        `LexEntry`/`LexSense` themselves -- so it must never be proposed as
        a cast_interface/rewrite for a confirmed-polymorphic receiver.
        """
        api_index = _FakeAPIIndex()
        code = (
            "for c in project.LexEntry.GetComplexFormComponents(entry):\n"
            "    h = c.HeadWord\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        for issue in result["casting_issues"]:
            self.assertNotEqual(issue["cast_interface"], "ISenseOrEntry", issue)
            self.assertIsNone(issue["rewrite"], issue)

    def test_defect4_variable_spelling_does_not_override_dataflow(self):
        """Renaming the loop var to `sense` (a `_RECEIVER_NAME_TO_INTERFACE`
        entry) must produce the SAME cast_interface (None) as any other
        name -- verified against both `c` and `sense` for the identical
        polymorphic binding.
        """
        api_index = _FakeAPIIndex()
        index = {
            "properties": {
                **FAKE_CASTING_INDEX["properties"],
                "Gloss": {
                    "defined_on": ["ILexSense", "ISenseOrEntry"],
                    "requires_cast_from": ["ICmObject"],
                },
            },
            "polymorphic_collections": {},
            "class_name_mapping": FAKE_CASTING_INDEX["class_name_mapping"],
        }
        code_c = (
            "for c in project.LexEntry.GetComplexFormComponents(entry):\n"
            "    g = c.Gloss\n"
        )
        code_sense = (
            "for sense in project.LexEntry.GetComplexFormComponents(entry):\n"
            "    g = sense.Gloss\n"
        )
        result_c = detect_casting_needs(code_c, index, api_index=api_index)
        result_sense = detect_casting_needs(code_sense, index, api_index=api_index)
        issue_c = next(i for i in result_c["casting_issues"] if i["property"] == "Gloss")
        issue_sense = next(i for i in result_sense["casting_issues"] if i["property"] == "Gloss")
        self.assertEqual(issue_c["cast_interface"], issue_sense["cast_interface"])
        self.assertIsNone(
            issue_sense["cast_interface"],
            f"'sense' must not resolve ILexSense purely from spelling; "
            f"got: {issue_sense}",
        )


class TestRemediationRound2Pass1FalsePositive(unittest.TestCase):
    """Regression tests for the round-2 remediation defect: pass 1
    (KNOWN_CASTING_PATTERNS) hard-blocking correct code, using the verbatim
    inputs from the report.

    Two independent causes, both covered here:
      1. Pass 1 never consulted the loop-target dataflow (only pass 2 did)
         -- now wired via `_receiver_ifaces_for`.
      2. The pattern regexes were unanchored substrings (`\\.LexemeForm`
         matched inside `.LexemeFormOA`; `entry\\s*\\.\\s*HeadWord` matched
         inside `myentry.HeadWord`) -- now anchored.
    """

    def test_verbatim_lexemeformoa_chain_not_flagged(self):
        """The exact verbatim repro from the report: `entry` is provably
        ILexEntry (GetAll's element_type, non-polymorphic) and
        LexemeFormOA IS defined on ILexEntry, so there is nothing to cast.
        """
        api_index = _FakeAPIIndex()
        code = (
            "for entry in project.LexEntry.GetAll():\n"
            "    n = entry.LexemeFormOA.MorphTypeRA.Name.Text\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX, api_index=api_index)
        self.assertEqual(
            result["casting_issues"], [],
            f"a confirmed-ILexEntry receiver's LexemeFormOA access must not "
            f"be flagged at all; got: {result['casting_issues']}",
        )

    def test_myentry_headword_not_pattern1_error_hardblocked(self):
        """`myentry.HeadWord` -- a DIFFERENT variable that merely ends in
        "entry" -- must not trip the "entry"-receiver-literal pattern.
        `myentry` is otherwise genuinely untyped, so the property access
        may still be flagged (correctly) by pass 2's generic index-driven
        loop at "warning" severity -- what must NOT happen is pass 1's
        hard "error"-severity known-pattern hit.
        """
        code = "myentry = something\nh = myentry.HeadWord\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        headword_issues = [
            i for i in result["casting_issues"] if i["property"] == "HeadWord"
        ]
        for issue in headword_issues:
            self.assertNotEqual(
                issue["severity"], "error",
                f"myentry.HeadWord must not hard-block via pass 1's "
                f"'entry'-receiver-literal pattern; got: {issue}",
            )

    def test_dataflow_suppresses_pass1_exact_literal_match(self):
        """Cause 1 in isolation: pass 1's pattern for the EXACT literal
        "LexemeForm" (no OA suffix, so anchoring alone doesn't explain a
        suppression here) must still be suppressed when the receiver's
        loop-target dataflow proves it's ILexEntry.
        """
        api_index = _FakeAPIIndex()
        index = {
            "properties": {
                **FAKE_CASTING_INDEX["properties"],
            },
            "polymorphic_collections": {},
            "class_name_mapping": FAKE_CASTING_INDEX["class_name_mapping"],
        }
        code = (
            "for entry in project.LexEntry.GetAll():\n"
            "    form = entry.LexemeForm\n"
        )
        result = detect_casting_needs(code, index, api_index=api_index)
        self.assertEqual(
            result["casting_issues"], [],
            f"pass 1 must consult the dataflow before flagging a confirmed "
            f"ILexEntry receiver; got: {result['casting_issues']}",
        )

    def test_untyped_receiver_still_hard_blocks_at_error(self):
        """Guard against over-correction: an UNRESOLVED/unknown receiver
        (no loop-target binding, no cast alias -- genuinely no
        information) must still hard-block at 'error' severity via pass 1.
        Suppression must key on a CONFIRMED receiver type, never on the
        mere absence of information.
        """
        code = "def f(entry):\n    form = entry.LexemeForm\n    return form\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        issues = [i for i in result["casting_issues"] if i["property"] == "LexemeForm"]
        self.assertTrue(issues, f"expected LexemeForm to still flag; got: {result}")
        self.assertEqual(issues[0]["severity"], "error")

    def test_headword_owner_chain_still_hard_blocks_at_error(self):
        """Guard against over-correction (companion): `.Owner.HeadWord` on
        a genuinely untyped receiver must still hard-block -- proves the
        anchoring fix didn't accidentally widen the gap on the OTHER
        HeadWord pattern too.
        """
        code = "def f(obj):\n    hw = obj.Owner.HeadWord\n    return hw\n"
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        issues = [i for i in result["casting_issues"] if i["property"] == "HeadWord"]
        self.assertTrue(issues, f"expected HeadWord to still flag; got: {result}")
        self.assertEqual(issues[0]["severity"], "error")


if __name__ == "__main__":
    unittest.main()
