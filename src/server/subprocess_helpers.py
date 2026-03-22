#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Async subprocess execution helpers.

Provides non-blocking subprocess execution using asyncio instead of subprocess.run()
which blocks the event loop.
"""

import asyncio
import sys
from typing import Optional, Dict, Any


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
        asyncio.TimeoutError: If script exceeds timeout_seconds
        OSError: If script cannot be executed
    """
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.DEVNULL,
            env=env,
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
            # Terminate the process if it exceeds timeout
            process.kill()
            try:
                await process.wait()
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
