#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #305: preflight-check flexicon import names with did-you-mean.

Weak models invented import names (``WfiWordformOperations``,
``InflectionFeatures``, ``get_all_forms``, ``import flexicon.Lexicon``) and
only found out from a bare runtime ImportError. The ``unknown_import`` gate
reads the installed flexicon statically (never imports it) and rejects with
candidates; a runtime ImportError gets the same candidates.

The checker tests use a synthetic package on disk so they do not depend on
which pyflexicon is installed; one test runs against the real install when
it is present.
"""

import ast
import asyncio
import importlib.util
import textwrap

import pytest

from flextoolsmcp.server import flexicon_imports as fi
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    detect_unknown_flexicon_imports,
    detect_unknown_import_error,
)
from test_issue49_validate_only import _parse, _stub_agreement_env  # noqa: E402


@pytest.fixture
def fake_surface(tmp_path, monkeypatch):
    """A tiny flexicon-shaped package, wired in as the installed one."""
    pkg = tmp_path / "flexicon"
    (pkg / "code" / "Lexicon").mkdir(parents=True)
    (pkg / "__init__.py").write_text(textwrap.dedent("""
        version = "9.9.9"
        from .code.FLExProject import FLExProject
        from .code.Lexicon.LexEntryOperations import LexEntryOperations
        from .code.TextsWords import WordformOperations
        try:
            from .code.extra import InflectionFeatureOperations
        except ImportError:
            pass
        __all__ = ["FLExProject", "LexEntryOperations", "WordformOperations",
                   "InflectionFeatureOperations", "FLExInitialize"]
    """), encoding="utf-8")
    (pkg / "code" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "code" / "Lexicon" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "code" / "Lexicon" / "LexEntryOperations.py").write_text(
        "class LexEntryOperations:\n    pass\n", encoding="utf-8"
    )
    (pkg / "code" / "FLExProject.py").write_text("class FLExProject:\n    pass\n", encoding="utf-8")

    class _Spec:
        origin = str(pkg / "__init__.py")

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        fi.importlib.util, "find_spec",
        lambda name, *a, **k: _Spec() if name == "flexicon" else real_find_spec(name, *a, **k),
    )
    fi._SURFACE_CACHE.clear()
    yield fi.load_surface()
    fi._SURFACE_CACHE.clear()


ACCESSORS = {
    "Wordforms": "WordformOperations",
    "InflectionFeatures": "InflectionFeatureOperations",
    "LexEntry": "LexEntryOperations",
}


def _check(code, surface):
    return fi.check_imports(ast.parse(code), None, ACCESSORS, surface=surface)


class TestStaticSurface:
    def test_reads_names_without_importing(self, fake_surface):
        assert fake_surface.source_found is True
        assert {"FLExProject", "LexEntryOperations", "WordformOperations",
                "InflectionFeatureOperations", "FLExInitialize", "version",
                "code"} <= fake_surface.root_names
        assert "flexicon.code.Lexicon.LexEntryOperations" in fake_surface.modules

    def test_valid_imports_pass(self, fake_surface):
        r = _check(
            "from flexicon import FLExProject, LexEntryOperations as LEO\n"
            "from flexicon import *\n"
            "import flexicon\n"
            "import flexicon.code.Lexicon\n"
            "from flexicon.code.Lexicon.LexEntryOperations import LexEntryOperations\n"
            "from flexlibs2 import WordformOperations\n"
            "from os import path\n",
            fake_surface,
        )
        assert r["has_unknown"] is False, r["issues"]


class TestUnknownNames:
    def test_wfi_prefix_suggests_real_class_and_accessor(self, fake_surface):
        r = _check("from flexicon import WfiWordformOperations\n", fake_surface)
        assert r["has_unknown"] is True
        issue = r["issues"][0]
        assert issue["kind"] == "name"
        assert issue["did_you_mean"][0] == "WordformOperations"
        assert issue["access_path"] == "project.Wordforms"
        assert "from flexicon import WordformOperations" in issue["suggestion"]

    def test_accessor_imported_as_class(self, fake_surface):
        issue = _check("from flexicon import InflectionFeatures\n", fake_surface)["issues"][0]
        assert issue["access_path"] == "project.InflectionFeatures"
        assert "no import needed" in issue["suggestion"]
        assert "InflectionFeatureOperations" in issue["did_you_mean"]

    def test_invented_helper_has_no_false_candidate(self, fake_surface):
        issue = _check("from flexicon import get_all_forms\n", fake_surface)["issues"][0]
        assert issue["did_you_mean"] == []
        assert "flextools_search_by_capability" in issue["suggestion"]

    def test_unknown_module_path(self, fake_surface):
        issue = _check("import flexicon.Lexicon\n", fake_surface)["issues"][0]
        assert issue["kind"] == "module"
        assert issue["did_you_mean"] == ["flexicon.code.Lexicon"]

    def test_unknown_name_in_real_submodule(self, fake_surface):
        r = _check("from flexicon.code.Lexicon.LexEntryOperations import Nope\n", fake_surface)
        assert r["has_unknown"] is True
        assert "has no 'Nope'" in r["issues"][0]["suggestion"]

    def test_star_reexport_module_is_open(self, fake_surface, tmp_path):
        (tmp_path / "flexicon" / "code" / "Lexicon" / "__init__.py").write_text(
            "from .LexEntryOperations import *\n", encoding="utf-8"
        )
        fi._SURFACE_CACHE.clear()
        surface = fi.load_surface()
        assert _check("from flexicon.code.Lexicon import Anything\n", surface)["has_unknown"] is False


class TestFailOpen:
    def test_no_source_and_no_index_skips(self, monkeypatch):
        monkeypatch.setattr(fi.importlib.util, "find_spec", lambda name, *a, **k: None)
        fi._SURFACE_CACHE.clear()
        assert fi.load_surface(None) is None
        r = fi.check_imports(ast.parse("from flexicon import Whatever\n"), None)
        assert r["has_unknown"] is False

    def test_index_fallback_checks_root_names_only(self, monkeypatch):
        monkeypatch.setattr(fi.importlib.util, "find_spec", lambda name, *a, **k: None)
        fi._SURFACE_CACHE.clear()

        class Idx:
            flexicon = {"entities": {
                "LexEntryOperations": {"import_statement": "from flexicon import LexEntryOperations"},
                "FLExProject": {"top_level_importable": True},
            }}

        r = fi.check_imports(
            ast.parse(
                "from flexicon import LexEntriesOperations, cast_to_concrete\n"
                "import flexicon.Made.Up\n"
            ), Idx()
        )
        # Helpers the index never lists are not judged; module paths neither.
        assert [i["name"] for i in r["issues"]] == ["LexEntriesOperations"]
        assert r["issues"][0]["did_you_mean"] == ["LexEntryOperations"]


class TestRuntimeDiagnosis:
    def test_cannot_import_name(self, fake_surface):
        d = fi.diagnose_import_error(
            "Execution error: cannot import name 'WfiWordformOperations' from "
            "'flexicon' (C:\\x\\flexicon\\__init__.py)",
            None, ACCESSORS, surface=fake_surface,
        )
        assert d["is_unknown_import"] is True
        assert d["did_you_mean"][0] == "WordformOperations"
        assert d["access_path"] == "project.Wordforms"

    def test_no_module_named(self, fake_surface):
        d = fi.diagnose_import_error(
            "No module named 'flexicon.Lexicon'", None, surface=fake_surface
        )
        assert d["is_unknown_import"] is True
        assert d["did_you_mean"] == ["flexicon.code.Lexicon"]

    def test_unrelated_error(self):
        assert fi.diagnose_import_error("No module named 'requests'")["is_unknown_import"] is False


@pytest.mark.skipif(importlib.util.find_spec("flexicon") is None, reason="pyflexicon not installed")
def test_real_install_issue_examples():
    """The exact names from the issue, against the installed flexicon."""
    fi._SURFACE_CACHE.clear()
    code = (
        "from flexicon import WfiWordformOperations, LexEntryOperations, FLExProject\n"
        "import flexicon.Lexicon\n"
    )
    r = detect_unknown_flexicon_imports(ast.parse(code), None)
    by = {i["name"] or i["module"]: i for i in r["issues"]}
    assert set(by) == {"WfiWordformOperations", "flexicon.Lexicon"}
    assert by["WfiWordformOperations"]["did_you_mean"][0] == "WordformOperations"
    assert by["flexicon.Lexicon"]["did_you_mean"][0] == "flexicon.code.Lexicon"
    d = detect_unknown_import_error("cannot import name 'InflectionFeatures' from 'flexicon'")
    assert "InflectionFeatureOperations" in d["did_you_mean"]


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------

def _run(args):
    return _parse(asyncio.run(execution_mod.handle_run_module(args)))


def _args(code, **extra):
    return {"code": code, "project_name": "TestProj_305", "write_enabled": False,
            "skip_api_check": True, **extra}


def test_live_gate_rejects_with_envelope(monkeypatch, tmp_path, fake_surface, reset_session_state):
    _stub_agreement_env(monkeypatch, tmp_path)
    data = _run(_args("from flexicon import WfiWordformOperations\nreport.Info('x')\n"))
    assert data["error_code"] == "unknown_import", data
    assert data["did_you_mean"] == ["WordformOperations"]
    assert data["issues"][0]["lineno"] == 1
    assert data["next_steps"][0].startswith("Line 1:")

    validate = _run({**_args("from flexicon import WfiWordformOperations\n"), "validate_only": True})
    gate = {c["gate"]: c for c in validate["checks"]}["unknown_import"]
    assert gate["passed"] is False
    assert gate["did_you_mean"] == ["WordformOperations"]


def test_live_gate_passes_valid_imports(monkeypatch, tmp_path, fake_surface, reset_session_state):
    _stub_agreement_env(monkeypatch, tmp_path)
    data = _run(_args("from flexicon import LexEntryOperations\nreport.Info('x')\n"))
    assert data.get("error_code") != "unknown_import", data


def test_runtime_import_error_gets_candidates(monkeypatch, tmp_path, fake_surface, reset_session_state):
    _stub_agreement_env(monkeypatch, tmp_path)
    import json as _json

    async def _fake_run(path, timeout_seconds=None):
        payload = {
            "success": False,
            "error": "Execution error: No module named 'flexicon.Lexicon'\nTraceback...",
            "messages": [],
            "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
        }
        return {"stdout": "===FLEXTOOLS_RESULT_JSON===\n" + _json.dumps(payload),
                "stderr": "", "timeout": False, "returncode": 0}

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)
    # A dynamic import the static gate cannot see.
    data = _run(_args("import importlib\nimportlib.import_module('flexicon.Lexicon')\n"))
    assert data.get("error_type") == "UnknownImportError", data
    assert data["did_you_mean"] == ["flexicon.code.Lexicon"]
    assert "flexicon.code.Lexicon" in data["help"]
