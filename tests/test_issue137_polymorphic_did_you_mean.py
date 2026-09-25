#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #137: runtime PolymorphicAttributeError on indexed LCM interfaces should
carry did-you-mean hints from the liblcm index, not a bare error string.

Reproduces the logged ITsString / get_WritingSystem miss (session
session_154034_auto-Claude-Swahili.log): after #135 indexed the KernelInterfaces
family, the index has real members like get_RunText and get_Properties, but
detect_unknown_attribute_error only handled FLExProject accessors and
Operations classes.
"""

import unittest


class TestIssue137IndexedInterfaceDidYouMean(unittest.TestCase):
    def test_itsstring_get_writingsystem_suggests_indexed_member(self):
        from flextoolsmcp.server import APIIndex, get_index_dir
        from flextoolsmcp.server.validators import detect_unknown_attribute_error

        api_index = APIIndex.load(get_index_dir())
        err = "'ITsString' object has no attribute 'get_WritingSystem'"
        result = detect_unknown_attribute_error(err, api_index)

        self.assertTrue(result.get("has_suggestion"), result)
        self.assertEqual(result.get("object_type"), "ITsString")
        self.assertEqual(result.get("attribute_name"), "get_WritingSystem")
        self.assertTrue(result.get("did_you_mean"))
        # difflib ranks get_Properties first at ~0.52; either is actionable.
        self.assertTrue(
            any(m.startswith("get_") for m in result["did_you_mean"]),
            result["did_you_mean"],
        )
        self.assertIn("Did you mean", result.get("suggestion", ""))

    def test_unknown_interface_still_no_suggestion(self):
        from flextoolsmcp.server.validators import detect_unknown_attribute_error

        err = "'NotARealLcmType' object has no attribute 'FooBar'"
        result = detect_unknown_attribute_error(err, api_index=None)
        self.assertFalse(result.get("has_suggestion"))


if __name__ == "__main__":
    unittest.main()
