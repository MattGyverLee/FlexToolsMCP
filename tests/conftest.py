#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pytest configuration and shared fixtures."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Add src and src/flextoolsmcp to path (shared across all tests).
# Tests import both `from flextoolsmcp.xxx` (package form) and
# `from server.xxx` (legacy bare form); both must resolve.
src_path = str(Path(__file__).parent.parent / "src")
pkg_path = str(Path(__file__).parent.parent / "src" / "flextoolsmcp")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
if pkg_path not in sys.path:
    sys.path.insert(0, pkg_path)

# Issue #173: isolate logs for the whole suite before any test module imports
# flextoolsmcp.server.kernel (several test files import kernel at collection time).
_PYTEST_LOG_DIR: Path | None = None


def pytest_configure(config):
    """Isolate logging for the whole test run (issue #173).

    Must run before any test module imports ``kernel.setup_logging``.
    """
    global _PYTEST_LOG_DIR
    if os.environ.get("FLEXTOOLSMCP_LOG_DIR"):
        return
    _PYTEST_LOG_DIR = Path(tempfile.mkdtemp(prefix="flextoolsmcp_pytest_logs_"))
    os.environ["FLEXTOOLSMCP_LOG_DIR"] = str(_PYTEST_LOG_DIR)


def pytest_unconfigure(config):
    global _PYTEST_LOG_DIR
    if _PYTEST_LOG_DIR is not None and _PYTEST_LOG_DIR.exists():
        shutil.rmtree(_PYTEST_LOG_DIR, ignore_errors=True)
    _PYTEST_LOG_DIR = None


@pytest.fixture
def reset_session_state():
    """Reset session state for tests that need a clean state.

    Consolidates duplicate session reset patterns from multiple test files.
    Usage: add 'reset_session_state' parameter to test function.
    """
    from flextoolsmcp.server.kernel import reset_session

    reset_session()
    yield
    # Cleanup after test
    reset_session()
