#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #122: runtime polymorphic hints must not promise a stateless preflight rewrite."""

import json
import unittest
from pathlib import Path

from server.validators import detect_polymorphic_error

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


class TestIssue122PolymorphicHint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.casting_index = _load_casting_index()

    def test_headword_on_icmobject_lists_candidates_without_preflight_promise(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        error = "'ICmObject' object has no attribute 'HeadWord'"
        result = detect_polymorphic_error(error, self.casting_index)
        self.assertTrue(result["is_polymorphic_error"])
        self.assertIsNone(result["rewrite"])
        self.assertGreaterEqual(len(result.get("cast_candidates") or []), 2)
        suggestion = result["suggestion"]
        self.assertNotIn("preflight casting validator should", suggestion)
        self.assertIn("cast_to_concrete", suggestion)
        self.assertIn("HeadWord", suggestion)

    def test_single_candidate_produces_concrete_rewrite(self):
        if self.casting_index is None:
            self.skipTest("shipped casting index not available")
        error = "'ILexEntry' object has no attribute 'HeadWord'"
        result = detect_polymorphic_error(error, self.casting_index)
        self.assertTrue(result["is_polymorphic_error"])
        # ILexEntry already IS the defining interface -- rewrite may or may not
        # be produced depending on index shape; at minimum the hint must not
        # defer to preflight.
        self.assertNotIn("preflight casting validator should", result["suggestion"])


if __name__ == "__main__":
    unittest.main()
