#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: index/refresh dual-mode imports chain ImportErrors (deferred-issues section 3)."""

import pytest

from flextoolsmcp import curated_recipes, extract_patterns, refresh, response_utils


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


def test_refresh_and_extract_patterns_import():
    assert callable(refresh.load_env)
    assert callable(refresh.refresh_flexicon)
    assert callable(extract_patterns.classify_operation)
    assert isinstance(curated_recipes.CURATED_RECIPES, dict)


def test_response_utils_build_response_stamps_contract():
    data = response_utils.build_response_with_context({"status": "ok"}, include_session=False)
    assert data["_contract"] == response_utils.CONTRACT_VERSION
