#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #85: `flextools_get_navigation_path` fails on EVERY call
with "'dict' object has no attribute 'from_object'".

Root cause: dispatch at src/flextoolsmcp/server.py always calls
`await handler(dumped)` where `dumped = validated_args.model_dump()` -- a
plain dict, never the pydantic model. `handle_get_navigation_path` was the
only handler in the package that assumed it received the pydantic
`GetNavigationPathInput` object (`args.from_object` / `args.to_object`)
instead of a dict (`args.get("from_object")` / `args.get("to_object")`),
matching every sibling handler.

This file covers:
  1. The dispatch path actually invoking the handler with a dict -- this
     had ZERO coverage before, which is exactly how the bug shipped.
  2. A direct-call regression test locking the dict-based access pattern.
  3. Nav-path smoke tests against the shipped navigation graph, covering two
     DIFFERENT outcomes now that the find_path_bfs() reconstruction bug
     (D2, commit 2053e12) is fixed:
       - IFsFeatStruc -> IFsFeatDefn: a real 2-hop path exists in the graph
         data (IFsFeatStruc --FeatureSpecsOC--> IFsFeatureSpecification
         --FeatureRA--> IFsFeatDefn) and now RESOLVES correctly.
       - ILexSense -> IFsSymFeatVal: no edge exists in the graph at all.
         MsFeaturesOA lives on the concrete IMoStemMsa, not the base
         IMoMorphSynAnalysis that the graph walks through, so there is no
         edge to follow -- this needs a downcast edge (CP3 scope, issue
         #86), not a BFS fix. found:false here is CORRECT, not a bug.
  4. A minimal unit test isolating find_path_bfs() itself, showing it now
     correctly reconstructs both a direct edge and a two-hop path.
"""

import asyncio
import json
from functools import lru_cache
from pathlib import Path

import pytest


def run_async(coro):
    """Run an async coroutine synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@lru_cache(maxsize=1)
def _get_srv():
    """Load server.py directly via importlib (mirrors tests/test_mcp_tools.py)."""
    import importlib.util

    server_py = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_server_module_issue85", str(server_py))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec from {server_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def srv():
    """A server module instance with a real api_index loaded (navigation
    graph lives on the api_index, not the session)."""
    from server import APIIndex  # type: ignore
    from server.kernel import initialize_kernel, set_api_index, get_index_dir  # type: ignore

    initialize_kernel()
    set_api_index(APIIndex.load(get_index_dir()))
    return _get_srv()


@pytest.fixture(autouse=True)
def _reset_session(srv):
    """flextools_get_navigation_path is READ_ONLY_SAFE and auto-inits on a
    cold session (issue #53), but reset between tests so state doesn't leak."""
    from server.session import SessionState  # type: ignore

    srv.session_state = SessionState()  # type: ignore
    yield


def _call(srv, arguments):
    return run_async(srv.call_tool("flextools_get_navigation_path", arguments))


def _parse(result):
    assert len(result) > 0, "Empty response"
    return json.loads(result[0].text)


# ---------------------------------------------------------------------------
# 1. Dispatch path: the actual bug. Before the fix this raised
#    "'dict' object has no attribute 'from_object'" for EVERY call.
# ---------------------------------------------------------------------------

class TestDispatchInvokesHandlerWithDict:
    def test_call_tool_does_not_raise_attributeerror(self, srv):
        """This is the exact repro for issue #85: going through the real
        call_tool() dispatch (validate -> model_dump() -> handler(dict)),
        not calling the handler function directly."""
        result = _call(srv, {"from_object": "ILexEntry", "to_object": "ILexSense"})
        parsed = _parse(result)
        # The bug manifested as a bare string reply containing the
        # AttributeError text (see issue #85's draft follow-up issue about
        # server.py:986 lacking a try/except). Assert it is genuinely gone.
        assert "from_object" not in json.dumps(parsed) or "has no attribute" not in json.dumps(parsed)
        assert "AttributeError" not in result[0].text
        assert "has no attribute 'from_object'" not in result[0].text

    def test_dispatch_returns_structured_result_not_error_string(self, srv):
        result = _call(srv, {"from_object": "ILexEntry", "to_object": "ILexSense"})
        parsed = _parse(result)
        # Regardless of whether a path is found, the response must be the
        # structured envelope, not a crash message.
        assert "from" in parsed
        assert "to" in parsed
        assert "found" in parsed


# ---------------------------------------------------------------------------
# 2. Direct-call regression: locks the dict-based access pattern itself,
#    matching every sibling handler in the package (args.get(...), not
#    args.<attr>).
# ---------------------------------------------------------------------------

class TestHandlerAcceptsPlainDict:
    def test_handler_called_with_plain_dict_directly(self, srv):
        from server.handlers.discovery import handle_get_navigation_path

        args = {"from_object": "ILexEntry", "to_object": "ILexSense"}
        assert isinstance(args, dict)
        result = run_async(handle_get_navigation_path(args))
        parsed = _parse(result)
        assert parsed["from"] == "ILexEntry"
        assert parsed["to"] == "ILexSense"


# ---------------------------------------------------------------------------
# 3. Nav-path smoke tests against the shipped navigation graph.
# ---------------------------------------------------------------------------

class TestNavigationGraphSmoke:
    def test_known_good_query_now_resolves_via_bfs(self, srv):
        """IFsFeatStruc -> IFsFeatDefn has a genuine 2-hop path in the raw
        graph data (IFsFeatStruc --FeatureSpecsOC--> IFsFeatureSpecification
        --FeatureRA--> IFsFeatDefn; confirmed by an independent BFS replay
        of navigation_graph_liblcm-v11.0.0.json). It was previously masked
        by a second, pre-existing defect (D2): the "Wave 3 Efficiency"
        parent-tracking rewrite (commit 2053e12) never recorded
        `parent[end]` before reconstructing the path, so `while node in
        parent` at the target immediately failed and every multi-hop (and
        even direct-edge) match reconstructed to an empty path --
        indistinguishable from "no path found" to the caller. This bug was
        invisible until #85's AttributeError fix let the BFS branch
        actually run live.

        Now that D2 is fixed (find_path_bfs() seeds the path with the
        final edge before walking `parent` backwards from `current`), this
        query correctly resolves to the genuine 2-hop path.
        """
        result = _call(srv, {"from_object": "IFsFeatStruc", "to_object": "IFsFeatDefn"})
        parsed = _parse(result)
        assert parsed["found"] is True, parsed
        assert parsed["source"] == "computed"
        steps = parsed["steps"]
        assert len(steps) == 2, steps
        assert steps[0]["from"] == "IFsFeatStruc"
        assert steps[0]["to"] == "IFsFeatureSpecification"
        assert steps[0]["via"] == "FeatureSpecsOC"
        assert steps[1]["from"] == "IFsFeatureSpecification"
        assert steps[1]["to"] == "IFsFeatDefn"
        assert steps[1]["via"] == "FeatureRA"

    def test_missing_downcast_edge_still_not_found(self, srv):
        """ILexSense -> IFsSymFeatVal is NOT reachable in the current graph,
        and this is CORRECT -- not a symptom of the D2 BFS bug. MsFeaturesOA
        lives on the concrete IMoStemMsa, not the base IMoMorphSynAnalysis
        that the graph walks through, so there genuinely is no edge to
        follow. Reaching it requires a downcast/`required_cast` labeled
        edge, which is explicitly CP3 scope (issue #86, DEC-4) -- not
        something find_path_bfs() can produce today. This test pins the
        CURRENT (pre-CP3) behaviour so it doesn't regress silently and so
        it gets revisited once CP3 lands.
        """
        result = _call(srv, {"from_object": "ILexSense", "to_object": "IFsSymFeatVal"})
        parsed = _parse(result)
        assert parsed["found"] is False, parsed


# ---------------------------------------------------------------------------
# 4. Isolated unit test for find_path_bfs()'s reconstruction logic (not #85
#    itself -- see module docstring). Kept minimal and independent of the
#    shipped graph data so it doesn't depend on graph contents.
# ---------------------------------------------------------------------------

class TestFindPathBfsReconstruction:
    """find_path_bfs() previously never recorded the target node (`end`) in
    `parent` before reconstructing, so `while node in parent` at the target
    failed immediately and the function returned [] even when a match was
    found -- for every call, including a trivial single-edge graph (D2,
    regression from commit 2053e12). The fix seeds the reconstructed path
    with the final edge (current -> target) directly, then walks `parent`
    backwards from `current`, without ever mutating `parent[end]` (which
    could already hold a different, valid parent from an earlier visit)."""

    def test_direct_edge_reports_correct_path(self):
        from server.handlers.discovery import find_path_bfs

        graph = {"A": [["B", "PropX", "owns"]]}
        assert find_path_bfs(graph, "A", "B") == [
            {"from": "A", "to": "B", "via": "PropX", "type": "owns"}
        ]

    def test_two_hop_edge_reports_correct_path(self):
        from server.handlers.discovery import find_path_bfs

        graph = {
            "A": [["B", "PropX", "owns"]],
            "B": [["C", "PropY", "owns"]],
        }
        assert find_path_bfs(graph, "A", "C") == [
            {"from": "A", "to": "B", "via": "PropX", "type": "owns"},
            {"from": "B", "to": "C", "via": "PropY", "type": "owns"},
        ]
