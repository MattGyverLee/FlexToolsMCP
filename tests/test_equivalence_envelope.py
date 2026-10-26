#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 contract: equivalence tools emit the tool-response envelope (issue #54)."""

import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import equivalence as eq_mod
from flextoolsmcp.server.response_models import RejectionEnvelope


@pytest.mark.asyncio
async def test_get_wrapper_dependencies_success_uses_contract(monkeypatch):
    bridge = {
        "by_method": {
            "LexEntryOperations.GetGloss": {"properties": ["Gloss"], "methods": []},
        },
    }
    monkeypatch.setattr(eq_mod, "get_api_index", lambda: object())
    monkeypatch.setattr(eq_mod, "_get_bridge", lambda _lib: bridge)

    out = await eq_mod.handle_get_wrapper_dependencies(
        {"method": "LexEntryOperations.GetGloss", "library": "flexicon"},
    )
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "ok"
    assert payload["found"] is True


@pytest.mark.asyncio
async def test_get_wrapper_dependencies_missing_index_uses_error_envelope(monkeypatch):
    monkeypatch.setattr(eq_mod, "get_api_index", lambda: None)

    out = await eq_mod.handle_get_wrapper_dependencies(
        {"method": "LexEntryOperations.GetGloss", "library": "flexicon"},
    )
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "error"
    assert payload["error_code"] == "server_state_error"
    assert payload["server_state"] == "api_index_not_loaded"
    assert payload["tool"] == "flextools_get_wrapper_dependencies"
    RejectionEnvelope.model_validate(payload)


@pytest.mark.asyncio
async def test_find_wrappers_for_lcm_missing_reverse_mapping_uses_error_envelope(monkeypatch):
    monkeypatch.setattr(eq_mod, "get_api_index", lambda: object())
    monkeypatch.setattr(eq_mod, "_get_reverse_mapping", lambda: None)

    out = await eq_mod.handle_find_wrappers_for_lcm({"lcm_name": "ILexEntry", "kind": "entity"})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "error"
    assert payload["error_code"] == "server_state_error"
    assert payload["server_state"] == "reverse_mapping_not_loaded"
    assert payload["tool"] == "flextools_find_wrappers_for_lcm"
    RejectionEnvelope.model_validate(payload)
