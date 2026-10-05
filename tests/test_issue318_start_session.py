#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #318: flextools_start silently accepts unknown args; session
user_request bleeds across concurrent agents.

  * `task` is now an alias for `user_request` (a caller passing task="..."
    gets it honored instead of silently dropped; an explicit user_request
    wins when both are given).
  * Unknown keys reach the handler (FlexToolsStartInput is extra="allow")
    and are reported as a top-level `ignored_params` list plus a warning,
    instead of vanishing.
  * user_request is filed per session_id: concurrent agents sharing one
    server process pass distinct session_id tokens on start (and echo the
    token on run_module) so each agent's turn-level request resolves to its
    own, not whichever agent started last.
"""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel
from flextoolsmcp.server.handlers import admin as admin_mod
from flextoolsmcp.server.session import SessionState


def _state():
    return kernel.get_session_state()


def _parse(response):
    return json.loads(response[0].text)


@pytest.fixture(autouse=True)
def _clean_session():
    kernel.reset_session()
    yield
    kernel.reset_session()


@pytest.fixture(autouse=True)
def _ensure_ops_logger():
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()


def _warnings(data):
    return data.get("warnings", [])


class TestTaskAlias:
    def test_task_becomes_the_turn_user_request(self):
        data = _parse(asyncio.run(admin_mod.handle_start({"task": "T050 port recipe"})))
        assert data["status"] == "session_initialized", data
        assert _state().get_user_request() == "T050 port recipe"
        assert "ignored_params" not in data, "task is a known key, not ignored"
        assert any("task" in w and "user_request" in w for w in _warnings(data)), (
            f"alias should be visible: {_warnings(data)}"
        )

    def test_explicit_user_request_wins_over_task(self):
        data = _parse(
            asyncio.run(
                admin_mod.handle_start(
                    {"task": "T050 port recipe", "user_request": "verbatim human text"}
                )
            )
        )
        assert _state().get_user_request() == "verbatim human text"
        assert not any("alias" in w for w in _warnings(data)), (
            f"no alias note when user_request was explicit: {_warnings(data)}"
        )

    def test_model_keeps_task_out_of_ignored(self):
        # End-to-end through the Pydantic model: `task` is declared, so it
        # must not be reported as ignored after dispatch validation.
        from flextoolsmcp.server.models import FlexToolsStartInput

        dumped = FlexToolsStartInput(
            api_mode="flexicon", task="T050 port recipe"
        ).model_dump()
        data = _parse(asyncio.run(admin_mod.handle_start(dumped)))
        assert "ignored_params" not in data, data.get("ignored_params")
        assert _state().get_user_request() == "T050 port recipe"


class TestIgnoredParams:
    def test_unknown_key_is_reported(self):
        data = _parse(
            asyncio.run(admin_mod.handle_start({"write_enbled": True}))
        )
        assert data["status"] == "session_initialized", data
        assert data["ignored_params"] == ["write_enbled"], data
        assert any("write_enbled" in w for w in _warnings(data)), _warnings(data)

    def test_unknown_key_survives_dispatch_validation(self):
        # The production path validates through the model before the handler
        # sees the args; extra="allow" must let the typo through to the warning.
        from flextoolsmcp.server.models import FlexToolsStartInput

        dumped = FlexToolsStartInput(
            api_mode="flexicon", write_enbled=True
        ).model_dump()
        assert dumped.get("write_enbled") is True
        data = _parse(asyncio.run(admin_mod.handle_start(dumped)))
        assert data["ignored_params"] == ["write_enbled"], data

    def test_known_keys_are_not_ignored(self):
        data = _parse(
            asyncio.run(
                admin_mod.handle_start(
                    {
                        "api_mode": "flexicon",
                        "project_name": "",
                        "write_enabled": False,
                        "user_request": "hi",
                        "session_id": "agent-1",
                        "task": "t",
                        "output_type": "auto",
                    }
                )
            )
        )
        assert "ignored_params" not in data, data.get("ignored_params")

    def test_multiple_unknown_keys_sorted(self):
        data = _parse(
            asyncio.run(admin_mod.handle_start({"zzz": 1, "aaa": 2}))
        )
        assert data["ignored_params"] == ["aaa", "zzz"], data


class TestPerSessionUserRequest:
    def test_concurrent_agents_keep_their_own_request(self):
        asyncio.run(
            admin_mod.handle_start(
                {"session_id": "agent-A", "user_request": "Implement task T047"}
            )
        )
        asyncio.run(
            admin_mod.handle_start(
                {"session_id": "agent-B", "user_request": "Implement task T050"}
            )
        )
        # The issue's bleed: every op carried the last-started agent's
        # request. Keyed lookup resolves each agent's own.
        assert _state().get_user_request("agent-A") == "Implement task T047"
        assert _state().get_user_request("agent-B") == "Implement task T050"

    def test_no_token_falls_back_to_turn_scalar(self):
        asyncio.run(admin_mod.handle_start({"user_request": "solo turn"}))
        assert _state().get_user_request() == "solo turn"
        assert _state().get_user_request("never-seen") == "solo turn"

    def test_restart_without_request_resets_that_sessions_slot(self):
        asyncio.run(
            admin_mod.handle_start(
                {"session_id": "agent-A", "user_request": "first turn"}
            )
        )
        asyncio.run(admin_mod.handle_start({"session_id": "agent-A"}))
        assert _state().get_user_request("agent-A") == ""

    def test_start_echoes_the_session_id(self):
        data = _parse(
            asyncio.run(admin_mod.handle_start({"session_id": "agent-A"}))
        )
        assert data["session"]["session_id"] == "agent-A", data["session"]


class TestSessionStateUnit:
    def test_configure_files_request_under_session_id(self):
        s = SessionState()
        s.configure(session_id="A", user_request="req-A")
        s.configure(session_id="B", user_request="req-B")
        assert s.get_user_request("A") == "req-A"
        assert s.get_user_request("B") == "req-B"
        # Scalar keeps the latest for single-agent callers.
        assert s.user_request == "req-B"
        assert s.get_user_request() == "req-B"

    def test_configure_without_user_request_leaves_slots_alone(self):
        s = SessionState()
        s.configure(session_id="A", user_request="req-A")
        # Cold-start style configure() without the kwarg must not blank it.
        s.configure(session_id="A", api_mode="flexicon")
        assert s.get_user_request("A") == "req-A"

    def test_reset_clears_the_slots(self):
        s = SessionState()
        s.configure(session_id="A", user_request="req-A")
        s.reset()
        assert s.user_request_by_session == {}
        assert s.get_user_request("A") == ""
