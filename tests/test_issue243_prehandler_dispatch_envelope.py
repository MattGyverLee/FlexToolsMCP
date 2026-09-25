#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #243: pre-handler dispatch failures must return the tool-response envelope."""

import asyncio
import importlib.util
import json
from pathlib import Path
from unittest import TestCase, main

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.dispatch import TOOL_LIST_CATEGORIES


def _load_server_module():
    server_py = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_server_module_issue243", str(server_py))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestIssue243PrehandlerDispatchEnvelope(TestCase):
    def _parse(self, result):
        self.assertTrue(result)
        return json.loads(result[0].text)

    def test_session_not_initialized_returns_structured_envelope(self):
        srv = _load_server_module()
        old_initialized = srv.session_state.initialized
        srv.session_state.initialized = False
        try:
            # flextools_prepare_report is not session-independent and not read-only-safe.
            result = asyncio.run(srv.call_tool("flextools_prepare_report", {}))
        finally:
            srv.session_state.initialized = old_initialized

        parsed = self._parse(result)
        self.assertEqual(parsed.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(parsed.get("status"), "error")
        self.assertEqual(parsed.get("error_code"), "session_not_initialized")
        self.assertIn("flextools_start", parsed.get("message", ""))
        self.assertEqual(parsed.get("tool"), "flextools_prepare_report")
        nested = parsed.get("error")
        self.assertIsInstance(nested, dict)
        self.assertEqual(nested.get("code"), "session_not_initialized")

    def test_unknown_tool_returns_structured_envelope(self):
        srv = _load_server_module()
        old_initialized = srv.session_state.initialized
        srv.session_state.initialized = True
        try:
            result = asyncio.run(srv.call_tool("flextools_nonexistent_tool", {}))
        finally:
            srv.session_state.initialized = old_initialized

        parsed = self._parse(result)
        self.assertEqual(parsed.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(parsed.get("status"), "error")
        self.assertEqual(parsed.get("error_code"), "unknown_tool")
        self.assertIn("flextools_nonexistent_tool", parsed.get("message", ""))
        self.assertEqual(parsed.get("tool"), "flextools_nonexistent_tool")

    def test_invalid_input_returns_structured_envelope(self):
        srv = _load_server_module()
        old_initialized = srv.session_state.initialized
        srv.session_state.initialized = True
        try:
            # object_type is required; omit it to force Pydantic validation failure.
            result = asyncio.run(srv.call_tool("flextools_get_object_api", {}))
        finally:
            srv.session_state.initialized = old_initialized

        parsed = self._parse(result)
        self.assertEqual(parsed.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(parsed.get("status"), "error")
        self.assertEqual(parsed.get("error_code"), "invalid_input")
        self.assertEqual(parsed.get("tool"), "flextools_get_object_api")
        self.assertIn("received_arguments", parsed)


if __name__ == "__main__":
    main()
