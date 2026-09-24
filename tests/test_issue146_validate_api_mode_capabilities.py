#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #146: _validate_api_mode must probe flexicon.CAPABILITIES, not version."""

import sys
import types
import unittest
from unittest import mock

from flextoolsmcp.server.handlers import execution as execution_mod


class TestIssue146ValidateApiModeCapabilities(unittest.TestCase):
    def test_flexicon_with_version_but_no_capabilities_is_rejected(self):
        """A 4.3.x-style build must not pass just because it has __version__."""
        fake = types.ModuleType("flexicon")
        fake.__version__ = "4.3.0"
        with mock.patch.dict(sys.modules, {"flexicon": fake}):
            ok, msg = execution_mod._validate_api_mode("flexicon")
        self.assertFalse(ok)
        self.assertIn("CAPABILITIES", msg)

    def test_flexicon_with_capabilities_passes(self):
        fake = types.ModuleType("flexicon")
        fake.CAPABILITIES = frozenset({"per-operation-uow"})
        with mock.patch.dict(sys.modules, {"flexicon": fake}):
            ok, msg = execution_mod._validate_api_mode("flexicon")
        self.assertTrue(ok, msg)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
