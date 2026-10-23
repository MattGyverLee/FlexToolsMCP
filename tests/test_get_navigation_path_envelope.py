#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2: flextools_get_navigation_path must emit the tool-response envelope (#54, #369 batch 2)."""

import asyncio
import json
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from flextoolsmcp.response_utils import CONTRACT_VERSION


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestGetNavigationPathEnvelope(TestCase):
    def _parse(self, result):
        self.assertTrue(result)
        return json.loads(result[0].text)

    def test_success_carries_contract_and_status_ok(self):
        from server.handlers.discovery import handle_get_navigation_path

        fake_index = MagicMock()
        fake_index.navigation_graph = {
            "common_paths": {},
            "graph": {"ILexEntry": [["ILexSense", "SensesOS", "owns"]]},
            "entities": {},
        }
        with patch("server.handlers.discovery.get_api_index", return_value=fake_index):
            parsed = self._parse(
                run_async(
                    handle_get_navigation_path(
                        {"from_object": "ILexEntry", "to_object": "ILexSense"}
                    )
                )
            )
        self.assertEqual(parsed.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(parsed.get("status"), "ok")
        self.assertTrue(parsed.get("found"))

    def test_missing_api_index_returns_server_state_error_envelope(self):
        from server.handlers.discovery import handle_get_navigation_path

        with patch("server.handlers.discovery.get_api_index", return_value=None):
            parsed = self._parse(
                run_async(
                    handle_get_navigation_path(
                        {"from_object": "ILexEntry", "to_object": "ILexSense"}
                    )
                )
            )
        self.assertEqual(parsed.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(parsed.get("status"), "error")
        self.assertEqual(parsed.get("error_code"), "server_state_error")
        self.assertEqual(parsed.get("server_state"), "api_index_not_loaded")
        self.assertEqual(parsed.get("tool"), "flextools_get_navigation_path")

    def test_missing_navigation_graph_returns_server_state_error_envelope(self):
        from server.handlers.discovery import handle_get_navigation_path

        fake_index = MagicMock()
        fake_index.navigation_graph = None
        with patch("server.handlers.discovery.get_api_index", return_value=fake_index):
            parsed = self._parse(
                run_async(
                    handle_get_navigation_path(
                        {"from_object": "ILexEntry", "to_object": "ILexSense"}
                    )
                )
            )
        self.assertEqual(parsed.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(parsed.get("status"), "error")
        self.assertEqual(parsed.get("error_code"), "server_state_error")
        self.assertEqual(parsed.get("server_state"), "navigation_graph_not_loaded")
        self.assertEqual(parsed.get("tool"), "flextools_get_navigation_path")


if __name__ == "__main__":
    main()
