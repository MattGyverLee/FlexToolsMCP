#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-tests for parser-check CP5's fakes (tests/fakes/), so the sandbox-spine
tests that drive hcparse.ps1 against them stand on proven ground.

The Python fakes are run directly with this interpreter (portable); the
`.cmd` shims are exercised on Windows only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from flextoolsmcp.server.parse.measure import summarize_parser_parameters

HC_FAKE = Path(__file__).parent / "fakes" / "hc_fake.py"
GEN_FAKE = Path(__file__).parent / "fakes" / "generate_fake.py"

GRAMMAR = {
    "language": "Sena Fake",
    "words": {
        "membaca": [[["mem", "ACT"], ["baca", "read"]]],
        "baca": [[["baca", "read"]], [["baca", ""]]],
        "xyz": [],
        "q#": {"invalid_segment": 2},
        "don't": [[["don't", "NEG"]]],
        # An astral-plane form: 2 UTF-16 code units, 1 Python code point (F-6).
        "\U00010400a": [[["\U00010400", "X"], ["a", "LONGGLOSS"]]],
    },
}


def u32(code: int) -> int:
    return code & 0xFFFFFFFF


def run_py(script: Path, args, timeout: float = 30):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
    )


def hc_lines(proc) -> list:
    return proc.stdout.decode("utf-16-le").split("\r\n")


@pytest.fixture
def hc_env(fake_hc, tmp_path):
    config = fake_hc.write_config(tmp_path / "hc-config.xml", GRAMMAR)
    script = tmp_path / "hc-script.txt"

    def run(lines, timeout: float = 30):
        script.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        return run_py(HC_FAKE, ["-i", config, "-s", script], timeout=timeout)

    return run


# ---------------------------------------------------------------------------
# hc_fake.py
# ---------------------------------------------------------------------------


def test_hc_help_is_utf16_usage_and_exits_minus_one(fake_hc):
    proc = run_py(HC_FAKE, ["-h"])
    lines = hc_lines(proc)
    assert lines[0] == "Usage: hc [OPTIONS]"
    assert lines[1] == "HermitCrab.NET is a phonological and morphological parser."
    assert u32(proc.returncode) in (0xFFFFFFFF, 0xFF)
    assert not proc.stdout.startswith(b"\xff\xfe")


def test_hc_no_input_file_prints_usage(fake_hc):
    proc = run_py(HC_FAKE, [])
    assert hc_lines(proc)[0] == "Usage: hc [OPTIONS]"


def test_hc_parse_blocks_and_stats(hc_env):
    proc = hc_env(
        [
            'parse "membaca"',
            'parse "baca"',
            'parse "xyz"',
            'parse "q#"',
            'parse "don\'t"',
            'parse "\U00010400a"',
            "stats -p",
        ]
    )
    assert proc.returncode == 0
    out = proc.stdout.decode("utf-16-le")
    assert out.startswith(
        'Reading configuration file "hc-config.xml"... done.\r\n'
        "Compiling rules... done.\r\nSena Fake loaded.\r\n\r\n"
    )
    assert (
        'Parsing "membaca"\r\nParse 1\r\nMorphs: mem baca\r\nGloss:  ACT read\r\n'
        "Parse time: 0ms\r\n\r\n"
    ) in out
    # Two parses; an empty gloss prints as `?` (F-7).
    assert "Parse 2\r\nMorphs: baca\r\nGloss:  ?   \r\n" in out
    assert 'Parsing "xyz"\r\nNo valid parses.\r\nParse time: 0ms\r\n\r\n' in out
    assert (
        'Parsing "q#"\r\nThe word contains an invalid segment at position 2.\r\n\r\n'
    ) in out
    assert "Morphs: don't\r\n" in out
    # Column width counts UTF-16 code units: the astral form is 2 wide.
    assert "Morphs: \U00010400 a        \r\nGloss:  X  LONGGLOSS\r\n" in out
    assert out.endswith("# of parses: 6, successful: 4, failed: 1, error: 1\r\n\r\n")


def test_hc_test_sections(hc_env):
    proc = hc_env(
        [
            'test -p "mem:ACT|baca:read" "membaca"',
            'test -p "baca:read" "baca"',
            'test "xyz"',
            'test -p "x:y" "xyz"',
            "stats -t",
        ]
    )
    out = proc.stdout.decode("utf-16-le")
    assert 'Testing "membaca"\r\nTest passed.\r\n\r\n' in out
    assert (
        'Testing "baca"\r\nTest failed.\r\nExpected parses:\r\nNone\r\n'
        "Actual parses:\r\nMorphs: baca\r\nGloss:  ?   \r\n\r\n"
    ) in out
    assert 'Testing "xyz"\r\nTest passed.\r\n\r\n' in out
    assert (
        'Testing "xyz"\r\nTest failed.\r\nExpected parses:\r\nMorphs: x\r\nGloss:  y\r\n'
        "Actual parses:\r\nNone\r\n\r\n"
    ) in out
    assert out.endswith("# of tests: 4, passed: 2, failed: 2, error: 0\r\n\r\n")


def test_hc_stats_override(hc_env, fake_hc):
    fake_hc.set(parse_stats="9,8,7,6")
    out = hc_env(['parse "xyz"', "stats -p"]).stdout.decode("utf-16-le")
    assert "# of parses: 9, successful: 8, failed: 7, error: 6\r\n" in out


def test_hc_load_error_knob(hc_env, fake_hc):
    fake_hc.set(mode="load_error", load_error="bad grammar")
    proc = hc_env(['parse "xyz"'])
    assert hc_lines(proc)[:2] == [
        'Reading configuration file "hc-config.xml"... ',
        "Load Error: bad grammar",
    ]
    assert u32(proc.returncode) in (0xFFFFFFFF, 0xFF)


def test_hc_missing_and_empty_config(fake_hc, tmp_path):
    script = tmp_path / "s.txt"
    script.write_text('parse "a"\n', encoding="utf-8")
    proc = run_py(HC_FAKE, ["-i", tmp_path / "nope.xml", "-s", script])
    assert hc_lines(proc)[1].startswith("IO Error: Could not find file")
    empty = tmp_path / "empty.xml"
    empty.write_bytes(b"")
    proc = run_py(HC_FAKE, ["-i", empty, "-s", script])
    assert hc_lines(proc)[1] == "Load Error: Root element is missing."
    assert u32(proc.returncode) in (0xFFFFFFFF, 0xFF)


def test_hc_runtime_missing(fake_hc):
    fake_hc.set(mode="runtime_missing", runtime_version="10.0.0")
    proc = run_py(HC_FAKE, ["-h"])
    err = proc.stderr.decode("utf-8")
    assert "You must install or update .NET to run this application." in err
    assert "Framework: 'Microsoft.NETCore.App', version '10.0.0' (x64)" in err
    assert proc.stdout == b""
    if sys.platform == "win32":
        assert u32(proc.returncode) == 0x80008096


def test_hc_not_hermitcrab(fake_hc):
    fake_hc.set(mode="not_hermitcrab")
    proc = run_py(HC_FAKE, ["-h"])
    out = proc.stdout.decode("utf-16-le")
    assert "HermitCrab.NET" not in out and out.startswith("Usage:")
    assert proc.returncode == 1


def test_hc_echo_round_trips_non_latin(fake_hc, tmp_path):
    fake_hc.set(mode="echo")
    lines = ['parse "பாடம்"', 'parse "\U00010400"', "stats -p"]
    script = tmp_path / "s.txt"
    script.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    proc = run_py(HC_FAKE, ["-i", tmp_path / "x.xml", "-s", script])
    assert proc.returncode == 0
    assert proc.stdout.decode("utf-16-le") == "".join(line + "\r\n" for line in lines)


def test_hc_bom_knob(hc_env, fake_hc):
    fake_hc.set(bom=1)
    assert hc_env(['parse "xyz"']).stdout.startswith(b"\xff\xfe")


def test_hc_sleep_on_word_leaves_header_in_flight(hc_env, fake_hc):
    fake_hc.set(sleep_on_word=1, sleep_seconds=60)
    with pytest.raises(subprocess.TimeoutExpired) as info:
        hc_env(['parse "membaca"', 'parse "xyz"', 'parse "baca"'], timeout=5)
    out = (info.value.stdout or info.value.output or b"").decode("utf-16-le")
    # First word must finish (Parse time is wall-clock -- don't pin to 0ms).
    assert 'Parsing "membaca"' in out
    assert re.search(r"Parse time: \d+ms", out)
    assert out.endswith('Parsing "xyz"\r\n')


def test_hc_crash_on_word(hc_env, fake_hc):
    fake_hc.set(crash_on_word=1)
    proc = hc_env(['parse "membaca"', 'parse "xyz"', 'parse "baca"'])
    out = proc.stdout.decode("utf-16-le")
    assert out.endswith('Parsing "xyz"\r\n')
    assert "Unhandled exception." in proc.stderr.decode("utf-8")
    assert proc.returncode != 0


def test_hc_records_argv(hc_env, fake_hc):
    hc_env(['parse "xyz"'])
    (call,) = fake_hc.invocations()
    assert call["argv"][0] == "-i" and call["argv"][2] == "-s"
    assert call["script"] == 'parse "xyz"\n'


# ---------------------------------------------------------------------------
# generate_fake.py
# ---------------------------------------------------------------------------


def _copy_layout(tmp_path, project):
    """work/<run_id>/<name>/<name>.fwdata, as the script's copy lays it out."""
    work = tmp_path / "work" / "run1"
    (work / project.name).mkdir(parents=True)
    fwdata = work / project.name / project.fwdata.name
    fwdata.write_bytes(project.fwdata.read_bytes())
    (work / project.name / "WritingSystemStore").mkdir()
    (work / project.name / "WritingSystemStore" / "en.ldml").write_text(
        "<ldml />", encoding="utf-8"
    )
    (work / ".flextoolsmcp-sandbox-work").write_text("{}", encoding="utf-8")
    return work, fwdata


def test_generator_help_with_too_few_args(fake_generator):
    proc = run_py(GEN_FAKE, [])
    out = proc.stdout.decode("utf-8")
    assert out.startswith(
        "Generates a HermitCrab configuration file from a FieldWorks project.\r\n"
    )
    assert proc.returncode == 0 and "Writing completed." not in out


def test_generator_missing_fwdata(fake_generator, tmp_path):
    proc = run_py(GEN_FAKE, [tmp_path / "none.fwdata", tmp_path / "c.xml"])
    assert proc.stdout.decode() == "The FieldWorks project file could not be found.\r\n"
    assert proc.returncode == 1


def test_generator_success_lists_folder_and_writes_loadable_config(
    fake_generator, fake_hc, fake_project, tmp_path
):
    work, fwdata = _copy_layout(tmp_path, fake_project)
    config = tmp_path / "out" / "hc-config.xml"
    config.parent.mkdir()
    fake_generator.set(grammar=json.dumps(GRAMMAR))
    proc = run_py(GEN_FAKE, [fwdata, config])
    assert proc.returncode == 0
    assert proc.stdout.decode().split("\r\n")[:4] == [
        "Loading FieldWorks project...",
        "Loading completed.",
        "Writing HC configuration file...",
        "Writing completed.",
    ]
    listing = fake_generator.listing()
    assert Path(listing["root"]) == work
    assert "FakeProj/FakeProj.fwdata" in listing["files"]
    assert "FakeProj/WritingSystemStore" in listing["dirs"]
    # The config round-trips into the fake hc.
    script = tmp_path / "s.txt"
    script.write_text('parse "membaca"\n', encoding="utf-8")
    out = run_py(HC_FAKE, ["-i", config, "-s", script]).stdout.decode("utf-16-le")
    assert "Sena Fake loaded." in out and "Morphs: mem baca" in out


def test_generator_listing_sees_a_forbidden_file(
    fake_generator, fake_project, tmp_path
):
    work, fwdata = _copy_layout(tmp_path, fake_project)
    (fwdata.parent / (fwdata.name + ".lock")).write_text("1", encoding="utf-8")
    run_py(GEN_FAKE, [fwdata, tmp_path / "c.xml"])
    assert "FakeProj/FakeProj.fwdata.lock" in fake_generator.listing()["files"]


@pytest.mark.parametrize(
    "mode,needle",
    [
        ("locked", "The FieldWorks project is currently open in another application."),
        (
            "migration",
            "The FieldWorks project was created with an older version of FLEx.",
        ),
    ],
)
def test_generator_refusals(fake_generator, fake_project, tmp_path, mode, needle):
    fake_generator.set(mode=mode)
    config = tmp_path / "c.xml"
    proc = run_py(GEN_FAKE, [fake_project.fwdata, config])
    out = proc.stdout.decode()
    assert proc.returncode == 1 and needle in out and "Loading failed." in out
    assert not config.exists()


def test_generator_honor_lock(fake_generator, fake_project, tmp_path):
    fake_generator.set(honor_lock=1)
    proc = run_py(GEN_FAKE, [fake_project.fwdata, tmp_path / "c.xml"])
    assert proc.returncode == 1 and "currently open" in proc.stdout.decode()


def test_generator_crash(fake_generator, fake_project, tmp_path):
    fake_generator.set(mode="crash")
    config = tmp_path / "c.xml"
    proc = run_py(GEN_FAKE, [fake_project.fwdata, config])
    assert proc.returncode != 0 and "Writing completed." not in proc.stdout.decode()
    assert "NotImplementedException" in proc.stderr.decode()
    assert not config.exists()


def test_generator_empty_config(fake_generator, fake_project, tmp_path):
    fake_generator.set(mode="empty_config")
    config = tmp_path / "c.xml"
    proc = run_py(GEN_FAKE, [fake_project.fwdata, config])
    assert proc.returncode == 0 and "Writing completed." in proc.stdout.decode()
    assert config.stat().st_size == 0


def test_generator_load_errors(fake_generator, fake_project, tmp_path):
    fake_generator.set(load_errors=8)
    lines = (
        run_py(GEN_FAKE, [fake_project.fwdata, tmp_path / "c.xml"])
        .stdout.decode()
        .split("\r\n")
    )
    assert lines[0] == "Loading FieldWorks project..."
    errors = lines[1:9]
    assert errors[0] == 'The form "fake1" contains an undefined phoneme at 1.'
    assert errors[6].startswith('The rewrite rule "rule7" is invalid.')
    assert errors[7].startswith('The form "fake8"')
    assert lines[9:13] == [
        "Loading completed.",
        "Writing HC configuration file...",
        "Writing completed.",
        "",
    ]


def test_generator_slow_start(fake_generator, fake_project, tmp_path):
    fake_generator.set(sleep_seconds=60)
    with pytest.raises(subprocess.TimeoutExpired):
        run_py(GEN_FAKE, [fake_project.fwdata, tmp_path / "c.xml"], timeout=3)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _stored_parameters(fwdata: Path):
    for _, elem in ET.iterparse(str(fwdata)):
        if elem.tag == "rt" and elem.get("class") == "MoMorphData":
            return elem.findtext("ParserParameters/Uni")
    return None


def test_fake_project_layout_and_active_parser(fake_project):
    for path in (
        fake_project.fwdata,
        fake_project.writing_systems,
        *fake_project.excluded,
    ):
        assert path.exists(), path
    summary = summarize_parser_parameters(_stored_parameters(fake_project.fwdata))
    assert summary["parseable"] and summary["active_parser"] == "HC"
    assert summary["hc"] == {"GuessRoots": "false", "MaxCompoundRules": "4"}


def test_fake_project_factory_xample(fake_project_factory):
    project = fake_project_factory(name="Sena 3", active_parser="XAmple")
    assert project.fwdata.name == "Sena 3.fwdata"
    summary = summarize_parser_parameters(_stored_parameters(project.fwdata))
    assert summary["active_parser"] == "XAmple"


def test_sandbox_root_env(sandbox_root):
    assert os.environ["FLEXTOOLSMCP_PARSE_SANDBOX_DIR"] == str(sandbox_root)
    assert sandbox_root.is_dir()


# ---------------------------------------------------------------------------
# the .cmd shims (Windows)
# ---------------------------------------------------------------------------


@pytest.mark.windows_only
def test_hc_shim_forwards_and_propagates_exit(fake_hc):
    proc = subprocess.run(
        [str(fake_hc.path), "-h"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
    )
    assert proc.stdout.decode("utf-16-le").startswith("Usage: hc [OPTIONS]\r\n")
    assert u32(proc.returncode) == 0xFFFFFFFF
    fake_hc.set(mode="runtime_missing")
    proc = subprocess.run(
        [str(fake_hc.path), "-h"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
    )
    assert u32(proc.returncode) == 0x80008096


@pytest.mark.windows_only
def test_generator_shim_with_spaced_paths(
    fake_generator, fake_project_factory, tmp_path
):
    project = fake_project_factory(name="Sena 3")
    config = tmp_path / "out dir" / "hc config.xml"
    config.parent.mkdir()
    proc = subprocess.run(
        [str(fake_generator.path), str(project.fwdata), str(config)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert config.stat().st_size > 0
    (call,) = fake_generator.invocations()
    assert call["argv"] == [str(project.fwdata), str(config)]
    fake_generator.set(mode="locked")
    proc = subprocess.run(
        [str(fake_generator.path), str(project.fwdata), str(config)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 1
