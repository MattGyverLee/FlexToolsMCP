#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Tool-Level Tests for FlexToolsMCP.

Tests the MCP tool dispatch layer: tool registration, naming conventions,
annotations, workflow gates, response structure, and error handling.

These tests exercise list_tools() and call_tool() directly without requiring
the full API indexes -- they mock the index to keep tests self-contained.
"""

import json
import asyncio
from functools import lru_cache
from pathlib import Path
from unittest import TestCase, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_async(coro):
    """Run an async coroutine synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@lru_cache(maxsize=1)
def _get_srv():
    """Load and cache server.py module (avoiding reloading on every call).

    The decorated list_tools() and call_tool() functions live in server.py,
    not in server/__init__.py. We load it directly via importlib.
    """
    import importlib.util
    server_py = Path(__file__).parent.parent / "src" / "server.py"
    spec = importlib.util.spec_from_file_location("_server_module", str(server_py))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec from {server_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_tools():
    """Call list_tools() to get the registered tool list."""
    srv = _get_srv()
    return run_async(srv.list_tools())


def call_tool(name, arguments=None):
    """Call a tool by name and return the result."""
    srv = _get_srv()
    return run_async(srv.call_tool(name, arguments or {}))


# ---------------------------------------------------------------------------
# Tool Registration Tests
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = [
    "flextools_start",
    "flextools_get_object_api",
    "flextools_search_by_capability",
    "flextools_get_navigation_path",
    "flextools_find_examples",
    "flextools_list_categories",
    "flextools_list_entities_in_category",
    "flextools_get_module_template",
    "flextools_start_module",
    "flextools_run_module",
    "flextools_get_operation_logs",
    "flextools_resolve_property",
    "flextools_manage_config",
    "flextools_get_session_history",
    "flextools_undo_last_operation",
]
# Dynamically derive count instead of magic number (eliminates out-of-sync issues)
EXPECTED_TOOL_COUNT = len(EXPECTED_TOOL_NAMES)

# Tools that should be marked readOnlyHint=True
READ_ONLY_TOOLS = [
    "flextools_start",
    "flextools_get_object_api",
    "flextools_search_by_capability",
    "flextools_get_navigation_path",
    "flextools_find_examples",
    "flextools_list_categories",
    "flextools_list_entities_in_category",
    "flextools_get_module_template",
    "flextools_start_module",
    "flextools_resolve_property",
    "flextools_get_operation_logs",
    "flextools_get_session_history",
]

# Tools that should be marked destructiveHint=True
DESTRUCTIVE_TOOLS = [
    "flextools_run_module",
    "flextools_run_operation",
    "flextools_undo_last_operation",
]


# ---------------------------------------------------------------------------
# Base Classes for Test Consolidation
# ---------------------------------------------------------------------------

class ToolsTestBase(TestCase):
    """Base class that consolidates common tool setup patterns."""

    @classmethod
    def setUpClass(cls):
        """Load tools and build lookup tables for all subclasses."""
        cls.tools = get_tools()
        cls.tool_names = [t.name for t in cls.tools]
        cls.tools_by_name = {t.name: t for t in cls.tools}


class TestToolRegistration(ToolsTestBase):
    """Test that all tools are registered correctly."""

    def test_tool_count(self):
        """All 16 tools should be registered."""
        self.assertEqual(len(self.tools), EXPECTED_TOOL_COUNT,
                         f"Expected {EXPECTED_TOOL_COUNT} tools, got {len(self.tools)}: "
                         f"{self.tool_names}")

    def test_all_expected_tools_present(self):
        """Every expected tool name should be in the registry."""
        for name in EXPECTED_TOOL_NAMES:
            self.assertIn(name, self.tool_names,
                          f"Missing tool: {name}")

    def test_all_tools_have_flextools_prefix(self):
        """Every tool name should start with 'flextools_'."""
        for name in self.tool_names:
            self.assertTrue(name.startswith("flextools_"),
                            f"Tool '{name}' missing 'flextools_' prefix")

    def test_no_duplicate_tool_names(self):
        """Tool names must be unique."""
        self.assertEqual(len(self.tool_names), len(set(self.tool_names)),
                         "Duplicate tool names found")

    def test_all_tools_have_description(self):
        """Every tool should have a non-empty description."""
        for tool in self.tools:
            self.assertTrue(tool.description and len(tool.description.strip()) > 0,
                            f"Tool '{tool.name}' has empty description")

    def test_all_tools_have_input_schema(self):
        """Every tool should have an inputSchema."""
        for tool in self.tools:
            self.assertIsNotNone(tool.inputSchema,
                                 f"Tool '{tool.name}' has no inputSchema")
            self.assertEqual(tool.inputSchema.get("type"), "object",
                             f"Tool '{tool.name}' inputSchema type should be 'object'")


# ---------------------------------------------------------------------------
# Tool Annotation Tests
# ---------------------------------------------------------------------------

class TestToolAnnotations(ToolsTestBase):
    """Test that all tools have correct MCP annotations."""

    def test_all_tools_have_annotations(self):
        """Every tool should have an annotations dict."""
        for tool in self.tools:
            self.assertIsNotNone(tool.annotations,
                                 f"Tool '{tool.name}' missing annotations")

    def test_annotations_have_required_keys(self):
        """Every annotation dict should have all 4 standard keys."""
        required_keys = {"readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint"}
        for tool in self.tools:
            if tool.annotations is None:
                continue
            # annotations may be a dict or object with attributes
            ann = tool.annotations
            if hasattr(ann, '__dict__'):
                ann_keys = set(vars(ann).keys())
            else:
                ann_keys = set(ann.keys())
            for key in required_keys:
                self.assertIn(key, ann_keys,
                              f"Tool '{tool.name}' annotations missing '{key}'")

    def test_readonly_tools_annotated_correctly(self):
        """Read-only tools should have readOnlyHint=True."""
        for name in READ_ONLY_TOOLS:
            tool = self.tools_by_name.get(name)
            if tool is None:
                continue
            ann = tool.annotations
            readonly = ann.get("readOnlyHint") if isinstance(ann, dict) else getattr(ann, "readOnlyHint", None)
            self.assertTrue(readonly,
                            f"Tool '{name}' should be readOnlyHint=True")

    def test_destructive_tools_annotated_correctly(self):
        """Destructive tools should have destructiveHint=True and readOnlyHint=False."""
        for name in DESTRUCTIVE_TOOLS:
            tool = self.tools_by_name.get(name)
            if tool is None:
                continue
            ann = tool.annotations
            if isinstance(ann, dict):
                destructive = ann.get("destructiveHint")
                readonly = ann.get("readOnlyHint")
            else:
                destructive = getattr(ann, "destructiveHint", None)
                readonly = getattr(ann, "readOnlyHint", None)
            self.assertTrue(destructive,
                            f"Tool '{name}' should be destructiveHint=True")
            self.assertFalse(readonly,
                             f"Tool '{name}' should be readOnlyHint=False")

    def test_manage_config_is_not_readonly(self):
        """manage_config has mixed read/write, so readOnlyHint should be False."""
        tool = self.tools_by_name.get("flextools_manage_config")
        if tool is None:
            return
        ann = tool.annotations
        readonly = ann.get("readOnlyHint") if isinstance(ann, dict) else getattr(ann, "readOnlyHint", None)
        self.assertFalse(readonly,
                         "flextools_manage_config should be readOnlyHint=False (mixed read/write)")


# ---------------------------------------------------------------------------
# Workflow Gate Tests
# ---------------------------------------------------------------------------

class TestWorkflowGates(TestCase):
    """Test that tools enforce the 'call flextools_start first' gate."""

    @classmethod
    def setUpClass(cls):
        """Reset session state to uninitialized before gate tests."""
        from server.session import SessionState  # type: ignore
        srv = _get_srv()
        # Reset to uninitialized state
        srv.session_state = SessionState()  # type: ignore

    def _parse_response(self, result):
        """Parse TextContent list into JSON."""
        self.assertTrue(len(result) > 0, "Empty response")
        text = result[0].text
        return json.loads(text)

    def test_search_before_start_returns_error(self):
        """Calling flextools_search_by_capability before start should return init error."""
        result = call_tool("flextools_search_by_capability", {"query": "add gloss"})
        data = self._parse_response(result)
        self.assertIn("error", data)
        self.assertIn("not initialized", data.get("error", "").lower())

    def test_get_object_api_before_start_returns_error(self):
        """Calling flextools_get_object_api before start should return init error."""
        result = call_tool("flextools_get_object_api", {"object_type": "ILexEntry"})
        data = self._parse_response(result)
        self.assertIn("error", data)

    def test_run_operation_before_start_returns_error(self):
        """Calling flextools_run_operation before start should return init error."""
        result = call_tool("flextools_run_operation", {"operations": "print('hello')"})
        data = self._parse_response(result)
        self.assertIn("error", data)

    def test_list_categories_before_start_returns_error(self):
        """Calling flextools_list_categories before start should return init error."""
        result = call_tool("flextools_list_categories", {})
        data = self._parse_response(result)
        self.assertIn("error", data)


# ---------------------------------------------------------------------------
# Error Handling Tests
# ---------------------------------------------------------------------------

class TestErrorHandling(TestCase):
    """Test that tools return structured errors, not tracebacks."""

    def test_unknown_tool_returns_error(self):
        """Calling a nonexistent tool should return an error message."""
        # Must initialize session first so we get past the gate
        from server.session import SessionState  # type: ignore
        srv = _get_srv()
        old_state = srv.session_state
        srv.session_state = SessionState()  # type: ignore
        srv.session_state.initialized = True

        try:
            result = call_tool("flextools_nonexistent_tool", {})
            self.assertTrue(len(result) > 0)
            text = result[0].text
            self.assertIn("Unknown tool", text)
        finally:
            srv.session_state = old_state  # type: ignore

    def test_unknown_tool_without_prefix(self):
        """Old unprefixed tool names should no longer work."""
        # Reset session to initialized so we get past the gate
        from server.session import SessionState  # type: ignore
        srv = _get_srv()
        old_state = srv.session_state
        srv.session_state = SessionState()  # type: ignore
        srv.session_state.initialized = True

        try:
            result = call_tool("start", {})
            text = result[0].text
            self.assertIn("Unknown tool", text)
        finally:
            srv.session_state = old_state  # type: ignore


# ---------------------------------------------------------------------------
# Description Cross-Reference Tests
# ---------------------------------------------------------------------------

class TestDescriptionReferences(ToolsTestBase):
    """Test that tool descriptions reference prefixed tool names, not old names."""

    # Old unprefixed names that should NOT appear in descriptions
    OLD_NAMES_TO_CHECK = [
        "search_by_capability(",
        "get_object_api(",
        "run_operation(",
        "run_module(",
        "get_navigation_path(",
        "find_examples(",
        "resolve_property(",
        "get_module_template(",
    ]

    def test_no_unprefixed_tool_references_in_descriptions(self):
        """Tool descriptions should not reference old unprefixed tool names."""
        for tool in self.tools:
            desc = tool.description
            for old_ref in self.OLD_NAMES_TO_CHECK:
                # Allow the old name if it appears after "flextools_"
                # e.g., "flextools_search_by_capability(" is fine
                # but bare "search_by_capability(" is not
                if old_ref in desc:
                    # Check it's always preceded by "flextools_"
                    idx = 0
                    while True:
                        pos = desc.find(old_ref, idx)
                        if pos == -1:
                            break
                        # Check the characters before
                        prefix_start = max(0, pos - len("flextools_"))
                        preceding = desc[prefix_start:pos]
                        self.assertTrue(
                            preceding.endswith("flextools_"),
                            f"Tool '{tool.name}' description contains unprefixed "
                            f"reference '{old_ref}' at position {pos}:\n"
                            f"  ...{desc[max(0,pos-30):pos+len(old_ref)+10]}..."
                        )
                        idx = pos + 1


if __name__ == "__main__":
    main()
