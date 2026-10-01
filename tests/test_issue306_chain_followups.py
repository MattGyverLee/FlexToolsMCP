#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #306 follow-up: detect_invalid_project_chains' method branch.

It derived the Operations class as accessor + "Operations", so for every
accessor whose class is named differently (project.Senses ->
LexSenseOperations, not "SensesOperations") the lookup found nothing and
method typos were never caught. It also read only the class's own methods,
so it could not suggest (or recognise) inherited ones like
BaseOperations.MoveUp. Now it resolves through _accessor_to_ops_map and the
same base-class-aware, decidability-checked member lookup the unknown_method
gate uses; _operation_method_names (runtime did-you-mean) is inherited-aware
too.
"""

import ast

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    _operation_method_names,
    detect_invalid_project_chains,
    detect_unknown_attribute_error,
    detect_unknown_operations_methods,
)


class _FakeIndex:
    casting_index = None
    flexicon = {
        "entities": {
            "FLExProject": {
                "methods": [],
                "properties": [
                    # Accessor name != class name minus "Operations".
                    {"name": "Senses", "return_type": "LexSenseOperations"},
                    {"name": "LexEntry", "return_type": "LexEntryOperations"},
                    {"name": "Odd", "return_type": "OddOperations"},
                ],
            },
            "BaseOperations": {
                "base_classes": [],
                "methods": [
                    {"name": "MoveUp", "is_mutating": True},
                    {"name": "Sort", "is_mutating": True},
                    {"name": "__init__", "is_mutating": False},
                ],
                "properties": [],
            },
            "LexSenseOperations": {
                "base_classes": ["BaseOperations"],
                "methods": [
                    {"name": "GetGloss", "is_mutating": False},
                    {"name": "SetGloss", "is_mutating": True},
                    {"name": "GetDefinition", "is_mutating": False},
                ],
                "properties": [],
            },
            "LexEntryOperations": {
                "base_classes": ["BaseOperations"],
                "methods": [
                    {"name": "GetLexemeForm", "is_mutating": False},
                    {"name": "Create", "is_mutating": True},
                ],
                "properties": [],
            },
            # Ancestor not indexed -> membership undecidable -> never flagged.
            "OddOperations": {
                "base_classes": ["SomeUnindexedMixin"],
                "methods": [{"name": "Known", "is_mutating": False}],
                "properties": [],
            },
        }
    }


IDX = _FakeIndex()


def _chain(code):
    return detect_invalid_project_chains(ast.parse(code), IDX)


def _method_issues(code):
    return [i for i in _chain(code)["issues"] if i["kind"] == "method"]


class TestChainMethodBranch:
    def test_accessor_whose_class_is_not_accessor_plus_operations(self):
        """project.Senses -> LexSenseOperations: a typo is now caught."""
        issues = _method_issues("project.Senses.GetGlos(s)\n")
        assert len(issues) == 1
        assert issues[0]["typo_attr"] == "GetGlos"
        assert "GetGloss" in issues[0]["did_you_mean"]
        assert "LexSenseOperations" in issues[0]["suggestion"]
        assert "SensesOperations" not in issues[0]["suggestion"]

    @pytest.mark.parametrize("code", [
        "project.Senses.MoveUp(e, s)\n",
        "project.Senses.Sort(e)\n",
        "project.LexEntry.MoveUp(e)\n",
    ])
    def test_inherited_method_not_flagged(self, code):
        assert _chain(code)["has_invalid"] is False

    def test_typo_of_inherited_method_suggests_it(self):
        issues = _method_issues("project.Senses.MovUp(e, s)\n")
        assert [i["did_you_mean"] for i in issues] == [["MoveUp"]]

    def test_real_own_methods_not_flagged(self):
        assert _chain("project.Senses.GetGloss(s)\nproject.Senses.SetGloss(s, 'x')\n")["has_invalid"] is False

    def test_undecidable_ancestry_is_skipped(self):
        assert _chain("project.Odd.Knwn()\n")["has_invalid"] is False

    def test_dunder_never_suggested(self):
        issues = _method_issues("project.Senses.__intt__()\n")
        assert all("__init__" not in i["did_you_mean"] for i in issues)


class TestOperationMethodNames:
    def test_includes_inherited_own_first(self):
        names = _operation_method_names(IDX, "LexSenseOperations")
        assert names[:3] == ["GetGloss", "SetGloss", "GetDefinition"]
        assert "MoveUp" in names and "Sort" in names

    def test_partial_ancestry_is_best_effort(self):
        assert _operation_method_names(IDX, "OddOperations") == ["Known"]

    def test_runtime_did_you_mean_reaches_inherited(self):
        res = detect_unknown_attribute_error(
            "'LexSenseOperations' object has no attribute 'MovUp'", IDX
        )
        assert res["has_suggestion"] is True
        assert res["did_you_mean"] == ["MoveUp"]


class TestGateInterplay:
    """Direct and aliased forms answer with the same code; validate_only does
    not report one call under two gates."""

    def _checks(self, code):
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
        return {c["gate"]: c for c in checks}

    @pytest.mark.parametrize("code", [
        "project.Senses.MovUp(e, s)\n",
        "ops = project.Senses\nops.MovUp(e, s)\n",
    ], ids=["direct", "aliased"])
    def test_non_getter_typo_is_unknown_method_only(self, code):
        by_gate = self._checks(code)
        assert by_gate["invalid_api_chain"]["passed"] is True
        assert by_gate["unknown_method"]["passed"] is False
        issues = by_gate["unknown_method"]["issues"]
        assert [(i["class"], i["method"], i["did_you_mean"]) for i in issues] == [
            ("LexSenseOperations", "MovUp", ["MoveUp"])
        ]

    def test_direct_and_aliased_detector_agree(self):
        direct = detect_unknown_operations_methods(ast.parse("project.Senses.MovUp(e, s)\n"), IDX)
        aliased = detect_unknown_operations_methods(
            ast.parse("ops = project.Senses\nops.MovUp(e, s)\n"), IDX
        )
        assert [(i["class"], i["method"], i["did_you_mean"]) for i in direct["issues"]] == [
            (i["class"], i["method"], i["did_you_mean"]) for i in aliased["issues"]
        ]

    @pytest.mark.parametrize("code", [
        "project.Senses.GetGlos(s)\n",
        "ops = project.Senses\nops.GetGlos(s)\n",
    ], ids=["direct", "aliased"])
    def test_confident_getter_typo_is_unknown_method_once(self, code):
        """#32 rule shared by both gates: a confident Get* typo is reported --
        under unknown_method only (the chain issue is deferred to it)."""
        by_gate = self._checks(code)
        assert by_gate["invalid_api_chain"]["passed"] is True
        assert by_gate["unknown_method"]["passed"] is False
        assert [i["method"] for i in by_gate["unknown_method"]["issues"]] == ["GetGlos"]

    @pytest.mark.parametrize("code", [
        "project.Senses.GetGlossText(s)\n",
        "ops = project.Senses\nops.GetGlossText(s)\n",
        "project.Senses.GetDefinitionOrGloss(s)\n",
        "project.LexEntry.FindByForm('x')\n",
    ], ids=["direct_extension", "aliased_extension", "unrelated_getter", "find"])
    def test_getter_newer_than_index_passes_both_gates(self, code):
        by_gate = self._checks(code)
        assert by_gate["invalid_api_chain"]["passed"] is True
        assert by_gate["unknown_method"]["passed"] is True


class TestConfidentGetterTypoRule:
    @pytest.mark.parametrize("name, expected", [
        ("GetGlos", True),          # truncation typo
        ("GetLexemeFrom", True),    # transposition (vs GetLexemeForm)
        ("GetGlossText", False),    # extension: a newer getter
        ("GetGlosses", False),      # plural extension
        ("GetGlosss", True),        # doubled final letter: a typo
        ("GetGlossx", True),        # lowercase non-plural tail: a typo
        ("GetNewThing", False),     # unrelated
    ])
    def test_rule(self, name, expected):
        from flextoolsmcp.server.validators import _has_confident_member_typo_match

        cands = ["GetGloss", "SetGloss", "GetLexemeForm", "GetDefinition"]
        assert _has_confident_member_typo_match(name, cands) is expected

    def test_detectors_skip_unconfident_getter(self):
        for code in ("project.Senses.GetGlossText(s)\n", "ops = project.Senses\nops.GetGlossText(s)\n"):
            tree = ast.parse(code)
            assert detect_invalid_project_chains(tree, IDX)["issues"] == []
            assert detect_unknown_operations_methods(tree, IDX)["issues"] == []


# ---------------------------------------------------------------------------
# End to end through handle_run_module
# ---------------------------------------------------------------------------

def _run(monkeypatch, tmp_path, code, **extra):
    import asyncio
    import json

    from flextoolsmcp.server import kernel, project_discovery

    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: IDX)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(
        execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []}
    )
    args = {
        "code": code,
        "project_name": "TestProject",
        "skip_module_check": True,
        "skip_api_check": True,
        "write_enabled": False,
        "auto_fix": True,
    }
    args.update(extra)
    item = asyncio.run(execution_mod.handle_run_module(args))[0]
    return json.loads(item["text"] if isinstance(item, dict) else item.text)


class TestRunModuleAgreement:
    @pytest.mark.parametrize("code", [
        "project.Senses.MovUp(e, s)\n",
        "ops = project.Senses\nops.MovUp(e, s)\n",
    ], ids=["direct", "aliased"])
    def test_typo_of_inherited_write_is_unknown_method(self, monkeypatch, tmp_path, code):
        """The direct form used to be eligible for the #46 typo auto-fix,
        which would rewrite it to the mutating MoveUp AFTER the
        unprotected_writes gate had run. The fix is declined when it would
        introduce an unguarded write, so both forms get unknown_method."""
        data = _run(monkeypatch, tmp_path, code)
        assert data["status"] == "error"
        assert data["error_code"] == "unknown_method", data
        assert data["did_you_mean"] == ["MoveUp"]

    def test_typo_of_readonly_method_is_still_auto_fixed(self, monkeypatch, tmp_path):
        seen = []

        class _Stop(Exception):
            pass

        def _spy(tree, idx):
            seen.append(ast.unparse(tree))
            raise _Stop()

        monkeypatch.setattr(execution_mod, "detect_unknown_operations_methods", _spy)
        with pytest.raises(_Stop):
            _run(monkeypatch, tmp_path, "project.Senses.GetDefinitio(s)\n")
        assert seen and "project.Senses.GetDefinition(s)" in seen[-1]
