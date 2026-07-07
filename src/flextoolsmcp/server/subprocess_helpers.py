#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Async subprocess execution helpers.

Provides non-blocking subprocess execution using asyncio instead of subprocess.run()
which blocks the event loop.
"""

import asyncio
import logging
import os
import subprocess
import sys
from typing import Optional, Dict, Any

_log = logging.getLogger(__name__)


def _kill_process_tree(pid: int) -> None:
    """Kill a process and all of its descendants.

    Issue #57 (B): process.kill() on Windows terminates only the immediate
    child process.  When the script spawns grandchildren (e.g. pythonnet /
    FLExInit holding the .fwdata lock), those grandchildren become orphans and
    keep the project locked indefinitely.

    Strategy chosen: ``taskkill /T /F /PID`` on Windows (no extra deps);
    ``os.killpg`` on POSIX (process group).  psutil is NOT added as a runtime
    dep because neither requirements.txt nor pyproject.toml lists it.

    The function is best-effort: errors are logged at WARNING level but never
    re-raised so that callers always get a clean timeout response.
    """
    if sys.platform == "win32":
        try:
            # /T = terminate whole tree, /F = force, /PID = by process ID.
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("taskkill failed for PID %d: %s", pid, exc)
    else:
        # POSIX: create_subprocess_exec gives us an OS-level child; try to
        # kill the entire process group so grandchildren also receive SIGKILL.
        try:
            os.killpg(os.getpgid(pid), 9)  # 9 = SIGKILL
        except ProcessLookupError:
            pass  # already gone -- fine
        except Exception as exc:  # noqa: BLE001
            _log.warning("killpg failed for PID %d: %s", pid, exc)


async def run_script_async(
    script_path: str,
    timeout_seconds: int = 120,
    env: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Run a Python script asynchronously without blocking the event loop.

    Args:
        script_path: Full path to the Python script to run
        timeout_seconds: Maximum execution time before terminating
        env: Optional environment variables dict

    Returns:
        Dict with keys:
        - returncode: Process exit code
        - stdout: Standard output
        - stderr: Standard error
        - timeout: Whether execution was terminated by timeout

    Raises:
        OSError: If script cannot be executed
    """
    # On POSIX we set start_new_session so the child gets its own process
    # group; that lets _kill_process_tree(pid) reach all grandchildren via
    # os.killpg.  On Windows the kwarg is not accepted, so we omit it.
    extra_kwargs: Dict[str, Any] = {}
    if sys.platform != "win32":
        extra_kwargs["start_new_session"] = True

    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            env=env,
            **extra_kwargs,
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds
            )
            return {
                "returncode": process.returncode,
                "stdout": stdout_data.decode("utf-8", errors="replace"),
                "stderr": stderr_data.decode("utf-8", errors="replace"),
                "timeout": False,
            }
        except asyncio.TimeoutError:
            # Kill the entire process tree (not just the direct child) so that
            # grandchildren spawned by pythonnet / FLExInit cannot hold the
            # .fwdata lock open after we return.  See issue #57 (B).
            pid = process.pid
            _kill_process_tree(pid)
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except Exception:
                pass
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Process terminated after {timeout_seconds} seconds",
                "timeout": True,
            }

    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "timeout": False,
        }
