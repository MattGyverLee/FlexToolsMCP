#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 contract bug: flextools_resolve_type success must carry the tool-response envelope."""

import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import api as api_mod


@pytest.fixture(autouse=True)
def _loaded_api_index():
    from flextoolsmcp.server import APIIndex, get_index_dir
    from flextoolsmcp.server import kernel

    kernel.initialize_kernel()
    kernel.set_api_index(APIIndex.load(get_index_dir()))
    yield


@pytest.mark.asyncio
async def test_resolve_type_hit_stamps_contract_and_status():
    out = await api_mod.handle_resolve_type({"type_name": "ILexEntry"})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "ok"
    assert payload["found"] is True
    assert payload["name"] == "ILexEntry"
    assert "import_statement" in payload


@pytest.mark.asyncio
async def test_resolve_type_miss_stamps_contract_and_status():
    out = await api_mod.handle_resolve_type({"type_name": "NotARealTypeNameZZZ"})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "ok"
    assert payload["found"] is False
    assert payload["type_name"] == "NotARealTypeNameZZZ"
    assert "suggestions" in payload
