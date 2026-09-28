#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 3 US1 server instructions (FR-027).

SERVER_INSTRUCTIONS must tell the assistant to check recipes first and how
to use PARAMS (edit values only; run with source="existing" when only PARAMS
changed). The instructions must round-trip through build_server under the
installed mcp.
"""

from flextoolsmcp.server.tool_definitions import SERVER_INSTRUCTIONS


class TestServerInstructions:
    def test_instructions_check_recipes_first(self):
        lowered = SERVER_INSTRUCTIONS.lower()
        assert "recipes" in lowered
        assert "check" in lowered

    def test_instructions_params_guidance(self):
        assert "PARAMS" in SERVER_INSTRUCTIONS
        assert 'source="existing"' in SERVER_INSTRUCTIONS

    def test_instructions_write_recipe_guidance(self):
        lowered = SERVER_INSTRUCTIONS.lower()
        assert "dry run" in lowered or "dry-run" in lowered
        assert "user_intent" in SERVER_INSTRUCTIONS

    def test_instructions_round_trip_under_installed_mcp(self):
        from flextoolsmcp.mcp_compat import build_server

        async def _list_tools():
            return []

        async def _call_tool(name, arguments):
            return []

        server = build_server(
            "test-instructions",
            _list_tools,
            _call_tool,
            instructions=SERVER_INSTRUCTIONS,
        )
        assert getattr(server, "instructions", None) == SERVER_INSTRUCTIONS
