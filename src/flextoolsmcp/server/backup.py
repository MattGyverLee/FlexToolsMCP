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
from typing import Any, Dict, Optional, Tuple

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


#: Free space must be at least this multiple of the bytes about to be written.
DISK_SPACE_FACTOR = 2


def _remove_partial_backup(dest_file: Path, dest_dir: Path) -> None:
    """Best-effort removal of a copy that did not complete, and its empty
    timestamp folder. Never raises: the caller re-raises the copy error."""
    try:
        if dest_file.exists():
            dest_file.unlink()
    except OSError:
        pass
    try:
        dest_dir.rmdir()  # only succeeds when empty
    except OSError:
        pass


def disk_space_ok(
    path: Path, needed_bytes: int
) -> Tuple[bool, int, Optional[int]]:
    """The one statement of the disk-space rule (Principle VI).

    Checks whether the volume holding ``path`` has at least
    ``DISK_SPACE_FACTOR`` (2) times ``needed_bytes`` free. ``path`` must be an
    existing directory or file on the target volume (it is passed straight to
    ``shutil.disk_usage``).

    Returns ``(ok, required_bytes, free_bytes)``:

    - ``required_bytes`` is ``2 * needed_bytes`` -- the threshold applied, and
      the figure a refusal reports as ``needed_bytes``.
    - ``free_bytes`` is the volume's free space, or ``None`` when it cannot be
      measured (``OSError`` from ``disk_usage``).
    - ``ok`` is False only when ``free_bytes`` is known and below
      ``required_bytes``. An unmeasurable volume is fail-open (``ok`` True),
      matching the backup's long-standing behaviour.

    Never raises for an unreadable volume. Callers: the pre-write backup
    (`_space_skip_reason`) and the parse sandbox's work-directory check.
    """
    required_bytes = DISK_SPACE_FACTOR * needed_bytes
    try:
        free_bytes: Optional[int] = shutil.disk_usage(path).free
    except OSError:
        free_bytes = None
    ok = free_bytes is None or free_bytes >= required_bytes
    return ok, required_bytes, free_bytes


def _space_skip_reason(fwdata_path: Path) -> Optional[str]:
    """``insufficient_disk_space`` when free disk < 2x the project, else None.

    Applies the shared `disk_space_ok` rule. Shared by the backup itself and
    by `predict_backup_skip`, so a preview's stated backup outcome and the
    backup that follows it apply the same test (CP4 FR-007, SC-004).
    """
    project_size = fwdata_path.stat().st_size
    ok, _required, _free = disk_space_ok(fwdata_path.parent, project_size)
    if not ok:
        return "insufficient_disk_space"
    return None


def predict_backup_skip(project_name: str) -> Optional[str]:
    """Why a backup of this project would be skipped right now, or None.

    A prediction, never a backup: nothing is copied or created. It answers
    the two filesystem questions `perform_pre_write_backup` asks before it
    copies (is there a .fwdata; is there room), with the same helpers, so
    CP4's mutation plan can state the backup's expected outcome before a
    human confirms (FR-007). The config opt-out is the caller's to report.
    Never raises.
    """
    try:
        fwdata_path = get_project_fwdata_path(project_name)
        if fwdata_path is None:
            return "project_fwdata_not_found"
        return _space_skip_reason(fwdata_path)
    except Exception as e:  # noqa: BLE001 - a prediction must never raise
        return f"backup_failed: {e}"


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

        # Skip (with WARN, logged by the caller) if free disk < 2x project size.
        space_skip = _space_skip_reason(fwdata_path)
        if space_skip is not None:
            return {"path": None, "created": False, "skipped_reason": space_skip}

        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        dest_dir = BACKUP_ROOT / project_name / timestamp
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / fwdata_path.name
        try:
            shutil.copy2(fwdata_path, dest_file)
        except BaseException:
            # A failed copy must not leave a truncated .fwdata that retention
            # (or a person restoring) would take for a real backup (CP5
            # pattern audit, sweep 2: cleanup on every path, not just success).
            _remove_partial_backup(dest_file, dest_dir)
            raise

        # The copy above exists now, so nothing below may report it as absent
        # or delete it: an unparseable retention falls back to the default
        # (it used to raise into `backup_failed` with the copy on disk), and
        # a retention of 0 still keeps the backup just taken (it used to
        # delete it while returning `created: True` and its path).
        try:
            retention = int(config_get(BACKUP_RETENTION_KEY, BACKUP_RETENTION_DEFAULT))
        except (TypeError, ValueError):
            retention = int(BACKUP_RETENTION_DEFAULT)
        _prune_old_backups(BACKUP_ROOT / project_name,
                           max(retention, 1) if retention >= 0 else retention)

        return {"path": str(dest_file), "created": True, "skipped_reason": None}
    except Exception as e:  # noqa: BLE001 - best-effort, must never raise
        return {"path": None, "created": False, "skipped_reason": f"backup_failed: {e}"}
