#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Subprocess children must inherit the parent's effective import path.

When the MCP server is started from a source checkout, ``server.py`` puts
``src/`` on ``sys.path`` without necessarily setting ``PYTHONPATH``. Any
``run_script_async`` / parse-worker child that imports ``flextoolsmcp`` must
see the same path or imports fail with a misleading ``ModuleNotFoundError``.
"""

import asyncio
import os
import sys
import textwrap

from server.subprocess_helpers import child_process_env, run_script_async


def test_child_process_env_includes_sys_path_directories():
    env = child_process_env()
    assert env["PYTHONUTF8"] == "1"
    on_path = set(env["PYTHONPATH"].split(os.pathsep))
    for entry in sys.path:
        if entry and os.path.isdir(entry):
            assert entry in on_path


def test_run_script_async_child_can_import_flextoolsmcp(tmp_path):
    """End-to-end: child launched through run_script_async resolves the package."""
    script = tmp_path / "import_probe.py"
    script.write_text(
        textwrap.dedent(
            """\
            import flextoolsmcp
            print("OK:", flextoolsmcp.__name__)
            """
        ),
        encoding="utf-8",
    )
    result = asyncio.run(run_script_async(str(script), timeout_seconds=30))
    assert result["timeout"] is False, result["stderr"]
    assert result["returncode"] == 0, result["stderr"]
    assert "OK: flextoolsmcp" in result["stdout"]
