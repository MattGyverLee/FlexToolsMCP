"""Regression tests for issue #173 -- pytest must not write the real log tree."""

from pathlib import Path


def test_get_log_dir_is_isolated_under_pytest():
    from flextoolsmcp.server.kernel import get_log_dir

    real_log_dir = Path.home() / ".flextoolsmcp" / "logs"
    assert get_log_dir() != real_log_dir
    assert get_log_dir().is_dir()
