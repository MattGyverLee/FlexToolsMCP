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


# ---------------------------------------------------------------------------
# Handler-level adoption tests (issues #168 / #169 / #170).
#
# These exercise the three call sites Task 1 changed (execution.py,
# grammar_health.py, parse.py's _resolve_project) through the real handlers,
# not the bare `resolve_project_name`/`resolve_or_explain` unit above.
#
# LATENT TRAP (do not re-break): execution.py, grammar_health.py and
# parse.py all import `resolve_or_explain` INSIDE the function that uses it
# (`from ..project_discovery import resolve_or_explain`), so patching the
# attribute on the *handler* module (e.g. `exec_mod.resolve_or_explain`) is a
# no-op -- the fresh import re-reads the name from the project_discovery
# module object every call. The `exact_resolver` fixture below patches
# `flextoolsmcp.server.project_discovery.resolve_or_explain` directly, which
# *is* consulted, matching the pattern already used by ~12 other test files.
# admin.py is the one handler that imports it at module scope; not relevant
# here since admin.py's guard is out of scope for #168 (see admin.py:507).
# ---------------------------------------------------------------------------

import asyncio
import json as _json
import logging as _logging

import pytest as _pytest

import flextoolsmcp.server.handlers.admin as _admin_mod
import flextoolsmcp.server.handlers.execution as _exec_mod
import flextoolsmcp.server.handlers.grammar_health as _gh_mod
import flextoolsmcp.server.handlers.parse as _parse_mod
import flextoolsmcp.server.project_discovery as _pd_mod
from flextoolsmcp.server.session import SessionState as _SessionState

# A syntax error is the cheapest way to reach the end of the project-
# resolution block (which runs unconditionally, before any subprocess/live
# FieldWorks touch) without needing a real project on disk -- the same trick
# tests/test_issue10_session_persistence.py uses.
_BROKEN_CODE = "def Main(project, report, modifyAllowed:\n    pass"


def _ensure_kernel_ready():
    from flextoolsmcp.server.kernel import initialize_kernel, set_api_index, get_index_dir
    from flextoolsmcp.server import APIIndex
    initialize_kernel()
    set_api_index(APIIndex.load(get_index_dir()))


@_pytest.fixture
def isolated_session():
    """Save/restore the process-wide session_state singleton (mirrors
    test_issue10_session_persistence.py's own fixture) so these adoption
    tests don't leak project/api_mode/write_enabled state into other test
    files sharing the same pytest run."""
    _ensure_kernel_ready()
    saved = _exec_mod.session_state
    saved.__dict__.clear()
    saved.__dict__.update(_SessionState().__dict__)
    try:
        yield saved
    finally:
        saved.__dict__.clear()
        saved.__dict__.update(_SessionState().__dict__)


@_pytest.fixture
def exact_resolver(monkeypatch):
    """Force every project name through resolve_or_explain's 'exact' branch.

    Patched in two places: `project_discovery` itself (consulted by
    execution.py/grammar_health.py/parse.py, which import it function-locally
    on every call -- see the LATENT TRAP note above) AND `admin.py`'s own
    module attribute (admin.py binds its own name at import time, so a patch
    on `project_discovery` alone is a no-op for flextools_start)."""
    _passthrough = lambda name: (name, None)
    monkeypatch.setattr(_pd_mod, "resolve_or_explain", _passthrough)
    monkeypatch.setattr(_admin_mod, "resolve_or_explain", _passthrough)


async def _run_module(**kwargs):
    return await _exec_mod.handle_run_module(dict(kwargs))


class TestExactNameAdoptionPerHandler:
    """#168 item 5.1: exact-name resolution adopts into the session at each
    of the three Task 1 sites; a bare follow-up call must not re-raise
    project_name_required."""

    def test_run_module_adopts_and_a_bare_followup_reuses_it(
        self, isolated_session, exact_resolver
    ):
        first = asyncio.run(_run_module(code=_BROKEN_CODE, project_name="ProjA"))
        first_data = _json.loads(first[0].text)
        assert first_data.get("error_code") == "syntax_error"
        assert _exec_mod.session_state.project_name == "ProjA"

        second = asyncio.run(_run_module(code=_BROKEN_CODE))
        second_data = _json.loads(second[0].text)
        assert second_data.get("error_code") != "project_name_required"

    def test_grammar_health_adopts_and_a_bare_followup_reuses_it(
        self, isolated_session, exact_resolver, monkeypatch
    ):
        async def _fake_scan(**_kwargs):
            return {
                "success": True,
                "findings": {"checks_run": [], "checks_skipped": [], "findings": []},
            }

        monkeypatch.setattr(_exec_mod, "run_scan_module", _fake_scan)

        first = asyncio.run(
            _gh_mod.handle_flextools_grammar_health({"project_name": "ProjB"})
        )
        first_data = _json.loads(first[0].text)
        assert first_data.get("status") == "ok"
        assert _exec_mod.session_state.project_name == "ProjB"

        second = asyncio.run(_gh_mod.handle_flextools_grammar_health({}))
        second_data = _json.loads(second[0].text)
        assert second_data.get("error_code") != "project_name_required"

    def test_try_word_resolver_adopts_and_a_bare_followup_reuses_it(
        self, isolated_session, exact_resolver
    ):
        # Task 1 site 3 lives in `_resolve_project`, the shared helper
        # `handle_flextools_try_word` calls before ever touching ParseRunner
        # or the worker channel; exercised directly here to avoid
        # duplicating the RecordingWorker/Pool doubles already committed in
        # tests/test_try_word_handler.py (a dirty file this task must not
        # touch).
        name, err = _parse_mod._resolve_project("ProjC")
        assert err is None
        assert name == "ProjC"
        assert _exec_mod.session_state.project_name == "ProjC"

        name2, err2 = _parse_mod._resolve_project(None)
        assert err2 is None
        assert name2 == "ProjC"


class TestIssue169ColdStartThenAdopt:
    """#169: no new flag. An empty flextools_start() followed by
    run_module(project_name=X) must adopt X, and a bare run_module()
    afterward must target X -- with no cold_adopt_consumed flag involved."""

    def test_empty_start_then_run_module_with_project_then_bare_run_module(
        self, isolated_session, exact_resolver
    ):
        asyncio.run(_admin_mod.handle_start({}))
        assert _exec_mod.session_state.project_name == ""

        asyncio.run(_run_module(code=_BROKEN_CODE, project_name="ProjD"))
        assert _exec_mod.session_state.project_name == "ProjD"

        second = asyncio.run(_run_module(code=_BROKEN_CODE))
        second_data = _json.loads(second[0].text)
        assert second_data.get("error_code") != "project_name_required"
        assert _exec_mod.session_state.project_name == "ProjD"


class TestNoStompRegression:
    """Mandatory regression (this is the test that would fail under the
    REJECTED cold_adopt_consumed-flag design): adopting a project through
    run_module must never re-enter the cold-start branch and must never
    stomp an explicit api_mode or downgrade an inherited write_enabled."""

    def test_adopted_project_does_not_reset_api_mode_or_write_enabled(
        self, isolated_session, exact_resolver
    ):
        asyncio.run(
            _admin_mod.handle_start({"api_mode": "liblcm", "write_enabled": True})
        )
        assert _exec_mod.session_state.api_mode == "liblcm"
        assert _exec_mod.session_state.write_enabled is True

        asyncio.run(_run_module(code=_BROKEN_CODE, project_name="ProjE"))

        assert _exec_mod.session_state.api_mode == "liblcm"
        assert _exec_mod.session_state.write_enabled is True
        assert _exec_mod.session_state.project_name == "ProjE"


class TestProjectAdoptedLogging:
    """Task 3: [PROJECT-ADOPTED] fires on a genuine A->B change and does
    NOT fire on the first adopt from an empty session project."""

    def test_fires_on_a_genuine_change(self, isolated_session, exact_resolver, caplog):
        asyncio.run(_admin_mod.handle_start({"project_name": "ProjF"}))
        assert _exec_mod.session_state.project_name == "ProjF"

        with caplog.at_level(_logging.INFO):
            asyncio.run(_run_module(code=_BROKEN_CODE, project_name="ProjG"))

        assert any(
            "[PROJECT-ADOPTED]" in r.message
            and "ProjF" in r.message
            and "ProjG" in r.message
            for r in caplog.records
        )

    def test_does_not_fire_on_first_adopt_from_empty_session(
        self, isolated_session, exact_resolver, caplog
    ):
        asyncio.run(_admin_mod.handle_start({}))
        assert _exec_mod.session_state.project_name == ""

        with caplog.at_level(_logging.INFO):
            asyncio.run(_run_module(code=_BROKEN_CODE, project_name="ProjH"))

        assert not any("[PROJECT-ADOPTED]" in r.message for r in caplog.records)


if __name__ == "__main__":
    unittest.main()
