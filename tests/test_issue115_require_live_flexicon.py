#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #115: shared flexicon skip helper catches non-ImportError init failures."""

import builtins

import pytest

from conftest import require_live_flexicon


def test_require_live_flexicon_skips_on_bare_exception(monkeypatch):
    """importorskip would ERROR; require_live_flexicon must SKIP instead."""
    real_import = builtins.__import__

    def _boom(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "flexicon":
            raise Exception("64bit FieldWorks 9 not found")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _boom)

    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_live_flexicon()
    assert "64bit FieldWorks 9 not found" in str(excinfo.value)


def test_require_live_flexicon_skips_on_import_error(monkeypatch):
    real_import = builtins.__import__

    def _missing(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "flexicon":
            raise ImportError("no such module")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _missing)

    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_live_flexicon()
    assert "no such module" in str(excinfo.value)
