#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archive Old API Versions

Moves older versioned API files to archive subdirectories, keeping only
the latest version of each API in the main index directory. Archived
versions remain accessible to the build scripts.

Usage:
    python src/archive_old_versions.py
    python src/archive_old_versions.py --keep 2  # Keep last 2 versions
"""

import argparse
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

if __package__:
    from .file_utils import get_index_dir
else:
    from file_utils import get_index_dir


# Version token in an index filename: '_v4.2.1' or '-v11.0.0'. The separator is
# '_' (e.g. flexicon_api_v4.2.1.json) or '-' (e.g. common_patterns_flexicon-v4.1.2.json).
_VERSION_RE = re.compile(r'[-_]v(\d+)\.(\d+)\.(\d+)')

# Subdirectories under the index root that never hold live versioned files.
_SKIP_DIRS = {"archive", "embeddings"}


def parse_version(filename: str) -> Tuple[int, int, int]:
    """Extract version tuple from filename like 'liblcm_api_v11.0.0.json'."""
    match = _VERSION_RE.search(filename)
    if match:
        major, minor, patch = match.groups()
        return (int(major), int(minor), int(patch))
    return (0, 0, 0)


def version_group_key(filename: str) -> str:
    """Strip the version token so all versions of one index share a key.

    'flexicon_api_v4.2.1.json'             -> 'flexicon_api'
    'common_patterns_flexicon-v4.1.2.json' -> 'common_patterns_flexicon'
    'casting_index_liblcm-v11.0.0.json'    -> 'casting_index_liblcm'
    """
    return _VERSION_RE.sub('', Path(filename).stem)


def _index_directories(index_dir: Path) -> List[Path]:
    """Directories that may hold live versioned files: the index root plus each
    immediate subdirectory, excluding archive/ and embeddings/.

    Discovering directories (rather than hardcoding them) keeps archiving correct
    when the index folder layout changes -- files are grouped by naming
    convention wherever they live, so a relocated or newly added index type is
    archived automatically instead of being silently skipped.
    """
    dirs = [index_dir]
    if index_dir.exists():
        for child in sorted(index_dir.iterdir()):
            if child.is_dir() and child.name not in _SKIP_DIRS:
                dirs.append(child)
    return dirs


def archive_versions_in_directory(
    directory: Path,
    keep_count: int = 1
) -> Dict[str, List[str]]:
    """Archive old versions of every version-group of files in `directory`.

    Files are grouped by name-without-version (see version_group_key), so all
    versioned index files in the directory are handled -- no per-type glob
    pattern needed. archive/ and embeddings/ subdirectories are never recursed
    into (only files directly in `directory` are considered).

    Args:
        directory: Directory containing versioned files
        keep_count: Number of latest versions to keep per group

    Returns:
        Dict with 'archived' and 'kept' file-name lists (across all groups)
    """
    if not directory.exists():
        return {"archived": [], "kept": []}

    # Group versioned files by their non-version stem.
    groups: Dict[str, List[Path]] = {}
    for f in directory.glob("*.json"):
        if not _VERSION_RE.search(f.name):
            continue
        groups.setdefault(version_group_key(f.name), []).append(f)

    archived: List[str] = []
    kept: List[str] = []

    for files in groups.values():
        # Sort by version, latest first.
        files.sort(key=lambda f: parse_version(f.name), reverse=True)
        if len(files) <= keep_count:
            kept.extend(f.name for f in files)
            continue

        keep_files = files[:keep_count]
        archive_files = files[keep_count:]
        kept.extend(f.name for f in keep_files)

        archive_dir = directory / "archive"
        archive_dir.mkdir(exist_ok=True)
        for old_file in archive_files:
            try:
                shutil.move(str(old_file), str(archive_dir / old_file.name))
                archived.append(old_file.name)
                print(f"  [ARCHIVE] {old_file.name} -> {directory.name}/archive/")
            except FileNotFoundError:
                # File already gone - skip it
                pass

    return {"archived": archived, "kept": kept}


def main():
    parser = argparse.ArgumentParser(
        description="Archive old API versions to subdirectories"
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=1,
        help="Number of latest versions to keep in main directory (default: 1)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output"
    )

    args = parser.parse_args()

    index_dir = get_index_dir()

    print("[INFO] Archiving old API versions...")
    print(f"  Keeping {args.keep} latest version(s)")

    total_archived = 0
    total_kept = 0

    # Discover every directory that may hold versioned files and archive by
    # naming convention. No hardcoded directory->pattern map to drift when the
    # index layout changes.
    for directory in _index_directories(index_dir):
        result = archive_versions_in_directory(directory, keep_count=args.keep)
        archived_count = len(result["archived"])
        if archived_count > 0:
            rel = directory.name if directory != index_dir else "index root"
            print(f"[OK] {rel}: Archived {archived_count}, "
                  f"Keeping {len(result['kept'])}")
            total_archived += archived_count
            total_kept += len(result["kept"])

    if not args.quiet:
        print(f"\n[DONE] Archived {total_archived} old versions")
        if total_archived == 0:
            print("  (No old versions to archive)")

    return 0


if __name__ == "__main__":
    exit(main())
