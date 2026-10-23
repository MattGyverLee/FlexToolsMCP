#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 contract bug: flextools_find_examples success must carry the tool-response envelope."""

import asyncio
import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import api as api_mod


@pytest.mark.asyncio
async def test_find_examples_success_stamps_contract_and_status():
    out = await api_mod.handle_find_examples({"max_results": 1})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "ok"
    assert "examples" in payload
