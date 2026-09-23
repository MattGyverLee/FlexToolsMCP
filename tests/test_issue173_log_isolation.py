"""Regression tests for issue #173 -- pytest must not write the real log tree."""

import os
from pathlib import Path

from flextoolsmcp.server.kernel import _ENV_LOG_DIR, get_log_dir


def test_pytest_uses_isolated_log_dir():
    """Guard: the suite-wide conftest hook must redirect logs away from ~."""
    configured = os.environ.get(_ENV_LOG_DIR)
    assert configured, "FLEXTOOLSMCP_LOG_DIR must be set under pytest"

    log_dir = get_log_dir()
    default_home = Path.home() / ".flextoolsmcp" / "logs"
    assert log_dir != default_home
    assert log_dir == Path(configured)


def test_get_log_dir_respects_env_override(monkeypatch, tmp_path):
    """Production override: FLEXTOOLSMCP_LOG_DIR relocates the log root."""
    target = tmp_path / "custom_logs"
    monkeypatch.setenv(_ENV_LOG_DIR, str(target))
    assert get_log_dir() == target
    assert target.is_dir()
