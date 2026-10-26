#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: dual-mode import fallbacks must chain ImportErrors (deferred-issues §3)."""

import builtins

import pytest

from flextoolsmcp.server.handlers import _import_helper as ih


def test_safe_import_chains_when_fallback_also_fails(monkeypatch):
    real_import = builtins.__import__
    calls = []

    def _import(name, globals=None, locals=None, fromlist=(), level=0):
        calls.append(name)
        if name in ("pkg.mod", "script.mod"):
            raise ImportError(f"no module named {name!r}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _import)

    with pytest.raises(ImportError) as excinfo:
        ih.safe_import("pkg.mod", "script.mod")

    assert calls == ["pkg.mod", "script.mod"]
    assert excinfo.value.__cause__ is not None
    assert "pkg.mod" in str(excinfo.value.__cause__)


def test_import_with_fallback_preserves_success_on_primary():
    assert ih._import_with_fallback(lambda: 1, lambda: 2) == 1


def test_import_with_fallback_uses_fallback_after_import_error():
    assert ih._import_with_fallback(
        lambda: (_ for _ in ()).throw(ImportError("primary")),
        lambda: "fallback",
    ) == "fallback"
