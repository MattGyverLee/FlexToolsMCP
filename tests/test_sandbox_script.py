#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 T034 + T063: the invariants of the packaged `hcparse.ps1`
(contracts/hcparse.md, section 7), for `-Mode Generate`, `-Mode Parse` and
`-Mode Test`.

These tests drive the REAL script through
`powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`
(`sandbox.script.build_argv`), with stdin closed, against the fake
GenerateHCConfig and the fake `hc` (tests/fakes/).

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

Parse mode (`-HcPath -Config (-WordFile | -Words) -TimeoutSeconds -RunDir`)
  * `-WordFile` is read as UTF-8, one item per line (a blank line is an
    item with reason `empty`); `-Words` is split on `[,\\s]+`. Order is kept,
    nothing is de-duplicated.
  * `<RunDir>/dispatch.json` = {"schema": "flextoolsmcp.hc-dispatch/1",
    "mode": "parse", "items": [...]}, written before hc starts. Each item is
    exactly {index, word, sent, line, reason, flags}: `index` is the 0-based
    input position; a word without `"` is sent as `parse "<w>"`; a word with
    `"` and no `'` as `parse '<w>'`; both quotes -> sent false,
    `both_quote_characters`; empty -> `empty`; tab / CR / LF ->
    `control_character`; unsent items have `line: null`; sent items have
    `reason: null`; `flags` is always a list, and a word starting with `-`
    is sent (plain `parse "-w"`) with `flags: ["leading_dash_unverified"]`.
  * `<RunDir>/hc-script.txt` is UTF-8 with NO BOM: the `line` of every sent
    item, in order, then `stats -p`; never `tracing on`.
  * hc is invoked with exactly `-i <Config> -s <RunDir>/hc-script.txt`
    (never `-o`, never `-c`).
  * `<RunDir>/hc-stdout.txt` is hc's UTF-16LE stdout decoded, written as
    UTF-8 without a BOM (and without U+FEFF), line by line; `hc-stderr.txt`
    is UTF-8. On timeout every line hc emitted before the kill is kept.
  * RunDir ends holding exactly dispatch.json, hc-script.txt, hc-stdout.txt,
    hc-stderr.txt and run.json; nothing is written outside it.
  * Exit 0 on completion, 5 when hc fails to start (exit -1, `Load Error:`),
    6 on timeout (hc's process tree is killed).
  * run.json: as above with `mode: "parse"`, `inputs` {config, word_count =
    len(items), timeout_seconds}, `hc` {exit_code (null on timeout),
    timed_out, killed, in_flight_index (the dispatch `index` of the word in
    flight at the kill, else null), stdout_bom (bool)}, `items` (== the
    dispatch items); no `generate` key.

Test mode (`-HcPath -Config -AssertionFile -TimeoutSeconds -RunDir`; T063)
  * `-AssertionFile` is the corpus JSON (data-model section 5):
    {"schema": "flextoolsmcp.hc-corpus/1", "assertions": [{"word",
    "expected": [[{"form", "gloss"}, ...], ...]}, ...]}. Unreadable JSON, an
    unknown schema, or a structurally malformed assertion exits 2 before
    anything is written.
  * dispatch.json has `mode: "test"` and one item per assertion, with the
    same keys as Parse mode ({index, word, sent, line, reason, flags}). The
    word is checked and quoted exactly as in Parse mode.
  * A sent line is `test -p <f:g|f:g> [-p ...] [--] <quoted word>`: one
    `-p` per expected parse, in order; morphs joined by `|`; every morph is
    `form:gloss` (an empty gloss is written `?`, F-7; an empty form is
    allowed); `--` only before a word starting with `-` (also flagged
    `leading_dash_unverified`). `expected: []` is `test <quoted word>` with
    no `-p`: hc's TestCommand then passes only when the word has no parse,
    and otherwise lists the parses under `Actual parses:`.
  * Not expressible (sent false, never emitted): a form or gloss with `|`,
    `:` or a backslash -> `delimiter_in_expectation`; with `'`, `"` or
    whitespace -> `quote_or_space_in_expectation`; an expected parse with
    zero morphs -> `empty_expected_parse`. The word's own faults (`empty`,
    `control_character`, `both_quote_characters`) are checked first.
  * hc-script.txt (UTF-8, no BOM) never contains a backslash (one before a
    delimiter makes hc's Split loop forever) and never a morph without `:`
    (F-5's leak); it ends with `stats -t`.
  * run.json: `mode: "test"`, `inputs.word_count` = number of assertions,
    `hc` as in Parse mode with `in_flight_index` taken from `Testing "..."`
    headers, `items` == the dispatch items.

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

GRAMMAR = {
    "language": "Fake Lang",
    "words": {
        "membaca": [[["mem", "ACT"], ["baca", "read"]]],
        "xyz": [],
        "q#": {"invalid_segment": 2},
        "don't": [[["don't", "NEG"]]],
        "-an": [[["-an", "NMLZ"]]],
    },
    "default": [],
}

NON_LATIN = [
    "\u014b\u0300omb\u00e9",  # Latin + combining grave
    "\u0928\u092e\u0938\u094d\u0924\u0947",  # Devanagari
    "\u0633\u0644\u0627\u0645",  # Arabic
    "\u6f22\u5b57",  # CJK
    "\U00010400a",  # astral plane (2 UTF-16 code units)
]

PARSE_FILES = {"dispatch.json", "hc-script.txt", "hc-stdout.txt", "hc-stderr.txt", "run.json"}
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
# Parse mode
# ---------------------------------------------------------------------------


@pytest.fixture
def parse_env(tmp_path, sandbox_root, fake_hc):
    config = fake_hc.write_config(
        sandbox_root / "config-cache" / "FakeProj" / "0123456789abcdef" / "hc-config.xml",
        GRAMMAR,
    )
    run_dir = tmp_path / "records" / "run-0001" / "sandbox"
    run_dir.mkdir(parents=True)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    env = SimpleNamespace(tmp=tmp_path, root=sandbox_root, hc=fake_hc, config=config,
                          run_dir=run_dir)

    def word_file(words: List[str]) -> Path:
        path = inputs / "words.txt"
        path.write_bytes(("\n".join(words) + "\n").encode("utf-8"))
        return path

    def run(words: Optional[List[str]] = None, **overrides):
        params = dict(HcPath=fake_hc.path, Config=config, TimeoutSeconds=30, RunDir=run_dir)
        if words is not None:
            params["WordFile"] = word_file(words)
        params.update(overrides)
        return run_script(tmp_path, "Parse", **params)

    env.word_file = word_file
    env.run = run
    return env


def _item(index, word, line=None, reason=None, flags=()):
    return {
        "index": index,
        "word": word,
        "sent": line is not None,
        "line": line,
        "reason": reason,
        "flags": list(flags),
    }


QUOTING_WORDS = [
    "membaca",
    "don't",
    'say"hi',
    "a\"b'c",
    "",
    "tab\there",
    "-an",
    "membaca",
    "two words",
    NON_LATIN[0],
]

QUOTING_ITEMS = [
    _item(0, "membaca", 'parse "membaca"'),
    _item(1, "don't", 'parse "don\'t"'),
    _item(2, 'say"hi', "parse 'say\"hi'"),
    _item(3, "a\"b'c", reason="both_quote_characters"),
    _item(4, "", reason="empty"),
    _item(5, "tab\there", reason="control_character"),
    _item(6, "-an", 'parse "-an"', flags=["leading_dash_unverified"]),
    _item(7, "membaca", 'parse "membaca"'),  # never de-duplicated here
    _item(8, "two words", 'parse "two words"'),
    _item(9, NON_LATIN[0], 'parse "%s"' % NON_LATIN[0]),
]


def test_dispatch_items_quoting_and_order(parse_env):
    res = parse_env.run(QUOTING_WORDS)

    assert res.code == 0, (res.code, res.stderr)
    dispatch = read_json(parse_env.run_dir / "dispatch.json")
    assert dispatch["schema"] == "flextoolsmcp.hc-dispatch/1"
    assert dispatch["mode"] == "parse"
    assert dispatch["items"] == QUOTING_ITEMS


def test_hc_script_is_utf8_without_bom_and_ends_with_stats(parse_env):
    parse_env.run(QUOTING_WORDS)

    raw = (parse_env.run_dir / "hc-script.txt").read_bytes()
    assert not raw.startswith(UTF8_BOM)
    lines = read_utf8_lines(parse_env.run_dir / "hc-script.txt")
    sent = [item["line"] for item in QUOTING_ITEMS if item["sent"]]
    assert lines == sent + ["stats -p"]
    assert not any("tracing" in line for line in lines)
    assert NON_LATIN[0].encode("utf-8") in raw


def test_hc_is_invoked_with_only_i_and_s(parse_env):
    parse_env.run(["membaca", "xyz"])

    calls = parse_env.hc.invocations()
    assert len(calls) == 1
    argv = calls[0]["argv"]
    assert len(argv) == 4 and argv[0] == "-i" and argv[2] == "-s", argv
    assert same_path(argv[1], parse_env.config)
    assert same_path(argv[3], parse_env.run_dir / "hc-script.txt")
    for banned in ("-o", "-c", "--output-file", "--continue", "/o", "/c"):
        assert not any(a == banned or a.startswith(banned + "=") for a in argv), banned
    # hc read the script the tests see.
    assert calls[0]["script"].splitlines() == read_utf8_lines(parse_env.run_dir / "hc-script.txt")


@pytest.mark.parametrize("words_arg, expected", [
    ("a,b c", ["a", "b", "c"]),
    ("alpha, beta,,gamma  delta", ["alpha", "beta", "gamma", "delta"]),
])
def test_words_parameter_split_on_commas_and_whitespace(parse_env, words_arg, expected):
    res = parse_env.run(Words=words_arg)

    assert res.code == 0, (res.code, res.stderr)
    items = read_json(parse_env.run_dir / "dispatch.json")["items"]
    assert [i["word"] for i in items] == expected
    assert [i["index"] for i in items] == list(range(len(expected)))
    assert all(i["sent"] for i in items)


def test_parse_success_run_json_and_files(parse_env):
    before = snapshot(parse_env.root)

    res = parse_env.run(["membaca", "xyz", "q#", "a\"b'c"])

    assert res.code == 0, (res.code, res.stderr)
    assert {p.name for p in parse_env.run_dir.iterdir()} == PARSE_FILES
    assert snapshot(parse_env.root) == before  # nothing written outside RunDir
    dispatch = read_json(parse_env.run_dir / "dispatch.json")
    run = read_json(parse_env.run_dir / "run.json")
    assert_run_json_common(run, "parse", 0)
    assert "generate" not in run
    assert same_path(run["inputs"]["config"], parse_env.config)
    assert run["inputs"]["word_count"] == 4
    assert run["inputs"]["timeout_seconds"] == 30
    assert run["items"] == dispatch["items"]
    hc = run["hc"]
    assert hc["exit_code"] == 0
    assert hc["timed_out"] is False
    assert hc["killed"] is False
    assert hc["in_flight_index"] is None
    assert isinstance(hc["stdout_bom"], bool)

    out = read_utf8_lines(parse_env.run_dir / "hc-stdout.txt")
    assert out[0] == 'Reading configuration file "hc-config.xml"... done.'
    assert "Fake Lang loaded." in out
    assert 'Parsing "membaca"' in out
    assert "Morphs: mem baca" in out
    assert "Gloss:  ACT read" in out
    assert "The word contains an invalid segment at position 2." in out
    assert "# of parses: 3, successful: 1, failed: 1, error: 1" in out
    read_utf8_lines(parse_env.run_dir / "hc-stderr.txt")  # UTF-8, no BOM


@pytest.mark.parametrize("bom", [None, "1"])
def test_non_latin_round_trip_through_utf16(parse_env, bom):
    parse_env.hc.set(mode="echo", bom=bom)

    res = parse_env.run(NON_LATIN)

    assert res.code == 0, (res.code, res.stderr)
    script_lines = read_utf8_lines(parse_env.run_dir / "hc-script.txt")
    assert read_utf8_lines(parse_env.run_dir / "hc-stdout.txt") == script_lines
    raw = (parse_env.run_dir / "hc-stdout.txt").read_bytes()
    for word in NON_LATIN:
        assert ('parse "%s"' % word).encode("utf-8") in raw
    run = read_json(parse_env.run_dir / "run.json")
    assert isinstance(run["hc"]["stdout_bom"], bool)
    assert [i["word"] for i in run["items"]] == NON_LATIN


def test_console_output_is_ascii_with_non_latin_data(parse_env):
    # run_script asserts ASCII on every invocation; this one carries the
    # most non-ASCII data, including in paths the script might echo.
    res = parse_env.run(NON_LATIN + ["a\"b'c", "tab\there"])
    assert res.code == 0, (res.code, res.stderr)
    assert res.stdout  # it does say something (progress prose)


def test_hc_start_failure_exits_5(parse_env):
    parse_env.hc.set(mode="load_error", load_error="The feature 'bogus' is not defined.")
    before = snapshot(parse_env.root)

    res = parse_env.run(["membaca", "xyz"])

    assert res.code == 5, (res.code, res.stderr)
    assert snapshot(parse_env.root) == before
    dispatch = read_json(parse_env.run_dir / "dispatch.json")  # written before hc started
    assert [i["word"] for i in dispatch["items"]] == ["membaca", "xyz"]
    run = read_json(parse_env.run_dir / "run.json")
    assert_run_json_common(run, "parse", 5)
    assert run["hc"]["exit_code"] == -1
    assert run["hc"]["timed_out"] is False
    assert run["hc"]["in_flight_index"] is None
    out = read_utf8_lines(parse_env.run_dir / "hc-stdout.txt")
    assert "Load Error: The feature 'bogus' is not defined." in out


def test_hc_timeout_keeps_pre_kill_lines_and_names_in_flight_word(parse_env):
    # Item 0 is never sent, so the in-flight dispatch index (3) differs from
    # hc's own word counter (2).
    words = ["a\"b'c", "w0", "w1", "w2", "w3"]
    parse_env.hc.set(sleep_on_word=2, sleep_seconds=60)
    before = snapshot(parse_env.root)

    res = parse_env.run(words, TimeoutSeconds=3)

    assert res.code == 6, (res.code, res.stderr)
    assert res.elapsed < 45
    assert_tree_killed(str(parse_env.config))
    assert snapshot(parse_env.root) == before

    run = read_json(parse_env.run_dir / "run.json")
    assert_run_json_common(run, "parse", 6)
    hc = run["hc"]
    assert hc["timed_out"] is True
    assert hc["killed"] is True
    assert hc["exit_code"] is None
    assert hc["in_flight_index"] == 3
    assert run["inputs"]["timeout_seconds"] == 3
    assert [i["word"] for i in run["items"]] == words

    out = read_utf8_lines(parse_env.run_dir / "hc-stdout.txt")
    normalised = [re.sub(r"^Parse time: \d+ms$", "Parse time: <n>ms", line) for line in out]

    def block(word):
        return ['Parsing "%s"' % word, "No valid parses.", "Parse time: <n>ms", ""]

    assert normalised == [
        'Reading configuration file "hc-config.xml"... done.',
        "Compiling rules... done.",
        "Fake Lang loaded.",
        "",
    ] + block("w0") + block("w1") + ['Parsing "w2"']


@pytest.mark.parametrize("override", [
    {"TimeoutSeconds": None},
    {"TimeoutSeconds": "abc"},
    {"HcPath": None},
    {"Config": "missing"},
    {"WordFile": "missing"},
])
def test_parse_bad_parameter_exits_2(parse_env, override):
    if override.get("Config") == "missing":
        override = {"Config": parse_env.tmp / "nope.xml"}
    if override.get("WordFile") == "missing":
        override = {"WordFile": parse_env.tmp / "nope.txt"}
    params = {"WordFile": parse_env.word_file(["membaca"])}
    params.update(override)

    res = parse_env.run(**params)

    assert res.code == 2, (res.code, res.stderr)
    assert list(parse_env.run_dir.iterdir()) == []
    assert parse_env.hc.invocations() == []


# ---------------------------------------------------------------------------
# Test mode (T063)
# ---------------------------------------------------------------------------


def _m(form, gloss):
    return {"form": form, "gloss": gloss}


ROOT_FORM = "ŋomb"

TEST_GRAMMAR = {
    "language": "Fake Lang",
    "words": {
        "membaca": [[["mem", "ACT"], ["baca", "read"]]],
        "baca": [[["baca", "read"]]],
        "xyz": [],
        "kata": [[["kata", ""]]],  # hc prints the empty gloss as `?` (F-7)
        "x": [[["", "ZERO"], ["x", "X"]]],
        "-an": [[["-an", "NMLZ"]]],
        ROOT_FORM + "é": [[[ROOT_FORM, "ROOT"], ["é", "FV"]]],
    },
    "default": [],
}

#: (assertion, expected dispatch item), in corpus order.
TEST_CASES = [
    ({"word": "membaca", "expected": [[_m("mem", "ACT"), _m("baca", "read")]]},
     _item(0, "membaca", 'test -p mem:ACT|baca:read "membaca"')),
    ({"word": "baca", "expected": [[_m("baca", "read")], [_m("baca", "book")]]},
     _item(1, "baca", 'test -p baca:read -p baca:book "baca"')),
    ({"word": "xyz", "expected": []},
     _item(2, "xyz", 'test "xyz"')),
    ({"word": "don't", "expected": []},
     _item(3, "don't", 'test "don\'t"')),
    ({"word": 'say"hi', "expected": []},
     _item(4, 'say"hi', "test 'say\"hi'")),
    ({"word": "kata", "expected": [[_m("kata", "")]]},
     _item(5, "kata", 'test -p kata:? "kata"')),
    ({"word": "x", "expected": [[_m("", "ZERO"), _m("x", "X")]]},
     _item(6, "x", 'test -p :ZERO|x:X "x"')),
    ({"word": "-an", "expected": [[_m("-an", "NMLZ")]]},
     _item(7, "-an", 'test -p -an:NMLZ -- "-an"', flags=["leading_dash_unverified"])),
    ({"word": ROOT_FORM + "é",
      "expected": [[_m(ROOT_FORM, "ROOT"), _m("é", "FV")]]},
     _item(8, ROOT_FORM + "é",
           'test -p %s:ROOT|é:FV "%sé"' % (ROOT_FORM, ROOT_FORM))),
    # Not expressible: never sent.
    ({"word": "p1", "expected": [[_m("a|b", "G")]]},
     _item(9, "p1", reason="delimiter_in_expectation")),
    ({"word": "p2", "expected": [[_m("ab", "G:H")]]},
     _item(10, "p2", reason="delimiter_in_expectation")),
    ({"word": "p3", "expected": [[_m("a\\b", "G")]]},
     _item(11, "p3", reason="delimiter_in_expectation")),
    ({"word": "p4", "expected": [[_m("ab", "it's")]]},
     _item(12, "p4", reason="quote_or_space_in_expectation")),
    ({"word": "p5", "expected": [[_m('a"b', "G")]]},
     _item(13, "p5", reason="quote_or_space_in_expectation")),
    ({"word": "p6", "expected": [[_m("ab", "two words")]]},
     _item(14, "p6", reason="quote_or_space_in_expectation")),
    ({"word": "p7", "expected": [[_m("ab", "G\t")]]},
     _item(15, "p7", reason="quote_or_space_in_expectation")),
    ({"word": "p8", "expected": [[_m("ab", "G")], []]},
     _item(16, "p8", reason="empty_expected_parse")),
    ({"word": "a\"b'c", "expected": []},
     _item(17, "a\"b'c", reason="both_quote_characters")),
    ({"word": "", "expected": []},
     _item(18, "", reason="empty")),
    ({"word": "t\tab", "expected": []},
     _item(19, "t\tab", reason="control_character")),
]


def corpus(assertions, schema="flextoolsmcp.hc-corpus/1"):
    return {"schema": schema, "name": "baseline", "project": "FakeProj",
            "created_at": "2026-09-24T00:00:00Z", "assertions": assertions}


@pytest.fixture
def test_env(tmp_path, sandbox_root, fake_hc):
    config = fake_hc.write_config(
        sandbox_root / "config-cache" / "FakeProj" / "0123456789abcdef" / "hc-config.xml",
        TEST_GRAMMAR,
    )
    run_dir = tmp_path / "records" / "run-0002" / "sandbox"
    run_dir.mkdir(parents=True)
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    env = SimpleNamespace(tmp=tmp_path, root=sandbox_root, hc=fake_hc, config=config,
                          run_dir=run_dir)

    def assertion_file(doc) -> Path:
        path = inputs / "corpus.json"
        if isinstance(doc, str):
            path.write_bytes(doc.encode("utf-8"))
        else:
            path.write_bytes(json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8"))
        return path

    def run(doc=None, **overrides):
        params = dict(HcPath=fake_hc.path, Config=config, TimeoutSeconds=30, RunDir=run_dir)
        if doc is not None:
            params["AssertionFile"] = assertion_file(doc)
        params.update(overrides)
        return run_script(tmp_path, "Test", **params)

    env.run = run
    return env


def test_test_mode_dispatch_items(test_env):
    res = test_env.run(corpus([a for a, _ in TEST_CASES]))

    assert res.code == 0, (res.code, res.stderr)
    dispatch = read_json(test_env.run_dir / "dispatch.json")
    assert dispatch["schema"] == "flextoolsmcp.hc-dispatch/1"
    assert dispatch["mode"] == "test"
    assert dispatch["items"] == [item for _, item in TEST_CASES]


def test_test_mode_script_is_safe_and_ends_with_stats_t(test_env):
    test_env.run(corpus([a for a, _ in TEST_CASES]))

    raw = (test_env.run_dir / "hc-script.txt").read_bytes()
    assert not raw.startswith(UTF8_BOM)
    assert b"\\" not in raw  # a backslash before a delimiter hangs hc's Split
    lines = read_utf8_lines(test_env.run_dir / "hc-script.txt")
    assert lines == [item["line"] for _, item in TEST_CASES if item["sent"]] + ["stats -t"]
    assert not any("tracing" in line for line in lines)
    for line in lines[:-1]:
        tokens = line.split(" ")
        for k, token in enumerate(tokens):
            if token == "-p":
                for morph in tokens[k + 1].split("|"):
                    assert ":" in morph, (line, morph)  # F-5: never a morph without `:`


def test_test_mode_runs_hc_and_writes_run_json(test_env):
    before = snapshot(test_env.root)

    res = test_env.run(corpus([a for a, _ in TEST_CASES]))

    assert res.code == 0, (res.code, res.stderr)
    assert {p.name for p in test_env.run_dir.iterdir()} == PARSE_FILES
    assert snapshot(test_env.root) == before
    calls = test_env.hc.invocations()
    assert len(calls) == 1
    argv = calls[0]["argv"]
    assert len(argv) == 4 and argv[0] == "-i" and argv[2] == "-s", argv
    assert same_path(argv[1], test_env.config)
    assert same_path(argv[3], test_env.run_dir / "hc-script.txt")

    run = read_json(test_env.run_dir / "run.json")
    assert_run_json_common(run, "test", 0)
    assert "generate" not in run
    assert run["inputs"]["word_count"] == len(TEST_CASES)
    assert run["inputs"]["timeout_seconds"] == 30
    assert run["items"] == read_json(test_env.run_dir / "dispatch.json")["items"]
    assert run["hc"]["exit_code"] == 0
    assert run["hc"]["timed_out"] is False
    assert run["hc"]["in_flight_index"] is None

    out = read_utf8_lines(test_env.run_dir / "hc-stdout.txt")
    assert 'Testing "membaca"' in out
    assert 'Testing "-an"' in out
    # 9 sent; only `baca` fails (the grammar has no `book` parse). An F-5
    # leak of a bad -p into a later test would fail more of them.
    assert "# of tests: 9, passed: 8, failed: 1, error: 0" in out


def test_test_mode_timeout_names_the_in_flight_assertion(test_env):
    # Item 0 is unsent, so hc's word 1 is dispatch index 2.
    assertions = [
        {"word": "p1", "expected": [[_m("a|b", "G")]]},
        {"word": "membaca", "expected": [[_m("mem", "ACT"), _m("baca", "read")]]},
        {"word": "xyz", "expected": []},
        {"word": "kata", "expected": [[_m("kata", "")]]},
    ]
    test_env.hc.set(sleep_on_word=1, sleep_seconds=60)

    res = test_env.run(corpus(assertions), TimeoutSeconds=3)

    assert res.code == 6, (res.code, res.stderr)
    assert_tree_killed(str(test_env.config))
    run = read_json(test_env.run_dir / "run.json")
    assert_run_json_common(run, "test", 6)
    assert run["hc"]["timed_out"] is True
    assert run["hc"]["killed"] is True
    assert run["hc"]["in_flight_index"] == 2
    out = read_utf8_lines(test_env.run_dir / "hc-stdout.txt")
    assert out[-1] == 'Testing "xyz"'
    assert "Test passed." in out


def test_test_mode_hc_start_failure_exits_5(test_env):
    test_env.hc.set(mode="load_error")

    res = test_env.run(corpus([{"word": "xyz", "expected": []}]))

    assert res.code == 5, (res.code, res.stderr)
    run = read_json(test_env.run_dir / "run.json")
    assert_run_json_common(run, "test", 5)
    assert run["hc"]["exit_code"] == -1


@pytest.mark.parametrize("doc", [
    "{not json",
    corpus([], schema="flextoolsmcp.hc-corpus/99"),
    {"schema": "flextoolsmcp.hc-corpus/1"},  # no assertions
    corpus([{"expected": []}]),  # no word
    corpus([{"word": "a", "expected": "x"}]),  # expected not a list
    corpus([{"word": "a", "expected": [[{"form": "a"}]]}]),  # morph without gloss
])
def test_test_mode_malformed_corpus_exits_2(test_env, doc):
    res = test_env.run(doc)

    assert res.code == 2, (res.code, res.stderr)
    assert list(test_env.run_dir.iterdir()) == []
    assert test_env.hc.invocations() == []
