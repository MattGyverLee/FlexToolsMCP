#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The write ladder is EXTRACTED, not copied (parser-check CP4, FR-002, R-07).

`run_module`'s confirmation, access gate and backup rungs used to be inline in
`handle_run_module`. CP4 moves them into `server/write_ladder.py` so filing
walks the SAME rungs through the SAME code (FR-002: "reuse run_module's
mechanisms, not copies of them"; constitution Principle VI).

What this file proves:

  * `handle_run_module` reaches each ladder leaf exactly once per path, and
    only through `write_ladder` -- the leaves are patched here and counted;
  * no rung is re-implemented: an AST scan finds no direct call to
    `probe_project_access` / `perform_pre_write_backup` / `build_access_remedy`
    inside `handle_run_module`, inside the filing path of
    `handlers/parse.py`, or anywhere in the `server/filing/` package. The one
    place those leaves are called for a write decision is `write_ladder.py`.

The behaviour of the rungs themselves is proven by the EXISTING ladder suite
(`test_issue55_write_safety_ladder.py`, `test_shared_mode_*.py`,
`test_issue92_write_path_e2e.py`, `test_async_locking.py`), which must pass
with no modification -- that is the extraction's exit gate (T008).
"""

import ast
import asyncio
import json
from pathlib import Path

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server import write_ladder
from flextoolsmcp.server.handlers import execution as execution_mod

SRC = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server"

#: The leaves a write decision may call only through write_ladder.
_LADDER_LEAVES = {"probe_project_access", "perform_pre_write_backup", "build_access_remedy"}


def _parse(resp_list):
    item = resp_list[0]
    return json.loads(item["text"] if isinstance(item, dict) else item.text)


def _stub_env(monkeypatch, tmp_path):
    """A mutating script that passes every non-ladder gate."""
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(
        execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []}
    )
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True, "mutating_calls": [],
            "unprotected_liblcm_calls": [], "confidence": "high",
        },
    )
    monkeypatch.setattr(
        execution_mod, "detect_cud_operations",
        lambda code: {"is_cud": True, "operations": ["CREATE (Create())"]},
    )
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs",
        lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []},
    )


class _Counter:
    def __init__(self, result=None, boom=False):
        self.calls = 0
        self.result = result
        self.boom = boom

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.boom:
            raise AssertionError("this ladder leaf must not be reached on this path")
        return self.result(*args, **kwargs) if callable(self.result) else self.result


def _free_decision(project_name):
    return write_ladder.AccessDecision(
        project_name=project_name, access=None, verdict="free",
        refusal=None, advisory=None,
    )


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def _ok_script(path, timeout_seconds):
    payload = {"success": True, "summary": {"info_count": 0, "warning_count": 0,
                                            "error_count": 0}, "messages": []}
    return {"stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
            "stderr": "", "timeout": False, "returncode": 0}


def _args(project, confirmed):
    return {
        "code": "if modifyAllowed:\n    project.LexEntry.Create(x)\n",
        "project_name": project,
        "write_enabled": True,
        "confirmed": confirmed,
        "skip_api_check": True,
        "skip_module_check": True,
    }


def test_unconfirmed_run_probes_access_and_predicts_backup_once(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path)
    probe = _Counter(_free_decision)
    intent = _Counter(write_ladder.BackupIntent(outcome="will_be_taken"))
    take = _Counter(boom=True)
    monkeypatch.setattr(write_ladder, "probe_write_access", probe)
    monkeypatch.setattr(write_ladder, "backup_intent", intent)
    monkeypatch.setattr(write_ladder, "take_backup", take)

    data = _parse(asyncio.run(execution_mod.handle_run_module(_args("LadderA", False))))

    assert data["error_code"] == "confirmation_required"
    assert (probe.calls, intent.calls, take.calls) == (1, 1, 0)
    assert data["backup"]["intent"] is True


def test_confirmed_run_probes_access_and_takes_backup_once(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path)
    monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
    monkeypatch.setattr(execution_mod, "run_script_async", _ok_script)
    probe = _Counter(_free_decision)
    intent = _Counter(boom=True)
    take = _Counter({"path": "/fake/backup", "created": True, "skipped_reason": None})
    monkeypatch.setattr(write_ladder, "probe_write_access", probe)
    monkeypatch.setattr(write_ladder, "backup_intent", intent)
    monkeypatch.setattr(write_ladder, "take_backup", take)

    data = _parse(asyncio.run(execution_mod.handle_run_module(_args("LadderB", True))))

    assert data.get("success") is True
    assert (probe.calls, intent.calls, take.calls) == (1, 0, 1)
    assert data["backup"]["path"] == "/fake/backup"


def test_a_refusal_from_the_access_decision_is_run_modules_project_locked(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path)
    monkeypatch.setattr(execution_mod, "run_script_async", _Counter(boom=True))
    refused = write_ladder.AccessDecision(
        project_name="LadderC", access=object(), verdict="open_exclusive",
        refusal={"guidance": "Close FieldWorks.", "lock_file_path": None,
                 "verdict": "open_exclusive", "sharing_enabled": False,
                 "holder_pid": 1, "holder_process": "FieldWorks", "remedy": "Close FieldWorks."},
        advisory=None,
    )
    monkeypatch.setattr(write_ladder, "probe_write_access", lambda name: refused)
    monkeypatch.setattr(write_ladder, "take_backup", _Counter(boom=True))

    data = _parse(asyncio.run(execution_mod.handle_run_module(_args("LadderC", True))))

    assert data["error_code"] == "project_locked"
    assert data["verdict"] == "open_exclusive"


# ---------------------------------------------------------------------------
# No copy of the rung code anywhere a write decision is made
# ---------------------------------------------------------------------------


def _called_names(node):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                yield func.id
            elif isinstance(func, ast.Attribute):
                yield func.attr


def _function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"function {name!r} not found")


def test_handle_run_module_calls_no_ladder_leaf_directly():
    tree = ast.parse((SRC / "handlers" / "execution.py").read_text(encoding="utf-8"))
    body = _function(tree, "handle_run_module")
    direct = _LADDER_LEAVES & set(_called_names(body))
    assert not direct, f"handle_run_module calls {sorted(direct)} directly; use write_ladder"


def test_the_filing_path_calls_no_ladder_leaf_directly():
    tree = ast.parse((SRC / "handlers" / "parse.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "filing" not in node.name and node.name != "handle_flextools_parse_text":
            continue
        direct = _LADDER_LEAVES & set(_called_names(node))
        assert not direct, f"{node.name} calls {sorted(direct)} directly; use write_ladder"


def test_the_filing_package_calls_no_ladder_leaf_directly():
    filing = SRC / "filing"
    if not filing.is_dir():
        pytest.skip("server/filing does not exist yet")
    for path in filing.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        direct = _LADDER_LEAVES & set(_called_names(tree))
        assert not direct, f"{path.name} calls {sorted(direct)} directly; use write_ladder"


def test_write_ladder_is_where_the_leaves_are_called():
    tree = ast.parse((SRC / "write_ladder.py").read_text(encoding="utf-8"))
    called = set(_called_names(tree))
    assert {"probe_project_access", "build_access_remedy"} <= called
