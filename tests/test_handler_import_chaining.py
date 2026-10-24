#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: handler dual-mode imports must chain ImportErrors (deferred-issues section 3)."""

import builtins

import pytest

from flextoolsmcp.server.handlers import _import_helper as ih


def test_safe_import_chains_when_both_paths_fail(monkeypatch):
    def _boom(name, *args, **kwargs):
        raise ImportError(f"cannot import {name}")

    monkeypatch.setattr(builtins, "__import__", _boom)

    with pytest.raises(ImportError) as excinfo:
        ih.safe_import("pkg.mod", "abs.mod")

    assert "abs.mod" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "pkg.mod" in str(excinfo.value.__cause__)


def test_handler_modules_import():
    """Smoke: chained handler import blocks still load under package mode."""
    from flextoolsmcp.server.handlers import api, catalog, execution, admin

    assert callable(execution.handle_run_module)
    assert callable(api.handle_get_object_api)
    assert callable(catalog.handle_list_categories)
    assert callable(admin.handle_start)
