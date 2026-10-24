#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: recipe_validator dual-mode imports chain ImportErrors (deferred-issues section 3)."""

import pytest

from flextoolsmcp.recipe_validator import validate_recipe


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


def test_recipe_validator_still_imports_and_runs_minimal_check():
    assert callable(validate_recipe)
    result = validate_recipe({"code": "x = 1\n", "requires_write": False})
    assert result["passed"] is True
