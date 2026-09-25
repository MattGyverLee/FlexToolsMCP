#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #138: shipped recipe for multi-run (tagged) paragraph text creation."""

import json

import pytest

from flextoolsmcp.curated_recipes import CURATED_RECIPES
from flextoolsmcp.recipe_validator import validate_recipe
from flextoolsmcp.server import APIIndex, get_index_dir
from flextoolsmcp.server.recipes import find_recipe_for_search


@pytest.fixture(scope="module")
def api_index():
    return APIIndex.load(get_index_dir())


def test_create_interlinear_recipe_passes_preflight(api_index):
    recipe = CURATED_RECIPES["create-interlinear-text"]
    result = validate_recipe(recipe, api_index)
    assert result["passed"], json.dumps(result, indent=2)


def test_create_interlinear_recipe_matches_search_intent():
    recipe = find_recipe_for_search("create interlinear text with tagged runs")
    assert recipe is not None
    assert recipe["id"] == "create-interlinear-text"
