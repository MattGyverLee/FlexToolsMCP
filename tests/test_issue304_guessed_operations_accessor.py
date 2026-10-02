#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #304: guessed ``project.<X>Operations`` accessors.

Weak models wrote ``project.WordformOperations`` (the class name as an
accessor). The ``missing_imports`` gate then told them to import
``WordformOperations``, which fixed nothing, and ``invalid_api_chain`` let
the name through because its fuzzy match against ``Wordforms`` is below the
threshold. Search results showed ``from flexicon import
WordformOperations`` and never ``project.Wordforms``, because FLExProject
documents that accessor with the import alias ``WfiWordformOperations``, which
has no index entry (the gap PR #342 called out).

Now:
- the accessor map resolves documented aliases to the indexed class, so
  ``project.Wordforms`` maps to ``WordformOperations`` (and its method typos
  are checked);
- ``project.<X>Operations`` is always an ``invalid_api_chain`` accessor issue,
  pointing at the facade accessor when the index has one;
- ``missing_imports`` does not suggest importing a name used only as
  ``project.<name>``;
- search / get_object_api carry ``access_path`` even where the index omits it.
"""

import ast
import json
from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import api as api_mod
from flextoolsmcp.server.validators import (
    _accessor_to_ops_map,
    _resolve_ops_alias,
    detect_invalid_project_chains,
    detect_missing_operations_imports,
)
from flextoolsmcp.flexicon_analyzer import _extract_facade_access_paths


def _shipped_index():
    python_dir = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "index" / "python"
    candidates = sorted(python_dir.glob("flexicon_api_v*.json"))
    if not candidates:
        pytest.skip("no shipped flexicon index")

    class Idx:
        flexicon = json.loads(candidates[-1].read_text(encoding="utf-8"))
        casting_index = None

    return Idx()


@pytest.fixture(scope="module")
def idx():
    return _shipped_index()


class TestAliasResolution:
    def test_wordforms_maps_to_indexed_class(self, idx):
        assert _accessor_to_ops_map(idx)["Wordforms"] == "WordformOperations"

    def test_every_accessor_class_is_indexed(self, idx):
        entities = idx.flexicon["entities"]
        unresolved = {a: c for a, c in _accessor_to_ops_map(idx).items() if c not in entities}
        assert unresolved == {}

    def test_resolver_keeps_known_and_unknown_names(self):
        entities = {"WordformOperations": {}, "LexEntryOperations": {}}
        assert _resolve_ops_alias("WfiWordformOperations", entities) == "WordformOperations"
        assert _resolve_ops_alias("LexEntryOperations", entities) == "LexEntryOperations"
        assert _resolve_ops_alias("MysteryOperations", entities) == "MysteryOperations"
        assert _resolve_ops_alias("Operations", entities) == "Operations"

    def test_wordforms_method_typos_now_checked(self, idx):
        r = detect_invalid_project_chains(ast.parse("project.Wordforms.GetAl()\n"), idx)
        assert r["has_invalid"] is True
        assert r["issues"][0]["did_you_mean"][0] == "GetAll"


class TestGuessedOperationsAccessor:
    def test_mapped_class_points_at_facade_accessor(self, idx):
        r = detect_invalid_project_chains(
            ast.parse("ops = project.WordformOperations\n"), idx
        )
        issue = r["issues"][0]
        assert issue["kind"] == "accessor"
        assert issue["did_you_mean"] == ["Wordforms"]
        assert issue["match_ratio"] == 1.0
        assert "use project.Wordforms" in issue["suggestion"]
        assert "no import needed" in issue["suggestion"]

    def test_unmapped_name_still_rejected_without_auto_fix(self, idx):
        r = detect_invalid_project_chains(
            ast.parse("for w in project.ParseOperations.GetAll():\n    pass\n"), idx
        )
        issue = r["issues"][0]
        assert issue["expr"] == "project.ParseOperations"
        assert issue["match_ratio"] < 0.9  # below the auto-fix threshold
        assert "FLExProject has no attribute 'ParseOperations'" in issue["suggestion"]

    def test_no_candidates_still_blocks(self):
        r = detect_invalid_project_chains(ast.parse("project.ZzqxOperations.Go()\n"), None)
        assert r["has_invalid"] is True
        assert r["issues"][0]["did_you_mean"] == []
        assert "flextools_search_by_capability" in r["issues"][0]["suggestion"]

    def test_real_accessors_unaffected(self, idx):
        code = (
            "for e in project.LexEntry.GetAll():\n"
            "    report.Info(str(project.Wordforms.GetAll()))\n"
        )
        assert detect_invalid_project_chains(ast.parse(code), idx)["has_invalid"] is False


class TestMissingImports:
    def test_project_attribute_use_is_not_an_import_problem(self):
        r = detect_missing_operations_imports("x = project.WordformOperations.GetAll()\n", "flexicon")
        assert r["has_missing"] is False

    def test_real_class_use_still_needs_import(self):
        r = detect_missing_operations_imports(
            "ops = WordformOperations(project)\nx = project.WordformOperations\n", "flexicon"
        )
        assert r["missing_imports"] == ["WordformOperations"]


class TestAccessPath:
    def test_derived_for_wordform_operations(self, idx, monkeypatch):
        monkeypatch.setattr(api_mod, "get_api_index", lambda: idx)
        entity = idx.flexicon["entities"]["WordformOperations"]
        assert "access_path" not in entity  # the shipped gap this covers
        assert api_mod._entity_access_path("flexicon", "WordformOperations", entity) == "project.Wordforms"
        assert api_mod._build_entity_import("flexicon", "WordformOperations", "", entity) == "project.Wordforms"

    def test_recorded_access_path_wins(self, idx, monkeypatch):
        monkeypatch.setattr(api_mod, "get_api_index", lambda: idx)
        entity = {"access_path": "project.Custom"}
        assert api_mod._entity_access_path("flexicon", "LexEntryOperations", entity) == "project.Custom"

    def test_non_flexicon_or_unmapped_is_none(self, idx, monkeypatch):
        monkeypatch.setattr(api_mod, "get_api_index", lambda: idx)
        assert api_mod._entity_access_path("liblcm", "ILexEntry", {}) is None
        assert api_mod._entity_access_path("flexicon", "BaseOperations", {}) is None

    def test_get_object_api_payload_carries_it(self, idx, monkeypatch):
        monkeypatch.setattr(api_mod, "get_api_index", lambda: idx)
        entity = idx.flexicon["entities"]["WordformOperations"]
        page = api_mod.paginate_entity(
            entity, summary_only=True, method_filter="", limit=5, offset=0,
            object_type="WordformOperations", library="flexicon",
        )
        assert page["access_path"] == "project.Wordforms"


def test_generator_records_real_class_for_aliased_import(tmp_path):
    (tmp_path / "FLExProject.py").write_text(
        "class FLExProject:\n"
        "    @property\n"
        "    def Wordforms(self):\n"
        "        if not hasattr(self, '_wordform_ops'):\n"
        "            from .TextsWords.WordformOperations import WordformOperations as WfiWordformOperations\n"
        "            self._wordform_ops = WfiWordformOperations(self)\n"
        "        return self._wordform_ops\n",
        encoding="utf-8",
    )
    assert _extract_facade_access_paths(tmp_path) == {"WordformOperations": "project.Wordforms"}
