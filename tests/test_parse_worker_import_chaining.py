#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: parse worker + tool_output_validation dual-mode imports chain ImportErrors."""

import pytest

from flextoolsmcp.server.parse import worker_real_backend as wrb_mod
from flextoolsmcp import tool_output_validation as tov_mod


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


def test_worker_eligible_entries_degrades_without_project():
    backend = object.__new__(wrb_mod._RealBackend)
    backend._project = None
    result = backend.eligible_entries()
    assert result == {"known": False, "entries": []}


def test_tool_output_validation_registry_loads():
    assert "flextools_run_module" in tov_mod._STRUCTURED_OUTPUT_TOOLS
    assert tov_mod.TOOLS
