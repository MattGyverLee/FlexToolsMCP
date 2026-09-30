#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #312: search_by_capability surfaces MCP tools (flextools_try_word, the
parse family, grammar_health) and adds a zero-result fallback listing every
MCP tool plus a recipe-library pointer.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel
from flextoolsmcp.server import tool_search
from flextoolsmcp.server.tool_definitions import TOOLS


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _tool_names(rows):
    return [r["tool"] for r in rows]


# --------------------------------------------------------------------------
# find_mcp_tools unit tests
# --------------------------------------------------------------------------

class TestFindMcpTools:
    @pytest.mark.parametrize("query", [
        "try_word method",
        "ParserOperations.TryWord",
        "TryWord",
        "tryword",
        "flextools_try_word",
    ])
    def test_try_word_spellings(self, query):
        rows = tool_search.find_mcp_tools(query)
        assert rows and rows[0]["tool"] == "flextools_try_word", rows

    def test_unparsed_wordforms_hits_parse_family(self):
        names = _tool_names(tool_search.find_mcp_tools("get top 10 unparsed wordforms"))
        assert "flextools_parse_text" in names
        assert all(n.startswith("flextools_parse_") or n == "flextools_try_word"
                   for n in names), names

    def test_grammar_slow_hits_grammar_health(self):
        names = _tool_names(tool_search.find_mcp_tools("my grammar is slow"))
        assert names[:1] == ["flextools_grammar_health"]

    def test_sandbox_hits_parse_sandbox(self):
        names = _tool_names(tool_search.find_mcp_tools("test a grammar change in a sandbox"))
        assert names[0] == "flextools_parse_sandbox"

    @pytest.mark.parametrize("query", [
        "add a gloss to a sense",
        "list all entries with their glosses",
        "delete a sense",
        "set the part of speech",
        "",
    ])
    def test_ordinary_api_queries_hit_no_tool(self, query):
        assert tool_search.find_mcp_tools(query) == []

    def test_row_shape(self):
        row = tool_search.find_mcp_tools("try_word")[0]
        assert set(row) == {"tool", "summary", "note"}
        assert row["summary"].startswith("[PARSE]")
        assert "MCP tool" in row["note"]
        assert "not a Flexicon" in row["note"]

    def test_max_results(self):
        assert len(tool_search.find_mcp_tools("parse parser parsing", max_results=2)) == 2

    def test_excluded_tools_never_returned(self):
        for q in ("search by capability", "list skeletons", "skeleton"):
            names = _tool_names(tool_search.find_mcp_tools(q, max_results=10))
            assert "flextools_search_by_capability" not in names
            assert "flextools_list_skeletons" not in names

    def test_list_mcp_tools_catalog(self):
        rows = tool_search.list_mcp_tools()
        names = _tool_names(rows)
        assert "flextools_try_word" in names
        assert "flextools_list_recipes" in names
        assert "flextools_search_by_capability" not in names
        assert "flextools_list_skeletons" not in names
        assert len(names) == len(TOOLS) - 2
        assert all(set(r) == {"tool", "summary"} and r["summary"] for r in rows)

    def test_every_tool_name_reachable_by_its_own_name(self):
        # Guards against a future tool whose name tokens are all stopwords/
        # generic -- each visible tool must be findable by its exact name.
        for row in tool_search.list_mcp_tools():
            names = _tool_names(tool_search.find_mcp_tools(row["tool"], max_results=10))
            assert row["tool"] in names, row["tool"]


# --------------------------------------------------------------------------
# Handler integration
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_index():
    from flextoolsmcp.server import APIIndex, get_index_dir

    return APIIndex.load(get_index_dir())


@pytest.fixture(autouse=True)
def _configure_session(request, tmp_path, monkeypatch):
    if request.cls is not TestSearchHandler:
        yield
        return
    kernel.set_api_index(request.getfixturevalue("api_index"))
    kernel.session_state.configure(session_id="test-tool-search", api_mode="flexicon")
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path / "empty-recipes"))
    yield


class TestSearchHandler:
    def _search(self, query, **extra):
        from flextoolsmcp.server.handlers.api import handle_search_by_capability

        args = {"query": query, "semantic": False}
        args.update(extra)
        return json.loads(run_async(handle_search_by_capability(args))[0].text)

    def test_try_word_method_surfaces_tool(self):
        payload = self._search("try_word method")
        assert "flextools_try_word" in _tool_names(payload["mcp_tools"])

    def test_parser_operations_try_word_surfaces_tool(self):
        payload = self._search("ParserOperations.TryWord")
        assert payload["mcp_tools"][0]["tool"] == "flextools_try_word"

    def test_unparsed_wordforms_surfaces_parse_tool_and_recipe(self):
        payload = self._search("get top 10 unparsed wordforms")
        assert "flextools_parse_text" in _tool_names(payload["mcp_tools"])
        assert "parser-coverage" in [r.get("id") for r in payload["recipes"]]

    def test_nonsense_query_gets_zero_result_fallback(self):
        payload = self._search("zzqxv flurbnog")
        assert payload["results_count"] == 0
        fb = payload["zero_result_fallback"]
        names = _tool_names(fb["mcp_tools"])
        assert "flextools_try_word" in names
        assert "flextools_list_recipes" in names
        assert "flextools_search_by_capability" not in names
        assert "flextools_list_recipes" in fb["recipes_hint"]
        assert fb["message"]
        # Existing keys untouched.
        assert payload["recipes"] == [] and payload["recipes_count"] == 0
        assert "mcp_tools" not in payload

    def test_ordinary_api_query_has_no_fallback_or_tools(self):
        payload = self._search("add a gloss to a sense")
        assert payload["results_count"] > 0
        assert "zero_result_fallback" not in payload
        assert "mcp_tools" not in payload
