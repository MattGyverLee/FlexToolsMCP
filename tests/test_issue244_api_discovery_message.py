#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #244: clarify api_discovery_required when read-only auto-discovery exists."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.session import SessionState
from flextoolsmcp.server.handlers.execution import _api_discovery_required_copy


class TestIssue244ApiDiscoveryMessage(unittest.TestCase):
    def test_zero_discovery_unchanged_message(self):
        session = SessionState()
        copy = _api_discovery_required_copy(session, has_inline_discovery=False)
        self.assertIn("No APIs have been discovered yet", copy["message"])
        self.assertEqual(copy["auto_discovered_pending_validation"], [])
        self.assertIn("No APIs discovered yet", copy["log_summary"])

    def test_auto_discovered_named_in_message_and_payload(self):
        session = SessionState()
        session.record_auto_discovered_api("LexEntryOperations")
        session.record_auto_discovered_api("LexSenseOperations")
        copy = _api_discovery_required_copy(session, has_inline_discovery=False)
        self.assertIn("validated yet for a WRITE run", copy["message"])
        self.assertIn("LexEntryOperations", copy["message"])
        self.assertIn("LexSenseOperations", copy["message"])
        self.assertNotIn("No APIs have been discovered yet", copy["message"])
        self.assertEqual(
            copy["auto_discovered_pending_validation"],
            ["LexEntryOperations", "LexSenseOperations"],
        )
        self.assertIn("auto-discovered but not validated", copy["log_summary"])
        self.assertIn("LexEntryOperations", copy["hint"])

    def test_inline_discovery_still_mentions_auto_grants(self):
        session = SessionState()
        session.record_auto_discovered_api("POSOperations")
        copy = _api_discovery_required_copy(session, has_inline_discovery=True)
        self.assertIn("_inline_discovery", copy["message"])
        self.assertIn("POSOperations", copy["message"])
        self.assertIn("POSOperations", copy["hint"])


if __name__ == "__main__":
    unittest.main()
