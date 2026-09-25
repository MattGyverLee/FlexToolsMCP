#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T025 (parser-check CP5, US1): the three versions and the skew advisory (FR-005, R-03).

Written test-first: T031 (and T032 for the health block) make these pass.
API pinned in ``src/flextoolsmcp/server/parser_probe.py``:

``read_file_version(path) -> Optional[str]``
    The Win32 ``FileVersion`` (``GetFileVersionInfoW`` via ``ctypes``; no
    pythonnet, no assembly load) as a dotted string, e.g. ``"3.8.2.0"``.
    ``None`` for a missing file, a file with no version resource, or a
    non-Windows host. Never raises. Every version read below goes through
    this one module-level name, so tests monkeypatch it.

``HcToolDiscovery.detected_version`` -- the hc tool version, from:
    1. the tool-store path: the ``<ver>`` segment of
       ``...\\.dotnet\\tools\\.store\\sil.machine.morphology.hermitcrab.tool\\<ver>\\``,
       either because the hit itself lies under it (a ``.dll`` inside the
       store) or because the hit is a shim whose sibling ``.store`` holds it;
    2. the ``dotnet tool list -g`` row (tests/test_sandbox_discovery.py);
    3. for a ``.dll`` hit outside the store: ``read_file_version`` of
       ``SIL.Machine.Morphology.HermitCrab.dll`` beside it.

``ParserVersions`` gains (all defaulted):
    fieldworks_hermitcrab_version: Optional[str]
        read_file_version(get_resolved_fieldworks_dir() / FIELDWORKS_HERMITCRAB_DLL)
    generate_hc_config_version: Optional[str]
        read_file_version(<discover_generate_hc_config().expected_path>) when found
    hc_engine_version_skew: bool
        hermitcrab_versions_differ(hc_tool_version, fieldworks_hermitcrab_version)

``hermitcrab_versions_differ(a, b) -> bool``: False when either is None;
    numeric dotted versions compare as 4-tuples padded with zeros (so
    ``"3.8.2"`` == ``"3.8.2.0"``); anything unparseable compares as raw
    strings. Reported, never a floor, never a refusal.

Constants: ``FIELDWORKS_HERMITCRAB_DLL = "SIL.Machine.Morphology.HermitCrab.dll"``,
``ADVISORY_HC_ENGINE_VERSION_SKEW = "hc_engine_version_skew"``,
``HC_TOOL_PACKAGE_ID = "sil.machine.morphology.hermitcrab.tool"``.

Health (T032, data-model section 7): ``parser.sandbox.advisories`` carries
``hc_engine_version_skew`` (a string or a ``{"code": ...}`` object -- both
accepted here) while ``parser.sandbox.status`` stays ``"ready"``;
``parser.detected`` gains ``fieldworks_hermitcrab_version``,
``generate_hc_config_version`` and ``hc_source``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server import parser_probe  # noqa: E402
from flextoolsmcp.server.parser_probe import ProbeResult  # noqa: E402


HELP_TEXT = (
    "Usage: hc [OPTIONS]\r\n"
    "HermitCrab.NET is a phonological and morphological parser.\r\n"
)
PACKAGE_ID = "sil.machine.morphology.hermitcrab.tool"
HC_DLL = "SIL.Machine.Morphology.HermitCrab.dll"


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def make_file(path: Path, content: bytes = b"MZ fake") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def fake_help_run(argv, *args, **kwargs):
    argv = [str(a) for a in argv]
    if argv and argv[-1] == "-h":
        return subprocess.CompletedProcess(argv, -1, HELP_TEXT.encode("utf-16-le"), b"")
    raise AssertionError(f"unexpected subprocess.run argv: {argv!r}")


def install_file_versions(monkeypatch, versions: Dict[Path, Optional[str]]) -> list:
    """Patch ``parser_probe.read_file_version``; return the list of paths read."""
    table = {_key(p): v for p, v in versions.items()}
    reads: list = []

    def fake_read_file_version(path):
        reads.append(_key(path))
        return table.get(_key(path))

    monkeypatch.setattr(parser_probe, "read_file_version", fake_read_file_version, raising=False)
    return reads


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.delenv(parser_probe.HC_PATH_ENV_VAR, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(parser_probe.shutil, "which", lambda name, *a, **k: None)
    monkeypatch.setattr(parser_probe.subprocess, "run", fake_help_run)
    clear = getattr(parser_probe, "clear_hc_probe_cache", None)
    if clear:
        clear()
    yield home
    if clear:
        clear()


def install_tool(home: Path, version: str) -> Path:
    """Lay out a real-shaped global-tool install; return the shim."""
    tools = home / ".dotnet" / "tools"
    store = tools / ".store" / PACKAGE_ID / version
    # The real layout nests `<pkg>\<ver>\tools\net10.0\any\` below this; it is
    # flattened here to stay under MAX_PATH in pytest's tmp dirs. The version
    # is the segment right after `.store\<pkg>\` either way.
    make_file(store / "any" / "hc.dll")
    make_file(store / "any" / HC_DLL)
    return make_file(tools / "hc.exe")


def install_world(monkeypatch, tmp_path, home, *, hc_version, fw_hc_version, gen_version):
    """A ready sandbox world: real discovery through the tools dir + store,
    a stubbed FieldWorks dir, ParserCore and GenerateHCConfig probes."""
    fw = tmp_path / "FieldWorks 9"
    gen = make_file(fw / "GenerateHCConfig.exe")
    fw_dll = make_file(fw / HC_DLL)
    install_tool(home, hc_version)

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


# ---------------------------------------------------------------------------
# Public names
# ---------------------------------------------------------------------------


class TestNames:
    def test_constants(self):
        assert parser_probe.FIELDWORKS_HERMITCRAB_DLL == HC_DLL
        assert parser_probe.ADVISORY_HC_ENGINE_VERSION_SKEW == "hc_engine_version_skew"
        assert parser_probe.HC_TOOL_PACKAGE_ID == PACKAGE_ID

    def test_parser_versions_fields(self):
        v = parser_probe.ParserVersions()
        assert v.hc_tool_version is None
        assert v.fieldworks_hermitcrab_version is None
        assert v.generate_hc_config_version is None
        assert v.hc_engine_version_skew is False


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


# ---------------------------------------------------------------------------
# The hc tool version
# ---------------------------------------------------------------------------


class TestHcToolVersion:
    def test_shim_in_tools_dir_reads_the_store_version(self, monkeypatch, isolated):
        install_tool(isolated, "3.8.2")
        install_file_versions(monkeypatch, {})  # the store path, not a FileVersion
        result = parser_probe.discover_hc_tool()
        assert result.source == "dotnet_tools_dir"
        assert result.detected_version == "3.8.2"

    def test_shim_on_path_reads_the_store_version(self, monkeypatch, isolated):
        shim = install_tool(isolated, "3.9.1")
        monkeypatch.setattr(
            parser_probe.shutil, "which", lambda name, *a, **k: str(shim) if name == "hc" else None
        )
        result = parser_probe.discover_hc_tool()
        assert result.source == "path"
        assert result.detected_version == "3.9.1"

    def test_dll_inside_the_store_reads_the_path_segment(self, monkeypatch, isolated):
        install_tool(isolated, "3.10.0")
        dll = next((isolated / ".dotnet" / "tools" / ".store").rglob("hc.dll"))
        dotnet = make_file(isolated / "dotnet" / "dotnet.exe")
        monkeypatch.setattr(
            parser_probe.shutil,
            "which",
            lambda name, *a, **k: str(dotnet) if name == "dotnet" else None,
        )
        install_file_versions(monkeypatch, {})

        result = parser_probe.discover_hc_tool(override_path=dll)

        assert result.found is True
        assert result.detected_version == "3.10.0"

    def test_dll_outside_the_store_reads_hermitcrab_dll_beside_it(
        self, monkeypatch, tmp_path
    ):
        """R-15's no-SDK route: an unpacked hc.dll with its dependencies."""
        dll = make_file(tmp_path / "unpacked" / "hc.dll")
        beside = make_file(tmp_path / "unpacked" / HC_DLL)
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        monkeypatch.setattr(
            parser_probe.shutil,
            "which",
            lambda name, *a, **k: str(dotnet) if name == "dotnet" else None,
        )
        install_file_versions(monkeypatch, {beside: "3.8.2.0"})

        result = parser_probe.discover_hc_tool(override_path=dll)

        assert result.found is True
        assert result.detected_version == "3.8.2.0"


# ---------------------------------------------------------------------------
# All three versions, and the skew flag
# ---------------------------------------------------------------------------


class TestThreeVersions:
    def test_all_three_are_reported(self, monkeypatch, tmp_path, isolated):
        install_world(
            monkeypatch, tmp_path, isolated,
            hc_version="3.8.2", fw_hc_version="3.8.2.0", gen_version="9.3.11.1",
        )

        detector = parser_probe.ParserDetector()

        assert detector.versions.hc_tool_version == "3.8.2"
        assert detector.versions.fieldworks_hermitcrab_version == "3.8.2.0"
        assert detector.versions.generate_hc_config_version == "9.3.11.1"
        assert detector.versions.hc_engine_version_skew is False
        assert detector.sandbox_probe.hc.ok is True

    def test_skew_is_flagged_and_never_a_refusal(self, monkeypatch, tmp_path, isolated):
        install_world(
            monkeypatch, tmp_path, isolated,
            hc_version="3.7.1", fw_hc_version="3.8.2.0", gen_version="9.3.11.1",
        )

        detector = parser_probe.ParserDetector()

        assert detector.versions.hc_engine_version_skew is True
        assert detector.sandbox_probe.hc.ok is True
        assert detector.sandbox_probe.hc.signal is None
        assert detector.sandbox_probe.generate_config.ok is True

    def test_missing_fieldworks_version_is_not_skew(self, monkeypatch, tmp_path, isolated):
        install_world(
            monkeypatch, tmp_path, isolated,
            hc_version="3.8.2", fw_hc_version=None, gen_version=None,
        )

        detector = parser_probe.ParserDetector()

        assert detector.versions.fieldworks_hermitcrab_version is None
        assert detector.versions.generate_hc_config_version is None
        assert detector.versions.hc_engine_version_skew is False
        assert detector.sandbox_probe.hc.ok is True


class TestVersionsDiffer:
    @pytest.mark.parametrize(
        "a,b,expected",
        [
            ("3.8.2", "3.8.2.0", False),
            ("3.8.2.0", "3.8.2.0", False),
            ("3.8.2", "3.8.3.0", True),
            ("3.7.1", "3.8.2.0", True),
            ("not-a-version", "3.8.2.0", True),
            (None, "3.8.2.0", False),
            ("3.8.2", None, False),
            (None, None, False),
        ],
    )
    def test_hermitcrab_versions_differ(self, a, b, expected):
        assert parser_probe.hermitcrab_versions_differ(a, b) is expected


# ---------------------------------------------------------------------------
# Health: skew is an advisory, status stays ready
# ---------------------------------------------------------------------------


def _advisory_codes(sandbox: dict) -> list:
    codes = []
    for item in sandbox.get("advisories") or []:
        codes.append(item.get("code") if isinstance(item, dict) else item)
    return codes


class TestHealthBlock:
    def _block(self):
        from flextoolsmcp.server.handlers import diagnostic_health

        return diagnostic_health._build_parser_block()

    def test_skewed_fixture_gives_advisory_and_stays_ready(self, monkeypatch, tmp_path, isolated):
        install_world(
            monkeypatch, tmp_path, isolated,
            hc_version="3.7.1", fw_hc_version="3.8.2.0", gen_version="9.3.11.1",
        )

        parser = self._block()

        assert parser["sandbox"]["status"] == "ready"
        assert "hc_engine_version_skew" in _advisory_codes(parser["sandbox"])
        detected = parser["detected"]
        assert detected["hc_tool_version"] == "3.7.1"
        assert detected["fieldworks_hermitcrab_version"] == "3.8.2.0"
        assert detected["generate_hc_config_version"] == "9.3.11.1"
        assert detected["hc_source"] == "dotnet_tools_dir"

    def test_matching_versions_give_no_advisory(self, monkeypatch, tmp_path, isolated):
        install_world(
            monkeypatch, tmp_path, isolated,
            hc_version="3.8.2", fw_hc_version="3.8.2.0", gen_version="9.3.11.1",
        )

        parser = self._block()

        assert parser["sandbox"]["status"] == "ready"
        assert "advisories" in parser["sandbox"]
        assert "hc_engine_version_skew" not in _advisory_codes(parser["sandbox"])
