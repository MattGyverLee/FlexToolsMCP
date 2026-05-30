#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for src/server/project_discovery.py.

Critical test: the mtime regression guard. Listing projects MUST NOT
modify .fwdata modification times -- this is the bug class fixed in
P10-Export-FLEx issue #13. If this test ever fails, an open-project
call has crept into the listing path.

These tests do not require FieldWorks to be installed: they fabricate
a fake projects directory in a tempdir and point FW_PROJECTS_DIR at it.
"""

import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.project_discovery import (  # noqa: E402
    clear_cache,
    list_projects,
    resolve_project_name,
    resolve_or_explain,
)


def _make_fake_projects(root: Path, names) -> dict:
    """Create <root>/<name>/<name>.fwdata for each name. Return mtimes."""
    mtimes = {}
    for name in names:
        proj_dir = root / name
        proj_dir.mkdir()
        fwdata = proj_dir / (name + ".fwdata")
        fwdata.write_text("<fake xml/>", encoding="utf-8")
        mtimes[name] = os.path.getmtime(fwdata)
    return mtimes


class ProjectDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.projects_root = Path(self._tmp.name)
        self._prev_env = os.environ.get("FW_PROJECTS_DIR")
        os.environ["FW_PROJECTS_DIR"] = str(self.projects_root)
        clear_cache()

    def tearDown(self):
        if self._prev_env is None:
            os.environ.pop("FW_PROJECTS_DIR", None)
        else:
            os.environ["FW_PROJECTS_DIR"] = self._prev_env
        clear_cache()
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # Safety: the critical regression guard.
    # ------------------------------------------------------------------
    def test_listing_does_not_modify_fwdata_mtimes(self):
        """The whole point: listing must not touch .fwdata mtimes."""
        names = ["Alpha", "Bravo", "Charlie", "Delta"]
        before = _make_fake_projects(self.projects_root, names)

        # Sleep briefly so any mtime write would be detectable.
        time.sleep(0.05)

        for _ in range(20):
            clear_cache()  # bypass the in-process cache between calls
            list_projects()

        for name in names:
            fwdata = self.projects_root / name / (name + ".fwdata")
            self.assertAlmostEqual(
                os.path.getmtime(fwdata),
                before[name],
                places=4,
                msg=(
                    f".fwdata mtime changed for {name!r} -- "
                    "the listing path must never open or write to project files."
                ),
            )

    # ------------------------------------------------------------------
    # list_projects: basic behavior
    # ------------------------------------------------------------------
    def test_lists_only_directories_with_matching_fwdata(self):
        _make_fake_projects(self.projects_root, ["Real1", "Real2"])
        # Ghost directory: directory without matching .fwdata. FW leaves these
        # behind after deletion; we must filter them out.
        ghost = self.projects_root / "GhostProject"
        ghost.mkdir()

        names, source = list_projects()
        self.assertEqual(names, ["Real1", "Real2"])
        self.assertEqual(source, "env")
        self.assertNotIn("GhostProject", names)

    def test_returns_sorted_names(self):
        _make_fake_projects(self.projects_root, ["zebra", "alpha", "mango"])
        names, _ = list_projects()
        self.assertEqual(names, sorted(names))

    def test_empty_projects_directory(self):
        names, source = list_projects()
        self.assertEqual(names, [])
        self.assertEqual(source, "env")

    # ------------------------------------------------------------------
    # Cache behavior
    # ------------------------------------------------------------------
    def test_cache_returns_stable_result_within_ttl(self):
        _make_fake_projects(self.projects_root, ["First"])
        first, _ = list_projects()

        # Adding a new project should NOT be visible until cache expires.
        _make_fake_projects(self.projects_root, ["Second"])
        cached, _ = list_projects()
        self.assertEqual(first, cached)

    def test_force_refresh_bypasses_cache(self):
        _make_fake_projects(self.projects_root, ["First"])
        list_projects()
        _make_fake_projects(self.projects_root, ["Second"])
        names, _ = list_projects(force_refresh=True)
        self.assertEqual(names, ["First", "Second"])

    # ------------------------------------------------------------------
    # resolve_project_name: the fuzzy contract
    # ------------------------------------------------------------------
    def test_exact_match(self):
        _make_fake_projects(self.projects_root, ["Ejagham Mini - Kathie-test"])
        result = resolve_project_name("Ejagham Mini - Kathie-test")
        self.assertEqual(result.reason, "exact")
        self.assertEqual(result.resolved, "Ejagham Mini - Kathie-test")
        self.assertEqual(result.suggestions, [])

    def test_case_only_difference_autocorrects(self):
        _make_fake_projects(self.projects_root, ["Ejagham Mini - Kathie-test"])
        result = resolve_project_name("ejagham mini - kathie-test")
        self.assertEqual(result.reason, "normalized")
        self.assertEqual(result.resolved, "Ejagham Mini - Kathie-test")

    def test_whitespace_difference_autocorrects(self):
        _make_fake_projects(self.projects_root, ["Ejagham Mini - Kathie-test"])
        result = resolve_project_name("EjaghamMini-Kathie-test")
        self.assertEqual(result.reason, "normalized")
        self.assertEqual(result.resolved, "Ejagham Mini - Kathie-test")

    def test_case_and_whitespace_together_autocorrect(self):
        _make_fake_projects(self.projects_root, ["Ejagham Mini - Kathie-test"])
        result = resolve_project_name("  ejagham mini  -  kathie-test  ")
        self.assertEqual(result.reason, "normalized")
        self.assertEqual(result.resolved, "Ejagham Mini - Kathie-test")

    def test_no_match_returns_suggestions(self):
        _make_fake_projects(self.projects_root, [
            "Ejagham Mini - Kathie-test",
            "Ejagham Main",
            "Bafut",
        ])
        result = resolve_project_name("EjaghamX")
        self.assertEqual(result.reason, "no_match")
        self.assertIsNone(result.resolved)
        # Both Ejagham* projects should appear; Bafut should not.
        self.assertTrue(any("Ejagham" in s for s in result.suggestions))

    def test_no_match_with_no_close_options_returns_empty_suggestions(self):
        _make_fake_projects(self.projects_root, ["Alpha", "Bravo"])
        result = resolve_project_name("ZetaQuadrant")
        self.assertEqual(result.reason, "no_match")
        self.assertEqual(result.suggestions, [])

    def test_empty_request(self):
        result = resolve_project_name("")
        self.assertEqual(result.reason, "empty")
        self.assertIsNone(result.resolved)

    def test_passthrough_when_discovery_unavailable(self):
        # When the discovery layer returns nothing (no Windows / no FW /
        # registry blocked / etc.) we permissively pass the name through
        # rather than block the user. The runner will surface its own
        # error if the project truly does not exist.
        from unittest.mock import patch
        with patch(
            "server.project_discovery.list_projects",
            return_value=([], "unavailable"),
        ):
            clear_cache()
            result = resolve_project_name("WhateverProject")
            self.assertEqual(result.reason, "exact")
            self.assertEqual(result.resolved, "WhateverProject")

    # ------------------------------------------------------------------
    # resolve_or_explain: handler-facing wrapper
    # ------------------------------------------------------------------
    def test_resolve_or_explain_returns_name_on_match(self):
        _make_fake_projects(self.projects_root, ["MyProject"])
        resolved, err = resolve_or_explain("MyProject")
        self.assertEqual(resolved, "MyProject")
        self.assertIsNone(err)

    def test_resolve_or_explain_autocorrects_minor_diff(self):
        _make_fake_projects(self.projects_root, ["MyProject"])
        resolved, err = resolve_or_explain("myproject")
        self.assertEqual(resolved, "MyProject")
        self.assertIsNone(err)

    def test_resolve_or_explain_returns_error_payload_on_miss(self):
        _make_fake_projects(self.projects_root, ["Alpha", "Bravo"])
        resolved, err = resolve_or_explain("CompletelyDifferent")
        self.assertIsNone(resolved)
        self.assertIsNotNone(err)
        assert err is not None  # for type-checker narrowing
        self.assertEqual(err["error_code"], "project_not_found")
        self.assertIn("suggestions", err)
        self.assertIn("hint", err)

    def test_resolve_or_explain_empty_input_returns_pair_of_nones(self):
        resolved, err = resolve_or_explain("")
        self.assertIsNone(resolved)
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
