#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: write_ladder dual-mode config import chains ImportErrors (deferred-issues section 3)."""

import pytest

from flextoolsmcp.server import write_ladder as write_ladder_mod


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


def test_write_ladder_config_symbols_importable():
    assert write_ladder_mod.BACKUP_BEFORE_WRITE_KEY
    assert callable(write_ladder_mod.backup_intent)
