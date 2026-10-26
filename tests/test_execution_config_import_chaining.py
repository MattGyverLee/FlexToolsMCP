#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: execution module-level config import must chain errors (deferred-issues §3).

Open PR #407 chains most dual-mode imports in ``execution.py`` but leaves the
issue #46 ``config`` fallback on a bare ``except (ImportError, ValueError)`` that
discards the original error when the script-mode import also fails.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod


def test_execution_module_still_imports():
    assert callable(execution_mod.handle_run_module)
    assert execution_mod.AUTO_FIX_ENABLED_KEY


def test_config_import_chains_in_source():
    path = Path(execution_mod.__file__)
    text = path.read_text(encoding="utf-8")
    marker = "# Issue #46: auto-fix config"
    start = text.index(marker)
    block = text[start : start + 450]
    assert "except (ImportError, ValueError) as first_exc:" in block
    assert "raise second_exc from first_exc" in block


def test_dual_import_fallback_chains_when_both_fail():
    def _chain_harness(primary, fallback):
        try:
            return primary()
        except (ImportError, ValueError) as first_exc:
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
