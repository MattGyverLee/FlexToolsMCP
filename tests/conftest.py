#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pytest configuration and shared fixtures."""

import sys
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


@pytest.fixture
def reset_session_state():
    """Reset session state for tests that need a clean state.

    Consolidates duplicate session reset patterns from multiple test files.
    Usage: add 'reset_session_state' parameter to test function.
    """
    from server import reset_session, get_session_state
    reset_session()
    yield
    # Cleanup after test
    reset_session()
