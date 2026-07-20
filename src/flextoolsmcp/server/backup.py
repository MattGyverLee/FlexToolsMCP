#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Automatic pre-write backup (issue #55, Rung 2).

Before the FIRST mutating run_module() call per (session, project), copy the
project's .fwdata to a timestamped directory under
``~/.flextoolsmcp/backups/<project>/<UTC-timestamp>/``. Restore is
deliberately manual -- see docs/RECOVERY.md. An automated restore tool is a
separate future issue: restoring over a live project is the one operation
that must never be easy to invoke by accident.

This module is best-effort and MUST NOT raise -- a backup failure should
never block a write run. Callers get a structured result dict and decide how
to log/surface it.
"""

import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from .project_discovery import get_project_fwdata_path
except ImportError:
    from project_discovery import get_project_fwdata_path

try:
    from ..config import (
        config_get,
        BACKUP_BEFORE_WRITE_KEY,
        BACKUP_BEFORE_WRITE_DEFAULT,
        BACKUP_RETENTION_KEY,
        BACKUP_RETENTION_DEFAULT,
    )
except (ImportError, ValueError):
    from config import (
        config_get,
        BACKUP_BEFORE_WRITE_KEY,
        BACKUP_BEFORE_WRITE_DEFAULT,
        BACKUP_RETENTION_KEY,
        BACKUP_RETENTION_DEFAULT,
    )

# Backup root -- separate from config.py's CONFIG_DIR constant so this module
# has no import-time dependency ordering surprises.
BACKUP_ROOT = Path.home() / ".flextoolsmcp" / "backups"


def _prune_old_backups(project_backup_dir: Path, retention: int) -> None:
    """Keep only the newest ``retention`` timestamped backup dirs.

    Directory names are UTC timestamps in ``%Y%m%dT%H%M%SZ`` form, so a plain
    lexicographic sort is also a chronological sort.
    """
    if retention < 0 or not project_backup_dir.is_dir():
        return
    try:
        entries = sorted(
            (p for p in project_backup_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )
    except OSError:
        return
    excess = len(entries) - retention
    for old_dir in entries[:max(excess, 0)]:
        shutil.rmtree(old_dir, ignore_errors=True)


def perform_pre_write_backup(
    project_name: str,
    *,
    backup_before_write: Optional[bool] = None,
) -> Dict[str, Any]:
    """Copy the project's .fwdata to a fresh timestamped backup directory.

    Args:
        project_name: The FieldWorks project name (as it appears on disk).
        backup_before_write: Per-call override of the config kill switch.
            None (default) defers to config key BACKUP_BEFORE_WRITE_KEY.

    Returns:
        {
          "path": str | None,          # copied .fwdata path, or None
          "created": bool,             # True iff a new backup was written
          "skipped_reason": str | None,
        }

    Never raises: any exception is caught and reported via skipped_reason so
    a backup failure can never block (or crash) a write run.
    """
    enabled = (
        backup_before_write
        if backup_before_write is not None
        else bool(config_get(BACKUP_BEFORE_WRITE_KEY, BACKUP_BEFORE_WRITE_DEFAULT))
    )
    if not enabled:
        return {"path": None, "created": False, "skipped_reason": "backup_before_write=false"}

    try:
        fwdata_path = get_project_fwdata_path(project_name)
        if fwdata_path is None:
            return {"path": None, "created": False, "skipped_reason": "project_fwdata_not_found"}

        project_size = fwdata_path.stat().st_size

        try:
            usage = shutil.disk_usage(fwdata_path.parent)
            free_bytes = usage.free
        except OSError:
            free_bytes = None

        # Skip (with WARN, logged by the caller) if free disk < 2x project size.
        if free_bytes is not None and free_bytes < 2 * project_size:
            return {"path": None, "created": False, "skipped_reason": "insufficient_disk_space"}

        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        dest_dir = BACKUP_ROOT / project_name / timestamp
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / fwdata_path.name
        shutil.copy2(fwdata_path, dest_file)

        retention = int(config_get(BACKUP_RETENTION_KEY, BACKUP_RETENTION_DEFAULT))
        _prune_old_backups(BACKUP_ROOT / project_name, retention)

        return {"path": str(dest_file), "created": True, "skipped_reason": None}
    except Exception as e:  # noqa: BLE001 - best-effort, must never raise
        return {"path": None, "created": False, "skipped_reason": f"backup_failed: {e}"}
