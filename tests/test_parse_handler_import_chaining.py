#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: parse-handler dual-mode imports must chain ImportErrors (deferred-issues section 3)."""

import builtins
import importlib

import pytest


def test_parse_common_chains_when_both_project_discovery_paths_fail(monkeypatch):
    """Runtime import inside _resolve_project must preserve the first failure."""
    from flextoolsmcp.server.handlers.parse import common

    real_import = builtins.__import__

    def _fail_server_project_discovery(name, *args, **kwargs):
        if name == "server.project_discovery" or name.endswith("project_discovery"):
            raise ImportError(f"cannot import {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fail_server_project_discovery)

    with pytest.raises(ImportError) as excinfo:
        common._resolve_project("SomeProject")

    assert excinfo.value.__cause__ is not None


def test_parse_handler_modules_import():
    """Smoke: chained parse-handler import blocks still load under package mode."""
    for mod_name in (
        "flextoolsmcp.server.handlers.parse.common",
        "flextoolsmcp.server.handlers.parse.try_word",
        "flextoolsmcp.server.handlers.parse.runs",
        "flextoolsmcp.server.handlers.parse.sandbox",
        "flextoolsmcp.server.handlers.parse.filing",
    ):
        mod = importlib.import_module(mod_name)
        assert mod is not None
