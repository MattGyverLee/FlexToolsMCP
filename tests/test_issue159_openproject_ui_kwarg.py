#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #159 -- `FLExProject.OpenProject()` rejects the `ui=` kwarg on older
Flexicon builds (a session's very first operation fails outright).

Root cause: the MCP's generated runners assumed a Flexicon `OpenProject()`
signature of `(..., ui=None)` (flexicon >=4.4.0). A stray older build in the
subprocess venv (e.g. 4.3.x, whose `OpenProject()` has no `ui` parameter)
raises `TypeError: OpenProject() got an unexpected keyword argument 'ui'`
before the session ever touches the project.

Fix: probe the INSTALLED ``OpenProject`` signature *in the subprocess that is
about to call it* (a server-side probe would describe the server's flexicon,
not the worker's), and omit `ui=` with a visible WARNING when the parameter is
absent. The same probe-and-degrade pattern is now applied at all three call
sites:

- the `handle_run_module` generated runner (session bootstrap),
- the T030 scan-seam runner (`_build_scan_script` / `run_scan`),
- the parse worker's `_RealBackend.open()` (`worker_main.py`).

This suite proves the degrade path at every site, live-FLEx-free:

- ``TestRunModuleGeneratedScript`` / ``TestScanSeamGeneratedScript`` /
  ``TestParseWorkerSource``: source-level shape of the *actual* generated
  runner text (and the worker's backend) -- the probe is present and the
  no-``ui`` fallback exists with an explicit issue-#159 warning.
- ``TestRunModuleRuntime``: EXECUTES the captured `handle_run_module` runner
  as a real subprocess against two fake `flexicon` packages -- one whose
  ``OpenProject`` accepts ``ui=None`` (>=4.4.0 behaviour) and one whose
  signature has no ``ui`` parameter at all (4.3.x behaviour, where merely
  passing `ui=` is a ``TypeError``). On the old build the run must still
  SUCCEED, must NOT pass ``ui=`` (a regression to the unguarded form fails
  the subprocess with the exact issue-#159 error), and must surface the
  degradation as a WARNING.

No FieldWorks, no live project, no casting gate (#40/#97) -- scoped to the
issue-#159 version-skew fix only.
"""

import ast
import asyncio
import json
import os
import re
import subprocess
import sys
import textwrap


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
        "project_name": "TestProj_159",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
    }
    result = asyncio.run(execution_mod.handle_run_module(args))
    _parse(result)  # sanity: must be valid JSON response
    assert "script" in captured, "run_script_async was never invoked -- gate rejected before generation"
    return captured["script"]


# ---------------------------------------------------------------------------
# Source-level shape: all three call sites carry the probe + degrade path.
# ---------------------------------------------------------------------------

class TestRunModuleGeneratedScript:
    """The `handle_run_module` runner must probe the installed signature and
    keep a no-`ui` fallback open call that warns about issue #159."""

    def test_generated_script_is_valid_python(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path)
        ast.parse(script)  # must not raise

    def test_probes_installed_openproject_signature(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path)
        assert "inspect.signature(FLExProject.OpenProject).parameters" in script
        assert '_openproject_accepts_ui = "ui" in inspect.signature' in script

    @staticmethod
    def _openproject_calls(script):
        """All `FLExProject.OpenProject(...)` call keyword-arg names in the runner."""
        tree = ast.parse(script)
        opens = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (
                getattr(node.func, "attr", None) == "OpenProject"
            ):
                opens.append({kw.arg for kw in node.keywords if kw.arg is not None})
        assert opens, "no OpenProject() call found in runner"
        return opens

    def test_ui_branch_and_no_ui_fallback_both_present(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path)
        # >=4.4.0 branch passes ui through; the fallback branch omits it.
        calls = self._openproject_calls(script)
        assert any("ui" in kw for kw in calls), ">=4.4.0 ui= passthrough missing"
        assert any("ui" not in kw for kw in calls), "no-`ui` fallback call missing"
        # The fallback must be the exact issue-#159 degrade: visible warning
        # plus comment, and the no-ui call must still be guarded by the
        # same outer try (a TypeError is caught, not swallowed).
        assert "issue #159" in script
        assert "report.Warning(" in script.split("else:", 1)[1]
        assert "except Exception as e:" in script.split("else:", 1)[1]


def _openproject_call_kwargs(src):
    """Set of `OpenProject(...)` keyword-arg name-sets appearing in `src`.

    AST-based so string-shaped `ui=` text inside comments/warnings can never
    trip the assertions -- the point is which keywords are PASSED, not which
    words appear in the degrade message."""
    tree = ast.parse(src)
    sets = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "OpenProject":
                sets.append({kw.arg for kw in node.keywords if kw.arg is not None})
    return sets


class TestScanSeamGeneratedScript:
    """The T030 scan runner (`_build_scan_script`) gets the same treatment."""

    def _scan_script(self):
        return execution_mod._build_scan_script(
            module_import_path="flextoolsmcp.server.scan.does_not_exist",
            function_name="run_grammar_scan",
            project_name="TestProj_159",
            write_enabled=False,
        )

    def test_scan_script_is_valid_python(self):
        ast.parse(self._scan_script())

    def test_scan_script_probes_openproject_signature(self):
        script = self._scan_script()
        assert "_openproject_accepts_ui" in script
        assert 'inspect.signature(FLExProject.OpenProject)' in script

    def test_scan_script_has_no_ui_fallback_with_warning(self):
        script = self._scan_script()
        calls = _openproject_call_kwargs(script)
        assert any("ui" in kw for kw in calls), ">=4.4.0 ui= passthrough missing"
        assert any("ui" not in kw for kw in calls), "no-`ui` fallback call missing"
        assert "issue #159" in script
        assert "report.Warning(" in script.split("else:", 1)[1]


class TestParseWorkerSource:
    """The parse worker's `_RealBackend.open()` must stay in step -- it is
    the third OpenProject call site and cannot be imported server-side (see
    worker_main.py's header), so this asserts on its own source text."""

    def test_backend_open_probes_and_falls_back(self):
        src_path = os.path.join(
            os.path.dirname(execution_mod.__file__),
            "..", "parse", "worker_main.py",
        )
        with open(src_path, encoding="utf-8-sig", errors="replace") as f:
            source = f.read()

        # Narrow to the `_RealBackend.open` method body so a stray `else` /
        # OpenProject elsewhere in the 1600-line module can't pollute the check.
        tree = ast.parse(source)
        open_method = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name != "_RealBackend":
                continue
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "open":
                    open_method = m
        assert open_method is not None, "_RealBackend.open not found"
        method_src = ast.get_source_segment(source, open_method)

        # The probe must live inside this method, in the subprocess that is
        # about to call OpenProject (never a server-side assumption).
        assert '"ui" in inspect.signature(FLExProject.OpenProject).parameters' in method_src

        # Both branches present: with ui (>=4.4.0) and without (older flexicon
        # reports the degradation visibly rather than TypeError-ing).
        calls = _openproject_call_kwargs(method_src)
        assert any("ui" in kw for kw in calls), ">=4.4.0 ui= passthrough missing"
        assert any("ui" not in kw for kw in calls), "no-`ui` fallback call missing"
        assert "issue #159" in method_src
        assert "report" in method_src or "_log(" in method_src


# ---------------------------------------------------------------------------
# Runtime: execute the captured run_module runner against old vs new flexicon.
# ---------------------------------------------------------------------------

# >=4.4.0 shape: OpenProject accepts `ui=None`.
_NEW_FLEXICON_INIT = textwrap.dedent(
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
                        "ui_passed": True,
                        "ui_type": type(ui).__name__ if ui is not None else None,
                    }, f)

        def CloseProject(self):
            pass
    """
)

# 4.3.x shape: OpenProject has NO `ui` parameter. Passing ui= is a TypeError,
# byte-for-byte the issue-#159 failure. A regression to the unguarded call
# therefore fails the subprocess instead of silently passing.
_OLD_FLEXICON_INIT = textwrap.dedent(
    """
    import os


    def FLExInitialize():
        pass


    def FLExCleanup():
        pass


    class FLExProject:
        def OpenProject(self, projectName=None, writeEnabled=False, undoable=True):
            capture_path = os.environ.get("FAKE_FLEXICON_CAPTURE_PATH")
            if capture_path:
                import json
                with open(capture_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "projectName": projectName,
                        "writeEnabled": writeEnabled,
                        "undoable": undoable,
                        "ui_passed": False,
                    }, f)

        def CloseProject(self):
            pass
    """
)

# `inspect.signature` must be able to read the fake's OpenProject; plain
# Python methods are always introspectable, which is the point of the probe.
# Deliberately NOT a C# bound method that would make inspect fail (the
# broad `except Exception` fallback is covered by the source-level tests).

_FAKE_HEADLESS_UI = textwrap.dedent(
    """
    class HeadlessLcmUI:
        def __init__(self, *a, **k):
            pass
    """
)


def _write_fake_flexicon(root, *, openproject_init):
    pkg = root / "flexicon"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(openproject_init, encoding="utf-8")
    code_pkg = pkg / "code"
    code_pkg.mkdir(exist_ok=True)
    (code_pkg / "__init__.py").write_text("", encoding="utf-8")
    (code_pkg / "headless_ui.py").write_text(_FAKE_HEADLESS_UI, encoding="utf-8")


def _run_script(script_path, fake_root, *, capture_path=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(fake_root) + os.pathsep + env.get("PYTHONPATH", "")
    if capture_path:
        env["FAKE_FLEXICON_CAPTURE_PATH"] = str(capture_path)
    else:
        env.pop("FAKE_FLEXICON_CAPTURE_PATH", None)
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True, text=True, env=env, timeout=30,
    )
    marker = "===FLEXTOOLS_RESULT_JSON==="
    assert marker in proc.stdout, f"no result marker in stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    payload = json.loads(proc.stdout.split(marker, 1)[1])
    return payload


class TestRunModuleRuntime:
    def test_new_flexicon_still_passes_ui_kwarg(self, monkeypatch, tmp_path):
        """>=4.4.0 regression lock: the ui= passthrough must survive."""
        script = _capture_generated_script(monkeypatch, tmp_path)
        script_path = tmp_path / "runner.py"
        script_path.write_text(script, encoding="utf-8")
        _write_fake_flexicon(tmp_path / "new_pkgs", openproject_init=_NEW_FLEXICON_INIT)
        capture_path = tmp_path / "capture.json"

        payload = _run_script(
            script_path, tmp_path / "new_pkgs", capture_path=capture_path,
        )
        assert payload["success"] is True
        assert payload["error"] is None

        captured = json.loads(capture_path.read_text(encoding="utf-8"))
        assert captured["ui_passed"] is True
        assert captured["ui_type"] == "HeadlessLcmUI"

    def test_old_flexicon_omits_ui_kwarg_and_succeeds(self, monkeypatch, tmp_path):
        """4.3.x regression lock -- the actual issue-#159 scenario: the old
        OpenProject() has no `ui` parameter at all. The run must still
        SUCCEED (probe detects the absence, ui= is omitted, a WARNING names
        the degradation). If the guard is ever reverted, the subprocess
        fails with -- literally -- "got an unexpected keyword argument 'ui'",
        the typecheck in _run_script surfaces the TypeError."""

        script = _capture_generated_script(monkeypatch, tmp_path)
        script_path = tmp_path / "runner.py"
        script_path.write_text(script, encoding="utf-8")
        _write_fake_flexicon(tmp_path / "old_pkgs", openproject_init=_OLD_FLEXICON_INIT)
        capture_path = tmp_path / "capture.json"

        payload = _run_script(
            script_path, tmp_path / "old_pkgs", capture_path=capture_path,
        )
        assert payload["success"] is True, payload.get("error")
        assert payload["error"] is None
        assert "got an unexpected keyword argument" not in json.dumps(payload)

        captured = json.loads(capture_path.read_text(encoding="utf-8"))
        assert captured["ui_passed"] is False
        assert captured["projectName"] == "TestProj_159"

        warnings = [m for m in payload["messages"] if m.get("type") == "WARNING"]
        assert warnings, f"expected a visible issue-#159 warning, got: {payload['messages']}"
        assert any("issue #159" in w["message"] for w in warnings)

    def test_scan_seam_survives_old_flexicon(self, tmp_path, monkeypatch):
        """The T030 scan runner executes its own OpenProject; run the actual
        script against the old flexicon to prove the scan seam also survives
        without ui=. The scan module itself is faked via PYTHONPATH."""
        script = execution_mod._build_scan_script(
            module_import_path="fake_scan_module",
            function_name="scan_now",
            project_name="TestProj_159",
            write_enabled=False,
        )
        script_path = tmp_path / "scan_runner.py"
        script_path.write_text(script, encoding="utf-8")
        _write_fake_flexicon(tmp_path / "old_pkgs", openproject_init=_OLD_FLEXICON_INIT)

        fake_mod = tmp_path / "old_pkgs" / "fake_scan_module.py"
        fake_mod.write_text(
            "def scan_now(project):\n    return {'checked': True}\n",
            encoding="utf-8",
        )

        env = dict(os.environ)
        env["PYTHONPATH"] = str(tmp_path / "old_pkgs") + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True, text=True, env=env, timeout=30,
        )

        assert "===FLEXTOOLS_RESULT_JSON===" in proc.stdout, (
            f"no result marker: {proc.stdout!r}\nstderr: {proc.stderr!r}"
        )
        envelope = json.loads(proc.stdout.split("===FLEXTOOLS_RESULT_JSON===", 1)[1])
        assert envelope["success"] is True, envelope
        # The degrade warning must be visible in the scan's own report.
        assert any(
            m.get("type") == "WARNING" and "issue #159" in m.get("message", "")
            for m in envelope["messages"]
        ), envelope["messages"]


# ---------------------------------------------------------------------------
# Source-level: the fix must stay styled like its neighbours (the repo's
# graceful-degrade-with-visible-warning convention). These are cheap guards
# against the probe silently being replaced by an unconditional `ui=` again.
# ---------------------------------------------------------------------------

class TestDegradeConvention:
    _PROBE_RE = re.compile(r'_openproject_accepts_ui = "ui" in inspect\.signature')

    def test_probe_is_broad_except(self, monkeypatch, tmp_path):
        """The probe must degrade to False on ANY introspection failure
        (uninspectable method, missing flexicon) -- a narrow except could
        reintroduce the crash on the exact odd build the issue is about."""
        script = _capture_generated_script(monkeypatch, tmp_path)
        _m = self._PROBE_RE.search(script)
        assert _m is not None, "probe line missing from generated runner"
        probe_start = _m.start()
        probe = script[probe_start:probe_start + 320]
        assert "except Exception:" in probe
        assert "_openproject_accepts_ui = False" in probe