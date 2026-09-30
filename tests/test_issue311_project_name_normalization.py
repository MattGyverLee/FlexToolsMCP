#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #311: punctuation-only / quoted project_name normalization.

A weak driving model passed project_name='``' (two backticks) on a session
already bound to a project. The handler only tested `if not project_name`,
so the truthy junk string went to fuzzy resolution and came back as
project_not_found with suggestions=[] -- no way to recover.

Covered here (no live FLEx):
  - normalize_project_name() unit behaviour
  - backtick-only name falls back to the session project (run_module,
    grammar_health, the parse tools' shared _resolve_project)
  - punctuation-only with no session project -> project_name_required
  - a quoted real name is unwrapped before resolution
  - project_not_found includes available_projects even with no suggestions
"""

import asyncio
import json

import pytest

import flextoolsmcp.server.handlers.admin as admin_mod
import flextoolsmcp.server.handlers.execution as exec_mod
import flextoolsmcp.server.handlers.grammar_health as gh_mod
import flextoolsmcp.server.handlers.parse.common as parse_common
import flextoolsmcp.server.project_discovery as pd
from flextoolsmcp.server.project_discovery import (
    normalize_project_name,
    resolve_or_explain,
)
from flextoolsmcp.server.session import SessionState

# Cheapest way past the project-resolution block without a real project:
# a syntax error is rejected right after it (same trick as
# tests/test_project_discovery.py).
_BROKEN_CODE = "def Main(project, report, modifyAllowed:\n    pass"


def _data(result):
    return json.loads(result[0].text)


# ---------------------------------------------------------------------------
# normalize_project_name()
# ---------------------------------------------------------------------------


class TestNormalizeProjectName:
    @pytest.mark.parametrize(
        "raw",
        [None, "", "``", "`", "''", '""', "   ", "` `", "“”", "`'\"", "-", "``.``"],
    )
    def test_non_names_become_none(self, raw):
        assert normalize_project_name(raw) is None

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Sena 3", "Sena 3"),
            ("`Sena 3`", "Sena 3"),
            ("``Sena 3``", "Sena 3"),
            ("'Sena 3'", "Sena 3"),
            ('"Sena 3"', "Sena 3"),
            ("“Sena 3”", "Sena 3"),
            ("  `Claude-Swahili`  ", "Claude-Swahili"),
            # Internal punctuation / quotes are preserved.
            ("`O'Brien Lexicon`", "O'Brien Lexicon"),
            ("A`B", "A`B"),
        ],
    )
    def test_real_names_are_unwrapped_not_altered(self, raw, expected):
        assert normalize_project_name(raw) == expected


# ---------------------------------------------------------------------------
# resolve_or_explain(): normalization + available_projects
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_projects(monkeypatch):
    names = ["Alpha", "Bravo", "Sena 3"]
    monkeypatch.setattr(pd, "list_projects", lambda force_refresh=False: (names, "default"))
    return names


class TestResolveOrExplain:
    def test_quoted_real_name_resolves(self, fake_projects):
        resolved, err = resolve_or_explain("`Sena 3`")
        assert err is None
        assert resolved == "Sena 3"

    def test_punctuation_only_is_treated_as_empty(self, fake_projects):
        assert resolve_or_explain("``") == (None, None)

    def test_not_found_carries_available_projects_without_suggestions(self, fake_projects):
        resolved, err = resolve_or_explain("Zzqx")
        assert resolved is None
        assert err["error_code"] == "project_not_found"
        assert err["suggestions"] == []
        assert err["available_projects"] == fake_projects
        assert err["total_count"] == len(fake_projects)
        assert "plain project name" in err["hint"]
        assert "flextools_list_projects" in err["hint"]


# ---------------------------------------------------------------------------
# Handler level
# ---------------------------------------------------------------------------


def _ensure_kernel_ready():
    from flextoolsmcp.server import APIIndex
    from flextoolsmcp.server.kernel import get_index_dir, initialize_kernel, set_api_index

    initialize_kernel()
    set_api_index(APIIndex.load(get_index_dir()))


@pytest.fixture
def isolated_session():
    _ensure_kernel_ready()
    saved = exec_mod.session_state
    saved.__dict__.clear()
    saved.__dict__.update(SessionState().__dict__)
    try:
        yield saved
    finally:
        saved.__dict__.clear()
        saved.__dict__.update(SessionState().__dict__)


@pytest.fixture
def recording_resolver(monkeypatch):
    """Exact-match passthrough that records every name it was asked about."""
    seen = []

    def _passthrough(name):
        seen.append(name)
        return name, None

    monkeypatch.setattr(pd, "resolve_or_explain", _passthrough)
    monkeypatch.setattr(admin_mod, "resolve_or_explain", _passthrough)
    return seen


def _run_module(**kwargs):
    return asyncio.run(exec_mod.handle_run_module(dict(kwargs)))


class TestRunModule:
    def test_backtick_only_name_falls_back_to_session_project(
        self, isolated_session, recording_resolver
    ):
        isolated_session.project_name = "ProjA"
        data = _data(_run_module(code=_BROKEN_CODE, project_name="``"))
        assert data.get("error_code") == "syntax_error"
        assert recording_resolver == ["ProjA"]
        assert isolated_session.project_name == "ProjA"

    def test_punctuation_only_with_no_session_project_is_name_required(
        self, isolated_session, recording_resolver, fake_projects
    ):
        assert not isolated_session.get_project()
        data = _data(_run_module(code=_BROKEN_CODE, project_name="``"))
        assert data.get("error_code") == "project_name_required"
        assert data.get("available_projects") == fake_projects
        assert recording_resolver == []

    def test_quoted_real_name_is_unwrapped(self, isolated_session, recording_resolver):
        data = _data(_run_module(code=_BROKEN_CODE, project_name="`Sena 3`"))
        assert data.get("error_code") == "syntax_error"
        assert recording_resolver == ["Sena 3"]
        assert isolated_session.project_name == "Sena 3"

    def test_project_not_found_includes_available_projects(
        self, isolated_session, fake_projects
    ):
        data = _data(_run_module(code=_BROKEN_CODE, project_name="Zzqx"))
        assert data.get("error_code") == "project_not_found"
        assert data.get("suggestions") == []
        assert data.get("available_projects") == fake_projects
        assert data.get("total_count") == len(fake_projects)
        assert "flextools_list_projects" in data.get("hint", "")


class TestSiblingHandlers:
    def test_parse_resolve_project_falls_back_to_session(
        self, isolated_session, recording_resolver
    ):
        isolated_session.project_name = "ProjC"
        name, err = parse_common._resolve_project("``")
        assert err is None
        assert name == "ProjC"
        assert recording_resolver == ["ProjC"]

    def test_parse_resolve_project_no_session_is_name_required(
        self, isolated_session, recording_resolver, fake_projects
    ):
        name, err = parse_common._resolve_project("``")
        assert name is None
        data = _data(err)
        assert data.get("error_code") == "project_name_required"
        assert data.get("available_projects") == fake_projects

    def test_parse_resolve_project_not_found_includes_available_projects(
        self, isolated_session, fake_projects
    ):
        name, err = parse_common._resolve_project("Zzqx")
        assert name is None
        data = _data(err)
        assert data.get("error_code") == "project_not_found"
        assert data.get("available_projects") == fake_projects

    def test_grammar_health_backtick_only_falls_back_to_session(
        self, isolated_session, recording_resolver, monkeypatch
    ):
        async def _fake_scan(**kwargs):
            _fake_scan.project = kwargs.get("project_name")
            return {
                "success": True,
                "findings": {"checks_run": [], "checks_skipped": [], "findings": []},
            }

        monkeypatch.setattr(exec_mod, "run_scan_module", _fake_scan)
        isolated_session.project_name = "ProjB"
        data = _data(asyncio.run(gh_mod.handle_flextools_grammar_health({"project_name": "``"})))
        assert data.get("status") == "ok"
        assert _fake_scan.project == "ProjB"

    def test_start_with_backtick_only_name_sets_no_project(
        self, isolated_session, recording_resolver
    ):
        data = _data(asyncio.run(admin_mod.handle_start({"project_name": "``"})))
        assert data.get("error_code") is None
        assert isolated_session.project_name == ""
        assert recording_resolver == []

    def test_start_with_quoted_name_unwraps_it(self, isolated_session, recording_resolver):
        asyncio.run(admin_mod.handle_start({"project_name": "`Sena 3`"}))
        assert isolated_session.project_name == "Sena 3"
        assert recording_resolver == ["Sena 3"]
