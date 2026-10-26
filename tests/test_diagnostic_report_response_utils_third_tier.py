#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: diagnostic_report response_utils import needs catalog-parity third tier.

``catalog.py`` falls through ``response_utils`` to ``server.response_utils``.
``diagnostic_report.py`` stopped at bare ``response_utils`` in the script-mode
fallback block, so launches that only expose ``server.*`` on ``sys.path`` could
fail to import the report handler even though catalog handlers worked. Chaining
preserves the original error when all three paths fail (deferred-issues §3).
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers import diagnostic_report as report_mod


def test_diagnostic_report_module_still_imports():
    assert callable(report_mod.handle_prepare_report)


def test_response_utils_block_has_server_fallback_and_chaining():
    path = Path(report_mod.__file__)
    text = path.read_text(encoding="utf-8")
    marker = "from ...response_utils import error_response, build_response_with_context"
    start = text.index(marker)
    block = text[start : start + 750]
    assert "from server.response_utils import error_response, build_response_with_context" in block
    assert "except (ImportError, ValueError) as first_exc:" in block
    assert "raise third_exc from second_exc" in block


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
