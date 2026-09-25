#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 re-plan T104 (US1; FR-001, FR-004, FR-005; D7): discovery
of the sandbox's engine -- FieldWorks' bundled HermitCrab DLL.

The sandbox no longer shells out to an `hc` console tool (HANDOFF.md); its
parse worker loads the engine FieldWorks ships. Discovery is therefore a
presence-plus-`FileVersion` read of ``SIL.Machine.Morphology.HermitCrab.dll``
in ``versioning.get_resolved_fieldworks_dir()``:

``discover_fieldworks_hermitcrab(*, search_paths=None) -> EngineDiscovery``
    ``EngineDiscovery(ProbeResult)`` adds ``found``, ``file_version`` and
    ``reason``. Found: ``ok=found=True``, ``expected_path`` = the DLL,
    ``file_version`` = ``detected_version`` = its ``FileVersion``. Missing:
    ``signal="not_found"``, ``expected_path`` = where it should be (the bare
    DLL name when no FieldWorks install resolves). A path that exists but is
    not a file: ``signal="not_hermitcrab"``.

It never spawns a process and never loads an assembly (no pythonnet), so it
is safe on the health path. The retired four-source `hc` lookup
(``HC_TOOL_PATH``, PATH, the dotnet tools dir, ``dotnet tool list -g``) and
its ``hc -h`` probe are gone; a test pins that they stay gone.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server import parser_probe  # noqa: E402
from flextoolsmcp.server.parser_probe import ProbeResult  # noqa: E402

HC_DLL = "SIL.Machine.Morphology.HermitCrab.dll"


def make_file(path: Path, content: bytes = b"MZ fake") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def fw(monkeypatch, tmp_path):
    """A stub FieldWorks directory, resolved by the probe."""
    directory = tmp_path / "FieldWorks 9"
    directory.mkdir()
    monkeypatch.setattr(parser_probe, "get_resolved_fieldworks_dir",
                        lambda search_paths=None: directory)
    return directory


@pytest.fixture(autouse=True)
def no_processes(monkeypatch):
    """Discovery must never spawn anything (D7)."""
    import subprocess

    def boom(*a, **k):
        raise AssertionError("engine discovery spawned a process")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)


class TestPublicNames:
    def test_component_vocabulary(self):
        assert parser_probe.COMPONENT_FIELDWORKS_HERMITCRAB == "fieldworks_hermitcrab"
        assert parser_probe.SANDBOX_COMPONENTS == {"fieldworks_hermitcrab",
                                                   "GenerateHCConfig.exe"}
        assert parser_probe.FIELDWORKS_HERMITCRAB_DLL == HC_DLL

    def test_repair_hint_is_the_contract_literal(self):
        assert parser_probe.FIELDWORKS_REPAIR_HINT == (
            "GenerateHCConfig.exe ships with FieldWorks 9; repair or reinstall FieldWorks.")

    def test_signals_stay_outside_closed_signals(self):
        for signal in (parser_probe.SANDBOX_SIGNAL_NOT_FOUND,
                       parser_probe.SANDBOX_SIGNAL_NOT_HERMITCRAB):
            assert signal not in parser_probe.CLOSED_SIGNALS

    @pytest.mark.parametrize("name", [
        "discover_hc_tool", "probe_hc", "HcProbe", "HcToolDiscovery", "classify_hc_help",
        "hc_invoke_argv", "HC_PATH_ENV_VAR", "HC_SOURCES", "HC_TOOL_PACKAGE_ID",
        "HC_INSTALL_HINT", "COMPONENT_HC", "SANDBOX_SIGNAL_RUNTIME_MISSING",
        "hermitcrab_versions_differ", "ADVISORY_HC_ENGINE_VERSION_SKEW",
    ])
    def test_the_retired_hc_lookup_stays_retired(self, name):
        assert not hasattr(parser_probe, name), name

    def test_the_module_imports_no_process_or_clr_machinery(self):
        source = Path(parser_probe.__file__).read_text(encoding="utf-8")
        assert "import subprocess" not in source
        assert "import shutil" not in source


class TestDiscovery:
    def test_present_dll_is_found_with_its_file_version(self, fw, monkeypatch):
        dll = make_file(fw / HC_DLL)
        monkeypatch.setattr(parser_probe, "read_file_version",
                            lambda path: "3.8.2.0" if Path(path) == dll else None)
        result = parser_probe.discover_fieldworks_hermitcrab()
        assert isinstance(result, ProbeResult)
        assert result.ok is True and result.found is True and result.signal is None
        assert result.expected_path == str(dll)
        assert result.file_version == result.detected_version == "3.8.2.0"
        assert result.reason is None

    def test_a_dll_without_a_version_is_still_found(self, fw, monkeypatch):
        make_file(fw / HC_DLL)
        monkeypatch.setattr(parser_probe, "read_file_version", lambda path: None)
        result = parser_probe.discover_fieldworks_hermitcrab()
        assert result.found is True and result.file_version is None

    def test_missing_dll_is_not_found_naming_where_it_should_be(self, fw):
        result = parser_probe.discover_fieldworks_hermitcrab()
        assert result.ok is False and result.found is False
        assert result.signal == "not_found"
        assert result.expected_path == str(fw / HC_DLL)
        assert HC_DLL in result.reason and str(fw) in result.reason

    def test_no_fieldworks_install_gives_the_bare_dll_name(self, monkeypatch):
        monkeypatch.setattr(parser_probe, "get_resolved_fieldworks_dir",
                            lambda search_paths=None: None)
        result = parser_probe.discover_fieldworks_hermitcrab()
        assert result.signal == "not_found" and result.expected_path == HC_DLL
        assert "No FieldWorks installation" in result.reason

    def test_a_directory_in_its_place_is_not_hermitcrab(self, fw):
        (fw / HC_DLL).mkdir()
        result = parser_probe.discover_fieldworks_hermitcrab()
        assert result.found is False and result.signal == "not_hermitcrab"

    def test_search_paths_reach_the_resolver(self, monkeypatch, tmp_path):
        seen = []

        def resolver(search_paths=None):
            seen.append(search_paths)
            return None

        monkeypatch.setattr(parser_probe, "get_resolved_fieldworks_dir", resolver)
        parser_probe.discover_fieldworks_hermitcrab(search_paths=[tmp_path])
        assert seen == [[tmp_path]]

    def test_no_assembly_is_loaded(self, fw, monkeypatch):
        """D7: a read of the file, never a load (no pythonnet import)."""
        make_file(fw / HC_DLL)
        for name in list(sys.modules):
            if name == "clr" or name.startswith("clr."):
                monkeypatch.delitem(sys.modules, name)
        parser_probe.discover_fieldworks_hermitcrab()
        assert "clr" not in sys.modules


class TestDetectorWiring:
    def _detector(self, monkeypatch, fw, *, engine_version="3.8.2.0"):
        dll = make_file(fw / HC_DLL)
        gen = make_file(fw / "GenerateHCConfig.exe")
        core = ProbeResult(ok=True, expected_path=str(fw / "ParserCore.dll"))
        monkeypatch.setattr(parser_probe, "probe_parser_core", lambda *a, **k: core)
        monkeypatch.setattr(parser_probe, "discover_generate_hc_config",
                            lambda search_paths=None: ProbeResult(ok=True, expected_path=str(gen)))
        versions = {str(dll): engine_version, str(gen): "9.3.11.1"}
        monkeypatch.setattr(parser_probe, "read_file_version",
                            lambda path: versions.get(str(path)))
        return parser_probe.ParserDetector()

    def test_sandbox_probe_carries_the_engine(self, monkeypatch, fw):
        detector = self._detector(monkeypatch, fw)
        engine = detector.sandbox_probe.engine
        assert engine.found is True and engine.expected_path == str(fw / HC_DLL)
        assert detector.sandbox_probe.generate_config.ok is True
        assert detector.versions.fieldworks_hermitcrab_version == "3.8.2.0"
        assert detector.versions.generate_hc_config_version == "9.3.11.1"

    def test_a_raising_engine_probe_does_not_blank_the_others(self, monkeypatch, fw):
        def broken(**kw):
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(parser_probe, "discover_fieldworks_hermitcrab", broken)
        detector = self._detector(monkeypatch, fw)
        engine = detector.sandbox_probe.engine
        assert engine.ok is False and engine.signal == parser_probe.SIGNAL_LOAD_FAILED
        assert engine.expected_path == HC_DLL
        assert detector.read_probe.ok is True
