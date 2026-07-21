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
