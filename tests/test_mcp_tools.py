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

# Loads src/flextoolsmcp/server.py directly via importlib (no live FLEx needed).


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
    server_py = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server.py"
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
    "flextools_list_projects",
    "flextools_get_module_template",
    "flextools_start_module",
    "flextools_run_module",
    "flextools_get_operation_logs",
    "flextools_resolve_property",
    "flextools_resolve_type",
    "flextools_manage_config",
    "flextools_get_session_history",
    "flextools_undo_last_operation",
    "flextools_get_wrapper_dependencies",
    "flextools_find_wrappers_for_lcm",
    "flextools_list_skeletons",
    "flextools_prepare_report",
    "flextools_health",
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
    "flextools_list_projects",
    "flextools_get_module_template",
    "flextools_start_module",
    "flextools_resolve_property",
    "flextools_resolve_type",
    "flextools_get_operation_logs",
    "flextools_get_session_history",
    "flextools_get_wrapper_dependencies",
    "flextools_find_wrappers_for_lcm",
    "flextools_list_skeletons",
    "flextools_health",
]

# Tools that should be marked destructiveHint=True
DESTRUCTIVE_TOOLS = [
    "flextools_run_module",
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
        """All expected tools should be registered (count derived from EXPECTED_TOOL_NAMES)."""
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

    def test_list_projects_before_start_is_allowed(self):
        """flextools_list_projects is session-independent: it must NOT be blocked
        by the init gate, since listing projects is the natural first step before
        choosing one to start() with (it scans the directory, never loads the LCM)."""
        result = call_tool("flextools_list_projects", {})
        data = self._parse_response(result)
        # Should reach the real handler (returns a projects payload), not the
        # "Session not initialized" gate error.
        self.assertNotIn("not initialized", str(data.get("error", "")).lower())
        self.assertIn("projects", data)


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


class TestModuleTemplateLoading(TestCase):
    """Regression tests for flextools_get_module_template (issue #77).

    The templates used to live at the repo root and were resolved via a
    parents[3] walk, so they were absent from the wheel and unreachable once
    the code was installed under site-packages (uvx / pip). They now ship as
    package data inside flextoolsmcp/templates and resolve package-relative.
    """

    ALL_FLAVORS = [
        "flexicon", "flexlibs_stable", "liblcm",
        "stable", "advanced", "flexlibs2",
    ]

    def test_bundled_templates_dir_exists(self):
        from flextoolsmcp.file_utils import get_bundled_templates_dir
        d = get_bundled_templates_dir()
        self.assertTrue(
            d.exists(),
            f"Bundled templates dir missing: {d}. It must live inside the "
            f"package so uvx/pip installs can find it (issue #77).",
        )

    @staticmethod
    def _fetch(flavor):
        from flextoolsmcp.server.handlers.admin import handle_get_module_template
        result = run_async(handle_get_module_template({"flavor": flavor}))
        return json.loads(result[0].text)

    def test_every_flavor_returns_a_template(self):
        for flavor in self.ALL_FLAVORS:
            payload = self._fetch(flavor)
            self.assertNotEqual(
                payload.get("error"), "template_not_found",
                f"Flavor '{flavor}' failed to load its template: {payload}",
            )
            self.assertEqual(payload.get("status"), "success", payload)
            self.assertTrue(
                payload.get("template", "").strip(),
                f"Flavor '{flavor}' returned an empty template.",
            )

    def test_unknown_flavor_reports_invalid_flavor(self):
        payload = self._fetch("nope")
        self.assertEqual(payload.get("error"), "invalid_flavor", payload)


class TestToolOutcomeLogging(TestCase):
    """Every tool call must leave an outcome trace in the operations log.

    A failing tool used to leave only the [TOOL CALL] marker (INFO) while the
    failure itself was DEBUG-only, so failures were invisible at the default
    level. call_tool now emits [TOOL OK] (INFO) / [TOOL ERROR] (WARNING) for
    every dispatch. This is what makes a template_not_found (issue #77) or any
    other tool failure show up in the logs.
    """

    def _capture(self, tool, args, initialized=False):
        import logging as _logging
        srv = _get_srv()
        # call_tool logs through the module-level `operations_logger`; make sure
        # one exists and capture what it emits.
        ops = srv.operations_logger
        if ops is None:
            ops = _logging.getLogger("flextoolsmcp.operations")
            srv.operations_logger = ops
        records = []

        class _Capture(_logging.Handler):
            def emit(self, record):
                records.append((record.levelno, record.getMessage()))

        h = _Capture()
        ops.addHandler(h)
        prev_level = ops.level
        ops.setLevel(_logging.DEBUG)
        # Optionally slip past the session gate to reach the dispatch/outcome
        # path (the gate itself already logs [BLOCKED] at WARNING).
        prev_init = srv.session_state.initialized
        if initialized:
            srv.session_state.initialized = True
        try:
            run_async(srv.call_tool(tool, args))
        finally:
            srv.session_state.initialized = prev_init
            ops.removeHandler(h)
            ops.setLevel(prev_level)
        return records

    def test_blocked_tool_leaves_a_warning_trace(self):
        import logging as _logging
        # Session-gated tool without a session: the gate itself must leave a
        # visible (WARNING) trace, not a silent return.
        records = self._capture("flextools_get_module_template", {"flavor": "flexicon"})
        self.assertTrue(
            any(lvl == _logging.WARNING and "[BLOCKED] flextools_get_module_template" in m
                for lvl, m in records),
            f"blocked tool left no WARNING trace: {[m for _, m in records]}",
        )

    def test_handler_error_emits_tool_error_at_warning(self):
        import logging as _logging
        srv = _get_srv()
        # A handler that returns an error payload (top-level "error" key) must
        # surface as [TOOL ERROR] at WARNING -- previously DEBUG-only. Swap in a
        # stub handler for one tool for the duration of the call so we don't
        # depend on any tool's live error state.
        from mcp.types import TextContent as _TC
        real_route = srv.get_tool_handler("flextools_get_module_template")
        _, input_model = real_route

        async def _boom(_args):
            return [_TC(type="text", text=json.dumps({"error": "kaboom"}))]

        records = []

        class _Capture(_logging.Handler):
            def emit(self, record):
                records.append((record.levelno, record.getMessage()))

        ops = srv.operations_logger or _logging.getLogger("flextoolsmcp.operations")
        srv.operations_logger = ops
        h = _Capture(); ops.addHandler(h); ops.setLevel(_logging.DEBUG)
        prev_init = srv.session_state.initialized
        srv.session_state.initialized = True
        orig = srv.get_tool_handler
        srv.get_tool_handler = lambda n: (_boom, input_model) if n == "flextools_get_module_template" else orig(n)
        try:
            run_async(srv.call_tool("flextools_get_module_template", {"flavor": "flexicon"}))
        finally:
            srv.get_tool_handler = orig
            srv.session_state.initialized = prev_init
            ops.removeHandler(h)

        err = [(lvl, m) for lvl, m in records if "[TOOL ERROR]" in m]
        self.assertTrue(err, f"expected a [TOOL ERROR] trace: {[m for _, m in records]}")
        self.assertEqual(err[0][0], _logging.WARNING)
        self.assertIn("kaboom", err[0][1])

    def test_handler_success_emits_tool_ok_at_info(self):
        import logging as _logging
        records = self._capture(
            "flextools_get_module_template", {"flavor": "flexicon"}, initialized=True
        )
        ok = [(lvl, m) for lvl, m in records if "[TOOL OK]" in m]
        self.assertTrue(ok, f"expected a [TOOL OK] trace: {[m for _, m in records]}")
        self.assertEqual(ok[0][0], _logging.INFO)


if __name__ == "__main__":
    main()
