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

#: Stream buffer ceiling for `spawn_module_async`'s child, in bytes. See
#: the docstring on `spawn_module_async` for why this exists and why it is
#: a ceiling raise rather than a solution: it must comfortably clear a
#: parse worker's `trace_xml` line, which `contracts/tools.md` documents
#: as running to "tens or hundreds of kilobytes" in the normal case, and
#: which broke the worker channel outright at asyncio's 64 KiB default
#: (cycle 5 verification, live on Claude-Swahili's `mtu`).
_STREAM_LIMIT_BYTES = 64 * 1024 * 1024


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


async def spawn_module_async(
    module_import_path: str,
    args: Optional[list] = None,
    env: Optional[Dict[str, str]] = None,
) -> asyncio.subprocess.Process:
    """Launch a **long-lived** child module with pipes held open.

    The long-lived sibling of ``run_script_async``, and deliberately in this
    module rather than in the caller's: it is the same execution mechanism
    (plain CPython via ``sys.executable``, same POSIX ``start_new_session``
    so ``_kill_process_tree`` can reach grandchildren), differing only in
    that the caller keeps talking to the child instead of awaiting one
    result.  Putting it here is what keeps ``_kill_process_tree`` the single
    teardown path for every process this server starts (issue #57); a caller
    rolling its own ``create_subprocess_exec`` would be a second execution
    mechanism with its own, weaker, cleanup story.

    The module is addressed by **dotted import path** (``python -m <path>``),
    the same way ``run_scan_module`` addresses its scan modules.

    Unlike ``run_script_async`` this does NOT wait, time out, or read the
    child's output: lifetime and protocol belong to the caller, which for the
    parse worker is ``server/parse/worker_client.py``.  That caller is
    responsible for calling ``_kill_process_tree(proc.pid)`` on teardown --
    a long-lived pythonnet child holding a ``.fwdata`` lock is exactly the
    known failure issue #57 exists for, and a graceful shutdown request is
    not a substitute for it.

    THE ``limit=`` KWARG IS A CEILING RAISE, NOT A FIX. Without it,
    ``create_subprocess_exec`` gives the child's stdout ``StreamReader``
    asyncio's default 64 KiB buffer. ``worker_client._read_message`` reads
    that stream with ``readline()`` (one JSON object per line), and a parse
    worker's response line carries `trace_xml` inline -- a `TraceWordXml`
    trace that `contracts/tools.md` documents as running to "tens or
    hundreds of kilobytes" in the *normal* case. Any such line past 64 KiB
    makes `readline()` raise `asyncio.LimitOverrunError` ("Separator is not
    found, and chunk exceed the limit"), which `_read_loop` cannot recover
    from -- it kills the whole worker channel, failing every request still
    pending on it, not just the one whose trace was too big. Reproduced
    live on `Claude-Swahili`'s `mtu` (3 analyses, `level='explain'`); see
    `specs/parser-check-cp2b/reviews/cycle5-verification.md`.

    64 MiB gives three orders of magnitude of headroom over the documented
    "hundreds of kilobytes" case -- enough that a legitimately huge trace
    (a highly ambiguous wordform against a large grammar) still gets
    through, while still bounding the memory a single line can claim. It is
    NOT the real fix: the payload still crosses this pipe in full and is
    still held in memory on both ends while it does. The real fix is for
    the worker to write the trace to the run record itself and send only a
    path -- exactly what the server already does on the *other* side of
    this same trace today, in `runner.py:411-418`, just one hop too late.
    An issue is being drafted for that; this raise buys headroom until it
    lands.

    Args:
        module_import_path: dotted path, e.g.
            "flextoolsmcp.server.parse.worker_main".
        args: additional argv passed after the module path.
        env: optional environment for the child.

    Returns:
        The running ``asyncio.subprocess.Process``, with stdin/stdout/stderr
        all piped.

    Raises:
        OSError: if the child cannot be spawned.
    """
    extra_kwargs: Dict[str, Any] = {}
    if sys.platform != "win32":
        extra_kwargs["start_new_session"] = True

    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        module_import_path,
        *(args or []),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        limit=_STREAM_LIMIT_BYTES,
        **extra_kwargs,
    )
