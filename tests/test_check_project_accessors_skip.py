#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #115 sibling: maintenance script must skip, not crash, without FieldWorks."""

import builtins
import importlib.util
import sys
from pathlib import Path

def _load_check_project_accessors_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_project_accessors.py"
    spec = importlib.util.spec_from_file_location("check_project_accessors", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_check_project_accessors_skips_on_non_import_error(monkeypatch, capsys):
    """Installed pyflexicon without a .NET runtime must exit 0 with [SKIP], not traceback."""
    mod = _load_check_project_accessors_module()
    real_import = builtins.__import__

    def _boom(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "flexicon":
            raise RuntimeError("Failed to create a default .NET runtime")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _boom)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "[SKIP]" in out
    assert "Failed to create a default .NET runtime" in out


def test_check_project_accessors_skips_on_import_error(monkeypatch, capsys):
    mod = _load_check_project_accessors_module()
    real_import = builtins.__import__

    def _missing(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "flexicon":
            raise ImportError("no such module")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _missing)

    assert mod.main() == 0
    assert "[SKIP]" in capsys.readouterr().out
