#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #149: flextools_start api_versions must not masquerade index as installed."""

import asyncio
import json

import pytest

from flextoolsmcp.server import kernel
from flextoolsmcp.server.handlers import admin as admin_mod


def _write_api_file(lib_dir, prefix, version):
    lib_dir.mkdir(parents=True, exist_ok=True)
    path = lib_dir / f"{prefix}_v{version}.json"
    path.write_text(
        json.dumps({"version": version, "entities": {}}),
        encoding="utf-8",
    )


def _parse_start_response(response):
    return json.loads(response[0].text)


@pytest.fixture(autouse=True)
def _ensure_ops_logger():
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()


class TestIssue149ApiVersions:
    def test_start_session_reports_fallback_not_installed_version(
        self, tmp_path, monkeypatch
    ):
        index_dir = tmp_path / "index"
        _write_api_file(index_dir / "python", "flexicon_api", "4.1.0")
        _write_api_file(index_dir / "liblcm", "liblcm_api", "11.0.0")
        _write_api_file(index_dir / "python", "flexlibs_api", "1.2.8")

        import flextoolsmcp.server.handlers.diagnostic_health as dh

        monkeypatch.setattr(dh, "get_index_dir", lambda: index_dir)
        monkeypatch.setattr(
            dh,
            "detect_installed_library_version",
            lambda display_name, **kw: {
                "Flexicon": "4.2.1",
                "LibLCM": "11.0.0",
                "FlexLibs stable": "1.2.8",
            }.get(display_name),
        )

        data = _parse_start_response(asyncio.run(admin_mod.handle_start({})))
        versions = data["session"]["api_versions"]

        flexicon = versions["flexicon"]
        assert flexicon["installed"] == "4.2.1"
        assert flexicon["index_loaded"] == "4.1.0"
        assert flexicon["match"] == "fallback_latest"
        assert flexicon["installed"] != flexicon["index_loaded"]

    def test_start_session_exact_match_reports_same_installed_and_index(
        self, tmp_path, monkeypatch
    ):
        index_dir = tmp_path / "index"
        _write_api_file(index_dir / "python", "flexicon_api", "4.2.1")
        _write_api_file(index_dir / "liblcm", "liblcm_api", "11.0.0")
        _write_api_file(index_dir / "python", "flexlibs_api", "1.2.8")

        import flextoolsmcp.server.handlers.diagnostic_health as dh

        monkeypatch.setattr(dh, "get_index_dir", lambda: index_dir)
        monkeypatch.setattr(
            dh,
            "detect_installed_library_version",
            lambda display_name, **kw: {
                "Flexicon": "4.2.1",
                "LibLCM": "11.0.0",
                "FlexLibs stable": "1.2.8",
            }.get(display_name),
        )

        data = _parse_start_response(asyncio.run(admin_mod.handle_start({})))
        flexicon = data["session"]["api_versions"]["flexicon"]
        assert flexicon["match"] == "exact"
        assert flexicon["installed"] == flexicon["index_loaded"] == "4.2.1"
