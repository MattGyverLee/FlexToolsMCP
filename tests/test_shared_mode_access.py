#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #93 CP2: the shared-mode access probe (project_access.py).

Follows the shape of tests/test_startup_lock_sweep.py: the projects tree is
faked via the FW_PROJECTS_DIR env var, never a real FieldWorks install.
Real-shaped .fwdata.lock JSON (including the "__type" key, and a genuine
.NET-ticks Timestamp) and .plsx files are written to disk; _pid_is_alive is
monkeypatched for the alive/dead split so nothing here depends on a real PID.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# Verbatim shape from the live probe (SPEC Section 1 fact 4 + the amendment):
# one line, no trailing newline, carrying the Palaso.IO.FileLock "__type" key
# that the SPEC text doesn't mention but that real lock files do carry.
REAL_LOCK_JSON = (
    '{"__type":"FileLockContent:#Palaso.IO.FileLock","PID":68436,'
    '"ProcessName":"FieldWorks","Timestamp":639222387834226079}'
)
REAL_LOCK_TICKS = 639222387834226079


def _make_project(projects_dir: Path, project_name: str) -> Path:
    proj_dir = projects_dir / project_name
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / f"{project_name}.fwdata").write_text("", encoding="utf-8")
    return proj_dir


def _write_lock(proj_dir: Path, project_name: str, content: str) -> Path:
    lock_path = proj_dir / f"{project_name}.fwdata.lock"
    lock_path.write_text(content, encoding="utf-8")
    return lock_path


def _write_plsx(proj_dir: Path, sharing: str) -> Path:
    shared_dir = proj_dir / "SharedSettings"
    shared_dir.mkdir(parents=True, exist_ok=True)
    plsx_path = shared_dir / "LexiconSettings.plsx"
    plsx_path.write_text(
        f'<?xml version="1.0"?>\n<ProjectLexiconSettings projectSharing="{sharing}"/>\n',
        encoding="utf-8",
    )
    return plsx_path


@pytest.fixture
def fw_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FW_PROJECTS_DIR", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# read_lock_holder()
# ---------------------------------------------------------------------------

class TestReadLockHolder:
    def test_no_lock_file_returns_none(self, fw_dir):
        _make_project(fw_dir, "NoLock")
        from server.project_access import read_lock_holder
        assert read_lock_holder("NoLock") is None

    def test_real_shaped_lock_parses_ignoring_type_key(self, fw_dir):
        proj_dir = _make_project(fw_dir, "Claude-Swahili")
        _write_lock(proj_dir, "Claude-Swahili", REAL_LOCK_JSON)

        from server.project_access import read_lock_holder
        holder = read_lock_holder("Claude-Swahili")

        assert holder is not None
        assert holder.pid == 68436
        assert holder.process_name == "FieldWorks"
        assert holder.timestamp_ticks == REAL_LOCK_TICKS

    def test_empty_lock_file_returns_unknown_holder(self, fw_dir):
        """tests/test_startup_lock_sweep.py writes lock files with empty
        content -- this path is live and must not raise."""
        proj_dir = _make_project(fw_dir, "EmptyLock")
        _write_lock(proj_dir, "EmptyLock", "")

        from server.project_access import read_lock_holder
        holder = read_lock_holder("EmptyLock")

        assert holder is not None
        assert holder.pid is None
        assert holder.process_name is None
        assert holder.timestamp_ticks is None

    def test_non_json_lock_file_returns_unknown_holder(self, fw_dir):
        proj_dir = _make_project(fw_dir, "GarbageLock")
        _write_lock(proj_dir, "GarbageLock", "not json at all {{{")

        from server.project_access import read_lock_holder
        holder = read_lock_holder("GarbageLock")

        assert holder is not None
        assert holder.pid is None
        assert holder.process_name is None
        assert holder.timestamp_ticks is None

    def test_lock_json_missing_keys_returns_unknown_holder(self, fw_dir):
        proj_dir = _make_project(fw_dir, "PartialLock")
        _write_lock(proj_dir, "PartialLock", '{"SomeOtherKey": 1}')

        from server.project_access import read_lock_holder
        holder = read_lock_holder("PartialLock")

        assert holder is not None
        assert holder.pid is None
        assert holder.process_name is None
        assert holder.timestamp_ticks is None

    def test_lock_json_array_not_object_returns_unknown_holder(self, fw_dir):
        proj_dir = _make_project(fw_dir, "ArrayLock")
        _write_lock(proj_dir, "ArrayLock", "[1, 2, 3]")

        from server.project_access import read_lock_holder
        holder = read_lock_holder("ArrayLock")

        assert holder is not None
        assert holder.pid is None


# ---------------------------------------------------------------------------
# _ticks_to_age_seconds()
# ---------------------------------------------------------------------------

class TestTicksToAgeSeconds:
    def test_known_tick_value_converts_correctly(self):
        """639222387834226079 ticks is a verified 2026 date (SPEC amendment).
        A naive Unix-epoch interpretation would put this thousands of years
        in the future or past; the correct .NET-ticks conversion puts it
        within the last few minutes/hours/days of "now" during this cycle."""
        from server.project_access import _ticks_to_age_seconds, _TICKS_EPOCH

        expected_dt = _TICKS_EPOCH + timedelta(microseconds=REAL_LOCK_TICKS / 10)
        expected_age = (datetime.now() - expected_dt).total_seconds()

        age = _ticks_to_age_seconds(REAL_LOCK_TICKS)

        assert age is not None
        assert abs(age - expected_age) < 5.0
        # Sanity bound: correct conversion keeps this within recent history,
        # not centuries away (the naive-epoch failure mode this test guards
        # against).
        assert -3600 < age < 60 * 60 * 24 * 400

    def test_missing_ticks_returns_none(self):
        from server.project_access import _ticks_to_age_seconds
        assert _ticks_to_age_seconds(None) is None

    def test_garbage_ticks_returns_none(self):
        """An absurdly large Timestamp must not raise -- return None."""
        from server.project_access import _ticks_to_age_seconds
        assert _ticks_to_age_seconds(10 ** 30) is None


# ---------------------------------------------------------------------------
# is_project_sharing_enabled()
# ---------------------------------------------------------------------------

class TestIsProjectSharingEnabled:
    def test_sharing_true(self, fw_dir):
        proj_dir = _make_project(fw_dir, "Claude-Swahili")
        _write_plsx(proj_dir, "true")

        from server.project_access import is_project_sharing_enabled
        assert is_project_sharing_enabled("Claude-Swahili") is True

    def test_sharing_false(self, fw_dir):
        proj_dir = _make_project(fw_dir, "Target")
        _write_plsx(proj_dir, "false")

        from server.project_access import is_project_sharing_enabled
        assert is_project_sharing_enabled("Target") is False

    def test_missing_plsx_is_false(self, fw_dir):
        _make_project(fw_dir, "NoSharedSettings")

        from server.project_access import is_project_sharing_enabled
        assert is_project_sharing_enabled("NoSharedSettings") is False

    def test_malformed_plsx_is_none(self, fw_dir):
        proj_dir = _make_project(fw_dir, "BadXml")
        shared_dir = proj_dir / "SharedSettings"
        shared_dir.mkdir(parents=True, exist_ok=True)
        (shared_dir / "LexiconSettings.plsx").write_text(
            "<not><valid xml", encoding="utf-8"
        )

        from server.project_access import is_project_sharing_enabled
        assert is_project_sharing_enabled("BadXml") is None

    def test_missing_attribute_is_false(self, fw_dir):
        proj_dir = _make_project(fw_dir, "NoAttr")
        shared_dir = proj_dir / "SharedSettings"
        shared_dir.mkdir(parents=True, exist_ok=True)
        (shared_dir / "LexiconSettings.plsx").write_text(
            '<?xml version="1.0"?>\n<ProjectLexiconSettings/>\n', encoding="utf-8"
        )

        from server.project_access import is_project_sharing_enabled
        assert is_project_sharing_enabled("NoAttr") is False


# ---------------------------------------------------------------------------
# probe_project_access() -- the full verdict matrix
# ---------------------------------------------------------------------------

class TestProbeProjectAccess:
    def test_no_lock_file_is_free(self, fw_dir):
        proj_dir = _make_project(fw_dir, "FreeProject")
        _write_plsx(proj_dir, "true")

        from server.project_access import probe_project_access
        access = probe_project_access("FreeProject")

        assert access.verdict == "free"
        assert access.holder is None
        assert access.lock_age_seconds is None
        assert access.sharing_enabled is True

    def test_live_fieldworks_with_sharing_on_is_open_shared(self, fw_dir, monkeypatch):
        proj_dir = _make_project(fw_dir, "Claude-Swahili")
        _write_lock(proj_dir, "Claude-Swahili", REAL_LOCK_JSON)
        _write_plsx(proj_dir, "true")

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: True)

        access = pa.probe_project_access("Claude-Swahili")

        assert access.verdict == "open_shared"
        assert access.sharing_enabled is True
        assert access.holder.pid == 68436
        assert access.holder.process_name == "FieldWorks"
        assert access.lock_age_seconds is not None

    def test_live_fieldworks_with_sharing_off_is_open_exclusive(self, fw_dir, monkeypatch):
        proj_dir = _make_project(fw_dir, "Target")
        _write_lock(proj_dir, "Target", REAL_LOCK_JSON)
        _write_plsx(proj_dir, "false")

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: True)

        access = pa.probe_project_access("Target")

        assert access.verdict == "open_exclusive"
        assert access.sharing_enabled is False

    def test_dead_fieldworks_pid_is_stale_lock(self, fw_dir, monkeypatch):
        """French-FLExTrans-Exp5 / Puguli case: real FieldWorks lock, but the
        process is dead."""
        proj_dir = _make_project(fw_dir, "French-FLExTrans-Exp5")
        _write_lock(proj_dir, "French-FLExTrans-Exp5", REAL_LOCK_JSON)
        _write_plsx(proj_dir, "false")

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: False)

        access = pa.probe_project_access("French-FLExTrans-Exp5")

        assert access.verdict == "stale_lock"

    def test_dead_non_fieldworks_pid_is_stale_lock_not_held_by_other(self, fw_dir, monkeypatch):
        """The Target scenario from the live probe: ProcessName "python" (a
        leftover MCP subprocess), but the PID is dead -- dead always wins
        over "who was it"."""
        proj_dir = _make_project(fw_dir, "Target")
        lock_json = (
            '{"__type":"FileLockContent:#Palaso.IO.FileLock","PID":54480,'
            '"ProcessName":"python","Timestamp":639222387834226079}'
        )
        _write_lock(proj_dir, "Target", lock_json)
        _write_plsx(proj_dir, "false")

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: False)

        access = pa.probe_project_access("Target")

        assert access.verdict == "stale_lock"
        assert access.holder.process_name == "python"

    def test_live_non_fieldworks_pid_is_held_by_other(self, fw_dir, monkeypatch):
        """A live, non-FieldWorks holder is a genuine collision -- the case
        the pre-CP2 code could not express."""
        proj_dir = _make_project(fw_dir, "Target")
        lock_json = (
            '{"__type":"FileLockContent:#Palaso.IO.FileLock","PID":54480,'
            '"ProcessName":"python","Timestamp":639222387834226079}'
        )
        _write_lock(proj_dir, "Target", lock_json)
        _write_plsx(proj_dir, "false")

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: True)

        access = pa.probe_project_access("Target")

        assert access.verdict == "held_by_other"
        assert access.holder.process_name == "python"
        assert access.holder.pid == 54480

    def test_empty_lock_falls_back_to_open_exclusive(self, fw_dir):
        """Holder unknown (empty lock file) -- cannot verify liveness or
        identity; fall back to the pre-CP2 behavior of treating any existing
        lock as exclusively held."""
        proj_dir = _make_project(fw_dir, "EmptyLockProject")
        _write_lock(proj_dir, "EmptyLockProject", "")
        _write_plsx(proj_dir, "true")

        from server.project_access import probe_project_access
        access = probe_project_access("EmptyLockProject")

        assert access.verdict == "open_exclusive"
        assert access.lock_age_seconds is None

    def test_malformed_lock_falls_back_to_open_exclusive(self, fw_dir):
        proj_dir = _make_project(fw_dir, "GarbageLockProject")
        _write_lock(proj_dir, "GarbageLockProject", "{{not json")

        from server.project_access import probe_project_access
        access = probe_project_access("GarbageLockProject")

        assert access.verdict == "open_exclusive"

    def test_garbage_timestamp_yields_none_age_not_crash(self, fw_dir, monkeypatch):
        proj_dir = _make_project(fw_dir, "GarbageTimestamp")
        lock_json = (
            '{"PID":123,"ProcessName":"FieldWorks","Timestamp":"not-a-number"}'
        )
        _write_lock(proj_dir, "GarbageTimestamp", lock_json)
        _write_plsx(proj_dir, "true")

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: True)

        access = pa.probe_project_access("GarbageTimestamp")

        # Timestamp was a string, not an int -- read_lock_holder discards it.
        assert access.holder.timestamp_ticks is None
        assert access.lock_age_seconds is None
        assert access.verdict == "open_shared"

    def test_unresolvable_projects_dir_is_free(self, monkeypatch):
        import server.project_access as pa
        monkeypatch.setattr(pa, "get_projects_directory", lambda: None)

        access = pa.probe_project_access("Anything")

        assert access.verdict == "free"
        assert access.sharing_enabled is None
        assert access.holder is None


# ---------------------------------------------------------------------------
# _pid_is_alive() -- a light real-world smoke test (current process is alive,
# a PID of 0/negative is treated as not-alive). No dependency on FieldWorks.
# ---------------------------------------------------------------------------

class TestPidIsAlive:
    def test_current_process_is_alive(self):
        import os
        from server.project_access import _pid_is_alive
        assert _pid_is_alive(os.getpid()) is True

    def test_non_positive_pid_is_not_alive(self):
        from server.project_access import _pid_is_alive
        assert _pid_is_alive(0) is False
        assert _pid_is_alive(-1) is False
        assert _pid_is_alive(None) is False


# ---------------------------------------------------------------------------
# sweep_stale_locks(): holder-aware warning strings (T2.6)
# ---------------------------------------------------------------------------

class TestSweepStaleLocksHolderAware:
    def test_warning_names_live_holder(self, fw_dir, monkeypatch):
        proj_dir = _make_project(fw_dir, "Claude-Swahili")
        _write_lock(proj_dir, "Claude-Swahili", REAL_LOCK_JSON)

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: True)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()

        assert len(warnings) == 1
        assert "FieldWorks" in warnings[0]
        assert "68436" in warnings[0]
        assert "still running" in warnings[0]

    def test_warning_names_dead_holder(self, fw_dir, monkeypatch):
        proj_dir = _make_project(fw_dir, "French-FLExTrans-Exp5")
        _write_lock(proj_dir, "French-FLExTrans-Exp5", REAL_LOCK_JSON)

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: False)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()

        assert len(warnings) == 1
        assert "no longer running (stale)" in warnings[0]

    def test_warning_names_non_fieldworks_holder(self, fw_dir, monkeypatch):
        """The Target scenario: a live, non-FieldWorks holder must be
        nameable -- the exact gap the old mtime-only sweep could not close."""
        proj_dir = _make_project(fw_dir, "Target")
        lock_json = (
            '{"__type":"FileLockContent:#Palaso.IO.FileLock","PID":54480,'
            '"ProcessName":"python","Timestamp":639222387834226079}'
        )
        _write_lock(proj_dir, "Target", lock_json)

        import server.project_access as pa
        monkeypatch.setattr(pa, "_pid_is_alive", lambda pid: True)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()

        assert len(warnings) == 1
        assert "python" in warnings[0]
        assert "54480" in warnings[0]
        assert "still running" in warnings[0]

    def test_unreadable_lock_is_reported_as_exclusively_held(self, fw_dir):
        """Issue #93 cycle 7 (P1-companion, lock-site-inventory.md /
        cycle7-qc.md): this test used to assert "Stale lock detected" from
        an empty/unreadable lock file, with a docstring claiming
        tests/test_startup_lock_sweep.py required that exact wording.
        That claim was independently verified FALSE by both lex-lead and
        the mechanical inventory -- `grep -c "Stale lock detected"
        tests/test_startup_lock_sweep.py` returns 0; that file's only
        wording assertions (lines 47-62) check for the project name and
        the substring ".fwdata.lock", both wording-agnostic. The original
        wording was also the confirmed P1 defect: declaring "Stale" and
        "Close FieldWorks" from an UNKNOWN holder inverts
        probe_project_access's documented safe fallback (unknown holder
        -> open_exclusive). This test now pins the corrected wording."""
        proj_dir = _make_project(fw_dir, "LockedProject")
        _write_lock(proj_dir, "LockedProject", "")

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()

        assert len(warnings) == 1
        assert "could not be identified" in warnings[0]
        assert "exclusively held" in warnings[0]
        assert "Stale lock detected" not in warnings[0]
        assert "LockedProject" in warnings[0]
        assert ".fwdata.lock" in warnings[0]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
