#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: execution lazy dual-mode imports must chain errors (deferred-issues §3).

Open PR #407 chains module-level handler imports and sibling PRs #448/#452/#453/#454
cover ``_recipes_module``, ``response_utils``, ``config``, and ``resolve_or_explain``.
This batch covers the remaining lazy ``(ImportError, ValueError)`` / ``ImportError``
fallbacks in diagnosis, validate-only, and write-gate paths.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod


def test_execution_module_still_imports():
    assert callable(execution_mod.handle_run_module)


_LAZY_IMPORT_MARKERS = (
    "from ..parse import own_worker as _own_worker",
    "from ..project_access import probe_project_access",
    "from ..project_discovery import list_projects, get_last_directory",
    "from ..project_discovery import get_project_fwdata_path",
    "from ..project_discovery import find_lock_file",
    "from ..project_discovery import normalize_project_name, project_not_found_fields",
    "from ..project_discovery import available_projects_payload",
    "from ...project_adoption import adopt_resolved_project",
)


@pytest.mark.parametrize("marker", _LAZY_IMPORT_MARKERS)
def test_lazy_import_markers_chain_in_source(marker: str):
    text = Path(execution_mod.__file__).read_text(encoding="utf-8")
    start = 0
    found = 0
    while True:
        idx = text.find(marker, start)
        if idx == -1:
            break
        block = text[idx : idx + 420]
        assert "first_exc" in block
        assert "raise second_exc from first_exc" in block
        found += 1
        start = idx + len(marker)
    assert found >= 1


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
