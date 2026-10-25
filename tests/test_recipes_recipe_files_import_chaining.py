#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: recipes.py must chain dual-mode ImportErrors for recipe_files (deferred-issues section 3).

PR #408 chains curated_recipes and local_recipes helpers but left the module-level
``extract_code_terms`` fallback swallowing both failures as ``_extract_code_terms = None``,
discarding the original ImportError when the absolute import also fails.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server import recipes as recipes_mod


def test_extract_code_terms_import_is_available():
    """Happy path: recipe_files resolves and search can use code-term extraction."""
    assert recipes_mod._extract_code_terms is not None


def test_recipe_files_dual_import_chains_in_source():
    """Regression: do not revert to silent ``_extract_code_terms = None`` on double failure."""
    recipes_path = Path(recipes_mod.__file__)
    text = recipes_path.read_text(encoding="utf-8")
    assert "_extract_code_terms = None" not in text
    assert "raise _recipe_files_second from _recipe_files_first" in text


def test_dual_import_fallback_chains_when_both_fail():
    """Same contract as tests/test_package_import_chaining.py (deferred-issues section 3)."""

    def _chain_harness(primary, fallback):
        try:
            return primary()
        except ImportError as first_exc:
            try:
                return fallback()
            except ImportError as second_exc:
                raise second_exc from first_exc

    with pytest.raises(ImportError) as excinfo:
        _chain_harness(
            lambda: (_ for _ in ()).throw(ImportError("package-mode failed")),
            lambda: (_ for _ in ()).throw(ImportError("script-mode failed")),
        )
    assert "script-mode failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "package-mode failed" in str(excinfo.value.__cause__)
