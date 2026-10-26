#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #54 follow-up: flextools_get_session_history must use the tool-response envelope."""

import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel as kernel_mod
from flextoolsmcp.server.handlers import admin as admin_mod


def _parse(out):
    return json.loads(out[0].text)


@pytest.fixture(autouse=True)
def _readonly_session():
    kernel_mod.session_state.configure(session_id="test-session-history-envelope", api_mode="flexicon")
    yield


@pytest.mark.asyncio
async def test_get_session_history_success_carries_tool_response_envelope():
    data = _parse(await admin_mod.handle_get_session_history({}))
    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "ok"
    assert "history" in data
