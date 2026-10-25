#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #115 sibling: shared CLR skip helper catches non-ImportError init failures."""

import builtins

import pytest

from conftest import require_live_clr


def test_require_live_clr_skips_on_runtime_error(monkeypatch):
    """importorskip would ERROR; require_live_clr must SKIP instead."""
    real_import = builtins.__import__

    def _boom(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "clr":
            raise RuntimeError("Could not find libmono")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _boom)

    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_live_clr()
    assert "Could not find libmono" in str(excinfo.value)


def test_require_live_clr_skips_on_import_error(monkeypatch):
    real_import = builtins.__import__

    def _missing(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "clr":
            raise ImportError("no such module")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _missing)

    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_live_clr()
    assert "no such module" in str(excinfo.value)
