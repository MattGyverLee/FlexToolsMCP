#!/usr/bin/env python3
"""Tests for the shared flexicon availability guard (issue #115)."""

import builtins

import pytest

from conftest import require_live_flexicon


def test_require_live_flexicon_skips_on_non_import_error(monkeypatch):
    """Bare Exception during flexicon init must become pytest.skip, not ERROR."""
    real_import = builtins.__import__

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "flexicon":
            raise Exception("64bit FieldWorks 9 not found")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setitem(__import__("sys").modules, "flexicon", None)
    monkeypatch.delitem(__import__("sys").modules, "flexicon", raising=False)
    monkeypatch.setattr(builtins, "__import__", _import)

    with pytest.raises(pytest.skip.Exception) as excinfo:
        require_live_flexicon()
    assert "flexicon unavailable" in str(excinfo.value)
