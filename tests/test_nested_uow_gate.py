#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #92 follow-up: nested-UnitOfWork pre-flight gate.

CP1 (issue #92) hardcoded `undoable=False` at the generated OpenProject()
call on the premise that flexicon's `undoable=True` path opened no
UnitOfWork and every mutating call raised. Issue #144 re-derived that
premise: it is false on flexicon builds advertising the
"per-operation-uow" capability (probed via `_probe_undoable_capability()`
/ the `getattr(flexicon, "CAPABILITIES", frozenset())` gate in
handlers/execution.py). Under `undoable=True` on those builds,
`OpenProject()` opens no session-long envelope BECAUSE each mutation opens
its own named task instead (flexicon's FLExProject.py); nothing raises. On
flexicon <=4.3.0 (no capability token), the legacy path still holds: one
non-undoable UnitOfWork is opened once at OpenProject() and closed once at
CloseProject().

Either way, a script that opens its OWN raw liblcm UnitOfWork on top of
that -- UndoableUnitOfWorkHelper / NonUndoableUnitOfWorkHelper (constructor
or static .Do*() calls), or a bare
IActionHandler.BeginUndoTask()/BeginNonUndoableTask() -- nests a second
task inside whichever one is already open: the runner's session task in
legacy mode, or flexicon's own per-operation task in capable mode. liblcm
does not merge tasks opened this way; the already-open UnitOfWork is
rolled back first (discarding the writes it was holding), before the
second Begin* call throws.

`validators.detect_nested_unit_of_work()` is an AST-based pre-flight
detector (unit-tested directly below); `handlers.execution.handle_run_module`
wires it in as a hard-refuse gate, `nested_unit_of_work`, that fires ONLY on
write-enabled runs and stays construct-based and unconditional regardless
of mode -- a script cannot know at the call site whether it is executing
inside flexicon's per-operation wrapper. Only the user-facing message is
mode-conditional (see TestGateWiring below and handlers/execution.py).

Covers:
- TestDetectNestedUnitOfWork: each raw construct is detected by the
  validator directly (one case per sibling shape).
- TestGateWiring: the gate refuses a write-enabled run containing any of
  those constructs, takes no project lock and spawns no subprocess; an
  ordinary guarded write (no raw UoW construct) is NOT refused; a construct
  appearing only inside a comment or a string literal is NOT refused; a
  read-only run containing the construct is NOT refused (per the write-only
  condition above).
"""

import asyncio
import contextlib
import importlib.abc
import importlib.util
import json
import sys


from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import detect_nested_unit_of_work


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


# ---------------------------------------------------------------------------
# Direct validator coverage -- one case per sibling construct shape.
# ---------------------------------------------------------------------------

class TestDetectNestedUnitOfWork:
    def test_undoable_helper_constructor(self):
        code = (
            "from SIL.LCModel.Infrastructure import UndoableUnitOfWorkHelper\n"
            "h = UndoableUnitOfWorkHelper(action_handler, 'u', 'r')\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any("UndoableUnitOfWorkHelper" in c["construct"] for c in result["constructs"])

    def test_nonundoable_helper_constructor(self):
        code = "h = NonUndoableUnitOfWorkHelper(cache.ActionHandlerAccessor)\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any("NonUndoableUnitOfWorkHelper" in c["construct"] for c in result["constructs"])

    def test_undoable_helper_static_do(self):
        code = (
            "UndoableUnitOfWorkHelper.Do('u', 'r', action_handler, lambda: None)\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "UndoableUnitOfWorkHelper.Do(...)" for c in result["constructs"])

    def test_nonundoable_helper_static_do(self):
        code = "NonUndoableUnitOfWorkHelper.Do(action_handler, lambda: None)\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "NonUndoableUnitOfWorkHelper.Do(...)" for c in result["constructs"])

    def test_raw_begin_undo_task(self):
        code = "project.project.ActionHandlerAccessor.BeginUndoTask('a', 'b')\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "...BeginUndoTask(...)" for c in result["constructs"])

    def test_raw_begin_non_undoable_task(self):
        code = "cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True
        assert any(c["construct"] == "...BeginNonUndoableTask(...)" for c in result["constructs"])

    def test_guard_does_not_suppress_detection(self):
        """An `if modifyAllowed:` guard does not fix the nesting collision --
        the detector must fire regardless of guard state."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if modifyAllowed:\n"
            "        cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is True

    def test_flexicon_undoable_operation_not_flagged(self):
        """project.UndoableOperation()/project.Transaction() are flexicon's own
        nesting-aware wrappers (they ask ActionHandlerAccessor.CurrentDepth
        and join instead of nesting) -- must never false-positive here."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    with project.UndoableOperation('label'):\n"
            "        pass\n"
            "    with project.Transaction('label'):\n"
            "        if modifyAllowed:\n"
            "            project.LexEntry.SetLexemeForm(entry, 'x')\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is False
        assert result["constructs"] == []

    def test_construct_in_comment_not_flagged(self):
        code = (
            "# call UndoableUnitOfWorkHelper.Do(x) or BeginUndoTask() manually\n"
            "# also NonUndoableUnitOfWorkHelper(handler)\n"
            "x = 1\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is False

    def test_construct_in_string_not_flagged(self):
        code = (
            "msg = 'call UndoableUnitOfWorkHelper.Do(x) or BeginUndoTask() manually'\n"
            "msg2 = \"NonUndoableUnitOfWorkHelper(handler)\"\n"
        )
        result = detect_nested_unit_of_work(code)
        assert result["has_nested_uow_risk"] is False


# ---------------------------------------------------------------------------
# Gate wiring inside handle_run_module.
# ---------------------------------------------------------------------------

def _boom_lock(*a, **k):
    raise AssertionError("get_project_write_lock must NOT be called")


def _boom_subprocess(*a, **k):
    raise AssertionError("run_script_async must NOT be called")


def _stub_env(monkeypatch, tmp_path, *, is_cud=True):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
            "confidence": "high",
        },
    )
    monkeypatch.setattr(
        execution_mod, "detect_cud_operations",
        lambda code: {"is_cud": is_cud, "operations": ["CREATE (Create())"] if is_cud else []},
    )
    monkeypatch.setattr(execution_mod, "detect_casting_needs", lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []})


async def _fake_run_script_async_ok(path, timeout_seconds):
    payload = {
        "success": True,
        "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
        "messages": [],
    }
    return {
        "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload),
        "stderr": "",
        "timeout": False,
        "returncode": 0,
    }


class _FakeLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class TestGateWiring:
    def test_raw_uow_construct_refused_write_enabled(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": (
                "if modifyAllowed:\n"
                "    cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
            ),
            "project_name": "TestProj_nested",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "nested_unit_of_work"
        assert "constructs" in data

    def test_helper_constructor_refused_write_enabled(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)

        args = {
            "code": (
                "from SIL.LCModel.Infrastructure import UndoableUnitOfWorkHelper\n"
                "if modifyAllowed:\n"
                "    h = UndoableUnitOfWorkHelper(action_handler, 'u', 'r')\n"
            ),
            "project_name": "TestProj_nested2",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "nested_unit_of_work"

    def test_ordinary_guarded_write_not_refused(self, monkeypatch, tmp_path):
        """A plain guarded write with no raw UoW construct must NOT be refused
        by this gate (no false positive)."""
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
        monkeypatch.setattr(
            execution_mod, "perform_pre_write_backup",
            lambda name, **k: {"path": None, "created": False, "skipped_reason": "backup_before_write=false"},
        )

        args = {
            "code": (
                "if modifyAllowed:\n"
                "    project.LexEntry.SetLexemeForm(entry, 'x')\n"
            ),
            "project_name": "TestProj_plain",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "nested_unit_of_work"
        assert data.get("success") is True

    def test_construct_only_in_comment_not_refused(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", lambda name: _FakeLock())
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)
        monkeypatch.setattr(
            execution_mod, "perform_pre_write_backup",
            lambda name, **k: {"path": None, "created": False, "skipped_reason": "backup_before_write=false"},
        )

        args = {
            "code": (
                "# UndoableUnitOfWorkHelper.Do(x) mentioned only in a comment\n"
                "if modifyAllowed:\n"
                "    project.LexEntry.SetLexemeForm(entry, 'x')\n"
            ),
            "project_name": "TestProj_comment",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "nested_unit_of_work"
        assert data.get("success") is True

    def test_readonly_run_with_construct_not_refused(self, monkeypatch, tmp_path):
        """Per the write-only condition: flexicon's OpenProject() only opens
        a UnitOfWork when writeEnabled=True (FLExProject.py), so a read-only
        run has nothing open to nest into -- the gate must not fire."""
        _stub_env(monkeypatch, tmp_path, is_cud=False)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run_script_async_ok)

        args = {
            "code": "cache.ActionHandlerAccessor.BeginNonUndoableTask()\n",
            "project_name": "TestProj_readonly",
            "write_enabled": False,
            "confirmed": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data.get("error_code") != "nested_unit_of_work"


# ---------------------------------------------------------------------------
# Issue #144: capability probe + mode-conditional rejection message.
# ---------------------------------------------------------------------------

class _FakeFlexiconModuleWithCapability:
    CAPABILITIES = frozenset({"per-operation-uow", "transaction-rollback"})


class _FakeFlexiconModuleWithoutCapability:
    """Simulates flexicon <=4.3.0: no CAPABILITIES attribute at all."""


@contextlib.contextmanager
def _flexicon_import_raises(message, name="flexicon"):
    """Make `import <name>` raise a bare Exception, as a FieldWorks-less host does.

    Not `monkeypatch.setitem(sys.modules, name, None)` -- that yields an
    ImportError, which is the one failure mode these call sites already
    handled. The real hazard is the NON-ImportError: flexicon imports fine
    and then raises out of its own init. Reproduced here with a meta-path
    finder whose loader raises in exec_module, which is where the real
    InitialiseFWGlobals() call lives.
    """
    class _RaisingLoader(importlib.abc.Loader):
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            raise Exception(message)

    class _RaisingFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == name:
                return importlib.util.spec_from_loader(fullname, _RaisingLoader())
            return None

    finder = _RaisingFinder()
    cached = sys.modules.pop(name, None)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop(name, None)
        if cached is not None:
            sys.modules[name] = cached


class TestCapabilityProbe:
    def test_probe_true_when_capability_token_present(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "flexicon", _FakeFlexiconModuleWithCapability())
        assert execution_mod._probe_undoable_capability() is True

    def test_probe_false_on_capability_less_build(self, monkeypatch):
        """Simulated flexicon <=4.3.0 build: CAPABILITIES is undefined, so
        getattr(..., frozenset()) yields an empty set and the probe is
        False -- the legacy floor is preserved byte-for-byte."""
        import sys
        monkeypatch.setitem(sys.modules, "flexicon", _FakeFlexiconModuleWithoutCapability())
        assert execution_mod._probe_undoable_capability() is False

    def test_probe_false_when_flexicon_not_importable(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "flexicon", None)
        assert execution_mod._probe_undoable_capability() is False

    def test_probe_false_when_flexicon_raises_at_import(self, monkeypatch):
        """Installed flexicon, no FieldWorks -- the probe must NOT propagate.

        `import flexicon` runs FLExGlobals.InitialiseFWGlobals() at import
        time, which raises a BARE `Exception` ("64bit FieldWorks 9 not
        found"), not an ImportError. Windows CI is precisely that host:
        pyflexicon is a declared dependency and installs, FieldWorks does
        not exist. While this probe caught only ImportError that exception
        escaped `handle_run_module`, and every write-enabled gate test that
        reached the mode-conditional message died with it -- main was red
        on two tests in this file for that reason alone.

        The probe only picks message wording, so an uninitializable
        flexicon must read as "no capability", never as a traceback.
        """
        with _flexicon_import_raises("64bit FieldWorks 9 not found"):
            assert execution_mod._probe_undoable_capability() is False


class TestApiModeValidationResilience:
    """`_validate_api_mode` reports "unusable here"; it never raises.

    Same root cause as TestCapabilityProbe's import-raises case: flexicon
    and flexlibs both run FieldWorks init at import time and raise a bare
    Exception when FLEx is absent. An installed-but-uninitializable library
    is exactly what this function exists to report, so it has to come back
    as a clean (False, reason) pair.
    """

    def test_flexicon_installed_but_uninitializable_is_a_clean_refusal(self):
        with _flexicon_import_raises("64bit FieldWorks 9 not found"):
            ok, msg = execution_mod._validate_api_mode("flexicon")
        assert ok is False
        assert "not initializable" in msg
        assert "64bit FieldWorks 9 not found" in msg

    def test_flexlibs_installed_but_uninitializable_is_a_clean_refusal(self):
        with _flexicon_import_raises("64bit FieldWorks 9 not found", name="flexlibs"):
            ok, msg = execution_mod._validate_api_mode("flexlibs_stable")
        assert ok is False
        assert "not initializable" in msg

    def test_flexicon_missing_still_reports_not_found(self, monkeypatch):
        """The ImportError branch keeps its own distinct wording."""
        import sys
        monkeypatch.setitem(sys.modules, "flexicon", None)
        ok, msg = execution_mod._validate_api_mode("flexicon")
        assert ok is False
        assert "not found" in msg


class TestModeConditionalMessage:
    """The nested_unit_of_work rejection message text depends on whether
    the installed flexicon build advertises the per-operation-uow
    capability (issue #144) -- the gate itself fires either way."""

    def test_message_is_legacy_variant_when_capability_absent(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)
        monkeypatch.setattr(execution_mod, "_probe_undoable_capability", lambda: False)

        args = {
            "code": (
                "if modifyAllowed:\n"
                "    cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
            ),
            "project_name": "TestProj_nested_legacy_msg",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "nested_unit_of_work"
        assert "already-open non-undoable task" in data["message"]
        assert "per-operation" not in data["message"]

    def test_message_is_capable_variant_when_capability_present(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom_lock)
        monkeypatch.setattr(execution_mod, "run_script_async", _boom_subprocess)
        monkeypatch.setattr(execution_mod, "_probe_undoable_capability", lambda: True)

        args = {
            "code": (
                "if modifyAllowed:\n"
                "    cache.ActionHandlerAccessor.BeginNonUndoableTask()\n"
            ),
            "project_name": "TestProj_nested_capable_msg",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        data = _parse(result)
        assert data["error_code"] == "nested_unit_of_work"
        assert "own named unit of work" in data["message"]
        assert "already-open non-undoable task" not in data["message"]
