#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #103: hvo instability preflight guard.

liblcm renumbers hvos on every cache load
(`src/SIL.LCModel/Application/Impl/DomainDataByFlid.cs:40-44`: "The hvo values
are true 'handles' in that they are valid for one session, but may not be the
same integer for another session for the 'same' object ... CmObject identity
can only be guaranteed by using their Guids"). Field evidence: 2440/2440 entry
hvos changed across two consecutive READ-ONLY run_module calls with zero
writes between them; 0/2440 guids changed. A bare integer literal reaching an
`*_or_hvo` parameter (or `project.Object(<int>)`) can only have been copied
from a prior call's output or the FLEx UI -- it cannot be a hvo read this run,
because a hvo read this run would be a `.Hvo` expression, not a literal.

`validators.detect_hvo_literal_args()` is an AST-based pre-flight detector
(unit-tested directly below); `handlers.execution.handle_run_module` wires it
in as:
  - a hard-refuse gate, `hvo_literal_write_risk`, on WRITE-enabled runs (a
    wrong-target write is exactly the silent-corruption scenario #103
    documents), and
  - a non-blocking advisory in the `warnings` list on READ-ONLY runs (a stray
    literal in exploratory/read code cannot corrupt anything).

Covers:
- TestDetectHvoLiteralArgs: each detected shape (keyword *_or_hvo literal,
  resolved positional *_or_hvo literal, project.Object(<int>)), plus the
  negative cases (a `.Hvo` variable, a non-hvo keyword, an unresolvable
  receiver) that must NOT be flagged.
- TestGateWiring: the gate refuses a write-enabled run containing any hvo
  literal risk, takes no project lock and spawns no subprocess; the same code
  in a read-only run is NOT refused (success, with an advisory in
  `warnings`); an ordinary write using a `.Hvo`-derived variable (no literal)
  is NOT refused.
"""

import ast
import asyncio
import json


from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import detect_hvo_literal_args


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


class _FakeApiIndex:
    """Minimal api_index stand-in: FLExProject.<Accessor> -> Operations class,
    and LexEntryOperations.Delete(entry_or_hvo) parameter names."""

    def __init__(self):
        self.flexicon = {
            "entities": {
                "FLExProject": {
                    "properties": [
                        {"name": "LexEntry", "return_type": "LexEntryOperations"},
                    ]
                },
                "LexEntryOperations": {
                    "methods": [
                        {"name": "Delete", "parameters": [{"name": "entry_or_hvo"}]},
                        {"name": "SetHomographNumber", "parameters": [
                            {"name": "entry_or_hvo"}, {"name": "number"},
                        ]},
                    ]
                },
            }
        }


# ---------------------------------------------------------------------------
# Direct validator coverage -- one case per sibling detection shape.
# ---------------------------------------------------------------------------

class TestDetectHvoLiteralArgs:
    def test_keyword_arg_literal_flagged(self):
        code = "project.LexEntry.Delete(entry_or_hvo=1234)\n"
        result = detect_hvo_literal_args(code)
        assert result["has_hvo_literal_risk"] is True
        assert any("entry_or_hvo=1234" in f["detail"] for f in result["findings"])

    def test_project_object_int_literal_flagged(self):
        code = "entry = project.Object(1234)\n"
        result = detect_hvo_literal_args(code)
        assert result["has_hvo_literal_risk"] is True
        assert any("project.Object(1234)" in f["detail"] for f in result["findings"])

    def test_positional_literal_flagged_via_project_accessor(self):
        code = "project.LexEntry.Delete(1234)\n"
        result = detect_hvo_literal_args(code, api_index=_FakeApiIndex())
        assert result["has_hvo_literal_risk"] is True
        assert any("Delete" in f["detail"] for f in result["findings"])

    def test_positional_literal_flagged_via_inline_operations_construction(self):
        code = "LexEntryOperations(project).Delete(1234)\n"
        result = detect_hvo_literal_args(code, api_index=_FakeApiIndex())
        assert result["has_hvo_literal_risk"] is True

    def test_positional_literal_flagged_via_local_alias(self):
        code = (
            "entry_ops = LexEntryOperations(project)\n"
            "entry_ops.Delete(1234)\n"
        )
        result = detect_hvo_literal_args(code, api_index=_FakeApiIndex())
        assert result["has_hvo_literal_risk"] is True

    def test_second_positional_arg_not_flagged(self):
        """SetHomographNumber(entry_or_hvo, number) -- literal in the SECOND
        (non-hvo) position must not false-positive."""
        code = "project.LexEntry.SetHomographNumber(entry, 7)\n"
        result = detect_hvo_literal_args(code, api_index=_FakeApiIndex())
        assert result["has_hvo_literal_risk"] is False

    def test_hvo_attribute_variable_not_flagged(self):
        """A hvo read THIS run (`entry.Hvo`) is legitimate -- only a bare
        integer LITERAL is the risk."""
        code = (
            "h = entry.Hvo\n"
            "project.LexEntry.Delete(entry_or_hvo=h)\n"
        )
        result = detect_hvo_literal_args(code, api_index=_FakeApiIndex())
        assert result["has_hvo_literal_risk"] is False

    def test_non_hvo_keyword_not_flagged(self):
        code = "project.LexEntry.SetHeadword(entry_or_hvo=entry, text='run')\n"
        result = detect_hvo_literal_args(code)
        assert result["has_hvo_literal_risk"] is False

    def test_unresolvable_receiver_positional_literal_not_flagged(self):
        """False negatives are safer than false positives on plain non-hvo
        integer args when the receiver's Operations class can't be resolved."""
        code = "some_unknown_object.DoSomething(1234)\n"
        result = detect_hvo_literal_args(code, api_index=_FakeApiIndex())
        assert result["has_hvo_literal_risk"] is False

    def test_bool_not_treated_as_int_literal(self):
        code = "project.LexEntry.Delete(entry_or_hvo=True)\n"
        result = detect_hvo_literal_args(code)
        assert result["has_hvo_literal_risk"] is False

    def test_construct_in_comment_or_string_not_flagged(self):
        code = (
            "# project.LexEntry.Delete(entry_or_hvo=1234)\n"
            "msg = 'project.Object(1234)'\n"
        )
        result = detect_hvo_literal_args(code)
        assert result["has_hvo_literal_risk"] is False

    def test_accepts_preparsed_tree(self):
        code = "project.Object(999)\n"
        tree = ast.parse(code)
        result = detect_hvo_literal_args(code, tree=tree)
        assert result["has_hvo_literal_risk"] is True

    def test_syntax_error_returns_no_risk(self):
        result = detect_hvo_literal_args("def (:\n")
        assert result == {"has_hvo_literal_risk": False, "findings": []}


# ---------------------------------------------------------------------------
# Gate wiring inside handle_run_module.
# ---------------------------------------------------------------------------

def _boom_lock(*a, **k):
    raise AssertionError("get_project_write_lock must NOT be called")


def _boom_subprocess(*a, **k):
    raise AssertionError("run_script_async must NOT be called")


def _stub_env(monkeypatch, tmp_path, *, is_cud=True):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
            "confidence": "high",
        },
    )
    monkeypatch.setattr(
        execution_mod, "detect_cud_operations",
        lambda code: {"is_cud": is_cud, "operations": ["CREATE (Create())"] if is_cud else []},
    )
    monkeypatch.setattr(execution_mod, "detect_casting_needs", lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []})


async def _fake_run_script_async_ok(path, timeout_seconds):
    payload = {
        "success": True,
        "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
        "messages": [],
    }
    return {
        "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
        "stderr": "",
        "timeout": False,
        "returncode": 0,
    }


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestGateWiring:
    def test_write_enabled_keyword_literal_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": (
                "if modifyAllowed:\n"
                "    project.LexEntry.Delete(entry_or_hvo=1234)\n"
            ),
            "project_name": "TestProj_hvo1",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "hvo_literal_write_risk"
        assert "findings" in data

    def test_write_enabled_object_int_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": (
                "entry = project.Object(1234)\n"
                "if modifyAllowed:\n"
                "    project.LexEntry.SetHeadword(entry, text='run')\n"
            ),
            "project_name": "TestProj_hvo2",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "hvo_literal_write_risk"

    def test_readonly_run_with_literal_not_refused_but_warned(self, monkeypatch, tmp_path):
        """Read-only runs get a WARNING, not a rejection -- a stray literal in
        exploratory/read code cannot corrupt anything."""
        _stub_env(monkeypatch, tmp_path, is_cud=False)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)

        args = {
            "code": "project.LexEntry.Delete(entry_or_hvo=1234)\n",
            "project_name": "TestProj_hvo_readonly",
            "write_enabled": False,
            "confirmed": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "hvo_literal_write_risk"
        assert data.get("success") is True
        warnings = data.get("warnings") or []
        assert any("hvo stability" in w for w in warnings)

    def test_ordinary_write_with_hvo_attribute_not_refused(self, monkeypatch, tmp_path):
        """A write using a `.Hvo` read THIS run (no literal) must NOT be
        refused by this gate (no false positive)."""
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
        monkeypatch.setattr(
            execution_mod, "perform_pre_write_backup",
            lambda name, **k: {"path": None, "created": False, "skipped_reason": "backup_before_write=false"},
        )

        args = {
            "code": (
                "if modifyAllowed:\n"
                "    h = entry.Hvo\n"
                "    project.LexEntry.Delete(entry_or_hvo=h)\n"
            ),
            "project_name": "TestProj_hvo_plain",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "hvo_literal_write_risk"
        assert data.get("success") is True

    def test_construct_only_in_comment_not_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
        monkeypatch.setattr(
            execution_mod, "perform_pre_write_backup",
            lambda name, **k: {"path": None, "created": False, "skipped_reason": "backup_before_write=false"},
        )

        args = {
            "code": (
                "# project.LexEntry.Delete(entry_or_hvo=1234) mentioned only in a comment\n"
                "if modifyAllowed:\n"
                "    project.LexEntry.SetLexemeForm(entry, 'x')\n"
            ),
            "project_name": "TestProj_hvo_comment",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "hvo_literal_write_risk"
        assert data.get("success") is True
