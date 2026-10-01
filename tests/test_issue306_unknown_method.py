#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #306: a method an indexed Operations class does not have is a wrong
NAME, not a write.

`project.Parser.TryWord(...)` (ParserOperations has ParseWord / ParseWordXml /
TraceWordXml) used to be classified mutating by certify_script_readonly's
"method not in index" branch and rejected as unprotected_writes, so a weak
model kept adding guards. The fix:

  * detect_unknown_operations_methods reports it as unknown_method with
    did-you-mean candidates, for the direct AND every aliased receiver shape;
  * certify_script_readonly no longer counts it as a mutation (when the class's
    whole ancestry is indexed), and resolves inherited methods;
  * a genuinely mutating indexed method still triggers unprotected_writes.
"""

import ast
import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    certify_script_readonly,
    detect_unknown_operations_methods,
)


class _FakeIndex:
    casting_index = None
    flexicon = {
        "entities": {
            "FLExProject": {
                "methods": [],
                "properties": [
                    {"name": "Parser", "return_type": "ParserOperations"},
                    {"name": "LexEntry", "return_type": "LexEntryOperations"},
                ],
            },
            "BaseOperations": {
                "base_classes": [],
                "methods": [
                    {"name": "MoveUp", "is_mutating": True},
                    {"name": "GetSyncableProperties", "is_mutating": False},
                    {"name": "__init__", "is_mutating": False},
                ],
                "properties": [],
            },
            "ParserOperations": {
                "access_path": "project.Parser",
                "base_classes": ["BaseOperations"],
                "methods": [
                    {"name": "ParseWord", "is_mutating": False},
                    {"name": "ParseWordXml", "is_mutating": False},
                    {"name": "TraceWordXml", "is_mutating": False},
                    {"name": "Reload", "is_mutating": False},
                ],
                "properties": [],
            },
            "LexEntryOperations": {
                "access_path": "project.LexEntry",
                "base_classes": ["BaseOperations"],
                "methods": [
                    {"name": "Create", "is_mutating": True},
                    {"name": "GetLexemeForm", "is_mutating": False},
                ],
                "properties": [],
            },
            # Ancestor not indexed -> membership undecidable.
            "OddOperations": {
                "access_path": "project.Odd",
                "base_classes": ["SomeUnindexedMixin"],
                "methods": [{"name": "Known", "is_mutating": False}],
                "properties": [],
            },
        }
    }


IDX = _FakeIndex()

DIRECT = "res = project.Parser.TryWord('abc')\nprint(res)\n"
ALIASED = "parser_ops = project.Parser\nres = parser_ops.TryWord('abc')\nprint(res)\n"
CTOR_ALIAS = (
    "from flexicon import ParserOperations\n"
    "p = ParserOperations(project)\n"
    "p.TryWord('abc')\n"
)
INLINE_CTOR = "from flexicon import ParserOperations\nParserOperations(project).TryWord('x')\n"
STATIC = "from flexicon import ParserOperations\nParserOperations.TryWord('x')\n"


def _detect(code):
    return detect_unknown_operations_methods(ast.parse(code), IDX)


class TestDetector:
    @pytest.mark.parametrize(
        "code", [DIRECT, ALIASED, CTOR_ALIAS, INLINE_CTOR, STATIC],
        ids=["direct", "aliased", "ctor_alias", "inline_ctor", "static"],
    )
    def test_every_receiver_shape_reports_unknown_method(self, code):
        result = _detect(code)
        assert result["has_unknown"] is True
        assert len(result["issues"]) == 1
        issue = result["issues"][0]
        assert issue["class"] == "ParserOperations"
        assert issue["method"] == "TryWord"

    def test_did_you_mean_names_the_real_methods(self):
        issue = _detect(DIRECT)["issues"][0]
        assert issue["did_you_mean"]
        assert set(issue["did_you_mean"]) <= {"ParseWord", "ParseWordXml", "TraceWordXml"}
        assert "ParseWord" in issue["available_methods"]
        assert "__init__" not in issue["available_methods"]
        assert "TryWord" in issue["suggestion"]
        assert issue["expr"] == "project.Parser.TryWord"

    def test_aliased_expr_names_the_alias(self):
        issue = _detect(ALIASED)["issues"][0]
        assert issue["expr"] == "parser_ops.TryWord"
        assert issue["lineno"] == 2

    def test_real_and_inherited_methods_pass(self):
        code = (
            "project.Parser.ParseWord('abc')\n"
            "p = project.Parser\n"
            "p.TraceWordXml('abc')\n"
            "project.LexEntry.MoveUp(e)\n"
            "project.LexEntry.GetSyncableProperties(e)\n"
        )
        assert _detect(code)["has_unknown"] is False

    def test_unindexed_getter_still_passes_issue32(self):
        """#32: a Get*/Find*/... method missing from a lagging index must run."""
        code = "project.Parser.GetNewThing()\nParserOperations(project).FindIt()\n"
        assert _detect(code)["has_unknown"] is False
        assert certify_script_readonly(code, IDX)["is_certified_readonly"] is True

    def test_undecidable_ancestry_is_skipped(self):
        assert _detect("project.Odd.Whatever()\n")["has_unknown"] is False

    def test_unrelated_receivers_are_ignored(self):
        assert _detect("x = []\nx.TryWord()\nreport.Info('hi')\n")["has_unknown"] is False

    def test_no_close_match_gives_empty_list_and_discovery_pointer(self):
        issue = _detect("project.Parser.Zzzqqq()\n")["issues"][0]
        assert issue["did_you_mean"] == []
        assert "flextools_get_object_api" in issue["suggestion"]


class TestCertifyNoLongerCallsItMutating:
    @pytest.mark.parametrize("code", [DIRECT, ALIASED, CTOR_ALIAS], ids=["direct", "aliased", "ctor_alias"])
    def test_unknown_method_is_not_a_mutation(self, code):
        cert = certify_script_readonly(code, IDX)
        assert cert["is_certified_readonly"] is True
        assert cert["mutating_calls"] == []
        assert [(u["class"], u["method"]) for u in cert["unknown_calls"]] == [
            ("ParserOperations", "TryWord")
        ]

    def test_genuinely_mutating_indexed_method_still_flagged(self):
        cert = certify_script_readonly("project.LexEntry.Create('x')\n", IDX)
        assert cert["is_certified_readonly"] is False
        assert [(m["class"], m["method"], m["source"]) for m in cert["mutating_calls"]] == [
            ("LexEntryOperations", "Create", "index")
        ]

    def test_inherited_mutating_method_classified_from_index(self):
        cert = certify_script_readonly("project.LexEntry.MoveUp(e)\n", IDX)
        assert cert["is_certified_readonly"] is False
        assert [(m["method"], m["source"]) for m in cert["mutating_calls"]] == [("MoveUp", "index")]
        assert cert["unknown_calls"] == []

    def test_undecidable_class_stays_fail_closed(self):
        cert = certify_script_readonly("project.Odd.Whatever()\n", IDX)
        assert cert["is_certified_readonly"] is False
        assert [(m["method"], m["source"]) for m in cert["mutating_calls"]] == [("Whatever", "unknown")]


# ---------------------------------------------------------------------------
# End to end through handle_run_module
# ---------------------------------------------------------------------------

def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _stub_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: IDX)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(
        execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []}
    )


def _run(code):
    return _parse(asyncio.run(execution_mod.handle_run_module({
        "code": code,
        "project_name": "TestProject",
        "skip_module_check": True,
        "skip_api_check": True,
        "write_enabled": False,
    })))


class TestRunModule:
    @pytest.mark.parametrize("code", [DIRECT, ALIASED], ids=["direct", "aliased"])
    def test_rejects_with_unknown_method_not_unprotected_writes(self, monkeypatch, tmp_path, code):
        _stub_env(monkeypatch, tmp_path)
        data = _run(code)
        assert data["status"] == "error"
        assert data["error_code"] == "unknown_method", data
        assert data["did_you_mean"]
        assert set(data["did_you_mean"]) <= {"ParseWord", "ParseWordXml", "TraceWordXml"}
        assert data["issues"][0]["method"] == "TryWord"
        assert any("modifyAllowed" in step for step in data["next_steps"])

    @pytest.mark.parametrize("code", [DIRECT, ALIASED], ids=["direct", "aliased"])
    def test_validate_only_agrees(self, code):
        class _Session:
            def get_discovered_apis(self):
                return set()

        checks, _w = execution_mod._build_validate_only_checks(
            code=code,
            code_tree=ast.parse(code),
            syntax_error=None,
            api_idx=IDX,
            session_state_obj=_Session(),
            write_enabled=False,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )
        by_gate = {c["gate"]: c for c in checks}
        assert by_gate["unprotected_writes"]["passed"] is True
        assert by_gate["invalid_api_chain"]["passed"] is True
        assert by_gate["unknown_method"]["passed"] is False
        assert by_gate["unknown_method"]["issues"][0]["method"] == "TryWord"

    def test_mutating_indexed_method_still_unprotected_writes(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        data = _run("project.LexEntry.Create('x')\n")
        assert data["status"] == "error"
        assert data["error_code"] == "unprotected_writes"
