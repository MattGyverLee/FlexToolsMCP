#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #335: library recipes were never used.

In the 2026-09-30 Claude-Swahili sessions `flextools_list_recipes` was called
0 times and 0 of 26 `run_module` calls started from a recipe; recipes only
appeared nested under `results[0].recipe` / `recipes`, which the model read
past. Now:

- search_by_capability returns a top-level `recommended_recipe` ahead of the
  API hits when one shipped recipe clearly wins the query;
- run_module failure responses name the closest recipes in `next_steps` on
  `partial_module_structure` / `casting_issues_detected` rejects and on the
  2nd consecutive failure with the same `user_intent`;
- run_module adds a non-blocking `recipe_hint` when `user_intent` matches a
  library recipe the code is not from;
- a run that called report.Error is not remembered as a local-* recipe
  (failed runs never were).

No live FLEx: the subprocess is stubbed.
"""

import asyncio
import json

import pytest

from flextoolsmcp.curated_recipes import CURATED_RECIPES
from flextoolsmcp.response_utils import error_response
from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server import recipes as recipe_search
from flextoolsmcp.server.handlers import execution as execution_mod
session_state = kernel.session_state


def _parse(response):
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# recommend_recipe (pure)
# ---------------------------------------------------------------------------

class TestRecommendRecipe:
    @pytest.mark.parametrize("query,expected", [
        # The API-shaped queries from the 2026-09-30 logs.
        ("create a new lexical entry", "create-entries-idempotent"),
        ("find or create a lexentry by headword", "ensure-morpheme-entries"),
        ("parse a wordform and get morphological decomposition", "wordform-analyses"),
        ("list entries", "list-entries-with-glosses"),
        ("find empty definitions", "find-empty-definitions"),
    ])
    def test_clear_winner_is_recommended(self, query, expected):
        rec = recipe_search.recommend_recipe(query)
        assert rec is not None
        assert rec["id"] == expected

    @pytest.mark.parametrize("query", [
        "entry",               # object-only
        "get gloss of sense",  # tie between two recipes
        "zibble wobble",       # nothing
        "",
    ])
    def test_no_clear_winner_is_not_recommended(self, query):
        assert recipe_search.recommend_recipe(query) is None

    @pytest.mark.parametrize("query", [
        "delete duplicate entries",
        "merge duplicate entries",
    ])
    def test_write_intent_never_gets_a_read_only_recipe(self, query):
        # Review of #335: a phrase hit on find-duplicate-headwords used to win.
        assert recipe_search.recommend_recipe(query) is None
        assert recipe_search.recipe_hint_for_run(query, HAND_WRITTEN) is None

    def test_shape_has_no_code(self):
        rec = recipe_search.recommend_recipe("list entries")
        assert list(rec) == ["id", "intent", "params", "requires_write", "how_to_run"]
        assert "code" not in rec
        assert rec["intent"] == CURATED_RECIPES[rec["id"]]["intent"]
        assert f'recipe_id="{rec["id"]}"' in rec["how_to_run"]
        assert 'source="existing"' in rec["how_to_run"]
        assert "dry-run" not in rec["how_to_run"]

    def test_write_recipe_how_to_run_names_the_dry_run(self):
        rec = recipe_search.recommend_recipe("create a new lexical entry")
        assert rec["requires_write"] is True
        assert "dry-run first" in rec["how_to_run"]
        assert "confirmed=True" in rec["how_to_run"]

    def test_local_recipes_are_never_recommended(self, monkeypatch):
        local = {
            "id": "local-abc", "intent": "frobnicate the zibble lexicon",
            "match_terms": ["frobnicate zibble"], "entities": ["LexEntry"],
            "code": "x = 1\n", "source": "local", "use_count": 50,
        }
        monkeypatch.setattr(recipe_search, "_LOCAL_PROVIDER", lambda: [local])
        assert recipe_search.recommend_recipe("frobnicate the zibble lexicon") is None


# ---------------------------------------------------------------------------
# closest_recipes (pure)
# ---------------------------------------------------------------------------

class TestClosestRecipes:
    def test_by_intent(self):
        rows = recipe_search.closest_recipes("create a new lexical entry", 3)
        assert 1 <= len(rows) <= 3
        assert rows[0]["id"] == "create-entries-idempotent"
        for row in rows:
            assert set(row) == {"id", "intent", "requires_write", "score"}

    def test_by_code(self):
        code = (
            "for e in project.LexEntry.GetAll():\n"
            "    for s in project.LexEntry.GetAllSenses(e):\n"
            "        report.Info(project.Senses.GetGloss(s))\n"
        )
        rows = recipe_search.closest_recipes(code, 3)
        assert rows and rows[0]["id"] == "list-entries-with-glosses"

    def test_k_and_nothing(self):
        assert len(recipe_search.closest_recipes("list entries", 1)) == 1
        assert recipe_search.closest_recipes("zibble wobble", 3) == []
        assert recipe_search.closest_recipes_step("zibble wobble") is None

    def test_step_text(self):
        step = recipe_search.closest_recipes_step("list entries")
        assert step.startswith("closest recipes: list-entries-with-glosses")
        assert "flextools_list_recipes" in step


# ---------------------------------------------------------------------------
# recipe_hint_for_run (pure)
# ---------------------------------------------------------------------------

HAND_WRITTEN = (
    "count = 0\n"
    "for entry in project.LexEntry.GetAll():\n"
    "    count += 1\n"
    "    report.Info(project.LexEntry.GetHeadword(entry))\n"
)


class TestRecipeHint:
    def test_hint_when_code_is_not_from_the_recipe(self):
        hint = recipe_search.recipe_hint_for_run("list entries", HAND_WRITTEN)
        assert hint["id"] == "list-entries-with-glosses"
        assert set(hint) == {"id", "intent", "requires_write", "how_to_run", "message"}

    def test_no_hint_when_code_is_the_recipe(self):
        code = CURATED_RECIPES["list-entries-with-glosses"]["code"]
        assert recipe_search.recipe_hint_for_run("list entries", code) is None

    def test_no_hint_when_only_params_changed(self):
        recipe = CURATED_RECIPES["ensure-morpheme-entries"]
        code = recipe["code"]
        start = code.index("# --- PARAMS ---")
        end = code.index("# --- END PARAMS ---")
        edited = code[:start] + "# --- PARAMS ---\nMORPHEMES = ['ku-', '-a']\n" + code[end:]
        assert recipe_search.code_is_from_recipe(edited, recipe)
        assert recipe_search.recipe_hint_for_run(
            "find or create a lexentry by headword", edited) is None

    def test_no_hint_without_a_strong_intent(self):
        assert recipe_search.recipe_hint_for_run(None, HAND_WRITTEN) is None
        assert recipe_search.recipe_hint_for_run("  ", HAND_WRITTEN) is None
        assert recipe_search.recipe_hint_for_run("entry", HAND_WRITTEN) is None


# ---------------------------------------------------------------------------
# Failure next_steps via the shared failure wrapper
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_session():
    session_state.reset()
    yield session_state
    session_state.reset()


def _wrap(response, error_code, intent=None, code=""):
    token = execution_mod._RUN_RECIPE_CONTEXT.set(
        {"user_intent": intent, "code": code, "recipe_hint": None})
    try:
        return _parse(execution_mod._attach_assistance_if_loop(
            response, error_code=error_code, code_size_bytes=len(code)))
    finally:
        execution_mod._RUN_RECIPE_CONTEXT.reset(token)


class TestFailureNextSteps:
    def test_partial_module_structure_lists_closest_recipes(self, fresh_session):
        data = _wrap(
            error_response("partial_module_structure", "half a module",
                           next_steps=["pass skip_module_check=True"]),
            "partial_module_structure", intent="list entries")
        assert data["next_steps"][0] == "pass skip_module_check=True"
        assert data["next_steps"][-1].startswith("closest recipes: list-entries-with-glosses")
        assert data["closest_recipes"][0]["id"] == "list-entries-with-glosses"

    def test_casting_string_next_steps_stays_a_string(self, fresh_session):
        data = _wrap(
            error_response("casting_issues_detected", "cast it",
                           next_steps="Cast to ILexEntry first."),
            "casting_issues_detected", code=HAND_WRITTEN)
        assert isinstance(data["next_steps"], str)
        assert data["next_steps"].startswith("Cast to ILexEntry first.\nclosest recipes: ")
        assert data["closest_recipes"]

    def test_other_rejects_wait_for_the_second_same_intent_failure(self, fresh_session):
        def _fail(intent):
            return _wrap(error_response("runtime_error", "boom", next_steps=["fix it"]),
                         "runtime_error", intent=intent)

        first = _fail("list entries")
        assert "closest_recipes" not in first
        assert first["next_steps"] == ["fix it"]
        second = _fail("List  entries")  # same intent, normalized
        assert second["next_steps"][-1].startswith("closest recipes: ")
        # A different intent restarts the streak.
        assert "closest_recipes" not in _fail("count senses by pos")

    def test_success_resets_the_streak(self, fresh_session):
        _wrap(error_response("runtime_error", "boom"), "runtime_error", intent="list entries")
        session_state.reset_op_signals()
        data = _wrap(error_response("runtime_error", "boom"), "runtime_error",
                     intent="list entries")
        assert "closest_recipes" not in data

    @pytest.mark.parametrize("non_code", [
        "project_locked", "confirmation_required", "server_state_error",
    ])
    def test_non_code_failures_do_not_streak(self, fresh_session, non_code):
        intent = "add a gloss to a sense"
        for _ in range(3):
            data = _wrap(error_response(non_code, "not the code"), non_code,
                         intent=intent)
            assert "closest_recipes" not in data
        # ...and they do not count: one code failure after them is still #1.
        data = _wrap(error_response("runtime_error", "boom"), "runtime_error",
                     intent=intent)
        assert "closest_recipes" not in data

    def test_confirm_then_lock_on_a_recipe_run_has_no_pointer(self, fresh_session):
        # Review of #335: the recipe-following write flow.
        code = CURATED_RECIPES["add-gloss-to-sense"]["code"]
        intent = "add a gloss to a sense"
        first = _wrap(error_response("confirmation_required", "confirm"),
                      "confirmation_required", intent=intent, code=code)
        second = _wrap(error_response("project_locked", "locked"),
                       "project_locked", intent=intent, code=code)
        assert "closest_recipes" not in first
        assert "closest_recipes" not in second

    def test_pointer_leaves_out_the_recipe_the_code_is_from(self, fresh_session):
        code = CURATED_RECIPES["add-gloss-to-sense"]["code"]
        intent = "add a gloss to a sense"
        for _ in range(2):
            data = _wrap(error_response("runtime_error", "boom"), "runtime_error",
                         intent=intent, code=code)
        ids = [row["id"] for row in data.get("closest_recipes", [])]
        assert "add-gloss-to-sense" not in ids
        steps = data.get("next_steps") or []
        assert not any("add-gloss-to-sense" in s for s in steps)

    def test_legacy_error_object_mirrors_the_pointer(self, fresh_session):
        data = _wrap(
            error_response("casting_issues_detected", "m", next_steps="do x"),
            "casting_issues_detected", intent="list entries")
        assert data["error"]["next_steps"] == data["next_steps"]
        assert data["error"]["closest_recipes"] == data["closest_recipes"]

    def test_no_intent_never_streaks(self, fresh_session):
        for _ in range(3):
            data = _wrap(error_response("runtime_error", "boom"), "runtime_error",
                         code=HAND_WRITTEN)
        assert "closest_recipes" not in data


# ---------------------------------------------------------------------------
# Handler level: search_by_capability
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_index():
    from flextoolsmcp.server import APIIndex, get_index_dir

    return APIIndex.load(get_index_dir())


class TestSearchByCapability:
    @pytest.fixture(autouse=True)
    def _session(self, api_index, tmp_path, monkeypatch):
        kernel.set_api_index(api_index)
        kernel.session_state.configure(session_id="test-335", api_mode="flexicon")
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path / "empty-recipes"))
        yield

    def _search(self, query):
        from flextoolsmcp.server.handlers.api import handle_search_by_capability
        return _parse(asyncio.run(handle_search_by_capability({"query": query})))

    def test_recommended_recipe_comes_before_results(self):
        data = self._search("create a new lexical entry")
        rec = data["recommended_recipe"]
        assert rec["id"] == "create-entries-idempotent"
        assert "code" not in rec
        keys = list(data)
        assert keys.index("recommended_recipe") < keys.index("results")
        assert keys.index("recommended_recipe") < keys.index("recipes")
        # Existing keys unchanged.
        assert "recipes" in data and "results" in data

    def test_absent_without_a_clear_winner(self):
        data = self._search("entry")
        assert "recommended_recipe" not in data

    def test_at_most_one_code_body(self):
        data = self._search("create a new lexical entry")
        bodies = 0
        if data["results"] and "code" in (data["results"][0].get("recipe") or {}):
            bodies += 1
        bodies += sum(1 for r in data["recipes"] if "code" in r)
        assert bodies <= 1


# ---------------------------------------------------------------------------
# Handler level: run_module (subprocess stubbed)
# ---------------------------------------------------------------------------

class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _stub_env(monkeypatch, tmp_path, runner_payload):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path / "recipes"))
    monkeypatch.delenv("FLEXTOOLSMCP_SKELETON_DIR", raising=False)
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state",
                        lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
            "confidence": "high",
        },
    )
    monkeypatch.setattr(execution_mod, "detect_cud_operations",
                        lambda code: {"is_cud": False, "operations": []})
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs",
        lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []},
    )
    monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())

    async def _fake_run(path, timeout_seconds):
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(runner_payload),
            "stderr": "",
            "timeout": False,
            "returncode": 0,
        }

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)


def _run(intent, code=HAND_WRITTEN):
    return _parse(asyncio.run(execution_mod.handle_run_module({
        "code": code,
        "project_name": "TestProj_335",
        "user_intent": intent,
        "skip_api_check": True,
        "skip_module_check": True,
    })))


def _stored_recipes(tmp_path):
    path = tmp_path / "recipes" / "recipes.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


_INFO = [{"type": "INFO", "message": "alpha"}, {"type": "INFO", "message": "beta"}]
_SUMMARY = {"info_count": 2, "warning_count": 0, "error_count": 0}


class TestRunModule:
    def test_success_carries_recipe_hint_and_is_remembered(self, monkeypatch, tmp_path,
                                                           fresh_session):
        _stub_env(monkeypatch, tmp_path, {
            "success": True, "messages": _INFO, "summary": _SUMMARY})
        data = _run("list entries")
        assert data["status"] == "ok"
        assert data["recipe_hint"]["id"] == "list-entries-with-glosses"
        assert [r["intent"] for r in _stored_recipes(tmp_path)] == ["list entries"]

    def test_no_hint_when_running_the_recipe(self, monkeypatch, tmp_path, fresh_session):
        _stub_env(monkeypatch, tmp_path, {
            "success": True, "messages": _INFO, "summary": _SUMMARY})
        data = _run("list entries",
                    code=CURATED_RECIPES["list-entries-with-glosses"]["code"])
        assert "recipe_hint" not in data

    def test_failed_run_is_not_remembered(self, monkeypatch, tmp_path, fresh_session):
        _stub_env(monkeypatch, tmp_path, {
            "success": False, "error": "Execution error: boom",
            "messages": _INFO, "summary": _SUMMARY})
        data = _run("list entries")
        assert data["status"] == "error"
        assert data["recipe_hint"]["id"] == "list-entries-with-glosses"
        assert _stored_recipes(tmp_path) == []

    def test_run_that_reported_errors_is_not_remembered(self, monkeypatch, tmp_path,
                                                        fresh_session):
        _stub_env(monkeypatch, tmp_path, {
            "success": True,
            "messages": _INFO + [{"type": "ERROR", "message": "could not create ku-"}],
            "summary": {"info_count": 2, "warning_count": 0, "error_count": 1}})
        data = _run("make the morpheme entries")
        assert data["status"] == "ok"
        assert _stored_recipes(tmp_path) == []

    def test_second_same_intent_runtime_failure_lists_closest_recipes(
            self, monkeypatch, tmp_path, fresh_session):
        _stub_env(monkeypatch, tmp_path, {
            "success": False, "error": "Execution error: boom",
            "messages": [], "summary": _SUMMARY})
        first = _run("list entries")
        assert "closest_recipes" not in first
        second = _run("list entries")
        assert second["closest_recipes"][0]["id"] == "list-entries-with-glosses"
        assert any(str(s).startswith("closest recipes: ")
                   for s in second["next_steps"])
