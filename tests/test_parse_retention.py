#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run retention: newest twenty per project BY RECORDED CREATION TIME
(parser-check CP3, FR-022; research.md R-03; contracts/artifact.md s.8).

This file is written so that the two tempting wrong implementations FAIL,
not merely disagree:

  * sorting run-directory NAMES -- what `server/backup.py` does, soundly,
    because its directories are timestamp-named. Run directories are opaque
    hex. The fixture names the runs so name order is the REVERSE of
    creation order: a name-sorted pruner keeps exactly the wrong twenty.
  * `st_mtime` -- what `record.list_run_ids()` uses for its own caller. The
    fixture touches the OLDEST runs last, so mtime order is also the reverse
    of creation order.

Each wrong ordering is also computed here and asserted to differ from the
right answer, so the fixture cannot quietly lose its discriminating power
in a later edit.

Run with:
    python -m pytest tests/test_parse_retention.py -q
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse import retention  # noqa: E402
from flextoolsmcp.server.parse.record import list_run_ids  # noqa: E402

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _make_run(root: Path, run_id: str, *, project: str, created: datetime) -> Path:
    run_dir = root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "meta.json").write_text(
        json.dumps({
            "run_id": run_id,
            "stage": "completed",
            "project_name": project,
            "created_at": created.isoformat(),
        }),
        encoding="utf-8",
    )
    return run_dir


@pytest.fixture
def runs(tmp_path):
    """25 runs of project P. Creation order is i = 0..24 (0 oldest).

    Names DESCEND as creation ascends (`ff..`, `fe..`, ...), and the oldest
    runs are touched last, so both name order and mtime order run exactly
    backwards against creation order.
    """
    root = tmp_path / "runs"
    ids = []
    for i in range(25):
        run_id = f"{255 - i:02x}" + "0" * 30
        _make_run(root, run_id, project="P", created=BASE + timedelta(hours=i))
        ids.append(run_id)
    now = time.time()
    for i, run_id in enumerate(ids):
        # oldest run -> newest mtime
        stamp = now - i * 60
        os.utime(root / run_id, (stamp, stamp))
    return root, ids


def test_keeps_the_newest_twenty_by_created_at(runs):
    root, ids = runs
    removed = retention.prune_runs("P", record_dir=root)
    survivors = sorted(p.name for p in root.iterdir())

    assert sorted(removed) == sorted(ids[:5]), "the five OLDEST by created_at go"
    assert survivors == sorted(ids[5:])


def test_a_name_sorted_pruner_would_keep_the_wrong_runs(runs):
    root, ids = runs
    by_name_newest_first = sorted(ids, reverse=True)[:20]
    by_creation = retention.runs_by_creation("P", record_dir=root)[:20]
    assert set(by_name_newest_first) != set(by_creation), (
        "the fixture no longer distinguishes name order from creation order"
    )
    assert by_creation == list(reversed(ids))[:20]


def test_an_mtime_sorted_pruner_would_keep_the_wrong_runs(runs):
    root, ids = runs
    by_mtime = sorted(
        ids, key=lambda r: (root / r).stat().st_mtime, reverse=True
    )[:20]
    by_creation = retention.runs_by_creation("P", record_dir=root)[:20]
    assert set(by_mtime) != set(by_creation), (
        "the fixture no longer distinguishes mtime order from creation order"
    )


def test_list_run_ids_mtime_order_is_not_what_retention_uses(runs, monkeypatch):
    """Reusing list_run_ids() for retention is the named wrong mechanism."""
    root, _ = runs
    monkeypatch.setenv("FLEXTOOLSMCP_PARSE_RECORD_DIR", str(root))
    assert list_run_ids()[:20] != retention.runs_by_creation("P", record_dir=root)[:20]


def test_retention_is_per_project(tmp_path):
    root = tmp_path / "runs"
    for i in range(22):
        _make_run(root, f"{i:032x}", project="Busy", created=BASE + timedelta(minutes=i))
    quiet = _make_run(root, "a" * 32, project="Quiet", created=BASE - timedelta(days=30))

    retention.prune_runs("Busy", record_dir=root)
    assert quiet.exists(), "a busy project must not push a quiet one's baseline out"
    assert len(retention.runs_by_creation("Busy", record_dir=root)) == 20


def test_an_undatable_run_is_kept_and_not_counted(tmp_path):
    root = tmp_path / "runs"
    for i in range(21):
        _make_run(root, f"{i:032x}", project="P", created=BASE + timedelta(minutes=i))
    broken = root / ("b" * 32)
    broken.mkdir()
    (broken / "meta.json").write_text("{not json", encoding="utf-8")

    removed = retention.prune_runs("P", record_dir=root)
    assert removed == [f"{0:032x}"]
    assert broken.exists(), "a run with no readable creation time is never guessed at"


def test_a_protected_run_survives_even_when_old(tmp_path):
    root = tmp_path / "runs"
    for i in range(21):
        _make_run(root, f"{i:032x}", project="P", created=BASE + timedelta(minutes=i))
    oldest = f"{0:032x}"
    removed = retention.prune_runs("P", record_dir=root, protect=[oldest])
    assert removed == []
    assert (root / oldest).exists()


def test_only_valid_run_ids_are_considered(tmp_path):
    root = tmp_path / "runs"
    stray = root / "not-a-run"
    stray.mkdir(parents=True)
    (stray / "meta.json").write_text(
        json.dumps({"project_name": "P", "created_at": BASE.isoformat()}), encoding="utf-8"
    )
    assert retention.runs_by_creation("P", record_dir=root) == []
    retention.prune_runs("P", keep=0, record_dir=root)
    assert stray.exists()


def test_the_runner_prunes_at_creation(tmp_path):
    """Retention is wired: a new run on a full project removes the oldest."""
    import asyncio

    from flextoolsmcp.server.parse.runner import ParseRunner

    root = tmp_path / "runs"
    for i in range(20):
        _make_run(root, f"{i:032x}", project="P", created=BASE + timedelta(minutes=i))

    class Worker:
        def listen_to_run(self, *a):
            pass

        def stop_listening(self, *a):
            pass

        def is_running(self):
            return True

        async def parse_word(self, **kwargs):
            return {"parse": {"parsed": True, "analysis_count": 1}, "trace_xml": None}

    class Pool:
        async def get(self, name):
            return Worker()

        def peek(self, name):
            return None

        async def aclose(self):
            pass

    async def go():
        runner = ParseRunner(pool=Pool(), record_dir=root)
        await runner.start_run(project_name="P", wordforms=["a"])

    asyncio.run(go())
    assert not (root / f"{0:032x}").exists()
    assert len(retention.runs_by_creation("P", record_dir=root)) == 20
