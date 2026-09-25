#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Load project ``.env`` and surface obsolete configuration (issue #141).

FlexToolsMCP reads path overrides from a repo-root ``.env`` when present.
Legacy installs sometimes still set ``FLEXLIBS2_PATH`` from an old flexlibs2
layout; nothing in this package consumes that variable today, so it looks like
active configuration while having no effect.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List, Optional

# Keys that may appear in user .env files but are not read anywhere in this
# package. Value is the user-facing remediation text.
OBSOLETE_ENV_VARS = {
    "FLEXLIBS2_PATH": (
        "FLEXLIBS2_PATH is obsolete and is not read by FlexToolsMCP. "
        "Remove it from .env (or comment it out). Use "
        "`pip install pyflexicon` / FLEXICON_PATH for a flexicon source checkout."
    ),
}


def load_project_env(project_root: Optional[Path] = None) -> Optional[Path]:
    """Load ``project_root/.env`` into ``os.environ`` (setdefault semantics).

    Returns the path when a file was read, else ``None``. Obsolete keys listed
    in ``OBSOLETE_ENV_VARS`` are not applied; a warning is recorded for them
    via :func:`collect_obsolete_env_warnings` instead.
    """
    if project_root is None:
        if __package__:
            from .file_utils import get_project_root
        else:
            from file_utils import get_project_root
        project_root = get_project_root()

    env_file = project_root / ".env"
    if not env_file.is_file():
        return None

    with open(env_file, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key in OBSOLETE_ENV_VARS:
                # Do not load dead configuration; warn below.
                os.environ.setdefault(f"_FLEXTOOLSMCP_OBSOLETE_{key}", value)
                continue
            os.environ.setdefault(key, value)
    return env_file


def collect_obsolete_env_warnings() -> List[str]:
    """Return warning strings for obsolete env vars currently set."""
    warnings: List[str] = []
    for key, message in OBSOLETE_ENV_VARS.items():
        if os.environ.get(key):
            warnings.append(f"[WARN] {message} (found {key} in the environment.)")
            continue
        shadow = os.environ.get(f"_FLEXTOOLSMCP_OBSOLETE_{key}")
        if shadow is not None:
            warnings.append(
                f"[WARN] {message} (found {key}={shadow!r} in .env.)"
            )
    return warnings


def emit_obsolete_env_warnings(
    *,
    print_fn: Callable[[str], None] = print,
    logger: Optional[object] = None,
) -> None:
    """Log or print obsolete-configuration warnings once per process."""
    for message in collect_obsolete_env_warnings():
        if logger is not None:
            warn = getattr(logger, "warning", None)
            if callable(warn):
                warn(message)
                continue
        print_fn(message)
