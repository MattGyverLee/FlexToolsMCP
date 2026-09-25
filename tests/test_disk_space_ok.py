"""Tests for the shared 2x free-space rule, backup.disk_space_ok (CP5 T012)."""

from flextoolsmcp.server import backup as backup_mod


class _Usage:
    def __init__(self, free):
        self.free = free


def _patch_free(monkeypatch, free):
    seen = []

    def fake(path):
        seen.append(path)
        return _Usage(free)

    monkeypatch.setattr(backup_mod.shutil, "disk_usage", fake)
    return seen


def test_enough_space_ok(monkeypatch, tmp_path):
    seen = _patch_free(monkeypatch, 2000)
    assert backup_mod.disk_space_ok(tmp_path, 1000) == (True, 2000, 2000)
    assert seen == [tmp_path]


def test_below_twice_needed_refuses(monkeypatch, tmp_path):
    _patch_free(monkeypatch, 1999)
    assert backup_mod.disk_space_ok(tmp_path, 1000) == (False, 2000, 1999)


def test_between_needed_and_twice_needed_refuses(monkeypatch, tmp_path):
    # Enough for one copy but not the 2x margin.
    _patch_free(monkeypatch, 1500)
    ok, required, free = backup_mod.disk_space_ok(tmp_path, 1000)
    assert ok is False
    assert required == 2000
    assert free == 1500


def test_unmeasurable_volume_fails_open(monkeypatch, tmp_path):
    def boom(path):
        raise OSError("no volume")

    monkeypatch.setattr(backup_mod.shutil, "disk_usage", boom)
    assert backup_mod.disk_space_ok(tmp_path, 1000) == (True, 2000, None)


def test_zero_needed_always_ok(monkeypatch, tmp_path):
    _patch_free(monkeypatch, 0)
    assert backup_mod.disk_space_ok(tmp_path, 0) == (True, 0, 0)


def test_space_skip_reason_uses_shared_rule(monkeypatch, tmp_path):
    fwdata = tmp_path / "P.fwdata"
    fwdata.write_bytes(b"x" * 100)
    _patch_free(monkeypatch, 199)
    assert backup_mod._space_skip_reason(fwdata) == "insufficient_disk_space"
    _patch_free(monkeypatch, 200)
    assert backup_mod._space_skip_reason(fwdata) is None
