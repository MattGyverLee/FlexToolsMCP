#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 contract: flextools_manage_config uses the tool-response envelope (issue #243)."""

import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel as kernel_mod
from flextoolsmcp.server.handlers import admin as admin_mod


def _parse(out):
    return json.loads(out[0].text)


@pytest.fixture(autouse=True)
def _initialized_session(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEXTOOLS_CONFIG_PATH", str(tmp_path / "config.json"))
    kernel_mod.session_state.configure(session_id="test-manage-config-envelope", api_mode="flexicon")
    yield


@pytest.mark.asyncio
async def test_manage_config_list_success_carries_tool_response_envelope():
    data = _parse(await admin_mod.handle_manage_config({"action": "list"}))
    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "ok"
    assert data["success"] is True
    assert "config" in data


@pytest.mark.asyncio
async def test_manage_config_missing_key_uses_error_envelope():
    data = _parse(await admin_mod.handle_manage_config({"action": "get"}))
    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "error"
    assert data["error_code"] == "invalid_input"
    assert data["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_manage_config_unknown_action_uses_error_envelope():
    data = _parse(await admin_mod.handle_manage_config({"action": "nope"}))
    assert data["status"] == "error"
    assert data["error_code"] == "invalid_input"
