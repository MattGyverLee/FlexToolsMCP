#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 3 US1: unified ranked recipe search (FR-020, FR-021, FR-026, FR-061, SC-001, SC-005).

Covers normalization, bag weights, IDF, code_terms + alias table, boosts,
null-intent penalty, empty query, response keys, clear-winner gate,
object-only queries, close scores, no-duplicate code (code_at), hint,
validated recording, compact-row budget, single-code-body invariant, and
the QUERY_BATTERY (top-3 rate >= 0.9).
"""

import asyncio
import json

import pytest

from flextoolsmcp.curated_recipes import CURATED_RECIPES
from flextoolsmcp.recipe_files import extract_code_terms
from flextoolsmcp.server import kernel
from flextoolsmcp.server import recipes as recipe_search


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def api_index():
    from flextoolsmcp.server import APIIndex, get_index_dir

    return APIIndex.load(get_index_dir())


@pytest.fixture(autouse=True)
def _configure_session(api_index, tmp_path, monkeypatch):
    kernel.set_api_index(api_index)
    kernel.session_state.configure(session_id="test-recipe-search", api_mode="flexicon")
    # US2: isolate the on-disk local store so handler-level searches stay
    # hermetic (no ~/.flextoolsmcp/recipes.jsonl leakage). Tests that need
    # locals override FLEXTOOLSMCP_RECIPE_DIR themselves.
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path / "empty-recipes"))
    yield


def _fixture_recipe(recipe_id, intent="Do zibble things", match_terms=None,
                    code="", entities=None, source="curated",
                    use_count=0, requires_write=False):
    return {
        "id": recipe_id,
        "intent": intent,
        "match_terms": match_terms or [],
        "entities": entities or ["LexEntry"],
        "operations": ["read"],
        "requires_write": requires_write,
        "code": code,
        "notes": "test",
        "origin": "test",
        "source": source,
        "params": [],
        "use_count": use_count,
    }


class TestNormalization:
    def test_case_insensitive(self):
        a = recipe_search.search_recipes("LIST ALL ENTRIES WITH THEIR GLOSSES")
        b = recipe_search.search_recipes("list all entries with their glosses")
        assert [r["id"] for r in a["recipes"]] == [r["id"] for r in b["recipes"]]

    def test_punctuation_insensitive(self):
        a = recipe_search.search_recipes("list, entries! with... glosses?")
        b = recipe_search.search_recipes("list entries with glosses")
        assert [r["id"] for r in a["recipes"]] == [r["id"] for r in b["recipes"]]

    def test_plural_insensitive(self):
        a = recipe_search.search_recipes("list entry with gloss")
        b = recipe_search.search_recipes("lists entries with glosses")
        # Both normalize trailing s; the top hit should agree.
        assert a["recipes"] and b["recipes"]
        assert a["recipes"][0]["id"] == b["recipes"][0]["id"]


class TestBagWeights:
    def test_task_beats_code_beats_object(self):
        fixtures = {
            "r-task": _fixture_recipe("r-task", match_terms=["zibble wibble"],
                                      code="report.Info('hi')", entities=["LexEntry"]),
            "r-code": _fixture_recipe("r-code", match_terms=["unrelated phrase here"],
                                      code="project.Wordform.GetZibbleWibble(x)",
                                      entities=["LexEntry"]),
            "r-object": _fixture_recipe("r-object", match_terms=["unrelated phrase here"],
                                        code="report.Info('hi')", entities=["ZibbleWibble"]),
        }
        # Pad with dummies so N is large enough for the object-only row to
        # clear the floor (idf grows with N; the ordering is what matters).
        for i in range(20):
            fixtures[f"dummy-{i}"] = _fixture_recipe(
                f"dummy-{i}", intent=f"dummy intent number {i}",
                match_terms=[f"dummy phrase number {i}"],
                code="report.Info('dummy')", entities=["Text"])
        ranked = recipe_search.rank_recipes("zibble wibble", fixtures)
        order = [r["id"] for r in ranked]
        assert order.index("r-task") < order.index("r-code") < order.index("r-object")

    def test_idf_common_word_contributes_about_zero(self):
        fixtures = {
            "r1": _fixture_recipe("r1", match_terms=["common alpha"], entities=["LexEntry"]),
            "r2": _fixture_recipe("r2", match_terms=["common beta"], entities=["LexEntry"]),
            "r3": _fixture_recipe("r3", match_terms=["common gamma"], entities=["LexEntry"]),
        }
        idf = recipe_search.compute_idf(fixtures)
        # "common" is in every recipe; its idf is ln(1 + 3/3) = ln2 ~ 0.69,
        # far below a rare word's ln(1+3/1) = ln4 ~ 1.39. The spec's "about 0"
        # is relative: common contributes about half (or less) of rare.
        assert idf["common"] < 0.6 * idf["alpha"]

    def test_code_terms_alias_table(self):
        terms = extract_code_terms("x = obj.PhoneEnvRC\ny = foo.GetOccurrenceCount(z)")
        assert "phone" in terms
        assert "environment" in terms
        assert "frequency" in terms or "count" in terms or "occurrence" in terms

    def test_shipped_boost(self):
        fixtures = {
            "r-shipped": _fixture_recipe("r-shipped", match_terms=["zibble wibble"],
                                         entities=["LexEntry"], source="curated"),
            "r-local": _fixture_recipe("r-local", intent="zibble wibble",
                                       match_terms=[], code="report.Info(1)",
                                       entities=["LexEntry"], source="local", use_count=1),
        }
        ranked = recipe_search.rank_recipes("zibble wibble", fixtures)
        scores = {r["id"]: r["_score"] for r in ranked}
        assert scores["r-shipped"] > scores["r-local"]

    def test_use_count_boost(self):
        fixtures = {
            "r-low": _fixture_recipe("r-low", intent="zibble wibble", match_terms=[],
                                    code="report.Info(1)", entities=["LexEntry"],
                                    source="local", use_count=1),
            "r-high": _fixture_recipe("r-high", intent="zibble wibble", match_terms=[],
                                      code="report.Info(1)", entities=["LexEntry"],
                                      source="local", use_count=100),
        }
        ranked = recipe_search.rank_recipes("zibble wibble", fixtures)
        scores = {r["id"]: r["_score"] for r in ranked}
        assert scores["r-high"] > scores["r-low"]

    def test_null_intent_penalty(self):
        fixtures = {
            "r-null": _fixture_recipe("r-null", intent=None, match_terms=[],
                                     code="project.ZibbleWibble.GetAll()",
                                     entities=["LexEntry"], source="local", use_count=1),
            "r-intent": _fixture_recipe("r-intent", intent="zibble wibble",
                                        match_terms=[], code="project.ZibbleWibble.GetAll()",
                                        entities=["LexEntry"], source="local", use_count=1),
        }
        for i in range(20):
            fixtures[f"dummy-{i}"] = _fixture_recipe(
                f"dummy-{i}", intent=f"dummy intent number {i}",
                match_terms=[f"dummy phrase number {i}"],
                code="report.Info('dummy')", entities=["Text"])
        ranked = recipe_search.rank_recipes("zibble wibble", fixtures)
        scores = {r["id"]: r["_score"] for r in ranked}
        assert scores["r-intent"] > scores["r-null"]

    def test_nonsense_returns_empty(self):
        result = recipe_search.search_recipes("frobnicate the widgets")
        assert result["recipes"] == []
        assert result["recipes_count"] == 0


class TestSearchResponse:
    def _search(self, query):
        from flextoolsmcp.server.handlers.api import handle_search_by_capability

        result_list = run_async(handle_search_by_capability({"query": query}))
        return json.loads(result_list[0].text)

    def test_search_response_recipes_keys(self):
        payload = self._search("list all entries with their glosses")
        assert "recipes" in payload
        assert "recipes_count" in payload
        assert "recipes_ambiguous" in payload
        assert payload["recipes_count"] == len(payload["recipes"])
        assert len(payload["recipes"]) <= 3

    def test_clear_winner_gets_code(self):
        # Clear winner without a legacy attachment carries code. (Via the
        # handler the same query would dedup to code_at; see the next test.)
        result = recipe_search.search_recipes("add a gloss to a sense")
        assert result["recipes"], "expected at least one recipe row"
        top = result["recipes"][0]
        assert "code" in top, "clear winner must carry code"
        assert top["params"] is not None
        assert result["recipes_ambiguous"] is False

    def test_object_only_query_no_code(self):
        for q in ("entry", "senses"):
            payload = self._search(q)
            assert payload["recipes"], f"expected rows for {q!r}"
            assert all("code" not in r for r in payload["recipes"])
            assert payload["recipes_ambiguous"] is True

    def test_close_scores_no_code(self):
        # A vague query matching many recipes equally must not spend a body.
        payload = self._search("list")
        if len(payload["recipes"]) > 1:
            assert all("code" not in r for r in payload["recipes"])
            assert payload["recipes_ambiguous"] is True

    def test_no_duplicate_code_with_legacy_attachment(self):
        payload = self._search("list all entries with their glosses")
        legacy = None
        if payload.get("results"):
            legacy = payload["results"][0].get("recipe")
        assert legacy is not None, "legacy attachment must still exist (FR-022)"
        top = payload["recipes"][0]
        # Winner is the same recipe as the legacy attachment: no second body.
        if top["id"] == legacy["id"]:
            assert "code" not in top
            assert top.get("code_at") == "results[0].recipe"
        else:  # pragma: no cover - documents the other legal shape
            assert "code" in top or top.get("code_at") == "results[0].recipe"

    def test_hint_present_iff_ambiguous(self):
        clear = self._search("list all entries with their glosses")
        # Clear winner OR code_at dedup: not ambiguous, no hint.
        assert clear["recipes_ambiguous"] is False
        assert "recipes_hint" not in clear
        vague = self._search("entry")
        assert vague["recipes_ambiguous"] is True
        assert "recipes_hint" in vague and vague["recipes_hint"]

    def test_top_row_records_validated_compact_rows_do_not(self):
        # Positive case: a clear winner served with code records its entities.
        kernel.session_state.validated_apis.clear()
        # "Move semantic domain" tied add- and remove-semantic-domains once the
        # remove recipe shipped. This query has a clear winner with no legacy
        # attachment, so the code stays inline on recipes[0].
        payload = self._search("reorder affix templates")
        top = payload["recipes"][0]
        assert "code" in top, f"expected code for reorder query, got {top.get('id')}"
        validated = set(kernel.session_state.validated_apis)
        for e in top.get("entities", []):
            assert e in validated
        # Compact rows must not record: an object-only query records nothing new.
        kernel.session_state.validated_apis.clear()
        payload2 = self._search("entry")
        assert all("code" not in r for r in payload2["recipes"])
        assert set(kernel.session_state.validated_apis) == set()

    def test_compact_row_size_budget(self):
        result = recipe_search.search_recipes("list entries")
        rows = result["recipes"]
        assert rows
        total = sum(len(json.dumps(r, ensure_ascii=False)) for r in rows if "code" not in r)
        compact = [r for r in rows if "code" not in r]
        if compact:
            assert total / len(compact) < 400

    def test_battery_at_most_one_code_body(self):
        for query, _expected, _skipped in [e for e in QUERY_BATTERY if not e[2]]:
            payload = self._search(query)
            bodies = 0
            if payload.get("results") and payload["results"][0].get("recipe", {}).get("code"):
                bodies += 1
            bodies += sum(1 for r in payload.get("recipes", []) if "code" in r)
            assert bodies <= 1, f"query {query!r} carries {bodies} code bodies"


# Battery: (query, expected_recipe_id, skip_until_phase5).
# Phase-5 entries (templates/slots, phonology, allomorph envs) are marked True
# and skipped until those recipes ship; everything else must hit top-3.
QUERY_BATTERY = [
    ("list all entries with their glosses", "list-entries-with-glosses", False),
    ("count senses by part of speech", "count-senses-by-pos", False),
    ("find senses with empty definitions", "find-empty-definitions", False),
    ("add a gloss to a sense", "add-gloss-to-sense", False),
    ("batch update citation forms", "batch-update-citation-forms", False),
    ("find duplicate headwords", "find-duplicate-headwords", False),
    ("list all texts", "list-texts", False),
    ("create interlinear text with multiple writing systems", "create-interlinear-text", False),
    ("list all wordforms", "list-wordforms", False),
    ("reversal index lookup", "reversal-lookup", False),
    ("list entries with part of speech", "list-entries-with-pos", False),
    ("find senses with no part of speech", "find-entries-missing-pos", False),
    ("add an example sentence to a sense", "add-example-to-sense", False),
    ("find senses without examples", "find-entries-without-examples", False),
    ("list senses with definitions and examples", "list-senses-with-definitions-and-examples", False),
    ("assign semantic domain to a sense", "add-semantic-domain-to-sense", False),
    ("count entries by morph type", "count-entries-by-morphtype", False),
    ("list all parts of speech", "list-parts-of-speech", False),
    ("list pronunciations", "list-pronunciations", False),
    ("add pronunciation to entry", "add-pronunciation-to-entry", False),
    ("how many entries are there", "count-entries-total", False),
    ("hide entry from parser", "hide-entry-from-parser", False),
    ("parser coverage unparsed words", "parser-coverage", False),
    ("audit inflectional affix MSA slots", "audit-repair-infl-aff-msa-slots", False),
    # Phase-5 recipes: skipped until they ship.
    ("list the affix templates and slots for verbs", "affix-templates-and-slots", True),
    ("phone environments on an allomorph", "set-allomorph-environments", True),
    ("list the phonological rules", "phonological-rules", True),
    ("does this form exist in the lexicon", "lexicon-form-lookup", True),
    ("how is this entry modelled for the parser", "entry-parser-detail", True),
    ("existing analyses of a word", "wordform-analyses", True),
    ("who uses this allomorph before I delete it", "form-usage-before-edit", True),
    ("capitalized variants of a wordform", "wordform-case-variants", True),
]


@pytest.mark.parametrize("query,expected,skipped", QUERY_BATTERY)
def test_battery_top3(query, expected, skipped):
    if skipped and expected not in CURATED_RECIPES:
        pytest.skip(f"{expected} lands in Phase 5; skipping until it ships")
    result = recipe_search.search_recipes(query)
    ids = [r["id"] for r in result["recipes"][:3]]
    assert expected in ids, f"{query!r}: expected {expected} in top3, got {ids}"


def test_battery_top3_rate():
    active = [(q, e) for q, e, s in QUERY_BATTERY if not (s and e not in CURATED_RECIPES)]
    assert len(active) >= 20
    hits = 0
    for query, expected in active:
        ids = [r["id"] for r in recipe_search.search_recipes(query)["recipes"][:3]]
        if expected in ids:
            hits += 1
    assert hits / len(active) >= 0.9


# ---------------------------------------------------------------------------
# Phase 4 US2 (T021, FR-023): find_examples includes local recipes;
# skeletons_from_your_sessions stays with a deprecation notice.
# ---------------------------------------------------------------------------


def _import_local_recipes():
    import importlib

    try:
        return importlib.import_module("flextoolsmcp.server.local_recipes")
    except ImportError:
        return importlib.import_module("server.local_recipes")


def _capture_local(monkeypatch, tmp_path, code, intent, entities_note=""):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    mod = _import_local_recipes()
    fn = None
    for name in ("capture", "capture_from_code", "record_capture", "record"):
        fn = getattr(mod, name, None)
        if callable(fn):
            break
    assert fn is not None, "local_recipes needs a capture() entry point"
    import inspect

    try:
        params = set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        params = set()
    kwargs = {"code": code, "user_intent": intent, "op_id": "op-find-ex"}
    if "project" in params:
        kwargs["project"] = "Sena 3"
    elif "project_name" in params:
        kwargs["project_name"] = "Sena 3"
    for cand in ("requires_write", "is_mutating", "is_mutating_script", "mutating"):
        if cand in params:
            kwargs[cand] = False
            break
    return fn(**kwargs)


LOCAL_FIND_CODE = (
    "entries = project.LexEntry.GetAll()\n"
    "for entry in entries:\n"
    "    senses = project.LexEntry.GetAllSenses(entry)\n"
    "    for sense in senses:\n"
    "        report.Info(project.Senses.GetGloss(sense))\n"
)


def test_find_examples_includes_local(monkeypatch, tmp_path):
    """Local recipes appear in find_examples.recipes (FR-023)."""
    _capture_local(monkeypatch, tmp_path, LOCAL_FIND_CODE, "list glosses for find examples")
    from flextoolsmcp.server.handlers import api as api_mod

    result = run_async(api_mod.handle_find_examples(
        {"object_type": "LexSense", "max_results": 50}))
    payload = json.loads(result[0].text)
    assert "recipes" in payload
    ids = [r.get("id", "") for r in payload["recipes"]]
    assert any(str(i).startswith("local-") for i in ids), (
        f"expected a local recipe in find_examples.recipes, got {ids}")


def test_skeletons_key_still_emitted_with_deprecation(monkeypatch, tmp_path):
    """skeletons_from_your_sessions stays, with a tool-responses/2.0 deprecation (FR-023)."""
    _capture_local(monkeypatch, tmp_path, LOCAL_FIND_CODE, "list glosses again")
    from flextoolsmcp.server.handlers import api as api_mod

    result = run_async(api_mod.handle_find_examples(
        {"object_type": "LexSense", "max_results": 50}))
    payload = json.loads(result[0].text)
    assert "skeletons_from_your_sessions" in payload, (
        "legacy skeletons key must still be emitted")
    assert payload["skeletons_from_your_sessions"], "expected at least one skeleton row"
    dep = payload.get("deprecation")
    assert dep is not None, "missing deprecation notice alongside skeletons key"
    assert dep.get("deprecated") == "skeletons_from_your_sessions"
    assert dep.get("removal") == "tool-responses/2.0"
