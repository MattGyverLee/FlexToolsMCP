#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #54 follow-up: catalog list tools must use the tool-response envelope."""

import asyncio
import json

import pytest

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel as kernel_mod
from flextoolsmcp.server.handlers import catalog as catalog_mod


def _parse(out):
    return json.loads(out[0].text)


@pytest.fixture(autouse=True)
def _readonly_session():
    kernel_mod.session_state.configure(session_id="test-catalog-envelope", api_mode="flexicon")
    # Success paths require a loaded API index (merged #384 returns the
    # api_index_not_loaded error envelope otherwise), and full-suite test
    # order must not decide whether the index happens to be loaded already.
    try:
        from flextoolsmcp.server import APIIndex, get_index_dir

        kernel_mod.set_api_index(APIIndex.load(get_index_dir()))
    except Exception:
        pass
    yield


@pytest.mark.parametrize(
    "handler, args",
    [
        (catalog_mod.handle_list_categories, {}),
        (catalog_mod.handle_list_entities_in_category, {"category": "lexicon"}),
        (catalog_mod.handle_list_projects, {}),
    ],
)
def test_catalog_list_success_paths_carry_tool_response_envelope(handler, args):
    data = _parse(asyncio.run(handler(args)))
    assert data["_contract"] == CONTRACT_VERSION
    assert data["status"] == "ok"
