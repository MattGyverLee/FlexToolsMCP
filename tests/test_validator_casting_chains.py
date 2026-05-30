#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #15: cast-alias awareness in `detect_casting_needs`.

Before Phase 1, the preflight casting validator was regex-only and didn't
talk to the AST-based `_resolve_alias_maps` helper that
`certify_script_readonly` already used. Chains like

    e = ILexEntry(entry)
    lf = e.LexemeFormOA

were flagged on the second line even though the first line's cast already
satisfied the requirement. After the fix, alias-rooted accesses are skipped
when the alias's interface is listed in the property's `defined_on` /
`available_on`. Bare access and wrong-interface casts must still flag.
"""

import unittest
from server.validators import detect_casting_needs


# Minimal stand-in casting_index for the regex-fallback path. The real index
# is produced by build_casting_index.py from the LibLCM JSON dump; we only
# need a couple of property entries to drive the lookup loop.
FAKE_CASTING_INDEX = {
    "properties": {
        "LexemeFormOA": {
            "defined_on": ["ILexEntry"],
            "requires_cast_from": ["ICmObject"],
        },
        "HeadWord": {
            "defined_on": ["ILexEntry"],
            "requires_cast_from": ["ICmObject"],
        },
    },
    "polymorphic_collections": {},
}


class TestCastAliasAwareness(unittest.TestCase):
    """Phase 1 fix: cast aliases satisfy property access on subsequent lines."""

    def _properties_flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    def test_cast_alias_satisfies_property_access(self):
        """`e = ILexEntry(x); lf = e.LexemeFormOA` should NOT flag LexemeForm.

        The cast alias `e` is known to be ILexEntry, which is the interface
        that defines LexemeFormOA. The validator must skip the flag.
        """
        code = (
            "from SIL.LCModel import ILexEntry\n"
            "def f(entry):\n"
            "    e = ILexEntry(entry)\n"
            "    lf = e.LexemeFormOA\n"
            "    return lf\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        flagged = self._properties_flagged(result)
        self.assertNotIn(
            "LexemeForm", flagged,
            f"LexemeForm should not be flagged when LHS is cast to ILexEntry; "
            f"got issues: {result['casting_issues']}"
        )
        # And the casting-index loop must not flag LexemeFormOA either.
        self.assertNotIn("LexemeFormOA", flagged)

    def test_no_cast_still_flags(self):
        """Bare `lf.LexemeFormOA` access (no cast in sight) must still flag."""
        code = (
            "def f(lf):\n"
            "    x = lf.LexemeFormOA\n"
            "    return x\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        flagged = self._properties_flagged(result)
        # KNOWN_CASTING_PATTERNS has a LexemeForm entry with pattern r"\.LexemeForm"
        # which matches .LexemeFormOA too. That flag must still fire.
        self.assertIn(
            "LexemeForm", flagged,
            f"Bare lf.LexemeFormOA must still be flagged; got: {result['casting_issues']}"
        )

    def test_wrong_interface_cast_still_flags(self):
        """Casting to the wrong interface must still flag.

        IMoForm doesn't define LexemeFormOA -- `f = IMoForm(x); f.LexemeFormOA`
        must still get caught so the user can fix the cast target. This is
        the safety guarantee that proves we're not blindly trusting any cast.
        """
        code = (
            "from SIL.LCModel import IMoForm\n"
            "def f(x):\n"
            "    morph = IMoForm(x)\n"
            "    lf = morph.LexemeFormOA\n"
            "    return lf\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        flagged = self._properties_flagged(result)
        # The KNOWN_CASTING_PATTERNS "LexemeForm" check uses available_on =
        # ["ILexEntry"] -- IMoForm is NOT a substring of that, so the flag
        # must still fire.
        self.assertIn(
            "LexemeForm", flagged,
            f"IMoForm(x).LexemeFormOA must still flag (wrong interface cast); "
            f"got: {result['casting_issues']}"
        )

    def test_chained_aliases_propagate(self):
        """`a = ILexEntry(x); b = a; lf = b.LexemeFormOA` should NOT flag.

        Chained Name rebinds must propagate the cast alias so the second-hop
        variable inherits the interface.
        """
        code = (
            "from SIL.LCModel import ILexEntry\n"
            "def f(x):\n"
            "    a = ILexEntry(x)\n"
            "    b = a\n"
            "    lf = b.LexemeFormOA\n"
            "    return lf\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        flagged = self._properties_flagged(result)
        self.assertNotIn(
            "LexemeForm", flagged,
            f"Chained cast alias b should inherit ILexEntry from a; "
            f"got issues: {result['casting_issues']}"
        )
        self.assertNotIn("LexemeFormOA", flagged)

    def test_getattr_workaround_no_longer_needed(self):
        """Regression: the literal user pattern from issue #15 must pass.

        From the issue body, the user had to fall back to gattr(gattr(...))
        because each line of the chain was getting flagged. With the alias
        fix, the natural form should pass preflight.
        """
        # Verbatim shape from the issue body's "Reproducing" section, made
        # syntactically self-contained by wrapping in a function.
        code = (
            "from flexlibs2 import LexEntryOperations\n"
            "from SIL.LCModel import ILexEntry, IMoForm\n"
            "def f(project, vws):\n"
            "    leops = LexEntryOperations(project)\n"
            "    for e in leops.GetAll():\n"
            "        lf = ILexEntry(e).LexemeFormOA\n"
            "        # second-hop access rooted at a cast alias\n"
            "        lf_typed = IMoForm(lf)\n"
            "        tss = lf_typed.Form\n"
            "    return tss\n"
        )
        result = detect_casting_needs(code, FAKE_CASTING_INDEX)
        # The first-line `ILexEntry(e).LexemeFormOA` is inline -- the regex may
        # still flag it because the alias check is line-scoped to assignments.
        # But the IMoForm(lf); lf_typed.Form chain MUST not raise a LexemeForm
        # flag -- there is no `.LexemeForm` access on lf_typed.
        flagged_lines = [
            (issue["property"], issue["line"]) for issue in result["casting_issues"]
        ]
        # No LexemeForm flag on the lf_typed.Form line.
        for prop, line in flagged_lines:
            self.assertFalse(
                prop == "LexemeForm" and line >= 7,
                f"Unexpected LexemeForm flag on line {line}: {flagged_lines}"
            )


    def test_base_interface_cast_does_not_satisfy_derived_property(self):
        """Substring-collision safety guard (domain review): a cast to a
        base interface must NOT satisfy a property defined only on a
        derived interface, even though LCM's I-prefixed naming convention
        produces 492 substring collisions (e.g. 'ICmAgent' is a substring
        of 'ICmAgentEvaluation').

        We add a fake casting pattern keyed off a property that only lives
        on a hypothetical derived interface, then cast to the BASE
        interface. The flag must still fire.
        """
        index = {
            "properties": {
                "DerivedOnlyProperty": {
                    "defined_on": ["ICmAgentEvaluation"],
                    "requires_cast_from": ["ICmObject"],
                },
            },
            "polymorphic_collections": {},
        }
        code = (
            "from SIL.LCModel import ICmAgent\n"
            "def f(x):\n"
            "    a = ICmAgent(x)\n"
            "    v = a.DerivedOnlyProperty\n"
            "    return v\n"
        )
        result = detect_casting_needs(code, index)
        flagged = self._properties_flagged(result)
        self.assertIn(
            "DerivedOnlyProperty", flagged,
            f"ICmAgent cast must NOT satisfy property defined only on "
            f"ICmAgentEvaluation (substring-collision safety guard); "
            f"got: {result['casting_issues']}"
        )


class TestTypedChainSegmentBypass(unittest.TestCase):
    """Option-1 follow-up to issue #21: when the regex's obj_var is a
    mid-chain property name (not a real variable) and the chain root is a
    typed receiver -- either a cast alias or an inline `I*(...)` call --
    the static cast already constrains the chain's type. Flagging the
    next attribute as needing-a-cast would require return-type info the
    validator doesn't track, so the false positive must be dropped.

    Captured from Seth's 2026-05-28 session: `wf.Form.BestVernacularAlternative`
    and `IWfiWordform(ana).Form.BestVernacularAlternative.Text` were both
    being rejected as needing-a-cast on `Form` / `BestVernacularAlternative`.
    """

    INDEX = {
        "properties": {
            "Form": {
                "defined_on": ["IMoForm", "IWfiWordform", "IWfiGloss"],
                "requires_cast_from": ["IAnalysis", "ICmObject"],
            },
            "BestVernacularAlternative": {
                "defined_on": ["IMultiAccessorBase"],
                "requires_cast_from": ["ITsMultiString"],
            },
        },
        "polymorphic_collections": {},
    }

    def _flagged(self, result):
        return {issue["property"] for issue in result["casting_issues"]}

    def test_inline_typed_receiver_chain_does_not_flag(self):
        """`IWfiWordform(ana).Form.BestVernacularAlternative.Text` -- no alias,
        chain rooted at an inline cast call. Must NOT flag Form or
        BestVernacularAlternative.
        """
        code = (
            "def f(ana):\n"
            "    return IWfiWordform(ana).Form.BestVernacularAlternative.Text or '?'\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("Form", flagged)
        self.assertNotIn("BestVernacularAlternative", flagged)

    def test_alias_then_chain_does_not_flag(self):
        """`wf = IWfiWordform(ana); wf.Form.BestVernacularAlternative.Text` --
        chain rooted at a cast-alias Name. Must NOT flag Form or
        BestVernacularAlternative.
        """
        code = (
            "def f(ana):\n"
            "    wf = IWfiWordform(ana)\n"
            "    return wf.Form.BestVernacularAlternative.Text or '?'\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertNotIn("Form", flagged)
        self.assertNotIn("BestVernacularAlternative", flagged)

    def test_untyped_root_still_flags(self):
        """The bypass keys off a TYPED chain root. A bare variable access like
        `mstring.BestVernacularAlternative` (no cast in sight, no typed
        receiver upstream) must still flag -- we don't know what `mstring` is,
        so removing the warning would let real bugs through. Probe the
        BestVernacularAlternative arm directly because the advanced loop's
        regex consumes `.Form.` before reaching it in a longer chain.
        """
        code = (
            "def f(mstring):\n"
            "    return mstring.BestVernacularAlternative.Text\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertIn("BestVernacularAlternative", flagged)

    def test_untyped_root_chain_still_flags_first_segment(self):
        """And `obj.Form...` from an unknown root must still flag Form --
        the bypass only suppresses MID-chain segments after a typed root,
        not the head of a chain rooted at an untyped variable.
        """
        code = (
            "def f(obj):\n"
            "    return obj.Form.BestVernacularAlternative.Text\n"
        )
        flagged = self._flagged(detect_casting_needs(code, self.INDEX))
        self.assertIn("Form", flagged)


if __name__ == "__main__":
    unittest.main()
