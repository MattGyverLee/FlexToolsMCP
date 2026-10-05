#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #316: casting hint must not suggest an unrelated interface.

Regression of #97 ("wrong cast interface suggested"): the runtime hint for
`'IMoStemMsa' object has no attribute 'ProdRestrictOA'` emitted
`rewrite: IMoMorphData(stem).ProdRestrictOA`. ProdRestrictOA lives on the
project-level morph data (IMoMorphData), not on a stem MSA -- following the
hint raises at runtime. The rewrite must be suppressed when the receiver's
known interface is not a base/sibling of the owner interface, and the
same-stem property that IS on the receiver (ProdRestrictRC) must be offered
as a did-you-mean alternative. Legitimate casts (downcast, identity,
sibling, upcast) and unknown receivers must keep working.
"""

import json
import unittest
from pathlib import Path

from server.validators import (
    _cast_owner_related_to_receiver,
    _did_you_mean_property,
    _pick_cast_interface,
    detect_casting_needs,
    detect_polymorphic_error,
)

_CASTING_INDEX_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "flextoolsmcp"
    / "index"
    / "casting_index_liblcm-v11.0.0.json"
)


def _load_casting_index():
    if not _CASTING_INDEX_PATH.is_file():
        return None
    with _CASTING_INDEX_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


class TestIssue316UnrelatedInterfaceRewrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.casting_index = _load_casting_index()

    def test_shipped_index_carries_interface_ancestors(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        ancestors = self.casting_index.get("interface_ancestors")
        self.assertIsInstance(ancestors, dict)
        self.assertIn("IMoMorphSynAnalysis", ancestors["IMoStemMsa"])
        self.assertNotIn("IMoMorphData", ancestors["IMoStemMsa"])

    def test_unrelated_owner_rewrite_suppressed(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        result = detect_polymorphic_error(
            "'IMoStemMsa' object has no attribute 'ProdRestrictOA'",
            self.casting_index,
        )
        self.assertTrue(result["is_polymorphic_error"])
        self.assertIsNone(result["rewrite"])
        self.assertNotIn("IMoMorphData(stem)", result["suggestion"])

    def test_did_you_mean_offers_prod_restrict_rc(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        result = detect_polymorphic_error(
            "'IMoStemMsa' object has no attribute 'ProdRestrictOA'",
            self.casting_index,
        )
        self.assertIn("Did you mean 'ProdRestrictRC'?", result["suggestion"])
        self.assertIn("IMoStemMsa", result["suggestion"])

    def test_pick_suppresses_unrelated_single_candidate(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        self.assertIsNone(
            _pick_cast_interface(
                "ProdRestrictOA",
                ["IMoMorphData"],
                self.casting_index,
                receiver_interfaces={"IMoStemMsa"},
            )
        )

    def test_pick_keeps_downcast(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        # Receiver is a base of the owner: the classic legitimate cast.
        self.assertEqual(
            "IMoStemMsa",
            _pick_cast_interface(
                "SomeProp",
                ["IMoStemMsa"],
                self.casting_index,
                receiver_interfaces={"IMoMorphSynAnalysis"},
            ),
        )

    def test_pick_keeps_identity_and_sibling_and_upcast(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        self.assertEqual(
            "IMoStemMsa",
            _pick_cast_interface(
                "SomeProp",
                ["IMoStemMsa"],
                self.casting_index,
                receiver_interfaces={"IMoStemMsa"},
            ),
        )
        # Siblings under IMoMorphSynAnalysis stay allowed (issue wording).
        self.assertEqual(
            "IMoDerivStepMsa",
            _pick_cast_interface(
                "SomeProp",
                ["IMoDerivStepMsa"],
                self.casting_index,
                receiver_interfaces={"IMoStemMsa"},
            ),
        )
        # Upcast to a base interface always succeeds at runtime.
        self.assertEqual(
            "IMoMorphSynAnalysis",
            _pick_cast_interface(
                "SomeProp",
                ["IMoMorphSynAnalysis"],
                self.casting_index,
                receiver_interfaces={"IMoStemMsa"},
            ),
        )

    def test_pick_fails_open_for_unknown_receiver(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        # Never suppress on absence of information: unknown names and a
        # missing receiver_interfaces argument keep legacy behavior.
        self.assertEqual(
            "IMoMorphData",
            _pick_cast_interface(
                "SomeProp",
                ["IMoMorphData"],
                self.casting_index,
                receiver_interfaces={"IFooUnknown"},
            ),
        )
        self.assertEqual(
            "IMoMorphData",
            _pick_cast_interface("SomeProp", ["IMoMorphData"], self.casting_index),
        )

    def test_relatedness_helper_spot_checks(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        idx = self.casting_index
        self.assertFalse(
            _cast_owner_related_to_receiver("IMoMorphData", {"IMoStemMsa"}, idx)
        )
        self.assertTrue(
            _cast_owner_related_to_receiver("IMoStemMsa", {"IMoMorphSynAnalysis"}, idx)
        )
        self.assertTrue(
            _cast_owner_related_to_receiver("IMoStemMsa", {"IMoStemMsa"}, idx)
        )

    def test_did_you_mean_helper(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        self.assertEqual(
            "ProdRestrictRC",
            _did_you_mean_property("ProdRestrictOA", "IMoStemMsa", self.casting_index),
        )
        # No cardinality suffix to swap -> no suggestion.
        self.assertIsNone(
            _did_you_mean_property("HeadWord", "ILexEntry", self.casting_index)
        )
        # Receiver without the property -> no suggestion.
        self.assertIsNone(
            _did_you_mean_property(
                "ProdRestrictOA", "ILexEntry", self.casting_index
            )
        )

    def test_preflight_suppresses_rewrite_for_proven_unrelated_receiver(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        code = (
            "from SIL.LCModel import IMoStemMsa\n"
            "stem = IMoStemMsa(entry)\n"
            "x = stem.ProdRestrictOA\n"
            "print(x)\n"
        )
        result = detect_casting_needs(code, self.casting_index)
        hits = [
            i
            for i in (result.get("casting_issues") or [])
            if i.get("property") == "ProdRestrictOA"
        ]
        self.assertTrue(hits, "preflight should still flag the access")
        for hit in hits:
            self.assertIsNone(hit.get("rewrite"))
            self.assertIsNone(hit.get("cast_interface"))

    def test_preflight_keeps_rewrite_for_unknown_receiver(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        code = "x = foo.ProdRestrictOA\n"
        result = detect_casting_needs(code, self.casting_index)
        hits = [
            i
            for i in (result.get("casting_issues") or [])
            if i.get("property") == "ProdRestrictOA"
        ]
        self.assertTrue(hits, "preflight should still flag the access")
        self.assertTrue(
            any(h.get("rewrite") for h in hits),
            "unknown receiver must fail open and keep the legacy rewrite",
        )


if __name__ == "__main__":
    unittest.main()
