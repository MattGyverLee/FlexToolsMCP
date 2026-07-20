#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #52: recipe-grade common patterns served through search.

Covers:
  - Generation-time preflight: every shipped (curated) recipe passes the
    full validator chain (recipe_validator.validate_all).
  - Serving: a query matching a recipe's match_terms attaches exactly one
    recipe to the top hit of handle_search_by_capability; unrelated
    queries attach none.
  - find_examples: operation_type/object_type filters also search recipes.
"""

import asyncio
import json

import pytest

from flextoolsmcp.curated_recipes import CURATED_RECIPES
from flextoolsmcp.recipe_validator import validate_all
from flextoolsmcp.server import APIIndex, get_index_dir
from flextoolsmcp.server.recipes import find_recipe_for_search, find_recipes_for_examples
from flextoolsmcp.server import kernel
from flextoolsmcp.server.handlers.api import handle_search_by_capability, handle_find_examples


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def api_index():
    """Real API index (flexicon-only load path is enough for these checks)."""
    return APIIndex.load(get_index_dir())


@pytest.fixture(autouse=True)
def _configure_session(api_index):
    """Point kernel's module-level api_index/session_state at a real, configured session."""
    kernel.set_api_index(api_index)
    kernel.session_state.configure(session_id="test-recipes", api_mode="flexicon")
    yield


# ---------------------------------------------------------------------------
# Generation-time preflight (CI gate): every shipped recipe must pass.
# ---------------------------------------------------------------------------

class TestRecipePreflight:
    def test_all_curated_recipes_pass_preflight(self, api_index):
        failures = validate_all(CURATED_RECIPES, api_index)
        assert failures == {}, json.dumps(failures, indent=2)

    def test_curated_recipes_are_all_marked_curated(self):
        # Guard against accidentally shipping a mined candidate: every entry
        # in CURATED_RECIPES must be source="curated", never "mined".
        for recipe_id, recipe in CURATED_RECIPES.items():
            assert recipe.get("source") == "curated", (
                f"{recipe_id} has source={recipe.get('source')!r}; only curated "
                "recipes may live in CURATED_RECIPES"
            )

    def test_curated_recipes_are_well_formed(self):
        required_keys = {
            "intent", "match_terms", "entities", "operations",
            "requires_write", "code", "notes", "source", "verified_against",
        }
        for recipe_id, recipe in CURATED_RECIPES.items():
            missing = required_keys - set(recipe.keys())
            assert not missing, f"{recipe_id} missing keys: {missing}"
            assert recipe["match_terms"], f"{recipe_id} has no match_terms"
            assert recipe["entities"], f"{recipe_id} has no entities"

    def test_write_recipes_are_guarded(self):
        for recipe_id, recipe in CURATED_RECIPES.items():
            if recipe.get("requires_write"):
                assert "if modifyAllowed:" in recipe["code"], (
                    f"{recipe_id} requires_write=True but code lacks an "
                    "'if modifyAllowed:' guard"
                )


# ---------------------------------------------------------------------------
# Pure matching helpers.
# ---------------------------------------------------------------------------

class TestRecipeMatching:
    def test_matching_query_returns_a_recipe(self):
        recipe = find_recipe_for_search("list all entries with their glosses")
        assert recipe is not None
        assert recipe["id"] == "list-entries-with-glosses"

    def test_unrelated_query_returns_none(self):
        assert find_recipe_for_search("frobnicate the widgets") is None

    def test_empty_query_returns_none(self):
        assert find_recipe_for_search("") is None

    def test_find_recipes_for_examples_by_operation_type(self):
        matches = find_recipes_for_examples(operation_type="write")
        assert matches
        assert all(r.get("requires_write") for r in matches)

    def test_find_recipes_for_examples_by_object_type(self):
        matches = find_recipes_for_examples(object_type="LexSense")
        assert matches
        assert all(
            any("sense" in e.lower() for e in r.get("entities", []))
            for r in matches
        )

    def test_find_recipes_for_examples_no_filters_returns_empty(self):
        assert find_recipes_for_examples() == []

    def test_find_recipes_for_examples_no_match_returns_empty(self):
        assert find_recipes_for_examples(object_type="ZzzNonExistentType") == []


# ---------------------------------------------------------------------------
# Handler-level integration: exactly one recipe on the top hit.
# ---------------------------------------------------------------------------

class TestSearchByCapabilityRecipeAttachment:
    def _search(self, query):
        result_list = run_async(handle_search_by_capability({"query": query}))
        payload = json.loads(result_list[0].text)
        return payload

    def test_matching_query_attaches_recipe_to_top_hit_only(self):
        payload = self._search("list all entries with their glosses")
        results = payload["results"]
        assert results, "expected at least one search result"
        assert "recipe" in results[0]
        assert results[0]["recipe"]["id"] == "list-entries-with-glosses"
        # Exactly one recipe attached across the whole response.
        recipe_count = sum(1 for r in results if "recipe" in r)
        assert recipe_count == 1

    def test_unrelated_query_attaches_no_recipe(self):
        payload = self._search("frobnicate the discourse chart widgets")
        results = payload["results"]
        assert all("recipe" not in r for r in results)


class TestFindExamplesRecipes:
    def _find_examples(self, **kwargs):
        result_list = run_async(handle_find_examples(kwargs))
        payload = json.loads(result_list[0].text)
        return payload

    def test_operation_type_write_surfaces_recipes(self):
        payload = self._find_examples(operation_type="write")
        assert payload["recipes_count"] > 0
        assert all(r.get("requires_write") for r in payload["recipes"])

    def test_no_filters_surfaces_no_recipes(self):
        payload = self._find_examples()
        assert payload["recipes"] == []
        assert payload["recipes_count"] == 0
