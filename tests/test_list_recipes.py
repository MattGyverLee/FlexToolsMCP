#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 6 US4: flextools_list_recipes (FR-024..026, FR-061, SC-006).

- Each `source`, `requires_write`, `limit` clamp, `query` ordering,
  shipped-first default order, `recipe_id` returns the full recipe,
  no `code` without `recipe_id`, `recipe_not_found` shape and field order
  with `closest_matches`, `test_recipe_id_records_validated`,
  `test_list_skeletons_alias_shape_and_deprecation`.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture()
def recipe_env(tmp_path, monkeypatch):
    """Isolate the on-disk local store and configure a session."""
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path / "recipes"))
    kernel.session_state.configure(session_id="test-list-recipes", api_mode="flexicon")
    kernel.session_state.validated_apis.clear()
    try:
        from flextoolsmcp.server import APIIndex, get_index_dir

        kernel.set_api_index(APIIndex.load(get_index_dir()))
    except Exception:
        pass
    return tmp_path


def _seeded(monkeypatch):
    """Seed shipped + local recipes; return (shipped_dict, local_list)."""
    import flextoolsmcp.curated_recipes as curated_mod
    import flextoolsmcp.server.local_recipes as lr_mod
    import flextoolsmcp.server.handlers.catalog as catalog_mod

    shipped = {
        "alpha-read": {
            "intent": "Alpha read recipe",
            "match_terms": ["alpha things"],
            "entities": ["LexEntry"],
            "operations": ["read"],
            "requires_write": False,
            "code": "entries = project.LexEntry.GetAll()\nreport.Info('alpha')\n",
            "notes": "alpha notes",
            "origin": "test",
            "source": "curated",
            "params": [],
            "verified_against": {"flexicon": "4.11.0", "verified_by": "preflight"},
        },
        "beta-write": {
            "intent": "Beta write recipe",
            "match_terms": ["beta things"],
            "entities": ["LexSense"],
            "operations": ["read", "write"],
            "requires_write": True,
            "code": "if modifyAllowed:\n    report.Info('beta')\n",
            "notes": "beta notes",
            "origin": "test",
            "source": "curated",
            "params": [{"name": "X", "default": "1", "description": "x param"}],
            "verified_against": {"flexicon": "4.11.0", "verified_by": "preflight"},
        },
    }
    local = [
        {
            "id": "local-aaa",
            "intent": "Local gamma recipe",
            "code": "entries = project.LexEntry.GetAll()\nfor e in entries:\n    report.Info(e)\n    report.Info('done')\n",
            "entities": ["LexEntry"],
            "requires_write": False,
            "operations": ["read"],
            "params": [],
            "projects": ["Sena 3"],
            "first_used": "2026-09-27T00:00:00+00:00",
            "last_used": "2026-09-28T00:00:00+00:00",
            "use_count": 3,
            "op_ids": ["op-1"],
            "source": "local",
            "migrated": False,
            "schema": "local-recipe/1",
        }
    ]
    monkeypatch.setattr(curated_mod, "CURATED_RECIPES", dict(shipped))
    monkeypatch.setattr(lr_mod, "load_local_recipes", lambda: list(local))
    monkeypatch.setattr(lr_mod, "list_local_recipes", lambda limit=100: list(local)[:limit])
    # Catalog may have imported the names directly; patch there too when present.
    for attr in ("CURATED_RECIPES",):
        if hasattr(catalog_mod, attr):
            monkeypatch.setattr(catalog_mod, attr, dict(shipped))
    return shipped, local


def _call_list_recipes(args):
    from flextoolsmcp.server.handlers import catalog as catalog_mod

    return run_async(catalog_mod.handle_list_recipes(args))


def _parse(result):
    assert len(result) > 0
    text = result[0].text
    return json.loads(text)


class TestListRecipesFilters:
    def test_source_shipped_only(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        data = _parse(_call_list_recipes({"source": "shipped"}))
        assert data["source"] == "shipped"
        assert data["recipes"]
        assert {r["source"] for r in data["recipes"]} == {"shipped"}

    def test_source_local_only(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        data = _parse(_call_list_recipes({"source": "local"}))
        assert data["source"] == "local"
        assert data["recipes"]
        assert {r["source"] for r in data["recipes"]} == {"local"}

    def test_source_all(self, recipe_env, monkeypatch):
        shipped, local = _seeded(monkeypatch)
        data = _parse(_call_list_recipes({"source": "all"}))
        ids = {r["id"] for r in data["recipes"]}
        assert set(shipped) | {r["id"] for r in local} <= ids

    def test_requires_write_filter(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        writes = _parse(_call_list_recipes({"requires_write": True}))
        assert writes["recipes"]
        assert all(r["requires_write"] for r in writes["recipes"])
        reads = _parse(_call_list_recipes({"requires_write": False}))
        assert reads["recipes"]
        assert all(not r["requires_write"] for r in reads["recipes"])

    def test_limit_clamp(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        low = _parse(_call_list_recipes({"limit": 0}))
        assert len(low["recipes"]) == 1
        high = _parse(_call_list_recipes({"limit": 500}))
        # Clamped to 1..200: never errors, never returns more than exist.
        assert len(high["recipes"]) <= 200

    def test_query_ordering_matches_ranker(self, recipe_env, monkeypatch):
        shipped, local = _seeded(monkeypatch)
        from flextoolsmcp.server import recipes as recipe_search

        merged = dict(shipped)
        for rec in local:
            merged[rec["id"]] = rec
        ranked = [r["id"] for r in recipe_search.rank_recipes("beta things", recipes=merged)]
        data = _parse(_call_list_recipes({"query": "beta things"}))
        assert data["recipes"]
        assert data["recipes"][0]["id"] == ranked[0]

    def test_shipped_first_default_order(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        data = _parse(_call_list_recipes({}))
        sources = [r["source"] for r in data["recipes"]]
        # All shipped rows come before any local row when no query is given.
        assert sources == sorted(sources, key=lambda s: 0 if s == "shipped" else 1)

    def test_no_code_without_recipe_id(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        data = _parse(_call_list_recipes({}))
        assert data["recipes"]
        assert all("code" not in r for r in data["recipes"])

    def test_recipe_id_returns_full_recipe(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        data = _parse(_call_list_recipes({"recipe_id": "alpha-read"}))
        assert "recipe" in data
        full = data["recipe"]
        assert full["id"] == "alpha-read"
        assert full["code"]
        assert "notes" in full
        assert "match_terms" in full
        assert "operations" in full

    def test_recipe_not_found_shape_and_field_order(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        data = _parse(_call_list_recipes({"recipe_id": "alpha-reed"}))
        assert data.get("error_code") == "recipe_not_found"
        assert data["recipe_id"] == "alpha-reed"
        assert isinstance(data["closest_matches"], list)
        assert data["closest_matches"] and len(data["closest_matches"]) <= 3
        assert "alpha-read" in data["closest_matches"]
        assert "flextools_list_recipes(query=" in data["hint"]
        # Field order: recipe_id, closest_matches, hint (after error_code/message).
        keys = list(data.keys())
        assert keys.index("recipe_id") < keys.index("closest_matches") < keys.index("hint")

    def test_recipe_id_records_validated(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        kernel.session_state.validated_apis.clear()
        _parse(_call_list_recipes({"recipe_id": "alpha-read"}))
        assert "LexEntry" in kernel.session_state.validated_apis


class TestListSkeletonsAlias:
    def test_alias_shape_and_deprecation(self, recipe_env, monkeypatch):
        _seeded(monkeypatch)
        from flextoolsmcp.server.handlers import catalog as catalog_mod

        result = run_async(catalog_mod.handle_list_skeletons({"limit": 10}))
        data = json.loads(result[0].text)
        assert {"count", "limit", "storage_path", "skeletons"} <= set(data)
        assert data["skeletons"]
        row = data["skeletons"][0]
        assert {"name", "source", "entities", "user_intent", "captured_at", "op_id"} <= set(row)
        dep = data.get("deprecation")
        assert dep
        assert dep["deprecated"] == "flextools_list_skeletons"
        assert "flextools_list_recipes" in dep["replacement"]
        assert dep["removal"] == "tool-responses/2.0"
