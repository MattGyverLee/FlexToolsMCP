#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: grammar_health response_utils import needs catalog-parity third tier (deferred-issues §3).

``catalog.py`` already falls through ``response_utils`` to ``server.response_utils``.
``grammar_health.py`` stopped at bare ``response_utils``, so script-mode launches that
only expose ``server.*`` on ``sys.path`` failed to import the handler module even
though catalog handlers worked. Chaining preserves the original error when all
three paths fail.
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import grammar_health as grammar_health_mod


def test_grammar_health_module_still_imports():
    assert callable(grammar_health_mod.handle_flextools_grammar_health)


def test_response_utils_block_has_server_fallback_and_chaining():
    path = Path(grammar_health_mod.__file__)
    text = path.read_text(encoding="utf-8")
    marker = "from ...response_utils import build_response_with_context, error_response"
    start = text.index(marker)
    block = text[start - 20 : start + 900]
    assert "from server.response_utils import build_response_with_context, error_response" in block
    assert "except (ImportError, ValueError) as _response_utils_first:" in block
    assert "raise _response_utils_third from _response_utils_second" in block


def test_triple_import_fallback_chains_when_all_fail():
    def _chain_harness(primary, middle, last):
        try:
            return primary()
        except (ImportError, ValueError) as first_exc:
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
