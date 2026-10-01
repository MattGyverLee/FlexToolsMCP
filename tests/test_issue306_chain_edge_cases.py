#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #306 follow-up, QC round: edge cases of the base-class-aware member
lookup shared by the invalid_api_chain and unknown_method gates, and of the
typo auto-fix's unprotected-write check in run_module.
"""

import ast
import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    _operation_method_names,
    _ops_class_member_records,
    detect_invalid_project_chains,
    detect_unknown_operations_methods,
)


class _FakeIndex:
    casting_index = None
    flexicon = {
        "entities": {
            "FLExProject": {
                "methods": [],
                "properties": [
                    {"name": "Senses", "return_type": "LexSenseOperations"},
                    {"name": "Grand", "return_type": "GrandOperations"},
                    {"name": "Loop", "return_type": "LoopAOperations"},
                    # Not an Operations return type, and no WidgetsOperations
                    # entity: neither gate can type it.
                    {"name": "Widgets", "return_type": "WidgetRegistry"},
                ],
            },
            "BaseOperations": {
                "base_classes": [],
                "methods": [
                    {"name": "MoveUp", "is_mutating": True},
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
                "properties": [{"name": "DefaultAnalysisWs"}],
            },
            # Grand -> Parent -> BaseOperations (grandparent MoveUp).
            "ParentOperations": {
                "base_classes": ["BaseOperations"],
                "methods": [{"name": "ParentThing", "is_mutating": False}],
                "properties": [],
            },
            "GrandOperations": {
                "base_classes": ["ParentOperations"],
                "methods": [{"name": "OwnThing", "is_mutating": False}],
                "properties": [],
            },
            # A cycle in base_classes must terminate.
            "LoopAOperations": {
                "base_classes": ["LoopBOperations"],
                "methods": [{"name": "AlphaMethod", "is_mutating": False}],
                "properties": [],
            },
            "LoopBOperations": {
                "base_classes": ["LoopAOperations"],
                "methods": [{"name": "BetaMethod", "is_mutating": False}],
                "properties": [],
            },
        }
    }


IDX = _FakeIndex()


def _both(code):
    tree = ast.parse(code)
    return (
        detect_invalid_project_chains(tree, IDX)["issues"],
        detect_unknown_operations_methods(tree, IDX)["issues"],
    )


class TestMemberLookupEdges:
    def test_untypeable_accessor_is_not_flagged(self):
        assert _both("project.Widgets.Frobnicat()\nproject.Widgets.Frobnicate()\n") == ([], [])

    def test_cyclic_base_classes_terminate_member_records(self):
        methods, _props = _ops_class_member_records(IDX, "LoopAOperations")
        assert set(methods) == {"AlphaMethod", "BetaMethod"}

    def test_cyclic_base_classes_terminate_method_names(self):
        assert _operation_method_names(IDX, "LoopAOperations") == ["AlphaMethod", "BetaMethod"]

    def test_cyclic_class_still_reports_typos(self):
        chain, unknown = _both("project.Loop.BetaMethd()\n")
        assert [i["did_you_mean"][0] for i in unknown] == ["BetaMethod"]
        assert [i["did_you_mean"][0] for i in chain] == ["BetaMethod"]

    def test_grandparent_method_is_recognised(self):
        assert _both("project.Grand.MoveUp(x)\nproject.Grand.ParentThing()\n") == ([], [])
        assert "MoveUp" in _operation_method_names(IDX, "GrandOperations")

    def test_grandparent_method_typo_suggests_it(self):
        _chain, unknown = _both("project.Grand.MovUp(x)\n")
        assert [i["did_you_mean"] for i in unknown] == [["MoveUp"]]

    def test_property_access_is_not_flagged(self):
        assert _both("ws = project.Senses.DefaultAnalysisWs\n") == ([], [])


# ---------------------------------------------------------------------------
# run_module: the typo auto-fix vs the unprotected_writes gate
# ---------------------------------------------------------------------------

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


def _run(code, **extra):
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


class _Stop(Exception):
    pass


def _spy_unknown_method_gate(monkeypatch):
    """Capture the code the unknown_method gate sees (i.e. after any auto-fix)
    and stop the run there."""
    seen = []

    def _spy(tree, idx):
        seen.append(ast.unparse(tree))
        raise _Stop()

    monkeypatch.setattr(execution_mod, "detect_unknown_operations_methods", _spy)
    return seen


class TestAutoFixWriteCheck:
    def test_certify_failure_declines_the_patch(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("certify blew up")

        monkeypatch.setattr(execution_mod, "certify_script_readonly", _boom)
        assert execution_mod._typo_fix_introduces_unprotected_write(
            "project.Senses.GetGloss(s)\n", IDX
        ) is True

    def test_readonly_patch_is_allowed(self):
        assert execution_mod._typo_fix_introduces_unprotected_write(
            "project.Senses.GetGloss(s)\n", IDX
        ) is False

    def test_unguarded_write_patch_is_declined(self):
        assert execution_mod._typo_fix_introduces_unprotected_write(
            "project.Senses.MoveUp(e, s)\n", IDX
        ) is True

    def test_guarded_write_fix_is_still_applied(self, monkeypatch, tmp_path):
        """MovUp -> MoveUp inside `if modifyAllowed:` adds no UNPROTECTED write,
        so the #46 auto-fix still applies on a read-only run."""
        _stub_env(monkeypatch, tmp_path)
        seen = _spy_unknown_method_gate(monkeypatch)
        with pytest.raises(_Stop):
            _run("if modifyAllowed:\n    project.Senses.MovUp(e, s)\n")
        assert seen and "project.Senses.MoveUp(e, s)" in seen[-1]

    def test_write_enabled_run_is_never_auto_fixed(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        seen = _spy_unknown_method_gate(monkeypatch)
        with pytest.raises(_Stop):
            _run("project.Senses.GetDefinitio(s)\n", write_enabled=True)
        assert seen and "GetDefinitio(s)" in seen[-1]

    def test_mixed_patch_with_one_mutating_fix_is_declined_whole(self, monkeypatch, tmp_path):
        """Two typos, one of which would become an unguarded write: the patch
        is all-or-nothing, so neither is applied and both are reported."""
        _stub_env(monkeypatch, tmp_path)
        data = _run("project.Senses.GetDefinitio(s)\nproject.Senses.MovUp(e, s)\n")
        assert data["error_code"] == "unknown_method", data
        assert [i["method"] for i in data["issues"]] == ["GetDefinitio", "MovUp"]
        assert [i["did_you_mean"] for i in data["issues"]] == [["GetDefinition"], ["MoveUp"]]
