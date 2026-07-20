#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File I/O utilities for index building scripts.

Consolidates common file operations (path resolution, JSON I/O) used across
multiple build scripts to eliminate duplication.
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, Any

if __package__:
    from .json_utils import sort_json_arrays
else:
    from json_utils import sort_json_arrays


# Root for all user-writable state (logs, skeletons, refreshed index overlay).
USER_DATA_DIR = Path.home() / ".flextoolsmcp"


def get_project_root() -> Path:
    """Get the repository root directory.

    This module lives at ``src/flextoolsmcp/file_utils.py``, so the repo root
    is three levels up. Used for locating ``.env`` and as the cwd for
    extractor subprocesses when regenerating indexes from source.

    Returns:
        Path to the repository root (only meaningful in a source checkout).
    """
    return Path(__file__).parent.parent.parent


def get_bundled_index_dir() -> Path:
    """Get the read-only index that ships inside the package.

    Lives at ``flextoolsmcp/index`` (next to this module) and is packaged into
    the wheel as package data.
    """
    return Path(__file__).parent / "index"


def get_bundled_templates_dir() -> Path:
    """Get the FlexTools module templates that ship inside the package.

    Lives at ``flextoolsmcp/templates`` (next to this module) and is packaged
    into the wheel as package data, so ``get_module_template`` works from a
    source checkout and from a ``pip``/``uvx`` install alike. Resolving relative
    to this module -- not to a repo-root ``parents[N]`` walk -- is what keeps it
    correct once the code is installed into ``site-packages``.
    """
    return Path(__file__).parent / "templates"


def get_user_index_dir() -> Path:
    """Get the user-writable index overlay (``~/.flextoolsmcp/index``)."""
    return USER_DATA_DIR / "index"


def _running_from_source() -> bool:
    """True when running from a git checkout (or editable install).

    In that case the in-tree package index is the canonical, committed copy,
    so refresh/build write there directly (to be committed and later bundled).
    A wheel install has no repo ``.git`` and must not write into site-packages.
    """
    return (get_project_root() / ".git").exists()


def _seed_user_index(bundled: Path, user: Path) -> None:
    """Copy any bundled index file missing from the user overlay.

    Runs per file so a package upgrade (which ships a newer bundled index)
    flows new versioned files into the overlay, while refresh-generated files
    already in the overlay are preserved.
    """
    try:
        if not bundled.exists():
            return
        user.mkdir(parents=True, exist_ok=True)
        for src in bundled.rglob("*"):
            if src.is_dir():
                continue
            dest = user / src.relative_to(bundled)
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
    except Exception:
        # A read-only home or race is non-fatal; the loader still falls back
        # to whatever exists. Never let seeding crash startup.
        pass


def get_index_dir() -> Path:
    """Resolve the working index directory (read + write).

    - Source checkout / editable install: use the in-tree package index so a
      maintainer's ``refresh`` updates the committed, bundled index.
    - Installed wheel (``pip``/``uvx``): the package index is read-only and may
      live in an ephemeral cache, so use a user-writable overlay under
      ``~/.flextoolsmcp/index``, seeded from the bundled index. Runtime
      auto-refresh writes here and the loader reads here.

    Override with the ``FLEXTOOLSMCP_INDEX_DIR`` environment variable.
    """
    override = os.environ.get("FLEXTOOLSMCP_INDEX_DIR")
    if override:
        return Path(override)

    bundled = get_bundled_index_dir()
    if _running_from_source():
        return bundled

    user = get_user_index_dir()
    _seed_user_index(bundled, user)
    return user


def load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON file with UTF-8 encoding.

    Args:
        path: Path to JSON file to load

    Returns:
        Parsed JSON data as dictionary

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file is not valid JSON
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: Path, verbose: bool = True) -> None:
    """Save data to JSON file with UTF-8 encoding and sorted arrays.

    Args:
        data: Dictionary to save
        path: Path to save JSON file to
        verbose: If True, print confirmation message

    Raises:
        IOError: If file cannot be written
    """
    data = sort_json_arrays(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
    if verbose:
        print(f"[INFO] Saved: {path}")
