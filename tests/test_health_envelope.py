#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #54 follow-up: flextools_health success must use the tool-response envelope."""

import asyncio
import json

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import diagnostic_health as dh


def _parse(out):
    return json.loads(out[0].text)


def test_flextools_health_success_carries_tool_response_envelope():
    for verbose in (False, True):
        data = _parse(asyncio.run(dh.handle_flextools_health({"verbose": verbose})))
        assert data["_contract"] == CONTRACT_VERSION
        assert data["status"] == "ok"
