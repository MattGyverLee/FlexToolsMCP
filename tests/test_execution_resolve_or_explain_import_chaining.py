#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: execution resolve_or_explain lazy imports must chain errors (deferred-issues §3).

Open PR #407 chains most dual-mode imports in ``execution.py`` but leaves both
``resolve_or_explain`` fallbacks (path-not-found helper and ``handle_run_module``)
on bare ``except (ImportError, ValueError)`` blocks that discard the original
error when the script-mode import also fails.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod


def test_execution_module_still_imports():
    assert callable(execution_mod.handle_run_module)


def test_resolve_or_explain_imports_chain_in_source():
    path = Path(execution_mod.__file__)
    text = path.read_text(encoding="utf-8")
    marker = "from ..project_discovery import resolve_or_explain"
    count = 0
    start = 0
    while True:
        idx = text.find(marker, start)
        if idx == -1:
            break
        block = text[idx : idx + 350]
        assert "except (ImportError, ValueError) as first_exc:" in block
        assert "raise second_exc from first_exc" in block
        count += 1
        start = idx + len(marker)
    assert count == 2


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
