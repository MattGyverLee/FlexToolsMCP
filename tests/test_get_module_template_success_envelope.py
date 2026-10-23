#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""flextools_get_module_template success path must emit the tool-response envelope."""

import asyncio
import json
from unittest import TestCase, main

from flextoolsmcp.response_utils import CONTRACT_VERSION


class TestGetModuleTemplateSuccessEnvelope(TestCase):
    def test_success_has_contract_and_ok_status(self):
        from flextoolsmcp.server.handlers.admin import handle_get_module_template

        async def _run():
            return await handle_get_module_template({"flavor": "flexicon"})

        result = asyncio.run(_run())
        self.assertTrue(result)
        data = json.loads(result[0].text)
        self.assertEqual(data.get("_contract"), CONTRACT_VERSION)
        self.assertEqual(data.get("status"), "ok")
        self.assertTrue((data.get("template") or "").strip())


if __name__ == "__main__":
    main()
