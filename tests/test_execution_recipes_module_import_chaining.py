#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: execution._recipes_module must chain dual-mode ImportErrors (deferred-issues §3).

PR #407 chains other recipe imports in execution.py but left ``_recipes_module()``
(the retry-loop closest-recipes helper) on a bare ``except (ImportError, ValueError)``
fallback that discards the original error when ``server.recipes`` also fails.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod


def test_recipes_module_still_loads_under_package_mode():
    mod = execution_mod._recipes_module()
    assert callable(getattr(mod, "closest_recipes", None))


def test_recipes_module_dual_import_chains_in_source():
    """Regression: _recipes_module must not revert to a silent fallback."""
    path = Path(execution_mod.__file__)
    text = path.read_text(encoding="utf-8")
    start = text.index("def _recipes_module():")
    block = text[start : start + 400]
    assert "except (ImportError, ValueError) as first_exc:" in block
    assert "raise second_exc from first_exc" in block


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
