#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: dispatch dual-mode handler imports must chain ImportErrors (deferred-issues section 3)."""

import pytest

from flextoolsmcp.server import dispatch as dispatch_mod


def test_dual_import_fallback_chains_when_both_fail():
    def _primary():
        raise ImportError("package-mode failed")

    def _fallback():
        raise ImportError("script-mode failed")

    with pytest.raises(ImportError) as excinfo:
        dispatch_mod._dual_import_fallback(_primary, _fallback)

    assert "script-mode failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "package-mode failed" in str(excinfo.value.__cause__)


def test_dual_import_fallback_uses_fallback_after_import_error():
    assert dispatch_mod._dual_import_fallback(
        lambda: (_ for _ in ()).throw(ImportError("primary")),
        lambda: "ok",
    ) == "ok"


def test_import_handlers_loads_run_module():
    handlers = dispatch_mod._import_handlers()
    assert callable(handlers["handle_run_module"])
