#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #89: unhandled handler exceptions must return the tool-response envelope."""

import asyncio
import importlib.util
import json
from pathlib import Path
from unittest import TestCase, main

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.dispatch import TOOL_LIST_CATEGORIES


def _load_server_module():
    server_py = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_server_module_issue89", str(server_py))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestIssue89HandlerDispatchEnvelope(TestCase):
    def test_unhandled_handler_exception_returns_structured_envelope(self):
        srv = _load_server_module()
        orig_get_handler = srv.get_tool_handler

        async def exploding_handler(_args):
            raise RuntimeError("simulated handler defect")

        def patched_get_handler(tool_name):
            route = orig_get_handler(tool_name)
            if tool_name == TOOL_LIST_CATEGORIES and route is not None:
                _handler, input_model = route
                return exploding_handler, input_model
            return route

        srv.get_tool_handler = patched_get_handler
        try:
            result = asyncio.run(srv.call_tool(TOOL_LIST_CATEGORIES, {}))
        finally:
            srv.get_tool_handler = orig_get_handler

        self.assertTrue(result)
        parsed = json.loads(result[0].text)
        self.assertEqual(parsed.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(parsed.get("status"), "error")
        self.assertEqual(parsed.get("error_code"), "internal_error")
        self.assertIn("simulated handler defect", parsed.get("message", ""))
        self.assertEqual(parsed.get("error_type"), "RuntimeError")
        self.assertEqual(parsed.get("tool"), TOOL_LIST_CATEGORIES)
        self.assertIn("traceback", parsed)
        nested = parsed.get("error")
        self.assertIsInstance(nested, dict)
        self.assertEqual(nested.get("code"), "internal_error")


if __name__ == "__main__":
    main()
