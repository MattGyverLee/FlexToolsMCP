#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #80: Graceful discovery redirect + provenance-sensitive preflight.

Covers:
- RunModuleInput.source provenance field (default 'authored', rejects junk).
- _build_capability_query: blends user_intent + entity tokens + guessed methods.
- _search_capability_inline: ranked method hits from the flexicon index; fail-open.
- _graceful_discovery_redirect: status:"ok", executed:False, needs_resubmit:True,
  carries _inline_discovery + capability_suggestions, validates against
  RunModuleSuccess. Telemetry line uses outcome "discovery_redirect" (not a reject).
- SAFETY INVARIANT: provenance ('source') can never skip write-safety -- the
  write-safety gate is wired before, and independent of, the discovery-gate skip.

Run with:
    python -m pytest tests/test_issue80_graceful_redirect.py -q -m "not requires_flex"
"""

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.models import RunModuleInput
from flextoolsmcp.server.response_models import RunModuleSuccess
from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers import execution
from flextoolsmcp.server.handlers.execution import (
    _build_capability_query,
    _search_capability_inline,
    _graceful_discovery_redirect,
)


# ---------------------------------------------------------------------------
# Fake index
# ---------------------------------------------------------------------------

class _FakeIndex:
    def __init__(self, entities):
        self.flexicon = {"entities": entities}


_ENTITIES = {
    "LexSenseOperations": {
        "category": "lexicon",
        "import_statement": "from flexicon import LexSenseOperations",
        "methods": [
            {
                "name": "GetSensePartOfSpeech",
                "signature": "(self, sense)",
                "description": "Get the part of speech of a sense",
                "is_mutating": False,
            },
            {
                "name": "GetGloss",
                "signature": "(self, sense)",
                "description": "Return the gloss text of a sense",
                "is_mutating": False,
            },
        ],
        "properties": [],
    },
    "FLExProject": {"properties": []},
}


# ---------------------------------------------------------------------------
# Provenance field
# ---------------------------------------------------------------------------

class TestSourceProvenanceField:
    def test_default_is_authored(self):
        assert RunModuleInput(code="x=1").source == "authored"

    def test_existing_accepted(self):
        assert RunModuleInput(code="x=1", source="existing").source == "existing"

    def test_invalid_source_rejected(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            RunModuleInput(code="x=1", source="from_the_ether")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _build_capability_query
# ---------------------------------------------------------------------------

class TestBuildCapabilityQuery:
    def test_blends_intent_entities_and_methods(self):
        tree = ast.parse("x = project.LexSense.GetSensePartOfSpeech(s)\n")
        q = _build_capability_query(
            tree, ["LexSenseOperations"], "find the part of speech for each sense"
        )
        assert "part of speech" in q
        # 'Operations' suffix stripped from the entity token
        assert "LexSense" in q and "LexSenseOperations" not in q
        # guessed method name surfaced
        assert "GetSensePartOfSpeech" in q

    def test_empty_inputs_yield_empty_query(self):
        assert _build_capability_query(None, [], None) == ""


# ---------------------------------------------------------------------------
# _search_capability_inline
# ---------------------------------------------------------------------------

class TestSearchCapabilityInline:
    def test_ranks_name_match_above_description_only(self):
        idx = _FakeIndex(_ENTITIES)
        rows = _search_capability_inline("part of speech sense", idx, limit=5)
        assert rows, "expected at least one capability hit"
        top = rows[0]
        assert top["entity"] == "LexSenseOperations"
        assert top["name"] == "GetSensePartOfSpeech"
        assert top["import_statement"] == "from flexicon import LexSenseOperations"

    def test_fail_open_on_empty_query(self):
        idx = _FakeIndex(_ENTITIES)
        assert _search_capability_inline("", idx) == []

    def test_fail_open_on_none_index(self):
        assert _search_capability_inline("gloss", None) == []

    def test_no_match_returns_empty(self):
        idx = _FakeIndex(_ENTITIES)
        assert _search_capability_inline("xyzzy plugh frobnicate", idx) == []


# ---------------------------------------------------------------------------
# _graceful_discovery_redirect
# ---------------------------------------------------------------------------

def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


class TestGracefulDiscoveryRedirect:
    def _redirect(self, tmp_path, monkeypatch):
        # Redirect telemetry JSONL to a tmp dir so we never touch prod logs (#74).
        monkeypatch.setattr(execution, "get_log_dir", lambda: tmp_path)
        return _graceful_discovery_redirect(
            op_id="op-test-80",
            seq=1,
            duration_s=0.01,
            reason="undiscovered_entity",
            message="I looked these up; apply and resubmit.",
            undiscovered=["POSOperations"],
            inline={"POSOperations": {"methods": []}},
            capability_suggestions=[{"entity": "LexSenseOperations", "name": "GetGloss"}],
            code_size_bytes=42,
        )

    def test_status_ok_but_not_executed(self, tmp_path, monkeypatch):
        data = _parse(self._redirect(tmp_path, monkeypatch))
        assert data["status"] == "ok"           # NOT an error
        assert data["executed"] is False        # code did not run
        assert data["_contract"] == CONTRACT_VERSION

    def test_carries_redirect_block_and_payloads(self, tmp_path, monkeypatch):
        data = _parse(self._redirect(tmp_path, monkeypatch))
        dr = data["discovery_redirect"]
        assert dr["needs_resubmit"] is True
        assert dr["reason"] == "undiscovered_entity"
        assert dr["undiscovered"] == ["POSOperations"]
        assert data["_inline_discovery"] == {"POSOperations": {"methods": []}}
        assert data["capability_suggestions"][0]["name"] == "GetGloss"

    def test_validates_against_run_module_success(self, tmp_path, monkeypatch):
        data = _parse(self._redirect(tmp_path, monkeypatch))
        m = RunModuleSuccess.model_validate(data, by_alias=True)
        assert m.status == "ok"
        assert m.executed is False
        assert m.discovery_redirect and m.discovery_redirect["needs_resubmit"] is True

    def test_telemetry_outcome_is_discovery_redirect_not_reject(self, tmp_path, monkeypatch):
        self._redirect(tmp_path, monkeypatch)
        jsonl = tmp_path / "operations.jsonl"
        assert jsonl.exists(), "redirect must emit a telemetry line"
        rec = json.loads(jsonl.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert rec["outcome"] == "discovery_redirect"
        assert rec["error_code"] == ""  # a redirect is not an error


# ---------------------------------------------------------------------------
# SAFETY INVARIANT: provenance can never bypass write-safety
# ---------------------------------------------------------------------------

class TestProvenanceCannotBypassWriteSafety:
    """The 'source' provenance flag is a COST lever, never a SAFETY lever.

    Structural guarantee against the whole class of "existing-script bypass":
    inside handle_run_module the write-safety reject (certify_script_readonly /
    unprotected_writes) must be wired BEFORE the discovery-gate skip, and the
    provenance skip token must never appear before that write-safety check. If a
    future edit reorders them, this test fails.
    """

    def _handler_body_lines(self):
        src = (
            Path(__file__).parent.parent
            / "src" / "flextoolsmcp" / "server" / "handlers" / "execution.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "handle_run_module"
        )
        return src.splitlines(), fn.lineno, fn.end_lineno

    def test_write_safety_precedes_discovery_skip(self):
        lines, start, end = self._handler_body_lines()
        body = "\n".join(lines[start - 1:end])

        # Write-safety reject wiring (runs unconditionally, no provenance guard).
        write_safety_idx = body.find("certify_script_readonly")
        # The point where provenance is allowed to skip the discovery gates.
        skip_apply_idx = body.find("if not _skip_discovery_gates")

        assert write_safety_idx != -1, "write-safety check missing from handler"
        assert skip_apply_idx != -1, "discovery-skip gate not wired in handler"
        # Write-safety must be evaluated BEFORE the provenance skip takes effect.
        assert write_safety_idx < skip_apply_idx, (
            "SAFETY REGRESSION: the write-safety gate must run before any "
            "provenance-driven discovery skip -- 'source' is a cost lever, never "
            "a safety lever."
        )

    def test_readonly_turn1_zero_discovery_does_not_hard_error(self):
        """Part 1 core claim: on the turn-1 zero-discovery gate, the WRITE branch
        still returns an api_discovery_required error, but the READ-ONLY branch
        must fall through (log only, no return) so per-entity auto-discovery /
        graceful redirect can take over. We assert the shape of that gate."""
        lines, start, end = self._handler_body_lines()
        body = "\n".join(lines[start - 1:end])

        gate = body.find("len(session_state.get_discovered_apis()) == 0")
        assert gate != -1, "turn-1 zero-discovery gate not found"
        # Bound the gate block to just before the per-entity gate.
        per_entity = body.find("detect_undiscovered_entities", gate)
        assert per_entity != -1
        gate_block = body[gate:per_entity]

        # WRITE branch keeps the hard error.
        assert "if write_enabled:" in gate_block, "gate must split write vs read-only"
        assert '"api_discovery_required"' in gate_block, \
            "write-path turn-1 gate must still emit api_discovery_required"
        # READ-ONLY branch (identified by its fall-through log marker) must not
        # return / error -- it falls through to the per-entity graceful path.
        marker = gate_block.find("deferring to")
        assert marker != -1, "read-only fall-through branch not found in gate"
        readonly_branch = gate_block[marker:]
        assert "return" not in readonly_branch and "error_response" not in readonly_branch, (
            "READ-ONLY turn-1 zero-discovery must fall through (no return / no "
            "hard error) so the graceful redirect path can handle it (issue #80)."
        )

    def test_write_safety_reject_not_guarded_by_provenance(self):
        """The unprotected_writes / CUD reject must not sit inside a provenance
        conditional. We assert the write-safety block does not mention the
        provenance tokens between certify_script_readonly and the casting check
        that follows it."""
        lines, start, end = self._handler_body_lines()
        body = "\n".join(lines[start - 1:end])
        ws = body.find("certify_script_readonly")
        casting = body.find("detect_casting_needs")
        assert ws != -1 and casting != -1 and ws < casting
        write_safety_region = body[ws:casting]
        assert "_skip_discovery_gates" not in write_safety_region
        assert "_provenance_existing" not in write_safety_region
