#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Self-tests for parser-check CP5's fakes (tests/fakes/), so the sandbox-spine
tests that drive hcparse.ps1's Generate mode against them stand on proven
ground. (The fake `hc` is gone with the `hc` CLI, re-plan T107: Parse and
Test run in the parse worker, whose `--stub --sandbox` engine is tested in
tests/test_sandbox_worker.py.)

The Python fakes are run directly with this interpreter (portable); the
`.cmd` shims are exercised on Windows only.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from flextoolsmcp.server.parse.measure import summarize_parser_parameters

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


def run_py(script: Path, args, timeout: float = 30):
    return subprocess.run(
        [sys.executable, str(script), *[str(a) for a in args]],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
    )


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


def test_generator_success_lists_folder_and_writes_the_grammar(
    fake_generator, fake_project, tmp_path
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
    # The config carries the grammar it was given, language and all.
    root = ET.fromstring(config.read_text(encoding="utf-8"))
    assert root.find("Language").get("name") == "Sena Fake"
    assert json.loads(root.find("FakeGrammar").text)["words"]["xyz"] == []


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
