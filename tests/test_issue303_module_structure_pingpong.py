#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #303: break the partial_module_structure / unprotected_writes ping-pong.

Weak models bounced between two rejections: a bare snippet with writes got
``unprotected_writes``; wrapping it in ``def Main`` got
``partial_module_structure``; dropping Main got ``unprotected_writes`` again.

Now:
- ``def Main`` with NEITHER scaffold piece runs as a snippet with a
  ``[module scaffold]`` warning and a ready-to-paste ``suggested_scaffold``.
- A genuine half-module (exactly one piece) still rejects, with the missing
  piece ready to paste, ``skip_module_check=True`` as the first next step,
  and one combined rejection when the code also has unguarded writes.
- ``unprotected_writes`` guidance says ``modifyAllowed`` is predefined in
  bare snippets and shows a bare-snippet fix.
"""

import ast
import asyncio
import json

from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    build_partial_module_rejection,
    detect_partial_module_structure,
    get_unprotected_write_guidance,
)
from test_issue49_validate_only import _parse, _stub_agreement_env  # noqa: E402


MAIN_WRAPPED = (
    "def Main(project, report, modifyAllowed):\n"
    "    report.Info('hello')\n"
)
DOCS_ONLY = (
    "docs = {FTM_Name: 'x'}\n"
    "def Main(project, report, modifyAllowed):\n"
    "    report.Info('hello')\n"
)
BINDING_ONLY = (
    "def Main(project, report, modifyAllowed):\n"
    "    report.Info('hello')\n"
    "FlexToolsModule = FlexToolsModuleClass(Main, docs)\n"
)

UNPROTECTED_CERT = {
    "is_certified_readonly": False,
    "confidence": "high",
    "mutating_calls": [
        {"class": "LexEntryOperations", "method": "SetLexemeForm", "is_mutating": True},
    ],
    "unprotected_liblcm_calls": [],
}
READONLY_CERT = {
    "is_certified_readonly": True,
    "confidence": "high",
    "mutating_calls": [],
    "unprotected_liblcm_calls": [],
}


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class TestDetector:
    def test_main_wrapped_snippet_is_not_partial(self):
        r = detect_partial_module_structure(MAIN_WRAPPED)
        assert r["is_partial_module"] is False
        assert r["is_main_wrapped_snippet"] is True
        assert r["has_main"] is True
        assert "ran as a snippet" in r["advisory"]

    def test_main_wrapped_scaffold_is_canonical(self):
        scaffold = detect_partial_module_structure(MAIN_WRAPPED)["suggested_scaffold"]
        assert "from flextoolslib import *" in scaffold
        for key in ("FTM_Name", "FTM_Version", "FTM_ModifiesDB",
                    "FTM_Synopsis", "FTM_Description"):
            assert key in scaffold
        assert "FlexToolsModule = FlexToolsModuleClass(Main, docs)" in scaffold
        assert "FTM_ModifiesDB  : False" in scaffold
        # The advisory carries the scaffold so the warning is self-contained.
        assert scaffold in detect_partial_module_structure(MAIN_WRAPPED)["advisory"]

    def test_scaffold_modifies_db_follows_guard(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if modifyAllowed:\n"
            "        report.Info('write')\n"
        )
        scaffold = detect_partial_module_structure(code)["suggested_scaffold"]
        assert "FTM_ModifiesDB  : True" in scaffold

    def test_scaffold_omits_import_when_present(self):
        code = "from flextoolslib import *\n" + MAIN_WRAPPED
        scaffold = detect_partial_module_structure(code)["suggested_scaffold"]
        assert "from flextoolslib import" not in scaffold

    def test_docs_only_half_module_rejects_with_binding_scaffold(self):
        r = detect_partial_module_structure(DOCS_ONLY)
        assert r["is_partial_module"] is True
        assert r["is_main_wrapped_snippet"] is False
        assert r["has_docs_dict"] is True
        assert r["has_flextools_binding"] is False
        assert "FlexToolsModuleClass(Main, docs)" in r["suggested_scaffold"]
        assert "FTM_Name" not in r["suggested_scaffold"]
        assert "skip_module_check=True" in r["suggestion"]

    def test_binding_only_half_module_rejects_with_docs_scaffold(self):
        r = detect_partial_module_structure(BINDING_ONLY)
        assert r["is_partial_module"] is True
        assert "FTM_Name" in r["suggested_scaffold"]
        assert "FlexToolsModuleClass" not in r["suggested_scaffold"]

    def test_bare_snippet_has_no_advisory(self):
        r = detect_partial_module_structure("report.Info('x')\n")
        assert r["is_partial_module"] is False
        assert r["is_main_wrapped_snippet"] is False
        assert r["advisory"] == ""
        assert r["suggested_scaffold"] == ""


# ---------------------------------------------------------------------------
# Shared rejection builder
# ---------------------------------------------------------------------------

class TestPartialModuleRejection:
    def test_skip_module_check_is_first_next_step(self):
        rej = build_partial_module_rejection(
            detect_partial_module_structure(DOCS_ONLY), READONLY_CERT
        )
        assert "skip_module_check=True" in rej["next_steps"][0]
        assert rej["also_unprotected_writes"] is False
        assert rej["mutations_found"] == []
        assert "modifyAllowed" not in rej["message"]

    def test_combined_with_unprotected_writes(self):
        rej = build_partial_module_rejection(
            detect_partial_module_structure(DOCS_ONLY), UNPROTECTED_CERT
        )
        assert rej["also_unprotected_writes"] is True
        assert rej["mutations_found"] == ["LexEntryOperations.SetLexemeForm()"]
        assert "if modifyAllowed:" in rej["message"]
        assert "skip_module_check=True" in rej["next_steps"][0]
        joined = " ".join(rej["next_steps"])
        assert "suggested_scaffold" in joined
        assert "if modifyAllowed:" in joined

    def test_no_cert_means_not_combined(self):
        rej = build_partial_module_rejection(detect_partial_module_structure(DOCS_ONLY))
        assert rej["also_unprotected_writes"] is False


# ---------------------------------------------------------------------------
# unprotected_writes guidance
# ---------------------------------------------------------------------------

class TestUnprotectedWriteGuidance:
    def test_states_modify_allowed_predefined_in_bare_snippets(self):
        g = get_unprotected_write_guidance(UNPROTECTED_CERT)
        assert "predefined in bare" in g["why"]
        assert "def Main" in g["why"]
        assert "if modifyAllowed:" in g["bare_snippet_fix"]
        assert "def Main" not in g["bare_snippet_fix"].split("\n", 1)[1]
        assert "no def Main is needed" in g["next_steps"][0]

    def test_backward_compatible_keys(self):
        g = get_unprotected_write_guidance(UNPROTECTED_CERT)
        for key in ("error", "message", "mutations_found", "why", "fix_pattern",
                    "templates_to_review", "next_steps"):
            assert key in g
        assert g["error"] == "unprotected_mutations_detected"
        assert set(g["fix_pattern"]) == {"before", "after"}

    def test_main_wrapper_note_for_main_wrapped_code(self):
        g = get_unprotected_write_guidance(UNPROTECTED_CERT, MAIN_WRAPPED)
        assert "runs as a snippet" in g["main_wrapper_note"]
        assert g["next_steps"][0].startswith("Note: ")

    def test_no_main_wrapper_note_for_bare_snippet(self):
        g = get_unprotected_write_guidance(UNPROTECTED_CERT, "report.Info('x')\n")
        assert "main_wrapper_note" not in g


# ---------------------------------------------------------------------------
# validate_only gate
# ---------------------------------------------------------------------------

def _validate_only_gate(code, monkeypatch, cert=READONLY_CERT):
    monkeypatch.setattr(execution_mod, "certify_script_readonly", lambda c, i, t: cert)
    checks = execution_mod._build_validate_only_checks(
        code=code,
        code_tree=ast.parse(code),
        syntax_error=None,
        api_idx=None,
        session_state_obj=object(),
        write_enabled=False,
        api_mode="flexicon",
        skip_api_check=True,
        provenance_existing=False,
        skip_module_check=False,
    )[0]
    return {c["gate"]: c for c in checks}


class TestValidateOnlyGate:
    def test_main_wrapped_passes_with_advisory(self, monkeypatch):
        by_gate = _validate_only_gate(MAIN_WRAPPED, monkeypatch)
        gate = by_gate["partial_module_structure"]
        assert gate["passed"] is True
        assert "ran as a snippet" in gate["advisory"]
        assert "FlexToolsModuleClass(Main, docs)" in gate["suggested_scaffold"]

    def test_half_module_fails_with_combined_detail(self, monkeypatch):
        by_gate = _validate_only_gate(DOCS_ONLY, monkeypatch, UNPROTECTED_CERT)
        gate = by_gate["partial_module_structure"]
        assert gate["passed"] is False
        assert gate["also_unprotected_writes"] is True
        assert "skip_module_check=True" in gate["next_steps"][0]
        # unprotected_writes also reports (no short-circuit in validate_only).
        assert by_gate["unprotected_writes"]["passed"] is False


# ---------------------------------------------------------------------------
# End to end: handle_run_module live gate agrees with validate_only
# ---------------------------------------------------------------------------

def _run(args):
    return _parse(asyncio.run(execution_mod.handle_run_module(args)))


def _base_args(code):
    return {
        "code": code,
        "project_name": "TestProj",
        "write_enabled": False,
        "skip_api_check": True,
    }


class TestLiveGate:
    def test_main_wrapped_snippet_runs_with_scaffold_warning(self, monkeypatch, tmp_path):
        _stub_agreement_env(monkeypatch, tmp_path)
        run_data = _run(_base_args(MAIN_WRAPPED))
        assert run_data.get("error_code") is None, run_data
        assert run_data.get("success") is True, run_data
        assert "[module scaffold]" in json.dumps(run_data)

        validate_data = _run({**_base_args(MAIN_WRAPPED), "validate_only": True})
        by_gate = {c["gate"]: c for c in validate_data["checks"]}
        assert by_gate["partial_module_structure"]["passed"] is True

    def test_half_module_with_unprotected_writes_is_one_combined_rejection(
        self, monkeypatch, tmp_path
    ):
        _stub_agreement_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "certify_script_readonly", lambda c, i, t: UNPROTECTED_CERT
        )
        data = _run(_base_args(DOCS_ONLY))
        assert data["error_code"] == "partial_module_structure", data
        assert data["also_unprotected_writes"] is True
        assert data["mutations_found"] == ["LexEntryOperations.SetLexemeForm()"]
        assert "if modifyAllowed:" in data["message"]
        assert "skip_module_check=True" in data["next_steps"][0]
        assert "FlexToolsModuleClass(Main, docs)" in data["suggested_scaffold"]

        validate_data = _run({**_base_args(DOCS_ONLY), "validate_only": True})
        by_gate = {c["gate"]: c for c in validate_data["checks"]}
        assert by_gate["partial_module_structure"]["passed"] is False

    def test_unprotected_writes_response_carries_bare_snippet_fix(
        self, monkeypatch, tmp_path
    ):
        _stub_agreement_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "certify_script_readonly", lambda c, i, t: UNPROTECTED_CERT
        )
        data = _run(_base_args(MAIN_WRAPPED))
        assert data["error_code"] == "unprotected_writes", data
        assert "if modifyAllowed:" in data["bare_snippet_fix"]
        assert "runs as a snippet" in data["main_wrapper_note"]
