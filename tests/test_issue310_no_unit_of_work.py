#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #310: raw LCM write "Not in the right state to register a change".

liblcm's UnitOfWorkService.RegisterCommon raises that InvalidOperationException
when a change is registered with no unit of work open. run_module used to hand
it back as an unstructured runtime failure, and the nested_unit_of_work gate
told raw-LCM writers to "just perform the mutation directly" -- which is the
exact thing that raises it on per-operation-uow flexicon (every supported
install), where the runner opens no session-long task. So a raw writer had no
legal path and was not told one existed.

Now:
- run_module maps the error to a structured `no_unit_of_work` code whose
  guidance fits the run's mode (read-only / per-operation / legacy session
  envelope) and names the supported raw path,
  `with project.UndoableOperation(label):`.
- the nested_unit_of_work rejection names that same path on per-operation
  builds instead of "drop the wrapper and write directly".

No live FLEx: the subprocess and the capability probe are stubbed.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.response_models import NoUnitOfWorkDetail, validate_detail
from flextoolsmcp.server.session import _ASSISTANCE_HINTS_BY_ERROR_CODE

LCM_ERROR = (
    "Execution error: Not in the right state to register a change\n"
    "Traceback (most recent call last):\n"
    "  File \"<module>\", line 8, in Main\n"
    "System.InvalidOperationException: Not in the right state to register a change\n"
    "   at SIL.LCModel.Infrastructure.Impl.UnitOfWorkService.RegisterCommon(...)\n"
    "   at SIL.LCModel.DomainImpl.PartOfSpeech.RemoveOwnee(...)\n"
    "   at SIL.LCModel.DomainImpl.LcmList`1.Add(...)\n"
)

RAW_PATH = 'with project.UndoableOperation("<label>"):'


def _diag(result, write_enabled):
    return execution_mod._diagnose_no_unit_of_work_error(result, write_enabled)


# ---------------------------------------------------------------------------
# Classification (pure function)
# ---------------------------------------------------------------------------

class TestClassification:
    def test_unrelated_error_is_not_classified(self):
        result = {"success": False, "error": "Execution error: boom\nTraceback..."}
        assert _diag(result, True) is None

    def test_no_error_is_not_classified(self):
        assert _diag({"success": True}, True) is None

    def test_marker_is_case_insensitive(self):
        result = {"error": "Execution error: NOT IN THE RIGHT STATE TO REGISTER A CHANGE"}
        assert _diag(result, True)["error_code"] == "no_unit_of_work"

    def test_reported_error_message_is_classified(self):
        """A script that catches the exception and calls report.Error() turns
        it into a ReportedError; the marker then lives in the messages."""
        result = {
            "success": False,
            "error_type": "ReportedError",
            "error": "Operation reported 1 error(s) via report.Error(); see messages for details.",
            "messages": [
                {"type": "INFO", "message": "moving POS"},
                {"type": "ERROR", "message": "failed: Not in the right state to register a change"},
            ],
            "undoable": True,
        }
        diag = _diag(result, True)
        assert diag["error_code"] == "no_unit_of_work"
        assert "Not in the right state" in diag["lcm_message"]

    def test_info_message_alone_is_not_classified(self):
        result = {
            "error": "Execution error: other",
            "messages": [{"type": "INFO", "message": "Not in the right state to register a change"}],
        }
        assert _diag(result, True) is None


# ---------------------------------------------------------------------------
# Mode-accurate guidance
# ---------------------------------------------------------------------------

class TestGuidanceByMode:
    def test_per_operation_mode_names_the_raw_path(self):
        diag = _diag({"error": LCM_ERROR, "undoable": True}, True)
        assert diag["uow_mode"] == "per_operation"
        assert diag["write_enabled"] is True
        assert diag["undoable"] is True
        g = diag["guidance"]
        assert RAW_PATH in g
        assert "project.POS.*" in g and "project.LexEntry.*" in g
        # Says why the other two routes are not the answer.
        assert "nested_unit_of_work" in g
        assert "project.Transaction()" in g
        assert "outside any undo task" in diag["message"]
        assert any(RAW_PATH in s for s in diag["next_steps"])
        assert diag["hint"] == g

    def test_undoable_unknown_defaults_to_per_operation(self):
        """Every supported install is per-operation-uow; an absent flag must
        not produce the legacy wording."""
        diag = _diag({"error": LCM_ERROR}, True)
        assert diag["uow_mode"] == "per_operation"
        assert diag["undoable"] is None

    def test_read_only_mode_says_no_write_can_register(self):
        diag = _diag({"error": LCM_ERROR, "undoable": False}, False)
        assert diag["uow_mode"] == "read_only"
        assert diag["write_enabled"] is False
        assert "read-only" in diag["message"]
        assert "write_enabled=false" in diag["message"]
        assert "if modifyAllowed:" in diag["guidance"]
        assert "write_enabled=true" in diag["guidance"]
        assert RAW_PATH in diag["guidance"]

    def test_legacy_session_envelope_mode(self):
        diag = _diag({"error": LCM_ERROR, "undoable": False}, True)
        assert diag["uow_mode"] == "session_envelope"
        assert "session" in diag["message"]
        # Legacy mode: UndoableOperation is not the fix (it needs undoable=True).
        assert RAW_PATH not in diag["guidance"]

    @pytest.mark.parametrize("undoable,write_enabled", [(True, True), (False, True), (False, False)])
    def test_detail_validates_against_model(self, undoable, write_enabled):
        diag = _diag({"error": LCM_ERROR, "undoable": undoable}, write_enabled)
        fields = set(NoUnitOfWorkDetail.model_fields)
        detail = validate_detail({k: v for k, v in diag.items() if k in fields})
        assert isinstance(detail, NoUnitOfWorkDetail)


def test_assistance_hints_name_the_raw_path():
    assert RAW_PATH in _ASSISTANCE_HINTS_BY_ERROR_CODE["no_unit_of_work"]
    nested = _ASSISTANCE_HINTS_BY_ERROR_CODE["nested_unit_of_work"]
    assert RAW_PATH in nested
    assert "Just perform the mutation directly" not in nested


# ---------------------------------------------------------------------------
# End-to-end through handle_run_module (subprocess stubbed)
# ---------------------------------------------------------------------------

def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _stub_env(monkeypatch, tmp_path, runner_payload):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
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
        lambda code: {"is_cud": True, "operations": ["CREATE (Add())"]},
    )
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs",
        lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []},
    )
    monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
    monkeypatch.setattr(
        execution_mod, "perform_pre_write_backup",
        lambda name, **k: {"path": None, "created": False, "skipped_reason": "backup_before_write=false"},
    )

    async def _fake_run(path, timeout_seconds):
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(runner_payload),
            "stderr": "",
            "timeout": False,
            "returncode": 0,
        }

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)


_CODE = (
    "if modifyAllowed:\n"
    "    target.SubPossibilitiesOS.Add(pos)\n"
)


def test_run_module_write_enabled_returns_no_unit_of_work(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path, {
        "success": False,
        "error": LCM_ERROR,
        "undoable": True,
        "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
        "messages": [],
    })
    data = _parse(asyncio.run(execution_mod.handle_run_module({
        "code": _CODE,
        "project_name": "TestProj_310",
        "write_enabled": True,
        "confirmed": True,
        "skip_api_check": True,
        "skip_module_check": True,
    })))
    assert data["status"] == "error"
    assert data["error_code"] == "no_unit_of_work"
    assert data["uow_mode"] == "per_operation"
    assert RAW_PATH in data["guidance"]
    assert RAW_PATH in data["help"]
    # The original liblcm text is preserved for debugging.
    assert "Not in the right state to register a change" in data["raw_error"]
    assert "outside any undo task" in data["error"]


def test_run_module_read_only_returns_read_only_guidance(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path, {
        "success": False,
        "error": LCM_ERROR,
        "undoable": False,
        "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
        "messages": [],
    })
    data = _parse(asyncio.run(execution_mod.handle_run_module({
        "code": _CODE,
        "project_name": "TestProj_310ro",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
    })))
    assert data["error_code"] == "no_unit_of_work"
    assert data["uow_mode"] == "read_only"
    assert "write_enabled=true" in data["guidance"]


# ---------------------------------------------------------------------------
# nested_unit_of_work rejection now names the legal raw path
# ---------------------------------------------------------------------------

def _nested_uow_rejection(monkeypatch, tmp_path, per_op):
    _stub_env(monkeypatch, tmp_path, {"success": True})

    def _boom(*a, **k):
        raise AssertionError("must not run the subprocess")

    monkeypatch.setattr(execution_mod, "run_script_async", _boom)
    monkeypatch.setattr(execution_mod, "_probe_undoable_capability", lambda: per_op)
    return _parse(asyncio.run(execution_mod.handle_run_module({
        "code": (
            "from SIL.LCModel.Infrastructure import UndoableUnitOfWorkHelper\n"
            "if modifyAllowed:\n"
            "    h = UndoableUnitOfWorkHelper(action_handler, 'u', 'r')\n"
        ),
        "project_name": "TestProj_310nested",
        "write_enabled": True,
        "confirmed": True,
        "skip_api_check": True,
        "skip_module_check": True,
    })))


def test_nested_uow_per_op_names_undoable_operation(monkeypatch, tmp_path):
    data = _nested_uow_rejection(monkeypatch, tmp_path, per_op=True)
    assert data["error_code"] == "nested_unit_of_work"
    steps = " ".join(data["next_steps"])
    assert RAW_PATH in steps
    assert "no_unit_of_work" in steps
    assert "Just perform the mutation directly" not in steps


def test_nested_uow_legacy_keeps_write_directly(monkeypatch, tmp_path):
    data = _nested_uow_rejection(monkeypatch, tmp_path, per_op=False)
    assert data["error_code"] == "nested_unit_of_work"
    steps = " ".join(data["next_steps"])
    assert "Just perform the mutation directly" in steps
    assert RAW_PATH not in steps
