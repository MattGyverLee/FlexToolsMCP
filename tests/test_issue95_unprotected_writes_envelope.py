#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #95: unprotected mutating code must return a structured rejection.

Two branches of the writeability gate are covered:

  mutating_calls          – Flexicon index detects an is_mutating=True method
                            called without `if modifyAllowed:`.  Original test.
  unprotected_liblcm_calls – Raw facade-accessor pattern
                            `project.<X>.Create(...)` matched by
                            _LIBLCM_MUTABLE_PATTERNS without a guard.
                            New tests for the #95 exact repro (bare snippet
                            and Main-shaped module).
"""

import asyncio
import json

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import certify_script_readonly


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


class _FakeIndex:
    flexicon = {
        "entities": {
            "LexEntryOperations": {
                "category": "lexicon",
                "methods": [
                    {"name": "Create", "signature": "(self, form)", "is_mutating": True},
                ],
                "properties": [],
            }
        }
    }


def _stub_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: _FakeIndex())
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})


class TestUnprotectedWritesEnvelope:
    def test_unprotected_create_returns_structured_rejection(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        code = (
            "from flexicon import LexEntryOperations\n"
            "ops = LexEntryOperations(project)\n"
            'ops.Create("probe", create_blank_sense=True)\n'
        )
        args = {
            "code": code,
            "project_name": "TestProj_95",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))

        assert data["status"] == "error"
        assert data["error_code"] == "unprotected_writes"
        assert data["_contract"] == CONTRACT_VERSION
        assert "modifyAllowed" in data["message"] or "modifyAllowed" in data.get("why", "")
        assert data.get("next_steps")
        assert data["error"]["code"] == "unprotected_writes"

    # ------------------------------------------------------------------
    # Issue #95 exact repro: unprotected_liblcm_calls branch
    # The original symptom was `'str' object has no attribute 'get'`
    # for `project.LexEntry.Create(...)` calls not inside `if modifyAllowed:`.
    # These land in unprotected_liblcm_calls (NOT mutating_calls) because the
    # facade-accessor regex `project.*.Create(` fires before any Flexicon index
    # lookup; the index never sees this call as a wrapper mutation.
    # ------------------------------------------------------------------

    def test_bare_snippet_project_create_returns_structured_rejection(
        self, monkeypatch, tmp_path
    ):
        """Bare snippet (no Main) calling project.LexEntry.Create() unguarded.

        Pins the issue #95 repro for the unprotected_liblcm_calls branch:
        `project.<X>.Create(...)` matches _LIBLCM_MUTABLE_PATTERNS and is
        placed in unprotected_liblcm_calls, not mutating_calls.  The handler
        must return a structured `unprotected_writes` rejection, not the
        original `'str' object has no attribute 'get'` crash.
        """
        _stub_env(monkeypatch, tmp_path)
        code = 'entry = project.LexEntry.Create("probe")\n'

        # Pre-flight: confirm which branch this code exercises.
        # Note: project.LexEntry.Create() fires BOTH unprotected_liblcm_calls
        # (the _LIBLCM_MUTABLE_PATTERNS `project.*.Create` regex) AND
        # mutating_calls via the `unresolved_receiver` heuristic (CUD method
        # name on an untyped receiver -- a different code path from the
        # Flexicon-index lookup used by the original test).  We assert the
        # liblcm branch fires specifically (method label `project.*.Create`)
        # so the test pins the exact pattern rather than just checking rejection.
        cert = certify_script_readonly(code, _FakeIndex(), None)
        liblcm_calls = cert.get("unprotected_liblcm_calls") or []
        assert liblcm_calls, (
            "precondition: project.LexEntry.Create() must populate "
            "unprotected_liblcm_calls (the _LIBLCM_MUTABLE_PATTERNS branch)"
        )
        assert any(c.get("method") == "project.*.Create" for c in liblcm_calls), (
            "precondition: unprotected_liblcm_calls entry must carry the "
            "project.*.Create label confirming _LIBLCM_MUTABLE_PATTERNS fired"
        )

        args = {
            "code": code,
            "project_name": "TestProj_95",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))

        assert data["status"] == "error"
        assert data["error_code"] == "unprotected_writes"
        assert data["_contract"] == CONTRACT_VERSION
        assert "modifyAllowed" in data["message"] or "modifyAllowed" in data.get("why", "")
        assert data.get("next_steps")
        assert data["error"]["code"] == "unprotected_writes"

    def test_main_shaped_project_create_returns_structured_rejection(
        self, monkeypatch, tmp_path
    ):
        """Main-shaped module calling project.LexEntry.Create() without guard.

        Pins the issue #95 repro for the unprotected_liblcm_calls branch when
        code defines `def Main(project, report, modifyAllowed)` but the
        mutating call is NOT wrapped in `if modifyAllowed:`.  Confirms the
        rejection is structural (not module-shape dependent): the same
        _LIBLCM_MUTABLE_PATTERNS path fires regardless of whether Main is
        present.
        """
        _stub_env(monkeypatch, tmp_path)
        code = (
            "def Main(project, report, modifyAllowed):\n"
            '    entry = project.LexEntry.Create("probe")\n'
            '    report.Info("created: %s" % str(entry))\n'
        )

        # Pre-flight: confirm which branch this code exercises.
        # Same dual-fire behaviour as the bare-snippet case: both
        # unprotected_liblcm_calls (_LIBLCM_MUTABLE_PATTERNS) and mutating_calls
        # (unresolved_receiver heuristic) fire for this pattern.  We assert the
        # liblcm branch fires with its specific label.
        cert = certify_script_readonly(code, _FakeIndex(), None)
        liblcm_calls = cert.get("unprotected_liblcm_calls") or []
        assert liblcm_calls, (
            "precondition: project.LexEntry.Create() inside Main (unguarded) "
            "must populate unprotected_liblcm_calls"
        )
        assert any(c.get("method") == "project.*.Create" for c in liblcm_calls), (
            "precondition: unprotected_liblcm_calls entry must carry the "
            "project.*.Create label confirming _LIBLCM_MUTABLE_PATTERNS fired"
        )

        args = {
            "code": code,
            "project_name": "TestProj_95",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))

        assert data["status"] == "error"
        assert data["error_code"] == "unprotected_writes"
        assert data["_contract"] == CONTRACT_VERSION
        assert "modifyAllowed" in data["message"] or "modifyAllowed" in data.get("why", "")
        assert data.get("next_steps")
        assert data["error"]["code"] == "unprotected_writes"
