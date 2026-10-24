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

    for key in list(sys.modules):
        if key.endswith("local_recipes"):
            del sys.modules[key]

    monkeypatch.setattr(builtins, "__import__", _boom)

    with pytest.raises(ImportError) as excinfo:
        recipes_mod._import_local_recipes_module()

    assert excinfo.value.__cause__ is not None
    assert "local_recipes" in str(excinfo.value.__cause__)


def test_recipes_and_local_recipes_still_import():
    from flextoolsmcp.server import local_recipes

    assert callable(recipes_mod.rank_recipes)
    assert callable(local_recipes.load_local_recipes)
