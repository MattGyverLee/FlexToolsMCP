#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: parse handler response_utils imports need catalog-parity third tier.

``catalog.py`` falls through ``response_utils`` to ``server.response_utils``.
Parse handler modules stopped at bare ``response_utils`` in the script-mode
fallback block, so launches that only expose ``server.*`` on ``sys.path`` could
fail to import parse tools even though catalog handlers worked. Chaining
preserves the original error when all three paths fail (deferred-issues section 3).
"""

from pathlib import Path

import pytest

from flextoolsmcp.server.handlers.parse import (
    common,
    filing,
    run_log,
    runs,
    sandbox,
    sandbox_checks,
    summary,
    try_word,
)

PARSE_MODULES = (
    common,
    filing,
    run_log,
    runs,
    sandbox,
    sandbox_checks,
    summary,
    try_word,
)


@pytest.mark.parametrize("mod", PARSE_MODULES, ids=lambda m: m.__name__.split(".")[-1])
def test_parse_handler_module_imports(mod):
    assert mod.__file__


def _response_utils_block(mod) -> str:
    path = Path(mod.__file__)
    text = path.read_text(encoding="utf-8")
    marker = "from ....response_utils import"
    start = text.index(marker)
    return text[start : start + 850]


@pytest.mark.parametrize("mod", PARSE_MODULES, ids=lambda m: m.__name__.split(".")[-1])
def test_response_utils_block_has_server_fallback_and_chaining(mod):
    block = _response_utils_block(mod)
    assert "from server.response_utils import" in block
    assert "except (ImportError, ValueError) as first_exc:" in block
    assert "raise third_exc from second_exc" in block
