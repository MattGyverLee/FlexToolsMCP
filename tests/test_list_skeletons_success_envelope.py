#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flextools_list_skeletons success path must emit the tool-response envelope."""

import asyncio
import json
from unittest import TestCase, main

from flextoolsmcp.response_utils import CONTRACT_VERSION


class TestListSkeletonsSuccessEnvelope(TestCase):
    def test_success_has_contract_and_status(self):
        from flextoolsmcp.server.handlers import catalog as catalog_mod

        async def _run():
            return await catalog_mod.handle_list_skeletons({"limit": 5})

        result = asyncio.run(_run())
        self.assertTrue(result)
        data = json.loads(result[0].text)
        self.assertEqual(data.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("skeletons", data)
        self.assertIn("count", data)


if __name__ == "__main__":
    main()
