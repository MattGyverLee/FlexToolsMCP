#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #218: size- and age-based pruning for ~/.flextoolsmcp/backups.

Count-based `backup_retention` alone does not bound disk use, so two new
config knobs join it (applied after the count retention):

- `backup_max_total_mb` (default 2048): total size cap across ALL projects'
  timestamped backups; the oldest backups are evicted first when exceeded.
- `backup_max_age_days` (default 180): backups older than the limit are
  evicted, oldest first.

Acceptance criteria covered here:
- the size cap evicts oldest-first across projects;
- the newest backup of every project is never evicted;
- the backup just taken survives;
- loose files (and non-timestamped directories) are left alone;
- malformed config values fall back to defaults and never fail a write.
- no change to the backup *intent* rules (covered by the #55 suite).

Also covered: the count retention is applied before the caps, the dry-run
estimate deletes nothing, the store summary reports sizes and caps, and the
filing plan discloses expected evictions.
"""

import time as _time

import pytest

from flextoolsmcp.server import backup as backup_mod
from flextoolsmcp.server import write_ladder
from flextoolsmcp.server.filing import plan as filing_plan


ONE_MB = 1024 * 1024


def _make_backup(root, project, ts_name, size_bytes=ONE_MB):
    """Create a timestamped backup dir with a file of the given size."""
    dest = root / project / ts_name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{project}.fwdata").write_bytes(b"x" * size_bytes)
    return dest


def _names(root, project):
    return sorted(p.name for p in (root / project).iterdir())


def _config(monkeypatch, **overrides):
    """Stub config_get: overrides win, everything else falls to defaults."""

    def _fake(key, default):
        return overrides.get(key, default)

    monkeypatch.setattr(backup_mod, "config_get", _fake)


def _caps_off(monkeypatch):
    """Disable the #218 caps; count retention stays at its default."""
    _config(
        monkeypatch,
        **{
            backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 0,
            backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 0,
        },
    )


@pytest.fixture()
def store(monkeypatch, tmp_path):
    """An isolated backup store: BACKUP_ROOT points at tmp_path."""
    root = tmp_path / "backups"
    root.mkdir()
    monkeypatch.setattr(backup_mod, "BACKUP_ROOT", root)
    return root


class TestSizeCap:
    def test_evicts_oldest_first_across_projects(self, monkeypatch, store):
        for proj in ("ProjA", "ProjB"):
            for ts in ("20260101T000000Z", "20260201T000000Z", "20260301T000000Z"):
                _make_backup(store, proj, ts)
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 4,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 0,
            },
        )
        report = backup_mod.prune_backup_store()
        # 6 MB over a 4 MB cap: the two oldest dirs go, one per project.
        assert report["bytes_freed"] == 2 * ONE_MB
        assert len(report["removed"]) == 2
        assert _names(store, "ProjA") == ["20260201T000000Z", "20260301T000000Z"]
        assert _names(store, "ProjB") == ["20260201T000000Z", "20260301T000000Z"]

    def test_newest_backup_per_project_never_evicted(self, monkeypatch, store):
        # A single 10 MB backup over a 1 MB cap: nothing may go -- it is the
        # project's newest (and only) backup.
        _make_backup(store, "Lonely", "20260101T000000Z", size_bytes=10 * ONE_MB)
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 1,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 0,
            },
        )
        report = backup_mod.prune_backup_store()
        assert report["removed"] == []
        assert _names(store, "Lonely") == ["20260101T000000Z"]

    def test_just_taken_backup_survives(self, monkeypatch, store, tmp_path):
        fwdata = tmp_path / "Tiny.fwdata"
        fwdata.write_bytes(b"x" * 100)
        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: fwdata)
        # A cap far below the incoming backup's own size: the backup just
        # taken must still exist afterwards.
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 0.00001,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 0,
                backup_mod.BACKUP_RETENTION_KEY: 5,
            },
        )
        fake_time = _time.gmtime(_time.time())
        monkeypatch.setattr(_time, "gmtime", lambda *a, _ft=fake_time: _ft)
        result = backup_mod.perform_pre_write_backup("Tiny")
        assert result["created"] is True
        assert result["path"] is not None
        from pathlib import Path

        assert Path(result["path"]).exists()
        assert result["pruned"] is not None

    def test_count_retention_applied_first(self, monkeypatch, store):
        for ts in ("20260101T000000Z", "20260201T000000Z", "20260301T000000Z"):
            _make_backup(store, "Many", ts)
        # retention=1 with the caps off: only the newest survives.
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_RETENTION_KEY: 1,
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 0,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 0,
            },
        )
        backup_mod.prune_backup_store()
        assert _names(store, "Many") == ["20260301T000000Z"]


class TestAgeLimit:
    def test_evicts_old_backups_oldest_first(self, monkeypatch, store):
        _make_backup(store, "Old", "20200101T000000Z")
        _make_backup(store, "Old", "20210101T000000Z")
        _make_backup(store, "Old", "20260101T000000Z")
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 0,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 30,
                backup_mod.BACKUP_RETENTION_KEY: 5,
            },
        )
        # Freeze "now" well after the newest backup so only the two older
        # dirs are past the 30-day limit.
        _freeze_now(monkeypatch, 2026, 6, 15)
        report = backup_mod.prune_backup_store()
        assert len(report["removed"]) == 2
        assert _names(store, "Old") == ["20260101T000000Z"]

    def test_newest_kept_even_when_older_than_limit(self, monkeypatch, store):
        _make_backup(store, "Ancient", "20200101T000000Z")
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 0,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 30,
                backup_mod.BACKUP_RETENTION_KEY: 5,
            },
        )
        _freeze_now(monkeypatch, 2026, 6, 15)
        report = backup_mod.prune_backup_store()
        # The only backup is also the newest: the age limit cannot take it.
        assert report["removed"] == []
        assert _names(store, "Ancient") == ["20200101T000000Z"]


def _freeze_now(monkeypatch, year, month, day):
    """Freeze backup_mod's clock for age-limit tests."""
    import datetime

    frozen = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    monkeypatch.setattr(backup_mod, "_utcnow", lambda: frozen)


class TestLooseFilesUntouched:
    def test_loose_files_and_odd_dirs_left_alone(self, monkeypatch, store):
        _make_backup(store, "Proj", "20260101T000000Z")
        _make_backup(store, "Proj", "20200101T000000Z")
        # Loose file (the before-restore.fwdata RECOVERY.md suggests) and an
        # oddly-named directory: neither is managed by any pruner.
        (store / "Proj" / "before-restore.fwdata").write_bytes(b"y" * 500)
        odd = store / "Proj" / "manual-copy"
        odd.mkdir()
        (odd / "data.bin").write_bytes(b"z" * 500)
        # Aggressive caps: 0 MB total and a 1-day age limit.
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 0.000001,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 1,
                backup_mod.BACKUP_RETENTION_KEY: 5,
            },
        )
        _freeze_now(monkeypatch, 2026, 6, 15)
        backup_mod.prune_backup_store()
        remaining = _names(store, "Proj")
        assert "before-restore.fwdata" in remaining
        assert "manual-copy" in remaining
        assert (odd / "data.bin").exists()
        # The old timestamped dir is gone; the newest survives the 0 MB cap.
        assert "20200101T000000Z" not in remaining
        assert "20260101T000000Z" in remaining


class TestMalformedConfig:
    @pytest.mark.parametrize(
        "key,bad",
        [
            (backup_mod.BACKUP_MAX_TOTAL_MB_KEY, "huge"),
            (backup_mod.BACKUP_MAX_TOTAL_MB_KEY, -5),
            (backup_mod.BACKUP_MAX_TOTAL_MB_KEY, float("nan")),
            (backup_mod.BACKUP_MAX_AGE_DAYS_KEY, "forever"),
            (backup_mod.BACKUP_MAX_AGE_DAYS_KEY, -1),
            (backup_mod.BACKUP_RETENTION_KEY, "many"),
        ],
    )
    def test_falls_back_to_defaults(self, monkeypatch, key, bad):
        _config(monkeypatch, **{key: bad})
        if key == backup_mod.BACKUP_MAX_TOTAL_MB_KEY:
            assert backup_mod._read_size_cap_mb() == float(
                backup_mod.BACKUP_MAX_TOTAL_MB_DEFAULT
            )
        elif key == backup_mod.BACKUP_MAX_AGE_DAYS_KEY:
            assert backup_mod._read_age_limit_days() == float(
                backup_mod.BACKUP_MAX_AGE_DAYS_DEFAULT
            )
        else:
            assert backup_mod._read_retention() == int(
                backup_mod.BACKUP_RETENTION_DEFAULT
            )

    def test_zero_and_null_disable_caps(self, monkeypatch):
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 0,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: None,
            },
        )
        assert backup_mod._read_size_cap_mb() is None
        assert backup_mod._read_age_limit_days() is None

    def test_malformed_config_never_fails_a_write(self, monkeypatch, store, tmp_path):
        fwdata = tmp_path / "P.fwdata"
        fwdata.write_bytes(b"x" * 100)
        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: fwdata)
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: "huge",
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: "forever",
                backup_mod.BACKUP_RETENTION_KEY: "many",
            },
        )
        fake_time = _time.gmtime(_time.time())
        monkeypatch.setattr(_time, "gmtime", lambda *a, _ft=fake_time: _ft)
        result = backup_mod.perform_pre_write_backup("P")
        assert result["created"] is True
        assert result["skipped_reason"] is None


class TestEstimateAndSummary:
    def test_estimate_deletes_nothing(self, monkeypatch, store):
        _make_backup(store, "A", "20260101T000000Z")
        _make_backup(store, "A", "20260201T000000Z")
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 2,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 0,
            },
        )
        before = _names(store, "A")
        estimate = backup_mod.estimate_prune_eviction("A", ONE_MB)
        # 2 MB stored + 1 MB incoming over a 2 MB cap: one eviction expected.
        assert estimate == {"backups": 1, "bytes": ONE_MB}
        assert _names(store, "A") == before

    def test_estimate_zero_when_caps_disabled(self, monkeypatch, store):
        _make_backup(store, "A", "20260101T000000Z")
        _caps_off(monkeypatch)
        assert backup_mod.estimate_prune_eviction("A", 10 * ONE_MB) == {
            "backups": 0,
            "bytes": 0,
        }

    def test_summary_reports_sizes_and_caps(self, monkeypatch, store):
        _make_backup(store, "A", "20260101T000000Z")
        (store / "A" / "before-restore.fwdata").write_bytes(b"y" * 500)
        _caps_off(monkeypatch)
        summary = backup_mod.backup_store_summary()
        assert summary["root"] == str(store)
        assert summary["projects"]["A"]["backups"] == 1
        assert summary["projects"]["A"]["bytes"] == ONE_MB
        assert summary["backup_bytes"] == ONE_MB
        assert summary["loose_bytes"] == 500
        assert summary["total_bytes"] == ONE_MB + 500
        assert summary["caps"] == {"max_total_mb": None, "max_age_days": None}

    def test_prune_never_raises_on_missing_root(self, monkeypatch, tmp_path):
        monkeypatch.setattr(backup_mod, "BACKUP_ROOT", tmp_path / "does-not-exist")
        assert backup_mod.prune_backup_store() == {
            "removed": [],
            "bytes_freed": 0,
        }
        assert backup_mod.backup_store_summary()["projects"] == {}


class TestPlanDisclosure:
    def test_backup_intent_carries_prune_eviction(self, monkeypatch, store, tmp_path):
        _make_backup(store, "FileMe", "20260101T000000Z")
        _make_backup(store, "FileMe", "20260201T000000Z")
        fwdata = tmp_path / "FileMe.fwdata"
        fwdata.write_bytes(b"x" * ONE_MB)
        monkeypatch.setattr(backup_mod, "get_project_fwdata_path", lambda name: fwdata)
        _config(
            monkeypatch,
            **{
                backup_mod.BACKUP_MAX_TOTAL_MB_KEY: 2,
                backup_mod.BACKUP_MAX_AGE_DAYS_KEY: 0,
            },
        )

        class _Session:
            def was_backed_up(self, name):
                return False

        intent = write_ladder.backup_intent(
            "FileMe",
            session_state=_Session(),
            session_key=write_ladder.FILING_BACKUP_KEY,
            once_per_session=False,
            predict_skips=True,
        )
        assert intent.outcome == "will_be_taken"
        assert intent.details["prune_eviction"] == {
            "backups": 1,
            "bytes": ONE_MB,
        }

    def test_plan_backup_block_discloses_eviction(self):
        plan, _plan_id = filing_plan.build_plan(
            scope={"kind": "all", "value": None, "limit": None},
            scope_fingerprint_key="k",
            words_in_scope=3,
            gate={},
            projection=_FakeProjection(),
            duplicate_disclosure={},
            backup={
                "outcome": "will_be_taken",
                "reason": None,
                "prune_eviction": {"backups": 2, "bytes": 3 * ONE_MB},
            },
            access={},
            send_receive=None,
            require_write_confirmation=True,
        )
        assert plan["backup"]["prune_eviction"] == {
            "backups": 2,
            "bytes": 3 * ONE_MB,
        }

    def test_plan_backup_block_omits_eviction_when_absent(self):
        plan, _plan_id = filing_plan.build_plan(
            scope={"kind": "all", "value": None, "limit": None},
            scope_fingerprint_key="k",
            words_in_scope=3,
            gate={},
            projection=_FakeProjection(),
            duplicate_disclosure={},
            backup={"outcome": "will_be_taken", "reason": None},
            access={},
            send_receive=None,
            require_write_confirmation=True,
        )
        assert "prune_eviction" not in plan["backup"]


class _FakeProjection:
    deletion = {"upper_bound": 0}
    disapproval_overwrites = {}
    in_use_approvals_projected = 0
