#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe FieldWorks project enumeration.

Lists projects WITHOUT opening them. Opening a project loads the LCM cache
and rewrites .fwdata mtimes, which corrupts backup workflows and SIL's
"last edited" UI signals. See P10-Export-FLEx issue #13 for the precedent.

Resolution order for the projects directory:
  1. FW_PROJECTS_DIR env var (developer override)
  2. Windows registry HKLM\\Software\\SIL\\FieldWorks\\9, value ProjectsDir
  3. Default %ProgramData%\\SIL\\FieldWorks\\Projects
  4. Subprocess fallback into flexicon.FLExLCM.GetListOfProjects()

Allowed I/O is restricted to:
  - registry read (read-only)
  - os.listdir (metadata only, no mtime change)
  - os.path.isfile (stat only, no mtime change)
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import difflib
import tempfile
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Mirrors SIL.FieldWorks.Common.FwUtils.FwDirectoryFinder
# (fieldworks/Src/Common/FwUtils/FwDirectoryFinder.cs:45,478 and
# FwRegistryHelper.cs:86,262). SuiteVersion is hardcoded "9" because FW9 has
# been the only shipping major for years; FW10 would need a constant update.
_FW_REGISTRY_KEY = r"Software\SIL\FieldWorks\9"
_FW_REGISTRY_VALUE = "ProjectsDir"
_FW_DEFAULT_SUBDIR = ("SIL", "FieldWorks", "Projects")
_FWDATA_EXT = ".fwdata"

# Short in-process cache. The same MCP session usually calls list_projects()
# multiple times in a row (one user call + one or more fuzzy resolutions);
# 10s absorbs that without lagging on freshly-created projects.
_CACHE_TTL_SECONDS = 10.0

_cache: dict = {
    "names": None,
    "source": None,
    "directory": None,
    "expires_at": 0.0,
}

# Issue #321: stale (acquirable) locks were logged at WARNING on every sweep
# (server startup plus every flextools_health call), burying real warnings
# in operations.log triage. Demoted findings are now logged at INFO at most
# once per (project, lock state) per server process. WARNING is reserved for
# a lock on the active session project that is held by another live process.
# Keyed by (project_name, "live" | "stale") so a lock that transitions from
# stale to live-held still gets logged again under its new state.
_logged_stale_locks: set = set()


@dataclass(frozen=True)
class ResolveResult:
    """Outcome of matching a requested project_name against the real list."""
    resolved: Optional[str]
    suggestions: list
    reason: str  # "exact" | "normalized" | "ambiguous_normalized" | "no_match" | "empty"


def get_projects_directory() -> Optional[tuple]:
    """Resolve the FieldWorks projects directory.

    Returns:
        (path, source) where source is "env" | "registry" | "default", or
        None if the directory could not be located.
    """
    env_override = os.environ.get("FW_PROJECTS_DIR", "").strip()
    if env_override:
        p = Path(env_override)
        if p.is_dir():
            return p, "env"
        # Bogus override: fall through rather than silently masking real config.

    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _FW_REGISTRY_KEY) as key:
                value, _vtype = winreg.QueryValueEx(key, _FW_REGISTRY_VALUE)
                if value:
                    p = Path(value)
                    if p.is_dir():
                        return p, "registry"
        except (OSError, FileNotFoundError):
            pass

        program_data = os.environ.get("ProgramData") or r"C:\ProgramData"
        default = Path(program_data, *_FW_DEFAULT_SUBDIR)
        if default.is_dir():
            return default, "default"

    return None


def _scan_directory(projects_dir: Path) -> list:
    """Return sorted project names under projects_dir.

    Mirrors flexicon.FLExLCM.GetListOfProjects: keep only entries where
    <dir>/<name>/<name>.fwdata exists, to filter ghost directories FW
    leaves behind after project deletion (flexicon Issue #48).
    """
    names = []
    try:
        for entry in os.listdir(projects_dir):
            fwdata = projects_dir / entry / (entry + _FWDATA_EXT)
            if os.path.isfile(fwdata):
                names.append(entry)
    except OSError:
        return []
    return sorted(names)


def _list_via_subprocess(timeout_seconds: int = 30) -> Optional[list]:
    """Last-resort: shell out to flexicon.FLExLCM.GetListOfProjects().

    Only used when registry + default-path discovery fail (rare). Slow
    (5-10s cold pythonnet start), but authoritative -- same enumeration
    FlexTools itself uses. Returns sorted names, or None on failure.
    """
    snippet = (
        "import json, sys\n"
        "try:\n"
        "    from flexicon.FLExLCM import GetListOfProjects\n"
        "    print(json.dumps(sorted(GetListOfProjects())))\n"
        "except Exception as exc:\n"
        "    sys.stderr.write(type(exc).__name__ + ': ' + str(exc))\n"
        "    sys.exit(1)\n"
    )
    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(snippet)
            script_path = f.name

        # Explicit codec on both ends (CP5 pattern audit, sweep 4).
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            return None
        stdout = result.stdout.strip()
        if not stdout:
            return None
        data = json.loads(stdout)
        return data if isinstance(data, list) else None
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        return None
    finally:
        if script_path is not None:
            try:
                os.unlink(script_path)
            except OSError:
                pass


def list_projects(force_refresh: bool = False) -> tuple:
    """List FieldWorks projects.

    Returns:
        (names, source) where source is one of:
        "env" | "registry" | "default" | "subprocess" | "unavailable"

    Safety: never opens any .fwdata file. Cached ~10s in-process.
    """
    now = time.monotonic()
    if not force_refresh and _cache["names"] is not None and _cache["expires_at"] > now:
        return _cache["names"], _cache["source"]

    dir_result = get_projects_directory()
    if dir_result is not None:
        projects_dir, source = dir_result
        names = _scan_directory(projects_dir)
        _cache.update({
            "names": names,
            "source": source,
            "directory": str(projects_dir),
            "expires_at": now + _CACHE_TTL_SECONDS,
        })
        return names, source

    names = _list_via_subprocess()
    if names is not None:
        _cache.update({
            "names": names,
            "source": "subprocess",
            "directory": None,
            "expires_at": now + _CACHE_TTL_SECONDS,
        })
        return names, "subprocess"

    _cache.update({
        "names": [],
        "source": "unavailable",
        "directory": None,
        "expires_at": now + _CACHE_TTL_SECONDS,
    })
    return [], "unavailable"


def get_last_directory() -> Optional[str]:
    """Return the projects directory used by the most recent list_projects()."""
    return _cache.get("directory")


def clear_cache() -> None:
    """Reset the in-process cache. Mainly for tests."""
    _cache.update({"names": None, "source": None, "directory": None, "expires_at": 0.0})


# Issue #311: characters a model wraps a name in when it means "the name"
# rather than typing the name -- markdown code ticks, straight and curly
# quotes. Stripped from the ENDS only; internal content is preserved.
_PROJECT_NAME_WRAPPERS = "`'\"‘’“”"

# Cap on the inlined project list in project_not_found / project_name_required
# payloads (issue #53) so a projects directory with hundreds of entries
# doesn't bloat every rejection.
AVAILABLE_PROJECTS_CAP = 15


def normalize_project_name(value) -> Optional[str]:
    """Normalize a project_name as it arrives from tool arguments (#311).

    Strips surrounding whitespace, quotes and backticks (so "`Sena 3`" ->
    "Sena 3"), leaving internal content untouched. A value with no
    alphanumeric character left (e.g. two backticks, "''", "  ") is not a
    name at all and returns None, so callers treat it exactly like an
    omitted project_name -- i.e. fall back to the session project.
    """
    if value is None:
        return None
    text = str(value).strip(_PROJECT_NAME_WRAPPERS + " \t\r\n\f\v")
    if not any(ch.isalnum() for ch in text):
        return None
    return text


def available_projects_payload() -> dict:
    """The self-healing `available_projects` block (issues #53, #311).

    Uses list_projects() -- directory scan + .fwdata existence only, never
    opens a project. Capped at AVAILABLE_PROJECTS_CAP names plus a
    total_count. Best-effort: discovery failure yields an empty list rather
    than breaking the rejection it decorates. NEVER selects a project.
    """
    try:
        names, _source = list_projects()
    except Exception:
        names = []
    return {
        "available_projects": list(names[:AVAILABLE_PROJECTS_CAP]),
        "total_count": len(names),
    }


_NORMALIZE_WS = re.compile(r"\s+")


def _normalize(s: str) -> str:
    """Strip whitespace and casefold for case/whitespace-insensitive match."""
    return _NORMALIZE_WS.sub("", s).casefold()


def resolve_project_name(requested: str) -> ResolveResult:
    """Match a requested project name against the real list.

    Returns a ResolveResult whose `reason` classifies the match:
      "exact"                  -- the name is exactly correct
      "normalized"             -- case/whitespace-only difference; safe to autocorrect
      "ambiguous_normalized"   -- multiple projects normalize to the same form
      "no_match"               -- bigger difference; caller should show suggestions
      "empty"                  -- requested was empty/None
    """
    if not requested:
        return ResolveResult(None, [], "empty")

    projects, _src = list_projects()
    if not projects:
        # Discovery failed entirely (no Windows, no FW, no subprocess). Pass
        # the name through so the subprocess runner can surface its own
        # error -- we shouldn't block users when our own discovery is broken.
        return ResolveResult(requested, [], "exact")

    if requested in projects:
        return ResolveResult(requested, [], "exact")

    target = _normalize(requested)
    matches = [p for p in projects if _normalize(p) == target]
    if len(matches) == 1:
        return ResolveResult(matches[0], [], "normalized")
    if len(matches) > 1:
        return ResolveResult(None, matches, "ambiguous_normalized")

    suggestions = difflib.get_close_matches(requested, projects, n=5, cutoff=0.6)
    return ResolveResult(None, suggestions, "no_match")


def find_lock_file(project_name: str) -> Optional[Path]:
    """Issue #33: check for a .fwdata.lock file before launching the subprocess.

    Existence check ONLY -- a lock file may be stale or shared. Use
    probe_project_access() for any accessibility decision. (Formerly
    check_project_locked(); renamed in the issue #93 CP6 cleanup because
    that name asserted a conclusion the return value does not support.)

    Returns the Path to the lock file if one exists, else None.
    Requires get_projects_directory() to succeed; if it can't determine the
    directory, returns None (let the subprocess surface its own error).
    """
    dir_result = get_projects_directory()
    if dir_result is None:
        return None
    projects_dir, _ = dir_result
    lock = Path(projects_dir) / project_name / (project_name + _FWDATA_EXT + ".lock")
    return lock if lock.exists() else None


def get_project_fwdata_path(project_name: str) -> Optional[Path]:
    """Issue #55 (Rung 2): resolve the on-disk .fwdata path for a project.

    Returns the Path if it exists, else None. Used by the pre-write backup
    step to locate the file to copy -- never opens it.
    """
    dir_result = get_projects_directory()
    if dir_result is None:
        return None
    projects_dir, _ = dir_result
    fwdata = Path(projects_dir) / project_name / (project_name + _FWDATA_EXT)
    return fwdata if fwdata.is_file() else None


def _describe_lock(project_name: str, lock_path: Path) -> tuple:
    """Build the sweep_stale_locks() warning for one existing lock file.

    Returns (message, holder_alive): holder_alive is True only when the
    lock's claimed PID is confirmed still running. A dead-PID (stale) lock,
    an unknown holder, or a lock whose holder cannot be identified all count
    as NOT alive -- issue #321 demotes exactly those to INFO (once per
    project per process), reserving WARNING for the active session project
    when another live process holds its lock.
    """
    # Local import: project_access imports get_projects_directory/_FWDATA_EXT
    # from this module at module load time, so importing it back at this
    # module's top level would be circular. Deferring the import to call
    # time (after both modules are fully loaded) breaks the cycle.
    from .project_access import (
        read_lock_holder,
        _pid_is_alive,
        _is_fieldworks_process_name,
        is_project_sharing_enabled,
        build_access_remedy,
        ProjectAccess,
    )

    holder = read_lock_holder(project_name)
    try:
        age_seconds = time.time() - lock_path.stat().st_mtime
        age_str = f"{age_seconds / 60:.0f} min" if age_seconds >= 60 else f"{age_seconds:.0f} s"
    except OSError:
        age_str = "unknown age"

    # Issue #321: default to "not a live holder" -- only a PID confirmed
    # running via _pid_is_alive() below flips this to True.
    holder_alive = False

    if holder is not None and holder.pid is not None:
        alive = _pid_is_alive(holder.pid)
        holder_alive = bool(alive)
        holder_desc = f"held by {holder.process_name or 'unknown process'} (PID {holder.pid})"
        status_desc = "still running" if alive else "no longer running (stale)"
        if alive:
            # Issue #93 cycle 7 (P2, lock-site-inventory.md
            # project_discovery.py:344-354): the old wording said
            # "Close FieldWorks" from a live PID alone, without
            # checking whether the holder IS FieldWorks or whether
            # project sharing is on -- wrong for a live non-FieldWorks
            # holder (held_by_other, where closing FieldWorks changes
            # nothing) and wrong for a sharing-enabled FieldWorks
            # holder (open_shared, where the write is expected to
            # succeed without closing anything). Branch on the
            # process name and delegate the held_by_other wording to
            # build_access_remedy() so it can never drift from the
            # CP3/CP4 text.
            if _is_fieldworks_process_name(holder.process_name):
                sharing_enabled = is_project_sharing_enabled(project_name)
                if sharing_enabled:
                    msg = (
                        f"Lock detected: {lock_path} ({age_str} old), {holder_desc}, "
                        f"process {status_desc}. Project sharing is enabled, so "
                        "writes through the shared commit log are expected to "
                        "succeed without closing FieldWorks."
                    )
                else:
                    msg = (
                        f"Lock detected: {lock_path} ({age_str} old), {holder_desc}, "
                        f"process {status_desc}. "
                        "Close FieldWorks (or delete the .lock file only if no FW process is running) "
                        "to allow write operations on this project."
                    )
            else:
                remedy = build_access_remedy(
                    ProjectAccess(
                        project_name=project_name,
                        verdict="held_by_other",
                        sharing_enabled=None,
                        holder=holder,
                        lock_age_seconds=None,
                    )
                )
                msg = (
                    f"Lock detected: {lock_path} ({age_str} old), {holder_desc}, "
                    f"process {status_desc}. {remedy}"
                )
        else:
            # Issue #93 sweep follow-up (see specs/_archive/shared-mode-access/
            # reviews/cycle5-qc.md P1-2): the holder is confirmed dead,
            # so this is a stale lock, not a live collision -- telling
            # the operator to "close FieldWorks" is the exact CP3/CP4
            # wording drift build_lock_diagnosis() exists to prevent
            # (there is nothing running to close). LCM treats a stale
            # lock as acquirable, so no action is required; only
            # mention manual deletion as a last resort.
            msg = (
                f"Lock detected: {lock_path} ({age_str} old), {holder_desc}, "
                f"process {status_desc}. This is a stale lock: LCM treats it "
                "as acquirable, so the next write attempt should succeed "
                "without any action. Delete the .lock file manually only if "
                "writes keep failing and you are certain no FieldWorks "
                "process is running."
            )
    else:
        # Issue #93 cycle 7 (P1, lock-site-inventory.md
        # project_discovery.py:372-377 -- CONFIRMED defect): the lock
        # file is empty/unreadable, so the holder is UNKNOWN, not
        # proven dead. The old wording declared "Stale lock detected"
        # from bare existence -- the exact inversion of
        # probe_project_access's documented fallback (unknown holder
        # -> open_exclusive, erring safe) -- and named FieldWorks
        # specifically when no ProcessName was ever read. Mirrors
        # build_access_remedy()'s unknown-holder branch
        # (project_access.py:250-262) verbatim so the two can never
        # drift apart.
        msg = (
            f"Lock detected: {lock_path} ({age_str} old), but the lock file is "
            "empty or unreadable so the holder could not be identified. "
            "Treating it as exclusively held. If no FieldWorks or python "
            "process is actually running, the lock is stale -- delete it "
            "manually and retry. This server never deletes lock files."
        )

    return msg, holder_alive


def sweep_stale_locks(active_project: Optional[str] = None) -> list:
    """Issue #57 (C); rewritten for issue #93 CP2 (T2.6): scan for
    .fwdata.lock files at server startup and report what's known about
    each holder.

    Log policy (issue #321): only a lock on the active session project
    that is held by another LIVE process is logged at WARNING. Everything
    else -- stale (acquirable) locks, unknown holders, live holders on
    unrelated projects -- is demoted to INFO and emitted at most once per
    (project, lock state) per server process, so repeated sweeps (every
    flextools_health call) no longer spam the log. The returned list still
    carries every finding's message, so the flextools_health response is
    unchanged.

    Args:
        active_project: name of the session's current project (from
            flextools_start), or None when no session project is set yet
            (e.g. at server startup). Compared after
            normalize_project_name() so quoting/whitespace wrappers can't
            defeat the match.

    Design: detection only, no deletion, ever. Previously this could only
    say "a lock file exists, we cannot be certain if it's stale." Now it
    reads the lock's claimed PID/ProcessName (project_access.read_lock_holder)
    and checks liveness (project_access._pid_is_alive), so the warning can
    name the holding process and say whether it is alive -- including the
    case (Section 1 fact 4) where the holder is a dead, non-FieldWorks
    process (e.g. a leftover MCP subprocess), which the old mtime-only
    check could not express at all.

    Returns:
        List of human-readable warning strings (one per lock file found).
        Empty list if no locks found or the projects directory is unavailable.
    """
    import logging
    _sweep_log = logging.getLogger(__name__)

    warnings: list = []
    dir_result = get_projects_directory()
    if dir_result is None:
        return warnings

    projects_dir, _source = dir_result
    try:
        entries = os.listdir(projects_dir)
    except OSError:
        return warnings

    active = normalize_project_name(active_project)

    for project_name in sorted(entries):
        lock_path = Path(projects_dir) / project_name / (project_name + _FWDATA_EXT + ".lock")
        if not lock_path.exists():
            continue

        # Issue #93 CP6 (P3, cycle 7): one malformed lock or an unexpected
        # probe error must not take the whole sweep down with it -- this
        # runs at server startup (an exception there fails startup) and on
        # every flextools_health call. Degrade to a holder-unknown warning.
        try:
            msg, holder_alive = _describe_lock(project_name, lock_path)
        except Exception as exc:  # noqa: BLE001 -- detection only, never fatal
            msg = (
                f"Lock detected: {lock_path}, but inspecting it failed "
                f"({type(exc).__name__}: {exc}). Treating it as exclusively "
                "held. This server never deletes lock files."
            )
            holder_alive = False

        # Issue #321: WARNING only when the lock is on the active session
        # project AND held by another live process. Everything else is
        # demoted to INFO, once per (project, lock state) per process.
        is_active = active is not None and normalize_project_name(project_name) == active
        if holder_alive and is_active:
            _sweep_log.warning("[STARTUP-LOCK-SWEEP] %s", msg)
        else:
            dedup_key = (project_name, "live" if holder_alive else "stale")
            if dedup_key not in _logged_stale_locks:
                _logged_stale_locks.add(dedup_key)
                _sweep_log.info("[STARTUP-LOCK-SWEEP] %s", msg)
        warnings.append(msg)

    return warnings


def resolve_or_explain(project_name: str) -> tuple:
    """Resolve a project_name for handler use.

    Returns:
        (resolved_name, None)   -- usable; caller proceeds with resolved_name
        (None, error_payload)   -- not usable; caller wraps payload in error_response()
        (None, None)            -- empty input; caller handles its own "no project" path

    The input is passed through normalize_project_name() first, so a quoted
    or backticked name resolves and a punctuation-only one counts as empty
    (#311). The error payload always carries `available_projects` /
    `total_count`, even when there are no fuzzy suggestions.
    """
    project_name = normalize_project_name(project_name)
    if not project_name:
        return None, None
    result = resolve_project_name(project_name)
    if result.reason in ("exact", "normalized"):
        return result.resolved, None
    return None, {
        "error_code": "project_not_found",
        "message": f"No project matches '{project_name}'.",
        "suggestions": result.suggestions,
        "reason": result.reason,
        "hint": (
            "project_name must be a plain project name (no quotes or "
            "backticks). Pick one of available_projects, or call "
            "flextools_list_projects, then retry with the exact name."
        ),
        **available_projects_payload(),
    }


def project_not_found_fields(err: dict) -> dict:
    """The error_response() kwargs for a resolve_or_explain() error payload.

    One place for the field list so every handler forwards the same shape
    (suggestions, reason, hint, available_projects, total_count).
    """
    return {
        "suggestions": err.get("suggestions", []),
        "reason": err.get("reason"),
        "hint": err.get("hint"),
        "available_projects": err.get("available_projects", []),
        "total_count": err.get("total_count", 0),
    }
