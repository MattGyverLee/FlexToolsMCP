#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #54 follow-up: flextools_get_operation_logs must use the tool-response envelope."""

import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel as kernel_mod
from flextoolsmcp.server.handlers import execution as execution_mod


def _parse(out):
    return json.loads(out[0].text)


@pytest.fixture(autouse=True)
def _readonly_session():
    kernel_mod.session_state.configure(session_id="test-op-logs-envelope", api_mode="flexicon")
    yield


@pytest.mark.asyncio
async def test_get_operation_logs_success_carries_tool_response_envelope():
    data = _parse(await execution_mod.handle_get_operation_logs({}))
    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "ok"
    assert "recent_logs" in data
