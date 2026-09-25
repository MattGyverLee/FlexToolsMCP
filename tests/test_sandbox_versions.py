#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 (FR-005; re-plan T104/T105, D7): the sandbox's versions.

``read_file_version(path) -> Optional[str]``
    The Win32 ``FileVersion`` (``GetFileVersionInfoW`` via ``ctypes``; no
    pythonnet, no assembly load) as a dotted string, e.g. ``"3.8.2.0"``.
    ``None`` for a missing file, a file with no version resource, or a
    non-Windows host. Never raises. Every version read goes through this one
    module-level name, so tests monkeypatch it.

``ParserVersions``: ``fieldworks_hermitcrab_version`` (the bundled engine's
``FileVersion``, from ``discover_fieldworks_hermitcrab``) and
``generate_hc_config_version``. Reported, never compared -- to a floor or
to each other. The re-plan retired the separately installed `hc` tool, so
there is one engine and no skew: ``hc_tool_version``,
``hc_engine_version_skew`` and the ``hc_engine_version_skew`` advisory are
gone.

Health (data-model section 7): ``parser.detected`` carries
``fieldworks_hermitcrab_version`` and ``generate_hc_config_version`` (and no
``hc_tool_version`` / ``hc_path`` / ``hc_source``); ``parser.sandbox`` has
no advisory for versions.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server import parser_probe  # noqa: E402
from flextoolsmcp.server.parser_probe import ProbeResult  # noqa: E402

HC_DLL = "SIL.Machine.Morphology.HermitCrab.dll"


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def make_file(path: Path, content: bytes = b"MZ fake") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def install_file_versions(monkeypatch, versions: Dict[Path, Optional[str]]) -> list:
    """Patch ``parser_probe.read_file_version``; return the list of paths read."""
    table = {_key(p): v for p, v in versions.items()}
    reads: list = []

    def fake_read_file_version(path):
        reads.append(_key(path))
        return table.get(_key(path))

    monkeypatch.setattr(parser_probe, "read_file_version", fake_read_file_version, raising=False)
    return reads


def install_world(monkeypatch, tmp_path, *, fw_hc_version, gen_version, with_engine=True):
    """A sandbox world: a stub FieldWorks dir with the engine and generator."""
    fw = tmp_path / "FieldWorks 9"
    gen = make_file(fw / "GenerateHCConfig.exe")
    fw_dll = make_file(fw / HC_DLL) if with_engine else fw / HC_DLL

    core = ProbeResult(ok=True, expected_path=str(fw / "ParserCore.dll"), detected_version="9.3.11")
    monkeypatch.setattr(parser_probe, "probe_parser_core", lambda *a, **k: core)
    monkeypatch.setattr(parser_probe, "get_resolved_fieldworks_dir", lambda search_paths=None: fw)
    monkeypatch.setattr(
        parser_probe,
        "discover_generate_hc_config",
        lambda search_paths=None: ProbeResult(ok=True, expected_path=str(gen)),
    )
    install_file_versions(monkeypatch, {fw_dll: fw_hc_version, gen: gen_version})
    return fw


class TestNames:
    def test_constants(self):
        assert parser_probe.FIELDWORKS_HERMITCRAB_DLL == HC_DLL

    def test_parser_versions_fields(self):
        v = parser_probe.ParserVersions()
        assert v.fieldworks_hermitcrab_version is None
        assert v.generate_hc_config_version is None
        assert not hasattr(v, "hc_tool_version")
        assert not hasattr(v, "hc_engine_version_skew")


class TestReadFileVersion:
    def test_missing_file_is_none(self, tmp_path):
        assert parser_probe.read_file_version(tmp_path / "nope.dll") is None

    def test_file_without_version_resource_is_none(self, tmp_path):
        assert parser_probe.read_file_version(make_file(tmp_path / "x.dll", b"not a PE")) is None

    @pytest.mark.windows_only
    def test_reads_a_real_file_version(self):
        # kernel32.dll always carries a version resource (a uv/venv
        # python.exe launcher does not, so sys.executable is no good here).
        kernel32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "kernel32.dll"
        version = parser_probe.read_file_version(kernel32)
        assert version is not None
        assert re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version), version


class TestDetectorVersions:
    def test_both_versions_are_reported(self, monkeypatch, tmp_path):
        install_world(monkeypatch, tmp_path, fw_hc_version="3.8.2.0", gen_version="9.3.11.1")
        versions = parser_probe.ParserDetector().versions
        assert versions.fieldworks_hermitcrab_version == "3.8.2.0"
        assert versions.generate_hc_config_version == "9.3.11.1"

    def test_a_missing_engine_has_no_version(self, monkeypatch, tmp_path):
        install_world(monkeypatch, tmp_path, fw_hc_version="3.8.2.0", gen_version="9.3.11.1",
                      with_engine=False)
        versions = parser_probe.ParserDetector().versions
        assert versions.fieldworks_hermitcrab_version is None
        assert versions.generate_hc_config_version == "9.3.11.1"


class TestHealthBlock:
    def _block(self):
        from flextoolsmcp.server.handlers import diagnostic_health

        return diagnostic_health._build_parser_block()

    def test_detected_carries_the_engine_versions_and_no_hc_keys(self, monkeypatch, tmp_path):
        fw = install_world(monkeypatch, tmp_path, fw_hc_version="3.8.2.0",
                           gen_version="9.3.11.1")
        parser = self._block()
        assert parser["sandbox"]["status"] == "ready"
        assert parser["sandbox"]["advisories"] == []
        detected = parser["detected"]
        assert detected["fieldworks_hermitcrab_version"] == "3.8.2.0"
        assert detected["generate_hc_config_version"] == "9.3.11.1"
        assert detected["fieldworks_hermitcrab_path"] == str(fw / HC_DLL)
        for retired in ("hc_tool_version", "hc_path", "hc_source"):
            assert retired not in detected
        engine = parser["sandbox"]["components"][0]
        assert engine["component"] == "fieldworks_hermitcrab"
        assert engine["file_version"] == "3.8.2.0"
