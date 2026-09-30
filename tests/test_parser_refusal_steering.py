#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression guard for CP6 (issue #167): every campaign refusal's steering
(``hint`` / ``install_hint`` / ``next_step``) must route the caller at a
registered tool, and must never fall back to a bare "retry" / "try again"
with nothing named to do instead.

Covers the ten campaign codes named in the CP6 task: parser_filing_in_progress,
parser_agent_missing, parse_morph_unresolved, parser_engine_mismatch,
parser_core_missing, parse_run_not_found, parser_tool_missing, parser_timeout,
parser_job_failed, parser_config_failed.

Table-driven over the builders/hint functions that produce the steering
text, rather than over full server round-trips, so it stays offline (no
FLEx, no live project, no worker process). Two sites that build their
steering inline in a raise statement, deep inside code that is impractical
to invoke standalone in a unit test (the filing worker's per-word setup,
and the sandbox engine-check's next_step), are instead checked by reading
their own source text -- the same "read the file, assert on its content"
approach `test_parser_health_block.py` and `test_parser_error_models.py`
already use for contract/doc transcription checks.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from flextoolsmcp.server.dispatch import get_all_tool_names

REGISTERED_TOOLS = set(get_all_tool_names())

_BARE_RETRY_RE = re.compile(r"\btry again\b|\bretry\b", re.IGNORECASE)

_REPO_ROOT = Path(__file__).parent.parent
_SRC = _REPO_ROOT / "src" / "flextoolsmcp" / "server"


def _iter_strings(obj):
    """Yield every string leaf reachable from obj (dict/list nesting)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)


def _iter_rungs(obj):
    """Yield every dict that looks like a `_rung()` result."""
    if isinstance(obj, dict):
        if {"action", "tool", "rationale", "est_cost"} <= obj.keys():
            yield obj
        for v in obj.values():
            yield from _iter_rungs(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_rungs(v)


def assert_no_bare_retry(payload, *, label: str) -> None:
    """No string in `payload` says "retry"/"try again" without a tool
    attached -- either the enclosing rung names a registered tool, or the
    string itself names one by name.
    """
    rung_texts = set()
    for rung in _iter_rungs(payload):
        tool = rung.get("tool")
        text = " ".join(str(v) for v in rung.values() if isinstance(v, str))
        rung_texts.add(text)
        if _BARE_RETRY_RE.search(text) and not tool:
            pytest.fail(
                f"{label}: rung {rung!r} says 'retry'/'try again' but names "
                f"no tool"
            )
        if tool is not None:
            assert tool in REGISTERED_TOOLS, (
                f"{label}: rung names {tool!r}, which is not a registered tool"
            )

    for s in _iter_strings(payload):
        if s in rung_texts:
            continue  # already checked above, rung-aware
        if _BARE_RETRY_RE.search(s):
            assert any(t in s for t in REGISTERED_TOOLS), (
                f"{label}: {s!r} says 'retry'/'try again' but names no "
                f"registered tool"
            )


def assert_names_a_real_tool_if_any(payload, *, label: str) -> None:
    """Every `tool` field anywhere in `payload` is None or registered."""
    for rung in _iter_rungs(payload):
        tool = rung.get("tool")
        if tool is not None:
            assert tool in REGISTERED_TOOLS, (
                f"{label}: rung names {tool!r}, which is not a registered tool"
            )


# ---------------------------------------------------------------------------
# parser_engine_mismatch
# ---------------------------------------------------------------------------


class TestParserEngineMismatch:
    def test_check_active_parser_hint(self):
        from flextoolsmcp.server import parser_probe

        project = SimpleNamespace(
            MorphologicalDataOA=SimpleNamespace(ActiveParser="XAmple")
        )
        with pytest.raises(parser_probe.ParserEngineMismatchError) as excinfo:
            parser_probe.check_active_parser(project, supported_engines=("HC",))
        assert_no_bare_retry(excinfo.value.detail, label="check_active_parser")

    def test_sandbox_engine_hint_unreadable(self):
        from flextoolsmcp.server.sandbox import engine as sandbox_engine

        reading = sandbox_engine.EngineReading(
            key=("path", 0, 0),
            readable=False,
            active_parser=None,
            configured_engine="XAmple",
            reason="locked",
            parameters=None,
        )
        hint = sandbox_engine._hint(reading, ["HC"])
        assert_no_bare_retry({"hint": hint}, label="sandbox_engine._hint (unreadable)")

    def test_sandbox_engine_hint_readable(self):
        from flextoolsmcp.server.sandbox import engine as sandbox_engine

        reading = sandbox_engine.EngineReading(
            key=("path", 0, 0),
            readable=True,
            active_parser="XAmple",
            configured_engine="XAmple",
            reason=None,
            parameters=None,
        )
        hint = sandbox_engine._hint(reading, ["HC"])
        assert_no_bare_retry({"hint": hint}, label="sandbox_engine._hint (readable)")

    def test_sandbox_run_engine_check_next_step_source(self):
        """`_sandbox_run_engine_check`'s rungs, read from source.

        Not invoked directly: building a `_SandboxPlan` needs a live-ish
        project/engine setup. The rung shape is simple enough (literal
        `_rung(...)` calls) that transcribing them here catches the same
        regression a direct call would.
        """
        text = (_SRC / "handlers" / "parse" / "sandbox_checks.py").read_text(encoding="utf-8")
        match = re.search(
            r"def _sandbox_run_engine_check.*?(?=\ndef _)", text, re.DOTALL
        )
        assert match, "_sandbox_run_engine_check not found"
        body = match.group(0)
        actions = re.findall(r'action="([^"]*)"', body)
        assert actions, "no rung actions found in _sandbox_run_engine_check"
        for action in actions:
            if _BARE_RETRY_RE.search(action):
                pytest.fail(
                    f"_sandbox_run_engine_check: action {action!r} is a bare "
                    f"retry"
                )
        assert "_sandbox_list_rung(" in body, (
            "the second rung should route to a real tool via "
            "_sandbox_list_rung"
        )

    def test_sandbox_list_rung_names_a_registered_tool(self):
        from flextoolsmcp.server.handlers.parse import _sandbox_list_rung

        rung = _sandbox_list_rung("TestProj")
        assert rung["tool"] in REGISTERED_TOOLS


# ---------------------------------------------------------------------------
# parser_core_missing
# ---------------------------------------------------------------------------


class TestParserCoreMissing:
    def test_surface_probe_refusal_detail(self):
        from flextoolsmcp.server.filing.filer import SurfaceProbe

        probe = SurfaceProbe(
            ok=False,
            signal="absent",
            expected_path="ParserCore.dll",
            detected_version=None,
            missing_members=["ParseFiler.ProcessParse"],
            load_error=None,
        )
        detail = probe.refusal_detail()
        assert_no_bare_retry(detail, label="SurfaceProbe.refusal_detail")
        assert "flextools_health" in detail["install_hint"]


# ---------------------------------------------------------------------------
# parser_agent_missing
# ---------------------------------------------------------------------------


class TestParserAgentMissing:
    def test_probe_hc_agent_absent_hint(self):
        from flextoolsmcp.server import parser_probe

        class KeyNotFoundException(Exception):
            pass

        class _LangProject:
            @property
            def DefaultParserAgent(self):
                raise KeyNotFoundException(
                    f"lookup failed for {parser_probe.HC_AGENT_GUID}"
                )

        project = SimpleNamespace(LangProject=_LangProject())
        result = parser_probe.probe_hc_agent(project, "HC")
        assert result.hint is not None
        assert_no_bare_retry({"hint": result.hint}, label="probe_hc_agent")
        # flextools_health never opens a project, so it cannot see the agent.
        assert "flextools_parse_text" in result.hint
        assert "flextools_health" not in result.hint

    def test_worker_filing_agent_missing_hint_source(self):
        """`FilingWorker._resolve_hc_agent`'s hint, read from source.

        Not invoked directly: it opens a real LCM project. The literal
        string is simple enough that reading it here catches the same
        regression a direct call would.
        """
        text = (_SRC / "filing" / "worker_filing.py").read_text(encoding="utf-8")
        match = re.search(
            r"def _resolve_hc_agent.*?(?=\n    def )", text, re.DOTALL
        )
        assert match, "_resolve_hc_agent not found"
        body = match.group(0)
        hint_match = re.search(r'"hint":\s*\(([^)]*)\)', body, re.DOTALL)
        assert hint_match, "no hint literal found in _resolve_hc_agent"
        hint_text = hint_match.group(1)
        assert_no_bare_retry({"hint": hint_text}, label="_resolve_hc_agent hint")
        assert "flextools_parse_text" in hint_text
        assert "flextools_health" not in hint_text


# ---------------------------------------------------------------------------
# parser_tool_missing
# ---------------------------------------------------------------------------


class TestParserToolMissing:
    def test_tool_missing_rungs(self):
        from flextoolsmcp.server.handlers.parse import _tool_missing_rungs

        rungs = _tool_missing_rungs("fieldworks_hermitcrab")
        assert_no_bare_retry(rungs, label="_tool_missing_rungs")
        assert_names_a_real_tool_if_any(rungs, label="_tool_missing_rungs")
        assert any(r.get("tool") == "flextools_health" for r in rungs)


# ---------------------------------------------------------------------------
# parse_morph_unresolved
# ---------------------------------------------------------------------------


class TestParseMorphUnresolved:
    def test_resolver_hints(self):
        from flextoolsmcp.server.parse.resolver import (
            AMBIGUOUS, NONE, NO_MSA, Resolution, refusal_detail,
        )

        spec = SimpleNamespace(headword="kosong", sense=None, msa_hvo=None,
                                position=0)
        for outcome in (AMBIGUOUS, NO_MSA, NONE):
            resolution = Resolution(spec=spec, candidates=[], outcome=outcome)
            detail = refusal_detail(resolution)
            # These hints are deliberately data-fix guidance (spelling, sense,
            # lexicon), not tool routes -- but must still never say a bare
            # "retry"/"try again".
            assert_no_bare_retry(detail, label=f"resolver hint ({outcome})")


# ---------------------------------------------------------------------------
# parse_run_not_found
# ---------------------------------------------------------------------------


class TestParseRunNotFound:
    def test_run_not_found_hint_names_tools(self):
        from flextoolsmcp.server.handlers import parse as parse_handlers

        runner = SimpleNamespace(
            known_run_ids=lambda: [],
            record_dir=None,
        )
        result = parse_handlers._live_run_not_found(runner, "0" * 32)
        payload = _text_content_to_dict(result)
        assert_no_bare_retry(payload, label="_live_run_not_found")
        hint = payload.get("hint", "")
        assert any(t in hint for t in ("flextools_try_word", "flextools_parse_text"))


# ---------------------------------------------------------------------------
# parser_filing_in_progress
# ---------------------------------------------------------------------------


class TestParserFilingInProgress:
    def test_in_progress_hint(self):
        from flextoolsmcp.server.filing.claims import FilingClaim, in_progress_hint

        claim = FilingClaim(
            project="TestProj", run_id="a" * 32, started_at="2026-01-01T00:00:00Z",
            shared=False,
        )
        hint = in_progress_hint(claim)
        assert_no_bare_retry({"hint": hint}, label="in_progress_hint")
        assert "flextools_parse_status" in hint


# ---------------------------------------------------------------------------
# parser_timeout / parser_job_failed / parser_config_failed
# ---------------------------------------------------------------------------


class TestSandboxFailureCodes:
    def test_failure_rungs_names_registered_tools(self):
        from flextoolsmcp.server.handlers.parse import _failure_rungs

        handle = SimpleNamespace(project_name="TestProj", run_id="a" * 32,
                                  words_completed=3)
        rungs = _failure_rungs(handle)
        assert_no_bare_retry(rungs, label="_failure_rungs")
        assert_names_a_real_tool_if_any(rungs, label="_failure_rungs")
        tools = {r.get("tool") for r in rungs}
        assert "flextools_grammar_health" in tools
        assert "flextools_health" in tools
        assert any(r.get("tool") == "flextools_parse_log" for r in rungs)

    def test_failure_rungs_no_words_completed_still_names_tools(self):
        from flextoolsmcp.server.handlers.parse import _failure_rungs

        handle = SimpleNamespace(project_name="TestProj", run_id="a" * 32,
                                  words_completed=0)
        rungs = _failure_rungs(handle)
        assert_no_bare_retry(rungs, label="_failure_rungs (no words)")
        assert_names_a_real_tool_if_any(rungs, label="_failure_rungs (no words)")


def _text_content_to_dict(result):
    import json

    item = result[0]
    text = getattr(item, "text", None)
    if text is None and isinstance(item, dict):
        text = item.get("text")
    return json.loads(text)


# ---------------------------------------------------------------------------
# Sweep: every rung this file could construct names a registered tool
# ---------------------------------------------------------------------------


def test_every_rung_shape_in_this_suite_has_the_expected_keys():
    """A guard on the guard: `_iter_rungs`'s shape test must actually match
    `handlers.parse._rung`'s output, or every check above would vacuously
    pass having found zero rungs.
    """
    from flextoolsmcp.server.handlers.parse import _rung

    rung = _rung(action="do X", tool="flextools_health", args=None,
                  rationale="why", est_cost="seconds")
    found = list(_iter_rungs({"next_step": [rung]}))
    assert len(found) == 1
    assert found[0] == rung
