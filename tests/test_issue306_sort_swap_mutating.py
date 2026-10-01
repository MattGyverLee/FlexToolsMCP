#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #306 follow-up: BaseOperations.Sort / Swap reorder an owning sequence,
so they are writes.

The flexicon generator derived is_mutating from a `self._EnsureWriteEnabled()`
call or a write-verb name prefix. Sort and Swap have neither (they bracket
their MoveTo calls in `self._TransactionCM(...)`), so both shipped
is_mutating False. That mattered once #338 made certify_script_readonly
resolve inherited methods from the index: an unguarded
`project.LexEntry.Sort(e)` certified read-only. The generator now treats
`self._TransactionCM(...)` as write evidence and Sort / Swap / Reorder* /
Insert* names as writes.
"""

import ast
import json
from pathlib import Path

import pytest

from flextoolsmcp.flexicon_analyzer import _name_reorders_sequence, analyze_method
from flextoolsmcp.server.validators import certify_script_readonly

INDEX = (
    Path(__file__).resolve().parent.parent
    / "src" / "flextoolsmcp" / "index" / "python" / "flexicon_api_v4.11.0.json"
)


def _analyze(src: str, cls: str = "BaseOperations") -> dict:
    node = ast.parse(src).body[0]
    return analyze_method(node, cls, [])


@pytest.fixture(scope="module")
def shipped():
    return json.loads(INDEX.read_text(encoding="utf-8"))


class TestShippedIndex:
    @pytest.mark.parametrize("name", ["Sort", "Swap"])
    def test_base_operations_reorder_methods_are_mutating(self, shipped, name):
        methods = {m["name"]: m for m in shipped["entities"]["BaseOperations"]["methods"]}
        assert methods[name]["is_mutating"] is True

    def test_every_base_operations_reorder_method_agrees(self, shipped):
        methods = {m["name"]: m for m in shipped["entities"]["BaseOperations"]["methods"]}
        for name in ("MoveUp", "MoveDown", "MoveToIndex", "MoveBefore", "MoveAfter",
                     "Sort", "Swap"):
            assert methods[name]["is_mutating"] is True, name

    def test_unguarded_inherited_sort_is_not_certified_readonly(self):
        from flextoolsmcp.server import APIIndex, get_index_dir

        idx = APIIndex.load(get_index_dir())
        if "BaseOperations" not in (idx.flexicon or {}).get("entities", {}):
            pytest.skip("flexicon index not loaded")
        for code in ("project.LexEntry.Sort(e)\n", "project.Senses.Swap(a, b)\n"):
            cert = certify_script_readonly(code, idx, ast.parse(code))
            assert cert["is_certified_readonly"] is False, code
            assert [(m["method"], m["source"]) for m in cert["mutating_calls"]] in (
                [("Sort", "index")], [("Swap", "index")]
            )


class TestGeneratorHeuristic:
    @pytest.mark.parametrize("name, expected", [
        ("Sort", True), ("Swap", True), ("Reorder", True), ("ReorderSenses", True),
        ("InsertAt", True), ("InsertBefore", True), ("InsertAfter", True),
        # Nouns / non-splice names: often getters or properties.
        ("SortKey", False), ("SortKeyWs", False), ("SortOrder", False),
        ("SortSpec", False), ("SortWs", False), ("SortField", False),
        ("SortBy", False), ("SortByKey", False), ("SortAlternative", False),
        ("SwapPair", False), ("InsertXml", False), ("Insert", False),
        ("Sorted", False), ("Insertion", False), ("Swapped", False),
        ("Reordered", False), ("GetSortKey", False),
    ])
    def test_name_reorders_sequence(self, name, expected):
        assert _name_reorders_sequence(name) is expected

    def test_sort_named_method_is_mutating_without_any_write_call(self):
        info = _analyze("def Sort(self, parent):\n    return 0\n")
        assert info["is_mutating"] is True

    def test_transaction_bracket_is_write_evidence(self):
        """flexicon's real Swap: no _EnsureWriteEnabled, MoveTo inside a
        _TransactionCM -- and a name the verb list need not know."""
        src = (
            "def Exchange(self, a, b):\n"
            "    seq = self._FindCommonSequence(a, b)\n"
            "    with self._TransactionCM('Swap items'):\n"
            "        seq.MoveTo(0, 0, seq, 2)\n"
            "    return True\n"
        )
        info = _analyze(src)
        assert info["is_mutating"] is True
        assert info["lcm_mapping"]["calls_ensure_write_enabled"] is True

    def test_plain_reader_stays_read_only(self):
        info = _analyze("def CompareTo(self, a, b):\n    return a == b\n")
        assert info["is_mutating"] is False

    def test_usage_hint_unchanged_for_sort(self):
        """The fix lives in is_mutating, not usage_hint, so the indexed
        usage_hint values do not churn."""
        info = _analyze("def Sort(self, parent):\n    return 0\n")
        assert info["usage_hint"] is None

