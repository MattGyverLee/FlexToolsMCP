"""Offline structural checks for the MCP Registry manifest (issue #369, Phase 4).

``server.json`` at the repo root is what gets published to the MCP Registry.
These tests pin the invariants that must hold for every release:

* the file is valid JSON with the registry's required top-level fields;
* ``name`` matches the ``mcp-name:`` ownership string in README.md (the
  registry verifies PyPI ownership by finding that literal string in the
  package's long description, which is README.md);
* ``version`` (top-level and per-package) equals the package ``VERSION``
  file, so the listing cannot silently lag the PyPI release;
* the package block points at the PyPI distribution ``flextools-mcp``
  over stdio.

Full schema validation (``mcp-publisher validate`` or jsonschema against
https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json)
is a manual/release-time step; these tests need no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_JSON = REPO_ROOT / "server.json"
README = REPO_ROOT / "README.md"
VERSION_FILE = REPO_ROOT / "VERSION"

EXPECTED_NAME = "io.github.mattgyverlee/flextoolsmcp"
EXPECTED_PACKAGE = "flextools-mcp"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(SERVER_JSON.read_text(encoding="utf-8"))


def test_server_json_is_valid_json_with_required_fields(manifest: dict) -> None:
    for field in ("name", "description", "version"):
        assert field in manifest, f"server.json is missing required field {field!r}"
        assert isinstance(manifest[field], str) and manifest[field]
    # Registry caps description at 100 chars (pyproject's is longer; the
    # manifest carries its own registry-only string on purpose).
    assert len(manifest["description"]) <= 100


def test_server_json_name_matches_readme_mcp_name(manifest: dict) -> None:
    assert manifest["name"] == EXPECTED_NAME
    readme = README.read_text(encoding="utf-8")
    match = re.search(r"mcp-name:\s*(\S+)", readme)
    assert match is not None, "README.md must carry the mcp-name: ownership string"
    assert match.group(1) == manifest["name"]


def test_server_json_version_matches_package_version(manifest: dict) -> None:
    package_version = VERSION_FILE.read_text(encoding="utf-8").strip()
    assert manifest["version"] == package_version
    for package in manifest["packages"]:
        assert package["version"] == package_version


def test_server_json_package_block(manifest: dict) -> None:
    assert len(manifest["packages"]) == 1
    package = manifest["packages"][0]
    assert package["registryType"] == "pypi"
    assert package["identifier"] == EXPECTED_PACKAGE
    assert package["transport"] == {"type": "stdio"}
    assert package["runtimeHint"] == "uvx"
    for env_var in package.get("environmentVariables", []):
        assert env_var["name"]
        # No secret values are ever declared in the manifest.
        assert env_var.get("isSecret") is not True or "value" not in env_var
