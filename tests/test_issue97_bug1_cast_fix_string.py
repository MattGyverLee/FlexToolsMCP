#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #97 Bug 1 (Swahili audit CP-D / D-1).

`detect_casting_needs`'s casting_issues loop used to build the human-facing
`fix` string with an unconditional `defined_on[0]` pick

    "fix": f"Cast {obj_var} to {casting_info.get('defined_on', ['concrete type'])[0]}"

completely independent of `cast_interface` (which is computed via the
deliberately-conservative `_pick_cast_interface`, and returns None on
genuine ambiguity by design -- see the Dennis cascade-failure rationale at
validators.py:3324-3337). The result: a payload could say
`cast_interface: None` while `fix` confidently named a single (frequently
wrong) interface, e.g. "Cast x to ILexEtymology" for a `Gloss` access that
is actually ambiguous between ILexEtymology / ILexSense / ISenseOrEntry.

These tests drive `detect_casting_needs` against the REAL shipped LibLCM
v11.0.0 casting index (not a synthetic fixture) so the invariant sweep
would catch a regression anywhere in the property map, not just at the
four confirmed-wrong pairings.
"""

import json
import re
import unittest
from pathlib import Path

from server.validators import detect_casting_needs, _pick_cast_interface

CASTING_INDEX_PATH = (
    Path(__file__).parent.parent
    / "src" / "flextoolsmcp" / "index" / "casting_index_liblcm-v11.0.0.json"
)

# A `fix` string counts as "confidently naming a single concrete interface"
# if it is exactly "Cast <receiver> to <ILibLcmInterface>" with nothing else
# hedging it. The ambiguous-candidates message ("... to one of: A, B, C --
# ambiguous, call flextools_resolve_property...") and the no-candidate
# degrade ("... to concrete type") must NOT match this.
_CONFIDENT_SINGLE_INTERFACE_FIX = re.compile(r"^Cast \S+ to (I[A-Za-z0-9_]+)$")


def _load_casting_index():
    if not CASTING_INDEX_PATH.exists():
        return None
    with open(CASTING_INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestAmbiguousFixNeverConfidentlyWrong(unittest.TestCase):
    """(a) THE INVARIANT: cast_interface is None => fix never names a
    single concrete interface as the definite target. Swept broadly
    across the real index, not just the four confirmed pairings."""

    @classmethod
    def setUpClass(cls):
        cls.casting_index = _load_casting_index()
        if cls.casting_index is None:
            return
        props = cls.casting_index.get("properties", {})
        # Sweep every property that (a) requires a cast and (b) is genuinely
        # ambiguous under a generic, unrecognized receiver name (no
        # _RECEIVER_NAME_TO_INTERFACE tie-break available).
        cls.ambiguous_props = []
        for name, info in props.items():
            defined_on = info.get("defined_on", [])
            if not info.get("requires_cast_from"):
                continue
            resolved = _pick_cast_interface(
                name, defined_on, cls.casting_index, receiver_name="unrecognized_receiver_zz"
            )
            i_prefixed = [d for d in defined_on if isinstance(d, str) and d.startswith("I")]
            if resolved is None and len(i_prefixed) > 1:
                cls.ambiguous_props.append(name)

    def test_shipped_index_has_broad_ambiguous_coverage(self):
        if self.casting_index is None:
            self.skipTest("shipped casting_index_liblcm-v11.0.0.json not found")
        # Sanity: the sweep set must be broad, not one or two cherry-picked
        # properties, or a regression elsewhere in the map could slip past.
        self.assertGreaterEqual(
            len(self.ambiguous_props), 50,
            f"Expected a broad ambiguous-property sweep, got {len(self.ambiguous_props)}",
        )

    def test_ambiguous_fix_never_names_definite_interface(self):
        if self.casting_index is None:
            self.skipTest("shipped casting_index_liblcm-v11.0.0.json not found")
        receiver = "unrecognized_receiver_zz"
        code = "\n".join(f"{receiver}.{name}" for name in self.ambiguous_props)
        result = detect_casting_needs(code, self.casting_index)
        issues_by_prop = {i["property"]: i for i in result["casting_issues"]}

        checked = 0
        for name in self.ambiguous_props:
            issue = issues_by_prop.get(name)
            if issue is None:
                # Some properties are filtered upstream (e.g. always-safe
                # members, conditional-safe members) before reaching the
                # fix-string logic -- not relevant to this invariant.
                continue
            if issue.get("cast_interface") is not None:
                # Receiver-name coincidence resolved it after all; not an
                # ambiguous case for this sweep.
                continue
            checked += 1
            fix = issue.get("fix", "")
            match = _CONFIDENT_SINGLE_INTERFACE_FIX.match(fix)
            self.assertIsNone(
                match,
                f"Property {name!r}: cast_interface is None but fix "
                f"confidently names {match.group(1) if match else '?'!r}: {fix!r}",
            )

        self.assertGreaterEqual(
            checked, 50,
            f"Expected to actually check a broad set of ambiguous issues, got {checked}",
        )


class TestResolvedFixAgreesWithCastInterface(unittest.TestCase):
    """(b) POSITIVE: a resolved case (cast_interface non-None) still yields
    "Cast x to <that same interface>" -- fix and cast_interface agree."""

    @classmethod
    def setUpClass(cls):
        cls.casting_index = _load_casting_index()

    def test_single_candidate_property_resolves_and_agrees(self):
        if self.casting_index is None:
            self.skipTest("shipped casting_index_liblcm-v11.0.0.json not found")
        code = "x = obj.AMPLEStringSegment\n"
        result = detect_casting_needs(code, self.casting_index)
        issues = [i for i in result["casting_issues"] if i["property"] == "AMPLEStringSegment"]
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["cast_interface"], "IPhEnvironment")
        self.assertEqual(issue["fix"], "Cast obj to IPhEnvironment")

    def test_receiver_name_tiebreak_resolves_and_agrees(self):
        if self.casting_index is None:
            self.skipTest("shipped casting_index_liblcm-v11.0.0.json not found")
        # Gloss is ambiguous (ILexEtymology/ILexSense/ISenseOrEntry) under a
        # generic receiver, but `sense` is a recognized tie-break name that
        # resolves it to ILexSense.
        code = "g = sense.Gloss\n"
        result = detect_casting_needs(code, self.casting_index)
        issues = [i for i in result["casting_issues"] if i["property"] == "Gloss"]
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["cast_interface"], "ILexSense")
        self.assertEqual(issue["fix"], "Cast sense to ILexSense")


class TestConfirmedWrongPairingsNoLongerConfident(unittest.TestCase):
    """(c) REPRO: two of the four confirmed wrong pairings from the live
    audit no longer confidently name the wrong interface.

    - Gloss: old bug said "Cast x to ILexEtymology" (defined_on[0]) for a
      receiver where cast_interface is actually None (ambiguous between
      ILexEtymology / ILexSense / ISenseOrEntry) -- reproduces the
      IWfiGloss -> ILexEtymology pairing.
    - Name: old bug said "Cast x to ICmAgent" (defined_on[0]) -- reproduces
      the ICmAgent mispairing (e.g. the reported "morph type -> ICmAgent").

    The other two reported pairings (IMoMorphSynAnalysis -> IMoDerivStepMsa,
    IFsClosedValue.FeatureRA -> ICmAgent) are not reproduced here: FeatureRA
    in the shipped v11.0.0 index resolves to
    ['IFsFeatureSpecification', 'IPhFeatureConstraint'], not ICmAgent, so
    that exact pairing is not present in this index snapshot to reproduce
    against; MSA-family properties are covered generically by the broad
    sweep in TestAmbiguousFixNeverConfidentlyWrong instead.
    """

    @classmethod
    def setUpClass(cls):
        cls.casting_index = _load_casting_index()

    def test_gloss_no_longer_confidently_says_ilexetymology(self):
        if self.casting_index is None:
            self.skipTest("shipped casting_index_liblcm-v11.0.0.json not found")
        code = "g = wfi_gloss.Gloss\n"
        result = detect_casting_needs(code, self.casting_index)
        issues = [i for i in result["casting_issues"] if i["property"] == "Gloss"]
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertIsNone(issue["cast_interface"])
        self.assertNotEqual(issue["fix"], "Cast wfi_gloss to ILexEtymology")
        self.assertIsNone(_CONFIDENT_SINGLE_INTERFACE_FIX.match(issue["fix"]))

    def test_name_no_longer_confidently_says_icmagent(self):
        if self.casting_index is None:
            self.skipTest("shipped casting_index_liblcm-v11.0.0.json not found")
        code = "n = morph_type.Name\n"
        result = detect_casting_needs(code, self.casting_index)
        issues = [i for i in result["casting_issues"] if i["property"] == "Name"]
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertIsNone(issue["cast_interface"])
        self.assertNotEqual(issue["fix"], "Cast morph_type to ICmAgent")
        self.assertIsNone(_CONFIDENT_SINGLE_INTERFACE_FIX.match(issue["fix"]))


if __name__ == "__main__":
    unittest.main()
