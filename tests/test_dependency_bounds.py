#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp 2.x-only support -- dependency bound regression tests (issue #369).

mcp 2.0.0 (released 2026-07-28) removed the low-level `Server.list_tools()`/
`call_tool()` decorators that `server.py` used to depend on, breaking every
install of flextools-mcp 2.3.1-2.9.0 that resolved the previously-uncapped
`mcp>=1.27.0` requirement to 2.x. Registration went through a dual-major
compat shim for a while; issue #369 retired the shim, inlined its 2.x branch
into `server.py`, and raised the floor, so the pin is now `mcp>=2,<3` --
floored at the only supported major, capped at the next unknown major.

These tests lock that range in place -- BOTH the `>=2` floor and the `<3`
cap -- and fail with a message that names `mcp` explicitly, so a future
regression is diagnosable from the assertion text alone (unlike the original
failure, which surfaced as an unrelated "cannot import name 'APIIndex'").
A floor check matters as much as the cap: asserting only `<3` would still
pass with the old 1.x floor, which is exactly the regression #369 removes.

SCOPE LIMIT: this file intentionally does NOT assert that every runtime
dependency has an upper bound. sentence-transformers, faiss-cpu, pythonnet,
httpx, and anyio are still deliberately uncapped today -- see the
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
    "httpx",
    "anyio",
}


def test_installed_mcp_major_version_is_supported():
    """The resolved mcp package must be 2.x.

    `server.py` registers handlers via the constructor-injected
    `on_list_tools=`/`on_call_tool=` adapters inlined there (issue #369);
    any other major is outside the verified range `>=2,<3`.
    """
    version_str = importlib_metadata.version("mcp")
    major = int(version_str.split(".")[0])
    assert major == 2, (
        f"mcp {version_str} outside supported range >=2,<3 -- "
        f"server.py only covers the 2.x constructor-injection API."
    )


def _assert_mcp_requirement(requirement: str, where: str) -> None:
    assert ">=2" in requirement, (
        f"{where} mcp requirement 'mcp{requirement}' is missing the "
        f">=2 floor -- server.py is mcp 2.x-only (issue #369), so a 1.x "
        f"floor must not come back."
    )
    assert "1.27" not in requirement and ">=1" not in requirement, (
        f"{where} mcp requirement 'mcp{requirement}' still carries a 1.x "
        f"floor -- expected '>=2' for mcp 2.x-only support (issue #369)."
    )
    assert "<3" in requirement, (
        f"{where} mcp requirement 'mcp{requirement}' pins below the "
        f"supported range -- the 2.x adapters in server.py are verified "
        f"against 2.x only, so the cap belongs at <3, not <2."
    )


def test_pyproject_mcp_requirement_has_floor_and_upper_bound():
    """pyproject.toml's mcp dependency must contain '>=2' AND '<3'."""
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Match the actual version-constrained dependency entry (e.g. "mcp>=2,<3"),
    # not the bare "mcp" string that also appears in the `keywords` list.
    match = re.search(r'"mcp(>=?[^"]*)"', pyproject_text)
    assert match, "Could not find an 'mcp' dependency entry in pyproject.toml"
    _assert_mcp_requirement(match.group(1), "pyproject.toml")


def test_requirements_txt_mcp_requirement_has_floor_and_upper_bound():
    """requirements.txt's mcp line must contain '>=2' AND '<3'."""
    requirements_text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(r"^mcp([^\s#]*)", requirements_text, re.MULTILINE)
    assert match, "Could not find an 'mcp' line in requirements.txt"
    _assert_mcp_requirement(match.group(1), "requirements.txt")


def _assert_pydantic_requirement(requirement: str, where: str) -> None:
    assert ">=2" in requirement, (
        f"{where} pydantic requirement 'pydantic{requirement}' is missing the "
        f">=2 floor -- the server targets pydantic v2 APIs."
    )
    assert "<3" in requirement, (
        f"{where} pydantic requirement 'pydantic{requirement}' is missing a "
        f"<3 cap -- uncapped majors can break fresh installs silently "
        f"(see specs/mcp2-compat/deferred-issues.md section 2)."
    )


def test_pyproject_pydantic_requirement_has_floor_and_upper_bound():
    """pyproject.toml pins pydantic to the supported 2.x major."""
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'"pydantic(>=?[^"]*)"', pyproject_text)
    assert match, "Could not find a 'pydantic' dependency entry in pyproject.toml"
    _assert_pydantic_requirement(match.group(1), "pyproject.toml")


def test_requirements_txt_pydantic_requirement_has_floor_and_upper_bound():
    """requirements.txt pins pydantic to the supported 2.x major."""
    requirements_text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(r"^pydantic([^\s#]*)", requirements_text, re.MULTILINE)
    assert match, "Could not find a pydantic line in requirements.txt"
    _assert_pydantic_requirement(match.group(1), "requirements.txt")
