#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""spawn_module_async must default child env to UTF-8 + parent sys.path (P2)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from flextoolsmcp.server.subprocess_helpers import spawn_module_async


@pytest.mark.asyncio
async def test_spawn_module_async_default_env_propagates_import_path():
    """Omitting `env` must still let the child import flextoolsmcp from sys.path.

    Mirrors the source-checkout case: pytest/conftest adds ``src/`` to
    ``sys.path`` but not to ``os.environ["PYTHONPATH"]``. Parse worker
    tests always passed ``worker_client._child_env()`` explicitly; the
    public ``spawn_module_async`` API did not apply the same default.
    """
    proc = await spawn_module_async(
        "flextoolsmcp.server.parse.worker_main",
        ["--help"],
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()

    # --help exits 0; import failure would exit non-zero with ModuleNotFoundError.
    assert proc.returncode == 0, stderr.decode("utf-8", "replace")


def test_child_process_env_includes_utf8_and_sys_path():
    from flextoolsmcp.server.subprocess_helpers import child_process_env

    env = child_process_env()
    assert env.get("PYTHONUTF8") == "1"
    assert env.get("PYTHONIOENCODING") == "utf-8"
    src_root = str(Path(__file__).resolve().parents[1] / "src")
    path_entries = env.get("PYTHONPATH", "").split(os.pathsep)
    assert src_root in path_entries
