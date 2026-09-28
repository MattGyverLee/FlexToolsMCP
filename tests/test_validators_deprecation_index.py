#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for unified-recipes T030: index-driven deprecation (FR-041, R17).

``detect_deprecated_members`` takes an optional ``api_index``. A member
counts as deprecated when it is curated-deprecated (as today) OR when its
flexicon index entry carries a deprecation flag or a deprecation marker in
its description (``.. deprecated::``, leading ``Deprecated``). The
``recipe_validator`` passes the index through; the run-time preflight keeps
its current curated-only behaviour (no ``api_index``), so ``run_module``
refusals are unchanged by this feature.
"""

import pytest

from flextoolsmcp.recipe_validator import validate_recipe
from flextoolsmcp.server import APIIndex, get_index_dir
from flextoolsmcp.server import kernel
from flextoolsmcp.server.validators import detect_deprecated_members


@pytest.fixture(scope="module")
def api_index():
    """Real API index (flexicon 4.11.0 carries index deprecation markers)."""
    return APIIndex.load(get_index_dir())


@pytest.fixture(autouse=True)
def _configure_session(api_index):
    kernel.set_api_index(api_index)
    kernel.session_state.configure(session_id="test-deprecation-index", api_mode="flexicon")
    yield


# EtymologyOperations.GetLanguage is index-deprecated (.. deprecated::, use
# GetLanguages()) but NOT curated-deprecated: it separates the two paths.
INDEX_DEPRECATED_CODE = (
    "for et in project.Etymology.GetAll():\n"
    "    lang = project.Etymology.GetLanguage(et)\n"
    "    report.Info(str(lang))\n"
)

CURATED_DEPRECATED_CODE = (
    "for entry in project.LexEntry.GetAll():\n"
    "    x = entry.DoNotUseForParsing\n"
    "    report.Info(str(x))\n"
)

CLEAN_CODE = (
    "for entry in project.LexEntry.GetAll():\n"
    "    headword = project.LexEntry.GetHeadword(entry)\n"
    "    report.Info(headword)\n"
)


def _recipe(code, **overrides):
    recipe = {
        "id": "seed-deprecated",
        "intent": "seed",
        "match_terms": ["seed"],
        "entities": ["Etymology"],
        "operations": ["read"],
        "requires_write": False,
        "code": code,
        "notes": "seed",
        "origin": "test",
        "source": "curated",
        "verified_against": {"flexicon": "4.11.0", "verified_by": "preflight"},
    }
    recipe.update(overrides)
    return recipe


class TestIndexDrivenDeprecation:
    def test_index_deprecated_method_detected_with_api_index(self, api_index):
        check = detect_deprecated_members(INDEX_DEPRECATED_CODE, None, api_index)
        assert check["has_deprecated"]
        assert any("GetLanguage" in f["expr"] for f in check["findings"])

    def test_clean_code_passes_with_api_index(self, api_index):
        check = detect_deprecated_members(CLEAN_CODE, None, api_index)
        assert not check["has_deprecated"]

    def test_runtime_preflight_without_index_is_unchanged(self):
        # Run-time preflight passes no api_index: curated-only behaviour.
        # The index-deprecated GetLanguage call must NOT be flagged there.
        check = detect_deprecated_members(INDEX_DEPRECATED_CODE)
        assert not check["has_deprecated"]

    def test_curated_deprecated_still_fails_without_index(self):
        check = detect_deprecated_members(CURATED_DEPRECATED_CODE)
        assert check["has_deprecated"]

    def test_validate_recipe_fails_for_index_deprecated(self, api_index):
        result = validate_recipe(_recipe(INDEX_DEPRECATED_CODE), api_index, shipped=True)
        assert not result["passed"]
        assert any("deprecat" in issue.lower() for issue in result["issues"])

    def test_validate_recipe_passes_clean_with_index(self, api_index):
        result = validate_recipe(_recipe(CLEAN_CODE), api_index, shipped=True)
        assert result["passed"], result["issues"]
