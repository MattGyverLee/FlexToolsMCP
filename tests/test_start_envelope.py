#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: flextools_start success path uses the tool-response envelope (issue #54)."""

import asyncio
import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel
from flextoolsmcp.server.handlers import admin as admin_mod


def _parse(response):
    return json.loads(response[0].text)


@pytest.fixture(autouse=True)
def _clean_session():
    kernel.reset_session()
    yield
    kernel.reset_session()


@pytest.fixture(autouse=True)
def _ensure_ops_logger():
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()


def test_start_success_stamps_contract_and_preserves_session_status():
    data = _parse(asyncio.run(admin_mod.handle_start({"api_mode": "flexicon"})))

    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "session_initialized"
    assert "session" in data
    assert data["session"]["initialized"] is True
