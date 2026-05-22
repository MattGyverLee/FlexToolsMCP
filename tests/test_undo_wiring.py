#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression tests for #14 (Undo wiring).

Does NOT require a live FieldWorks installation -- exercises the session
state, script template rendering, error paths, and dispatch wiring only.
A separate integration test against a real project is needed to verify
end-to-end Undo execution.
"""

import asyncio
import json

import pytest

from server import APIIndex
from server.kernel import set_api_index, initialize_kernel, get_session_state, get_index_dir
from server.handlers.admin import handle_start, handle_undo_last_operation
from server.undo_subprocess import build_undo_script, parse_undo_result


def _init_kernel():
    initialize_kernel()
    api_index = APIIndex.load(get_index_dir())
    set_api_index(api_index)


def _start(project_name: str, write_enabled: bool, undoable: bool) -> dict:
    args = {
        "api_mode": "flexlibs2",
        "project_name": project_name,
        "output_type": "auto",
        "write_enabled": write_enabled,
        "undoable": undoable,
        "_user_provided_keys": {"project_name", "write_enabled", "undoable"},
    }
    r = asyncio.run(handle_start(args))
    return json.loads(r[0].text)


def test_session_undoable_field_present():
    """SessionState now exposes 'undoable' both as a field and in summary()."""
    _init_kernel()
    _start("Proj_undoable_field", write_enabled=True, undoable=True)
    ss = get_session_state()
    assert ss.undoable is True
    assert ss.summary().get("undoable") is True


def test_undoable_coerced_off_when_write_disabled():
    """undoable=True is silently coerced to False when write_enabled=False."""
    _init_kernel()
    data = _start("Proj_coerce", write_enabled=False, undoable=True)
    ss = get_session_state()
    assert ss.undoable is False
    # And a warning is surfaced so the LLM doesn't silently lose the request.
    warnings = data.get("warnings", [])
    assert any("coerced to False" in w for w in warnings), warnings


def test_undoable_inherited_on_same_project_restart():
    """Re-init on same project without undoable arg inherits prior value."""
    _init_kernel()
    _start("Proj_inherit", write_enabled=True, undoable=True)
    # Restart with no undoable arg (and not in _user_provided_keys)
    r = asyncio.run(handle_start({
        "api_mode": "flexlibs2",
        "project_name": "Proj_inherit",
        "output_type": "auto",
        "write_enabled": True,
        "_user_provided_keys": {"project_name", "write_enabled"},
    }))
    ss = get_session_state()
    assert ss.undoable is True, "Should inherit prior undoable=True on same project"


def test_undo_refuses_without_undoable():
    """handle_undo_last_operation refuses with a helpful message when
    session has undoable=False, instead of crashing in the subprocess."""
    _init_kernel()
    _start("Proj_no_undoable", write_enabled=True, undoable=False)
    r = asyncio.run(handle_undo_last_operation({"count": 1}))
    data = json.loads(r[0].text)
    assert data["success"] is False
    assert "undoable=False" in data["message"]


def test_undo_refuses_without_write():
    """Refuses if write_enabled=False."""
    _init_kernel()
    _start("Proj_no_write", write_enabled=False, undoable=True)
    r = asyncio.run(handle_undo_last_operation({"count": 1}))
    data = json.loads(r[0].text)
    assert data["success"] is False
    assert "Write mode" in data["message"]


def test_undo_refuses_without_project_name():
    """Refuses if no project_name in session."""
    _init_kernel()
    _start("Proj_temp", write_enabled=True, undoable=True)
    get_session_state().project_name = ""
    r = asyncio.run(handle_undo_last_operation({"count": 1}))
    data = json.loads(r[0].text)
    assert data["success"] is False
    assert "project_name" in data["message"]


def test_undo_script_template_renders_valid_python():
    """The Undo subprocess script must always be valid Python."""
    import ast

    for count in (1, 5, 100):
        script = build_undo_script(project_name="Proj_X", undo_count=count)
        try:
            ast.parse(script)
        except SyntaxError as e:
            pytest.fail(f"build_undo_script(count={count}) produced invalid Python: {e}")


def test_undo_script_template_quotes_project_name_safely():
    """A project name containing quotes/backslashes must not break the
    rendered script (repr() handles this; we just sanity-check here)."""
    import ast

    nasty = 'Proj"with\'quotes\\and\\nbackslash'
    script = build_undo_script(project_name=nasty, undo_count=1)
    ast.parse(script)
    assert "PROJECT_NAME" in script
    # The repr() form must be present somewhere on the PROJECT_NAME line
    assert repr(nasty) in script


def test_parse_undo_result_extracts_json():
    """parse_undo_result picks up the sentinel-wrapped JSON payload."""
    stdout = (
        "[INFO] Running\n"
        "__UNDO_RESULT_START__\n"
        '{"success": true, "undid": 2, "stack_depth_before": 5, "stack_depth_after": 3}\n'
        "__UNDO_RESULT_END__\n"
        "[INFO] Done\n"
    )
    parsed = parse_undo_result(stdout)
    assert parsed["success"] is True
    assert parsed["undid"] == 2
    assert parsed["stack_depth_before"] == 5


def test_parse_undo_result_missing_marker():
    """No marker => structured error rather than blowup."""
    parsed = parse_undo_result("something failed before the script even ran")
    assert parsed["success"] is False
    assert parsed["error"] == "no_result_marker"


def test_parse_undo_result_malformed_json():
    """Malformed payload => structured error with the raw text."""
    stdout = "__UNDO_RESULT_START__\nnot json\n__UNDO_RESULT_END__"
    parsed = parse_undo_result(stdout)
    assert parsed["success"] is False
    assert parsed["error"] == "result_parse_failed"
    assert "raw" in parsed


def test_run_module_checkpoint_recorded_logic():
    """Session-side bookkeeping: when undoable & write_enabled, run_module
    should append to undo_checkpoints. We can't easily invoke the real
    handler without a FW project, so just verify the field exists and is
    a list that can be appended to."""
    _init_kernel()
    _start("Proj_chk", write_enabled=True, undoable=True)
    ss = get_session_state()
    assert hasattr(ss, "undo_checkpoints")
    assert isinstance(ss.undo_checkpoints, list)
    # The handler-side append uses these keys -- enforce them in a fake
    # checkpoint so a future shape change here forces test attention.
    ss.undo_checkpoints.append({
        "op_id": "fake-op",
        "seq": 1,
        "timestamp": "2026-05-22T00:00:00",
        "project_name": "Proj_chk",
        "info_count": 0,
        "warning_count": 0,
        "error_count": 0,
    })
    assert len(ss.undo_checkpoints) == 1


def test_undo_pops_checkpoint_on_no_real_undo():
    """Even without a live FW project, the handler must NOT pop checkpoints
    when the subprocess fails (so the local log stays in sync with reality)."""
    _init_kernel()
    _start("Proj_no_pop", write_enabled=True, undoable=True)
    ss = get_session_state()
    ss.undo_checkpoints = [{"op_id": "fake", "seq": 1}]
    r = asyncio.run(handle_undo_last_operation({"count": 1}))
    data = json.loads(r[0].text)
    # Subprocess will fail (no real flexlibs2/FW available) -> undid == 0
    assert data["success"] is False
    assert data.get("undid", 0) == 0
    # And no checkpoint should be popped
    assert ss.undo_checkpoints == [{"op_id": "fake", "seq": 1}]
