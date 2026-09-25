#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T024 (parser-check CP5, US1): `hc` discovery tests (FR-001..FR-004, R-03).

Written test-first: T030 makes these pass. The API they pin lives in
``src/flextoolsmcp/server/parser_probe.py``:

``discover_hc_tool(*, override_path=None, timeout=HC_DISCOVERY_TIMEOUT_SECONDS) -> HcToolDiscovery``
    Four ordered sources, first hit wins (FR-001):

    ==  ==================  ===========================================  =====================
    #   ``source``           where                                        notes
    ==  ==================  ===========================================  =====================
    1   ``"override"``       ``override_path`` or env ``HC_TOOL_PATH``    a missing file is final
    2   ``"path"``           ``shutil.which("hc")``
    3   ``"dotnet_tools_dir"`` ``<USERPROFILE>\\.dotnet\\tools\\hc.exe``    checked directly
    4   ``"dotnet_tool_list"`` ``dotnet tool list -g`` (``timeout`` bound)  only when 1-3 miss
    ==  ==================  ===========================================  =====================

    ``<USERPROFILE>`` is ``os.environ["USERPROFILE"]``, falling back to
    ``Path.home()``. A file hit (sources 1-3) is then identified and
    start-checked by ONE bounded ``hc -h`` run (``probe_hc``). A listing
    hit (source 4) has no file to run: the row naming the
    ``sil.machine.morphology.hermitcrab.tool`` package IS the identity check,
    and ``starts`` stays ``None`` (unobserved) -- so it can never read ready.

``HcToolDiscovery(ProbeResult)`` -- a ``ProbeResult`` subclass, so every
existing reader (``diagnostic_health``, ``ParserDetector``, ``_safe_probe``)
keeps working. Fields added (all defaulted):

    found: bool               -- a HermitCrab hc was located and identified
    starts: Optional[bool]    -- True/False from the -h probe; None = not run
    source: Optional[str]     -- one of HC_SOURCES (None only when nothing hit)
    path: Optional[str]       -- the concrete file found (None for a list hit / miss)
    reason: Optional[str]     -- human text for any not-ready outcome
    invoke_argv: Optional[List[str]] -- how to run it: [path] or [dotnet, path] (no "-h")

    Inherited, with these meanings: ``ok`` == ``found and starts is True``;
    ``signal`` in {None, not_found, timeout, runtime_missing, not_hermitcrab};
    ``expected_path`` = the path found or looked for (the override path, the
    hit, or ``HC_EXPECTED_PATH_DESCRIPTION``); ``detected_version`` = the hc
    tool version (T031; see tests/test_sandbox_versions.py); ``load_error`` =
    diagnostic text (kept for back-compat, may equal ``reason``).

``probe_hc(path, *, timeout=HC_PROBE_TIMEOUT_SECONDS) -> HcProbe``
    Runs ``subprocess.run(hc_invoke_argv(path) + ["-h"], stdin=DEVNULL,
    capture_output=True, timeout=5.0)`` in BYTES mode (no ``text``/``encoding``
    -- stdout is decoded UTF-16LE with any BOM tolerated, stderr UTF-8).
    Memoised for the process on ``(str(path), st_size, st_mtime_ns)``;
    ``clear_hc_probe_cache()`` empties the memo. Classification (R-03):

    - stdout has ``Usage: hc [OPTIONS]`` AND ``HermitCrab.NET is a
      phonological and morphological parser.`` -> found=True, starts=True
    - .NET host failure (stderr names a missing framework, or exit code
      0x80008096 / 0x8000809A, signed or unsigned) -> found=True,
      starts=False, signal="runtime_missing", reason naming the runtime and
      version parsed from ``Framework: 'Microsoft.NETCore.App', version 'X'``
    - ``subprocess.TimeoutExpired`` -> found=True, starts=False, signal="timeout"
    - anything else -> found=False, signal="not_hermitcrab"

``HcProbe`` (frozen dataclass): found, starts, signal, reason, exit_code.
``hc_invoke_argv(path) -> List[str]``: ``[str(path)]``, or
``[shutil.which("dotnet"), str(path)]`` for a ``.dll``.

Constants: ``SANDBOX_SIGNAL_RUNTIME_MISSING = "runtime_missing"``,
``SANDBOX_SIGNAL_NOT_HERMITCRAB = "not_hermitcrab"`` (both outside
``CLOSED_SIGNALS``); ``HC_SOURCE_OVERRIDE/PATH/DOTNET_TOOLS_DIR/DOTNET_TOOL_LIST``
and ``HC_SOURCES``; ``HC_PROBE_TIMEOUT_SECONDS = 5.0``;
``HC_TOOL_PACKAGE_ID = "sil.machine.morphology.hermitcrab.tool"``.

Hermetic: ``subprocess.run`` / ``shutil.which`` / ``USERPROFILE`` / ``HOME`` /
``HC_TOOL_PATH`` are monkeypatched; the ``windows_only`` tests run the real
fake hc (tests/fakes/hc.cmd) through the override source.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server import parser_probe  # noqa: E402


HELP_TEXT = (
    "Usage: hc [OPTIONS]\r\n"
    "HermitCrab.NET is a phonological and morphological parser.\r\n"
    "\r\n"
    "  -i, --input-file=FILE      read configuration from FILE\r\n"
    "  -h, --help                 show this help message and exit\r\n"
)
OTHER_TOOL_TEXT = (
    "Usage: hc [options] <file>\r\n"
    "hc - HydroCarbon molecular weight calculator, version 2.3\r\n"
)
RUNTIME_MISSING_STDERR = (
    "You must install or update .NET to run this application.\r\n"
    "\r\n"
    "App: C:\\Users\\J\u00f6s\u00e9\\.dotnet\\tools\\hc.exe\r\n"
    "Architecture: x64\r\n"
    "Framework: 'Microsoft.NETCore.App', version '10.0.0' (x64)\r\n"
    ".NET location: C:\\Program Files\\dotnet\\\r\n"
)
RUNTIME_MISSING_EXIT_UNSIGNED = 0x80008096
RUNTIME_MISSING_EXIT_SIGNED = 0x80008096 - (1 << 32)

TOOL_LIST_TEXT = (
    "Package Id                                  Version      Commands\r\n"
    "---------------------------------------------------------------------\r\n"
    "dotnet-ef                                   8.0.1        dotnet-ef\r\n"
    "sil.machine.morphology.hermitcrab.tool      3.8.2        hc\r\n"
)


def u16(text: str) -> bytes:
    return text.encode("utf-16-le")


# ---------------------------------------------------------------------------
# Seams
# ---------------------------------------------------------------------------


class FakeRun:
    """Stands in for ``subprocess.run``: answers ``... -h`` and
    ``dotnet tool list -g``; any other argv is a test failure."""

    def __init__(
        self,
        *,
        help_rc: int = -1,
        help_stdout: bytes = u16(HELP_TEXT),
        help_stderr: bytes = b"",
        help_exc: Optional[BaseException] = None,
        list_rc: int = 0,
        list_stdout: str = "",
        list_stderr: str = "",
        list_exc: Optional[BaseException] = None,
        help_by_path: Optional[dict] = None,
    ) -> None:
        self.help = (help_rc, help_stdout, help_stderr, help_exc)
        # {str(hc path): (rc, stdout, stderr)} overrides `help` for that path.
        self.help_by_path = {str(k): v for k, v in (help_by_path or {}).items()}
        self.listing = (list_rc, list_stdout, list_stderr, list_exc)
        self.calls: List[tuple] = []

    def __call__(self, argv, *args, **kwargs):
        argv = [str(a) for a in argv]
        self.calls.append((argv, kwargs))
        if argv and argv[-1] == "-h":
            if argv[-2] in self.help_by_path:
                rc, out, err = self.help_by_path[argv[-2]]
                return subprocess.CompletedProcess(argv, rc, out, err)
            rc, out, err, exc = self.help
            if exc is not None:
                raise exc
            return subprocess.CompletedProcess(argv, rc, out, err)
        if argv[1:] == ["tool", "list", "-g"]:
            rc, out, err, exc = self.listing
            if exc is not None:
                raise exc
            if kwargs.get("text") or kwargs.get("encoding") or kwargs.get("universal_newlines"):
                return subprocess.CompletedProcess(argv, rc, out, err)
            return subprocess.CompletedProcess(argv, rc, out.encode("utf-8"), err.encode("utf-8"))
        raise AssertionError(f"unexpected subprocess.run argv: {argv!r}")

    def help_calls(self) -> List[tuple]:
        return [c for c in self.calls if c[0] and c[0][-1] == "-h"]

    def list_calls(self) -> List[tuple]:
        return [c for c in self.calls if c[0][1:] == ["tool", "list", "-g"]]


def install_run(monkeypatch, fake: FakeRun) -> FakeRun:
    monkeypatch.setattr(parser_probe.subprocess, "run", fake)
    return fake


def install_which(monkeypatch, mapping: dict) -> None:
    def fake_which(name, *args, **kwargs):
        value = mapping.get(name)
        return str(value) if value is not None else None

    monkeypatch.setattr(parser_probe.shutil, "which", fake_which)


def make_file(path: Path, content: bytes = b"MZ fake") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def clear_cache() -> None:
    clear = getattr(parser_probe, "clear_hc_probe_cache", None)
    if clear is not None:
        clear()


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real override, PATH hit, tools dir or dotnet reaches discovery."""
    monkeypatch.delenv(parser_probe.HC_PATH_ENV_VAR, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    install_which(monkeypatch, {})
    install_run(monkeypatch, FakeRun())
    clear_cache()
    yield home
    clear_cache()


def tools_dir(home: Path) -> Path:
    return home / ".dotnet" / "tools"


# ---------------------------------------------------------------------------
# Public names
# ---------------------------------------------------------------------------


class TestPublicNames:
    def test_new_signals_exist_and_stay_outside_closed_signals(self):
        assert parser_probe.SANDBOX_SIGNAL_RUNTIME_MISSING == "runtime_missing"
        assert parser_probe.SANDBOX_SIGNAL_NOT_HERMITCRAB == "not_hermitcrab"
        for sig in ("runtime_missing", "not_hermitcrab", "not_found", "timeout"):
            assert sig not in parser_probe.CLOSED_SIGNALS

    def test_source_vocabulary(self):
        assert parser_probe.HC_SOURCE_OVERRIDE == "override"
        assert parser_probe.HC_SOURCE_PATH == "path"
        assert parser_probe.HC_SOURCE_DOTNET_TOOLS_DIR == "dotnet_tools_dir"
        assert parser_probe.HC_SOURCE_DOTNET_TOOL_LIST == "dotnet_tool_list"
        assert parser_probe.HC_SOURCES == frozenset(
            {"override", "path", "dotnet_tools_dir", "dotnet_tool_list"}
        )

    def test_probe_timeout_is_five_seconds(self):
        assert parser_probe.HC_PROBE_TIMEOUT_SECONDS == 5.0

    def test_discovery_result_is_a_probe_result(self, tmp_path):
        """Back-compat: existing readers use .ok/.signal/.expected_path/.detected_version."""
        hc = make_file(tmp_path / "bin" / "hc.exe")
        result = parser_probe.discover_hc_tool(override_path=hc)
        assert isinstance(result, parser_probe.HcToolDiscovery)
        assert isinstance(result, parser_probe.ProbeResult)
        assert result.ok is True
        assert result.ok == (result.found and result.starts is True)
        assert result.expected_path == str(hc)


# ---------------------------------------------------------------------------
# FR-001: each source in isolation, with `source` recorded
# ---------------------------------------------------------------------------


class TestEachSourceInIsolation:
    def test_override_env_var(self, monkeypatch, tmp_path):
        hc = make_file(tmp_path / "custom" / "hc.exe")
        monkeypatch.setenv(parser_probe.HC_PATH_ENV_VAR, str(hc))

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.starts is True
        assert result.source == "override"
        assert result.path == str(hc)
        assert result.signal is None

    def test_override_argument_beats_env(self, monkeypatch, tmp_path):
        env_hc = make_file(tmp_path / "env" / "hc.exe")
        arg_hc = make_file(tmp_path / "arg" / "hc.exe")
        monkeypatch.setenv(parser_probe.HC_PATH_ENV_VAR, str(env_hc))

        result = parser_probe.discover_hc_tool(override_path=arg_hc)

        assert result.source == "override"
        assert result.path == str(arg_hc)

    def test_path(self, monkeypatch, tmp_path):
        hc = make_file(tmp_path / "onpath" / "hc.exe")
        install_which(monkeypatch, {"hc": hc})

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.starts is True
        assert result.source == "path"
        assert result.path == str(hc)
        assert result.expected_path == str(hc)

    def test_dotnet_tools_dir(self, isolated):
        hc = make_file(tools_dir(isolated) / "hc.exe")

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.starts is True
        assert result.source == "dotnet_tools_dir"
        assert Path(result.path) == hc
        assert result.invoke_argv == [str(hc)]

    def test_dotnet_tool_list(self, monkeypatch, tmp_path):
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        install_which(monkeypatch, {"dotnet": dotnet})
        fake = install_run(monkeypatch, FakeRun(list_stdout=TOOL_LIST_TEXT))

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.source == "dotnet_tool_list"
        assert result.detected_version == "3.8.2"
        # No file to run: startability is unobserved, so never ready.
        assert result.starts is not True
        assert result.ok is False
        assert fake.list_calls(), "dotnet tool list -g was never run"
        _, kwargs = fake.list_calls()[0]
        # Pattern-audit sweep 4: an explicit encoding, never the locale default.
        assert kwargs.get("encoding"), f"tool list run without explicit encoding: {kwargs!r}"

    def test_nothing_anywhere_is_not_found(self):
        result = parser_probe.discover_hc_tool()

        assert result.found is False
        assert result.ok is False
        assert result.signal == "not_found"
        assert result.source is None
        assert result.expected_path == parser_probe.HC_EXPECTED_PATH_DESCRIPTION

    def test_tool_list_timeout_is_timeout_not_not_found(self, monkeypatch, tmp_path):
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        install_which(monkeypatch, {"dotnet": dotnet})
        install_run(
            monkeypatch,
            FakeRun(list_exc=subprocess.TimeoutExpired(["dotnet"], 5.0)),
        )

        result = parser_probe.discover_hc_tool()

        assert result.found is False
        assert result.signal == "timeout"


class TestOrder:
    def test_path_beats_tools_dir_and_list(self, monkeypatch, isolated, tmp_path):
        on_path = make_file(tmp_path / "onpath" / "hc.exe")
        make_file(tools_dir(isolated) / "hc.exe")
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        install_which(monkeypatch, {"hc": on_path, "dotnet": dotnet})
        fake = install_run(monkeypatch, FakeRun(list_stdout=TOOL_LIST_TEXT))

        result = parser_probe.discover_hc_tool()

        assert result.source == "path"
        assert fake.list_calls() == []

    def test_tools_dir_found_with_path_lacking_it(self, monkeypatch, isolated, tmp_path):
        """US1 scenario 2: the server started before the tool was installed,
        so its PATH has no tools dir -- the real shutil.which misses."""
        empty = tmp_path / "emptybin"
        empty.mkdir()
        monkeypatch.setenv("PATH", str(empty))
        monkeypatch.setattr(parser_probe.shutil, "which", _REAL_WHICH)
        assert _REAL_WHICH("hc") is None
        hc = make_file(tools_dir(isolated) / "hc.exe")

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.source == "dotnet_tools_dir"
        assert Path(result.path) == hc

    def test_missing_override_does_not_fall_through(self, monkeypatch, isolated, tmp_path):
        on_path = make_file(tmp_path / "onpath" / "hc.exe")
        make_file(tools_dir(isolated) / "hc.exe")
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        install_which(monkeypatch, {"hc": on_path, "dotnet": dotnet})
        fake = install_run(monkeypatch, FakeRun(list_stdout=TOOL_LIST_TEXT))
        missing = tmp_path / "nowhere" / "hc.exe"
        monkeypatch.setenv(parser_probe.HC_PATH_ENV_VAR, str(missing))

        result = parser_probe.discover_hc_tool()

        assert result.found is False
        assert result.signal == "not_found"
        assert result.source == "override"
        assert result.expected_path == str(missing)
        assert fake.calls == [], "a missing override must not probe or list anything"

    def test_sdk_less_tool_list_failure_plus_direct_hit_is_found(
        self, monkeypatch, isolated, tmp_path
    ):
        """Edge case: no SDK, so `dotnet tool list -g` would fail -- but step 3
        already found the file, so the listing never runs and never reads as
        'not installed'. The typical FLEx machine: the runtime is missing too."""
        hc = make_file(tools_dir(isolated) / "hc.exe")
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        install_which(monkeypatch, {"dotnet": dotnet})
        fake = install_run(
            monkeypatch,
            FakeRun(
                help_rc=RUNTIME_MISSING_EXIT_UNSIGNED,
                help_stdout=b"",
                help_stderr=RUNTIME_MISSING_STDERR.encode("utf-8"),
                list_rc=145,
                list_stderr="No .NET SDKs were found.",
            ),
        )

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.source == "dotnet_tools_dir"
        assert Path(result.path) == hc
        assert result.starts is False
        assert result.signal == "runtime_missing"
        assert fake.list_calls() == []

    def test_not_hermitcrab_on_path_falls_through_to_tools_dir(
        self, monkeypatch, isolated, tmp_path
    ):
        """A stray, unrelated `hc` on PATH must not hide the real one."""
        stray = make_file(tmp_path / "onpath" / "hc.exe")
        real = make_file(tools_dir(isolated) / "hc.exe")
        install_which(monkeypatch, {"hc": stray})
        install_run(
            monkeypatch,
            FakeRun(help_by_path={stray: (1, u16(OTHER_TOOL_TEXT), b"")}),
        )

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.starts is True
        assert result.source == "dotnet_tools_dir"
        assert Path(result.path) == real

    def test_not_hermitcrab_everywhere_reports_not_hermitcrab(
        self, monkeypatch, isolated, tmp_path
    ):
        stray = make_file(tmp_path / "onpath" / "hc.exe")
        install_which(monkeypatch, {"hc": stray})
        install_run(monkeypatch, FakeRun(help_rc=1, help_stdout=u16(OTHER_TOOL_TEXT)))

        result = parser_probe.discover_hc_tool()

        assert result.found is False
        assert result.signal == "not_hermitcrab"
        assert result.source == "path"
        assert result.expected_path == str(stray)

    def test_not_hermitcrab_override_does_not_fall_through(
        self, monkeypatch, isolated, tmp_path
    ):
        stray = make_file(tmp_path / "custom" / "hc.exe")
        make_file(tools_dir(isolated) / "hc.exe")
        install_run(
            monkeypatch,
            FakeRun(help_by_path={stray: (1, u16(OTHER_TOOL_TEXT), b"")}),
        )

        result = parser_probe.discover_hc_tool(override_path=stray)

        assert result.found is False
        assert result.signal == "not_hermitcrab"
        assert result.source == "override"


# ---------------------------------------------------------------------------
# FR-003 / FR-004: the `hc -h` identity + startability probe
# ---------------------------------------------------------------------------


class TestProbeInvocation:
    def test_exe_argv_is_exactly_hc_dash_h_with_stdin_closed_and_5s(self, tmp_path, monkeypatch):
        hc = make_file(tmp_path / "bin" / "hc.exe")
        fake = install_run(monkeypatch, FakeRun())

        parser_probe.discover_hc_tool(override_path=hc)

        assert len(fake.help_calls()) == 1
        argv, kwargs = fake.help_calls()[0]
        assert argv == [str(hc), "-h"]
        assert kwargs.get("stdin") == subprocess.DEVNULL
        assert kwargs.get("timeout") == 5.0
        # Bytes mode: stdout (UTF-16LE) and stderr (UTF-8) need different decodings.
        assert not kwargs.get("text") and not kwargs.get("universal_newlines")
        assert "encoding" not in kwargs

    def test_dll_form_runs_as_dotnet_hc_dll(self, tmp_path, monkeypatch):
        dll = make_file(tmp_path / "tool" / "hc.dll")
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        install_which(monkeypatch, {"dotnet": dotnet})
        fake = install_run(monkeypatch, FakeRun())

        result = parser_probe.discover_hc_tool(override_path=dll)

        assert result.found is True
        assert result.starts is True
        assert result.invoke_argv == [str(dotnet), str(dll)]
        argv, kwargs = fake.help_calls()[0]
        assert argv == [str(dotnet), str(dll), "-h"]
        assert kwargs.get("stdin") == subprocess.DEVNULL
        assert kwargs.get("timeout") == 5.0

    def test_dll_without_dotnet_host_cannot_start(self, tmp_path, monkeypatch):
        dll = make_file(tmp_path / "tool" / "hc.dll")
        fake = install_run(monkeypatch, FakeRun())  # which("dotnet") -> None (isolated)

        result = parser_probe.discover_hc_tool(override_path=dll)

        assert result.found is True
        assert result.starts is False
        assert result.signal == "runtime_missing"
        assert "dotnet host not found on PATH" in result.reason
        assert result.ok is False
        assert fake.help_calls() == []

    def test_hc_invoke_argv_helper(self, tmp_path, monkeypatch):
        dotnet = make_file(tmp_path / "dotnet" / "dotnet.exe")
        install_which(monkeypatch, {"dotnet": dotnet})
        exe = tmp_path / "hc.exe"
        dll = tmp_path / "hc.dll"
        assert parser_probe.hc_invoke_argv(exe) == [str(exe)]
        assert parser_probe.hc_invoke_argv(dll) == [str(dotnet), str(dll)]


class TestProbeClassification:
    def _discover(self, monkeypatch, tmp_path, **run_kwargs):
        hc = make_file(tmp_path / "bin" / "hc.exe")
        install_run(monkeypatch, FakeRun(**run_kwargs))
        return parser_probe.discover_hc_tool(override_path=hc)

    def test_usage_text_decoded_utf16le_is_ready(self, monkeypatch, tmp_path):
        result = self._discover(monkeypatch, tmp_path)
        assert (result.found, result.starts, result.signal) == (True, True, None)
        assert result.ok is True

    def test_usage_text_with_bom_is_ready(self, monkeypatch, tmp_path):
        result = self._discover(
            monkeypatch, tmp_path, help_stdout=b"\xff\xfe" + u16(HELP_TEXT)
        )
        assert (result.found, result.starts) == (True, True)

    def test_other_usage_text_is_not_hermitcrab(self, monkeypatch, tmp_path):
        result = self._discover(
            monkeypatch, tmp_path, help_rc=1, help_stdout=u16(OTHER_TOOL_TEXT)
        )
        assert result.found is False
        assert result.signal == "not_hermitcrab"
        assert result.ok is False

    def test_usage_text_in_the_wrong_encoding_is_not_hermitcrab(self, monkeypatch, tmp_path):
        """Only the one real encoding counts -- hc writes UTF-16LE."""
        result = self._discover(
            monkeypatch, tmp_path, help_stdout=HELP_TEXT.encode("utf-8")
        )
        assert result.found is False
        assert result.signal == "not_hermitcrab"

    def test_only_one_usage_line_is_not_hermitcrab(self, monkeypatch, tmp_path):
        result = self._discover(
            monkeypatch, tmp_path, help_stdout=u16("Usage: hc [OPTIONS]\r\n")
        )
        assert result.found is False
        assert result.signal == "not_hermitcrab"

    @pytest.mark.parametrize(
        "exit_code", [RUNTIME_MISSING_EXIT_UNSIGNED, RUNTIME_MISSING_EXIT_SIGNED]
    )
    def test_host_failure_is_runtime_missing_naming_the_runtime(
        self, monkeypatch, tmp_path, exit_code
    ):
        result = self._discover(
            monkeypatch,
            tmp_path,
            help_rc=exit_code,
            help_stdout=b"",
            help_stderr=RUNTIME_MISSING_STDERR.encode("utf-8"),  # UTF-8, non-ASCII path
        )
        assert result.found is True
        assert result.starts is False
        assert result.signal == "runtime_missing"
        assert result.ok is False
        assert result.reason and "Microsoft.NETCore.App" in result.reason
        assert "10.0" in result.reason

    def test_framework_missing_stderr_alone_is_runtime_missing(self, monkeypatch, tmp_path):
        result = self._discover(
            monkeypatch,
            tmp_path,
            help_rc=1,
            help_stdout=b"",
            help_stderr=RUNTIME_MISSING_STDERR.replace("10.0.0", "10.0.3").encode("utf-8"),
        )
        assert (result.found, result.starts, result.signal) == (True, False, "runtime_missing")
        assert "10.0.3" in result.reason

    def test_host_exit_0x8000809a_without_text_is_runtime_missing(self, monkeypatch, tmp_path):
        result = self._discover(
            monkeypatch, tmp_path, help_rc=0x8000809A, help_stdout=b"", help_stderr=b""
        )
        assert (result.found, result.starts, result.signal) == (True, False, "runtime_missing")

    def test_probe_timeout_is_found_but_cannot_start(self, monkeypatch, tmp_path):
        result = self._discover(
            monkeypatch, tmp_path, help_exc=subprocess.TimeoutExpired(["hc", "-h"], 5.0)
        )
        assert result.found is True
        assert result.starts is False
        assert result.signal == "timeout"
        assert result.ok is False


class TestProbeMemo:
    def test_memoised_on_path_size_mtime(self, monkeypatch, tmp_path):
        hc = make_file(tmp_path / "bin" / "hc.exe")
        fake = install_run(monkeypatch, FakeRun())

        first = parser_probe.probe_hc(hc)
        second = parser_probe.probe_hc(hc)
        parser_probe.discover_hc_tool(override_path=hc)

        assert len(fake.help_calls()) == 1
        assert first == second
        assert (first.found, first.starts) == (True, True)

    def test_changed_file_is_probed_again(self, monkeypatch, tmp_path):
        hc = make_file(tmp_path / "bin" / "hc.exe")
        fake = install_run(monkeypatch, FakeRun())
        parser_probe.probe_hc(hc)

        hc.write_bytes(b"MZ fake, reinstalled and larger")
        st = hc.stat()
        os.utime(hc, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
        parser_probe.probe_hc(hc)

        assert len(fake.help_calls()) == 2

    def test_clear_cache_forces_a_new_probe(self, monkeypatch, tmp_path):
        hc = make_file(tmp_path / "bin" / "hc.exe")
        fake = install_run(monkeypatch, FakeRun())
        parser_probe.probe_hc(hc)
        parser_probe.clear_hc_probe_cache()
        parser_probe.probe_hc(hc)
        assert len(fake.help_calls()) == 2

    def test_probe_result_shape(self, monkeypatch, tmp_path):
        hc = make_file(tmp_path / "bin" / "hc.exe")
        install_run(
            monkeypatch,
            FakeRun(help_rc=RUNTIME_MISSING_EXIT_UNSIGNED, help_stdout=b"",
                    help_stderr=RUNTIME_MISSING_STDERR.encode("utf-8")),
        )
        probe = parser_probe.probe_hc(hc)
        assert isinstance(probe, parser_probe.HcProbe)
        assert probe.found is True and probe.starts is False
        assert probe.signal == "runtime_missing"
        assert "Microsoft.NETCore.App" in probe.reason
        assert probe.exit_code in (RUNTIME_MISSING_EXIT_UNSIGNED, RUNTIME_MISSING_EXIT_SIGNED)


# ---------------------------------------------------------------------------
# The real fake hc (tests/fakes/hc.cmd), through the override source
# ---------------------------------------------------------------------------


@pytest.mark.windows_only
class TestAgainstFakeHc:
    @pytest.fixture(autouse=True)
    def real_subprocess(self, monkeypatch):
        monkeypatch.setattr(parser_probe.subprocess, "run", _REAL_RUN)

    def test_normal_is_ready_and_ran_only_dash_h(self, fake_hc, monkeypatch):
        monkeypatch.setenv(parser_probe.HC_PATH_ENV_VAR, str(fake_hc.path))

        result = parser_probe.discover_hc_tool()

        assert (result.found, result.starts, result.signal) == (True, True, None)
        assert result.source == "override"
        assert result.invoke_argv == [str(fake_hc.path)]
        assert [inv["argv"] for inv in fake_hc.invocations()] == [["-h"]]

    def test_not_hermitcrab(self, fake_hc, monkeypatch):
        fake_hc.set(mode="not_hermitcrab")
        monkeypatch.setenv(parser_probe.HC_PATH_ENV_VAR, str(fake_hc.path))

        result = parser_probe.discover_hc_tool()

        assert result.found is False
        assert result.signal == "not_hermitcrab"

    def test_runtime_missing(self, fake_hc, monkeypatch):
        fake_hc.set(mode="runtime_missing", runtime_version="10.0.0")
        monkeypatch.setenv(parser_probe.HC_PATH_ENV_VAR, str(fake_hc.path))

        result = parser_probe.discover_hc_tool()

        assert result.found is True
        assert result.starts is False
        assert result.signal == "runtime_missing"
        assert "Microsoft.NETCore.App" in result.reason
        assert "10.0" in result.reason

    def test_bom_on_stdout_is_still_ready(self, fake_hc, monkeypatch):
        fake_hc.set(bom=1)
        monkeypatch.setenv(parser_probe.HC_PATH_ENV_VAR, str(fake_hc.path))

        result = parser_probe.discover_hc_tool()

        assert (result.found, result.starts) == (True, True)


# Captured at import, before any fixture patches them.
_REAL_RUN = subprocess.run
_REAL_WHICH = __import__("shutil").which
