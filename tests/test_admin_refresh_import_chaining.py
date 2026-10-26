#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: admin refresh paths must chain dual-mode ImportErrors (deferred-issues section 3).

Open PR #407 chains most handler imports but leaves the lazy refresh-module loader
on the old silent-discard pattern.
"""

import builtins

import pytest

from flextoolsmcp.server.handlers import admin


def test_load_refresh_module_chains_when_both_paths_fail(monkeypatch):
    real_import = builtins.__import__

    def _boom(name, globals=None, locals=None, fromlist=(), level=0):
        if fromlist and "refresh" in fromlist:
            raise ImportError("package-mode refresh import failed")
        if name == "refresh":
            raise ImportError("script-mode refresh import failed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _boom)

    with pytest.raises(ImportError) as excinfo:
        admin._load_refresh_module()

    assert "refresh" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
