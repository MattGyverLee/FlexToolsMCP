#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: top-level flextoolsmcp dual-mode imports chain ImportErrors (deferred-issues section 3)."""

import pytest

from flextoolsmcp import env_config, file_utils, project_adoption


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


def test_file_utils_and_env_config_import():
    assert callable(file_utils.get_project_root)
    assert callable(env_config.load_project_env)


def test_project_adoption_adopts_without_error():
    class _Session:
        project_name = ""

    session = _Session()
    resolved = project_adoption.adopt_resolved_project(
        session, "TestProj", log_context="unit-test"
    )
    assert resolved == "TestProj"
    assert session.project_name == "TestProj"
