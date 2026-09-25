#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #87: find_wrappers_for_lcm must not downgrade Entity.Property to entity."""

import asyncio
import unittest
from unittest.mock import patch

from flextoolsmcp.server.handlers.equivalence import handle_find_wrappers_for_lcm


_FAKE_REVERSE = {
    "by_liblcm_entity": {
        "IMoStemMsa": {
            "flexlibs_2": {"class": "MSAOperations", "methods": ["GetClassName"]},
            "flexlibs_stable": None,
        },
    },
    "properties": {},
    "methods": {},
    "factories": {},
    "repositories": {},
}


class TestIssue87DottedLcmProperty(unittest.TestCase):
    def _run(self, **kwargs):
        with patch(
            "flextoolsmcp.server.handlers.equivalence._get_reverse_mapping",
            return_value=_FAKE_REVERSE,
        ):
            payload = asyncio.run(handle_find_wrappers_for_lcm(kwargs))
        import json
        return json.loads(payload[0].text)

    def test_dotted_property_not_downgraded_to_empty_entity(self):
        """IMoStemMsa.MsFeaturesOA must not return found+entity with 0 methods."""
        result = self._run(lcm_name="IMoStemMsa.MsFeaturesOA", kind="auto")
        self.assertFalse(result["found"])
        self.assertEqual(result["kind"], "property")
        self.assertIn("MsFeaturesOA", result["message"])
        self.assertNotEqual(result.get("kind"), "entity")

    def test_bare_entity_still_resolves(self):
        result = self._run(lcm_name="IMoStemMsa", kind="auto")
        self.assertTrue(result["found"])
        self.assertEqual(result["kind"], "entity")
        self.assertIn("MSAOperations", result["summary"])


if __name__ == "__main__":
    unittest.main()
