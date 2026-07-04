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


def parse_version(filename: str) -> Tuple[int, int, int]:
    """Extract version tuple from filename like 'liblcm_api_v11.0.0.json'."""
    match = re.search(r'v(\d+)\.(\d+)\.(\d+)', filename)
    if match:
        major, minor, patch = match.groups()
        return (int(major), int(minor), int(patch))
    return (0, 0, 0)


def archive_versions_in_directory(
    directory: Path,
    pattern: str,
    keep_count: int = 1
) -> Dict[str, List[str]]:
    """Archive old versions in a directory.

    Args:
        directory: Directory containing versioned files
        pattern: Glob pattern like "liblcm_api_v*.json"
        keep_count: Number of latest versions to keep in main directory

    Returns:
        Dict with 'archived' and 'kept' file lists
    """
    if not directory.exists():
        return {"archived": [], "kept": []}

    # Find all versioned files
    files = sorted(directory.glob(pattern))
    if len(files) <= keep_count:
        return {"archived": [], "kept": [f.name for f in files]}

    # Sort by version (descending, so latest first)
    files_with_versions = [(f, parse_version(f.name)) for f in files]
    files_with_versions.sort(key=lambda x: x[1], reverse=True)

    # Keep latest N, archive the rest
    keep_files = [f for f, _ in files_with_versions[:keep_count]]
    archive_files = [f for f, _ in files_with_versions[keep_count:]]

    # Create archive directory
    archive_dir = directory / "archive"
    archive_dir.mkdir(exist_ok=True)

    # Move old files to archive
    archived = []
    for old_file in archive_files:
        try:
            archive_path = archive_dir / old_file.name
            shutil.move(str(old_file), str(archive_path))
            archived.append(old_file.name)
            print(f"  [ARCHIVE] {old_file.name} -> archive/")
        except FileNotFoundError:
            # File already gone - skip it
            pass

    return {
        "archived": archived,
        "kept": [f.name for f in keep_files]
    }


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

    # Archive patterns by directory
    # Note: patterns are defined only in their canonical locations to avoid duplication
    patterns = {
        index_dir / "liblcm": [
            ("liblcm_api_v*.json", "LibLCM"),
            ("casting_index_liblcm-v*.json", "Casting Index"),
            ("navigation_graph_liblcm-v*.json", "Navigation Graph"),
            ("reverse_mapping_liblcm-v*.json", "Reverse Mapping"),
        ],
        index_dir / "flexlibs": [
            ("flexlibs_api_v*.json", "FlexLibs"),
            ("flexicon_api_v*.json", "Flexicon"),
            ("common_patterns_flexicon-v*.json", "Common Patterns"),
        ],
    }

    total_archived = 0
    total_kept = 0

    for directory, file_patterns in patterns.items():
        if not directory.exists():
            continue

        for pattern, label in file_patterns:
            result = archive_versions_in_directory(
                directory,
                pattern,
                keep_count=args.keep
            )

            archived_count = len(result["archived"])
            kept_count = len(result["kept"])

            if archived_count > 0:
                print(f"[OK] {label}: Archived {archived_count}, Keeping {kept_count}")
                total_archived += archived_count
                total_kept += kept_count

    if not args.quiet:
        print(f"\n[DONE] Archived {total_archived} old versions")
        if total_archived == 0:
            print("  (No old versions to archive)")

    return 0


if __name__ == "__main__":
    exit(main())
