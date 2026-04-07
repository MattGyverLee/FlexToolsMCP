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

    Supports formats like 'liblcm_api_v11.0.0.json' or 'flexlibs2_api-v2.1.5.json'.

    Args:
        filename: Filename containing version pattern (e.g., 'api_v11.0.0.json')

    Returns:
        Tuple of (major, minor, patch) for sorting, or (0, 0, 0) if not found
    """
    match = re.search(r'v(\d+)\.(\d+)\.(\d+)', filename)
    if match:
        return tuple(map(int, match.groups()))
    return (0, 0, 0)


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
        library_name: Display name for logging (e.g., 'LibLCM', 'FlexLibs 2.0')
        import_path: Module name for Python imports (e.g., 'flexlibs2')
        package_name: Package name for importlib.metadata (e.g., 'flexlibs2')
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

    # Try Python package detection (FlexLibs, FlexLibs2)
    if import_path:
        try:
            module = __import__(import_path)
            if hasattr(module, '__version__'):
                version = module.__version__  # type: ignore
                log_debug(f"Detected {library_name} version from __version__: {version}")
                return version
        except Exception:
            pass

        # Try package metadata fallback
        try:
            from importlib.metadata import version
            pkg_version = version(package_name or import_path)
            log_debug(f"Detected {library_name} version from metadata: {pkg_version}")
            return pkg_version
        except Exception:
            pass

    log_debug(f"Could not detect {library_name} version")
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
        - Results cached for entire process lifetime
        - Assumes index directory content is static during runtime
        - Call clear_file_discovery_cache() if index changes during execution
        - Safe for repeated calls (idempotent)
        - Single-threaded use (safe in normal MCP server context)
    """
    cache_key = (str(index_dir), f"{prefix}_latest")

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
    Results are cached to avoid repeated filesystem operations.

    Args:
        index_dir: Parent directory (e.g., index/liblcm)
        prefix: File prefix (e.g., 'liblcm_api')
        target_version: Version to match (e.g., '11.0.0')

    Returns:
        Path to matching file, or None if not found
    """
    cache_key = (str(index_dir), f"{prefix}_v{target_version}")

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
