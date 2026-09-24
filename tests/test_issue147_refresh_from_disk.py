#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #147 -- RefreshFromDisk before CloseProject on write-enabled runs."""

import asyncio
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

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
        execution_mod,
        "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True,
            "mutating_calls": [],
            "unprotected_liblcm_calls": [],
            "confidence": "high",
        },
    )
    monkeypatch.setattr(execution_mod, "detect_cud_operations", lambda code: {"is_cud": False, "operations": []})
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs", lambda code, ci, tree: {"has_casting_issues": False, "casting_issues": []}
    )


def _capture_generated_script(monkeypatch, tmp_path, *, write_enabled=False):
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
        "code": "report.Info('hi')\n",
        "project_name": "TestProj_147",
        "write_enabled": write_enabled,
        "skip_api_check": True,
        "skip_module_check": True,
    }
    asyncio.run(execution_mod.handle_run_module(args))
    assert "script" in captured
    return captured["script"]


class TestGeneratedScriptRefreshFromDisk:
    def test_write_enabled_runner_wires_refresh_before_close(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path, write_enabled=True)
        assert "def _maybe_refresh_from_disk" in script
        assert '"refresh-from-disk"' in script or "'refresh-from-disk'" in script
        assert "_maybe_refresh_from_disk(project)" in script
        idx_refresh = script.index("_maybe_refresh_from_disk(project)")
        idx_close = script.index("project.CloseProject()", idx_refresh)
        assert idx_refresh < idx_close

    def test_read_only_runner_guards_refresh_with_write_enabled(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path, write_enabled=False)
        assert "def _maybe_refresh_from_disk" in script
        assert "if not WRITE_ENABLED" in script


_FAKE_FLEXICON = textwrap.dedent(
    """
    import os

    CAPABILITIES = ("refresh-from-disk", "ui-injection")

    def FLExInitialize():
        pass

    def FLExCleanup():
        pass

    class HeadlessLcmUI:
        pass

    class FLExProject:
        def OpenProject(self, projectName=None, writeEnabled=False, undoable=True, ui=None):
            pass

        def RefreshFromDisk(self):
            path = os.environ.get("FAKE_FLEXICON_EVENTS_PATH")
            if path:
                with open(path, "a", encoding="utf-8") as f:
                    f.write("refresh\\n")

        def CloseProject(self):
            path = os.environ.get("FAKE_FLEXICON_EVENTS_PATH")
            if path:
                with open(path, "a", encoding="utf-8") as f:
                    f.write("close\\n")
    """
)


def _run_captured_script(script: str, fake_root: Path):
    script_path = fake_root / "runner.py"
    script_path.write_text(script, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(fake_root) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    marker = "===FLEXTOOLS_RESULT_JSON==="
    assert marker in proc.stdout, proc.stdout + proc.stderr
    return json.loads(proc.stdout.split(marker, 1)[1])


class TestRunnerRefreshFromDiskRuntime:
    def test_refresh_runs_before_close_on_write_enabled(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path, write_enabled=True)
        fake_pkg = tmp_path / "pkgs"
        pkg = fake_pkg / "flexicon"
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(_FAKE_FLEXICON, encoding="utf-8")
        (pkg / "code").mkdir()
        (pkg / "code" / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "code" / "headless_ui.py").write_text("class HeadlessLcmUI:\n    pass\n", encoding="utf-8")

        events_path = tmp_path / "events.log"
        env_extra = {"FAKE_FLEXICON_EVENTS_PATH": str(events_path)}

        script_path = tmp_path / "runner.py"
        script_path.write_text(script, encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(fake_pkg) + os.pathsep + env.get("PYTHONPATH", "")
        env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        marker = "===FLEXTOOLS_RESULT_JSON==="
        assert marker in proc.stdout, proc.stdout + proc.stderr
        payload = json.loads(proc.stdout.split(marker, 1)[1])
        assert payload["success"] is True
        events = events_path.read_text(encoding="utf-8")
        assert events.index("refresh") < events.index("close")
