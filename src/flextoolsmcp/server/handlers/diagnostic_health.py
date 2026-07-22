#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_health: composed diagnostic snapshot (issue #56).

"Why is this API missing?" and "which versions am I actually running?" were
previously answerable only by reading server logs. This module is pure
COMPOSITION of existing detectors -- it introduces no new detection logic:

- detect_installed_library_version() / detect_liblcm_version_from_disk()
  (server/versioning.py) for installed-vs-index version comparison
- find_versioned_api_file() / find_latest_versioned_api_file()
  (server/versioning.py) for the "exact | fallback_latest | missing" index
  match state (recomputed fresh on every call, so a refresh that happened
  since server startup -- in this process or another -- is reflected; see
  the directory-mtime cache key in versioning.py)
- get_index_dir() / get_log_dir() for filesystem locations
- session_state for the current session snapshot
- sweep_stale_locks() (already collected at startup) for lock warnings
- op_telemetry's JSONL loader for the last-5-operations verbose block
"""

import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps

try:
    from ...response_utils import build_response_with_context
except (ImportError, ValueError):
    from response_utils import build_response_with_context

# session_state / get_log_dir / get_api_index come from the shared helper;
# json_response is also provided but re-imported explicitly for clarity.
json_response, session_state, get_log_dir, get_api_index = safe_import_kernel_deps()

try:
    from ...file_utils import get_index_dir
except (ImportError, ValueError):
    from file_utils import get_index_dir

try:
    from ..versioning import (
        detect_installed_library_version,
        detect_liblcm_version_from_disk,
        locate_liblcm_dll,
        find_versioned_api_file,
        find_latest_versioned_api_file,
        extract_version_string,
    )
except ImportError:
    from server.versioning import (
        detect_installed_library_version,
        detect_liblcm_version_from_disk,
        locate_liblcm_dll,
        find_versioned_api_file,
        find_latest_versioned_api_file,
        extract_version_string,
    )

try:
    from ..project_discovery import check_project_locked
except (ImportError, ValueError):
    from server.project_discovery import check_project_locked

try:
    from . import op_telemetry
except ImportError:
    from server.handlers import op_telemetry


# ============================================================
# Library detection (mirrors server.py's get_installed_*_version() helpers --
# duplicated here rather than imported, since server.py imports the handler
# package and importing back would create a cycle).
# ============================================================

_LIBRARY_SPECS: List[Dict[str, Any]] = [
    {
        "key": "flexicon",
        "display_name": "Flexicon",
        "prefix": "flexicon_api",
        "lib_subdir": "python",
        "detect_kwargs": {"import_path": "flexicon", "package_name": "pyflexicon"},
    },
    {
        "key": "liblcm",
        "display_name": "LibLCM",
        "prefix": "liblcm_api",
        "lib_subdir": "liblcm",
        "detect_kwargs": {"assembly_name": "SIL.LCModel"},
    },
    {
        "key": "flexlibs_stable",
        "display_name": "FlexLibs stable",
        "prefix": "flexlibs_api",
        "lib_subdir": "python",
        "detect_kwargs": {"import_path": "flexlibs", "package_name": "flexlibs"},
    },
]


def _detect_installed_version(spec: Dict[str, Any]) -> Optional[str]:
    """Detect the installed version for one library spec."""
    return detect_installed_library_version(
        spec["display_name"], **spec["detect_kwargs"]
    )


def compute_library_match(
    lib_dir: Path,
    prefix: str,
    installed_version: Optional[str],
) -> Dict[str, Any]:
    """Compute {installed, index_loaded, match} for one library.

    Pure with respect to its inputs (lib_dir contents + installed_version) --
    kept as a standalone function so tests can point it at a fixture
    directory instead of the real index tree.

    match values:
        "exact"           -- a versioned index file matches installed_version exactly
        "fallback_latest" -- no exact match; serving the latest shipped/refreshed index
        "missing"         -- no versioned index file found for this library at all
    """
    index_loaded: Optional[str] = None
    match = "missing"

    if installed_version:
        exact_path = find_versioned_api_file(lib_dir, prefix, installed_version)
        if exact_path is not None:
            index_loaded = installed_version
            match = "exact"

    if match != "exact":
        latest_path = find_latest_versioned_api_file(lib_dir, prefix)
        if latest_path is not None:
            index_loaded = extract_version_string(latest_path.name)
            match = "fallback_latest"
        else:
            match = "missing"

    return {
        "installed": installed_version,
        "index_loaded": index_loaded,
        "match": match,
    }


def _build_libraries_block(index_dir: Path) -> Dict[str, Dict[str, Any]]:
    libraries: Dict[str, Dict[str, Any]] = {}
    for spec in _LIBRARY_SPECS:
        installed_version = _detect_installed_version(spec)
        lib_dir = index_dir / spec["lib_subdir"]
        libraries[spec["key"]] = compute_library_match(lib_dir, spec["prefix"], installed_version)
    return libraries


def _build_fieldworks_block() -> Dict[str, Any]:
    """FieldWorks install detection + on-disk LibLCM version (server.py doesn't
    have this loaded into the CLR until a project is open, so we read the DLL
    off disk -- same approach as the session-header log line)."""
    dll_path = locate_liblcm_dll()
    liblcm_version_on_disk = detect_liblcm_version_from_disk()
    return {
        "install_path": str(dll_path.parent) if dll_path else None,
        "detected": dll_path is not None,
        "liblcm_version_on_disk": liblcm_version_on_disk,
    }


def _read_index_file_meta(path: Path) -> Dict[str, Any]:
    """Read {name, schema, entities} from a versioned API JSON file."""
    meta: Dict[str, Any] = {"name": path.name, "schema": None, "entities": 0}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        meta["schema"] = data.get("_schema") or data.get("schema")
        entities = data.get("entities")
        if isinstance(entities, dict):
            meta["entities"] = len(entities)
        elif isinstance(entities, list):
            meta["entities"] = len(entities)
    except (OSError, json.JSONDecodeError):
        pass
    return meta


def _build_indexes_block(index_dir: Path, libraries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    for spec in _LIBRARY_SPECS:
        lib_status = libraries[spec["key"]]
        if lib_status["match"] == "missing":
            continue
        lib_dir = index_dir / spec["lib_subdir"]
        version = lib_status["index_loaded"]
        path = find_versioned_api_file(lib_dir, spec["prefix"], version) if version else None
        if path is None:
            path = find_latest_versioned_api_file(lib_dir, spec["prefix"])
        if path is not None:
            files.append(_read_index_file_meta(path))

    api_index = get_api_index()
    casting_loaded = bool(api_index and api_index.casting_index)
    navigation_loaded = bool(api_index and api_index.navigation_graph)

    return {
        "dir": str(index_dir),
        "overlay_dir": str(Path.home() / ".flextoolsmcp" / "index"),
        "files": files,
        "casting_index": {
            "loaded": casting_loaded,
            "schema": (api_index.casting_index or {}).get("_schema") if casting_loaded else None,
        },
        "navigation_graph": {
            "loaded": navigation_loaded,
            "schema": (api_index.navigation_graph or {}).get("_schema") if navigation_loaded else None,
        },
    }


def _build_warnings(libraries: Dict[str, Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    for spec in _LIBRARY_SPECS:
        status = libraries[spec["key"]]
        if status["match"] == "fallback_latest" and status["installed"]:
            warnings.append(
                f"Index fallback active: installed {spec['display_name']} "
                f"{status['installed']} has no matching index; using "
                f"{status['index_loaded'] or '?'} (stale). Run refresh with "
                f"'python -m flextoolsmcp.refresh'."
            )
    api_index = get_api_index()
    if api_index is not None:
        warnings.extend(getattr(api_index, "startup_lock_warnings", []) or [])
    return warnings


# ============================================================
# Verbose-only diagnostics
# ============================================================

def _check_flexinit_importable() -> Dict[str, Any]:
    try:
        from flexicon import FLExInitialize  # noqa: F401
        return {"importable": True, "error": None}
    except Exception as exc:
        return {"importable": False, "error": str(exc)}


def _check_pythonnet_available() -> Dict[str, Any]:
    try:
        import clr  # type: ignore  # noqa: F401
        return {"available": True, "error": None}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _build_project_lock_block() -> Dict[str, Any]:
    project_name = session_state.project_name or ""
    if not project_name:
        return {"project": None, "locked": False, "lock_file_path": None}
    lock_path = check_project_locked(project_name)
    return {
        "project": project_name,
        "locked": lock_path is not None,
        "lock_file_path": str(lock_path) if lock_path else None,
    }


def _build_recent_operations(limit: int = 5) -> List[Dict[str, Any]]:
    try:
        log_dir = get_log_dir()
        records = op_telemetry._load_jsonl_records(log_dir)
    except Exception:
        return []
    recent = records[-limit:]
    return [
        {
            "ts": r.get("ts"),
            "outcome": r.get("outcome"),
            "error_code": r.get("error_code") or None,
            "project": r.get("project"),
        }
        for r in recent
    ]


def _build_verbose_block() -> Dict[str, Any]:
    return {
        "project_lock": _build_project_lock_block(),
        "flexinit_importable": _check_flexinit_importable(),
        "pythonnet_available": _check_pythonnet_available(),
        "recent_operations": _build_recent_operations(5),
    }


# ============================================================
# Handler
# ============================================================

async def handle_flextools_health(args: dict) -> List[TextContent]:
    """Composed read-only diagnostic snapshot for flextools_health (issue #56).

    No side effects: never mutates session state, never opens a FieldWorks
    project, never writes files. Safe to call at any point in a session
    (even before flextools_start -- see server.py's _SESSION_INDEPENDENT_TOOLS
    if this tool is later added there).
    """
    verbose = bool(args.get("verbose", False))

    index_dir = get_index_dir()
    libraries = _build_libraries_block(index_dir)

    result: Dict[str, Any] = {
        "server": {
            "version": _server_version(),
            "python": platform.python_version(),
            "pid": os.getpid(),
        },
        "fieldworks": _build_fieldworks_block(),
        "libraries": libraries,
        "indexes": _build_indexes_block(index_dir, libraries),
        "session": session_state.summary(),
        "logs": {
            "operations_log": str(get_log_dir() / "operations.log"),
            "operations_jsonl": str(get_log_dir() / "operations.jsonl"),
        },
        "warnings": _build_warnings(libraries),
    }

    if verbose:
        result["verbose"] = _build_verbose_block()

    result = build_response_with_context(result, include_session=False)
    return json_response(result)


def _server_version() -> str:
    try:
        try:
            from ... import __version__
        except (ImportError, ValueError):
            from flextoolsmcp import __version__
        return __version__
    except Exception:
        return "unknown"
