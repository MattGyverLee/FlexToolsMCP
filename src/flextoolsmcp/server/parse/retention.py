#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run retention: keep the newest twenty runs per project (parser-check CP3,
FR-022; research.md R-03; contracts/artifact.md section 8).

THE POLICY IS ADOPTED, THE MECHANISM IS NOT. `server/backup.py`'s
`_prune_old_backups` keeps the newest N and deletes the rest -- that policy
is exactly what FR-022 asks for. Its mechanism is a lexicographic sort of
directory names, and its own docstring records why that is sound *there*:
backup directories are named by UTC timestamp, so name order is time order.
Run directories are `secrets.token_hex(16)`. Sorting them by name prunes in
effectively random order -- a week-old baseline survives while this
morning's run is deleted, and the comparison the user was about to make
loses its baseline with no error anywhere.

THE ORDERING IS `meta.json`'s `created_at`. Two tempting alternatives are
both wrong, and each has a test that fails it:

  * directory names -- opaque hex, as above;
  * `st_mtime` -- the order `record.list_run_ids()` uses, which is right for
    ITS caller (naming the handles that exist) and wrong here: mtime moves
    whenever anything later lands in the directory, a drill-down trace for
    instance, so an old run that was just inspected would look new.

A RUN THIS MODULE CANNOT DATE IS KEPT, not deleted. A directory whose
`meta.json` is missing or unreadable has no recorded creation time, and
guessing one is how a retention pass deletes the wrong thing. It also does
not count toward the twenty: it is outside the ordering, not at either end
of it.

A RUN STILL IN FLIGHT IS NEVER DELETED. The caller passes the ids it holds
live (`protect`), and they are skipped even when they fall outside the
newest twenty -- deleting a running batch's directory would make its next
`append_result` recreate a directory with no meta.json in it.

Pure server-side: no project, no pythonnet. Nothing here touches a
FieldWorks project (FR-063); it deletes only this server's own run records.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .record import get_record_dir, is_valid_run_id

__all__ = ["DEFAULT_RUNS_PER_PROJECT", "runs_by_creation", "prune_runs"]

#: FR-022 / contracts/tools.md section 5.
DEFAULT_RUNS_PER_PROJECT = 20


def _created_at(run_dir: Path) -> Optional[tuple[datetime, Optional[str]]]:
    """(creation time, project name) from `meta.json`, or None if undatable."""
    try:
        data = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        raw = data["created_at"]
        stamp = datetime.fromisoformat(str(raw))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp, data.get("project_name")


def runs_by_creation(
    project_name: Optional[str],
    *,
    record_dir: Optional[Path] = None,
) -> list[str]:
    """This project's run ids, newest first by recorded creation time.

    Undatable runs are omitted -- see the module docstring. Ties (two runs
    created in the same microsecond) break on run id so the order is total
    and repeatable; the tie-break decides nothing that matters.
    """
    root = record_dir or get_record_dir()
    if not root.is_dir():
        return []
    dated = []
    for run_dir in root.iterdir():
        if not run_dir.is_dir() or not is_valid_run_id(run_dir.name):
            continue
        info = _created_at(run_dir)
        if info is None:
            continue
        stamp, owner = info
        if owner != project_name:
            continue
        dated.append((stamp, run_dir.name))
    dated.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [run_id for _, run_id in dated]


def prune_runs(
    project_name: Optional[str],
    *,
    keep: int = DEFAULT_RUNS_PER_PROJECT,
    protect: Iterable[str] = (),
    record_dir: Optional[Path] = None,
) -> list[str]:
    """Delete this project's runs beyond the newest `keep`. Returns the ids removed.

    Other projects' runs are untouched: the twenty is per project, so a
    busy project cannot push a quiet one's baseline out.
    """
    if keep < 0:
        return []
    root = record_dir or get_record_dir()
    protected = set(protect)
    removed = []
    for run_id in runs_by_creation(project_name, record_dir=root)[keep:]:
        if run_id in protected:
            continue
        shutil.rmtree(root / run_id, ignore_errors=True)
        if not (root / run_id).exists():
            removed.append(run_id)
    return removed
