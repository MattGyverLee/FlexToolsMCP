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

        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
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


def check_project_locked(project_name: str) -> Optional[Path]:
    """Issue #33: check for a .fwdata.lock file before launching the subprocess.

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


def resolve_or_explain(project_name: str) -> tuple:
    """Resolve a project_name for handler use.

    Returns:
        (resolved_name, None)   -- usable; caller proceeds with resolved_name
        (None, error_payload)   -- not usable; caller wraps payload in error_response()
        (None, None)            -- empty input; caller handles its own "no project" path
    """
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
            "Call flextools_list_projects to see all available projects, "
            "then retry with the exact name."
        ),
    }
