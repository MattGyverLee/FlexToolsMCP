#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File I/O utilities for index building scripts.

Consolidates common file operations (path resolution, JSON I/O) used across
multiple build scripts to eliminate duplication.
"""

import json
from pathlib import Path
from typing import Dict, Any

if __package__:
    from .json_utils import sort_json_arrays
else:
    from json_utils import sort_json_arrays


def get_project_root() -> Path:
    """Get the project root directory.

    Returns:
        Path to the project root (parent of src/ directory)
    """
    return Path(__file__).parent.parent


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
