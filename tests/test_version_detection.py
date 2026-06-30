#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #38 root cause: library version detection must honor a live
module `version` attribute (flexlibs2's convention) before falling back to
potentially-stale importlib.metadata.

For path / editable installs -- the common dev setup -- pip metadata goes
stale while the source on sys.path is the version actually in use. Detecting
the wrong version made the server load a mismatched index (3.0.0) even though
flexlibs2 4.0.1 was on the path, which re-surfaced the #38 false-rejections.
"""

import sys
import types
import unittest

from server.versioning import detect_installed_library_version


class TestVersionDetection(unittest.TestCase):
    def _install_fake_module(self, name, **attrs):
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod
        self.addCleanup(lambda: sys.modules.pop(name, None))
        return mod

    def test_prefers_dunder_version(self):
        self._install_fake_module("fake_lib_dunder", __version__="9.9.9")
        self.assertEqual(
            detect_installed_library_version(
                "Fake", import_path="fake_lib_dunder", package_name="fake_lib_dunder"
            ),
            "9.9.9",
        )

    def test_honors_plain_version_attribute(self):
        # flexlibs2 exposes `version`, not `__version__`. This must be detected
        # rather than falling through to importlib.metadata.
        self._install_fake_module("fake_lib_plain", version="4.0.1")
        self.assertEqual(
            detect_installed_library_version(
                "Fake", import_path="fake_lib_plain", package_name="fake_lib_plain"
            ),
            "4.0.1",
        )

    def test_live_attribute_beats_stale_metadata(self):
        # Even if importlib.metadata would resolve a (stale) version, the live
        # module attribute wins.
        self._install_fake_module("fake_lib_live", version="4.0.1")
        result = detect_installed_library_version(
            "Fake", import_path="fake_lib_live", package_name="fake_lib_live"
        )
        self.assertEqual(result, "4.0.1")

    def test_ignores_non_string_version(self):
        # A module exposing version as a tuple/int must not be returned raw.
        self._install_fake_module("fake_lib_tuple", version=(4, 0, 1))
        result = detect_installed_library_version(
            "Fake", import_path="fake_lib_tuple", package_name="fake_lib_tuple"
        )
        # Falls through to metadata (absent) -> None for this fake package.
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
