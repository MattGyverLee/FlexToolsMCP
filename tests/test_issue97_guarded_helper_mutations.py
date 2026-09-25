#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #97 (minor): mutations inside guarded helper calls.

When a module-level helper is invoked only from ``if modifyAllowed:`` in
``Main``, writes inside the helper must not be classified as unprotected.
"""

import unittest

from flextoolsmcp.server import APIIndex
from flextoolsmcp.server.kernel import get_index_dir
from flextoolsmcp.server.validators import certify_script_readonly


class TestIssue97GuardedHelperMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_index = APIIndex.load(get_index_dir())

    def _certify(self, code: str):
        return certify_script_readonly(code, self.api_index)

    def test_helper_called_only_from_guard_is_protected(self):
        code = """
def apply_gloss(project, sense):
    project.Senses.SetGloss(sense, "probe")

def Main(project, report, modifyAllowed):
    if modifyAllowed:
        apply_gloss(project, sense)
"""
        cert = self._certify(code)
        self.assertTrue(
            cert["is_certified_readonly"],
            msg=f"expected guarded helper to certify readonly; got {cert}",
        )
        mutating = [m for m in cert.get("mutating_calls", []) if m.get("is_mutating")]
        self.assertEqual(mutating, [])
        self.assertGreaterEqual(len(cert.get("protected_calls") or []), 1)

    def test_mixed_guarded_and_unguarded_helper_calls_stay_unprotected(self):
        code = """
def apply_gloss(project, sense):
    project.Senses.SetGloss(sense, "probe")

def Main(project, report, modifyAllowed):
    if modifyAllowed:
        apply_gloss(project, sense)
    apply_gloss(project, sense)
"""
        cert = self._certify(code)
        self.assertFalse(cert["is_certified_readonly"])
        mutating = [m for m in cert.get("mutating_calls", []) if m.get("is_mutating")]
        self.assertGreaterEqual(len(mutating), 1)

    def test_helper_chain_inherits_protection(self):
        code = """
def inner_write(project, sense):
    project.Senses.SetGloss(sense, "probe")

def outer_write(project, sense):
    inner_write(project, sense)

def Main(project, report, modifyAllowed):
    if modifyAllowed:
        outer_write(project, sense)
"""
        cert = self._certify(code)
        self.assertTrue(cert["is_certified_readonly"])


if __name__ == "__main__":
    unittest.main()
