#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 contract: flextools_list_skeletons failure path uses the tool envelope."""

import asyncio
import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import catalog as catalog_mod
from flextoolsmcp.server.response_models import RejectionEnvelope


@pytest.mark.asyncio
async def test_list_skeletons_load_failure_uses_tool_contract_envelope(monkeypatch):
    def _boom(limit):
        raise OSError("recipes.jsonl unreadable")

    monkeypatch.setattr(catalog_mod.local_recipes, "list_local_recipes", _boom)

    out = await catalog_mod.handle_list_skeletons({"limit": 5})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "error"
    assert payload["error_code"] == "server_state_error"
    assert payload["server_state"] == "local_recipes_unavailable"
    assert payload["component"] == "local_recipes"
    assert payload["tool"] == "flextools_list_skeletons"
    assert payload["error"]["code"] == "server_state_error"
    assert "recipes.jsonl unreadable" in payload["message"]
    RejectionEnvelope.model_validate(payload)
