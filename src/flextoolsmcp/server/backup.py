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

Issue #218 adds size- and age-based pruning on top of the count-based
retention: `backup_max_total_mb` caps the total bytes of timestamped backups
across all projects, and `backup_max_age_days` evicts backups older than the
limit. Both run after every backup (and once at server startup), keep the
invariants (the backup just taken is never evicted, every project keeps its
newest backup, nothing outside the backup root is touched), and leave loose
files and non-timestamped directories alone.

This module is best-effort and MUST NOT raise -- a backup failure should
never block a write run. Callers get a structured result dict and decide how
to log/surface it.
"""

import datetime
import logging
import math
import re
import shutil
import time
from pathlib import Path
from typing import Any, Collection, Dict, List, NamedTuple, Optional, Set, Tuple

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
        BACKUP_MAX_TOTAL_MB_KEY,
        BACKUP_MAX_TOTAL_MB_DEFAULT,
        BACKUP_MAX_AGE_DAYS_KEY,
        BACKUP_MAX_AGE_DAYS_DEFAULT,
    )
except (ImportError, ValueError):
    from config import (
        config_get,
        BACKUP_BEFORE_WRITE_KEY,
        BACKUP_BEFORE_WRITE_DEFAULT,
        BACKUP_RETENTION_KEY,
        BACKUP_RETENTION_DEFAULT,
        BACKUP_MAX_TOTAL_MB_KEY,
        BACKUP_MAX_TOTAL_MB_DEFAULT,
        BACKUP_MAX_AGE_DAYS_KEY,
        BACKUP_MAX_AGE_DAYS_DEFAULT,
    )

logger = logging.getLogger(__name__)

# Backup root -- separate from config.py's CONFIG_DIR constant so this module
# has no import-time dependency ordering surprises.
BACKUP_ROOT = Path.home() / ".flextoolsmcp" / "backups"

#: Timestamped backup directories use ``%Y%m%dT%H%M%SZ`` names. Only
#: directories matching this pattern are managed by the pruners; loose files
#: and oddly-named directories are never counted, sized, or removed (#218).
BACKUP_TS_RE = re.compile(r"^\d{8}T\d{6}Z$")


def _parse_backup_ts(name: str) -> Optional[datetime.datetime]:
    """Parse a ``%Y%m%dT%H%M%SZ`` directory name to an aware UTC datetime.

    Returns None for anything that is not a timestamped backup directory
    (loose files, oddly-named directories -- never managed, #218).
    """
    if not BACKUP_TS_RE.match(name):
        return None
    try:
        return datetime.datetime.strptime(name, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        return None


class _BackupEntry(NamedTuple):
    project: str
    path: Path
    taken: datetime.datetime  # UTC, parsed from the directory name
    size_bytes: int


def _utcnow() -> datetime.datetime:
    """Current UTC time. A named seam so tests can freeze "now" without
    touching the datetime module."""
    return datetime.datetime.now(datetime.timezone.utc)


def _dir_size_bytes(path: Path) -> int:
    """Best-effort recursive size of a directory. Never raises."""
    total = 0
    try:
        for child in path.rglob("*"):
            try:
                if child.is_file() and not child.is_symlink():
                    total += child.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def _timestamped_entries(project_name: str, project_dir: Path) -> List[_BackupEntry]:
    """Timestamped backup dirs of one project, oldest first. Never raises."""
    entries: List[_BackupEntry] = []
    try:
        children = list(project_dir.iterdir())
    except OSError:
        return entries
    for child in children:
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        if not is_dir:
            continue
        taken = _parse_backup_ts(child.name)
        if taken is None:
            continue
        entries.append(
            _BackupEntry(project_name, child, taken, _dir_size_bytes(child))
        )
    entries.sort(key=lambda e: e.taken)
    return entries


def _collect_entries() -> List[_BackupEntry]:
    """All timestamped backup dirs across all projects, oldest first."""
    entries: List[_BackupEntry] = []
    try:
        project_dirs = sorted(
            (p for p in BACKUP_ROOT.iterdir() if p.is_dir()),
            key=lambda p: p.name,
        )
    except OSError:
        return entries
    for project_dir in project_dirs:
        entries.extend(_timestamped_entries(project_dir.name, project_dir))
    entries.sort(key=lambda e: e.taken)
    return entries


def _read_retention() -> int:
    """Count-based retention, falling back to the default on malformed config."""
    try:
        return int(config_get(BACKUP_RETENTION_KEY, BACKUP_RETENTION_DEFAULT))
    except (TypeError, ValueError, OverflowError):
        return int(BACKUP_RETENTION_DEFAULT)


def _cap_to_limit(raw: Any, default: float) -> Optional[float]:
    """Normalize a cap config value.

    None or 0 disables the cap (unlimited); a positive number is the limit;
    anything malformed or negative falls back to the default. Never raises.
    """
    if raw is None:
        return None
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(num):
        return default
    if num == 0:
        return None
    if num < 0:
        return default
    return num


def _read_size_cap_mb() -> Optional[float]:
    """Total-size cap in MB, or None when unlimited. Never raises."""
    try:
        raw = config_get(BACKUP_MAX_TOTAL_MB_KEY, BACKUP_MAX_TOTAL_MB_DEFAULT)
    except Exception:  # noqa: BLE001 -- best-effort, never raise
        return float(BACKUP_MAX_TOTAL_MB_DEFAULT)
    return _cap_to_limit(raw, float(BACKUP_MAX_TOTAL_MB_DEFAULT))


def _read_age_limit_days() -> Optional[float]:
    """Age limit in days, or None when unlimited. Never raises."""
    try:
        raw = config_get(BACKUP_MAX_AGE_DAYS_KEY, BACKUP_MAX_AGE_DAYS_DEFAULT)
    except Exception:  # noqa: BLE001 -- best-effort, never raise
        return float(BACKUP_MAX_AGE_DAYS_DEFAULT)
    return _cap_to_limit(raw, float(BACKUP_MAX_AGE_DAYS_DEFAULT))


def _prune_old_backups(
    project_backup_dir: Path,
    retention: int,
    protected: Collection[Path] = (),
) -> None:
    """Keep only the newest ``retention`` timestamped backup dirs.

    Only directories whose names are UTC timestamps (``%Y%m%dT%H%M%SZ``) are
    managed -- loose files and oddly-named directories are left alone (#218).
    Directories in ``protected`` (e.g. the backup just taken) are never
    removed. Directory names sort lexicographically == chronologically.
    """
    if retention < 0 or not project_backup_dir.is_dir():
        return
    protected_names = {p.name for p in protected}
    try:
        entries = [
            p
            for p in project_backup_dir.iterdir()
            if p.is_dir()
            and _parse_backup_ts(p.name) is not None
            and p.name not in protected_names
        ]
    except OSError:
        return
    entries.sort(key=lambda p: p.name)
    excess = len(entries) - max(retention, 0)
    for old_dir in entries[:max(excess, 0)]:
        shutil.rmtree(old_dir, ignore_errors=True)


def _compute_evictions(
    entries: List[_BackupEntry],
    *,
    retention: int,
    max_age_days: Optional[float],
    cap_bytes: Optional[float],
    protected: Set[str],
    now: datetime.datetime,
) -> List[_BackupEntry]:
    """Decide what the pruners would evict, without deleting anything.

    Phases, in order: count-based ``retention`` per project (skipped when
    negative), the age limit, then the total-size cap -- all oldest-first.
    Invariants: a protected path (the backup just taken) is never evicted,
    and every project keeps its newest backup.
    """
    remaining = list(entries)
    evicted: List[_BackupEntry] = []

    def _evict(victim: _BackupEntry) -> None:
        evicted.append(victim)
        remaining.remove(victim)

    def _by_project(pool: List[_BackupEntry]) -> Dict[str, List[_BackupEntry]]:
        groups: Dict[str, List[_BackupEntry]] = {}
        for entry in pool:
            groups.setdefault(entry.project, []).append(entry)
        for group in groups.values():
            group.sort(key=lambda e: e.taken)
        return groups

    def _newest(pool: List[_BackupEntry]) -> Set[int]:
        return {id(group[-1]) for group in _by_project(pool).values() if group}

    def _eligible(pool: List[_BackupEntry]) -> List[_BackupEntry]:
        newest_ids = _newest(pool)
        return [
            e
            for e in sorted(pool, key=lambda e: e.taken)
            if id(e) not in newest_ids and str(e.path) not in protected
        ]

    # 1. Count-based retention per project, applied first (#218 keeps it).
    if retention >= 0:
        for _project, group in _by_project(remaining).items():
            victims = [e for e in _eligible(group) if e in remaining]
            n_to_evict = max(0, len(group) - max(retention, 0))
            for victim in victims[:n_to_evict]:
                _evict(victim)

    # 2. Age limit: evict backups older than the limit, oldest first.
    if max_age_days is not None:
        cutoff = now - datetime.timedelta(days=max_age_days)
        for victim in _eligible(remaining):
            if victim.taken < cutoff:
                _evict(victim)

    # 3. Total-size cap: evict oldest-first until the store fits.
    if cap_bytes is not None:
        total = sum(e.size_bytes for e in remaining)
        while total > cap_bytes:
            candidates = _eligible(remaining)
            if not candidates:
                break
            victim = candidates[0]
            _evict(victim)
            total -= victim.size_bytes

    return evicted


def prune_backup_store(
    *,
    just_taken: Optional[Path] = None,
) -> Dict[str, Any]:
    """Prune the whole backup store: count retention, then age/size caps.

    Runs the per-project count-based retention first (unchanged behavior),
    then the #218 age limit and total-size cap across all projects, oldest
    first. Invariants: the backup just taken (``just_taken``) is never
    evicted, every project keeps its newest backup, loose files and
    non-timestamped directories are never touched, and nothing outside
    ``BACKUP_ROOT`` is ever considered.

    Returns ``{"removed": [str paths], "bytes_freed": int}``. Best-effort:
    never raises; each removal is logged.
    """
    report: Dict[str, Any] = {"removed": [], "bytes_freed": 0}
    try:
        if not BACKUP_ROOT.is_dir():
            return report
        protected = {just_taken} if just_taken is not None else set()
        retention = _read_retention()
        try:
            project_dirs = [p for p in BACKUP_ROOT.iterdir() if p.is_dir()]
        except OSError:
            project_dirs = []
        for project_dir in project_dirs:
            _prune_old_backups(project_dir, retention, protected)

        entries = _collect_entries()
        size_cap_mb = _read_size_cap_mb()
        victims = _compute_evictions(
            entries,
            retention=-1,  # count phase already applied above
            max_age_days=_read_age_limit_days(),
            cap_bytes=size_cap_mb * 1024 * 1024 if size_cap_mb is not None else None,
            protected={str(p) for p in protected},
            now=_utcnow(),
        )
        for victim in victims:
            try:
                shutil.rmtree(victim.path, ignore_errors=False)
            except OSError:
                continue
            if victim.path.exists():
                continue
            report["removed"].append(str(victim.path))
            report["bytes_freed"] += victim.size_bytes
            logger.info(
                "pruned backup %s (%d bytes, taken %s)",
                victim.path,
                victim.size_bytes,
                victim.taken.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
    except Exception:  # noqa: BLE001 -- best-effort, must never raise
        pass
    return report


def estimate_prune_eviction(
    project_name: str,
    new_backup_bytes: int,
) -> Dict[str, int]:
    """Dry-run of the #218 caps: what would a new backup evict? Deletes nothing.

    Simulates the age limit and total-size cap as if a ``new_backup_bytes``
    backup of ``project_name`` were taken right now (the hypothetical backup
    is protected, like the just-taken one). Count-based retention is routine
    and already disclosed by RECOVERY.md, so it is not part of this estimate.
    Returns ``{"backups": int, "bytes": int}``. Never raises.
    """
    try:
        now = _utcnow()
        entries = _collect_entries()
        sentinel = BACKUP_ROOT / project_name / "<pending-backup>"
        hypothetical = _BackupEntry(
            project_name, sentinel, now, max(int(new_backup_bytes), 0)
        )
        entries.append(hypothetical)
        size_cap_mb = _read_size_cap_mb()
        victims = _compute_evictions(
            entries,
            retention=-1,
            max_age_days=_read_age_limit_days(),
            cap_bytes=size_cap_mb * 1024 * 1024 if size_cap_mb is not None else None,
            protected={str(sentinel)},
            now=now,
        )
        victims = [v for v in victims if v.path != sentinel]
        return {
            "backups": len(victims),
            "bytes": sum(v.size_bytes for v in victims),
        }
    except Exception:  # noqa: BLE001 -- a prediction must never raise
        return {"backups": 0, "bytes": 0}


def predict_prune_eviction(project_name: str) -> Dict[str, int]:
    """What a backup of this project would evict under the #218 caps, or zeros.

    Resolves the project's .fwdata size as the incoming backup's size and
    dry-runs the caps. A prediction, never a backup: nothing is copied,
    created, or deleted. Never raises.
    """
    try:
        fwdata_path = get_project_fwdata_path(project_name)
        if fwdata_path is None:
            return {"backups": 0, "bytes": 0}
        return estimate_prune_eviction(project_name, fwdata_path.stat().st_size)
    except Exception:  # noqa: BLE001 -- a prediction must never raise
        return {"backups": 0, "bytes": 0}


def backup_store_summary() -> Dict[str, Any]:
    """Size snapshot of the backup store for flextools_health (#218).

    Reports the whole root's size (timestamped backups plus loose files, the
    latter never managed) and the effective caps. Never raises.
    """
    summary: Dict[str, Any] = {
        "root": str(BACKUP_ROOT),
        "total_bytes": 0,
        "backup_bytes": 0,
        "loose_bytes": 0,
        "projects": {},
        "caps": {
            "max_total_mb": _read_size_cap_mb(),
            "max_age_days": _read_age_limit_days(),
        },
    }
    try:
        if not BACKUP_ROOT.is_dir():
            return summary
        try:
            project_dirs = [p for p in BACKUP_ROOT.iterdir() if p.is_dir()]
        except OSError:
            return summary
        for project_dir in project_dirs:
            entries = _timestamped_entries(project_dir.name, project_dir)
            proj_bytes = sum(e.size_bytes for e in entries)
            summary["projects"][project_dir.name] = {
                "backups": len(entries),
                "bytes": proj_bytes,
            }
            summary["backup_bytes"] += proj_bytes
        summary["total_bytes"] = _dir_size_bytes(BACKUP_ROOT)
        summary["loose_bytes"] = summary["total_bytes"] - summary["backup_bytes"]
    except Exception:  # noqa: BLE001 -- diagnostics must never raise
        pass
    return summary


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
          "pruned": {                 # store prune report (#218); None when
            "backups_removed": int,   # no backup was taken
            "bytes_freed": int,
          } | None,
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
        return {"path": None, "created": False, "skipped_reason": "backup_before_write=false",
                "pruned": None}

    try:
        fwdata_path = get_project_fwdata_path(project_name)
        if fwdata_path is None:
            return {"path": None, "created": False, "skipped_reason": "project_fwdata_not_found",
                    "pruned": None}

        # Skip (with WARN, logged by the caller) if free disk < 2x project size.
        space_skip = _space_skip_reason(fwdata_path)
        if space_skip is not None:
            return {"path": None, "created": False, "skipped_reason": space_skip,
                    "pruned": None}

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
        retention = _read_retention()
        _prune_old_backups(BACKUP_ROOT / project_name,
                           max(retention, 1) if retention >= 0 else retention,
                           protected={dest_dir})

        # Issue #218: size- and age-based pruning across the whole store,
        # after the per-project count retention above. The backup just taken
        # is protected; the report says what the caps evicted.
        prune_report = prune_backup_store(just_taken=dest_dir)

        return {
            "path": str(dest_file),
            "created": True,
            "skipped_reason": None,
            "pruned": {
                "backups_removed": len(prune_report["removed"]),
                "bytes_freed": prune_report["bytes_freed"],
            },
        }
    except Exception as e:  # noqa: BLE001 - best-effort, must never raise
        return {"path": None, "created": False, "skipped_reason": f"backup_failed: {e}",
                "pruned": None}
