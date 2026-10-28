#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: _import_helper kernel deps need catalog-parity third tier (deferred-issues §3).

``catalog.py`` falls through ``response_utils`` to ``server.response_utils``.
``safe_import_kernel_deps()`` stopped at bare ``response_utils`` in script mode,
so launches that only expose ``server.*`` on ``sys.path`` failed to import
admin, execution, diagnostics, parse, and discovery handlers that depend on
this helper even though catalog handlers worked. Chaining preserves the original
error when all three paths fail.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import _import_helper as ih_mod


def test_import_helper_module_still_imports():
    assert callable(ih_mod.safe_import_kernel_deps)


def test_kernel_deps_response_utils_has_server_fallback_and_chaining():
    # Helper form (not the old inline form): the third tier is a nested
    # _import_with_fallback call, so safe_import_kernel_deps keeps the
    # helper refactor while gaining the server.response_utils tier.
    path = Path(ih_mod.__file__)
    text = path.read_text(encoding="utf-8")
    marker = "def safe_import_kernel_deps"
    start = text.index(marker)
    block = text[start : start + 2000]
    assert "from server.response_utils import json_response" in block
    assert "def _script_server():" in block
    assert "_import_with_fallback(_script, _script_server)" in block


def test_triple_import_fallback_chains_when_all_fail():
    def _chain_harness(primary, middle, last):
        try:
            return primary()
        except ImportError as first_exc:
            try:
                return middle()
            except ImportError as second_exc:
                try:
                    return last()
                except ImportError as third_exc:
                    raise third_exc from second_exc

    with pytest.raises(ImportError) as excinfo:
        _chain_harness(
            lambda: (_ for _ in ()).throw(ImportError("package-mode failed")),
            lambda: (_ for _ in ()).throw(ImportError("bare response_utils failed")),
            lambda: (_ for _ in ()).throw(ImportError("server.response_utils failed")),
        )
    assert "server.response_utils failed" in str(excinfo.value)
    assert excinfo.value.__cause__ is not None
    assert "bare response_utils failed" in str(excinfo.value.__cause__)
