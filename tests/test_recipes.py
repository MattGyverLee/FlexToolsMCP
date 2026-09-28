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
from flextoolsmcp.recipe_files import load_recipe_library
from flextoolsmcp.recipe_validator import validate_all, validate_recipe
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

    def test_shipped_file_recipes_pass_shipped_gate(self, api_index):
        # FR-040/FR-041/FR-045: file recipes also clear the shipped-only
        # checks (PARAMS, scrub, print ban, raw-LCM gate and ratchet).
        api_index.ensure_flexicon_bridge_loaded()
        file_recipes, errors = load_recipe_library()
        assert errors == []
        failures = {}
        for recipe_id, recipe in file_recipes.items():
            result = validate_recipe(recipe, api_index, shipped=True)
            if not result["passed"]:
                failures[recipe_id] = result
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

    def test_attachment_identical_to_pre_change(self):
        # FR-022: the legacy results[0].recipe attachment is byte-identical
        # to the pre-change shape: {"id": ..., **CURATED_RECIPES[id]}.
        payload = self._search("list all entries with their glosses")
        recipe = payload["results"][0]["recipe"]
        expected = {"id": "list-entries-with-glosses",
                    **CURATED_RECIPES["list-entries-with-glosses"]}
        assert recipe == expected

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


class TestVerifiedVersion:
    def test_verified_version_matches_index_target(self, api_index):
        from flextoolsmcp.curated_recipes import FLEXICON_VERIFIED_VERSION

        assert FLEXICON_VERIFIED_VERSION == api_index.flexicon_version


# ---------------------------------------------------------------------------
# Unified-recipes T029: shipped validator checks (FR-040, FR-041, FR-044,
# FR-050..053, SC-003). Each recipe below must FAIL validate_recipe with
# shipped=True for exactly one reason.
# ---------------------------------------------------------------------------

def _shipped_recipe(code, **overrides):
    recipe = {
        "id": "seed-shipped",
        "intent": "seed",
        "match_terms": ["seed"],
        "entities": ["LexEntry"],
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


CLEAN_SHIPPED_CODE = (
    "for entry in project.LexEntry.GetAll():\n"
    "    headword = project.LexEntry.GetHeadword(entry)\n"
    "    report.Info(headword)\n"
)


class TestShippedValidatorChecks:
    def test_clean_recipe_passes_shipped(self, api_index):
        result = validate_recipe(_shipped_recipe(CLEAN_SHIPPED_CODE), api_index, shipped=True)
        assert result["passed"], result["issues"]

    def test_bad_params_block_fails(self, api_index):
        code = (
            "# --- PARAMS ---\n"
            "COUNT = 10 + \n"
            "# --- END PARAMS ---\n" + CLEAN_SHIPPED_CODE
        )
        result = validate_recipe(_shipped_recipe(code), api_index, shipped=True)
        assert not result["passed"]
        assert any("PARAMS" in issue for issue in result["issues"])

    def test_unclosed_params_block_fails(self, api_index):
        code = "# --- PARAMS ---\nCOUNT = 10\n" + CLEAN_SHIPPED_CODE
        result = validate_recipe(_shipped_recipe(code), api_index, shipped=True)
        assert not result["passed"]
        assert any("PARAMS" in issue for issue in result["issues"])

    def test_unguarded_write_fails(self, api_index):
        code = (
            "for entry in project.LexEntry.GetAll():\n"
            "    project.LexEntry.Delete(entry)\n"
        )
        result = validate_recipe(
            _shipped_recipe(code, requires_write=True), api_index, shipped=True
        )
        assert not result["passed"]
        assert any("modifyAllowed" in issue for issue in result["issues"])

    def test_deprecated_member_fails(self, api_index):
        code = (
            "for entry in project.LexEntry.GetAll():\n"
            "    x = entry.DoNotUseForParsing\n"
            "    report.Info(str(x))\n"
        )
        result = validate_recipe(_shipped_recipe(code), api_index, shipped=True)
        assert not result["passed"]
        assert any("deprecat" in issue.lower() for issue in result["issues"])

    def test_guid_literal_fails(self, api_index):
        code = CLEAN_SHIPPED_CODE + "guid = '12345678-1234-1234-1234-1234567890ab'\n"
        result = validate_recipe(_shipped_recipe(code), api_index, shipped=True)
        assert not result["passed"]
        assert any("GUID" in issue or "scrub" in issue.lower() for issue in result["issues"])

    def test_user_path_fails(self, api_index):
        code = CLEAN_SHIPPED_CODE + "# data lived at C:\\Users\\someone\\data\n"
        result = validate_recipe(_shipped_recipe(code), api_index, shipped=True)
        assert not result["passed"]
        assert any("scrub" in issue.lower() or "path" in issue.lower() for issue in result["issues"])

    @pytest.mark.parametrize("name", ["Claude-Swahili", "Target"])
    def test_forbidden_default_names_fail(self, api_index, name):
        code = CLEAN_SHIPPED_CODE + f"PROJECT = '{name}'\n"
        result = validate_recipe(_shipped_recipe(code), api_index, shipped=True)
        assert not result["passed"]
        assert any("scrub" in issue.lower() or name in issue for issue in result["issues"])

    def test_print_call_fails(self, api_index):
        code = CLEAN_SHIPPED_CODE + "print(headword)\n"
        result = validate_recipe(_shipped_recipe(code), api_index, shipped=True)
        assert not result["passed"]
        assert any("print" in issue.lower() for issue in result["issues"])


# FR-050 batch: at least 12 of the 16 first-batch recipes ship (T034..T051).
FIRST_BATCH_IDS = [
    "parser-coverage",
    "lexicon-form-lookup",
    "entry-parser-detail",
    "wordform-analyses",
    "form-usage-before-edit",
    "affix-templates-and-slots",
    "phonological-rules",
    "wordform-case-variants",
    "create-entries-idempotent",
    "create-entry-like-comparator",
    "set-allomorph-environments",
    "add-inflectional-affix",
    "add-allomorph",
    "create-text-from-lines",
    "create-variant-entries",
    "affix-template-setup",
]


def test_first_batch_count():
    shipped = set(CURATED_RECIPES)
    have = [rid for rid in FIRST_BATCH_IDS if rid in shipped]
    assert len(have) >= 12, f"only {len(have)} of 16 batch recipes ship: {sorted(have)}"


def test_shipped_file_recipes_have_sena3_verification():
    file_recipes, _errors = load_recipe_library()
    assert file_recipes, "no file recipes ship yet"
    for recipe_id, recipe in file_recipes.items():
        verified_by = (recipe.get("verified_against") or {}).get("verified_by")
        assert verified_by in ("sena3-read", "sena3-dryrun", "sena3-live"), (
            f"{recipe_id} verified_by={verified_by!r}; FR-044 requires a "
            "Sena 3 run (sena3-read / sena3-dryrun / sena3-live)"
        )


def test_vernacular_recipes_normalize():
    # FR-051: shipped file recipes comparing vernacular text MUST
    # NFC-normalize both sides (unicodedata.normalize).
    file_recipes, _errors = load_recipe_library()
    for recipe_id, recipe in file_recipes.items():
        blob = (
            recipe.get("intent", "")
            + " " + " ".join(recipe.get("match_terms", []))
            + " " + recipe.get("notes", "")
        ).lower()
        if "vernacular" in blob or "nfc" in blob or "nfd" in blob:
            assert "normalize" in recipe["code"], (
                f"{recipe_id} touches vernacular text but never normalizes it"
            )


class _FakeReport:
    def __init__(self):
        self.info, self.warnings = [], []

    def Info(self, msg, ref=None):
        self.info.append(msg)

    def Warning(self, msg, ref=None):
        self.warnings.append(msg)


class _FakeOps:
    def __init__(self, **methods):
        self.__dict__.update(methods)


def test_lexicon_lookup_finds_nfd_form():
    # US3 acceptance 2: a lexeme form stored decomposed (NFD) is found by a
    # composed (NFC) query. Runs the shipped recipe code against a fake
    # project; Sena 3 has no decomposed vernacular forms to test live.
    import unicodedata

    recipes, _errors = load_recipe_library()
    code = recipes["lexicon-form-lookup"]["code"]
    stored = unicodedata.normalize("NFD", "café")
    assert stored != "café"
    entry = object()
    project = _FakeOps(
        LexEntry=_FakeOps(
            GetAll=lambda: [entry],
            GetLexemeForm=lambda e: stored,
            GetHeadword=lambda e: stored,
            GetSenses=lambda e: [],
            GetMorphType=lambda e: "stem",
        ),
        Allomorphs=_FakeOps(GetAll=lambda e: [], GetForm=lambda a: ""),
        Senses=_FakeOps(GetGloss=lambda s: "", GetPartOfSpeech=lambda s: ""),
        BuildGotoURL=lambda obj: "",
    )
    code = code.replace('KEYS = ["lekerer", "rekerer", "cibubu"]', 'KEYS = ["café"]')
    report = _FakeReport()
    exec(compile(code, "lexicon-form-lookup.py", "exec"), {"project": project, "report": report})
    assert len(report.info) == 1, report.info
    assert report.warnings == []
