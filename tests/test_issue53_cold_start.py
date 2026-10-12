#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for issue #53: cold-start tolerance.

End-to-end / integration coverage of the full call_tool() gate (auto-init
for READ_ONLY_SAFE tools, _session_note injection, cold run_module with/
without project_name) lives in tests/test_mcp_tools.py::TestWorkflowGates,
which already exercises the real dispatch path. This file focuses on the
smaller, directly-testable units the gate is built from:

  - SessionState.record_auto_init() / auto_init_count (the #42/#10
    regression guard: repeated auto-inits within one conversation must log
    at WARNING).
  - session.py's updated assistance hints for project_not_open /
    project_name_required (item 4 of the spec).
  - execution.py's _available_projects_payload() helper (item 2: the same
    safe enumeration flextools_list_projects uses, capped at 15 +
    total_count, never auto-selecting).

Does NOT require a live FieldWorks installation.
"""

import logging


from flextoolsmcp.server.session import SessionState, _ASSISTANCE_HINTS_BY_ERROR_CODE


# ---------------------------------------------------------------------------
# SessionState.record_auto_init()
# ---------------------------------------------------------------------------

class TestAutoInitCounter:
    def test_starts_at_zero(self):
        s = SessionState()
        assert s.auto_init_count == 0

    def test_first_auto_init_returns_one(self):
        s = SessionState()
        assert s.record_auto_init() == 1
        assert s.auto_init_count == 1

    def test_happy_path_is_exactly_one_per_conversation(self):
        """A conversation that never loses its session should only ever
        auto-init ONCE. This is the #53 acceptance test; the actual gate
        wiring (server.py) must never call record_auto_init() a second time
        once session_state.initialized is True."""
        s = SessionState()
        s.configure(api_mode="flexicon", write_enabled=False)
        count = s.record_auto_init()
        assert count == 1
        # A well-behaved caller would guard subsequent calls with
        # `if not s.initialized`, so a second call here is a caller bug --
        # but record_auto_init() itself must still count/warn honestly if
        # invoked (see WARNING test below), rather than silently no-op-ing.

    def test_second_auto_init_logs_warning(self, caplog):
        """Regression guard for #42/#10: a SECOND auto-init within the same
        session (same SessionState object) must log at WARNING -- this
        signals the underlying session-loss bug is biting, not that #53's
        cold-start tolerance is doing its job twice."""
        s = SessionState()
        with caplog.at_level(logging.INFO, logger="flextoolsmcp.server.session"):
            s.record_auto_init()
            s.record_auto_init()
        assert s.auto_init_count == 2
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("AUTO-INIT-REPEAT" in r.message for r in warning_records), (
            f"expected an AUTO-INIT-REPEAT warning on the 2nd auto-init; "
            f"got: {[r.message for r in caplog.records]}"
        )

    def test_first_auto_init_does_not_log_warning(self, caplog):
        s = SessionState()
        with caplog.at_level(logging.INFO, logger="flextoolsmcp.server.session"):
            s.record_auto_init()
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert not any("AUTO-INIT-REPEAT" in r.message for r in warning_records)


# ---------------------------------------------------------------------------
# Assistance hint text (spec item 4)
# ---------------------------------------------------------------------------

class TestAssistanceHintsPointToAvailableProjects:
    def test_project_name_required_hint_mentions_available_projects(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_name_required"]
        assert "available_projects" in hint
        assert "project_name" in hint

    def test_project_not_open_hint_mentions_available_projects(self):
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_not_open"]
        assert "available_projects" in hint
        assert "project_name" in hint

    def test_hints_no_longer_send_model_back_to_list_projects_first(self):
        """The old two-hop hint ('call list_projects, then start') is gone --
        the rejection now carries the list inline."""
        for code in ("project_name_required", "project_not_open"):
            hint = _ASSISTANCE_HINTS_BY_ERROR_CODE[code]
            # "list_projects" as a SEPARATE required first step should not
            # appear; the payload itself now carries the answer.
            assert "call flextools_list_projects" not in hint.lower()

    def test_project_not_open_hint_no_longer_mentions_run_module_parenthetical(self):
        """Issue #170: the old '(or directly to flextools_run_module)'
        parenthetical is gone -- replaced by an explicit flextools_start-first
        recommendation with the direct-call path spelled out as prose."""
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_not_open"]
        assert "(or directly to flextools_run_module)" not in hint

    def test_project_name_required_hint_now_mentions_flextools_start(self):
        """Issue #170: project_name_required now also points at
        flextools_start, not just 'pass it as project_name' in isolation."""
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_name_required"]
        assert "flextools_start" in hint

    def test_project_not_open_hint_mentions_flextools_start_before_per_op_phrasing(self):
        """Issue #170: flextools_start is the durable fix and must be named
        before the per-op ('directly to the failing call') phrasing."""
        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["project_not_open"]
        start_idx = hint.find("flextools_start")
        assert start_idx != -1
        per_op_idx = hint.find("directly to the failing call")
        assert per_op_idx != -1
        assert start_idx < per_op_idx


# ---------------------------------------------------------------------------
# execution._available_projects_payload()
# ---------------------------------------------------------------------------

class TestAvailableProjectsPayload:
    def _payload_fn(self):
        from flextoolsmcp.server.handlers.execution import _available_projects_payload
        return _available_projects_payload

    def test_uses_same_safe_enumeration_as_list_projects(self, monkeypatch):
        """Must call project_discovery.list_projects() -- the exact same safe,
        never-opens-a-project enumeration flextools_list_projects uses."""
        import flextoolsmcp.server.project_discovery as pd

        calls = []

        def _fake_list_projects(force_refresh=False):
            calls.append(force_refresh)
            return (["Alpha", "Beta", "Gamma"], "default")

        monkeypatch.setattr(pd, "list_projects", _fake_list_projects)
        payload_fn = self._payload_fn()
        result = payload_fn()
        assert calls, "helper never called project_discovery.list_projects()"
        assert result == {"available_projects": ["Alpha", "Beta", "Gamma"], "total_count": 3}

    def test_caps_at_fifteen_names_but_reports_true_total_count(self, monkeypatch):
        import flextoolsmcp.server.project_discovery as pd

        many = [f"Project{i}" for i in range(40)]
        monkeypatch.setattr(pd, "list_projects", lambda force_refresh=False: (many, "default"))
        payload_fn = self._payload_fn()
        result = payload_fn()
        assert len(result["available_projects"]) == 15
        assert result["available_projects"] == many[:15]
        assert result["total_count"] == 40

    def test_never_selects_a_project_itself(self, monkeypatch):
        """The payload is purely informational -- it must never contain a
        'selected'/'resolved' key or otherwise imply a choice was made."""
        import flextoolsmcp.server.project_discovery as pd

        monkeypatch.setattr(pd, "list_projects", lambda force_refresh=False: (["Only"], "default"))
        payload_fn = self._payload_fn()
        result = payload_fn()
        assert set(result.keys()) == {"available_projects", "total_count"}

    def test_discovery_failure_returns_empty_list_not_an_exception(self, monkeypatch):
        """Discovery is best-effort here; it must never crash the rejection
        response the caller actually needs."""
        import flextoolsmcp.server.project_discovery as pd

        def _boom(force_refresh=False):
            raise RuntimeError("registry unavailable")

        monkeypatch.setattr(pd, "list_projects", _boom)
        payload_fn = self._payload_fn()
        result = payload_fn()
        assert result == {"available_projects": [], "total_count": 0}


# ---------------------------------------------------------------------------
# Cycle-2 QC P1 (#369 Phase 5 fallout): the #53 cold-start gate must NOT be
# derived from the host-facing tool annotations. Phase 5 honestly
# reclassified flextools_parse_sandbox to readOnlyHint=False (it copies
# projects and spawns external tools), and because the gate read the
# annotation, a cold parse_sandbox call stopped auto-initializing. The
# gate now consults the explicit COLD_START_SAFE_TOOLS set in
# tool_definitions.py (the pre-Phase-5 READ_ONLY_SAFE membership);
# annotations remain UX hints for clients, not the server's policy
# boundary. End-to-end gate coverage mirrors
# tests/test_mcp_tools.py::TestWorkflowGates.
# ---------------------------------------------------------------------------

import asyncio
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _get_srv_p1():
    """Load src/flextoolsmcp/server.py directly (pattern: test_mcp_tools)."""
    import importlib.util

    server_py = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_srv_issue53_p1", str(server_py))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec from {server_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The pre-Phase-5 READ_ONLY_SAFE membership (git 722422a,
# server/tool_definitions.py): exactly the tools that were auto-init
# eligible before the Phase 5 annotation truth fixes. The cold-start set
# must equal this, no more and no less.
_PRE_PHASE5_COLD_START_SAFE = {
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
    "flextools_get_operation_logs",
    "flextools_resolve_property",
    "flextools_get_session_history",
    "flextools_health",
    "flextools_grammar_health",
    "flextools_try_word",
    "flextools_parse_status",
    "flextools_parse_log",
    "flextools_parse_diff",
    "flextools_parse_sandbox",
    "flextools_get_wrapper_dependencies",
    "flextools_resolve_type",
    "flextools_list_skeletons",
    "flextools_list_recipes",
    "flextools_find_wrappers_for_lcm",
}


class TestColdStartGateDecoupledFromAnnotations:
    def test_cold_start_safe_set_is_the_pre_phase5_membership(self):
        from flextoolsmcp.server.tool_definitions import COLD_START_SAFE_TOOLS

        assert set(COLD_START_SAFE_TOOLS) == _PRE_PHASE5_COLD_START_SAFE

    def test_parse_sandbox_annotation_stays_honest(self):
        """The fix must NOT re-flip parse_sandbox's annotation to buy back
        the gate: readOnlyHint stays False (Phase 5 truth fix stands)."""
        from flextoolsmcp.server.tool_definitions import TOOLS

        annotations = TOOLS["flextools_parse_sandbox"].annotations
        assert annotations.read_only_hint is False

    def test_cold_parse_sandbox_auto_initializes(self):
        """Cold flextools_parse_sandbox (no prior flextools_start) must
        auto-initialize a read-only session and dispatch, exactly as it
        did before Phase 5 -- NOT return session_not_initialized."""
        from flextoolsmcp.server import kernel
        from flextoolsmcp.server.handlers import admin as admin_mod
        from flextoolsmcp.server.handlers import execution as execution_mod

        srv = _get_srv_p1()
        kernel.initialize_kernel()
        kernel.set_api_index(srv.APIIndex.load(kernel.get_index_dir()))
        kernel.reset_session()
        srv.session_state = kernel.session_state
        admin_mod.session_state = kernel.session_state
        execution_mod.session_state = kernel.session_state
        assert not kernel.session_state.initialized

        result = asyncio.run(
            srv.call_tool(
                "flextools_parse_sandbox",
                {"action": "list", "project_name": "NoSuchProject"},
            )
        )
        data = json.loads(result[0].text)
        assert data.get("error_code") != "session_not_initialized", data
        assert kernel.session_state.initialized
        assert kernel.session_state.auto_init_count == 1
        assert not kernel.session_state.write_enabled
        assert "_session_note" in data
