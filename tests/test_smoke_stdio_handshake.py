"""P3: publish smoke stdio MCP handshake script (deferred-issues section 4)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "smoke_stdio_handshake.py"
SRC = REPO_ROOT / "src"


def test_smoke_stdio_handshake_against_run_entry():
    """Drive initialize + tools/list over stdio like publish.yml after wheel install."""
    if not SCRIPT.is_file():
        pytest.skip("smoke script not present")
    env = os.environ.copy()
    src = str(SRC)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            sys.executable,
            "-c",
            "from flextoolsmcp.server import run; run()",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "stdio handshake OK" in proc.stdout
