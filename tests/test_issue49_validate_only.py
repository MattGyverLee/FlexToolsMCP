#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #49: validate_only mode for run_module -- full preflight without
execution.

Covers:
- RunModuleInput.validate_only field (default False, accepted True).
- build_writeability_payload(): merges detect_cud_operations() +
  certify_script_readonly() findings with a `kind` discriminator
  (wrapper|raw_lcm), closing #44's self-contradictory count.
- _build_validate_only_checks(): runs gates 1-11 WITHOUT short-circuiting
  (except a syntax failure, which blocks the AST-dependent gates after it).
- handle_run_module(validate_only=True) end-to-end: never opens the project,
  never spawns the subprocess, side-effect-free discovery, distinct telemetry
  outcome ("validate_only", not "preflight_reject").
"""

import ast
import asyncio
import json

import pytest

from flextoolsmcp.server.models import RunModuleInput
from flextoolsmcp.server.validators import build_writeability_payload
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.handlers.execution import _build_validate_only_checks
from flextoolsmcp.server import kernel, project_discovery, project_access
from flextoolsmcp.server.project_access import LockHolder, ProjectAccess


@pytest.fixture(autouse=True)
def _ensure_operations_logger():
    """server_state gate checks the operations logger is initialized; make
    sure it is so unit-level _build_validate_only_checks() calls that don't
    go through the full handler (which initializes it via kernel) still see
    a healthy server_state gate."""
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _access(verdict="free", *, pid=68436, process="FieldWorks", sharing=None, holder=False):
    """Issue #93 cycle 7 (P1-A): a ProjectAccess factory for stubbing
    probe_project_access() in validate_only tests, mirroring
    tests/test_shared_mode_write_gate.py's `_access()`. Without this, the
    validate_only project_lock enrichment (execution.py:2049-2076) probes
    the LIVE HOST and its verdict/blocking fields are host-dependent."""
    return ProjectAccess(
        project_name="TestProj",
        verdict=verdict,
        sharing_enabled=sharing,
        holder=LockHolder(pid=pid, process_name=process, timestamp_ticks=None) if holder else None,
        lock_age_seconds=None,
    )


# ---------------------------------------------------------------------------
# RunModuleInput.validate_only field
# ---------------------------------------------------------------------------

class TestValidateOnlyField:
    def test_default_is_false(self):
        assert RunModuleInput(code="x=1").validate_only is False

    def test_explicit_true_accepted(self):
        assert RunModuleInput(code="x=1", validate_only=True).validate_only is True

    def test_backup_before_write_default_none(self):
        assert RunModuleInput(code="x=1").backup_before_write is None


# ---------------------------------------------------------------------------
# build_writeability_payload: shared #49/#55 builder
# ---------------------------------------------------------------------------

class TestBuildWriteabilityPayload:
    def test_no_mutations_is_not_mutating(self):
        cert = {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
        }
        cud_info = {"is_cud": False}
        payload = build_writeability_payload("x=1", None, None, cud_info=cud_info, cert=cert)
        assert payload["is_mutating_script"] is False
        assert payload["mutations_detected"] == []
        assert payload["would_require"] == {"write_enabled": False, "project_lock": False}

    def test_wrapper_and_raw_lcm_kinds_both_surface(self):
        """Regression for #44: a raw LCM write surfacing in
        unprotected_liblcm_calls but not the flexicon-index 'mutating' total
        no longer produces a self-contradictory count -- both are visible in
        mutations_detected with distinct `kind` discriminators."""
        cert = {
            "is_certified_readonly": False,
            "mutating_calls": [
                {"class": "LexSenseOperations", "method": "SetGloss", "is_mutating": True, "line": 14},
                {"class": "LexSenseOperations", "method": "GetGloss", "is_mutating": False, "line": 15},
            ],
            "unprotected_liblcm_calls": [
                {"method": "sense.Gloss.set_String", "line": 20, "context": "sense.Gloss.set_String(ws, 'x')"},
            ],
        }
        cud_info = {"is_cud": False}
        payload = build_writeability_payload("code", None, None, cud_info=cud_info, cert=cert)
        assert payload["is_mutating_script"] is True
        kinds = {(m["kind"], m["line"]) for m in payload["mutations_detected"]}
        assert ("wrapper", 14) in kinds
        assert ("raw_lcm", 20) in kinds
        # The non-mutating readonly call must NOT appear.
        assert not any(m["line"] == 15 for m in payload["mutations_detected"])
        # Sorted by line ascending.
        lines = [m["line"] for m in payload["mutations_detected"]]
        assert lines == sorted(lines)
        assert payload["would_require"] == {"write_enabled": True, "project_lock": True}

    def test_cud_regex_only_still_flags_mutating(self):
        """A script flagged by detect_cud_operations() (line-blind regex) but
        with no entries in cert's line-aware lists must still be reported as
        mutating (is_mutating_script True), even though mutations_detected
        may be empty (no line-aware source to report)."""
        cert = {"is_certified_readonly": True, "mutating_calls": [], "unprotected_liblcm_calls": []}
        cud_info = {"is_cud": True}
        payload = build_writeability_payload("code", None, None, cud_info=cud_info, cert=cert)
        assert payload["is_mutating_script"] is True
        assert payload["would_require"]["write_enabled"] is True

    def test_computes_cud_info_and_cert_when_not_supplied(self):
        """When cud_info/cert are omitted, the builder computes them itself."""
        payload = build_writeability_payload("x = 1\n", None, None)
        assert payload["is_mutating_script"] is False
        assert payload["mutations_detected"] == []


# ---------------------------------------------------------------------------
# _build_validate_only_checks: gate ordering / no-short-circuit / reporting
# ---------------------------------------------------------------------------

class TestBuildValidateOnlyChecks:
    def _fake_session_state(self):
        class _Fake:
            def get_discovered_apis(self):
                return set()
        return _Fake()

    def test_syntax_error_short_circuits_ast_gates_only(self):
        try:
            ast.parse("def broken(:\n")
        except SyntaxError as e:
            syn_exc = e
        else:
            pytest.fail("expected SyntaxError")

        checks, writeability = _build_validate_only_checks(
            code="def broken(:\n",
            code_tree=None,
            syntax_error=syn_exc,
            api_idx=None,
            session_state_obj=self._fake_session_state(),
            write_enabled=False,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )
        assert len(checks) == 1
        assert checks[0] == {
            "gate": "syntax",
            "passed": False,
            "issues": [{"line": syn_exc.lineno, "message": syn_exc.msg}],
        }
        assert writeability["is_mutating_script"] is False

    def test_all_green_script_all_gates_pass(self):
        code = "x = 1\nreport = None\n"
        tree = ast.parse(code)
        checks, writeability = _build_validate_only_checks(
            code=code,
            code_tree=tree,
            syntax_error=None,
            api_idx=None,
            session_state_obj=self._fake_session_state(),
            write_enabled=False,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )
        # All 11 production gates present, in production order.
        gate_order = [c["gate"] for c in checks]
        assert gate_order == [
            "syntax", "server_state", "partial_module_structure",
            "unprotected_writes", "casting", "api_discovery_required",
            "undiscovered_entity", "undefined_variables", "missing_imports",
            "wrong_library_imports", "invalid_api_chain",
        ]
        assert all(c["passed"] for c in checks)
        assert writeability["is_mutating_script"] is False

    def test_multi_fault_reports_every_failure_no_short_circuit(self, monkeypatch):
        """A script with problems at THREE independent gates must report ALL
        THREE in one response -- no short-circuit after the first failure."""
        monkeypatch.setattr(
            execution_mod, "validate_server_state",
            lambda: {"is_healthy": False, "issues": [("error", "api_index not loaded")]},
        )
        monkeypatch.setattr(
            execution_mod, "detect_casting_needs",
            lambda code, casting_index, tree: {
                "has_casting_issues": True,
                # Issue #49 B-5: per-issue severity now drives the verdict
                # (see _has_error_severity_casting_issue), so the mocked
                # issue must carry "error" itself, not just the top-level
                # summary field, to keep proving this gate still fails
                # here -- a known-pattern hit is genuinely "error"-tier and
                # must reject regardless of write_enabled.
                "casting_issues": [{"property": "Gloss", "line": 3, "severity": "error"}],
                "severity": "error",
            },
        )
        monkeypatch.setattr(
            execution_mod, "detect_undefined_variables",
            lambda code, tree: {"has_undefined": True, "undefined_vars": ["SomeInternal"]},
        )

        code = "x = 1\n"
        tree = ast.parse(code)
        checks, _ = _build_validate_only_checks(
            code=code,
            code_tree=tree,
            syntax_error=None,
            api_idx=None,
            session_state_obj=self._fake_session_state(),
            write_enabled=False,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )
        by_gate = {c["gate"]: c for c in checks}
        assert by_gate["server_state"]["passed"] is False
        assert by_gate["casting"]["passed"] is False
        assert by_gate["undefined_variables"]["passed"] is False
        # Gates untouched by the stubs still ran and passed -- proving no
        # short-circuit occurred once the first fault was found.
        assert by_gate["unprotected_writes"]["passed"] is True
        assert by_gate["invalid_api_chain"]["passed"] is True
        assert len(checks) == 11

    def test_mutating_script_writeability_has_both_kinds(self, monkeypatch):
        """Regression for #44: a mutating script's writeability block must
        carry BOTH wrapper and raw_lcm kinds when both are present."""
        monkeypatch.setattr(
            execution_mod, "certify_script_readonly",
            lambda code, api_idx, tree: {
                "is_certified_readonly": False,
                "mutating_calls": [
                    {"class": "LexEntryOperations", "method": "Create", "is_mutating": True, "line": 10},
                ],
                "unprotected_liblcm_calls": [
                    {"method": "entry.LexemeForm.set_String", "line": 22, "context": "..."},
                ],
            },
        )
        monkeypatch.setattr(
            execution_mod, "detect_cud_operations",
            lambda code: {"is_cud": True, "operations": ["CREATE (Create())"]},
        )
        code = "project.LexEntry.Create(x)\n"
        tree = ast.parse(code)
        checks, writeability = _build_validate_only_checks(
            code=code,
            code_tree=tree,
            syntax_error=None,
            api_idx=None,
            session_state_obj=self._fake_session_state(),
            write_enabled=False,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )
        assert writeability["is_mutating_script"] is True
        kinds = {m["kind"] for m in writeability["mutations_detected"]}
        assert kinds == {"wrapper", "raw_lcm"}
        by_gate = {c["gate"]: c for c in checks}
        assert by_gate["unprotected_writes"]["passed"] is False


class TestCastingGateAgreesWithRealGate:
    """Issue #49 B-5: this gate must agree with what handle_run_module's
    casting decision (issue #40 B-1) would actually do for the same issue
    set and write_enabled value -- not fail on ANY casting issue regardless
    of severity/write_enabled. Detection/reporting must stay intact either
    way; only the pass/fail verdict may change."""

    def _fake_session_state(self):
        class _Fake:
            def get_discovered_apis(self):
                return set()
        return _Fake()

    def _checks_for(self, monkeypatch, *, issues, write_enabled):
        monkeypatch.setattr(
            execution_mod, "detect_casting_needs",
            lambda code, casting_index, tree: {
                "has_casting_issues": True,
                "casting_issues": issues,
                "severity": "error" if any(i.get("severity") == "error" for i in issues) else "warning",
            },
        )
        code = "x = 1\n"
        tree = ast.parse(code)
        checks, _ = _build_validate_only_checks(
            code=code,
            code_tree=tree,
            syntax_error=None,
            api_idx=None,
            session_state_obj=self._fake_session_state(),
            write_enabled=write_enabled,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )
        return {c["gate"]: c for c in checks}

    def test_readonly_warning_tier_only_casting_passes(self, monkeypatch):
        """The bug: before the fix this gate reported passed=False here
        regardless of severity, even though handle_run_module(write_enabled=
        False) proceeds for an all-warning-tier issue set (issue #40 B-1).
        A dry-run validator that disagrees with the real gate is the exact
        trust bug issue #40 complained about."""
        by_gate = self._checks_for(
            monkeypatch,
            issues=[{"property": "Foo", "line": 1, "severity": "warning", "fix": "cast it to IFoo"}],
            write_enabled=False,
        )
        assert by_gate["casting"]["passed"] is True
        # Issues are still fully reported, never swallowed by the downgrade.
        assert by_gate["casting"]["issues"][0]["property"] == "Foo"
        assert "note" in by_gate["casting"]

    def test_write_enabled_warning_tier_only_casting_still_fails(self, monkeypatch):
        """Same warning-tier-only issue set, but write_enabled=True -- the
        real gate hard-rejects at EVERY severity on write runs, so
        validate_only must too."""
        by_gate = self._checks_for(
            monkeypatch,
            issues=[{"property": "Foo", "line": 1, "severity": "warning", "fix": "cast it to IFoo"}],
            write_enabled=True,
        )
        assert by_gate["casting"]["passed"] is False
        assert "note" not in by_gate["casting"]

    def test_readonly_error_tier_casting_still_fails(self, monkeypatch):
        """An error-severity issue (known-pattern hit, or a genuine
        attribute typo) still hard-rejects even read-only -- the downgrade
        is warning-tier-only, never blanket."""
        by_gate = self._checks_for(
            monkeypatch,
            issues=[{"property": "HeadWord", "line": 1, "severity": "error", "fix": "cast it to ILexEntry"}],
            write_enabled=False,
        )
        assert by_gate["casting"]["passed"] is False

    def test_readonly_mixed_severity_still_fails(self, monkeypatch):
        """One warning-tier issue plus one error-tier issue in the SAME
        read-only run must still fail -- ANY error-severity issue blocks
        the whole gate, matching handle_run_module's `any(...)` check."""
        by_gate = self._checks_for(
            monkeypatch,
            issues=[
                {"property": "Foo", "line": 1, "severity": "warning", "fix": "cast it to IFoo"},
                {"property": "HeadWord", "line": 2, "severity": "error", "fix": "cast it to ILexEntry"},
            ],
            write_enabled=False,
        )
        assert by_gate["casting"]["passed"] is False


class _RealCastingFakeIndex:
    """Real-shaped stand-in used by the end-to-end validate_only/run_module
    agreement tests below -- deliberately exercises REAL
    `detect_casting_needs` AND REAL `detect_interface_attribute_typos`,
    neither monkeypatched. Issue #39/#40 P1-2 (cycle 5): the predecessor of
    these tests monkeypatched `detect_interface_attribute_typos` to always
    return no typos, which made the test structurally unable to catch the
    bug it existed to guard -- `_build_validate_only_checks`'s Gate 5 never
    called that detector at all, so `validate_only` silently disagreed with
    `run_module` on the whole #39 typo class. A test that stubs out the
    component whose interaction is under test validates nothing.

    `IWfiAnalysis.CategoryRA` backs the genuine warning-tier casting hit;
    `ILexDb.Entries` (not `EntriesOC`) backs the genuine typo hit.
    """

    liblcm = {
        "entities": {
            "IWfiAnalysis": {"properties": [{"name": "CategoryRA"}], "methods": []},
            "ILexDb": {"properties": [{"name": "Entries"}], "methods": []},
        }
    }
    flexicon = {"entities": {}}
    flexlibs_stable = {"entities": {}}
    casting_index = {
        "properties": {
            "CategoryRA": {
                "requires_cast_from": ["ICmObject"],
                "defined_on": ["IWfiAnalysis"],
            },
        },
        "polymorphic_collections": {},
    }


def _stub_agreement_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    # Issue #93 cycle 7 (P1-A): this helper drives handle_run_module(...,
    # validate_only=True), which reaches the project_lock enrichment;
    # without stubbing probe_project_access too, that enrichment probes
    # the live host.
    monkeypatch.setattr(project_access, "probe_project_access", lambda name: _access("free"))
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: _RealCastingFakeIndex())
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True, "confidence": "high",
            "mutating_calls": [], "unprotected_liblcm_calls": [],
        },
    )

    async def fake_run_script_async(path, timeout_seconds=None):
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===\n" + json.dumps({"success": True, "messages": []}),
            "stderr": "", "timeout": False, "returncode": 0,
        }
    monkeypatch.setattr(execution_mod, "run_script_async", fake_run_script_async)


def test_validate_only_agrees_with_run_module_on_readonly_warning_tier_casting(monkeypatch, tmp_path):
    """Issue #49 B-5, end-to-end, REAL detection (cycle 5 rewrite -- see
    _RealCastingFakeIndex): for the SAME code and write_enabled=False,
    validate_only's verdict must match what handle_run_module(validate_only=
    False) actually does. A warning-tier-only casting issue set is
    downgraded (proceeds) by the real gate per issue #40 B-1; validate_only
    must report `validated`, not `validation_failed`, for the identical
    input. `ana.CategoryRA` is uncast (no cast alias in scope), so REAL
    detect_interface_attribute_typos naturally has nothing to check here --
    this exercises the genuine downgrade path end to end, not a stub of it."""
    _stub_agreement_env(monkeypatch, tmp_path)

    base_args = {
        "code": "def f(ana):\n    return ana.CategoryRA\n",
        "project_name": "TestProj",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
    }

    validate_result = asyncio.run(
        execution_mod.handle_run_module({**base_args, "validate_only": True})
    )
    validate_data = _parse(validate_result)

    run_result = asyncio.run(
        execution_mod.handle_run_module({**base_args, "validate_only": False})
    )
    run_data = _parse(run_result)

    # The real gate proceeds -- no casting rejection.
    assert run_data.get("error_code") != "casting_issues_detected", run_data
    assert run_data.get("success") is True, run_data

    # validate_only must agree: the casting gate is not a validation failure.
    assert validate_data["status"] == "validated", validate_data
    by_gate = {c["gate"]: c for c in validate_data["checks"]}
    assert by_gate["casting"]["passed"] is True, by_gate["casting"]


def test_validate_only_agrees_with_run_module_on_readonly_typo_class(monkeypatch, tmp_path):
    """Issue #39/#40 P1-2 regression, REAL detection (cycle 5): a pure
    attribute typo (`ILexDb.EntriesOC` -> `Entries`) is a genuine ERROR, not
    a downgradeable warning -- it must hard-reject on BOTH run_module and
    validate_only for the SAME read-only input.

    Before the fix, `_build_validate_only_checks`'s Gate 5 never called
    `detect_interface_attribute_typos` at all (only `handle_run_module`
    did), so validate_only reported `passed: True` / "run_module would
    proceed without rejecting" for code that run_module actually
    hard-rejects -- a false reassurance across the whole #39 typo class.
    Both call sites now share `_compute_casting_decision`, so this can no
    longer drift."""
    _stub_agreement_env(monkeypatch, tmp_path)

    base_args = {
        "code": "d = ILexDb(project)\nx = d.EntriesOC\n",
        "project_name": "TestProj",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
    }

    validate_result = asyncio.run(
        execution_mod.handle_run_module({**base_args, "validate_only": True})
    )
    validate_data = _parse(validate_result)

    run_result = asyncio.run(
        execution_mod.handle_run_module({**base_args, "validate_only": False})
    )
    run_data = _parse(run_result)

    # The real gate hard-rejects -- a genuine typo is "error" tier, never
    # downgradeable regardless of write_enabled.
    assert run_data.get("error_code") == "casting_issues_detected", run_data

    # validate_only must agree, not silently pass -- this is the P1-2 bug.
    assert validate_data["status"] == "validation_failed", validate_data
    by_gate = {c["gate"]: c for c in validate_data["checks"]}
    assert by_gate["casting"]["passed"] is False, by_gate["casting"]
    reported = {ci.get("property") for ci in by_gate["casting"]["issues"]}
    assert "EntriesOC" in reported, by_gate["casting"]


# ---------------------------------------------------------------------------
# handle_run_module(validate_only=True): end-to-end wiring
# ---------------------------------------------------------------------------

def _stub_validate_only_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    # Issue #93 cycle 7 (P1-A, cycle6-qc.md / lock-site-inventory.md
    # execution.py:2035-2047): the project_lock enrichment calls
    # probe_project_access() too -- stub it alongside check_project_locked
    # so verdict/blocking are deterministic instead of host-dependent.
    # Individual tests can override this via monkeypatch.setattr(
    # project_access, "probe_project_access", ...) for other verdicts.
    monkeypatch.setattr(project_access, "probe_project_access", lambda name: _access("free"))
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)

    def _boom(*a, **k):
        raise AssertionError("run_script_async must NEVER be invoked by validate_only")
    monkeypatch.setattr(execution_mod, "run_script_async", _boom)


class TestHandleRunModuleValidateOnly:
    def test_all_green_returns_validated_and_never_executes(self, monkeypatch, tmp_path):
        _stub_validate_only_env(monkeypatch, tmp_path)
        args = {
            "code": "x = 1\n",
            "project_name": "TestProj",
            "write_enabled": False,
            "validate_only": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["status"] == "validated"
        assert data["validate_only"] is True
        assert all(c["passed"] for c in data["checks"])
        assert "project_lock" in data
        assert data["project_lock"]["locked"] is False
        assert data["project_lock"]["verdict"] == "free"
        assert data["project_lock"]["blocking"] is False


    def test_multi_fault_script_reports_validation_failed(self, monkeypatch, tmp_path):
        _stub_validate_only_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "validate_server_state",
            lambda: {"is_healthy": False, "issues": [("error", "boom")]},
        )
        args = {
            "code": "x = 1\n",
            "project_name": "TestProj",
            "write_enabled": False,
            "validate_only": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["status"] == "validation_failed"
        by_gate = {c["gate"]: c for c in data["checks"]}
        assert by_gate["server_state"]["passed"] is False

    def test_telemetry_outcome_is_validate_only_not_preflight_reject(self, monkeypatch, tmp_path):
        _stub_validate_only_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "validate_server_state",
            lambda: {"is_healthy": False, "issues": [("error", "boom")]},
        )
        args = {
            "code": "x = 1\n",
            "project_name": "TestProj",
            "write_enabled": False,
            "validate_only": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        asyncio.run(execution_mod.handle_run_module(args))
        jsonl = tmp_path / "operations.jsonl"
        assert jsonl.exists()
        rec = json.loads(jsonl.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert rec["outcome"] == "validate_only"
        assert rec["outcome"] != "preflight_reject"

    def test_mutating_script_writeability_end_to_end(self, monkeypatch, tmp_path):
        _stub_validate_only_env(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "certify_script_readonly",
            lambda code, api_idx, tree: {
                "is_certified_readonly": False,
                "mutating_calls": [
                    {"class": "LexEntryOperations", "method": "Create", "is_mutating": True, "line": 1},
                ],
                "unprotected_liblcm_calls": [
                    {"method": "entry.LexemeForm.set_String", "line": 2, "context": "..."},
                ],
            },
        )
        args = {
            "code": "project.LexEntry.Create(x)\n",
            "project_name": "TestProj",
            "write_enabled": False,
            "validate_only": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["writeability"]["is_mutating_script"] is True
        kinds = {m["kind"] for m in data["writeability"]["mutations_detected"]}
        assert kinds == {"wrapper", "raw_lcm"}

    def test_discovery_gates_report_but_do_not_mark_discovered(self, monkeypatch, tmp_path):
        """Issue #49: validate_only must be side-effect-free -- an undiscovered
        entity is reported in `checks[]` but never added to auto_discovered_apis
        or validated_apis."""
        _stub_validate_only_env(monkeypatch, tmp_path)

        class _FakeIndex:
            flexicon = {"entities": {"POSOperations": {"methods": [], "properties": []}}}
            casting_index = None
        monkeypatch.setattr(execution_mod, "get_api_index", lambda: _FakeIndex())

        # Ensure a clean slate on the shared session_state singleton.
        execution_mod.session_state.discovered_apis = set()
        execution_mod.session_state.validated_apis = set()
        execution_mod.session_state.auto_discovered_apis = set()

        args = {
            "code": "pos = POSOperations(project)\npos.Create(x)\n",
            "project_name": "TestProj",
            "write_enabled": False,
            "validate_only": True,
            "skip_api_check": False,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["status"] == "validation_failed"
        by_gate = {c["gate"]: c for c in data["checks"]}
        assert by_gate["undiscovered_entity"]["passed"] is False
        # Side-effect free: nothing was marked discovered by validate_only.
        assert execution_mod.session_state.auto_discovered_apis == set()
        assert execution_mod.session_state.validated_apis == set()


# ---------------------------------------------------------------------------
# validate_only project_lock enrichment (issue #93 cycle 7, P1-A)
# ---------------------------------------------------------------------------

class TestValidateOnlyProjectLockEnrichment:
    """Issue #93 cycle 7 (P1-A): the validate_only project_lock enrichment
    (execution.py:2049-2076) was untested with a controlled probe -- every
    existing test stubbed check_project_locked but not
    probe_project_access, so verdict/blocking were whatever the live host
    happened to report. These pin the emitted payload for the three
    verdicts explicitly required by the cycle-7 fix, plus the fail-open
    interim patch's unprobed case."""

    def _run(self, monkeypatch, tmp_path, access):
        _stub_validate_only_env(monkeypatch, tmp_path)
        monkeypatch.setattr(project_access, "probe_project_access", lambda name: access)
        args = {
            "code": "x = 1\n",
            "project_name": "TestProj",
            "write_enabled": False,
            "validate_only": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        return _parse(result)["project_lock"]

    def test_free_is_not_blocking(self, monkeypatch, tmp_path):
        payload = self._run(monkeypatch, tmp_path, _access("free"))
        assert payload["verdict"] == "free"
        assert payload["blocking"] is False

    def test_open_shared_is_not_blocking(self, monkeypatch, tmp_path):
        payload = self._run(
            monkeypatch, tmp_path,
            _access("open_shared", sharing=True, holder=True),
        )
        assert payload["verdict"] == "open_shared"
        assert payload["blocking"] is False
        assert payload["sharing_enabled"] is True

    def test_open_exclusive_is_blocking(self, monkeypatch, tmp_path):
        payload = self._run(
            monkeypatch, tmp_path,
            _access("open_exclusive", sharing=False, holder=True),
        )
        assert payload["verdict"] == "open_exclusive"
        assert payload["blocking"] is True
        assert payload["sharing_enabled"] is False

    def test_unprobed_omits_verdict_and_reports_blocking_unknown(self, monkeypatch, tmp_path):
        """Fail-open interim patch (cycle 7): when the probe never actually
        ran (projects directory unresolvable), `verdict` must be omitted
        entirely and `blocking` must be null, not a confident False."""
        unprobed = ProjectAccess(
            project_name="TestProj",
            verdict="free",
            sharing_enabled=None,
            holder=None,
            lock_age_seconds=None,
            probed=False,
        )
        payload = self._run(monkeypatch, tmp_path, unprobed)
        assert "verdict" not in payload
        assert payload["blocking"] is None
