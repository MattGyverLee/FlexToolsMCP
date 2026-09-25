#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The sandbox config cache is invalidated after every write run (parser-check
CP5, FR-026; research R-12 "Invalidate"; tasks T053, T054).

Specified API:

  * `FilingObserver.after_terminal(handle, runner)` calls
    `sandbox.cache.invalidate(project_name)` on every terminal filing run,
    whether or not the shared read worker is recycled. A failure there (an
    exception from `invalidate`, or the module failing to import) is logged
    and never propagated; the read-worker recycling still happens.
  * `handlers.execution.handle_run_module` calls
    `sandbox.cache.invalidate(project_name)` once after a write-enabled run
    that completed without error (`success is True`, no `error`). A
    read-only run and a write run that reported an error do not invalidate.
    The import is lazy and guarded (`_invalidate_sandbox_cache_after_write`):
    an import failure or an exception from `invalidate` never changes the
    run_module response.
"""

import asyncio
import json
import sys

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.filing.observer import FilingObserver
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.parse.worker_client import SHARED_ROLE
from flextoolsmcp.server.sandbox import cache as cache_mod
from flextoolsmcp.server.sandbox import paths

PROJECT = "InvalProj"
CACHE_MODULE = "flextoolsmcp.server.sandbox.cache"


@pytest.fixture
def invalidations(monkeypatch):
    calls = []

    def _record(project):
        calls.append(project)
        return 1

    monkeypatch.setattr(cache_mod, "invalidate", _record)
    return calls


def _make_entry(project):
    """A usable cache entry for `project` under the (temp) sandbox root."""
    inputs = {"fwdata": "x.fwdata", "size": 1, "mtime_ns": 1}
    key = cache_mod.compute_key(inputs)
    entry = paths.config_cache_dir(project) / key
    entry.mkdir(parents=True)
    (entry / cache_mod.CONFIG_NAME).write_text("<HermitCrabInput/>", encoding="utf-8")
    meta = {"schema": cache_mod.SCHEMA, "cache_key": key, "inputs": inputs,
            "invalidated_at": None}
    (entry / cache_mod.KEY_JSON).write_text(json.dumps(meta), encoding="utf-8")
    assert cache_mod.lookup(project, key, touch=False) is not None
    return key


# ---------------------------------------------------------------------------
# T053: the filing observer
# ---------------------------------------------------------------------------


class _Runner:
    def __init__(self, busy=False):
        self._busy = busy
        self.stale = []
        self.released = []

    def read_worker_busy(self, project):
        return self._busy

    def mark_read_worker_stale(self, project):
        self.stale.append(project)

    async def release_worker(self, project, *, role):
        self.released.append((project, role))


def _observer(recycle=True):
    return FilingObserver(project_name=PROJECT, plan={}, plan_id="0" * 64, backup={},
                          no_recovery_warning=None, send_receive=False,
                          access_verdict="free", recycle_read_worker=recycle,
                          claim_token="t")


@pytest.mark.parametrize("busy", [False, True])
def test_after_filing_the_projects_cache_is_invalidated(invalidations, busy):
    runner = _Runner(busy)
    asyncio.run(_observer().after_terminal(None, runner))
    assert invalidations == [PROJECT]
    assert runner.stale == ([PROJECT] if busy else [])


def test_after_filing_the_cache_is_invalidated_even_without_recycling(invalidations):
    asyncio.run(_observer(recycle=False).after_terminal(None, _Runner()))
    assert invalidations == [PROJECT]


def test_after_filing_a_real_entry_is_no_longer_usable(sandbox_root):
    key = _make_entry(PROJECT)
    asyncio.run(_observer().after_terminal(None, _Runner()))
    assert cache_mod.lookup(PROJECT, key, touch=False) is None
    meta = json.loads((paths.config_cache_dir(PROJECT) / key / cache_mod.KEY_JSON)
                      .read_text(encoding="utf-8"))
    assert meta["invalidated_at"]


def test_an_invalidate_failure_never_breaks_filing(monkeypatch):
    def _boom(project):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(cache_mod, "invalidate", _boom)
    runner = _Runner(busy=True)
    asyncio.run(_observer().after_terminal(None, runner))
    assert runner.stale == [PROJECT]


def test_a_sandbox_import_failure_never_breaks_filing(monkeypatch):
    monkeypatch.setitem(sys.modules, CACHE_MODULE, None)
    runner = _Runner()
    asyncio.run(_observer().after_terminal(None, runner))
    assert runner.released == [(PROJECT, SHARED_ROLE)]


# ---------------------------------------------------------------------------
# T054: run_module
# ---------------------------------------------------------------------------


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _stub_env(monkeypatch, tmp_path, *, payload, is_cud=True):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state",
                        lambda: {"is_healthy": True, "issues": []})
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
    monkeypatch.setattr(execution_mod, "detect_casting_needs",
                        lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []})
    monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
    monkeypatch.setattr(execution_mod, "perform_pre_write_backup",
                        lambda name, **k: {"path": None, "created": False,
                                           "skipped_reason": "backup_before_write=false"})

    async def _fake_run_script_async(path, timeout_seconds):
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
            "stderr": "",
            "timeout": False,
            "returncode": 0,
        }

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async)


_OK = {"success": True, "messages": [],
       "summary": {"info_count": 0, "warning_count": 0, "error_count": 0}}
_FAILED = {"success": False, "error": "boom", "error_type": "RuntimeError", "messages": []}


def _run(project, *, write_enabled):
    args = {
        "code": ("if modifyAllowed:\n    project.LexEntry.Create(x)\n" if write_enabled
                 else "x = project.LexEntry.GetAll()\n"),
        "project_name": project,
        "write_enabled": write_enabled,
        "confirmed": write_enabled,
        "skip_api_check": True,
        "skip_module_check": True,
    }
    result = asyncio.run(execution_mod.handle_run_module(args))
    item = result[0]
    return json.loads(item["text"] if isinstance(item, dict) else item.text)


def test_a_successful_write_run_invalidates(monkeypatch, tmp_path, invalidations):
    _stub_env(monkeypatch, tmp_path, payload=_OK)
    data = _run("InvalProj_write", write_enabled=True)
    assert data.get("success") is True
    assert invalidations == ["InvalProj_write"]


def test_a_read_only_run_does_not_invalidate(monkeypatch, tmp_path, invalidations):
    _stub_env(monkeypatch, tmp_path, payload=_OK, is_cud=False)
    data = _run("InvalProj_read", write_enabled=False)
    assert data.get("success") is True
    assert invalidations == []


def test_a_failed_write_run_does_not_invalidate(monkeypatch, tmp_path, invalidations):
    _stub_env(monkeypatch, tmp_path, payload=_FAILED)
    data = _run("InvalProj_failed", write_enabled=True)
    assert data.get("success") is not True
    assert invalidations == []


def test_a_sandbox_import_failure_never_breaks_run_module(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path, payload=_OK)
    monkeypatch.setitem(sys.modules, CACHE_MODULE, None)
    data = _run("InvalProj_noimport", write_enabled=True)
    assert data.get("success") is True
    assert "error_code" not in data or data.get("error_code") is None


def test_an_invalidate_exception_never_breaks_run_module(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path, payload=_OK)

    def _boom(project):
        raise OSError("cache unreadable")

    monkeypatch.setattr(cache_mod, "invalidate", _boom)
    data = _run("InvalProj_boom", write_enabled=True)
    assert data.get("success") is True


def test_a_successful_write_run_makes_a_real_entry_unusable(monkeypatch, tmp_path, sandbox_root):
    _stub_env(monkeypatch, tmp_path, payload=_OK)
    key = _make_entry("InvalProj_real")
    _run("InvalProj_real", write_enabled=True)
    assert cache_mod.lookup("InvalProj_real", key, touch=False) is None
