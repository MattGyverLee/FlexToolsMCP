#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #42: Session-identity and discovery-state reset tests.

Tests:
- configure() stamps a new session_id each call (uuid4 hex).
- Calling configure() with a NEW session token wipes discovered_apis,
  validated_apis, and auto_discovered_apis.
- Calling configure() with the SAME session token does NOT wipe them.
- clear_discovered_apis() also clears auto_discovered_apis (#47).
- #42.2 regression: a WRITEABILITY-REJECT run emits
  "=== Operation #{seq} End ===" in the operations log.

Run with:
    python -m pytest tests/test_issue42_session_identity.py -q -m "not requires_flex"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.session import SessionState


# ---------------------------------------------------------------------------
# Session identity tests
# ---------------------------------------------------------------------------

class TestSessionIdentity:
    """configure() stamps a session_id and manages new-session resets."""

    def test_configure_stamps_session_id(self):
        s = SessionState()
        assert s.session_id == ""
        s.configure(api_mode="flexicon")
        # session_id must be non-empty after first configure(); exact format is
        # an implementation detail (may be "auto-<uuid>" or a project anchor).
        assert s.session_id, "session_id must be non-empty after configure()"

    def test_same_session_id_no_wipe(self):
        """Passing the same session_id on a second configure() preserves discovery."""
        s = SessionState()
        s.configure(session_id="aaa", api_mode="flexicon")
        s.discovered_apis.add("LexEntry.GetAll")
        s.validated_apis.add("LexEntryOperations")
        s.auto_discovered_apis.add("POSOperations")

        # Second configure() with the SAME session_id
        s.configure(session_id="aaa", api_mode="flexlibs_stable")

        assert "LexEntry.GetAll" in s.discovered_apis
        assert "LexEntryOperations" in s.validated_apis
        assert "POSOperations" in s.auto_discovered_apis

    def test_new_session_id_wipes_discovery(self):
        """A different session_id causes discovery state to be wiped."""
        s = SessionState()
        s.configure(session_id="session-A", api_mode="flexicon")
        s.discovered_apis.add("LexEntry.GetAll")
        s.validated_apis.add("LexEntryOperations")
        s.auto_discovered_apis.add("POSOperations")

        # New session
        s.configure(session_id="session-B", api_mode="flexicon")

        assert len(s.discovered_apis) == 0
        assert len(s.validated_apis) == 0
        assert len(s.auto_discovered_apis) == 0

    def test_first_configure_always_wipes(self):
        """On a fresh SessionState with empty session_id, first configure() always
        starts clean (empty -> new uuid is treated as a new session)."""
        s = SessionState()
        # Manually populate (simulating leftover from a previous test or import)
        s.discovered_apis.add("Foo.bar")
        s.validated_apis.add("FooOperations")
        s.auto_discovered_apis.add("BarOperations")

        s.configure(api_mode="flexicon")
        # A fresh uuid4 differs from "" -> new session -> wipe
        assert len(s.discovered_apis) == 0
        assert len(s.validated_apis) == 0
        assert len(s.auto_discovered_apis) == 0

    def test_clear_discovered_apis_includes_auto_discovered(self):
        """clear_discovered_apis() must also clear auto_discovered_apis."""
        s = SessionState()
        s.discovered_apis.add("Foo.bar")
        s.validated_apis.add("FooOperations")
        s.auto_discovered_apis.add("BarOperations")

        s.clear_discovered_apis()

        assert len(s.discovered_apis) == 0
        assert len(s.validated_apis) == 0
        assert len(s.auto_discovered_apis) == 0

    def test_auto_discovered_api_methods(self):
        """record_auto_discovered_api / was_auto_discovered round-trip."""
        s = SessionState()
        assert not s.was_auto_discovered("POSOperations")
        s.record_auto_discovered_api("POSOperations")
        assert s.was_auto_discovered("POSOperations")
        assert not s.was_auto_discovered("LexEntryOperations")


# ---------------------------------------------------------------------------
# #42.2: WRITEABILITY-REJECT operation-end regression
# ---------------------------------------------------------------------------

class TestWriteabilityRejectOperationEnd:
    """
    Regression: a WRITEABILITY-REJECT (unprotected_writes) preflight run MUST
    emit '=== Operation #{seq} End ===' in the operations log -- same as every
    other preflight rejection.

    We verify this by patching get_operations_logger and inspecting the
    calls made to the returned mock logger object.
    """

    def test_preflight_reject_emits_operation_end(self, tmp_path):
        """_log_preflight_reject passes '=== Operation #{N} End ===' to logger.info.

        Issue #74: pass an explicit `log_dir_fn` pointing at a pytest tmp_path
        so this test does not write a synthetic `test-op-*` row into the real
        `operations.jsonl`.
        """
        from unittest.mock import MagicMock, patch
        from flextoolsmcp.server.handlers import execution as exec_mod

        mock_logger = MagicMock()
        with patch.object(exec_mod, "get_operations_logger", return_value=mock_logger):
            exec_mod._log_preflight_reject(
                op_id="test-op-001",
                seq=7,
                duration_s=0.012,
                reason_code="unprotected_writes",
                detail="mutating_calls=['SetGloss']",
                log_dir_fn=lambda: tmp_path,
            )

        # Collect all string args passed to logger.info(...)
        info_calls = [str(c.args[0]) for c in mock_logger.info.call_args_list]
        combined = "\n".join(info_calls)
        assert "=== Operation #7 End" in combined, (
            f"Expected '=== Operation #7 End' in logger.info calls; got:\n{combined}"
        )
        assert "test-op-001" in combined

    def test_preflight_reject_emits_reject_marker(self, tmp_path):
        """_log_preflight_reject passes [REJECT] to logger.warning.

        Issue #74: pass an explicit `log_dir_fn` pointing at a pytest tmp_path
        so this test does not write a synthetic `test-op-*` row into the real
        `operations.jsonl`.
        """
        from unittest.mock import MagicMock, patch
        from flextoolsmcp.server.handlers import execution as exec_mod

        mock_logger = MagicMock()
        with patch.object(exec_mod, "get_operations_logger", return_value=mock_logger):
            exec_mod._log_preflight_reject(
                op_id="test-op-002",
                seq=3,
                duration_s=0.005,
                reason_code="unprotected_writes",
                detail="mutating_calls=['Delete']",
                log_dir_fn=lambda: tmp_path,
            )

        warning_calls = [str(c.args[0]) for c in mock_logger.warning.call_args_list]
        combined = "\n".join(warning_calls)
        assert "[REJECT]" in combined
        assert "unprotected_writes" in combined
