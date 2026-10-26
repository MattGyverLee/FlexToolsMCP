#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: local_recipes dual-mode lazy imports must chain errors (deferred-issues §3).

Open PR #409 chains many server-package fallbacks but ``local_recipes.py`` keeps
five inline package/script probes (validators, kernel, recipe_files) on bare
``except ImportError`` blocks that discard the original error when the fallback
import also fails.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server import local_recipes as local_recipes_mod


def test_local_recipes_module_still_imports():
    assert callable(local_recipes_mod._accessor_map)


def test_local_recipes_dual_import_blocks_chain_in_source():
    path = Path(local_recipes_mod.__file__)
    text = path.read_text(encoding="utf-8")
    assert text.count("raise second_exc from first_exc") >= 5


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
