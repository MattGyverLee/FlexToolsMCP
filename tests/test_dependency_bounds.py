#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp 2.0 compatibility -- dependency bound regression tests.

mcp 2.0.0 (released 2026-07-28) removed the low-level `Server.list_tools()`/
`call_tool()` decorators that `server.py` depends on, breaking every install
of flextools-mcp 2.3.1-2.9.0 that resolved the previously-uncapped
`mcp>=1.27.0` requirement to 2.x. These tests lock the upper bound in place
and fail with a message that names `mcp` explicitly, so a future regression
is diagnosable from the assertion text alone (unlike the original failure,
which surfaced as an unrelated "cannot import name 'APIIndex'").

SCOPE LIMIT: this file intentionally does NOT assert that every runtime
dependency has an upper bound. sentence-transformers, faiss-cpu, pythonnet,
pydantic, httpx, and anyio are all deliberately uncapped today -- see the
deferred issue in specs/mcp2-compat/deferred-issues.md ("Add upper bounds to
remaining uncapped runtime deps"). A general assertion would fail
immediately and is out of scope for this fix.

Run with:
    python -m pytest tests/test_dependency_bounds.py -q
"""

import importlib.metadata as importlib_metadata
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Deliberately uncapped runtime deps today (see module docstring). Do not
# widen this without also updating the deferred issue; do not replace this
# targeted mcp check with a blanket "every dep has an upper bound" assertion.
KNOWN_UNCAPPED_DEPS = {
    "sentence-transformers",
    "faiss-cpu",
    "pythonnet",
    "pydantic",
    "httpx",
    "anyio",
}


def test_installed_mcp_major_version_is_supported():
    """The resolved mcp package must be 1.x, not 2.x.

    mcp 2.0.0 removed Server.list_tools()/call_tool(); importing server.py
    against mcp>=2 raises AttributeError at decorator-registration time
    (see src/flextoolsmcp/server.py:808-855 and
    src/flextoolsmcp/server/__init__.py's lazy-loader diagnostics).
    """
    version_str = importlib_metadata.version("mcp")
    major = int(version_str.split(".")[0])
    assert major == 1, (
        f"mcp {version_str} outside supported range >=1.27.0,<2 -- the "
        f"low-level Server decorator API was removed in 2.0.0."
    )


def test_pyproject_mcp_requirement_has_upper_bound():
    """pyproject.toml's mcp dependency string must literally contain '<2'."""
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Match the actual version-constrained dependency entry (e.g. "mcp>=1.27.0,<2"),
    # not the bare "mcp" string that also appears in the `keywords` list.
    match = re.search(r'"mcp(>=?[^"]*)"', pyproject_text)
    assert match, "Could not find an 'mcp' dependency entry in pyproject.toml"
    requirement = match.group(1)
    assert "<2" in requirement, (
        f"pyproject.toml mcp requirement 'mcp{requirement}' has no upper "
        f"bound -- mcp>=2.0.0 removed the low-level Server decorator API "
        f"this project depends on."
    )


def test_requirements_txt_mcp_requirement_has_upper_bound():
    """requirements.txt's mcp line must literally contain '<2'."""
    requirements_text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(r"^mcp([^\s#]*)", requirements_text, re.MULTILINE)
    assert match, "Could not find an 'mcp' line in requirements.txt"
    requirement = match.group(1)
    assert "<2" in requirement, (
        f"requirements.txt mcp requirement 'mcp{requirement}' has no upper bound."
    )
