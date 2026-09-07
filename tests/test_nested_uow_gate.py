#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #92 follow-up: nested-UnitOfWork pre-flight gate.

CP1 hardcoded `undoable=False` at the generated OpenProject() call, so a
write-enabled run now always has ONE non-undoable UnitOfWork open for the
whole session (flexicon's FLExProject.OpenProject() -- writeEnabled=True
and undoable=False -- calls `MainCacheAccessor.BeginNonUndoableTask()` once
and closes it once at CloseProject()). A script that opens its OWN raw
liblcm UnitOfWork on top of that -- UndoableUnitOfWorkHelper /
NonUndoableUnitOfWorkHelper (constructor or static .Do*() calls), or a bare
IActionHandler.BeginUndoTask()/BeginNonUndoableTask() -- nests a second task
inside the runner's own. liblcm does not merge tasks opened this way; the
already-open UnitOfWork is rolled back first (discarding the whole run's
writes), before the second Begin* call throws.

`validators.detect_nested_unit_of_work()` is an AST-based pre-flight
detector (unit-tested directly below); `handlers.execution.handle_run_module`
wires it in as a hard-refuse gate, `nested_unit_of_work`, that fires ONLY on
write-enabled runs -- flexicon's OpenProject() only opens that UnitOfWork
when writeEnabled=True, so a read-only run has nothing open to nest into.

Covers:
- TestDetectNestedUnitOfWork: each raw construct is detected by the
  validator directly (one case per sibling shape).
- TestGateWiring: the gate refuses a write-enabled run containing any of
  those constructs, takes no project lock and spawns no subprocess; an
  ordinary guarded write (no raw UoW construct) is NOT refused; a construct
  appearing only inside a comment or a string literal is NOT refused; a
  read-only run containing the construct is NOT refused (per the write-only
  condition above).
"""

import asyncio
import json


from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import detect_nested_unit_of_work


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


# ---------------------------------------------------------------------------
# Direct validator coverage -- one case per sibling construct shape.
# ---------------------------------------------------------------------------

class TestDetectNestedUnitOfWork:
    def test_undoable_helper_constructor(self):
        code = (
            "from SIL.LCModel.Infrastructure import UndoableUnitOfWorkHelper\n"
            "h = UndoableUnitOfWorkHelper(action_handler, 'u', 'r')\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any("UndoableUnitOfWorkHelper" in c["construct"] for c in result["constructs"])

    def test_nonundoable_helper_constructor(self):
        code = "h = NonUndoableUnitOfWorkHelper(cache.ActionHandlerAccessor)\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any("NonUndoableUnitOfWorkHelper" in c["construct"] for c in result["constructs"])

    def test_undoable_helper_static_do(self):
        code = (
            "UndoableUnitOfWorkHelper.Do('u', 'r', action_handler, lambda: None)\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "UndoableUnitOfWorkHelper.Do(...)" for c in result["constructs"])

    def test_nonundoable_helper_static_do(self):
        code = "NonUndoableUnitOfWorkHelper.Do(action_handler, lambda: None)\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "NonUndoableUnitOfWorkHelper.Do(...)" for c in result["constructs"])

    def test_raw_begin_undo_task(self):
        code = "project.project.ActionHandlerAccessor.BeginUndoTask('a', 'b')\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "...BeginUndoTask(...)" for c in result["constructs"])

    def test_raw_begin_non_undoable_task(self):
        code = "cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "...BeginNonUndoableTask(...)" for c in result["constructs"])

    def test_guard_does_not_suppress_detection(self):
        """An `if modifyAllowed:` guard does not fix the nesting collision --
        the detector must fire regardless of guard state."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if modifyAllowed:\n"
            "        cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True

    def test_flexicon_undoable_operation_not_flagged(self):
        """project.UndoableOperation()/project.Transaction() are flexicon's own
        nesting-aware wrappers (they ask ActionHandlerAccessor.CurrentDepth
        and join instead of nesting) -- must never false-positive here."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    with project.UndoableOperation('label'):\n"
            "        pass\n"
            "    with project.Transaction('label'):\n"
            "        if modifyAllowed:\n"
            "            project.LexEntry.SetLexemeForm(entry, 'x')\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is False
        assert result["constructs"] == []

    def test_construct_in_comment_not_flagged(self):
        code = (
            "# call UndoableUnitOfWorkHelper.Do(x) or BeginUndoTask() manually\n"
            "# also NonUndoableUnitOfWorkHelper(handler)\n"
            "x = 1\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is False

    def test_construct_in_string_not_flagged(self):
        code = (
            "msg = 'call UndoableUnitOfWorkHelper.Do(x) or BeginUndoTask() manually'\n"
            "msg2 = \"NonUndoableUnitOfWorkHelper(handler)\"\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is False


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
    def test_raw_uow_construct_refused_write_enabled(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": (
                "if modifyAllowed:\n"
                "    cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
            ),
            "project_name": "TestProj_nested",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "nested_unit_of_work"
        assert "constructs" in data

    def test_helper_constructor_refused_write_enabled(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": (
                "from SIL.LCModel.Infrastructure import UndoableUnitOfWorkHelper\n"
                "if modifyAllowed:\n"
                "    h = UndoableUnitOfWorkHelper(action_handler, 'u', 'r')\n"
            ),
            "project_name": "TestProj_nested2",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "nested_unit_of_work"

    def test_ordinary_guarded_write_not_refused(self, monkeypatch, tmp_path):
        """A plain guarded write with no raw UoW construct must NOT be refused
        by this gate (no false positive)."""
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
                "    project.LexEntry.SetLexemeForm(entry, 'x')\n"
            ),
            "project_name": "TestProj_plain",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "nested_unit_of_work"
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
                "# UndoableUnitOfWorkHelper.Do(x) mentioned only in a comment\n"
                "if modifyAllowed:\n"
                "    project.LexEntry.SetLexemeForm(entry, 'x')\n"
            ),
            "project_name": "TestProj_comment",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "nested_unit_of_work"
        assert data.get("success") is True

    def test_readonly_run_with_construct_not_refused(self, monkeypatch, tmp_path):
        """Per the write-only condition: flexicon's OpenProject() only opens
        a UnitOfWork when writeEnabled=True (FLExProject.py), so a read-only
        run has nothing open to nest into -- the gate must not fire."""
        _stub_env(monkeypatch, tmp_path, is_cud=False)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)

        args = {
            "code": "cache.ActionHandlerAccessor.BeginNonUndoableTask()\n",
            "project_name": "TestProj_readonly",
            "write_enabled": False,
            "confirmed": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "nested_unit_of_work"
