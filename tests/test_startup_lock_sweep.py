#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #57 (C): startup stale-lock sweep.

Verifies that sweep_stale_locks() correctly detects .fwdata.lock files for
known projects and returns appropriate warning strings.  Does NOT require a
live FieldWorks installation -- the projects directory is faked via the
FW_PROJECTS_DIR env var.
"""

from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(projects_dir: Path, project_name: str, with_lock: bool = False) -> Path:
    """Create a minimal project directory structure under projects_dir."""
    proj_dir = projects_dir / project_name
    proj_dir.mkdir(parents=True, exist_ok=True)
    fwdata = proj_dir / f"{project_name}.fwdata"
    fwdata.write_text("", encoding="utf-8")
    if with_lock:
        lock = proj_dir / f"{project_name}.fwdata.lock"
        lock.write_text("", encoding="utf-8")
    return proj_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSweepStaleLocks:
    """Tests for sweep_stale_locks()."""

    def test_no_locks_returns_empty(self, tmp_path, monkeypatch):
        """No lock files -> empty warnings list."""
        monkeypatch.setenv("FW_PROJECTS_DIR", str(tmp_path))
        _make_project(tmp_path, "MyProject", with_lock=False)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()
        assert warnings == [], f"Expected no warnings, got: {warnings}"

    def test_lock_file_detected(self, tmp_path, monkeypatch):
        """A .fwdata.lock file is reported in warnings."""
        monkeypatch.setenv("FW_PROJECTS_DIR", str(tmp_path))
        _make_project(tmp_path, "LockedProject", with_lock=True)
        _make_project(tmp_path, "CleanProject", with_lock=False)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()

        assert len(warnings) == 1, f"Expected 1 warning, got: {warnings}"
        assert "LockedProject" in warnings[0], (
            f"Warning should mention the locked project: {warnings[0]}"
        )
        assert ".fwdata.lock" in warnings[0], (
            f"Warning should mention the lock file extension: {warnings[0]}"
        )

    def test_multiple_locks_all_reported(self, tmp_path, monkeypatch):
        """Multiple lock files all appear in warnings."""
        monkeypatch.setenv("FW_PROJECTS_DIR", str(tmp_path))
        for name in ("Alpha", "Beta", "Gamma"):
            _make_project(tmp_path, name, with_lock=True)
        _make_project(tmp_path, "Clean", with_lock=False)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()

        assert len(warnings) == 3, f"Expected 3 warnings, got: {warnings}"
        locked_names = {"Alpha", "Beta", "Gamma"}
        reported = {w for w in warnings if any(n in w for n in locked_names)}
        assert len(reported) == 3, f"Not all locked projects reported: {warnings}"

    def test_unavailable_directory_returns_empty(self, tmp_path, monkeypatch):
        """If get_projects_directory() returns None, return empty list."""
        # Patch get_projects_directory so it returns None regardless of OS state.
        import server.project_discovery as pd_mod
        monkeypatch.setattr(pd_mod, "get_projects_directory", lambda: None)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()
        assert warnings == [], f"Expected no warnings when dir unavailable, got: {warnings}"

    def test_warnings_are_strings(self, tmp_path, monkeypatch):
        """Each warning in the returned list is a non-empty string."""
        monkeypatch.setenv("FW_PROJECTS_DIR", str(tmp_path))
        _make_project(tmp_path, "Locked", with_lock=True)

        from server.project_discovery import sweep_stale_locks
        warnings = sweep_stale_locks()

        for w in warnings:
            assert isinstance(w, str) and w, f"Warning should be a non-empty string: {w!r}"

    def test_sweep_logs_warning(self, tmp_path, monkeypatch, caplog):
        """Stale locks are logged at WARNING level (detection surfaced in logs)."""
        import logging
        monkeypatch.setenv("FW_PROJECTS_DIR", str(tmp_path))
        _make_project(tmp_path, "LoggedLock", with_lock=True)

        from server.project_discovery import sweep_stale_locks
        with caplog.at_level(logging.WARNING, logger="flextoolsmcp.server.project_discovery"):
            sweep_stale_locks()

        lock_logs = [r for r in caplog.records if "LoggedLock" in r.message]
        assert lock_logs, "Expected at least one WARNING log mentioning LoggedLock"
