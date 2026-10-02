#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exclusive-access gate wiring in handle_run_module (specs/exclusive-access-gate
FR-004..FR-010, scenarios 1.1-1.8, 2.1).

A write-enabled script that changes writing systems or custom fields is
refused with `requires_exclusive_access` when the access probe says FieldWorks
holds the project in shared mode (`open_shared`) or cannot tell (`unknown`).
The refusal comes before the confirmation gate, the backup and any
subprocess. `open_exclusive` / `held_by_other` keep their `project_locked`
refusal.

Harness: tests/test_shared_mode_write_gate.py's. The certifier is stubbed, so
wrapper rows are fed in through the stubbed cert and raw shapes are found by
the detector's own AST pass. Detection against the real certifier and index
is covered in tests/test_exclusive_access_detect.py.
"""

import asyncio

import pytest

from flextoolsmcp.server import exclusive_access, project_access
from flextoolsmcp.server.handlers import execution as execution_mod

from test_shared_mode_write_gate import (
    _access,
    _allow_execution,
    _fake_run_script_async_ok,
    _parse,
    _refuse_execution,
    _stub_env,
)

WS_WRAPPER = (
    "if modifyAllowed:\n"
    "    project.WritingSystems.Create('qaa-x-zz')\n"
)
CF_WRAPPER = (
    "if modifyAllowed:\n"
    "    project.CustomFields.CreateField('LexEntry', 'zzExclTest', 'String')\n"
)
WS_RAW = (
    "lp = project.project.lp\n"
    "if modifyAllowed:\n"
    "    lp.CurrentVernacularWritingSystems.Add(ws)\n"
)
ORDINARY = "if modifyAllowed:\n    project.LexEntry.SetLexemeForm(entry, 'x')\n"

_ROWS = {
    WS_WRAPPER: [{"class": "WritingSystemOperations", "method": "Create", "line": 2,
                  "is_mutating": True, "source": "index", "protected": True}],
    CF_WRAPPER: [{"class": "CustomFieldOperations", "method": "CreateField", "line": 2,
                  "is_mutating": True, "source": "index", "protected": True}],
}


def _stub_cert(monkeypatch):
    """Certifier stub: guarded wrapper rows for the wrapper scripts, nothing
    for the rest (raw shapes are left to the detector's AST layer)."""
    def fake(code, api_idx, tree=None):
        return {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "protected_calls": _ROWS.get(code, []),
            "unknown_calls": [],
            "unprotected_liblcm_calls": [],
            "protected_liblcm_calls": [],
            "confidence": "high",
        }
    monkeypatch.setattr(execution_mod, "certify_script_readonly", fake)


class _ProbeCounter:
    def __init__(self, *verdicts):
        self.accesses = list(verdicts)
        self.calls = 0

    def __call__(self, name):
        self.calls += 1
        idx = min(self.calls - 1, len(self.accesses) - 1)
        return self.accesses[idx]


def _probe(monkeypatch, *accesses):
    counter = _ProbeCounter(*accesses)
    monkeypatch.setattr(project_access, "probe_project_access", counter)
    return counter


def _run(code, project_name="TestProj_excl_gate", **overrides):
    args = {
        "code": code,
        "project_name": project_name,
        "write_enabled": True,
        "confirmed": True,
        "skip_api_check": True,
        "skip_module_check": True,
    }
    args.update(overrides)
    return _parse(asyncio.run(execution_mod.handle_run_module(args)))


def _setup(monkeypatch, tmp_path, *, is_cud=True):
    _stub_env(monkeypatch, tmp_path, is_cud=is_cud)
    _stub_cert(monkeypatch)
    # With no index the chain check falls back to a static accessor list that
    # predates `project.WritingSystems`; the real index has it.
    monkeypatch.setattr(
        execution_mod, "detect_invalid_project_chains",
        lambda tree, idx: {"has_invalid": False, "issues": []},
    )


# ---------------------------------------------------------------------------
# Scenarios 1.1 / 1.2: refused on open_shared before anything runs
# ---------------------------------------------------------------------------

class TestRefusedWhileShared:
    @pytest.mark.parametrize(
        "code,key",
        [(WS_WRAPPER, "ws.wrapper"), (CF_WRAPPER, "cf.wrapper"), (WS_RAW, "ws.raw.lists")],
        ids=["ws_wrapper", "cf_wrapper", "ws_raw"],
    )
    def test_open_shared_refuses(self, monkeypatch, tmp_path, code, key):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)
        monkeypatch.setattr(
            execution_mod, "perform_pre_write_backup",
            lambda *a, **k: pytest.fail("backup must not run on refusal"),
        )

        data = _run(code)
        assert data["error_code"] == "requires_exclusive_access"
        assert [op["key"] for op in data["operations"]] == [key]
        assert data["verdict"] == "open_shared"
        assert data["holder_pid"] == 68436
        assert data["holder_process"] == "FieldWorks"
        assert "TestProj_excl_gate" in data["message"]
        assert "re-submit" in data["message"]

    def test_message_names_operation_and_reason(self, monkeypatch, tmp_path):
        """FR-008: each matched operation, its reason and failure class."""
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)

        data = _run(CF_WRAPPER)
        assert "CustomFieldOperations.CreateField (line 2)" in data["message"]
        assert exclusive_access.ROWS_BY_KEY["cf.wrapper"].reason in data["message"]
        assert data["operations"][0]["failure_class"] == "silently_lost"
        assert data["guidance"] == exclusive_access.REFUSAL_GUIDANCE
        assert "Close FieldWorks" in data["remedy"]

    def test_detail_validates_against_the_model(self, monkeypatch, tmp_path):
        """RequiresExclusiveAccessDetail is extra="forbid"; FR-008 fields."""
        from flextoolsmcp.server.response_models import (
            RejectionEnvelope,
            RequiresExclusiveAccessDetail,
        )

        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)

        data = _run(WS_WRAPPER)
        envelope = RejectionEnvelope.model_validate(data, by_alias=True)
        assert envelope.error_code == "requires_exclusive_access"
        fields = list(RequiresExclusiveAccessDetail.model_fields)
        assert fields == [
            "error_code", "guidance", "verdict", "holder_pid",
            "holder_process", "operations", "remedy", "stage",
        ]
        detail = RequiresExclusiveAccessDetail.model_validate(
            {k: data[k] for k in fields}
        )
        assert detail.operations[0].call == "WritingSystemOperations.Create"

    def test_refused_before_confirmation(self, monkeypatch, tmp_path):
        """confirmed=False on a match: the gate answers, not confirmation."""
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)

        data = _run(WS_WRAPPER, confirmed=False)
        assert data["error_code"] == "requires_exclusive_access"

    def test_uses_the_first_probe_decision(self, monkeypatch, tmp_path):
        """A later re-probe (the own-worker release path) cannot change the
        gate's verdict: it refuses on the first decision, probing once."""
        _setup(monkeypatch, tmp_path)
        counter = _probe(
            monkeypatch,
            _access("open_shared", sharing=True),
            _access("held_by_other", pid=4242, process="python", sharing=True),
        )
        _refuse_execution(monkeypatch)

        async def _no_release(*a, **k):
            raise AssertionError("own-worker release must not run for this gate")

        monkeypatch.setattr(execution_mod, "_release_own_worker_or_refuse", _no_release)

        data = _run(WS_WRAPPER)
        assert data["error_code"] == "requires_exclusive_access"
        assert data["verdict"] == "open_shared"
        assert counter.calls == 1


# ---------------------------------------------------------------------------
# FR-006: unknown
# ---------------------------------------------------------------------------

class TestUnknownVerdict:
    def test_unknown_with_match_refuses(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("unknown", holder=False))
        _refuse_execution(monkeypatch)

        data = _run(WS_WRAPPER)
        assert data["error_code"] == "requires_exclusive_access"
        assert data["verdict"] == "unknown"
        assert "could not be confirmed closed" in data["remedy"]
        assert data["holder_pid"] is None

    def test_unknown_ordinary_write_is_unchanged(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("unknown", holder=False))
        _allow_execution(monkeypatch)

        data = _run(ORDINARY)
        assert data.get("error_code") is None


# ---------------------------------------------------------------------------
# Scenarios 1.3 / 1.4: other verdicts
# ---------------------------------------------------------------------------

class TestOtherVerdicts:
    @pytest.mark.parametrize("verdict", ["free", "stale_lock"])
    def test_not_refused_when_fieldworks_does_not_hold_it(self, monkeypatch, tmp_path, verdict):
        _setup(monkeypatch, tmp_path)
        holder = verdict == "stale_lock"
        _probe(monkeypatch, _access(verdict, pid=999, process="python", holder=holder))
        _allow_execution(monkeypatch)

        data = _run(WS_WRAPPER)
        assert data.get("error_code") is None

    @pytest.mark.parametrize("verdict", ["open_exclusive", "held_by_other"])
    def test_project_locked_wins(self, monkeypatch, tmp_path, verdict):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access(verdict, sharing=False))
        _refuse_execution(monkeypatch)

        data = _run(WS_WRAPPER)
        assert data["error_code"] == "project_locked"
        assert data["verdict"] == verdict

    def test_ordinary_write_on_open_shared_still_proceeds(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _allow_execution(monkeypatch)

        data = _run(ORDINARY)
        assert data.get("error_code") is None
        assert data["shared_mode"]["verdict"] == "open_shared"


# ---------------------------------------------------------------------------
# Scenario 1.5 (FR-005) and 1.8: probe forcing; read-only runs
# ---------------------------------------------------------------------------

class TestProbeForcing:
    def test_certified_readonly_match_forces_the_probe(self, monkeypatch, tmp_path):
        """needs_lock is False (certified read-only, not CUD), but the match
        forces the probe, and the run is refused."""
        _setup(monkeypatch, tmp_path, is_cud=False)
        counter = _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)

        data = _run(WS_RAW)
        assert counter.calls == 1
        assert data["error_code"] == "requires_exclusive_access"

    def test_read_only_run_is_not_gated(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path, is_cud=False)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)

        data = _run(WS_RAW, write_enabled=False, confirmed=False)
        assert data.get("error_code") is None


# ---------------------------------------------------------------------------
# Scenario 1.7 (FR-009): validate_only
# ---------------------------------------------------------------------------

def _validate(code, write_enabled=True):
    return _run(code, validate_only=True, write_enabled=write_enabled)


class TestValidateOnly:
    def test_blocking_on_open_shared(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)

        excl = _validate(WS_RAW)["project_lock"]["exclusive_access"]
        assert excl["required"] is True
        assert excl["blocking"] is True
        assert [op["key"] for op in excl["operations"]] == ["ws.raw.lists"]

    def test_not_blocking_on_free(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("free", holder=False))
        _refuse_execution(monkeypatch)

        excl = _validate(WS_RAW)["project_lock"]["exclusive_access"]
        assert excl["required"] is True
        assert excl["blocking"] is False

    def test_unknown_reports_the_real_refusal(self, monkeypatch, tmp_path):
        """The real run refuses `unknown` (FR-006), so validate_only says so
        (FR-009) rather than the project_lock #118 `null`."""
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("unknown", holder=False))
        _refuse_execution(monkeypatch)

        excl = _validate(WS_RAW)["project_lock"]["exclusive_access"]
        assert excl["blocking"] is True

    def test_probe_unavailable_is_null(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)

        def _raise(name):
            raise OSError("registry unavailable")

        monkeypatch.setattr(project_access, "probe_project_access", _raise)
        _refuse_execution(monkeypatch)

        excl = _validate(WS_RAW)["project_lock"]["exclusive_access"]
        assert excl["required"] is True
        assert excl["blocking"] is None

    def test_read_only_validate_is_not_required(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)

        excl = _validate(WS_RAW, write_enabled=False)["project_lock"]["exclusive_access"]
        assert excl == {"required": False, "operations": [], "blocking": False}


# ---------------------------------------------------------------------------
# Scenario 2.1 (FR-010): the assistance hint
# ---------------------------------------------------------------------------

class TestAssistanceHint:
    def test_hint_exists(self):
        from flextoolsmcp.server.session import _ASSISTANCE_HINTS_BY_ERROR_CODE

        hint = _ASSISTANCE_HINTS_BY_ERROR_CODE["requires_exclusive_access"]
        assert "re-submit" in hint
        assert "do not rewrite" in hint.lower()

    def test_repeated_refusal_gets_the_specific_hint(self, monkeypatch, tmp_path):
        from flextoolsmcp.server.session import _ASSISTANCE_HINTS_BY_ERROR_CODE

        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)
        execution_mod.session_state.reset_op_signals()
        try:
            data = {}
            for _ in range(8):
                data = _run(WS_WRAPPER)
                if "_assistance" in data:
                    break
            assert data["error_code"] == "requires_exclusive_access"
            assert "_assistance" in data
            assert _ASSISTANCE_HINTS_BY_ERROR_CODE["requires_exclusive_access"] in (
                data["_assistance"]["message"]
            )
        finally:
            execution_mod.session_state.reset_op_signals()


# ---------------------------------------------------------------------------
# Conditional WritingSystems.Ensure(): snapshot + runtime peer schema guard
# ---------------------------------------------------------------------------

import json  # noqa: E402

ENSURE_OK = "if modifyAllowed:\n    project.WritingSystems.Ensure('en', 'English', is_vernacular=False)\n"
ENSURE_NEW = "if modifyAllowed:\n    project.WritingSystems.Ensure('qaa-x-new', 'New')\n"
ENSURE_VAR = "tag = 'en'\nif modifyAllowed:\n    project.WritingSystems.Ensure(tag, 'English', False)\n"
ENSURE_MIXED = (
    "if modifyAllowed:\n"
    "    project.WritingSystems.Ensure('en', 'English', is_vernacular=False)\n"
    "    project.WritingSystems.SetFontSize('en', 12)\n"
)
ENSURE_LATE = (
    "if modifyAllowed:\n"
    "    project.LexEntry.SetLexemeForm(entry, 'x')\n"
    "    project.WritingSystems.Ensure('en', 'English', is_vernacular=False)\n"
)


def _row(method, line, cls="WritingSystemOperations"):
    return {"class": cls, "method": method, "line": line, "is_mutating": True,
            "source": "index", "protected": True}


_ROWS.update({
    ENSURE_OK: [_row("Ensure", 2)],
    ENSURE_NEW: [_row("Ensure", 2)],
    ENSURE_VAR: [_row("Ensure", 3)],
    ENSURE_MIXED: [_row("Ensure", 2), _row("SetFontSize", 3)],
    ENSURE_LATE: [_row("SetLexemeForm", 2, cls="LexEntryOperations"), _row("Ensure", 3)],
})

ACTIVE = {"vernacular": ["seh"], "analysis": ["en", "pt"]}


def _stub_snapshot(monkeypatch, active=ACTIVE, guard=True):
    """Stub the two seams plan_conditional reads: the .fwdata active-list
    read (returns `active`; `None` = unreadable) and the guard probe."""
    calls = []

    def fake_read(project_name):
        calls.append(project_name)
        return active

    monkeypatch.setattr(execution_mod, "_read_active_writing_systems", fake_read)
    monkeypatch.setattr(execution_mod, "_peer_schema_guard_available", lambda: guard)
    return calls


def _capture_runner(monkeypatch, *, error=None):
    """run_script_async fake that records the runner's PEER_SCHEMA_GUARD line."""
    seen = {}

    async def fake(path, timeout_seconds):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        seen["text"] = text
        seen["guard"] = next(
            ln for ln in text.splitlines() if ln.startswith("PEER_SCHEMA_GUARD = ")
        )
        payload = {
            "success": error is None,
            "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
            "messages": [],
        }
        if error is not None:
            payload["error"] = error
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
            "stderr": "", "timeout": False, "returncode": 0,
        }

    _allow_execution(monkeypatch)
    monkeypatch.setattr(execution_mod, "run_script_async", fake)
    return seen


class TestConditionalEnsure:
    def test_already_active_runs_with_guard_required(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        snap_calls = _stub_snapshot(monkeypatch)
        seen = _capture_runner(monkeypatch)

        data = _run(ENSURE_OK)
        assert data.get("error_code") is None
        assert snap_calls == ["TestProj_excl_gate"]
        assert seen["guard"] == "PEER_SCHEMA_GUARD = 'required'"
        excl = data["exclusive_access"]
        assert excl["decision"] == "allowed_conditional"
        assert [m["key"] for m in excl["satisfied"]] == ["ws.ensure"]

    def test_would_add_is_refused_before_the_run(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _refuse_execution(monkeypatch)

        data = _run(ENSURE_NEW)
        assert data["error_code"] == "requires_exclusive_access"
        assert data["stage"] == "preflight"
        assert "would add a vernacular writing system" in data["message"]
        assert data["operations"][0]["conditional"] is True

    def test_non_literal_is_deferred_to_the_runtime_guard(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        seen = _capture_runner(monkeypatch)

        data = _run(ENSURE_VAR)
        assert data.get("error_code") is None
        assert seen["guard"] == "PEER_SCHEMA_GUARD = 'required'"
        assert [m["key"] for m in data["exclusive_access"]["deferred_to_runtime"]] == ["ws.ensure"]

    def test_refused_without_the_guard_and_no_file_read(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        read_calls = _stub_snapshot(monkeypatch, guard=False)
        _refuse_execution(monkeypatch)

        data = _run(ENSURE_OK)
        assert data["error_code"] == "requires_exclusive_access"
        assert "no peer schema guard" in data["message"]
        assert read_calls == []  # no point reading without the backstop

    def test_unreadable_file_defers_to_the_guard(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch, active=None)
        seen = _capture_runner(monkeypatch)

        data = _run(ENSURE_NEW)
        assert data.get("error_code") is None
        assert seen["guard"] == "PEER_SCHEMA_GUARD = 'required'"
        assert [m["key"] for m in data["exclusive_access"]["deferred_to_runtime"]] == ["ws.ensure"]

    def test_mixed_with_an_unconditional_call_is_refused_without_reading(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        snap_calls = _stub_snapshot(monkeypatch)
        _refuse_execution(monkeypatch)

        data = _run(ENSURE_MIXED)
        assert data["error_code"] == "requires_exclusive_access"
        assert snap_calls == []
        assert [op["key"] for op in data["operations"]] == ["ws.ensure", "ws.wrapper"]

    def test_free_does_not_read_or_guard(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("free", holder=False))
        snap_calls = _stub_snapshot(monkeypatch)
        seen = _capture_runner(monkeypatch)

        data = _run(ENSURE_NEW)
        assert data.get("error_code") is None
        assert snap_calls == []
        assert seen["guard"] == "PEER_SCHEMA_GUARD = 'off'"

    def test_ensure_after_other_writes_warns(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _capture_runner(monkeypatch)

        data = _run(ENSURE_LATE)
        assert any("Put Ensure() calls first" in w for w in data.get("warnings", []))

    def test_runtime_refusal_maps_to_the_same_code(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _capture_runner(monkeypatch, error=(
            "Execution error: WritingSystems.Ensure('en') needs to change ...\n"
            "Traceback ...\nflexicon.code.exceptions.FP_ExclusiveAccessRequiredError: ..."
        ))

        data = _run(ENSURE_OK)
        assert data["error_code"] == "requires_exclusive_access"
        assert data["stage"] == "runtime"
        assert "already saved" in data["remedy"]
        # Dual envelope (review finding on #343): the flat `message` plus the
        # nested `error` object, carrying the operations and probe facts the
        # contract documents for the preflight refusal.
        assert "WritingSystemOperations.Ensure (line 2)" in data["message"]
        assert data["error"]["code"] == "requires_exclusive_access"
        assert data["error"]["message"] == data["message"]
        assert data["error"]["operations"] == data["operations"]
        assert data["verdict"] == "open_shared"
        assert data["holder_pid"] == 68436
        assert data["holder_process"] == "FieldWorks"
        assert [op["key"] for op in data["operations"]] == ["ws.ensure"]
        assert data["operations"][0]["conditional"] is True
        # Runtime details retained: the raw .NET text and the messages.
        assert "FP_ExclusiveAccessRequiredError" in data["raw_error"]
        assert data["messages"] == []

    def test_runtime_refusal_validates_against_the_models(self, monkeypatch, tmp_path):
        """The published requires_exclusive_access envelope validates from the
        runtime response too (review finding on #343)."""
        from flextoolsmcp.server.response_models import (
            RejectionEnvelope,
            RequiresExclusiveAccessDetail,
        )

        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _capture_runner(monkeypatch, error=(
            "Execution error: WritingSystems.Ensure('en') needs to change ...\n"
            "Traceback ...\nflexicon.code.exceptions.FP_ExclusiveAccessRequiredError: ..."
        ))

        data = _run(ENSURE_OK)
        envelope = RejectionEnvelope.model_validate(data, by_alias=True)
        assert envelope.error_code == "requires_exclusive_access"
        detail = RequiresExclusiveAccessDetail.model_validate(
            {k: data[k] for k in RequiresExclusiveAccessDetail.model_fields}
        )
        assert detail.stage == "runtime"
        assert detail.verdict == "open_shared"
        assert [op.key for op in detail.operations] == ["ws.ensure"]

    def test_guard_unavailable_in_the_run_maps_to_the_same_code(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _capture_runner(monkeypatch, error="Execution error: PeerSchemaGuardUnavailable: ...")

        data = _run(ENSURE_OK)
        assert data["error_code"] == "requires_exclusive_access"
        assert data["stage"] == "runtime"
        assert "was not run" in data["error"]["message"]
        assert data["verdict"] == "open_shared"
        assert [op["key"] for op in data["operations"]] == ["ws.ensure"]


class TestPeerGuardBackstop:
    def test_ordinary_write_on_open_shared_turns_the_guard_on(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        seen = _capture_runner(monkeypatch)

        assert _run(ORDINARY).get("error_code") is None
        assert seen["guard"] == "PEER_SCHEMA_GUARD = 'on'"
        assert "project.SetPeerSchemaGuard(True)" in seen["text"]
        assert "PeerSchemaGuardUnavailable" in seen["text"]

    def test_ordinary_write_on_free_leaves_it_off(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("free", holder=False))
        seen = _capture_runner(monkeypatch)

        assert _run(ORDINARY).get("error_code") is None
        assert seen["guard"] == "PEER_SCHEMA_GUARD = 'off'"


class TestValidateOnlyConditional:
    def test_already_active_does_not_block(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _refuse_execution(monkeypatch)

        excl = _validate(ENSURE_OK)["project_lock"]["exclusive_access"]
        assert excl["required"] is True
        assert excl["conditional"] is True
        assert excl["blocking"] is False
        assert excl["deferred_to_runtime"] == []

    def test_would_add_blocks_with_the_reason(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _refuse_execution(monkeypatch)

        excl = _validate(ENSURE_NEW)["project_lock"]["exclusive_access"]
        assert excl["blocking"] is True
        assert "would add a vernacular writing system" in excl["notes"][0]

    def test_non_literal_is_reported_deferred(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _stub_snapshot(monkeypatch)
        _refuse_execution(monkeypatch)

        excl = _validate(ENSURE_VAR)["project_lock"]["exclusive_access"]
        assert excl["blocking"] is False
        assert [m["key"] for m in excl["deferred_to_runtime"]] == ["ws.ensure"]

    def test_mixed_still_blocks(self, monkeypatch, tmp_path):
        _setup(monkeypatch, tmp_path)
        _probe(monkeypatch, _access("open_shared", sharing=True))
        _refuse_execution(monkeypatch)

        excl = _validate(ENSURE_MIXED)["project_lock"]["exclusive_access"]
        assert excl["blocking"] is True
        assert "conditional" not in excl


# ---------------------------------------------------------------------------
# The active-list read is cached per .fwdata on (size, mtime)
# ---------------------------------------------------------------------------

import os  # noqa: E402

from flextoolsmcp.server import exclusive_access as _ea  # noqa: E402
from flextoolsmcp.server import project_discovery  # noqa: E402

_FWDATA = (
    "<CurVernWss>\n<Uni>seh</Uni>\n</CurVernWss>\n"
    "<CurAnalysisWss>\n<Uni>en pt</Uni>\n</CurAnalysisWss>\n"
)


class TestActiveWritingSystemCache:
    def _setup(self, monkeypatch, tmp_path, text=_FWDATA):
        f = tmp_path / "P.fwdata"
        f.write_text(text, encoding="utf-8")
        monkeypatch.setattr(project_discovery, "get_project_fwdata_path", lambda name: f)
        monkeypatch.setattr(execution_mod, "_ACTIVE_WS_CACHE", {})
        reads = []
        real = _ea.read_active_writing_systems

        def counting(path):
            reads.append(path)
            return real(path)

        monkeypatch.setattr(_ea, "read_active_writing_systems", counting)
        return f, reads

    def test_unchanged_file_is_read_once(self, monkeypatch, tmp_path):
        _, reads = self._setup(monkeypatch, tmp_path)
        first = execution_mod._read_active_writing_systems("P")
        second = execution_mod._read_active_writing_systems("P")
        assert first == second == {"vernacular": ["seh"], "analysis": ["en", "pt"]}
        assert len(reads) == 1

    def test_changed_file_is_read_again(self, monkeypatch, tmp_path):
        """A writing system added in FLEx (or by an MCP run) changes the file;
        the next call must see it, not refuse from a stale entry."""
        f, reads = self._setup(monkeypatch, tmp_path)
        execution_mod._read_active_writing_systems("P")
        f.write_text(_FWDATA.replace("seh</Uni>", "seh qaa-x-new</Uni>"), encoding="utf-8")
        st = f.stat()
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        active = execution_mod._read_active_writing_systems("P")
        assert active["vernacular"] == ["seh", "qaa-x-new"]
        assert len(reads) == 2

    def test_failed_read_is_not_cached(self, monkeypatch, tmp_path):
        f, reads = self._setup(monkeypatch, tmp_path, text="<nothing/>\n")
        assert execution_mod._read_active_writing_systems("P") is None
        assert execution_mod._read_active_writing_systems("P") is None
        assert len(reads) == 2
        assert execution_mod._ACTIVE_WS_CACHE == {}

    def test_missing_fwdata_is_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(project_discovery, "get_project_fwdata_path", lambda name: None)
        monkeypatch.setattr(execution_mod, "_ACTIVE_WS_CACHE", {})
        assert execution_mod._read_active_writing_systems("P") is None
