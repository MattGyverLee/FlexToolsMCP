#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 4 US2 handler-level capture (FR-011, FR-012).

Capture rules through handle_run_module with a stub executor:
- Captured with intent + at least 4 real lines on success.
- Not captured for a 2-line probe, an empty intent, or a failed run.
- requires_write only when write-enabled AND mutating.
- Issue #309: swallowed-exception / trivial-output runs are not captured;
  requires_write follows the run's write evidence (LCM action count).
"""

import asyncio
import importlib
import json
from pathlib import Path


def _import_local_recipes():
    try:
        return importlib.import_module("flextoolsmcp.server.local_recipes")
    except ImportError:
        return importlib.import_module("server.local_recipes")


def _load_rows():
    mod = _import_local_recipes()
    for name in ("load_local_recipes", "load_all", "list_local_recipes", "get_all"):
        fn = getattr(mod, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                return []
    for name in ("get_recipe_path", "get_recipes_path", "get_store_path"):
        fn = getattr(mod, name, None)
        if callable(fn):
            try:
                path = Path(str(fn()))
            except Exception:
                return []
            if not path.exists():
                return []
            rows = []
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
            return rows
    return []


def _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery):
    from flextoolsmcp.server import kernel

    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    # Real API index so real validators behave.
    try:
        from flextoolsmcp.server import APIIndex, get_index_dir
        idx = APIIndex.load(get_index_dir())
        monkeypatch.setattr(execution_mod, "get_api_index", lambda: idx)
        kernel.set_api_index(idx)
    except Exception:
        pass
    kernel.session_state.configure(session_id="test-capture", api_mode="flexicon")
    # Never copy a real project from a unit test: stub the pre-write backup.
    monkeypatch.setattr(
        execution_mod, "perform_pre_write_backup",
        lambda *_a, **_k: {"path": None, "created": False, "skipped_reason": "test"})


GOOD_CODE = (
    "entries = project.LexEntry.GetAll()\n"
    "for entry in entries:\n"
    "    senses = project.LexEntry.GetAllSenses(entry)\n"
    "    for sense in senses:\n"
    "        report.Info(project.Senses.GetGloss(sense))\n"
)

MUTATING_CODE = (
    "from flexicon import LexEntryOperations\n"
    "entries = project.LexEntry.GetAll()\n"
    "for entry in entries:\n"
    "    if modifyAllowed:\n"
    "        project.LexEntry.SetLexemeForm(entry, 'test-form')\n"
)


_INFO = [{"type": "info", "message": "gloss one", "ref": None}]


def _success_result():
    return {
        "success": True, "messages": list(_INFO), "info_count": 1,
        "warning_count": 0, "error_count": 0,
        "write_certification": {"performs_writes": False},
    }


def _fake_ok(payload):
    async def _fake(script_path, timeout_seconds=300, **_k):
        stdout = "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload)
        return {"stdout": stdout, "stderr": "", "returncode": 0, "timeout": False}
    return _fake


def _fake_fail(payload):
    async def _fake(script_path, timeout_seconds=300, **_k):
        stdout = "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload)
        return {"stdout": stdout, "stderr": "", "returncode": 0, "timeout": False}
    return _fake


def _base_args(code, intent, write_enabled=False, **extra):
    args = {"code": code, "project_name": "Sena 3",
            "write_enabled": write_enabled, "user_intent": intent,
            "skip_module_check": True, "source": "existing"}
    args.update(extra)
    return args


def test_captured_with_intent_and_real_lines(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(_success_result()))
    args = _base_args(GOOD_CODE, "list glosses")
    result = asyncio.new_event_loop().run_until_complete(
        execution_mod.handle_run_module(args))
    payload = json.loads(result[0].text)
    assert payload.get("success") is True
    rows = _load_rows()
    assert len(rows) == 1
    assert rows[0]["intent"] == "list glosses"
    assert rows[0]["requires_write"] is False


def test_not_captured_for_short_probe(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(_success_result()))
    args = _base_args("x = 1\ny = 2\n", "probe")
    asyncio.new_event_loop().run_until_complete(
        execution_mod.handle_run_module(args))
    assert _load_rows() == []


def test_not_captured_for_empty_intent(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(_success_result()))
    args = _base_args(GOOD_CODE, "   ")
    asyncio.new_event_loop().run_until_complete(
        execution_mod.handle_run_module(args))
    assert _load_rows() == []


def test_not_captured_for_failed_run(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_fail(
        {"success": False, "error": "boom", "messages": [],
         "info_count": 0, "warning_count": 0, "error_count": 1}))
    args = _base_args(GOOD_CODE, "list glosses")
    asyncio.new_event_loop().run_until_complete(
        execution_mod.handle_run_module(args))
    assert _load_rows() == []


def test_requires_write_only_when_mutating(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(
        {"success": True, "messages": list(_INFO), "info_count": 1,
         "warning_count": 0, "error_count": 0,
         "write_certification": {"performs_writes": True}}))
    args = _base_args(MUTATING_CODE, "mutating run",
                      write_enabled=True, confirmed=True)
    result = asyncio.new_event_loop().run_until_complete(
        execution_mod.handle_run_module(args))
    payload = json.loads(result[0].text)
    assert payload.get("success") is True
    rows = _load_rows()
    assert rows and rows[0]["requires_write"] is True


# ---------------------------------------------------------------------------
# Issue #309: remember gate + requires_write from write evidence
# ---------------------------------------------------------------------------

SWALLOW_CODE = (
    "for wf in project.Wordforms.GetAll():\n"
    "    try:\n"
    # A real WordformOperations method: since #304 project.Wordforms resolves
    # to WordformOperations, so an invented name is rejected as unknown_method.
    "        status = project.Wordforms.GetSpellingStatus(wf)\n"
    "    except Exception:\n"
    "        status = 'No - Unknown issue'\n"
    "    report.Info('Analyzed %s: %s' % (wf, status))\n"
)


def _run(execution_mod, args):
    result = asyncio.new_event_loop().run_until_complete(
        execution_mod.handle_run_module(args))
    return json.loads(result[0].text)


def test_not_captured_for_swallowed_exception(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(_success_result()))
    payload = _run(execution_mod, _base_args(SWALLOW_CODE, "top 10 unparsed wordforms"))
    assert payload.get("success") is True
    assert _load_rows() == []


def test_not_captured_for_trivial_repeated_messages(monkeypatch, tmp_path):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    msgs = [{"type": "info", "message": "Analyzed 000: No - Unknown issue", "ref": None}] * 24
    res = _success_result()
    res.update(messages=msgs, info_count=24)
    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(res))
    payload = _run(execution_mod, _base_args(GOOD_CODE, "top 10 unparsed wordforms"))
    assert payload.get("success") is True
    assert _load_rows() == []


def test_write_enabled_run_with_lcm_actions_requires_write(monkeypatch, tmp_path):
    """Preflight saw no write, but LCM counted actions: store as a write."""
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    res = _success_result()
    res["lcm_undoable_action_count"] = 7
    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(res))
    payload = _run(execution_mod, _base_args(GOOD_CODE, "repair cl.10 features",
                                             write_enabled=True, confirmed=True))
    assert payload.get("success") is True
    rows = _load_rows()
    assert rows and rows[0]["requires_write"] is True
    assert rows[0]["operations"] == ["read", "write"]


def test_write_enabled_run_with_zero_actions_stays_read(monkeypatch, tmp_path):
    """A write-enabled session running read-only code that changed nothing."""
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    import flextoolsmcp.server.handlers.execution as execution_mod
    import flextoolsmcp.server.project_discovery as project_discovery
    _stub_minimal(monkeypatch, tmp_path, execution_mod, project_discovery)

    res = _success_result()
    res["lcm_undoable_action_count"] = 0
    monkeypatch.setattr(execution_mod, "run_script_async", _fake_ok(res))
    payload = _run(execution_mod, _base_args(GOOD_CODE, "list glosses",
                                             write_enabled=True, confirmed=True))
    assert payload.get("success") is True
    rows = _load_rows()
    assert rows and rows[0]["requires_write"] is False
