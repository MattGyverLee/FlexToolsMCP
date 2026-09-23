#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for issue #171: reset_session() must mutate, not rebind."""

import flextoolsmcp.server.handlers.execution as exec_mod
from flextoolsmcp.server.kernel import reset_session, session_state as kernel_session_state


class TestResetSessionMutatesSingleton:
    """reset_session() must clear state visible through handler import bindings."""

    def test_reset_clears_state_on_handler_reference(self):
        before_id = id(exec_mod.session_state)
        assert exec_mod.session_state is kernel_session_state

        exec_mod.session_state.project_name = "LeakTestProject"
        exec_mod.session_state.initialized = True
        exec_mod.session_state.record_validated_api("LexEntryOperations")

        reset_session()

        assert id(exec_mod.session_state) == before_id
        assert exec_mod.session_state is kernel_session_state
        assert exec_mod.session_state.project_name == ""
        assert exec_mod.session_state.initialized is False
        assert exec_mod.session_state.validated_apis == set()

    def test_reset_session_state_fixture_pattern(self):
        """Mirrors tests/conftest.py reset_session_state fixture import path."""
        from flextoolsmcp.server.kernel import reset_session as fixture_reset

        exec_mod.session_state.project_name = "FixtureLeak"
        fixture_reset()
        assert exec_mod.session_state.project_name == ""
        assert fixture_reset is reset_session
