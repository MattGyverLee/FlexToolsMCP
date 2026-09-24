#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #108 (a): redundant ``project.project.Cache`` hop on LcmCache."""

import unittest

from server.validators import detect_casting_needs, detect_polymorphic_error


class TestIssue108RedundantCacheHopRuntime(unittest.TestCase):
    def test_lcmcache_cache_error_emits_strip_rewrite(self):
        error = "'LcmCache' object has no attribute 'Cache'"
        result = detect_polymorphic_error(error)
        self.assertTrue(result["is_polymorphic_error"])
        self.assertEqual(result["object_type"], "LcmCache")
        self.assertEqual(result["property_name"], "Cache")
        self.assertEqual(result["rewrite"], "project.project")
        self.assertIn("redundant", result["suggestion"].lower())
        self.assertNotIn("preflight casting validator should", result["suggestion"])


class TestIssue108RedundantCacheHopPreflight(unittest.TestCase):
    def test_project_project_cache_langproject_rewrite(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    lp = project.project.Cache.LangProject\n"
        )
        result = detect_casting_needs(code, casting_index={})
        self.assertTrue(result["has_casting_issues"])
        hop_issues = [
            i for i in result["casting_issues"] if i.get("kind") == "redundant_lcm_cache_hop"
        ]
        self.assertEqual(len(hop_issues), 1)
        issue = hop_issues[0]
        self.assertEqual(issue["rewrite"], "project.project.LangProject")
        self.assertIn("project.project.Cache.LangProject", issue["found_at"])

    def test_valid_project_cache_unchanged(self):
        """``project.Cache`` (flexicon escape hatch) must not be flagged."""
        code = "def Main(project, report, modifyAllowed):\n    c = project.Cache\n"
        result = detect_casting_needs(code, casting_index={})
        hop_issues = [
            i for i in result["casting_issues"] if i.get("kind") == "redundant_lcm_cache_hop"
        ]
        self.assertEqual(hop_issues, [])


if __name__ == "__main__":
    unittest.main()
