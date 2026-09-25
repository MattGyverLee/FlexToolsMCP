#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pytest configuration and shared fixtures."""

import json
import os
import shutil
import sys
import tempfile
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

# Issue #173: isolate logs for the whole suite before any test module imports
# flextoolsmcp.server.kernel (several test files import kernel at collection time).
_PYTEST_LOG_DIR: Path | None = None


def pytest_configure(config):
    """Isolate logging for the whole test run (issue #173).

    Must run before any test module imports ``kernel.setup_logging``.
    """
    global _PYTEST_LOG_DIR
    config.addinivalue_line(
        "markers",
        "windows_only: test needs Windows (skipped when sys.platform != 'win32')",
    )
    if os.environ.get("FLEXTOOLSMCP_LOG_DIR"):
        return
    _PYTEST_LOG_DIR = Path(tempfile.mkdtemp(prefix="flextoolsmcp_pytest_logs_"))
    os.environ["FLEXTOOLSMCP_LOG_DIR"] = str(_PYTEST_LOG_DIR)


def pytest_unconfigure(config):
    global _PYTEST_LOG_DIR
    if _PYTEST_LOG_DIR is not None and _PYTEST_LOG_DIR.exists():
        shutil.rmtree(_PYTEST_LOG_DIR, ignore_errors=True)
    _PYTEST_LOG_DIR = None


def require_live_flexicon():
    """Skip the calling test unless a live FieldWorks-backed flexicon import works.

    Unlike ``pytest.importorskip("flexicon")``, this also catches the bare
    ``Exception`` flexicon raises when no FieldWorks/SIL.LCModel runtime is
    present (pyflexicon is a runtime dependency, so CI always installs the
    package -- it just cannot always import successfully). See issue #115.
    """
    try:
        import flexicon  # noqa: F401
    except Exception as exc:  # noqa: BLE001 -- flexicon raises non-ImportError on missing FieldWorks
        pytest.skip(f"flexicon unavailable (no live FieldWorks install?): {exc}")
    return flexicon


@pytest.fixture
def reset_session_state():
    """Reset session state for tests that need a clean state.

    Consolidates duplicate session reset patterns from multiple test files.
    Usage: add 'reset_session_state' parameter to test function.
    """
    from flextoolsmcp.server.kernel import reset_session

    reset_session()
    yield
    # Cleanup after test
    reset_session()


# ---------------------------------------------------------------------------
# parser-check CP5: the sandbox spine's fakes (tests/fakes/)
# ---------------------------------------------------------------------------
#
# `fake_generator` hands out the `.cmd` shim, which runs the Python fake with
# THIS interpreter (FAKE_PYTHON). Knobs are environment variables (documented
# at the top of the fake) set through `monkeypatch`, so they are undone after
# the test and are inherited by any child process -- including hcparse.ps1
# and whatever it starts. (The fake `hc` is retired with the `hc` CLI,
# re-plan T107: Parse and Test run in the parse worker's `--sandbox` mode,
# driven in tests by its `--stub --sandbox` engine.)

FAKES_DIR = Path(__file__).parent / "fakes"


def pytest_collection_modifyitems(config, items):
    """`@pytest.mark.windows_only` skips off Windows."""
    if sys.platform == "win32":
        return
    skip = pytest.mark.skip(reason="windows_only: needs Windows")
    for item in items:
        if "windows_only" in item.keywords:
            item.add_marker(skip)


class FakeTool:
    """A fake executable plus its environment knobs.

    ``path`` is the `.cmd` shim to hand to the code under test; ``script`` is
    the Python fake it runs. ``set(mode="locked", load_errors=3)`` sets
    ``<PREFIX>MODE`` / ``<PREFIX>LOAD_ERRORS``; a value of None unsets it.
    Every invocation is appended to ``argv_file`` (one JSON object per line).
    """

    def __init__(self, monkeypatch, path: Path, script: Path, prefix: str, tmp: Path):
        self.path = path
        self.script = script
        self.prefix = prefix
        self._mp = monkeypatch
        for name in list(os.environ):
            if name.startswith(prefix):
                monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("FAKE_PYTHON", sys.executable)
        self.argv_file = tmp / ("%sargv.jsonl" % prefix.lower())
        self.set(argv_file=str(self.argv_file))

    def set(self, **knobs) -> "FakeTool":
        for key, value in knobs.items():
            name = self.prefix + key.upper()
            if value is None:
                self._mp.delenv(name, raising=False)
            else:
                self._mp.setenv(name, str(value))
        return self

    def invocations(self) -> list:
        if not self.argv_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.argv_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


@pytest.fixture
def fake_generator(monkeypatch, tmp_path):
    """The fake GenerateHCConfig (tests/fakes/GenerateHCConfig.cmd); knobs are FAKE_GEN_*.

    ``listing_file`` is pre-set: after a run, ``fake_generator.listing()`` is
    the JSON listing of the working folder the generator saw (FR-008).
    """
    tool = FakeTool(
        monkeypatch,
        FAKES_DIR / "GenerateHCConfig.cmd",
        FAKES_DIR / "generate_fake.py",
        "FAKE_GEN_",
        tmp_path,
    )
    tool.listing_file = tmp_path / "fake_gen_listing.json"
    tool.set(listing_file=str(tool.listing_file))

    def listing():
        if not tool.listing_file.exists():
            return None
        return json.loads(tool.listing_file.read_text(encoding="utf-8"))

    tool.listing = listing
    return tool


@pytest.fixture
def sandbox_root(monkeypatch, tmp_path):
    """A temp parse/sandbox root, installed as FLEXTOOLSMCP_PARSE_SANDBOX_DIR."""
    root = tmp_path / "parse-root"
    root.mkdir()
    monkeypatch.setenv("FLEXTOOLSMCP_PARSE_SANDBOX_DIR", str(root))
    return root


class FakeProject:
    """A fake FieldWorks project folder (see `make_fake_project`)."""

    def __init__(self, name: str, directory: Path):
        self.name = name
        self.dir = directory
        self.fwdata = directory / (name + ".fwdata")
        self.lock = directory / (name + ".fwdata.lock")
        self.writing_systems = directory / "WritingSystemStore"
        # Everything the FR-008 allowlist must leave behind.
        self.excluded = [
            self.lock,
            directory / ".hg",
            directory / "LinkedFiles",
            directory / "Backups",
        ]


def fake_fwdata_text(active_parser="HC") -> str:
    """A minimal `.fwdata` whose MoMorphData rt stores ParserParameters.

    The parameters are stored as a real project stores them: escaped XML
    inside `<Uni>`, which `summarize_parser_parameters` parses once
    unescaped. ``active_parser=None`` omits the `ActiveParser` element.
    """
    from xml.sax.saxutils import escape

    inner = "<ParserParameters><XAmple><MaxPrefixes>5</MaxPrefixes></XAmple>"
    if active_parser is not None:
        inner += "<ActiveParser>%s</ActiveParser>" % active_parser
    inner += (
        "<HC><GuessRoots>false</GuessRoots><MaxCompoundRules>4</MaxCompoundRules></HC>"
    )
    inner += "</ParserParameters>"
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<languageproject version="7000072">\n'
        '<rt class="LangProject" guid="98e6df3a-faa0-4882-8779-dc207d67ea05">\n'
        "<MorphologicalData>\n"
        '<objsur guid="b80228bc-ea5e-11de-9d24-0013722f8dec" t="o" />\n'
        "</MorphologicalData>\n"
        "</rt>\n"
        '<rt class="MoMorphData" guid="b80228bc-ea5e-11de-9d24-0013722f8dec" '
        'ownerguid="98e6df3a-faa0-4882-8779-dc207d67ea05">\n'
        "<ParserParameters>\n"
        "<Uni>%s</Uni>\n"
        "</ParserParameters>\n"
        "</rt>\n"
        "</languageproject>\n" % escape(inner)
    )


def make_fake_project(
    parent, name: str = "FakeProj", active_parser="HC"
) -> FakeProject:
    """Build `<parent>/<name>/` holding `<name>.fwdata`, `WritingSystemStore/`,
    `<name>.fwdata.lock`, `.hg/`, `LinkedFiles/` and `Backups/` (each non-empty)."""
    directory = Path(parent) / name
    directory.mkdir(parents=True)
    project = FakeProject(name, directory)
    project.fwdata.write_text(fake_fwdata_text(active_parser), encoding="utf-8")
    project.writing_systems.mkdir()
    (project.writing_systems / "en.ldml").write_text("<ldml />\n", encoding="utf-8")
    (project.writing_systems / "seh.ldml").write_text("<ldml />\n", encoding="utf-8")
    project.lock.write_text("12345\n", encoding="utf-8")
    (directory / ".hg" / "store").mkdir(parents=True)
    (directory / ".hg" / "hgrc").write_text("[paths]\n", encoding="utf-8")
    (directory / ".hg" / "store" / "00changelog.i").write_bytes(b"\x00\x01")
    (directory / "LinkedFiles" / "AudioVisual").mkdir(parents=True)
    (directory / "LinkedFiles" / "AudioVisual" / "clip.wav").write_bytes(b"RIFF")
    (directory / "Backups").mkdir()
    (directory / "Backups" / (name + " 2026-01-01.fwbackup")).write_bytes(b"PK")
    return project


@pytest.fixture
def fake_project(tmp_path):
    """A fake FieldWorks project `FakeProj` (ActiveParser HC) under tmp_path/projects."""
    return make_fake_project(tmp_path / "projects")


@pytest.fixture
def fake_project_factory(tmp_path):
    """``fake_project_factory(name="Sena 3", active_parser="XAmple")``."""
    return lambda name="FakeProj", active_parser="HC": make_fake_project(
        tmp_path / "projects", name, active_parser
    )
