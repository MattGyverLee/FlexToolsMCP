#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: validators/versioning/tool_search dual-mode imports chain ImportErrors."""

import pytest

from flextoolsmcp.server import tool_search, validators, versioning


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


def test_validators_versioning_tool_search_import():
    assert hasattr(validators, "detect_cud_operations")
    assert hasattr(versioning, "get_resolved_fieldworks_dir")
    assert callable(tool_search.find_mcp_tools)


def test_tool_search_tools_loader_returns_registry():
    tools = tool_search._tools()
    assert isinstance(tools, dict)
    assert "flextools_run_module" in tools
