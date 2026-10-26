#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 contract: flextools_get_module_template rejections use the tool envelope."""

import json
from pathlib import Path

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import admin as admin_mod
from flextoolsmcp.server.response_models import RejectionEnvelope


@pytest.mark.asyncio
async def test_get_module_template_invalid_flavor_uses_tool_contract_envelope():
    out = await admin_mod.handle_get_module_template({"flavor": "nope"})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "error"
    assert payload["error_code"] == "invalid_flavor"
    assert payload["error"]["code"] == "invalid_flavor"
    assert "nope" in payload["message"]
    assert "flexicon" in payload["available_flavors"]
    RejectionEnvelope.model_validate(payload)


@pytest.mark.asyncio
async def test_get_module_template_missing_file_uses_tool_contract_envelope(monkeypatch):
    monkeypatch.setattr(admin_mod, "_get_template", lambda _flavor: None)
    monkeypatch.setattr(
        admin_mod,
        "get_bundled_templates_dir",
        lambda: Path("/nonexistent/templates"),
    )

    out = await admin_mod.handle_get_module_template({"flavor": "flexicon"})
    payload = json.loads(out[0].text)

    assert payload["_contract"] == CONTRACT_VERSION
    assert payload["status"] == "error"
    assert payload["error_code"] == "template_not_found"
    assert payload["flavor"] == "flexicon"
    assert payload["error"]["code"] == "template_not_found"
    RejectionEnvelope.model_validate(payload)
