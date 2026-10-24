#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: server.py dual-mode import chains ImportErrors (deferred-issues section 3).

Open PRs #405-#409 cover handlers, dispatch, core recipes, and the server
package tree; this is the lone remaining site in the top-level server entry
module (liblcm reload -> clear_inherited_members_cache).
"""

import ast
from pathlib import Path

import pytest

SERVER_PY = Path(__file__).resolve().parents[1] / "src" / "flextoolsmcp" / "server.py"


def _dual_import_block_source():
    tree = ast.parse(SERVER_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        src = ast.get_source_segment(SERVER_PY.read_text(encoding="utf-8"), node)
        if src and "clear_inherited_members_cache" in src:
            return src
    raise AssertionError("clear_inherited_members_cache import block not found")


def test_server_py_chains_clear_inherited_members_cache_import():
    block = _dual_import_block_source()
    assert "raise _dual_second_exc from _dual_first_exc" in block


def test_dual_import_fallback_chains_when_both_fail():
    def _chain(primary, fallback):
        try:
            return primary()
        except ImportError as first_exc:
            try:
                return fallback()
            except ImportError as second_exc:
                raise second_exc from first_exc

    with pytest.raises(ImportError) as excinfo:
        _chain(
            lambda: (_ for _ in ()).throw(ImportError("package-mode failed")),
            lambda: (_ for _ in ()).throw(ImportError("script-mode failed")),
        )
    assert "script-mode failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "package-mode failed" in str(excinfo.value.__cause__)
