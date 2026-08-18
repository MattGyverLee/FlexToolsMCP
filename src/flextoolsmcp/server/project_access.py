#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Access probe: is a FieldWorks project free, shared, or exclusively held?

CP2 of the shared-mode-access feature (issue #93). This module is pure
filesystem + stdlib, matching project_discovery.py's documented I/O
constraint:

  Allowed I/O is restricted to:
    - registry read (via project_discovery.get_projects_directory(), read-only)
    - os.listdir / Path.is_file / Path.stat (metadata only, no mtime change)
    - reading the .fwdata.lock JSON and the .plsx XML as plain text

This module never opens a .fwdata file and never touches LCM. It composes a
verdict from three independently-fallible facts:

  1. Does a .fwdata.lock file exist, and if so, what does it claim
     (PID / ProcessName / Timestamp)? -- read_lock_holder()
  2. Is that PID actually alive right now? -- _pid_is_alive()
  3. Does <Project>\\SharedSettings\\LexiconSettings.plsx have
     projectSharing="true"? -- is_project_sharing_enabled()

CP2 is detection-only: nothing here changes any existing gate's behavior.
probe_project_access() is wired into flextools_health(verbose=True) (a
read-only diagnostic) and nowhere else this cycle.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .project_discovery import get_projects_directory, _FWDATA_EXT

# .NET DateTime ticks are 100-nanosecond units since 0001-01-01T00:00:00.
# Palaso.IO.FileLock's Timestamp field is written this way, NOT a Unix
# epoch -- treating it as seconds-since-1970 produces nonsense ages.
_TICKS_EPOCH = datetime(1, 1, 1)

# Windows OpenProcess() access right sufficient just to check the process
# exists -- no handle to memory, threads, or termination rights needed.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_ERROR_ACCESS_DENIED = 5


@dataclass(frozen=True)
class LockHolder:
    """What a .fwdata.lock file claims about who holds it.

    All fields are Optional because an empty or unparseable lock file is a
    real, observed case (see tests/test_startup_lock_sweep.py, which writes
    empty lock files) -- we tolerate it by returning "unknown" fields rather
    than raising or returning None for the whole holder.
    """
    pid: Optional[int]
    process_name: Optional[str]
    timestamp_ticks: Optional[int]


@dataclass(frozen=True)
class ProjectAccess:
    """Composed verdict for one project.

    verdict is one of:
      "free"           -- no .fwdata.lock file present
      "open_shared"    -- lock held by a live FieldWorks process, sharing on
      "open_exclusive" -- lock held by a live FieldWorks process, sharing off
                          (or the holder could not be identified -- see
                          probe_project_access()'s docstring for the
                          conservative fallback)
      "stale_lock"     -- lock file present but the claimed PID is dead
      "held_by_other"  -- lock held by a live process that is NOT FieldWorks
                          (e.g. a leftover MCP subprocess)
    """
    project_name: str
    verdict: str
    sharing_enabled: Optional[bool]
    holder: Optional[LockHolder]
    lock_age_seconds: Optional[float]


def _lock_path_for(projects_dir, project_name: str) -> Path:
    return Path(projects_dir) / project_name / (project_name + _FWDATA_EXT + ".lock")


def read_lock_holder(project_name: str) -> Optional[LockHolder]:
    """Parse <project>.fwdata.lock's JSON for PID / ProcessName / Timestamp.

    Returns:
        None if no lock file exists at all (nothing to hold).
        A LockHolder with some/all fields None if the file exists but is
        empty, non-JSON, not an object, or missing expected keys -- tolerate
        the file rather than raising. Real lock files also carry a
        "__type": "FileLockContent:#Palaso.IO.FileLock" key that we simply
        ignore (unknown keys are not an error).
    """
    dir_result = get_projects_directory()
    if dir_result is None:
        return None
    projects_dir, _source = dir_result
    lock_path = _lock_path_for(projects_dir, project_name)
    if not lock_path.is_file():
        return None

    try:
        raw = lock_path.read_text(encoding="utf-8-sig")
    except OSError:
        return LockHolder(pid=None, process_name=None, timestamp_ticks=None)

    raw = raw.strip()
    if not raw:
        return LockHolder(pid=None, process_name=None, timestamp_ticks=None)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return LockHolder(pid=None, process_name=None, timestamp_ticks=None)

    if not isinstance(data, dict):
        return LockHolder(pid=None, process_name=None, timestamp_ticks=None)

    pid = data.get("PID")
    if not isinstance(pid, int) or isinstance(pid, bool):
        pid = None

    process_name = data.get("ProcessName")
    if not isinstance(process_name, str):
        process_name = None

    timestamp_ticks = data.get("Timestamp")
    if not isinstance(timestamp_ticks, int) or isinstance(timestamp_ticks, bool):
        timestamp_ticks = None

    return LockHolder(pid=pid, process_name=process_name, timestamp_ticks=timestamp_ticks)


def _pid_is_alive(pid: Optional[int]) -> bool:
    """Is this PID a currently-running process? stdlib only -- no psutil.

    subprocess_helpers.py:29 records the deliberate decision to keep psutil
    out of runtime deps; adding it here would undo that.
    """
    if pid is None or pid <= 0:
        return False

    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        # OpenProcess failing with "access denied" still means the process
        # exists (we just can't query it, e.g. a higher-privilege process);
        # any other error (invalid parameter, etc.) means no such PID. Call
        # GetLastError() directly rather than ctypes.get_last_error(), which
        # only tracks errors from calls made with use_last_error=True.
        err = kernel32.GetLastError()
        return err == _ERROR_ACCESS_DENIED

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, we just can't signal it
    except OSError:
        return False
    return True


def _ticks_to_age_seconds(ticks: Optional[int]) -> Optional[float]:
    """Convert a .NET DateTime.Ticks value to an age in seconds (now - ticks).

    Returns None if ticks is missing or out of any sane datetime range
    (garbage Timestamp) -- callers must not assume a naive epoch.
    """
    if ticks is None:
        return None
    try:
        ticks = int(ticks)
        stamp = _TICKS_EPOCH + timedelta(microseconds=ticks / 10)
        return (datetime.now() - stamp).total_seconds()
    except (OverflowError, ValueError, TypeError, OSError):
        return None


def is_project_sharing_enabled(project_name: str) -> Optional[bool]:
    """Parse the root projectSharing attribute of LexiconSettings.plsx.

    Returns:
        True/False if the file parses and the attribute is readable.
        False if the file is simply missing (sharing was never turned on).
        None if the projects directory can't be resolved, or the file
        exists but is unreadable/malformed -- fail open, we genuinely don't
        know.
    """
    dir_result = get_projects_directory()
    if dir_result is None:
        return None
    projects_dir, _source = dir_result
    plsx_path = Path(projects_dir) / project_name / "SharedSettings" / "LexiconSettings.plsx"
    if not plsx_path.is_file():
        return False

    try:
        root = ET.parse(plsx_path).getroot()
    except (ET.ParseError, OSError):
        return None

    value = root.get("projectSharing")
    if value is None:
        return False
    return value.strip().lower() == "true"


def _is_fieldworks_process_name(process_name: Optional[str]) -> bool:
    return process_name is not None and process_name.strip().casefold() == "fieldworks"


def probe_project_access(project_name: str) -> ProjectAccess:
    """Compose lock + liveness + sharing into one access verdict.

    Verdict decision table (once a lock file is confirmed to exist):

        pid_alive | ProcessName == "FieldWorks" | sharing_enabled | verdict
        ----------|------------------------------|-----------------|------------------
        False     | (either)                     | (either)        | stale_lock
        True      | yes                          | True            | open_shared
        True      | yes                          | False/None      | open_exclusive
        True      | no                            | (either)        | held_by_other
        unknown   | (either)                      | (either)        | open_exclusive

    "unknown" is the empty/malformed-lock case (no parseable PID): we
    cannot verify liveness or identity, so we fall back to the pre-CP2
    behavior of treating any existing lock file as exclusively held,
    rather than risk declaring a genuinely-locked project free. A dead PID
    always wins over "who was it" -- Section 1 fact 4's Target example
    (PID belonging to a leftover python subprocess, not FieldWorks) is
    stale_lock, not held_by_other, precisely because the process is dead.

    No lock file at all -> "free", regardless of sharing_enabled (nothing
    to share access to).
    """
    dir_result = get_projects_directory()
    if dir_result is None:
        return ProjectAccess(
            project_name=project_name,
            verdict="free",
            sharing_enabled=None,
            holder=None,
            lock_age_seconds=None,
        )

    projects_dir, _source = dir_result
    lock_path = _lock_path_for(projects_dir, project_name)
    sharing_enabled = is_project_sharing_enabled(project_name)

    if not lock_path.is_file():
        return ProjectAccess(
            project_name=project_name,
            verdict="free",
            sharing_enabled=sharing_enabled,
            holder=None,
            lock_age_seconds=None,
        )

    holder = read_lock_holder(project_name)
    lock_age_seconds = _ticks_to_age_seconds(holder.timestamp_ticks if holder else None)

    pid_alive: Optional[bool] = None
    if holder is not None and holder.pid is not None:
        pid_alive = _pid_is_alive(holder.pid)

    if pid_alive is False:
        verdict = "stale_lock"
    elif pid_alive is True:
        if _is_fieldworks_process_name(holder.process_name if holder else None):
            verdict = "open_shared" if sharing_enabled else "open_exclusive"
        else:
            verdict = "held_by_other"
    else:
        verdict = "open_exclusive"

    return ProjectAccess(
        project_name=project_name,
        verdict=verdict,
        sharing_enabled=sharing_enabled,
        holder=holder,
        lock_age_seconds=lock_age_seconds,
    )
