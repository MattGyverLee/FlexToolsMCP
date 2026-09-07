#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #96 -- MCP-side halves (A-7, A-8) of the shared-mode read-after-write
staleness bug. This suite does NOT reproduce the staleness itself (that needs
a live FLEx master under human control -- see
specs/swahili-audit-2026-09/reviews/bugfix-cycle1-explore-96.md); it covers
the two adjacent defects that are fully MCP-side and fixable without a live
project:

A-7 (teardown visibility): the generated runner used to set
``result["success"] = True`` BEFORE ``project.CloseProject()`` ran, under a
bare ``finally: ... except: pass``. ``CloseProject()`` is where the commit
actually happens (flexicon ``FLExProject.py`` ``EndNonUndoableTask()`` ->
``UnitOfWorkService.Save()`` -> ``Dispose()``), so a commit failure during
teardown was invisible and the run still reported success.

A-8 (modal-dialog hazard): the generated ``OpenProject(...)`` call passed no
``ui=`` argument, so flexicon supplied the WinForms ``FwLcmUI`` -- whose
``ConflictingSave()`` is a modal dialog with no owner in a headless
subprocess, i.e. an indefinite hang. ``HeadlessLcmUI`` (flexicon
``code/headless_ui.py``) never blocks; it raises ``FP_ConflictingSaveError``
instead, which the A-7 fix now surfaces as a real failure instead of
swallowing it.

Two tiers of coverage, both live-FLEx-free:

- ``TestGeneratedScriptWiring``: captures the ACTUAL generated runner script
  text (via a monkeypatched ``run_script_async`` that reads the temp file
  before returning) and asserts the source-level shape: ``ui=`` is passed to
  ``OpenProject``, the ``HeadlessLcmUI`` import is guarded by
  ``except ImportError`` (graceful degradation, matching this repo's
  existing ``except ImportError`` convention -- see e.g.
  ``server/handlers/admin.py``), and the bare ``except: pass`` that used to
  follow ``project.CloseProject()`` is gone.
- ``TestRunnerScriptRuntime``: actually EXECUTES the captured script as a
  real subprocess against a small fake ``flexicon`` package (no FieldWorks,
  no live project) to prove the runtime behavior: normal close reports
  success with ``ui=HeadlessLcmUI()`` passed through; a raising
  ``CloseProject()`` demotes success to False and surfaces the exception;
  and a missing ``flexicon.code.headless_ui`` module degrades to
  ``ui=None`` while emitting a visible WARNING rather than failing or
  silently doing nothing.

Neither tier touches a live FieldWorks project or the casting gate (#40/#97)
or the #103 hvo gate -- this suite is scoped to A-7/A-8 only.
"""

import ast
import asyncio
import json
import os
import subprocess
import sys
import textwrap

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _stub_env(monkeypatch, tmp_path):
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
        lambda code: {"is_cud": False, "operations": []},
    )
    monkeypatch.setattr(execution_mod, "detect_casting_needs", lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []})


def _capture_generated_script(monkeypatch, tmp_path, code="report.Info('hi')\n"):
    """Drive handle_run_module for real, but intercept run_script_async to
    grab the actual generated runner script text instead of executing it."""
    _stub_env(monkeypatch, tmp_path)
    captured = {}

    async def _capture(path, timeout_seconds):
        with open(path, encoding="utf-8") as f:
            captured["script"] = f.read()
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

    monkeypatch.setattr(execution_mod, "run_script_async", _capture)

    args = {
        "code": code,
        "project_name": "TestProj_96",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
    }
    result = asyncio.run(execution_mod.handle_run_module(args))
    _parse(result)  # sanity: must be valid JSON response
    assert "script" in captured, "run_script_async was never invoked -- gate rejected before generation"
    return captured["script"]


# ---------------------------------------------------------------------------
# Tier 1: the generated script's source-level shape.
# ---------------------------------------------------------------------------

class TestGeneratedScriptWiring:
    def test_generated_script_is_valid_python(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path)
        ast.parse(script)  # must not raise

    def test_openproject_receives_ui_argument(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path)
        assert "OpenProject(projectName=PROJECT_NAME" in script
        assert "ui=_lcm_ui" in script or "ui=" in script.split("OpenProject(projectName=PROJECT_NAME", 1)[1][:200]

    def test_headless_ui_import_is_version_gated(self, monkeypatch, tmp_path):
        """A-8: the import must degrade gracefully (except ImportError), not
        hard-crash the whole run on an older flexicon build."""
        script = _capture_generated_script(monkeypatch, tmp_path)
        assert "from flexicon.code.headless_ui import HeadlessLcmUI" in script
        # It must be guarded, and the guard must be the repo's existing
        # ImportError-degrade convention, not a bare except.
        idx = script.index("from flexicon.code.headless_ui import HeadlessLcmUI")
        preceding = script[max(0, idx - 60):idx]
        assert "try:" in preceding
        following = script[idx:idx + 400]
        assert "except ImportError:" in following
        # The fallback must be visible, not silent.
        assert "report.Warning(" in following

    def test_teardown_no_longer_bare_except_pass(self, monkeypatch, tmp_path):
        """A-7 regression lock: CloseProject()'s exception handler must not
        be a bare `except: pass` that discards a commit failure."""
        script = _capture_generated_script(monkeypatch, tmp_path)
        idx = script.index("project.CloseProject()")
        following = script[idx:idx + 1200]
        assert "except:\n                pass" not in following
        assert "except Exception as e:" in following
        assert "TeardownError" in following


# ---------------------------------------------------------------------------
# Tier 2: actually running the generated script against a fake flexicon.
# ---------------------------------------------------------------------------

_FAKE_FLEXICON_INIT = textwrap.dedent(
    """
    import os


    def FLExInitialize():
        pass


    def FLExCleanup():
        pass


    class FLExProject:
        def OpenProject(self, projectName=None, writeEnabled=False, undoable=True, ui=None):
            capture_path = os.environ.get("FAKE_FLEXICON_CAPTURE_PATH")
            if capture_path:
                import json
                with open(capture_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "projectName": projectName,
                        "writeEnabled": writeEnabled,
                        "undoable": undoable,
                        "ui_is_none": ui is None,
                        "ui_type": type(ui).__name__ if ui is not None else None,
                    }, f)

        def CloseProject(self):
            if os.environ.get("FAKE_FLEXICON_CLOSE_RAISES"):
                raise RuntimeError("simulated ConflictingSave during teardown")
    """
)

_FAKE_HEADLESS_UI = textwrap.dedent(
    """
    class HeadlessLcmUI:
        def __init__(self, *a, **k):
            pass
    """
)


def _write_fake_flexicon(root, *, with_headless_ui):
    pkg = root / "flexicon"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(_FAKE_FLEXICON_INIT, encoding="utf-8")
    code_pkg = pkg / "code"
    code_pkg.mkdir(exist_ok=True)
    (code_pkg / "__init__.py").write_text("", encoding="utf-8")
    if with_headless_ui:
        (code_pkg / "headless_ui.py").write_text(_FAKE_HEADLESS_UI, encoding="utf-8")


def _run_script(script_path, fake_root, *, capture_path=None, close_raises=False):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(fake_root) + os.pathsep + env.get("PYTHONPATH", "")
    if capture_path:
        env["FAKE_FLEXICON_CAPTURE_PATH"] = str(capture_path)
    else:
        env.pop("FAKE_FLEXICON_CAPTURE_PATH", None)
    if close_raises:
        env["FAKE_FLEXICON_CLOSE_RAISES"] = "1"
    else:
        env.pop("FAKE_FLEXICON_CLOSE_RAISES", None)
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True, env=env, timeout=30,
    )
    marker = "===FLEXTOOLS_RESULT_JSON==="
    assert marker in proc.stdout, f"no result marker in stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    payload = json.loads(proc.stdout.split(marker, 1)[1])
    return payload


class TestRunnerScriptRuntime:
    """These tests never touch FieldWorks or a live project -- ``flexicon``
    is a tiny fake package injected via PYTHONPATH, matching flexicon's own
    public shape (``FLExInitialize``/``FLExCleanup``/``FLExProject`` with
    ``OpenProject(..., ui=None)``, ``code.headless_ui.HeadlessLcmUI``)."""

    def test_success_path_passes_headless_ui(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path)
        script_path = tmp_path / "runner.py"
        script_path.write_text(script, encoding="utf-8")
        _write_fake_flexicon(tmp_path / "fake_pkgs", with_headless_ui=True)
        capture_path = tmp_path / "capture.json"

        payload = _run_script(
            script_path, tmp_path / "fake_pkgs", capture_path=capture_path,
        )
        assert payload["success"] is True
        assert payload["error"] is None

        captured = json.loads(capture_path.read_text(encoding="utf-8"))
        assert captured["ui_is_none"] is False
        assert captured["ui_type"] == "HeadlessLcmUI"

    def test_teardown_failure_demotes_success_and_surfaces_error(self, monkeypatch, tmp_path):
        """A-7: CloseProject() raising must flip success to False and put
        the exception on the result, not swallow it."""
        script = _capture_generated_script(monkeypatch, tmp_path)
        script_path = tmp_path / "runner.py"
        script_path.write_text(script, encoding="utf-8")
        _write_fake_flexicon(tmp_path / "fake_pkgs", with_headless_ui=True)

        payload = _run_script(
            script_path, tmp_path / "fake_pkgs", close_raises=True,
        )
        assert payload["success"] is False
        assert payload["error_type"] == "TeardownError"
        assert "simulated ConflictingSave during teardown" in payload["error"]
        assert payload.get("teardown_error", {}).get("type") == "RuntimeError"

    def test_missing_headless_ui_degrades_with_visible_warning(self, monkeypatch, tmp_path):
        """A-8 fallback: an older flexicon build without headless_ui must
        not crash the run -- it falls back to ui=None (historical FwLcmUI
        behavior) and reports the degradation as a WARNING message, not
        silently."""
        script = _capture_generated_script(monkeypatch, tmp_path)
        script_path = tmp_path / "runner.py"
        script_path.write_text(script, encoding="utf-8")
        _write_fake_flexicon(tmp_path / "fake_pkgs", with_headless_ui=False)
        capture_path = tmp_path / "capture.json"

        payload = _run_script(
            script_path, tmp_path / "fake_pkgs", capture_path=capture_path,
        )
        assert payload["success"] is True

        captured = json.loads(capture_path.read_text(encoding="utf-8"))
        assert captured["ui_is_none"] is True

        warnings = [m for m in payload["messages"] if m.get("type") == "WARNING"]
        assert warnings, f"expected a visible fallback warning, got messages: {payload['messages']}"
        assert any("HeadlessLcmUI" in w["message"] and "not available" in w["message"] for w in warnings)


# ---------------------------------------------------------------------------
# Deliverable 3: the runtime_primer's shared-mode read-back rule must be
# truthful -- no promised interval, no retry count.
# ---------------------------------------------------------------------------

class TestRuntimePrimerSharedModeReadBack:
    def test_primer_states_the_rule_without_promising_a_safe_interval(self):
        from flextoolsmcp.server.handlers.admin import RUNTIME_PRIMER

        assert "shared_mode_read_back" in RUNTIME_PRIMER
        entry = RUNTIME_PRIMER["shared_mode_read_back"]
        blob = json.dumps(entry)

        assert (
            "a fresh read-only session under a live FLEx master shows the "
            "last master save, not your write" in blob
        )
        # Must not fabricate a safe waiting interval or retry count -- the
        # cycle-1 investigation proved the window is unbounded.
        for forbidden in ("18 second", "18s", "seconds is safe", "retry up to", "within 30", "within 60"):
            assert forbidden not in blob.lower(), f"primer must not promise an interval: found {forbidden!r}"
