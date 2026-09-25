#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 T034 (re-plan T107): the invariants of the packaged
`hcparse.ps1` (contracts/hcparse.md, section 7) for `-Mode Generate`, its one
remaining mode. Parse and Test moved into the parse worker's `--sandbox`
mode (contracts/sandbox-worker.md); the script refuses them with exit 2.

These tests drive the REAL script through
`powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`
(`sandbox.script.build_argv`), with stdin closed, against the fake
GenerateHCConfig (tests/fakes/).

The contract these tests pin (the seam Python's sandbox modules build on):

Generate mode (`-GenerateHCConfigPath -FwData -WorkDir -ConfigOut -RunDir
[-GenerateTimeoutSeconds]`)
  * The copy is the allowlist only: `<WorkDir>/<name>/<name>.fwdata` plus
    `<WorkDir>/<name>/WritingSystemStore/**`. The generator is run on that
    copy (argv[0]); no `*.lock`, `.hg`, `LinkedFiles` or `Backups` ever
    appears in `-WorkDir`. The live project folder is only read.
  * After every invocation `-WorkDir` holds nothing the script put there:
    at most the MCP's marker `.flextoolsmcp-sandbox-work` remains.
  * `<RunDir>/generate-config.log` is the generator's stdout+stderr
    verbatim, UTF-8, no BOM.
  * A `-ConfigOut` that resolves (after `..`) under `<sandbox root>/sandboxes`
    exits 3, runs nothing and writes nothing (no run.json either).
  * Exit 0 only when the generator exited 0, the config is non-empty and the
    output holds `Writing completed.`; otherwise 4; generator timeout 6
    (the tree is killed). Bad / missing parameter or input file: 2, no
    run.json.
  * run.json: schema `flextoolsmcp.hcparse-run/1`, `hcparse_version`,
    `mode: "generate"`, `exit_code` (= the process exit code), `inputs`,
    `started_at`, `ended_at`, `duration_ms`, `generate` {exit_code (null on
    timeout), timed_out, config_bytes, writing_completed}, `copy` {bytes =
    sum of the allowlisted file sizes, deleted}; no `hc` key.

Retired modes (T107): `-Mode Parse` and `-Mode Test` exit 2, run nothing and
write nothing (no run.json).

Every invocation's console output (stdout and stderr) is ASCII-only
(FR-021). The script text never names `Program Files` / `LOCALAPPDATA`
(FR-002), never uses `Invoke-Expression` / `-Command` (FR-022), and declares
`$script:HCPARSE_VERSION` exactly once (FR-024).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

import pytest

from flextoolsmcp.server.sandbox import script

pytestmark = pytest.mark.windows_only

MARKER = ".flextoolsmcp-sandbox-work"
UTF8_BOM = b"\xef\xbb\xbf"

#: How long any one script invocation may take before the test gives up.
RUN_TIMEOUT = 90

PROGRESS_LINES = [
    "Loading FieldWorks project...",
    "Loading completed.",
    "Writing HC configuration file...",
    "Writing completed.",
]

GENERATE_FILES = {"hc-config.xml", "generate-config.log", "run.json"}


# ---------------------------------------------------------------------------
# Running the script
# ---------------------------------------------------------------------------


def _kill_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(pid)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def assert_ascii(label: str, data: bytes) -> None:
    bad = [b for b in data if b > 0x7F]
    assert not bad, "%s is not ASCII-only (FR-021): %r" % (label, data[:400])


def run_script(tmp_path: Path, mode: str, timeout: float = RUN_TIMEOUT, **params):
    """Run hcparse.ps1 with stdin closed; console output goes to files (so a
    surviving grandchild cannot hold a pipe open). Asserts ASCII console."""
    argv = script.build_argv(mode, **params)
    console = tmp_path / "console"
    console.mkdir(exist_ok=True)
    n = len(list(console.glob("*.out")))
    out_path = console / ("%02d.out" % n)
    err_path = console / ("%02d.err" % n)
    started = time.monotonic()
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(proc.pid)
            proc.wait()
            pytest.fail("hcparse.ps1 -Mode %s did not finish within %ss" % (mode, timeout))
    elapsed = time.monotonic() - started
    stdout = out_path.read_bytes()
    stderr = err_path.read_bytes()
    assert_ascii("console stdout", stdout)
    assert_ascii("console stderr", stderr)
    return SimpleNamespace(code=code, stdout=stdout, stderr=stderr, elapsed=elapsed)


def processes_with(token: str) -> List[int]:
    """PIDs of running processes whose command line contains ``token``."""
    env = dict(os.environ, HCPARSE_TEST_TOKEN=token)
    query = (
        "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and "
        "$_.CommandLine.Contains($env:HCPARSE_TEST_TOKEN) } | "
        "ForEach-Object { $_.ProcessId }"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", query],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        env=env,
        timeout=60,
    )
    pids = [int(x) for x in proc.stdout.decode("ascii", "replace").split() if x.isdigit()]
    return [pid for pid in pids if pid != os.getpid()]


def assert_tree_killed(token: str) -> None:
    deadline = time.monotonic() + 8
    alive = processes_with(token)
    while alive and time.monotonic() < deadline:
        time.sleep(0.5)
        alive = processes_with(token)
    for pid in alive:  # do not leak sleepers into later tests
        _kill_tree(pid)
    assert not alive, "the fake is still running after the kill: %r" % alive


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def read_json(path: Path) -> dict:
    raw = path.read_bytes()
    assert not raw.startswith(UTF8_BOM), "%s must be UTF-8 without a BOM" % path.name
    return json.loads(raw.decode("utf-8"))


def read_utf8_lines(path: Path) -> List[str]:
    raw = path.read_bytes()
    assert not raw.startswith(UTF8_BOM), "%s must not start with a UTF-8 BOM" % path.name
    text = raw.decode("utf-8")
    assert "\ufeff" not in text, "%s carries a U+FEFF" % path.name
    lines = text.splitlines()
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def snapshot(root: Path, exclude: Optional[List[Path]] = None) -> Dict[str, tuple]:
    exclude = [Path(p) for p in (exclude or [])]
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if any(path == ex or ex in path.parents for ex in exclude):
            continue
        stat = path.stat()
        result[path.relative_to(root).as_posix()] = (
            path.is_dir(),
            None if path.is_dir() else stat.st_size,
            None if path.is_dir() else stat.st_mtime_ns,
        )
    return result


def leftover(work_dir: Path) -> List[str]:
    """What is left in -WorkDir besides the MCP's marker."""
    if not work_dir.exists():
        return []
    return sorted(p.name for p in work_dir.iterdir() if p.name != MARKER)


def same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def assert_run_json_common(run: dict, mode: str, exit_code: int) -> None:
    assert run["schema"] == "flextoolsmcp.hcparse-run/1"
    assert run["hcparse_version"] == script.read_hcparse_version()
    assert run["mode"] == mode
    assert run["exit_code"] == exit_code
    for key in ("started_at", "ended_at"):
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z", run[key]), run[key]
    assert isinstance(run["duration_ms"], int) and run["duration_ms"] >= 0
    assert isinstance(run["inputs"], dict)


# ---------------------------------------------------------------------------
# Static checks over the script text
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def script_text() -> str:
    return script.script_path().read_text(encoding="utf-8-sig")


def test_hcparse_version_declared_exactly_once(script_text):
    assert len(script.VERSION_RE.findall(script_text)) == 1
    # No second (indented or reassigned) declaration either.
    assert len(re.findall(r"\$script:HCPARSE_VERSION\s*=", script_text)) == 1


def test_no_hardcoded_install_locations(script_text):
    # FR-002 / FR-001: every tool path comes in as a parameter.
    for literal in ("Program Files", "ProgramFiles", "LOCALAPPDATA", "HermitCrabTool"):
        assert literal.lower() not in script_text.lower(), literal


def test_no_string_evaluation(script_text):
    # FR-022: nothing is ever evaluated as a string of PowerShell.
    assert not re.search(r"Invoke-Expression", script_text, re.I)
    assert not re.search(r"(?<![\w-])iex(?![\w-])", script_text, re.I)
    assert not re.search(r"(?<![\w])-Command\b", script_text, re.I)
    assert not re.search(r"\[scriptblock\]::Create", script_text, re.I)


# ---------------------------------------------------------------------------
# Generate mode
# ---------------------------------------------------------------------------


@pytest.fixture
def gen_env(tmp_path, sandbox_root, fake_project, fake_generator):
    work = sandbox_root / "work" / "run-0001"
    work.mkdir(parents=True)
    (work / MARKER).write_text(
        json.dumps({"run_id": "run-0001", "pid": os.getpid(),
                    "created_at": "2026-09-24T00:00:00Z",
                    "source_fwdata": str(fake_project.fwdata)}),
        encoding="utf-8",
    )
    run_dir = sandbox_root / "config-cache" / "FakeProj" / "0123456789abcdef.partial"
    run_dir.mkdir(parents=True)
    params = dict(
        GenerateHCConfigPath=fake_generator.path,
        FwData=fake_project.fwdata,
        WorkDir=work,
        ConfigOut=run_dir / "hc-config.xml",
        RunDir=run_dir,
        GenerateTimeoutSeconds=60,
    )
    allowlisted = [fake_project.fwdata] + sorted(
        p for p in fake_project.writing_systems.rglob("*") if p.is_file()
    )
    env = SimpleNamespace(
        tmp=tmp_path, root=sandbox_root, project=fake_project, gen=fake_generator,
        work=work, run_dir=run_dir, config_out=run_dir / "hc-config.xml",
        params=params, copy_bytes=sum(p.stat().st_size for p in allowlisted),
    )

    def run(**overrides):
        merged = dict(params)
        merged.update(overrides)
        return run_script(tmp_path, "Generate", **merged)

    env.run = run
    return env


def test_generate_copies_the_allowlist_only(gen_env):
    live_before = snapshot(gen_env.project.dir)
    # A copied lock would turn the fake into "currently open" (exit 1).
    gen_env.gen.set(honor_lock=1)

    res = gen_env.run()

    assert res.code == 0, res.stderr
    listing = gen_env.gen.listing()
    assert listing is not None, "the generator never ran on the copy"
    assert same_path(listing["root"], gen_env.work)
    assert sorted(listing["files"]) == sorted([
        MARKER,
        "FakeProj/FakeProj.fwdata",
        "FakeProj/WritingSystemStore/en.ldml",
        "FakeProj/WritingSystemStore/seh.ldml",
    ])
    assert sorted(listing["dirs"]) == ["FakeProj", "FakeProj/WritingSystemStore"]
    for entry in listing["files"] + listing["dirs"]:
        assert not entry.endswith(".lock")
        for banned in (".hg", "LinkedFiles", "Backups"):
            assert banned not in entry.split("/")

    calls = gen_env.gen.invocations()
    assert len(calls) == 1
    assert same_path(calls[0]["argv"][0], gen_env.work / "FakeProj" / "FakeProj.fwdata")
    assert not same_path(calls[0]["argv"][0], gen_env.project.fwdata)

    # The live project was only read.
    assert snapshot(gen_env.project.dir) == live_before
    assert leftover(gen_env.work) == []


def test_generate_success_run_json_and_outputs(gen_env):
    res = gen_env.run()

    assert res.code == 0, res.stderr
    assert gen_env.config_out.is_file() and gen_env.config_out.stat().st_size > 0
    assert {p.name for p in gen_env.run_dir.iterdir()} == GENERATE_FILES
    run = read_json(gen_env.run_dir / "run.json")
    assert_run_json_common(run, "generate", 0)
    assert "hc" not in run and "items" not in run
    assert same_path(run["inputs"]["fwdata"], gen_env.project.fwdata)
    assert same_path(run["inputs"]["config_out"], gen_env.config_out)
    assert run["inputs"]["timeout_seconds"] == 60
    assert run["generate"] == {
        "exit_code": 0,
        "timed_out": False,
        "config_bytes": gen_env.config_out.stat().st_size,
        "writing_completed": True,
    }
    assert run["copy"] == {"bytes": gen_env.copy_bytes, "deleted": True}
    assert leftover(gen_env.work) == []


def test_generate_log_is_the_generators_output_verbatim(gen_env):
    errors = [
        'The form "\u014baa" contains an undefined phoneme at 1.',
        'The environment "/ _ #" is invalid. Reason: \u6f22\u5b57',
        "Some bare reason line.",
    ]
    gen_env.gen.set(load_error_lines=json.dumps(errors))

    res = gen_env.run()

    assert res.code == 0, res.stderr  # load errors are a warning, not a failure
    log = read_utf8_lines(gen_env.run_dir / "generate-config.log")
    assert log == [PROGRESS_LINES[0]] + errors + PROGRESS_LINES[1:]


@pytest.mark.parametrize(
    "mode, gen_exit, must_log, writing_completed",
    [
        ("locked", 1, ["Loading failed.",
                       "The FieldWorks project is currently open in another application."],
         False),
        ("migration", 1, ["The FieldWorks project was created with an older version of FLEx."],
         False),
        ("crash", None, ["Unhandled Exception: System.NotImplementedException: "
                         "The method or operation is not implemented."], False),
        ("help", 0, ["generatehcconfig <input-project> <output-config>"], False),
        ("empty_config", 0, ["Writing completed."], True),
    ],
)
def test_generate_failure_exits_4(gen_env, mode, gen_exit, must_log, writing_completed):
    gen_env.gen.set(mode=mode)

    res = gen_env.run()

    assert res.code == 4, (res.code, res.stderr)
    run = read_json(gen_env.run_dir / "run.json")
    assert_run_json_common(run, "generate", 4)
    gen = run["generate"]
    if gen_exit is None:
        assert gen["exit_code"] not in (0, None)
    else:
        assert gen["exit_code"] == gen_exit
    assert gen["timed_out"] is False
    assert gen["writing_completed"] is writing_completed
    if mode == "empty_config":
        assert gen["config_bytes"] == 0
    log = read_utf8_lines(gen_env.run_dir / "generate-config.log")
    for line in must_log:
        assert line in log, (line, log)
    assert run["copy"]["deleted"] is True
    assert leftover(gen_env.work) == []


def test_generate_timeout_exits_6_and_kills_the_generator(gen_env):
    gen_env.gen.set(sleep_seconds=60)

    res = gen_env.run(GenerateTimeoutSeconds=2)

    assert res.code == 6, (res.code, res.stderr)
    assert res.elapsed < 45
    assert_tree_killed(str(gen_env.work))
    run = read_json(gen_env.run_dir / "run.json")
    assert_run_json_common(run, "generate", 6)
    assert run["generate"]["timed_out"] is True
    assert run["generate"]["exit_code"] is None
    assert run["generate"]["writing_completed"] is False
    assert run["inputs"]["timeout_seconds"] == 2
    assert run["copy"]["deleted"] is True
    assert leftover(gen_env.work) == []


@pytest.mark.parametrize("via_dotdot", [False, True])
def test_config_out_under_sandboxes_exits_3_and_writes_nothing(gen_env, via_dotdot):
    sandbox = gen_env.root / "sandboxes" / "FakeProj" / "mysb"
    sandbox.mkdir(parents=True)
    if via_dotdot:
        config_out = (gen_env.root / "config-cache" / "FakeProj" / ".." / ".."
                      / "sandboxes" / "FakeProj" / "mysb" / "hc-config.xml")
    else:
        config_out = sandbox / "hc-config.xml"
    before = snapshot(gen_env.root)

    res = gen_env.run(ConfigOut=config_out)

    assert res.code == 3, (res.code, res.stderr)
    assert snapshot(gen_env.root) == before  # no copy, no log, no run.json, no config
    assert gen_env.gen.invocations() == []


@pytest.mark.parametrize("override", [
    {"ConfigOut": None},
    {"WorkDir": None},
    {"GenerateHCConfigPath": None},
    {"FwData": "missing.fwdata"},
    {"GenerateTimeoutSeconds": "0"},
])
def test_generate_bad_parameter_exits_2(gen_env, override):
    if override.get("FwData"):
        override = {"FwData": gen_env.tmp / "missing.fwdata"}
    before = snapshot(gen_env.root)

    res = gen_env.run(**override)

    assert res.code == 2, (res.code, res.stderr)
    assert snapshot(gen_env.root) == before
    assert gen_env.gen.invocations() == []


# ---------------------------------------------------------------------------
# Retired modes (T107)
# ---------------------------------------------------------------------------


def test_build_argv_refuses_a_retired_mode():
    assert script.MODES == ("Generate",)
    for mode in ("Parse", "Test"):
        with pytest.raises(ValueError):
            script.build_argv(mode, RunDir="x")


@pytest.mark.parametrize("mode", ["Parse", "Test", "parse"])
def test_the_script_refuses_a_retired_mode_with_exit_2(tmp_path, mode):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    argv = [*script.ARGV_PREFIX, str(script.script_path()), "-Mode", mode,
            "-RunDir", str(run_dir)]
    proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=RUN_TIMEOUT)
    assert proc.returncode == 2, (proc.returncode, proc.stderr)
    assert_ascii("console stderr", proc.stderr)
    assert b"retired" in proc.stderr
    assert list(run_dir.iterdir()) == [], "a refused mode writes nothing"


def test_the_script_keeps_no_parse_or_test_machinery(script_text):
    for gone in ("$HcPath", "$WordFile", "$Words", "$AssertionFile", "$TimeoutSeconds",
                 "hc-script.txt", "dispatch.json", "hc-stdout.txt", "Invoke-HcRun"):
        assert gone not in script_text, gone
