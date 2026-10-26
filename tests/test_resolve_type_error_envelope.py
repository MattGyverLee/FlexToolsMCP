#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 contract bug: flextools_resolve_type must not emit a bare {error: ...} dict."""

import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import api as api_mod
from flextoolsmcp.server.response_models import RejectionEnvelope


@pytest.mark.asyncio
async def test_resolve_type_missing_index_uses_tool_contract_envelope(monkeypatch):
    monkeypatch.setattr(api_mod, "get_api_index", lambda: None)

    out = await api_mod.handle_resolve_type({"type_name": "ILexEntry"})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "error"
    assert payload["error_code"] == "server_state_error"
    assert payload["server_state"] == "api_index_not_loaded"
    assert payload["error"]["code"] == "server_state_error"
    RejectionEnvelope.model_validate(payload)
