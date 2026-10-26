#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: handle_run_module project_adoption dual-mode import must chain (deferred-issues section 3).

Open PR #449 chains ``adopt_resolved_project`` in ``grammar_health.py`` and #411
covers ``parse/common.py``. ``handle_run_module`` in ``execution.py`` still used a
bare ``except ImportError`` fallback that discards the package-mode traceback when
the script-mode import also fails.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod


def test_execution_module_still_imports():
    assert callable(getattr(execution_mod, "handle_run_module", None))


def test_handle_run_module_adopt_import_chains_in_source():
    path = Path(execution_mod.__file__)
    text = path.read_text(encoding="utf-8")
    assert "raise _adopt_second from _adopt_first" in text
    assert "log_context=\"flextools_run_module\"" in text
    # Regression: do not revert to a single bare fallback for this block.
    block_start = text.index('log_context="flextools_run_module"')
    window = text[max(0, block_start - 400) : block_start]
    assert "except ImportError as _adopt_first:" in window
    assert "except ImportError:\n            from project_adoption import adopt_resolved_project" not in window


def test_dual_import_fallback_chains_when_both_fail():
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
