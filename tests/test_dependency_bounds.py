#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp 1.x/2.x dual support -- dependency bound regression tests (issue #83).

mcp 2.0.0 (released 2026-07-28) removed the low-level `Server.list_tools()`/
`call_tool()` decorators that `server.py` used to depend on, breaking every
install of flextools-mcp 2.3.1-2.9.0 that resolved the previously-uncapped
`mcp>=1.27.0` requirement to 2.x. Registration now goes through
`src/flextoolsmcp/mcp_compat.py`, which supports both majors, so the pin is
`mcp>=1.27.0,<3` -- uncapped across the verified break, capped at the next
unknown major.

These tests lock that range in place and fail with a message that names `mcp`
explicitly, so a future regression is diagnosable from the assertion text
alone (unlike the original failure, which surfaced as an unrelated
"cannot import name 'APIIndex'").

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
    """The resolved mcp package must be 1.x or 2.x.

    `src/flextoolsmcp/mcp_compat.py` registers handlers via decorators on 1.x
    and via constructor-injected `on_list_tools=`/`on_call_tool=` on 2.x; any
    other major is outside the verified range `>=1.27.0,<3`.
    """
    version_str = importlib_metadata.version("mcp")
    major = int(version_str.split(".")[0])
    assert major in (1, 2), (
        f"mcp {version_str} outside supported range >=1.27.0,<3 -- "
        f"mcp_compat.py only covers the 1.x decorator API and the 2.x "
        f"constructor-injection API."
    )


def test_pyproject_mcp_requirement_has_upper_bound():
    """pyproject.toml's mcp dependency string must literally contain '<3'."""
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Match the actual version-constrained dependency entry (e.g. "mcp>=1.27.0,<3"),
    # not the bare "mcp" string that also appears in the `keywords` list.
    match = re.search(r'"mcp(>=?[^"]*)"', pyproject_text)
    assert match, "Could not find an 'mcp' dependency entry in pyproject.toml"
    requirement = match.group(1)
    assert "<3" in requirement, (
        f"pyproject.toml mcp requirement 'mcp{requirement}' pins below the "
        f"supported range -- mcp_compat.py covers 1.x and 2.x, so the cap "
        f"belongs at <3, not <2."
    )


def test_requirements_txt_mcp_requirement_has_upper_bound():
    """requirements.txt's mcp line must literally contain '<3'."""
    requirements_text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(r"^mcp([^\s#]*)", requirements_text, re.MULTILINE)
    assert match, "Could not find an 'mcp' line in requirements.txt"
    requirement = match.group(1)
    assert "<3" in requirement, (
        f"requirements.txt mcp requirement 'mcp{requirement}' pins below the "
        f"supported range -- expected '<3' for dual 1.x/2.x support."
    )
