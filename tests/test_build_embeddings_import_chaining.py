#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: build_embeddings dual-mode imports chain ImportErrors (deferred-issues section 3)."""

import pytest

from flextoolsmcp import build_embeddings, recipe_cli


def _chain_harness(primary, fallback):
    try:
        return primary()
    except ImportError as first_exc:
        try:
            return fallback()
        except ImportError as second_exc:
            raise second_exc from first_exc


def test_dual_import_fallback_chains_when_both_fail():
    with pytest.raises(ImportError) as excinfo:
        _chain_harness(
            lambda: (_ for _ in ()).throw(ImportError("package-mode failed")),
            lambda: (_ for _ in ()).throw(ImportError("script-mode failed")),
        )
    assert "script-mode failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "package-mode failed" in str(excinfo.value.__cause__)


def test_build_embeddings_module_imports():
    assert callable(build_embeddings.get_index_dir)
    assert callable(build_embeddings.sort_json_arrays)


def test_recipe_cli_module_imports():
    assert callable(recipe_cli.main)
    assert callable(recipe_cli.is_kebab_case)
