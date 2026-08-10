#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp 2.0 compatibility -- lazy loader diagnostics.

`src/flextoolsmcp/server/__init__.py`'s `__getattr__` lazily execs
`server.py` via `importlib.util.spec_from_file_location(...).exec_module(...)`.
Because `__getattr__` participates in Python's `from X import Y` protocol,
CPython's IMPORT_FROM opcode reinterprets ANY `AttributeError` escaping it as
"attribute absent", re-raising a generic `ImportError: cannot import name`
that destroys the real traceback. This is exactly what happened when mcp
2.0.0 removed `Server.list_tools()`/`call_tool()`: server.py raised
`AttributeError: 'Server' object has no attribute 'list_tools'` at
decorator-registration time, and every CI log downstream read
`ImportError: cannot import name 'APIIndex'`, naming neither mcp nor the
real failure site.

Covers:
- P0: an `AttributeError` raised while *executing* server.py surfaces as a
  clearly-labeled `ImportError` with the original exception chained via
  `__cause__`, not a laundered "cannot import name".
- P1: a cached load failure short-circuits on the SECOND lazy attribute
  touch -- server.py is not re-executed (no compounding side effects from
  logging setup / decorator registration).
- `list_tools` (and its siblings `call_tool`, `server`) are reachable via
  `from flextoolsmcp.server import list_tools` -- they were previously
  absent from LAZY_IMPORTS entirely, so nothing exercised the exact seam
  that broke.

Run with:
    python -m pytest tests/test_lazy_loader_diagnostics.py -q
"""

import importlib.util as importlib_util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import flextoolsmcp.server as fts_server  # noqa: E402


class _FakeLoader:
    """Wraps a real loader's spec but raises on exec_module, counting calls."""

    call_count = 0

    def __init__(self, real_loader):
        self._real_loader = real_loader

    def exec_module(self, module):
        _FakeLoader.call_count += 1
        raise AttributeError(
            "'Server' object has no attribute 'list_tools' (simulated mcp 2.0 removal)"
        )

    def create_module(self, spec):  # pragma: no cover - not exercised
        return None


@pytest.fixture(autouse=True)
def _reset_lazy_loader_state():
    """Isolate each test from the real module-level lazy-loader cache.

    These caches (`_server_module_cache`, `_server_load_error`) are genuine
    module attributes, not lazily loaded ones, so plain attribute
    get/set bypasses `__getattr__` entirely.
    """
    fts_server._server_module_cache = None
    fts_server._server_load_error = None
    _FakeLoader.call_count = 0
    yield
    fts_server._server_module_cache = None
    fts_server._server_load_error = None


def _patched_spec_from_file_location(orig):
    def _patched(*args, **kwargs):
        spec = orig(*args, **kwargs)
        spec.loader = _FakeLoader(spec.loader)
        return spec

    return _patched


def test_exec_module_failure_is_diagnosed_not_laundered(monkeypatch):
    """An AttributeError from exec'ing server.py must become a clearly
    labeled, chained ImportError -- not a generic 'cannot import name'.
    """
    orig = importlib_util.spec_from_file_location
    monkeypatch.setattr(
        importlib_util,
        "spec_from_file_location",
        _patched_spec_from_file_location(orig),
    )

    with pytest.raises(ImportError) as excinfo:
        _ = fts_server.APIIndex

    assert "NOT a missing-attribute error" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, AttributeError)
    assert "simulated mcp 2.0 removal" in str(excinfo.value.__cause__)


def test_second_access_after_failure_does_not_re_execute(monkeypatch):
    """Once a load failure is cached, later lazy attribute touches must fail
    fast from the cached error instead of re-executing server.py.
    """
    orig = importlib_util.spec_from_file_location
    monkeypatch.setattr(
        importlib_util,
        "spec_from_file_location",
        _patched_spec_from_file_location(orig),
    )

    with pytest.raises(ImportError):
        _ = fts_server.APIIndex
    assert _FakeLoader.call_count == 1

    with pytest.raises(ImportError) as excinfo:
        _ = fts_server.main

    # exec_module (and therefore spec_from_file_location's fake loader) must
    # NOT have been invoked a second time.
    assert _FakeLoader.call_count == 1
    assert excinfo.value.__cause__ is not None


def test_list_tools_is_importable_from_flextoolsmcp_server():
    """Locks in that list_tools/call_tool/server are lazy-loadable.

    Prior to this fix these names were absent from LAZY_IMPORTS, so
    `from flextoolsmcp.server import list_tools` raised
    `ImportError: cannot import name 'list_tools'` even when server.py
    itself was perfectly importable.
    """
    from flextoolsmcp.server import call_tool, list_tools, server

    assert callable(list_tools)
    assert callable(call_tool)
    assert server is not None
