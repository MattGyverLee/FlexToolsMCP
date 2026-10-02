#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #334: partial_module_structure rejects drove retry loops.

Models resubmitted byte-identical code after a reject, and the loop
assistance never fired (``assistance_triggered: false`` on every row).
Two causes: the detector needs 5 failures in a row (the streaks were 2-4),
and the JSONL close hardcoded ``assistance_triggered=False`` because it is
written before the response is wrapped.

Now:
- A byte-identical resubmit of just-rejected code is called out on its
  first repeat (``_assistance.pattern_detected == "identical_resubmit"``,
  top-level ``identical_resubmit: true``), for every gate.
- The JSONL ``assistance_triggered`` field previews what the response gets.
- The rejection leads with the cheapest fix: a mechanical bare-snippet
  ``auto_fixed_code`` naming the exact ``def Main`` line removed.
- With a ``user_intent``, next_steps name the closest recipes (existing
  ranker, no new ranking).
"""

import ast
import asyncio
import json

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.session import SessionState
from flextoolsmcp.server.validators import (
    build_bare_snippet_fix,
    build_partial_module_rejection,
    detect_partial_module_structure,
)
from test_issue49_validate_only import _parse, _stub_agreement_env  # noqa: E402
from test_issue303_module_structure_pingpong import (  # noqa: E402
    BINDING_ONLY,
    DOCS_ONLY,
    READONLY_CERT,
    UNPROTECTED_CERT,
)


# ---------------------------------------------------------------------------
# Bare-snippet auto-fix
# ---------------------------------------------------------------------------

class TestBareSnippetFix:
    def test_docs_only_becomes_bare_snippet(self):
        fix = build_bare_snippet_fix(DOCS_ONLY)
        assert fix["available"] is True, fix
        assert fix["code"] == "report.Info('hello')\n"
        assert fix["main_line"] == 2
        assert fix["main_line_text"] == "def Main(project, report, modifyAllowed):"
        assert fix["removed_scaffold"] == [{"lines": "1", "text": "docs = {FTM_Name: 'x'}"}]

    def test_binding_only_drops_binding(self):
        fix = build_bare_snippet_fix(BINDING_ONLY)
        assert fix["available"] is True, fix
        assert "Main" not in fix["code"]
        assert "FlexToolsModuleClass" not in fix["code"]
        ast.parse(fix["code"])

    def test_keeps_imports_comments_and_nesting(self):
        code = (
            "from flexicon import FLExProject\n"
            "docs = {FTM_Name: 'x',\n"
            "        FTM_Version: 1}\n"
            "def Main(project,\n"
            "         report, modifyAllowed):\n"
            "    # walk entries\n"
            "    for e in project.LexEntry.GetAll():\n"
            "        if modifyAllowed:\n"
            "            report.Info('w')\n"
        )
        fix = build_bare_snippet_fix(code)
        assert fix["available"] is True, fix
        assert fix["code"] == (
            "from flexicon import FLExProject\n"
            "# walk entries\n"
            "for e in project.LexEntry.GetAll():\n"
            "    if modifyAllowed:\n"
            "        report.Info('w')\n"
        )
        assert fix["removed_scaffold"][0]["lines"] == "2-3"

    @pytest.mark.parametrize("code,reason", [
        ("docs = {}\ndef Main(project, report, modifyAllowed):\n    return 1\n", "return"),
        ("docs = {}\ndef Main(p, r, m):\n    r.Info('x')\n", "parameters"),
        ("docs = {}\ndef Main(project, report, modifyAllowed): report.Info('x')\n", "def line"),
        ("docs = {}\ndef Main(project, report, modifyAllowed):\n    global X\n    X = 1\n", "global"),
    ])
    def test_unsafe_shapes_are_declined(self, code, reason):
        fix = build_bare_snippet_fix(code)
        assert fix["available"] is False
        assert reason in fix["reason"]

    def test_nested_function_return_is_fine(self):
        code = (
            "docs = {}\n"
            "def Main(project, report, modifyAllowed):\n"
            "    def helper(x):\n"
            "        return x\n"
            "    report.Info(helper('a'))\n"
        )
        assert build_bare_snippet_fix(code)["available"] is True

    def test_long_code_is_declined(self):
        body = "".join(f"    report.Info('{i}')\n" for i in range(100))
        code = "docs = {}\ndef Main(project, report, modifyAllowed):\n" + body
        fix = build_bare_snippet_fix(code)
        assert fix["available"] is False
        assert "longer than" in fix["reason"]


class TestRejectionLeadsWithCheapestFix:
    def test_auto_fix_is_first_step_and_names_the_line(self):
        rej = build_partial_module_rejection(
            detect_partial_module_structure(DOCS_ONLY), READONLY_CERT, DOCS_ONLY
        )
        assert rej["next_steps"][0].startswith("1. Cheapest: resubmit auto_fixed_code")
        assert "line 2 `def Main(project, report, modifyAllowed):`" in rej["next_steps"][0]
        assert "skip_module_check=True" in rej["next_steps"][1]
        assert rej["auto_fix"]["available"] is True
        assert "auto_fixed_code" in rej["message"]

    def test_no_auto_fix_lead_with_unprotected_writes(self):
        rej = build_partial_module_rejection(
            detect_partial_module_structure(DOCS_ONLY), UNPROTECTED_CERT, DOCS_ONLY
        )
        assert "skip_module_check=True" in rej["next_steps"][0]
        assert not any("auto_fixed_code" in s for s in rej["next_steps"])


# ---------------------------------------------------------------------------
# Identical-resubmit detection (session level)
# ---------------------------------------------------------------------------

class TestIdenticalResubmit:
    def test_second_identical_reject_fires(self):
        s = SessionState()
        s.begin_submission("a" * 64, 100)
        assert s.record_failure_and_detect("partial_module_structure", 100) is None
        s.begin_submission("a" * 64, 100)
        pattern = s.record_failure_and_detect("partial_module_structure", 100)
        assert pattern["pattern_detected"] == "identical_resubmit"
        assert pattern["identical_resubmit"] is True
        assert "same code" in pattern["message"]
        assert "auto_fixed_code" in pattern["message"]

    def test_changed_code_does_not_fire(self):
        s = SessionState()
        s.begin_submission("a" * 64, 100)
        s.record_failure_and_detect("partial_module_structure", 100)
        s.begin_submission("b" * 64, 101)
        assert s.record_failure_and_detect("partial_module_structure", 101) is None

    def test_identical_code_with_a_different_answer_does_not_fire(self):
        """Identical code that got past the first gate (recorded discovery,
        skip_module_check, ...) did NOT get "the same answer"."""
        s = SessionState()
        s.begin_submission("a" * 64, 100)
        s.record_failure_and_detect("api_discovery_required", 100)
        s.begin_submission("a" * 64, 100)
        assert s.record_failure_and_detect("RuntimeError", 100) is None

    def test_success_breaks_the_streak(self):
        s = SessionState()
        s.begin_submission("a" * 64, 100)
        s.record_failure_and_detect("syntax_error", 100)
        s.reset_op_signals()
        s.begin_submission("a" * 64, 100)
        assert s.record_failure_and_detect("syntax_error", 100) is None

    def test_mid_preflight_success_signal_does_not_erase_the_snapshot(self):
        """A warn-only casting pass records a None signal mid-preflight; the
        identical check is snapshotted at submission so a later reject of the
        same code still says so."""
        s = SessionState()
        s.begin_submission("a" * 64, 100)
        s.record_failure_and_detect("missing_imports", 100)
        s.begin_submission("a" * 64, 100)
        s.record_op_signal(error_code=None, code_size_bytes=100)
        pattern = s.record_failure_and_detect("missing_imports", 100)
        assert pattern and pattern["pattern_detected"] == "identical_resubmit"

    def test_preview_matches_and_does_not_mutate(self):
        s = SessionState()
        s.begin_submission("a" * 64, 100)
        s.record_failure_and_detect("syntax_error", 100)
        s.begin_submission("a" * 64, 100)
        before = list(s.recent_op_signals)
        preview = s.preview_failure_pattern("syntax_error")
        assert preview["pattern_detected"] == "identical_resubmit"
        assert list(s.recent_op_signals) == before
        assert s.record_failure_and_detect("syntax_error", 100)["pattern_detected"] == "identical_resubmit"


# ---------------------------------------------------------------------------
# End to end through handle_run_module
# ---------------------------------------------------------------------------

def _run(args):
    return _parse(asyncio.run(execution_mod.handle_run_module(args)))


def _args(code, **extra):
    return {
        "code": code,
        "project_name": "TestProj_334",
        "write_enabled": False,
        "skip_api_check": True,
        **extra,
    }


def _jsonl_rows(tmp_path):
    path = tmp_path / "operations.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class TestLiveGate:
    def test_identical_resubmit_gets_assistance_and_truthful_telemetry(
        self, monkeypatch, tmp_path, reset_session_state
    ):
        _stub_agreement_env(monkeypatch, tmp_path)
        first = _run(_args(DOCS_ONLY))
        assert first["error_code"] == "partial_module_structure", first
        assert first["auto_fixed_code"] == "report.Info('hello')\n"
        assert first["main_line_text"] == "def Main(project, report, modifyAllowed):"
        assert "_assistance" not in first

        second = _run(_args(DOCS_ONLY))
        assert second["error_code"] == "partial_module_structure"
        assert second["identical_resubmit"] is True
        assert second["_assistance"]["pattern_detected"] == "identical_resubmit"
        assert "same code" in second["_assistance"]["message"]

        rows = [r for r in _jsonl_rows(tmp_path) if r.get("error_code") == "partial_module_structure"]
        assert [r["assistance_triggered"] for r in rows[-2:]] == [False, True]

    def test_auto_fixed_code_passes_the_gate(self, monkeypatch, tmp_path, reset_session_state):
        _stub_agreement_env(monkeypatch, tmp_path)
        first = _run(_args(DOCS_ONLY))
        fixed = _run(_args(first["auto_fixed_code"]))
        assert fixed.get("error_code") is None, fixed

    def test_validate_only_carries_auto_fix(self, monkeypatch, tmp_path, reset_session_state):
        _stub_agreement_env(monkeypatch, tmp_path)
        data = _run({**_args(DOCS_ONLY), "validate_only": True})
        gate = {c["gate"]: c for c in data["checks"]}["partial_module_structure"]
        assert gate["passed"] is False
        assert gate["auto_fixed_code"] == "report.Info('hello')\n"

    def test_unprotected_writes_says_why_no_auto_fix(self, monkeypatch, tmp_path, reset_session_state):
        _stub_agreement_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "certify_script_readonly", lambda c, i, t: UNPROTECTED_CERT
        )
        data = _run(_args(DOCS_ONLY))
        assert "auto_fixed_code" not in data
        assert "unguarded writes" in data["auto_fix_unavailable_reason"]

    def test_user_intent_points_at_closest_recipes(self, monkeypatch, tmp_path, reset_session_state):
        _stub_agreement_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "_closest_recipes_step",
            lambda q, limit=2: f"Or reuse a recipe: flextools_list_recipes(recipe_id='x') [{q}]",
        )
        data = _run(_args(DOCS_ONLY, user_intent="create missing entries"))
        assert data["next_steps"][-1].endswith("[create missing entries]")


def test_closest_recipes_step_uses_shared_ranker():
    step = execution_mod._closest_recipes_step("list all lexical entries with glosses")
    if step is not None:  # shipped library present
        assert "flextools_list_recipes(recipe_id='" in step
    assert execution_mod._closest_recipes_step("") is None
    assert execution_mod._closest_recipes_step(None) is None
