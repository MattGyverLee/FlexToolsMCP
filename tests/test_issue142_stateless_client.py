#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #142: FLEXTOOLS_STATELESS skips API discovery gates for ephemeral clients."""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.handlers.execution import _build_validate_only_checks
from flextoolsmcp.server.kernel import (
    discovery_gate_skip_note,
    is_stateless_client_mode,
    should_skip_discovery_gates,
)
from flextoolsmcp.server.session import SessionState


class TestStatelessClientEnv:
    def test_stateless_off_by_default(self, monkeypatch):
        monkeypatch.delenv("FLEXTOOLS_STATELESS", raising=False)
        assert is_stateless_client_mode() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_stateless_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("FLEXTOOLS_STATELESS", value)
        assert is_stateless_client_mode() is True

    def test_should_skip_discovery_when_stateless(self, monkeypatch):
        monkeypatch.setenv("FLEXTOOLS_STATELESS", "1")
        assert should_skip_discovery_gates() is True
        assert discovery_gate_skip_note() == "skipped (FLEXTOOLS_STATELESS=1)"

    def test_provenance_still_wins_note(self, monkeypatch):
        monkeypatch.setenv("FLEXTOOLS_STATELESS", "1")
        assert discovery_gate_skip_note(provenance_existing=True) == "skipped (source=existing)"


class TestStatelessValidateOnlyDiscoveryGates:
    def _checks(self, *, write_enabled: bool, monkeypatch):
        monkeypatch.setenv("FLEXTOOLS_STATELESS", "1")
        code = "for e in project.LexEntry.GetAll():\n    pass\n"
        tree = ast.parse(code)
        session = SessionState()
        session.configure(api_mode="flexicon", write_enabled=write_enabled)
        return _build_validate_only_checks(
            code=code,
            code_tree=tree,
            syntax_error=None,
            api_idx=None,
            session_state_obj=session,
            write_enabled=write_enabled,
            api_mode="flexicon",
            skip_api_check=False,
            provenance_existing=False,
            skip_module_check=True,
        )[0]

    def test_write_run_skips_zero_discovery_gate(self, monkeypatch):
        checks = self._checks(write_enabled=True, monkeypatch=monkeypatch)
        by_gate = {c["gate"]: c for c in checks}
        assert by_gate["api_discovery_required"]["passed"] is True
        assert "FLEXTOOLS_STATELESS" in by_gate["api_discovery_required"]["note"]
        assert by_gate["undiscovered_entity"]["passed"] is True

    def test_read_run_skips_undiscovered_gate(self, monkeypatch):
        checks = self._checks(write_enabled=False, monkeypatch=monkeypatch)
        by_gate = {c["gate"]: c for c in checks}
        assert by_gate["undiscovered_entity"]["passed"] is True
        assert "FLEXTOOLS_STATELESS" in by_gate["undiscovered_entity"]["note"]
