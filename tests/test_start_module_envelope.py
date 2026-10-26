#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: flextools_start_module success paths use the tool-response envelope (issue #54)."""

import asyncio
import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel
from flextoolsmcp.server.handlers import execution as execution_mod


def _parse(response):
    item = response[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


@pytest.fixture(autouse=True)
def _clean_session():
    kernel.reset_session()
    yield
    kernel.reset_session()


@pytest.fixture(autouse=True)
def _ensure_ops_logger():
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()


def test_start_module_needs_input_stamps_contract():
    data = _parse(asyncio.run(execution_mod.handle_start_module({})))

    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "needs_input"
    assert "questions" in data


def test_start_module_complete_stamps_contract():
    data = _parse(
        asyncio.run(
            execution_mod.handle_start_module(
                {
                    "module_name": "Test Module",
                    "synopsis": "Does something useful",
                    "api_target": "flexicon",
                    "modifies_db": False,
                    "domain": "lexicon",
                }
            )
        )
    )

    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "complete"
    assert "template" in data
