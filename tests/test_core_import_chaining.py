#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: core recipe modules must chain dual-mode ImportErrors (deferred-issues section 3)."""

import builtins
import sys

import pytest

from flextoolsmcp.server import recipes as recipes_mod


def test_import_local_recipes_module_chains_when_both_paths_fail(monkeypatch):
    original = builtins.__import__

    def _boom(name, globals=None, locals=None, fromlist=(), level=0):
        fl = fromlist or ()
        if (name == "" and "local_recipes" in fl) or (
            name == "server" and "local_recipes" in fl
        ):
            raise ImportError(f"cannot import {name or 'relative'} local_recipes")
        return original(name, globals, locals, fl, level)

    # Deleting from sys.modules is test-session-global: handlers that already
    # imported local_recipes (e.g. catalog) keep the old module object, so
    # later tests patching the fresh module would silently miss. Save and
    # restore, so this test cannot orphan a stale module for later tests
    # (that orphaning is what broke test_list_recipes in full-suite order).
    saved = {k: v for k, v in sys.modules.items() if k.endswith("local_recipes")}
    for key in saved:
        del sys.modules[key]

    monkeypatch.setattr(builtins, "__import__", _boom)

    try:
        with pytest.raises(ImportError) as excinfo:
            recipes_mod._import_local_recipes_module()
    finally:
        for key in list(sys.modules):
            if key.endswith("local_recipes") and key not in saved:
                del sys.modules[key]
        sys.modules.update(saved)

    assert excinfo.value.__cause__ is not None
    assert "local_recipes" in str(excinfo.value.__cause__)


def test_recipes_and_local_recipes_still_import():
    from flextoolsmcp.server import local_recipes

    assert callable(recipes_mod.rank_recipes)
    assert callable(local_recipes.load_local_recipes)
