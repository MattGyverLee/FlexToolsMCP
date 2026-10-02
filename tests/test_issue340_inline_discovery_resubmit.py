#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #340 -- api_discovery_required said "resubmit" but an identical
resubmit was refused again.

The WRITE branch of the zero-discovery gate inlined get_object_api docs for
the detected entities (#29) but never recorded them as discovered, so the
next submission took the same branch. Now the inlined entities are recorded
the way get_object_api records them, and the copy says so.

Subprocess and project access are stubbed -- no FieldWorks, no live project.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.handlers.execution import (
    _api_discovery_required_copy,
    _names_covered_by_inline,
    _record_inline_discovery,
)
from flextoolsmcp.server.session import SessionState


class _FakeIndex:
    """Just enough of APIIndex for the discovery gates."""

    casting_index = None

    def __init__(self):
        self.flexicon = {
            "entities": {
                "FLExProject": {
                    "properties": [
                        {"name": "LexEntry", "return_type": "LexEntryOperations"},
                    ],
                },
                "LexEntryOperations": {
                    "category": "lexicon",
                    "import_statement": "from flexicon import LexEntryOperations",
                    "methods": [
                        {"name": "Delete", "signature": "Delete(entry_or_hvo)", "is_mutating": True},
                        {"name": "GetAll", "signature": "GetAll()"},
                    ],
                    "properties": [],
                },
            }
        }

    def ensure_casting_index_loaded(self):
        return None


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


@pytest.fixture
def stub_env(monkeypatch, tmp_path, reset_session_state):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    idx = _FakeIndex()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: idx)
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
        lambda code: {"is_cud": True, "operations": ["DELETE (Delete())"]},
    )
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs",
        lambda code, ci, tree, **k: {"has_casting_issues": False, "casting_issues": []},
    )
    monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
    monkeypatch.setattr(
        execution_mod, "perform_pre_write_backup",
        lambda name, **k: {"path": None, "created": False, "skipped_reason": "backup_before_write=false"},
    )
    calls = {"n": 0}

    async def _fake_run(path, timeout_seconds):
        calls["n"] += 1
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

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)
    return calls


_WRITE_CODE = (
    "for e in list(project.LexEntry.GetAll()):\n"
    "    if modifyAllowed:\n"
    "        project.LexEntry.Delete(e)\n"
)


def _write_args():
    return {
        "code": _WRITE_CODE,
        "project_name": "TestProj_340",
        "write_enabled": True,
        "confirmed": True,
    }


def test_refused_then_identical_resubmit_passes(stub_env):
    first = _parse(asyncio.run(execution_mod.handle_run_module(_write_args())))
    assert first["error_code"] == "api_discovery_required"
    assert "LexEntryOperations" in first["_inline_discovery"]
    # The copy is truthful: it names the recorded entities and the resubmit.
    assert "recorded them as discovered" in first["message"]
    assert "LexEntryOperations" in first["hint"]
    assert first["session"]["discovered_api_count"] > 0

    second = _parse(asyncio.run(execution_mod.handle_run_module(_write_args())))
    assert second.get("error_code") != "api_discovery_required", second
    assert second.get("error_code") != "undiscovered_entity", second
    assert stub_env["n"] == 1, "identical resubmit should reach the runner"


def test_resubmit_that_fails_later_is_not_flagged_identical(stub_env, monkeypatch):
    """The resubmit the refusal prescribed passes the gate; if the script then
    fails at runtime that is a new answer, not an identical resubmit."""
    async def _failing_run(path, timeout_seconds):
        payload = {
            "success": False,
            "error": "Execution error: boom",
            "error_type": "RuntimeError",
            "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
            "messages": [],
        }
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
            "stderr": "",
            "timeout": False,
            "returncode": 0,
        }

    monkeypatch.setattr(execution_mod, "run_script_async", _failing_run)
    first = _parse(asyncio.run(execution_mod.handle_run_module(_write_args())))
    assert first["error_code"] == "api_discovery_required"
    second = _parse(asyncio.run(execution_mod.handle_run_module(_write_args())))
    assert second.get("error_code") != "api_discovery_required", second
    assert "identical_resubmit" not in second, second
    assert (second.get("_assistance") or {}).get("pattern_detected") != "identical_resubmit"


def test_record_inline_discovery_mirrors_get_object_api():
    session = SessionState()
    inline = {
        "LexEntryOperations": {
            "methods": [{"name": "Delete"}, {"name": "GetAll"}],
            "properties": [{"name": "Count"}],
        }
    }
    recorded = _record_inline_discovery(session, inline)
    assert recorded == ["LexEntryOperations"]
    assert "LexEntryOperations" in session.validated_apis
    assert {"LexEntryOperations.Delete", "LexEntryOperations.GetAll",
            "LexEntryOperations.Count"} <= session.discovered_apis
    assert not session.auto_discovered_apis


def test_empty_inline_records_nothing():
    session = SessionState()
    assert _record_inline_discovery(session, {}) == []
    assert not session.discovered_apis
    assert not session.validated_apis


def test_names_covered_by_inline_matches_both_spellings():
    inline = {"POSOperations": {}, "LexSense": {}}
    assert _names_covered_by_inline(
        ["POS", "POSOperations", "LexSenseOperations", "Senses"], inline
    ) == ["POS", "POSOperations", "LexSenseOperations"]


def test_copy_drops_auto_entities_covered_by_inline():
    session = SessionState()
    session.record_auto_discovered_api("LexEntryOperations")
    session.record_auto_discovered_api("POSOperations")
    copy = _api_discovery_required_copy(
        session, has_inline_discovery=True, inlined_entities=["LexEntryOperations"],
    )
    assert copy["auto_discovered_pending_validation"] == ["POSOperations"]
    assert "the same code now passes this gate" in copy["message"]
    assert "POSOperations" in copy["hint"]
