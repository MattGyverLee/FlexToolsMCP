#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The per-run project copy's home, `work/<run_id>/` (parser-check CP5, FR-008,
FR-011, FR-042; research R-11; data-model sections 1-2).

WHO COPIES. Not this module: `scripts/hcparse.ps1 -Mode Generate` copies the
allowlist into `-WorkDir`. This module:
  - measures the allowlist (`<name>.fwdata` + `WritingSystemStore\\**`), for
    the free-space rule and the run record;
  - creates `work/<run_id>/` holding the marker `.flextoolsmcp-sandbox-work`
    = {"run_id", "pid", "created_at", "source_fwdata"};
  - deletes it, retrying a Windows sharing violation, and reports the
    outcome as the run meta's `copy.cleanup` / `copy.path_if_failed`;
  - checks free space before the copy (FR-012: 2x the allowlist on the
    `work/` volume, via the shared `backup.disk_space_ok`);
  - sweeps marked orphans left by dead runs (FR-011) before a server's
    first sandbox job.

ALLOWLIST, NOT EXCLUSIONS (FR-008). The lock marker, `.hg`, `LinkedFiles`,
`Backups` and everything else are left out by construction.

ROOT GUARD (data-model section 1). `delete` refuses any target that is not
strictly under `paths.work_root()` before touching anything, so no function
here can remove a user-owned sandbox or corpus, a cache entry, or anything in
a project folder. A copy still undeletable after the retries is reported as
`failed` with its path and left (marker included) for the startup sweep --
never hidden.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Union

from .. import backup as _backup
from . import paths as _paths

_log = logging.getLogger(__name__)

__all__ = [
    "MARKER_NAME",
    "ALLOWLIST_DIRS",
    "DELETE_RETRIES",
    "DELETE_RETRY_SECONDS",
    "CLEANUP_DELETED",
    "CLEANUP_FAILED",
    "CLEANUP_NOT_MADE",
    "AllowlistMeasure",
    "CleanupResult",
    "SpaceShortfall",
    "measure_allowlist",
    "check_free_space",
    "create",
    "read_marker",
    "delete",
    "sweep",
]

MARKER_NAME = ".flextoolsmcp-sandbox-work"
#: Directories copied whole, beside `<name>.fwdata` (R-11; LIVE L-1 may extend).
ALLOWLIST_DIRS = ("WritingSystemStore",)

DELETE_RETRIES = 3
DELETE_RETRY_SECONDS = 0.2

CLEANUP_DELETED = "deleted"
CLEANUP_FAILED = "failed"
CLEANUP_NOT_MADE = "not_made"

PathLike = Union[str, Path]


@dataclass(frozen=True)
class AllowlistMeasure:
    """What the copy will hold: files relative to `project_dir`, '/'-separated."""

    fwdata: Path
    project_dir: Path
    files: List[str]
    total_bytes: int


@dataclass(frozen=True)
class CleanupResult:
    """How a delete ended (the run meta's `copy` fields, data-model 6.2)."""

    cleanup: str
    path_if_failed: Optional[str]
    attempts: int

    def as_dict(self) -> dict:
        return {"cleanup": self.cleanup, "path_if_failed": self.path_if_failed}


@dataclass(frozen=True)
class SpaceShortfall:
    """FR-012 refusal figures: `needed_bytes` is 2x the allowlist size."""

    needed_bytes: int
    free_bytes: int


def _rmtree(path: PathLike) -> None:
    """The single delete seam."""
    shutil.rmtree(path)


# ---------------------------------------------------------------------------
# Allowlist measure
# ---------------------------------------------------------------------------


def measure_allowlist(fwdata: PathLike) -> AllowlistMeasure:
    """Measure `<project_dir>/<name>.fwdata` plus every file under the
    allowlisted directories. Reads metadata only; raises FileNotFoundError
    when the `.fwdata` is missing."""
    fwdata = Path(fwdata)
    if not fwdata.is_file():
        raise FileNotFoundError(f"Project file not found: {fwdata}")
    project_dir = fwdata.parent
    sizes = {fwdata.name: fwdata.stat().st_size}
    for dirname in ALLOWLIST_DIRS:
        root = project_dir / dirname
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                sizes[path.relative_to(project_dir).as_posix()] = path.stat().st_size
    files = sorted(sizes)
    return AllowlistMeasure(
        fwdata=fwdata,
        project_dir=project_dir,
        files=files,
        total_bytes=sum(sizes.values()),
    )


# ---------------------------------------------------------------------------
# Free space (FR-012)
# ---------------------------------------------------------------------------


def _nearest_existing(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return path


def check_free_space(
    fwdata: PathLike, *, measure: Optional[AllowlistMeasure] = None
) -> Optional[SpaceShortfall]:
    """None when the `work/` volume has 2x the allowlist free, else the shortfall.

    Uses the shared `backup.disk_space_ok` rule (fail-open when the volume
    cannot be measured) on the nearest existing ancestor of the work root.
    Creates nothing.
    """
    if measure is None:
        measure = measure_allowlist(fwdata)
    target = _nearest_existing(_paths.work_root())
    ok, required, free = _backup.disk_space_ok(target, measure.total_bytes)
    if ok or free is None:
        return None
    return SpaceShortfall(needed_bytes=required, free_bytes=free)


# ---------------------------------------------------------------------------
# create / marker
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create(run_id: str, *, source_fwdata: PathLike, pid: Optional[int] = None) -> Path:
    """Make `work/<run_id>/` with its marker and return its real path.

    `paths.work_dir` validates the run id (SandboxPathError) and the root
    (ArtifactInsideProject) before anything is created. An existing
    directory raises FileExistsError.
    """
    directory = _paths.work_dir(run_id)
    directory.mkdir(parents=True, exist_ok=False)
    try:
        marker = {
            "run_id": run_id,
            "pid": os.getpid() if pid is None else int(pid),
            "created_at": _utc_now(),
            "source_fwdata": os.path.abspath(source_fwdata),
        }
        (directory / MARKER_NAME).write_text(json.dumps(marker, indent=2), encoding="utf-8")
    except BaseException:
        # Pattern audit sweep 2: an unmarked directory is invisible to the
        # startup sweep, so remove the one this call made (the guarded
        # `delete`, strictly under work/) before re-raising.
        try:
            delete(directory)
        except Exception:  # noqa: BLE001 -- the original failure is the one to report
            _log.warning("workdir: could not remove unmarked %s", directory, exc_info=True)
        raise
    return directory


def read_marker(directory: PathLike) -> Optional[dict]:
    """The marker's contents, or None when it is absent or unreadable."""
    try:
        data = json.loads((Path(directory) / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def delete(target: PathLike) -> CleanupResult:
    """Delete a copy under `work/`, retrying; never raises for a failed delete.

    Raises `paths.SandboxPathError` (touching nothing) when `target` is not
    strictly under the work root.
    """
    real = _paths.assert_under(target, _paths.work_root())
    if not os.path.lexists(real):
        return CleanupResult(CLEANUP_NOT_MADE, None, 0)
    attempts = 0
    for attempt in range(1 + DELETE_RETRIES):
        if attempt:
            time.sleep(DELETE_RETRY_SECONDS)
        attempts += 1
        try:
            _rmtree(real)
        except FileNotFoundError:
            if not os.path.lexists(real):
                return CleanupResult(CLEANUP_DELETED, None, attempts)
        except OSError:
            continue
        else:
            return CleanupResult(CLEANUP_DELETED, None, attempts)
    return CleanupResult(CLEANUP_FAILED, str(real), attempts)


# ---------------------------------------------------------------------------
# Startup sweep (FR-011)
# ---------------------------------------------------------------------------


def sweep(live_run_ids: Iterable[str]) -> List[Path]:
    """Remove marked copies under `work/` whose run is not live; return them.

    Only direct children of the work root that hold a readable marker are
    candidates. A child is live when its directory name or its marker's
    `run_id` is in `live_run_ids`. Every delete goes through `delete`, so the
    root guard holds; a child that will not delete is left for next time.
    """
    live = {str(run_id) for run_id in live_run_ids}
    root = _paths.work_root()
    if not root.is_dir():
        return []
    removed: List[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.is_symlink():
            continue
        marker = read_marker(child)
        if marker is None:
            continue
        if child.name in live or str(marker.get("run_id")) in live:
            continue
        try:
            result = delete(child)
        except _paths.SandboxPathError:
            continue
        if result.cleanup == CLEANUP_DELETED:
            removed.append(child)
    return removed
