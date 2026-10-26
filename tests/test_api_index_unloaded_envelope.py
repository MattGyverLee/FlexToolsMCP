#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: API discovery tools must not crash or lie when the API index is unloaded."""

import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import api as api_mod
from flextoolsmcp.server.handlers import catalog as catalog_mod
from flextoolsmcp.server.response_models import RejectionEnvelope

_HANDLERS = (
    ("flextools_get_object_api", api_mod.handle_get_object_api, {"object_type": "ILexEntry"}),
    ("flextools_search_by_capability", api_mod.handle_search_by_capability, {"query": "add gloss"}),
    ("flextools_find_examples", api_mod.handle_find_examples, {"max_results": 1}),
    ("flextools_resolve_property", api_mod.handle_resolve_property, {"property_name": "HeadWord"}),
    ("flextools_resolve_type", api_mod.handle_resolve_type, {"type_name": "ILexEntry"}),
    ("flextools_list_categories", catalog_mod.handle_list_categories, {}),
    ("flextools_list_entities_in_category", catalog_mod.handle_list_entities_in_category, {"category": "lexicon"}),
)


@pytest.fixture()
def unloaded_index(monkeypatch):
    monkeypatch.setattr(api_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(catalog_mod, "get_api_index", lambda: None)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,handler,args", _HANDLERS)
async def test_api_discovery_tools_use_envelope_when_index_unloaded(
    unloaded_index, tool_name, handler, args
):
    out = await handler(args)
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "error"
    assert payload["error_code"] == "server_state_error"
    assert payload["server_state"] == "api_index_not_loaded"
    assert payload["component"] == "api_index"
    assert payload.get("tool") == tool_name
    assert payload["error"]["code"] == "server_state_error"
    RejectionEnvelope.model_validate(payload)
