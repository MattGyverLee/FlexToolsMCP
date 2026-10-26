#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #54: flextools_list_recipes success payloads carry the tool-response envelope."""

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION

try:
    from tests.test_list_recipes import (  # noqa: F401
        _call_list_recipes,
        _parse,
        _seeded,
        recipe_env,
    )
except ImportError:
    from test_list_recipes import (  # noqa: F401
        _call_list_recipes,
        _parse,
        _seeded,
        recipe_env,
    )

pytestmark = pytest.mark.usefixtures("recipe_env")


def test_list_recipes_list_success_carries_contract_envelope(monkeypatch):
    _seeded(monkeypatch)
    data = _parse(_call_list_recipes({"source": "all", "limit": 10}))
    assert data["status"] == "ok"
    assert data["_contract"] == CONTRACT_VERSION
    assert data["recipes_count"] >= 1


def test_list_recipes_by_id_success_carries_contract_envelope(monkeypatch):
    _seeded(monkeypatch)
    data = _parse(_call_list_recipes({"recipe_id": "alpha-read"}))
    assert data["status"] == "ok"
    assert data["_contract"] == CONTRACT_VERSION
    assert data["recipe"]["id"] == "alpha-read"
