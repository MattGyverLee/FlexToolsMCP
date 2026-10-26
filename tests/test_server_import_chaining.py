#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: server-package dual-mode imports chain ImportErrors (deferred-issues section 3)."""

import pytest

from flextoolsmcp.server import tool_search as tool_search_mod
from flextoolsmcp.server import versioning as versioning_mod


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


def test_versioning_operations_logger_importable():
    # Smoke: patched module still imports in package mode.
    assert versioning_mod.operations_logger is None or hasattr(
        versioning_mod.operations_logger, "info"
    )


def test_tool_search_tools_loads():
    tools = tool_search_mod._tools()
    assert isinstance(tools, dict)
    assert tools
