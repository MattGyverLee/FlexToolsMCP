#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Version detection and API file discovery utilities.

Consolidates version detection for multiple library types (C# assemblies, Python packages)
and provides efficient, cached file discovery for versioned API indexes.
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Callable
from functools import lru_cache

try:
    from .kernel import operations_logger
except ImportError:
    from server.kernel import operations_logger

# File discovery cache to avoid repeated glob operations
_file_discovery_cache: Dict[Tuple[str, str], Optional[Path]] = {}


# Safe logging helper for operations_logger (may be None during early init)
def _log_ops_info(msg: str) -> None:
    """Log info message, safely handling None logger during early init."""
    if operations_logger:
        operations_logger.info(msg)


def _log_ops_debug(msg: str) -> None:
    """Log debug message, safely handling None logger during early init."""
    if operations_logger:
        operations_logger.debug(msg)


def extract_version(filename: str) -> Tuple[int, int, int]:
    """Extract semantic version (major, minor, patch) from filename.

    Supports formats like 'liblcm_api_v11.0.0.json' or 'flexicon_api-v2.1.5.json'.

    Args:
        filename: Filename containing version pattern (e.g., 'api_v11.0.0.json')

    Returns:
        Tuple of (major, minor, patch) for sorting, or (0, 0, 0) if not found
    """
    match = re.search(r'v(\d+)\.(\d+)\.(\d+)', filename)
    if match:
        return tuple(map(int, match.groups()))
    return (0, 0, 0)


def extract_version_string(filename: str) -> Optional[str]:
    """Extract the version string (e.g. '11.0.0') from a versioned filename.

    Unlike extract_version() (which returns an (int, int, int) sort key and
    silently reads as (0, 0, 0) when no version segment is present), this
    returns the original dotted string or None -- used where the caller
    needs to *report* the version (e.g. flextools_health's index_loaded
    field), not just sort by it.
    """
    match = re.search(r'v(\d+\.\d+\.\d+)', filename)
    return match.group(1) if match else None


def detect_installed_library_version(
    library_name: str,
    import_path: Optional[str] = None,
    package_name: Optional[str] = None,
    assembly_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """Detect the installed version of a library (Python package or C# assembly).

    Tries multiple detection strategies based on library type:
    - For C# assemblies: Uses pythonnet reflection
    - For Python packages: Checks __version__ attribute, then importlib.metadata

    Args:
        library_name: Display name for logging (e.g., 'LibLCM', 'Flexicon')
        import_path: Module name for Python imports (e.g., 'flexicon')
        package_name: Package name for importlib.metadata (e.g., 'flexicon')
        assembly_name: C# assembly name (e.g., 'SIL.LCModel')
        logger: Logger instance (defaults to operations_logger if available)

    Returns:
        Version string (e.g., '11.0.0') or None if not detected
    """
    logger = logger or operations_logger

    # Helper to safely log (logger may be None during early initialization)
    def log_debug(msg: str) -> None:
        if logger:
            logger.debug(msg)

    # Try C# assembly reflection first (LibLCM)
    if assembly_name:
        try:
            import clr  # type: ignore
            clr.AddReference(assembly_name)  # type: ignore
            try:
                import System  # type: ignore
                asm = System.Reflection.Assembly.Load(assembly_name)
                version_attr = asm.GetName().Version
                version = f"{version_attr.Major}.{version_attr.Minor}.{version_attr.Build}"
                log_debug(f"Detected {library_name} version from assembly: {version}")
                return version
            except Exception as ex:
                log_debug(f"Could not extract {library_name} version from assembly: {ex}")
        except Exception as e:
            log_debug(f"Could not detect {library_name} (C# assembly): {e}")

    # Try Python package detection (FlexLibs, Flexicon)
    if import_path:
        # Live module attributes are checked FIRST and preferred over
        # importlib.metadata: for path / editable installs (the common dev
        # setup here), pip metadata goes stale while the source on sys.path is
        # the version actually in use. flexicon exposes its version as
        # `version` (not `__version__`); checking only `__version__` made the
        # server fall back to stale pip metadata and load a mismatched index
        # (e.g. detecting 3.0.0 while flexicon 4.0.1 was on the path). #38
        try:
            module = __import__(import_path)
            for attr in ("__version__", "version"):
                ver = getattr(module, attr, None)
                if isinstance(ver, str) and ver.strip():
                    log_debug(f"Detected {library_name} version from {attr}: {ver}")
                    return ver.strip()
        except Exception:
            pass

        # Try package metadata fallback (only when the live module had no
        # usable version attribute).
        try:
            from importlib.metadata import version
            pkg_version = version(package_name or import_path)
            log_debug(f"Detected {library_name} version from metadata: {pkg_version}")
            return pkg_version
        except Exception:
            pass

    log_debug(f"Could not detect {library_name} version")
    return None


def _default_liblcm_search_paths() -> list[Path]:
    """Standard search locations for the SIL.LCModel DLL / FieldWorks install.

    Shared by detect_liblcm_version_from_disk() and locate_liblcm_dll() (the
    latter used by flextools_health to report the detected install path) so
    the candidate list can't drift between the two callers.
    """
    import os

    search_paths: list[Path] = []
    env_path = os.environ.get("FIELDWORKS_DLL_PATH")
    if env_path:
        search_paths.append(Path(env_path))
    search_paths.extend([
        Path(r"D:/Github/Fieldworks/Output/Debug"),
        Path(r"D:/Github/Fieldworks/Output/Release"),
        Path(r"C:/Program Files/SIL/FieldWorks 9"),
        Path(r"C:/Program Files (x86)/SIL/FieldWorks 9"),
    ])
    return search_paths


def locate_liblcm_dll(
    dll_name: str = "SIL.LCModel.dll",
    search_paths: Optional[list[Path]] = None,
) -> Optional[Path]:
    """Find the SIL.LCModel DLL on disk without loading it.

    Args:
        dll_name: DLL filename to locate
        search_paths: Override search paths. Defaults to FIELDWORKS_DLL_PATH env
            var plus the standard FieldWorks install locations.

    Returns:
        Path to the DLL if found, else None. Does not require pythonnet --
        this is a plain filesystem check, used by flextools_health to report
        a FieldWorks install path even when pythonnet/CLR isn't available.
    """
    if search_paths is None:
        search_paths = _default_liblcm_search_paths()

    for base in search_paths:
        candidate = base / dll_name
        if candidate.exists():
            return candidate
    return None


def detect_liblcm_version_from_disk(
    dll_name: str = "SIL.LCModel.dll",
    search_paths: Optional[list[Path]] = None,
) -> Optional[str]:
    """Read SIL.LCModel version directly from the DLL on disk.

    Session-header logging runs before any FLExProject opens, so the assembly
    isn't yet loaded into the CLR -- `Assembly.Load("SIL.LCModel")` returns None.
    Reading the DLL off disk gives a usable version in the very first log line,
    which is when bug-report triage needs it most.

    Args:
        dll_name: DLL filename to locate
        search_paths: Override search paths. Defaults to FIELDWORKS_DLL_PATH env
            var plus the standard FieldWorks install locations.

    Returns:
        Version string like '11.0.0', or None if pythonnet/DLL unavailable.
    """
    dll_path = locate_liblcm_dll(dll_name, search_paths)

    if dll_path is None:
        _log_ops_debug(f"Could not locate {dll_name} on disk for version detection")
        return None

    try:
        import clr  # type: ignore  # noqa: F401
        import System  # type: ignore
        asm = System.Reflection.Assembly.LoadFile(str(dll_path))
        v = asm.GetName().Version
        return f"{v.Major}.{v.Minor}.{v.Build}"
    except Exception as exc:
        _log_ops_debug(f"Could not read {dll_name} version from {dll_path}: {exc}")
        return None


def find_api_files(
    index_dir: Path,
    prefix: str,
    target_version: Optional[str] = None,
    include_archive: bool = True,
) -> list[Path]:
    """Find API files matching a prefix and optional version.

    Searches in main directory and optional archive subdirectory.
    Handles both underscore (_) and hyphen (-) naming patterns for robustness.
    Results are sorted by version (descending).

    Args:
        index_dir: Parent directory (e.g., index/liblcm)
        prefix: File prefix (e.g., 'liblcm_api')
        target_version: If set, filter to exact version (e.g., '11.0.0')
        include_archive: Include archive subdirectory

    Returns:
        List of matching paths sorted by version (latest first)
    """
    if not index_dir.exists():
        return []

    files = []
    search_dirs = [index_dir]

    if include_archive and (index_dir / "archive").exists():
        search_dirs.append(index_dir / "archive")

    # Search both naming patterns
    for search_dir in search_dirs:
        files.extend(search_dir.glob(f"{prefix}_v*.json"))  # underscore pattern
        files.extend(search_dir.glob(f"{prefix}-v*.json"))  # hyphen pattern

    # Filter by version if specified
    if target_version:
        files = [f for f in files if f"v{target_version}" in f.name]

    # Remove duplicates and sort by version (descending)
    files = list(set(files))
    files.sort(key=lambda f: extract_version(f.name), reverse=True)

    return files


def _dir_state_token(index_dir: Path) -> float:
    """Return a cheap freshness token (mtime) for a directory.

    Used to key the file-discovery cache so that a write to ``index_dir``
    (e.g. ``auto_refresh_missing_api_file()`` writing a newly-generated
    versioned JSON file, whether from this process or an external
    ``refresh.py`` run) naturally invalidates any previously-cached lookup
    for that directory -- no explicit ``clear_file_discovery_cache()`` call
    required. Creating/removing an entry inside a directory updates that
    directory's mtime on both Windows and POSIX, which is exactly the
    "index changed" signal we need.

    Falls back to ``0.0`` when the directory doesn't exist (or stat fails);
    that's a stable, valid token in its own right -- lookups against a
    still-missing directory stay cheap until it's created.
    """
    try:
        return index_dir.stat().st_mtime
    except OSError:
        return 0.0


def find_latest_versioned_api_file(index_dir: Path, prefix: str) -> Optional[Path]:
    """Find the latest versioned API file for a library.

    Searches in both the main directory and archive subdirectories.
    Results are cached to avoid repeated filesystem operations.

    Args:
        index_dir: Parent directory (e.g., index/liblcm)
        prefix: File prefix (e.g., 'liblcm_api')

    Returns:
        Path to latest versioned file, or None if not found

    Caching:
        - Keyed on (index_dir, prefix, directory mtime) -- a write to
          index_dir (new/removed file) changes the mtime and transparently
          invalidates stale cache entries for that directory, so a refresh
          that happens between calls (in this process or another) is
          picked up on the next lookup without requiring callers to call
          clear_file_discovery_cache() themselves.
        - clear_file_discovery_cache() remains available for tests that
          want a hard reset regardless of mtime granularity.
        - Single-threaded use (safe in normal MCP server context)
    """
    cache_key = (str(index_dir), f"{prefix}_latest", _dir_state_token(index_dir))

    if cache_key in _file_discovery_cache:
        return _file_discovery_cache[cache_key]

    files = find_api_files(index_dir, prefix, include_archive=True)
    result = files[0] if files else None

    # Cache result
    _file_discovery_cache[cache_key] = result
    return result


def find_versioned_api_file(
    index_dir: Path,
    prefix: str,
    target_version: str,
) -> Optional[Path]:
    """Find API file matching a specific version.

    Tries exact match in main directory, then archive directory.
    Handles both underscore (_) and hyphen (-) naming patterns.
    Results are cached to avoid repeated filesystem operations, keyed on
    (index_dir, prefix, version, directory mtime) so a write to index_dir
    invalidates stale entries (see find_latest_versioned_api_file docstring).

    Args:
        index_dir: Parent directory (e.g., index/liblcm)
        prefix: File prefix (e.g., 'liblcm_api')
        target_version: Version to match (e.g., '11.0.0')

    Returns:
        Path to matching file, or None if not found
    """
    cache_key = (str(index_dir), f"{prefix}_v{target_version}", _dir_state_token(index_dir))

    if cache_key in _file_discovery_cache:
        return _file_discovery_cache[cache_key]

    # Try both naming patterns in main directory
    for pattern in [f"{prefix}_v{target_version}.json", f"{prefix}-v{target_version}.json"]:
        main_path = index_dir / pattern
        if main_path.exists():
            _log_ops_info(f"Found exact version match: {pattern}")
            _file_discovery_cache[cache_key] = main_path
            return main_path

    # Try archive directory
    archive_dir = index_dir / "archive"
    if archive_dir.exists():
        for pattern in [f"{prefix}_v{target_version}.json", f"{prefix}-v{target_version}.json"]:
            archive_path = archive_dir / pattern
            if archive_path.exists():
                _log_ops_info(f"Found exact version match in archive: {pattern}")
                _file_discovery_cache[cache_key] = archive_path
                return archive_path

    _log_ops_debug(f"No exact match found for {prefix} v{target_version}")
    _file_discovery_cache[cache_key] = None
    return None


def clear_file_discovery_cache() -> None:
    """Clear the file discovery cache. Useful for testing."""
    global _file_discovery_cache
    _file_discovery_cache.clear()
