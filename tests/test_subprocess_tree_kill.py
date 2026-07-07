#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression test for issue #57 (B): timeout kills the full process tree.

On Windows, process.kill() terminates only the immediate child.  If the child
spawns grandchildren (e.g. pythonnet / FLExInit holding a .fwdata lock),
those grandchildren become orphans and keep the project locked indefinitely.

This test verifies that after a timeout the target file (held open by a
grandchild helper script) is accessible again (openable for writing and
deletable), which proves the entire tree was terminated.

The grandchild helper opens a temp file and blocks indefinitely.  The parent
script spawns the grandchild and also blocks.  run_script_async() must kill
both within its timeout so the file is released.

Skipped on non-Windows because the Windows-specific taskkill path is the
subject of the regression; POSIX coverage is provided by the POSIX branch in
_kill_process_tree() (os.killpg), which is exercised indirectly.
"""

import asyncio
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

# Only meaningful on Windows where the original bug manifested.
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="taskkill process-tree kill only applies on Windows",
)


# ---------------------------------------------------------------------------
# Helper script bodies written to temp files at test time
# ---------------------------------------------------------------------------

# The grandchild: open the lock file for writing and block until killed.
_GRANDCHILD_BODY = textwrap.dedent("""\
    import sys
    import time

    lock_path = sys.argv[1]
    # Open the file exclusively (write mode) to simulate a file-lock holder.
    fh = open(lock_path, "w")
    fh.write("locked\\n")
    fh.flush()
    # Block indefinitely -- we expect to be killed by the parent's killer.
    while True:
        time.sleep(1)
""")

# The parent: spawn the grandchild as a subprocess, then block.
_PARENT_BODY_TEMPLATE = textwrap.dedent("""\
    import subprocess
    import sys
    import time

    grandchild_script = sys.argv[1]
    lock_path = sys.argv[2]

    # Spawn grandchild; it opens lock_path and blocks.
    proc = subprocess.Popen(
        [sys.executable, grandchild_script, lock_path],
    )
    # Block indefinitely -- we expect to be killed along with the grandchild.
    while True:
        time.sleep(1)
""")


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_timeout_kills_grandchild_releasing_file():
    """After a timeout, the file held by a grandchild is accessible.

    Scenario:
      run_script_async(parent.py, timeout=3)
        -> parent.py spawns grandchild.py which opens lock_file
      After timeout, _kill_process_tree must terminate both processes
        -> lock_file must be openable for writing and deletable.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        grandchild_script = tmpdir_path / "grandchild.py"
        parent_script = tmpdir_path / "parent.py"
        lock_file = tmpdir_path / "project.fwdata.lock"

        grandchild_script.write_text(_GRANDCHILD_BODY, encoding="utf-8")
        parent_script.write_text(_PARENT_BODY_TEMPLATE, encoding="utf-8")

        # Build the parent script with hardcoded paths (simpler than argv passing
        # through run_script_async which only takes a single script path).
        parent_script.write_text(
            textwrap.dedent(f"""\
                import subprocess, sys, time
                proc = subprocess.Popen(
                    [sys.executable, r"{grandchild_script}", r"{lock_file}"],
                )
                while True:
                    time.sleep(1)
            """),
            encoding="utf-8",
        )

        # Import here to ensure conftest has set up the path
        from server.subprocess_helpers import run_script_async

        result = asyncio.run(
            run_script_async(str(parent_script), timeout_seconds=3)
        )

        # run_script_async must have flagged this as a timeout
        assert result["timeout"] is True, (
            f"Expected timeout=True, got: {result}"
        )

        # Give the OS a moment to release file handles
        import time
        time.sleep(0.5)

        # The grandchild held lock_file open.  After the tree kill it must be
        # writable and deletable -- proving the grandchild was terminated.
        try:
            lock_file.write_text("released", encoding="utf-8")
            lock_file.unlink()
        except PermissionError as exc:
            pytest.fail(
                f"lock_file still held after timeout (grandchild orphaned): {exc}"
            )
