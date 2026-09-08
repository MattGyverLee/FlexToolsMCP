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

This module is detection-only: it composes facts, and never deletes a lock
file, writes LexiconSettings.plsx, or opens a project. Consumers decide what
to do with a verdict. As of CP4 those consumers are
flextools_health(verbose=True) (a read-only diagnostic), the write gate in
handlers/execution.py (which refuses only on "open_exclusive" and
"held_by_other" -- see build_access_remedy()), and (CP3) the post-hoc
diagnosis of a live LcmFileLockedException/FP_FileLockedError in
_diagnose_project_open_error(), which additionally needs to say something
about "stale_lock" -- see build_lock_diagnosis().
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

    probed: False only when the projects directory itself could not be
    resolved (get_projects_directory() returned None) -- in that case
    verdict is reported as "free" WITHOUT ever inspecting a lock file, a
    known fail-open gap (see specs/shared-mode-access/.crew-handoff.json
    fail_open_ruling). True (the default) means a lock file check actually
    ran, even if the result was "no lock file present". Callers that
    surface `verdict`/`blocking` to a human or machine consumer should
    treat probed=False as "unknown", not as a confirmed "free".
    """
    project_name: str
    verdict: str
    sharing_enabled: Optional[bool]
    holder: Optional[LockHolder]
    lock_age_seconds: Optional[float]
    probed: bool = True


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


ENABLE_SHARING_REMEDY = (
    "FieldWorks has this project open and project sharing is OFF, so LCM took "
    "the .fwdata lock exclusively and no other process can write to it. To let "
    "this server write while you keep FLEx open: in FieldWorks go to File > "
    "Project Management > FieldWorks Project Properties > Sharing tab, tick "
    "\"Share project contents with programs on this computer\", and click OK. "
    "FLEx will ask to reopen the project -- let it, because the flag is read "
    "once when the cache opens (LcmCache.cs:219). Then re-submit this same "
    "call: it re-checks the setting and continues automatically. This server "
    "never writes LexiconSettings.plsx on your behalf."
)


def build_access_remedy(access: "ProjectAccess") -> Optional[str]:
    """The user-actionable next step for a verdict that blocks a write.

    Returns None for verdicts that do not block ("free", "open_shared",
    "stale_lock") -- there is nothing for the user to do. Shared by the CP4
    write gate and (CP3) the post-hoc FP_FileLockedError diagnosis, so the
    two can never drift apart.
    """
    if access.verdict == "open_exclusive":
        if access.holder is None or access.holder.pid is None:
            # The empty/malformed-lock fallback: we could not identify a
            # holder at all, so do not assert that FieldWorks has it.
            return (
                "A .fwdata.lock file is present but unreadable, so the holder "
                "could not be identified. Treating it as exclusively held. If "
                "no FieldWorks or python process is actually running, the lock "
                "is stale -- delete it manually and retry. This server never "
                "deletes lock files."
            )
        return ENABLE_SHARING_REMEDY
    if access.verdict == "held_by_other":
        pid = access.holder.pid if access.holder else None
        name = (access.holder.process_name if access.holder else None) or "unknown"
        return (
            f"The lock is held by a live process that is not FieldWorks: PID "
            f"{pid} ({name}) -- most often a leftover FLExTools/MCP subprocess "
            "from an earlier run. This is a real collision, and enabling "
            "project sharing does not resolve it. Wait for that process to "
            "exit (or end it), then retry."
        )
    return None


def build_lock_diagnosis(access: "ProjectAccess") -> Optional[str]:
    """Full read-only diagnosis text for a live LcmFileLockedException /
    FP_FileLockedError (CP3, issue #93 T3.1-T3.4).

    build_access_remedy() answers a narrower question -- "what blocks a
    WRITE" -- and by design returns None for "free", "open_shared", and
    "stale_lock" because none of those block a write (see CP4's write gate
    at handlers/execution.py:4203-4299, which dispatches on ``access.verdict``
    membership, NOT on "remedy is not None"; confirmed before adding this
    function so widening build_access_remedy itself was ruled out -- doing
    so would have flipped tests/test_shared_mode_write_gate.py::
    TestBuildAccessRemedy::test_non_blocking_verdicts_have_no_remedy, which
    asserts build_access_remedy(...) is None for exactly ["free",
    "open_shared", "stale_lock"]).

    This function answers a broader question -- "why did LCM just refuse
    to open the project at all" -- which a stale lock DOES have an answer
    for. So it covers:

      - "open_exclusive" / "held_by_other": delegates to
        build_access_remedy() so the wording can never drift between CP3
        (this post-hoc diagnosis) and CP4 (the write gate).
      - "stale_lock": new text naming the dead holder PID, since
        build_access_remedy() deliberately has nothing to say here.
      - "free" / "open_shared" / anything else: None. Neither is a state a
        live lock error should be attributed to; callers fall back to
        their own generic hint.
    """
    if access.verdict in ("open_exclusive", "held_by_other"):
        return build_access_remedy(access)
    if access.verdict == "stale_lock":
        pid = access.holder.pid if access.holder else None
        pid_text = f"PID {pid}" if pid is not None else "an unreadable PID"
        return (
            f"A .fwdata.lock file is present naming {pid_text}, but that "
            "process is no longer running, so this is a stale lock, not a "
            "live collision. LCM treats a stale lock as acquirable on the "
            "next attempt, so simply retrying the same call often succeeds "
            "now that the process holding it has exited. This server never "
            "deletes lock files; if retries keep failing, delete "
            f"'{access.project_name}'s .fwdata.lock file manually once you "
            "have confirmed no FieldWorks or python process is actually "
            "running."
        )
    return None


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
        # Fail-open gap (interim patch, issue #93 cycle 7): we cannot
        # resolve the projects directory at all, so nothing was actually
        # probed. verdict="free" here is a placeholder, not a finding --
        # probed=False lets reporting sites tell "confirmed free" apart
        # from "we never looked". Widening this into a real "unknown"
        # verdict is deliberately DEFERRED (see fail_open_ruling); do not
        # expand scope here.
        return ProjectAccess(
            project_name=project_name,
            verdict="free",
            sharing_enabled=None,
            holder=None,
            lock_age_seconds=None,
            probed=False,
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
