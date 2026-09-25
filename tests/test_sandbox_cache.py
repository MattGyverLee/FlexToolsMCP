#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the sandbox spine's config cache (parser-check CP5, T037):
`src/flextoolsmcp/server/sandbox/cache.py` (T049). Research R-05, R-12;
data-model section 3; contracts/tools.md section 4; FR-009, FR-010,
FR-024..FR-026, SC-006.

THE API THESE TESTS SPECIFY (`flextoolsmcp.server.sandbox.cache`)
-----------------------------------------------------------------
Constants
  SCHEMA = "flextoolsmcp.hc-cache/1"
  CONFIG_NAME = "hc-config.xml"; LOG_NAME = "generate-config.log";
  KEY_JSON = "key.json"; PARTIAL_SUFFIX = ".partial"
  PROGRESS_LINES   the four GenerateHCConfig progress lines (R-05), in order
  LOAD_ERROR_KINDS ("undefined_phoneme", "invalid_affix_process",
                    "phoneme_no_grapheme", "duplicate_grapheme",
                    "invalid_environment", "invalid_reduplication_form",
                    "invalid_rewrite_rule", "other")
  STDERR_TAIL_LINES = 20; STDERR_TAIL_MAX_BYTES = 4096
  DEFAULT_GENERATE_TIMEOUT_SECONDS = 600

Pure helpers
  key_inputs(fwdata_path, generator_path, *, hcparse_version=None) -> dict
      {"fwdata_path" (abspath str), "fwdata_size", "fwdata_mtime_ns",
       "generate_hc_config_path", "generate_hc_config_size",
       "generate_hc_config_mtime_ns", "hcparse_version"}; the version
      defaults to `script.read_hcparse_version()`, looked up on the script
      MODULE at call time.
  compute_key(inputs) -> str      == parse.fingerprint.fingerprint_key(inputs)
  classify_load_error(line) -> str  one of LOAD_ERROR_KINDS
  extract_load_errors(output) -> [{"kind", "line"}]  every non-blank line not
      in PROGRESS_LINES, verbatim, in order (an exclusion list, R-05)
  stderr_tail(output) -> str      last 20 lines, non-ASCII escaped with
      Python's `backslashreplace`, then capped at 4096 bytes keeping the END
  judge_generation(exit_code, config_path, output) -> bool
      exit_code == 0 AND config exists and is non-empty AND a line equal to
      "Writing completed." is in output

Entries and errors
  CacheEntry: .project, .key, .path (config-cache/<project>/<key>/),
      .config_path, .log_path, .meta (key.json dict), .built (True only when
      THIS call ran the generator), .load_errors, .load_error_count
  ParserConfigFailed(Exception): .detail is a
      response_models.ParserConfigFailedDetail (exit_code, stderr_tail,
      log_path, run_id). exit_code is None on a generation timeout or when
      the script left no run.json.

Operations
  lock_for(project, key) -> asyncio.Lock   one per (project, key)
  reset_state() -> None                    drop locks (and later refcounts)
  lookup(project, key, *, touch=True) -> Optional[CacheEntry]
      usable = key.json valid (schema, cache_key == compute_key(inputs)),
      invalidated_at is None, hc-config.xml non-empty. `touch` rewrites
      last_used_at. `.partial` dirs are never entries.
  async build_entry(project, inputs, *, work_dir, run_id=None, log_dir=None,
                    active_parser="HC", versions=None,
                    timeout_seconds=DEFAULT_GENERATE_TIMEOUT_SECONDS,
                    run_script=None) -> CacheEntry
      The ONLY caller that passes ConfigOut to `script.build_argv`:
        build_argv("Generate", GenerateHCConfigPath=, FwData=, WorkDir=,
                   ConfigOut=<key>.partial/hc-config.xml,
                   RunDir=<key>.partial, GenerateTimeoutSeconds=)
      `run_script(argv) -> Awaitable[Optional[int]]` (the script's exit
      code; default `run_script_subprocess`, a real async subprocess with
      stdin closed). The generator's exit code is read from the RunDir's
      run.json `generate.exit_code` (None if missing or timed out); success
      is judged by `judge_generation` over the RunDir's generate-config.log
      and hc-config.xml. Success: key.json written (data-model section 3),
      `.partial` renamed onto `<key>/` (replacing an invalidated entry).
      Failure: `.partial` removed, ParserConfigFailed raised. Either way
      the whole log is copied to `<log_dir>/generate-config.log` when
      log_dir is given (the run's `sandbox/`), and `log_path` names that
      copy; without log_dir the failed log is kept as the FILE
      `config-cache/<project>/<key>.generate-config.log`.
  async ensure_entry(project, fwdata_path, generator_path, *, work_dir,
                     run_id=None, log_dir=None, active_parser="HC",
                     versions=None, timeout_seconds=..., run_script=None)
                     -> CacheEntry
      key_inputs -> compute_key -> under lock_for: lookup, else build_entry.
  invalidate(project) -> int   sets invalidated_at on every entry of the
      project (count returned); never creates directories.

US6 (T082 / T085): prune and the in-process refcount
  acquire(entry) -> int / release(entry) -> int   the refcount per
      (project, key) after the change; release never goes below 0.
  in_use(entry)   context manager: acquire, then release in `finally`.
  refcount(project, key) -> int
  reset_state() also clears every refcount.
  prune(project, keep=3) -> List[str]   the deleted keys. Only `<16 hex>`
      entry dirs are candidates (never `.partial`, failed-log files or
      foreign names). Unusable ones (invalidated, bad key.json, empty
      config) are deleted at refcount 0. Usable ones are ranked by
      last_used_at, newest first; those past rank `keep` are deleted at
      refcount 0. An in-use entry is never deleted and takes one of the
      `keep` slots first (the total stays at `keep` when runs allow). Every delete goes through the config-cache/ guard; an absent
      project is [] and creates nothing.

Most tests stub the script with `EmulatedScript`, a Python stand-in for
`hcparse.ps1 -Mode Generate` that runs the fake generator directly (portable).
The `windows_only` tests drive the real script against the fake generator;
they pass once the script's Generate mode lands (T043).
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from flextoolsmcp.server.parse.fingerprint import fingerprint_key
from flextoolsmcp.server.sandbox import paths, script

FAKES_DIR = Path(__file__).parent / "fakes"
GEN_FAKE = FAKES_DIR / "generate_fake.py"
SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "flextoolsmcp"

PROGRESS = (
    "Loading FieldWorks project...",
    "Loading completed.",
    "Writing HC configuration file...",
    "Writing completed.",
)

# ConsoleLogger.cs templates, as the fake emits them (generate_fake.py), with
# the kind each must be tagged as.
TEMPLATE_KINDS = [
    ('The form "fake1" contains an undefined phoneme at 1.', "undefined_phoneme"),
    ('The affix process "proc2" is invalid.', "invalid_affix_process"),
    ('The phoneme "ph3" does not contain any valid graphemes.', "phoneme_no_grapheme"),
    ('The phoneme "dup4" has the same grapheme as another phoneme.', "duplicate_grapheme"),
    ('The environment "/ _ #5" is invalid. Reason: fake reason 5', "invalid_environment"),
    ('The reduplication form "[C6]" is invalid. Reason: fake reason 6',
     "invalid_reduplication_form"),
    ('The rewrite rule "rule7" is invalid. Reason: fake reason 7', "invalid_rewrite_rule"),
    ("Something nobody templated went wrong.", "other"),
]

KEY_JSON_KEYS = {
    "schema", "cache_key", "inputs", "active_parser", "created_at",
    "last_used_at", "invalidated_at", "generation", "versions",
    "hc_parameters", "lcm_ids_path",
}
INPUT_KEYS = [
    "fwdata_path", "fwdata_size", "fwdata_mtime_ns",
    "generate_hc_config_path", "generate_hc_config_size",
    "generate_hc_config_mtime_ns", "hcparse_version",
]


def _cache():
    """Import the module under test inside the test body (test-first)."""
    try:
        return importlib.import_module("flextoolsmcp.server.sandbox.cache")
    except ImportError as exc:  # pragma: no cover - until T049 lands
        pytest.fail("flextoolsmcp.server.sandbox.cache is missing: %s" % exc)


@pytest.fixture(autouse=True)
def _fresh_cache_state():
    yield
    try:
        mod = importlib.import_module("flextoolsmcp.server.sandbox.cache")
    except ImportError:
        return
    reset = getattr(mod, "reset_state", None)
    if reset is not None:
        reset()


# --------------------------------------------------------------------------
# A Python stand-in for `hcparse.ps1 -Mode Generate`
# --------------------------------------------------------------------------

def _argv_params(argv):
    i = argv.index("-Mode")
    mode = argv[i + 1]
    rest = argv[i + 2:]
    params = {}
    for name, value in zip(rest[::2], rest[1::2], strict=True):
        assert name.startswith("-"), argv
        params[name[1:]] = value
    return mode, params


def _write_run_json(run_dir: Path, generate: dict) -> None:
    (run_dir / "run.json").write_text(
        json.dumps({
            "schema": "flextoolsmcp.hcparse-run/1",
            "hcparse_version": script.read_hcparse_version(),
            "mode": "generate",
            "generate": generate,
        }),
        encoding="utf-8",
    )


class EmulatedScript:
    """Does what Generate mode does, with the fake generator run directly.

    Writes the generator's combined output verbatim to `<RunDir>/generate-
    config.log`, lets it write `-ConfigOut`, and records `run.json`'s
    `generate` section. Records every argv (`calls`) and the RunDir state it
    saw (`seen`).
    """

    def __init__(self):
        self.calls = []
        self.argvs = []
        self.seen = []

    async def __call__(self, argv):
        self.argvs.append(list(argv))
        mode, params = _argv_params(argv)
        assert mode == "Generate"
        self.calls.append(params)
        run_dir = Path(params["RunDir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        self.seen.append({"run_dir_exists": run_dir.is_dir()})
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(GEN_FAKE), params["FwData"], params["ConfigOut"]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        (run_dir / "generate-config.log").write_bytes(proc.stdout)
        cfg = Path(params["ConfigOut"])
        text = proc.stdout.decode("utf-8", errors="replace")
        completed = "Writing completed." in text.splitlines()
        size = cfg.stat().st_size if cfg.exists() else 0
        _write_run_json(run_dir, {
            "exit_code": proc.returncode,
            "timed_out": False,
            "config_bytes": size,
            "writing_completed": completed,
        })
        return 0 if (proc.returncode == 0 and completed and size) else 4


class TimedOutScript:
    """The script killed the generator on its timeout (exit 6)."""

    def __init__(self, write_run_json=True):
        self.write_run_json = write_run_json
        self.calls = 0

    async def __call__(self, argv):
        self.calls += 1
        _mode, params = _argv_params(argv)
        run_dir = Path(params["RunDir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "generate-config.log").write_text(
            "Loading FieldWorks project...\r\n", encoding="utf-8")
        if self.write_run_json:
            _write_run_json(run_dir, {
                "exit_code": None, "timed_out": True,
                "config_bytes": 0, "writing_completed": False,
            })
            return 6
        return None


def _work_dir(label="run-cache-test") -> Path:
    # work/<run_id>/ takes only server-issued ids; `label` is for readability.
    from flextoolsmcp.server.parse import record

    run_id = record.new_run_id()
    wd = paths.work_dir(run_id)
    wd.mkdir(parents=True, exist_ok=True)
    (wd / ".flextoolsmcp-sandbox-work").write_text(
        json.dumps({"run_id": run_id, "pid": 0, "created_at": "2026-01-01T00:00:00Z",
                    "source_fwdata": ""}),
        encoding="utf-8",
    )
    return wd


def _ensure(cache, project, fake_generator, *, runner=None, **kw):
    kw.setdefault("work_dir", _work_dir())
    return cache.ensure_entry(
        project.name, project.fwdata, fake_generator.path,
        run_script=runner if runner is not None else EmulatedScript(), **kw)


def _cache_dir(project):
    return paths.config_cache_dir(project.name)


def _partials(project):
    d = _cache_dir(project)
    if not d.exists():
        return []
    return [p for p in d.iterdir() if p.name.endswith(".partial")]


def _key_json(entry_dir: Path) -> dict:
    return json.loads((entry_dir / "key.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# FR-024: the key recipe
# --------------------------------------------------------------------------

def test_key_inputs_recipe(fake_project, fake_generator):
    cache = _cache()
    inputs = cache.key_inputs(fake_project.fwdata, fake_generator.path,
                              hcparse_version="5.0.0")
    assert list(inputs) == INPUT_KEYS
    fw = Path(fake_project.fwdata)
    gen = Path(fake_generator.path)
    assert inputs["fwdata_path"] == str(fw.resolve())
    assert inputs["fwdata_size"] == fw.stat().st_size
    assert inputs["fwdata_mtime_ns"] == fw.stat().st_mtime_ns
    assert inputs["generate_hc_config_path"] == str(gen.resolve())
    assert inputs["generate_hc_config_size"] == gen.stat().st_size
    assert inputs["generate_hc_config_mtime_ns"] == gen.stat().st_mtime_ns
    assert inputs["hcparse_version"] == "5.0.0"


def test_key_is_fingerprint_key_recipe(fake_project, fake_generator):
    cache = _cache()
    inputs = cache.key_inputs(fake_project.fwdata, fake_generator.path,
                              hcparse_version="5.0.0")
    key = cache.compute_key(inputs)
    assert key == fingerprint_key(inputs)
    assert len(key) == 16 and all(c in "0123456789abcdef" for c in key)
    # Deterministic, and independent of dict order.
    assert cache.compute_key(dict(reversed(list(inputs.items())))) == key
    again = cache.key_inputs(fake_project.fwdata, fake_generator.path,
                             hcparse_version="5.0.0")
    assert cache.compute_key(again) == key


def test_version_bump_changes_key(fake_project, fake_generator):
    cache = _cache()
    a = cache.key_inputs(fake_project.fwdata, fake_generator.path, hcparse_version="5.0.0")
    b = cache.key_inputs(fake_project.fwdata, fake_generator.path, hcparse_version="5.0.1")
    assert cache.compute_key(a) != cache.compute_key(b)


def test_default_version_read_from_script_module_at_call_time(
        monkeypatch, fake_project, fake_generator):
    cache = _cache()
    monkeypatch.setattr(script, "read_hcparse_version", lambda: "9.9.9-test")
    inputs = cache.key_inputs(fake_project.fwdata, fake_generator.path)
    assert inputs["hcparse_version"] == "9.9.9-test"


def test_fwdata_change_changes_key(fake_project, fake_generator):
    cache = _cache()
    before = cache.compute_key(cache.key_inputs(fake_project.fwdata, fake_generator.path))
    fw = Path(fake_project.fwdata)
    fw.write_bytes(fw.read_bytes() + b"\n<!-- edit -->\n")
    after = cache.compute_key(cache.key_inputs(fake_project.fwdata, fake_generator.path))
    assert before != after


# --------------------------------------------------------------------------
# R-05: judging and load errors (pure)
# --------------------------------------------------------------------------

def test_progress_lines_and_kinds_constants():
    cache = _cache()
    assert tuple(cache.PROGRESS_LINES) == PROGRESS
    assert tuple(cache.LOAD_ERROR_KINDS) == tuple(k for _l, k in TEMPLATE_KINDS)


@pytest.mark.parametrize("line,kind", TEMPLATE_KINDS)
def test_classify_load_error(line, kind):
    assert _cache().classify_load_error(line) == kind


def test_extract_load_errors_by_exclusion():
    cache = _cache()
    lines = [PROGRESS[0], TEMPLATE_KINDS[0][0], "", TEMPLATE_KINDS[4][0],
             "A new FieldWorks progress line.", PROGRESS[1], PROGRESS[2], PROGRESS[3], ""]
    errors = cache.extract_load_errors("\r\n".join(lines))
    assert errors == [
        {"kind": "undefined_phoneme", "line": TEMPLATE_KINDS[0][0]},
        {"kind": "invalid_environment", "line": TEMPLATE_KINDS[4][0]},
        # Over-counted, never hidden (R-05 rationale).
        {"kind": "other", "line": "A new FieldWorks progress line."},
    ]


def test_judge_generation_needs_all_three(tmp_path):
    cache = _cache()
    good = "\r\n".join(PROGRESS)
    cfg = tmp_path / "hc-config.xml"
    cfg.write_text("<HermitCrabInput/>", encoding="utf-8")
    empty = tmp_path / "empty.xml"
    empty.write_bytes(b"")
    assert cache.judge_generation(0, cfg, good) is True
    assert cache.judge_generation(1, cfg, good) is False
    assert cache.judge_generation(None, cfg, good) is False
    assert cache.judge_generation(0, empty, good) is False
    assert cache.judge_generation(0, tmp_path / "missing.xml", good) is False
    assert cache.judge_generation(0, cfg, "\r\n".join(PROGRESS[:3])) is False


# --------------------------------------------------------------------------
# contracts/tools.md section 4: stderr_tail
# --------------------------------------------------------------------------

def test_stderr_tail_last_20_lines():
    cache = _cache()
    lines = ["line %d" % i for i in range(30)]
    tail = cache.stderr_tail("\r\n".join(lines) + "\r\n")
    assert tail.splitlines() == lines[-20:]


def test_stderr_tail_escapes_non_ascii():
    cache = _cache()
    tail = cache.stderr_tail("Café \U00010400 done")
    assert tail.isascii()
    assert "\\xe9" in tail and "\\U00010400" in tail
    assert "é" not in tail


def test_stderr_tail_capped_at_4_kib_keeping_the_end():
    cache = _cache()
    lines = ["%02d " % i + "x" * 500 for i in range(20)]
    tail = cache.stderr_tail("\n".join(lines))
    assert len(tail.encode("ascii")) <= 4096
    assert tail.endswith(lines[-1])
    assert cache.STDERR_TAIL_LINES == 20 and cache.STDERR_TAIL_MAX_BYTES == 4096


def test_stderr_tail_of_short_output_is_whole():
    cache = _cache()
    assert cache.stderr_tail("one\r\ntwo").splitlines() == ["one", "two"]
    assert cache.stderr_tail("") == ""


# --------------------------------------------------------------------------
# build_entry: success, argv, key.json, the .partial rename
# --------------------------------------------------------------------------

async def test_cold_build_writes_entry_and_key_json(
        sandbox_root, fake_project, fake_generator, tmp_path):
    cache = _cache()
    runner = EmulatedScript()
    log_dir = tmp_path / "run" / "sandbox"
    log_dir.mkdir(parents=True)
    entry = await _ensure(cache, fake_project, fake_generator, runner=runner,
                          run_id="r1", log_dir=log_dir,
                          versions={"generate_hc_config": "9.3.11.1",
                                    "fieldworks_hermitcrab": "3.8.2.0"})
    inputs = cache.key_inputs(fake_project.fwdata, fake_generator.path)
    key = cache.compute_key(inputs)

    assert entry.built is True
    assert entry.key == key and entry.project == fake_project.name
    assert entry.path == _cache_dir(fake_project) / key
    assert entry.config_path == entry.path / "hc-config.xml"
    assert entry.log_path == entry.path / "generate-config.log"
    assert entry.config_path.stat().st_size > 0
    assert "Writing completed." in entry.log_path.read_text(encoding="utf-8")
    # The whole log also lands in the run's sandbox/ (FR-009).
    assert (log_dir / "generate-config.log").read_bytes() == entry.log_path.read_bytes()

    meta = _key_json(entry.path)
    assert set(meta) == KEY_JSON_KEYS
    assert meta["schema"] == "flextoolsmcp.hc-cache/1" == cache.SCHEMA
    assert meta["cache_key"] == key == cache.compute_key(meta["inputs"])
    assert meta["inputs"] == inputs
    assert meta["active_parser"] == "HC"
    assert meta["invalidated_at"] is None
    assert meta["created_at"].endswith("Z") and meta["last_used_at"].endswith("Z")
    gen = meta["generation"]
    assert gen["exit_code"] == 0 and gen["writing_completed"] is True
    assert gen["load_errors"] == [] and gen["load_error_count"] == 0
    assert isinstance(gen["duration_ms"], int) and gen["duration_ms"] >= 0
    assert meta["versions"] == {"generate_hc_config": "9.3.11.1",
                                "fieldworks_hermitcrab": "3.8.2.0"}
    assert entry.meta == meta
    assert _partials(fake_project) == []
    # T099: the sidecar and the Morpher settings, neither in the key.
    assert meta["lcm_ids_path"] == "lcm-ids.json"
    assert entry.lcm_ids_path == entry.path / "lcm-ids.json"
    sidecar = json.loads(entry.lcm_ids_path.read_text(encoding="utf-8"))
    assert sidecar == {"schema": "flextoolsmcp.hc-lcm-ids/1", "valid": True,
                       "ids": {}, "invalid_ids": [], "error": None,
                       "vernacular_ws": None}
    # conftest's fake project stores <HC><GuessRoots>false</GuessRoots>.
    assert meta["hc_parameters"] == {"del_reapps": 0, "max_roots": 2,
                                     "merge_analyses": True, "guess_roots": False,
                                     "max_alternatives": 0}
    assert entry.hc_parameters == meta["hc_parameters"]


async def test_build_argv_generate_params(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    runner = EmulatedScript()
    wd = _work_dir("run-argv")
    entry = await _ensure(cache, fake_project, fake_generator, runner=runner,
                          work_dir=wd, timeout_seconds=123)
    assert len(runner.calls) == 1
    argv = runner.argvs[0]
    assert tuple(argv[:len(script.ARGV_PREFIX)]) == script.ARGV_PREFIX
    assert argv[len(script.ARGV_PREFIX)] == str(script.script_path())
    p = runner.calls[0]
    partial = _cache_dir(fake_project) / (entry.key + ".partial")
    assert Path(p["RunDir"]) == partial
    assert Path(p["ConfigOut"]) == partial / "hc-config.xml"
    assert Path(p["GenerateHCConfigPath"]) == Path(fake_generator.path)
    assert Path(p["FwData"]).resolve() == Path(fake_project.fwdata).resolve()
    assert Path(p["WorkDir"]) == wd
    assert p["GenerateTimeoutSeconds"] == "123"
    # ConfigOut is under config-cache/, never sandboxes/ (FR-026).
    assert paths.is_under(p["ConfigOut"], paths.config_cache_root())
    assert not paths.is_under(p["ConfigOut"], paths.sandboxes_root(), strict=False)


async def test_partial_is_renamed_atomically(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    states = []

    class Observing(EmulatedScript):
        async def __call__(self, argv):
            _m, params = _argv_params(argv)
            run_dir = Path(params["RunDir"])
            final = run_dir.with_name(run_dir.name[:-len(".partial")])
            states.append({"final_exists_during": final.exists(),
                           "name": run_dir.name})
            return await super().__call__(argv)

    entry = await _ensure(cache, fake_project, fake_generator, runner=Observing())
    assert states[0]["name"] == entry.key + ".partial"
    assert states[0]["final_exists_during"] is False
    assert entry.path.is_dir()
    assert not (entry.path.parent / (entry.key + ".partial")).exists()


async def test_stale_partial_is_cleared_before_build(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    key = cache.compute_key(cache.key_inputs(fake_project.fwdata, fake_generator.path))
    stale = _cache_dir(fake_project) / (key + ".partial")
    stale.mkdir(parents=True)
    (stale / "leftover.txt").write_text("from a killed build", encoding="utf-8")
    entry = await _ensure(cache, fake_project, fake_generator)
    assert not (entry.path / "leftover.txt").exists()
    assert _partials(fake_project) == []


# --------------------------------------------------------------------------
# FR-009: the five failure fixtures
# --------------------------------------------------------------------------

FR009_FIXTURES = [
    # (knobs, expected exit code or "nonzero", verbatim text that must be in the tail)
    pytest.param({"mode": "help"}, 0, "generatehcconfig <input-project> <output-config>",
                 id="help-exit-0"),
    pytest.param({"mode": "locked"}, 1,
                 "The FieldWorks project is currently open in another application.",
                 id="locked"),
    pytest.param({"mode": "migration"}, 1,
                 "The FieldWorks project was created with an older version of FLEx.",
                 id="migration"),
    pytest.param({"mode": "crash"}, "nonzero", "System.NotImplementedException", id="crash"),
    pytest.param({"mode": "empty_config"}, 0, "Writing completed.", id="empty-config"),
]


def _assert_config_failed(cache, exc, *, run_id, log_path, exit_code, needle):
    from flextoolsmcp.server.response_models import ParserConfigFailedDetail

    detail = exc.detail
    assert isinstance(detail, ParserConfigFailedDetail)
    dumped = detail.model_dump()
    assert list(dumped) == ["error_code", "exit_code", "stderr_tail", "log_path", "run_id"]
    assert dumped["error_code"] == "parser_config_failed"
    if exit_code == "nonzero":
        assert detail.exit_code not in (None, 0)
    else:
        assert detail.exit_code == exit_code
    assert detail.run_id == run_id
    assert Path(detail.log_path) == log_path
    tail = detail.stderr_tail
    assert tail.isascii()
    assert len(tail.splitlines()) <= 20
    assert len(tail.encode("ascii")) <= 4096
    if needle:
        assert needle in tail


@pytest.mark.parametrize("knobs,exit_code,needle", FR009_FIXTURES)
async def test_fr009_fixture_gives_parser_config_failed(
        sandbox_root, fake_project, fake_generator, tmp_path, knobs, exit_code, needle):
    cache = _cache()
    fake_generator.set(**knobs)
    log_dir = tmp_path / "run" / "sandbox"
    log_dir.mkdir(parents=True)
    with pytest.raises(cache.ParserConfigFailed) as info:
        await _ensure(cache, fake_project, fake_generator, run_id="run-fr009",
                      log_dir=log_dir)
    log_path = log_dir / "generate-config.log"
    _assert_config_failed(cache, info.value, run_id="run-fr009", log_path=log_path,
                          exit_code=exit_code, needle=needle)
    # The log is captured WHOLE: every line the generator printed.
    log = log_path.read_text(encoding="utf-8")
    if knobs["mode"] == "help":
        assert "Generates a HermitCrab configuration file" in log
        assert "Specifies the HC configuration path." in log
    if knobs["mode"] in ("locked", "migration"):
        assert log.splitlines()[:2] == ["Loading FieldWorks project...", "Loading failed."]
    # No usable entry, no .partial debris.
    key = cache.compute_key(cache.key_inputs(fake_project.fwdata, fake_generator.path))
    assert cache.lookup(fake_project.name, key) is None
    assert not (_cache_dir(fake_project) / key).exists()
    assert _partials(fake_project) == []


async def test_failed_log_kept_outside_partial_without_log_dir(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    fake_generator.set(mode="locked")
    with pytest.raises(cache.ParserConfigFailed) as info:
        await _ensure(cache, fake_project, fake_generator)
    key = cache.compute_key(cache.key_inputs(fake_project.fwdata, fake_generator.path))
    log_path = Path(info.value.detail.log_path)
    assert log_path == _cache_dir(fake_project) / (key + ".generate-config.log")
    assert log_path.is_file()
    assert "currently open in another application" in log_path.read_text(encoding="utf-8")
    assert info.value.detail.run_id is None
    assert _partials(fake_project) == []


async def test_long_non_ascii_failure_tail_is_bounded(
        sandbox_root, fake_project, fake_generator, tmp_path):
    cache = _cache()
    # 40 long non-ASCII "load error" lines, then a crash: the tail is bounded.
    lines = ["กข %02d " % i + "y" * 300 for i in range(40)]
    fake_generator.set(mode="crash", load_error_lines=json.dumps(lines))
    log_dir = tmp_path / "sandbox"
    log_dir.mkdir()
    with pytest.raises(cache.ParserConfigFailed) as info:
        await _ensure(cache, fake_project, fake_generator, log_dir=log_dir)
    tail = info.value.detail.stderr_tail
    assert tail.isascii()
    assert len(tail.splitlines()) <= 20
    assert len(tail.encode("ascii")) <= 4096
    # The log itself is whole and keeps the non-ASCII text verbatim (UTF-8).
    log = (log_dir / "generate-config.log").read_text(encoding="utf-8")
    assert all(line in log for line in lines)


async def test_generation_timeout_gives_null_exit_code(
        sandbox_root, fake_project, fake_generator, tmp_path):
    cache = _cache()
    log_dir = tmp_path / "sandbox"
    log_dir.mkdir()
    with pytest.raises(cache.ParserConfigFailed) as info:
        await _ensure(cache, fake_project, fake_generator, runner=TimedOutScript(),
                      run_id="run-timeout", log_dir=log_dir)
    assert info.value.detail.exit_code is None
    assert info.value.detail.run_id == "run-timeout"
    assert _partials(fake_project) == []


async def test_killed_script_without_run_json_gives_null_exit_code(
        sandbox_root, fake_project, fake_generator, tmp_path):
    cache = _cache()
    log_dir = tmp_path / "sandbox"
    log_dir.mkdir()
    with pytest.raises(cache.ParserConfigFailed) as info:
        await _ensure(cache, fake_project, fake_generator,
                      runner=TimedOutScript(write_run_json=False), log_dir=log_dir)
    assert info.value.detail.exit_code is None
    assert Path(info.value.detail.log_path).is_file()
    assert _partials(fake_project) == []


# --------------------------------------------------------------------------
# FR-010: load errors itemised, not refused; carried on a warm run
# --------------------------------------------------------------------------

async def test_load_errors_counted_tagged_and_usable(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    fake_generator.set(load_errors=3)
    entry = await _ensure(cache, fake_project, fake_generator)
    assert entry.built is True
    assert entry.load_error_count == 3
    assert [e["kind"] for e in entry.load_errors] == [
        "undefined_phoneme", "invalid_affix_process", "phoneme_no_grapheme"]
    assert [e["line"] for e in entry.load_errors] == [l for l, _k in TEMPLATE_KINDS[:3]]
    gen = _key_json(entry.path)["generation"]
    assert gen["load_error_count"] == 3 == len(gen["load_errors"])
    # Still usable: the run proceeds.
    assert entry.config_path.stat().st_size > 0
    assert cache.lookup(fake_project.name, entry.key) is not None


async def test_load_errors_carried_on_warm_run(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    fake_generator.set(load_errors=3)
    cold = await _ensure(cache, fake_project, fake_generator)
    fake_generator.set(load_errors=None)
    warm = await _ensure(cache, fake_project, fake_generator)
    assert warm.built is False
    assert warm.key == cold.key
    assert warm.load_error_count == 3
    assert warm.load_errors == cold.load_errors
    assert len(fake_generator.invocations()) == 1


# --------------------------------------------------------------------------
# R-12: the per-key lock builds once
# --------------------------------------------------------------------------

def test_lock_for_is_per_project_and_key():
    cache = _cache()
    a = cache.lock_for("P", "k1")
    assert isinstance(a, asyncio.Lock)
    assert cache.lock_for("P", "k1") is a
    assert cache.lock_for("P", "k2") is not a
    assert cache.lock_for("Q", "k1") is not a


async def test_two_concurrent_builds_run_generator_once(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    fake_generator.set(sleep_seconds="0.5")
    runner = EmulatedScript()
    first, second = await asyncio.gather(
        _ensure(cache, fake_project, fake_generator, runner=runner),
        _ensure(cache, fake_project, fake_generator, runner=runner),
    )
    assert len(runner.calls) == 1
    assert len(fake_generator.invocations()) == 1
    assert first.key == second.key and first.path == second.path
    assert sorted([first.built, second.built]) == [False, True]


# --------------------------------------------------------------------------
# lookup: usability, last_used_at
# --------------------------------------------------------------------------

async def test_lookup_skips_empty_config(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    entry = await _ensure(cache, fake_project, fake_generator)
    entry.config_path.write_bytes(b"")
    assert cache.lookup(fake_project.name, entry.key) is None


async def test_lookup_skips_missing_or_mismatched_key_json(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    entry = await _ensure(cache, fake_project, fake_generator)
    kj = entry.path / "key.json"
    meta = json.loads(kj.read_text(encoding="utf-8"))
    meta["cache_key"] = "0" * 16
    kj.write_text(json.dumps(meta), encoding="utf-8")
    assert cache.lookup(fake_project.name, entry.key) is None
    kj.write_text("{trunc", encoding="utf-8")
    assert cache.lookup(fake_project.name, entry.key) is None
    kj.unlink()
    assert cache.lookup(fake_project.name, entry.key) is None


def test_lookup_of_absent_project_creates_nothing(sandbox_root):
    cache = _cache()
    assert cache.lookup("NoSuchProject", "0123456789abcdef") is None
    assert not (sandbox_root / "config-cache" / "NoSuchProject").exists()


async def test_last_used_at_updated_on_use(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    entry = await _ensure(cache, fake_project, fake_generator)
    kj = entry.path / "key.json"
    meta = json.loads(kj.read_text(encoding="utf-8"))
    created = meta["created_at"]
    meta["last_used_at"] = "2000-01-01T00:00:00Z"
    kj.write_text(json.dumps(meta), encoding="utf-8")

    found = cache.lookup(fake_project.name, entry.key, touch=False)
    assert found is not None
    assert _key_json(entry.path)["last_used_at"] == "2000-01-01T00:00:00Z"

    found = cache.lookup(fake_project.name, entry.key)
    after = _key_json(entry.path)
    assert after["last_used_at"] > "2000-01-01T00:00:00Z"
    assert after["created_at"] == created
    assert found.meta["last_used_at"] == after["last_used_at"]

    meta = after
    meta["last_used_at"] = "2000-01-01T00:00:00Z"
    kj.write_text(json.dumps(meta), encoding="utf-8")
    warm = await _ensure(cache, fake_project, fake_generator)
    assert warm.built is False
    assert _key_json(entry.path)["last_used_at"] > "2000-01-01T00:00:00Z"


# --------------------------------------------------------------------------
# FR-026: invalidation
# --------------------------------------------------------------------------

async def test_invalidate_marks_every_entry_of_project(
        sandbox_root, fake_project, fake_project_factory, fake_generator):
    cache = _cache()
    first = await _ensure(cache, fake_project, fake_generator)
    fw = Path(fake_project.fwdata)
    fw.write_bytes(fw.read_bytes() + b"\n<!-- edit -->\n")
    second = await _ensure(cache, fake_project, fake_generator)
    assert first.key != second.key
    other = fake_project_factory("OtherProj")
    kept = await _ensure(cache, other, fake_generator)

    assert cache.invalidate(fake_project.name) == 2
    for entry in (first, second):
        assert _key_json(entry.path)["invalidated_at"] is not None
        assert _key_json(entry.path)["invalidated_at"].endswith("Z")
        assert cache.lookup(fake_project.name, entry.key) is None
    # Another project's entries are untouched.
    assert _key_json(kept.path)["invalidated_at"] is None
    assert cache.lookup(other.name, kept.key) is not None


def test_invalidate_absent_project_is_zero_and_creates_nothing(sandbox_root):
    cache = _cache()
    assert cache.invalidate("NeverBuilt") == 0
    assert not (sandbox_root / "config-cache" / "NeverBuilt").exists()


async def test_invalidated_entry_is_rebuilt(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    first = await _ensure(cache, fake_project, fake_generator)
    cache.invalidate(fake_project.name)
    again = await _ensure(cache, fake_project, fake_generator)
    assert again.built is True
    assert again.key == first.key
    assert _key_json(again.path)["invalidated_at"] is None
    assert cache.lookup(fake_project.name, again.key) is not None
    assert len(fake_generator.invocations()) == 2
    assert _partials(fake_project) == []


# --------------------------------------------------------------------------
# SC-006 offline: a slow generator is skipped on the second run
# --------------------------------------------------------------------------

async def test_sc006_slow_generator_skipped_on_second_run(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    fake_generator.set(sleep_seconds="1.0")
    t0 = time.monotonic()
    cold = await _ensure(cache, fake_project, fake_generator)
    cold_s = time.monotonic() - t0
    t1 = time.monotonic()
    warm = await _ensure(cache, fake_project, fake_generator)
    warm_s = time.monotonic() - t1
    assert cold.built is True and warm.built is False
    assert len(fake_generator.invocations()) == 1
    assert cold_s >= 1.0
    assert warm_s * 2 < cold_s


# --------------------------------------------------------------------------
# FR-026: only cache.build_entry passes -ConfigOut (AST pin)
# --------------------------------------------------------------------------

def _config_out_sites(tree):
    """(function name, lineno) for every ConfigOut keyword / string in code."""
    sites = []
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(
                    getattr(body[0], "value", None), ast.Constant):
                docstrings.add(id(body[0].value))

    def visit(node, func):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node.name
        if isinstance(node, ast.keyword) and node.arg in ("ConfigOut", "-ConfigOut"):
            sites.append((func, node.value.lineno))
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and id(node) not in docstrings
                and node.value.strip() in ("ConfigOut", "-ConfigOut")):
            sites.append((func, node.lineno))
        for child in ast.iter_child_nodes(node):
            visit(child, func)

    visit(tree, None)
    return sites


def test_only_cache_build_entry_passes_config_out():
    cache_py = SRC_ROOT / "server" / "sandbox" / "cache.py"
    assert cache_py.is_file(), "sandbox/cache.py is missing"
    offenders = []
    for py in SRC_ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for func, lineno in _config_out_sites(tree):
            if py.resolve() == cache_py.resolve() and func == "build_entry":
                continue
            offenders.append("%s:%d (%s)" % (py.relative_to(SRC_ROOT), lineno, func))
    assert offenders == [], "ConfigOut passed outside cache.build_entry: %s" % offenders
    tree = ast.parse(cache_py.read_text(encoding="utf-8"))
    assert any(func == "build_entry" for func, _l in _config_out_sites(tree)), (
        "cache.build_entry must be the one caller passing ConfigOut to build_argv")


# --------------------------------------------------------------------------
# US6 (T082): prune to 3 per project, LRU; the in-process refcount
# --------------------------------------------------------------------------

def _set_last_used(entry, stamp):
    kj = entry.path / "key.json"
    meta = json.loads(kj.read_text(encoding="utf-8"))
    meta["last_used_at"] = stamp
    kj.write_text(json.dumps(meta), encoding="utf-8")


async def _entries(cache, project, fake_generator, n):
    """`n` distinct usable entries for `project`, last_used_at oldest first."""
    made = []
    fw = Path(project.fwdata)
    for i in range(n):
        if i:
            fw.write_bytes(fw.read_bytes() + b"\n<!-- edit %d -->\n" % i)
        entry = await _ensure(cache, project, fake_generator)
        assert entry.built is True
        made.append(entry)
    for i, entry in enumerate(made):
        _set_last_used(entry, "2020-01-0%dT00:00:00.000Z" % (i + 1))
    return made


def _entry_dirs(project):
    d = _cache_dir(project)
    return sorted(p.name for p in d.iterdir() if p.is_dir()) if d.exists() else []


async def test_prune_keeps_three_most_recently_used(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    made = await _entries(cache, fake_project, fake_generator, 5)
    # Touch the oldest: it becomes the most recently used.
    _set_last_used(made[0], "2020-02-01T00:00:00.000Z")
    deleted = cache.prune(fake_project.name)
    assert sorted(deleted) == sorted([made[1].key, made[2].key])
    assert _entry_dirs(fake_project) == sorted([made[0].key, made[3].key, made[4].key])
    assert cache.prune(fake_project.name) == []


async def test_prune_keep_parameter(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    made = await _entries(cache, fake_project, fake_generator, 3)
    assert sorted(cache.prune(fake_project.name, keep=1)) == sorted(
        [made[0].key, made[1].key])
    assert _entry_dirs(fake_project) == [made[2].key]


async def test_prune_spares_in_use_entry(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    made = await _entries(cache, fake_project, fake_generator, 5)
    oldest = made[0]
    assert cache.acquire(oldest) == 1
    assert cache.refcount(fake_project.name, oldest.key) == 1
    deleted = cache.prune(fake_project.name)
    assert oldest.key not in deleted
    assert oldest.config_path.is_file()
    assert sorted(deleted) == sorted([made[1].key, made[2].key])
    # Held, it took a slot: 3 remain. Released, it is the least recently
    # used and is the first to go.
    assert _entry_dirs(fake_project) == sorted([oldest.key, made[3].key, made[4].key])
    assert cache.prune(fake_project.name) == []
    assert cache.release(oldest) == 0
    assert cache.prune(fake_project.name, keep=2) == [oldest.key]
    assert not oldest.path.exists()


async def test_refcount_nests_and_never_goes_negative(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    entry = await _ensure(cache, fake_project, fake_generator)
    assert cache.refcount(fake_project.name, entry.key) == 0
    assert cache.acquire(entry) == 1
    assert cache.acquire(entry) == 2
    assert cache.release(entry) == 1
    assert cache.release(entry) == 0
    assert cache.release(entry) == 0
    assert cache.refcount(fake_project.name, entry.key) == 0


async def test_in_use_context_manager_releases_on_error(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    entry = await _ensure(cache, fake_project, fake_generator)
    with pytest.raises(RuntimeError):
        with cache.in_use(entry):
            assert cache.refcount(fake_project.name, entry.key) == 1
            raise RuntimeError("run failed")
    assert cache.refcount(fake_project.name, entry.key) == 0


async def test_reset_state_clears_refcounts(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    entry = await _ensure(cache, fake_project, fake_generator)
    cache.acquire(entry)
    cache.reset_state()
    assert cache.refcount(fake_project.name, entry.key) == 0


async def test_prune_deletes_invalidated_at_refcount_zero(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    made = await _entries(cache, fake_project, fake_generator, 2)
    held = made[1]
    cache.acquire(held)
    cache.invalidate(fake_project.name)
    # Invalidated entries go even when fewer than 3 remain -- except in use.
    assert cache.prune(fake_project.name) == [made[0].key]
    assert held.path.is_dir()
    cache.release(held)
    assert cache.prune(fake_project.name) == [held.key]
    assert _entry_dirs(fake_project) == []


async def test_prune_deletes_unusable_entries(sandbox_root, fake_project, fake_generator):
    cache = _cache()
    made = await _entries(cache, fake_project, fake_generator, 3)
    made[0].config_path.write_bytes(b"")
    (made[1].path / "key.json").write_text("{trunc", encoding="utf-8")
    assert sorted(cache.prune(fake_project.name)) == sorted([made[0].key, made[1].key])
    assert _entry_dirs(fake_project) == [made[2].key]


async def test_prune_ignores_partial_failed_logs_and_foreign_names(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    made = await _entries(cache, fake_project, fake_generator, 1)
    d = _cache_dir(fake_project)
    partial = d / ("0" * 16 + ".partial")
    partial.mkdir()
    failed_log = d / ("1" * 16 + ".generate-config.log")
    failed_log.write_text("Loading failed.", encoding="utf-8")
    foreign = d / "not-an-entry"
    foreign.mkdir()
    cache.invalidate(fake_project.name)
    assert cache.prune(fake_project.name) == [made[0].key]
    assert partial.is_dir() and failed_log.is_file() and foreign.is_dir()


async def test_prune_is_per_project(
        sandbox_root, fake_project, fake_project_factory, fake_generator):
    cache = _cache()
    await _entries(cache, fake_project, fake_generator, 4)
    other = fake_project_factory("OtherProj")
    kept = await _entries(cache, other, fake_generator, 1)
    assert len(cache.prune(fake_project.name)) == 1
    assert _entry_dirs(other) == [kept[0].key]


def test_prune_absent_project_creates_nothing(sandbox_root):
    cache = _cache()
    assert cache.prune("NeverBuilt") == []
    assert not (sandbox_root / "config-cache" / "NeverBuilt").exists()


async def test_prune_deletes_through_the_config_cache_guard(
        monkeypatch, sandbox_root, fake_project, fake_generator):
    cache = _cache()
    made = await _entries(cache, fake_project, fake_generator, 4)
    guarded = []
    real = paths.assert_under

    def spy(path, root, **kw):
        guarded.append((Path(path), Path(root)))
        return real(path, root, **kw)

    monkeypatch.setattr(paths, "assert_under", spy)
    assert cache.prune(fake_project.name) == [made[0].key]
    root = paths.config_cache_root()
    assert (made[0].path, root) in guarded
    assert all(r == root for _p, r in guarded)


# --------------------------------------------------------------------------
# Windows: the real hcparse.ps1 against the fake generator
# --------------------------------------------------------------------------

@pytest.mark.windows_only
async def test_real_script_cold_build(sandbox_root, fake_project, fake_generator, tmp_path):
    cache = _cache()
    log_dir = tmp_path / "sandbox"
    log_dir.mkdir()
    entry = await cache.ensure_entry(
        fake_project.name, fake_project.fwdata, fake_generator.path,
        work_dir=_work_dir("run-real-cold"), run_id="run-real-cold", log_dir=log_dir)
    assert entry.built is True
    assert entry.config_path.stat().st_size > 0
    assert len(fake_generator.invocations()) == 1
    assert "Writing completed." in (log_dir / "generate-config.log").read_text(encoding="utf-8")
    assert _partials(fake_project) == []


@pytest.mark.windows_only
@pytest.mark.parametrize("knobs,exit_code,needle", FR009_FIXTURES)
async def test_real_script_fr009_fixture(
        sandbox_root, fake_project, fake_generator, tmp_path, knobs, exit_code, needle):
    cache = _cache()
    fake_generator.set(**knobs)
    log_dir = tmp_path / "sandbox"
    log_dir.mkdir()
    with pytest.raises(cache.ParserConfigFailed) as info:
        await cache.ensure_entry(
            fake_project.name, fake_project.fwdata, fake_generator.path,
            work_dir=_work_dir("run-real-fr009"), run_id="run-real-fr009", log_dir=log_dir)
    _assert_config_failed(cache, info.value, run_id="run-real-fr009",
                          log_path=log_dir / "generate-config.log",
                          exit_code=exit_code, needle=needle)
    assert _partials(fake_project) == []


@pytest.mark.windows_only
async def test_real_script_generate_timeout(sandbox_root, fake_project, fake_generator,
                                            tmp_path):
    cache = _cache()
    fake_generator.set(sleep_seconds="30")
    log_dir = tmp_path / "sandbox"
    log_dir.mkdir()
    t0 = time.monotonic()
    with pytest.raises(cache.ParserConfigFailed) as info:
        await cache.ensure_entry(
            fake_project.name, fake_project.fwdata, fake_generator.path,
            work_dir=_work_dir("run-real-timeout"), run_id="run-real-timeout",
            log_dir=log_dir, timeout_seconds=2)
    assert time.monotonic() - t0 < 25
    assert info.value.detail.exit_code is None
    assert _partials(fake_project) == []


@pytest.mark.windows_only
async def test_real_script_sc006_warm_skips_generation(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()
    fake_generator.set(sleep_seconds="2")
    t0 = time.monotonic()
    cold = await cache.ensure_entry(
        fake_project.name, fake_project.fwdata, fake_generator.path,
        work_dir=_work_dir("run-real-sc006a"))
    cold_s = time.monotonic() - t0
    t1 = time.monotonic()
    warm = await cache.ensure_entry(
        fake_project.name, fake_project.fwdata, fake_generator.path,
        work_dir=_work_dir("run-real-sc006b"))
    warm_s = time.monotonic() - t1
    assert cold.built is True and warm.built is False
    assert len(fake_generator.invocations()) == 1
    assert warm_s * 2 < cold_s


# --------------------------------------------------------------------------
# T099: lcm-ids.json (FR-050, D4 reversed) and key.json hc_parameters (D3)
# --------------------------------------------------------------------------

_CIRCUMFIX = "d7f713df-e8cf-11d3-9764-00c04f186933"


def _fwdata_with(rts, params="<ParserParameters><ActiveParser>HC</ActiveParser>"
                 "<HC><MaxRoots>3</MaxRoots></HC></ParserParameters>"):
    """A .fwdata whose n-th <rt> (1-based) is rts[n-1] = (class, morph_type_guid)."""
    from xml.sax.saxutils import escape

    body = []
    for n, (cls, morph_type) in enumerate(rts, start=1):
        inner = ""
        if morph_type:
            inner = '<MorphType><objsur guid="%s" t="r" /></MorphType>' % morph_type
        if cls == "MoMorphData":
            inner = "<ParserParameters><Uni>%s</Uni></ParserParameters>" % escape(params)
        body.append('<rt class="%s" guid="00000000-0000-0000-0000-%012d">%s</rt>'
                    % (cls, n, inner))
    return ('<?xml version="1.0" encoding="utf-8"?>\n<languageproject version="7000072">\n'
            + "\n".join(body) + "\n</languageproject>\n")


def _props(**named):
    return "<Properties>%s</Properties>" % "".join(
        '<Property name="%s">%s</Property>' % (k, v) for k, v in named.items())


def _config_with(entries):
    """entries: [(allomorph_props, morpheme_props, tag)] -> an HC config."""
    parts = []
    for i, (allo, morph, tag) in enumerate(entries):
        if tag == "LexicalEntry":
            parts.append('<LexicalEntry id="e%d"><Allomorphs><Allomorph id="a%d">'
                         "<PhoneticShape>x</PhoneticShape>%s</Allomorph></Allomorphs>"
                         "<Gloss>g</Gloss>%s</LexicalEntry>"
                         % (i, i, _props(**allo), _props(**morph)))
        else:
            parts.append('<MorphologicalRule id="r%d"><MorphologicalSubrules>'
                         '<MorphologicalSubrule id="s%d">%s</MorphologicalSubrule>'
                         "</MorphologicalSubrules><Gloss>g</Gloss>%s</MorphologicalRule>"
                         % (i, i, _props(**allo), _props(**morph)))
    stratum_props = _props(ID=999)
    return ('<?xml version="1.0" encoding="utf-8"?><HermitCrabInput><Language>'
            "<Strata><Stratum>%s%s</Stratum></Strata></Language></HermitCrabInput>"
            % ("".join(parts), stratum_props))


def _lcm_ids():
    return importlib.import_module("flextoolsmcp.server.sandbox.lcm_ids")


def _build(tmp_path, rts, entries, **kw):
    fw = tmp_path / "P.fwdata"
    fw.write_text(_fwdata_with(rts), encoding="utf-8")
    cfg = tmp_path / "hc-config.xml"
    cfg.write_text(_config_with(entries), encoding="utf-8")
    return _lcm_ids().build(cfg, fw, **kw)


_RTS = [
    ("LangProject", None),                                          # 1
    ("MoStemAllomorph", "d7f713e5-e8cf-11d3-9764-00c04f186933"),    # 2
    ("MoStemMsa", None),                                            # 3
    ("MoAffixProcess", _CIRCUMFIX),                                 # 4
    ("MoDerivAffMsa", None),                                        # 5
    ("LexEntryInflType", None),                                     # 6
    ("MoMorphData", None),                                          # 7
    ("MoAffixAllomorph", "d7f713dd-e8cf-11d3-9764-00c04f186933"),   # 8
]


def test_sidecar_maps_each_role_by_rt_document_order(tmp_path):
    from flextoolsmcp.server.sandbox import engine

    doc, params = _build(tmp_path, _RTS, [
        ({"ID": 2}, {"ID": 3, "InflTypeID": 6}, "LexicalEntry"),
        ({"ID": 4, "ID2": 8}, {"ID": 5}, "MorphologicalRule"),
    ])
    assert doc["schema"] == "flextoolsmcp.hc-lcm-ids/1"
    assert doc["valid"] is True and doc["invalid_ids"] == [] and doc["error"] is None
    ids = doc["ids"]
    assert set(ids) == {"2", "3", "4", "5", "6", "8"}
    assert ids["2"] == {"class": "MoStemAllomorph", "role": "form",
                        "guid": "00000000-0000-0000-0000-000000000002",
                        "morph_type_guid": "d7f713e5-e8cf-11d3-9764-00c04f186933"}
    assert ids["4"]["morph_type_guid"] == _CIRCUMFIX and ids["4"]["role"] == "form"
    assert ids["8"]["role"] == "form"
    assert ids["3"] == {"class": "MoStemMsa", "role": "msa",
                        "guid": "00000000-0000-0000-0000-000000000003"}
    assert ids["6"]["role"] == "infl_type" and "morph_type_guid" not in ids["6"]
    # A Stratum's Properties are not read by GetMorphs: id 999 is ignored.
    assert "999" not in ids and doc["valid"]
    # The same pass yields the ParserParameters text.
    assert engine.hc_parameters_from_text(params)["max_roots"] == 3


def test_form_ids_carry_their_default_vernacular_form_text(tmp_path):
    """FLEx shows a morph's allomorph form, so the map records each form
    id's `Form` in the first `CurVernWss` writing system (FR-050)."""
    fw = tmp_path / "P.fwdata"
    rts = (
        '<rt class="LangProject" guid="00000000-0000-0000-0000-000000000001">'
        "<CurVernWss><Uni>id-fonipa id</Uni></CurVernWss></rt>"
        '<rt class="MoAffixAllomorph" guid="00000000-0000-0000-0000-000000000002">'
        '<Form><AUni ws="id">meng</AUni><AUni ws="id-fonipa">meŋ</AUni></Form>'
        '<MorphType><objsur guid="d7f713db-e8cf-11d3-9764-00c04f186933" t="r" /></MorphType></rt>'
        '<rt class="MoStemMsa" guid="00000000-0000-0000-0000-000000000003"></rt>'
        '<rt class="MoStemAllomorph" guid="00000000-0000-0000-0000-000000000004">'
        '<Form><AUni ws="id">pukul</AUni></Form></rt>'
    )
    fw.write_text('<?xml version="1.0" encoding="utf-8"?>\n<languageproject version="7000072">'
                  + rts + "</languageproject>\n", encoding="utf-8")
    cfg = tmp_path / "hc-config.xml"
    cfg.write_text(_config_with([({"ID": 2}, {"ID": 3}, "LexicalEntry"),
                                 ({"ID": 4}, {"ID": 3}, "LexicalEntry")]), encoding="utf-8")
    doc, _ = _lcm_ids().build(cfg, fw)
    assert doc["valid"] is True and doc["vernacular_ws"] == "id-fonipa"
    assert doc["ids"]["2"]["form"] == "meŋ"
    # No text in the default vernacular: no `form`, so the worker keeps the surface.
    assert "form" not in doc["ids"]["4"]
    assert "form" not in doc["ids"]["3"] and "forms" not in doc["ids"]["2"]


def test_zero_form_ids_and_infl_type_are_not_looked_up(tmp_path):
    doc, _ = _build(tmp_path, _RTS, [
        ({"ID": 0}, {"ID": 3, "InflTypeID": 0}, "LexicalEntry"),
        ({"ID": 4, "ID2": 0}, {"ID": 5}, "MorphologicalRule"),
    ])
    assert doc["valid"] is True and set(doc["ids"]) == {"3", "4", "5"}


@pytest.mark.parametrize("entries, bad", [
    ([({"ID": 3}, {"ID": 5}, "LexicalEntry")], "3"),                    # an MSA as a form
    ([({"ID": 2}, {"ID": 2}, "LexicalEntry")], "2"),                    # one id, two roles
    ([({"ID": 2}, {"ID": 40}, "LexicalEntry")], "40"),                  # past the last rt
    ([({"ID": 2}, {"ID": 3, "InflTypeID": 5}, "LexicalEntry")], "5"),   # not an infl type
    ([({"ID": "x7"}, {"ID": 3}, "LexicalEntry")], "x7"),                # not an integer
    ([({"ID": 2}, {"ID": 0}, "LexicalEntry")], "0"),                    # a 0 MSA
])
def test_any_unresolved_id_marks_the_whole_map_invalid(tmp_path, entries, bad):
    doc, _ = _build(tmp_path, _RTS, entries)
    assert doc["valid"] is False
    assert bad in doc["invalid_ids"]
    assert bad not in doc["ids"]


def test_source_that_moved_is_invalid(tmp_path):
    lcm_ids = _lcm_ids()
    fw = tmp_path / "P.fwdata"
    fw.write_text(_fwdata_with(_RTS), encoding="utf-8")
    st = fw.stat()
    cfg = tmp_path / "hc-config.xml"
    cfg.write_text(_config_with([({"ID": 2}, {"ID": 3}, "LexicalEntry")]), encoding="utf-8")
    doc, params = lcm_ids.build(cfg, fw, expected_key=(str(fw), st.st_size + 1, st.st_mtime_ns))
    assert doc["valid"] is False and doc["error"] == "source_changed" and params is None
    doc, _ = lcm_ids.build(cfg, fw, expected_key=(str(fw), st.st_size, st.st_mtime_ns))
    assert doc["valid"] is True


def test_unreadable_inputs_are_invalid_never_raise(tmp_path):
    lcm_ids = _lcm_ids()
    cfg = tmp_path / "hc-config.xml"
    cfg.write_text(_config_with([({"ID": 2}, {"ID": 3}, "LexicalEntry")]), encoding="utf-8")
    doc, params = lcm_ids.build(cfg, tmp_path / "missing.fwdata")
    assert doc["valid"] is False and doc["error"] == "read_error" and params is None
    (tmp_path / "bad.xml").write_text("<HermitCrabInput>", encoding="utf-8")
    doc, _ = lcm_ids.build(tmp_path / "bad.xml", tmp_path / "missing.fwdata")
    assert doc["valid"] is False and doc["error"] == "config_unparseable"


def test_read_returns_none_for_absent_or_foreign(tmp_path):
    lcm_ids = _lcm_ids()
    assert lcm_ids.read(tmp_path / "none.json") is None
    (tmp_path / "x.json").write_text('{"schema": "other"}', encoding="utf-8")
    assert lcm_ids.read(tmp_path / "x.json") is None
    (tmp_path / "y.json").write_text("{not json", encoding="utf-8")
    assert lcm_ids.read(tmp_path / "y.json") is None
    good = {"schema": lcm_ids.SCHEMA, "valid": True, "ids": {}, "invalid_ids": [],
            "error": None}
    (tmp_path / "z.json").write_text(json.dumps(good), encoding="utf-8")
    assert lcm_ids.read(tmp_path / "z.json") == good


def test_sidecar_module_imports_no_lcm():
    code = ("import sys; import flextoolsmcp.server.sandbox.lcm_ids; "
            "bad=[m for m in sys.modules if m.split('.')[0] in "
            "('flexicon','flexlibs','clr','pythonnet','SIL')]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True).stdout.strip()
    assert out == "[]"


class _IdConfigScript(EmulatedScript):
    """Generates, then replaces the config with one that references ids."""

    def __init__(self, config_text, touch=None):
        super().__init__()
        self.config_text = config_text
        self.touch = touch

    async def __call__(self, argv):
        code = await super().__call__(argv)
        _mode, params = _argv_params(argv)
        Path(params["ConfigOut"]).write_text(self.config_text, encoding="utf-8")
        if self.touch is not None:
            self.touch()
        return code


async def test_build_reads_an_explicit_id_source(
        sandbox_root, fake_project, fake_generator, tmp_path):
    cache = _cache()
    copy = tmp_path / "copy.fwdata"
    copy.write_text(_fwdata_with(_RTS), encoding="utf-8")
    runner = _IdConfigScript(_config_with([({"ID": 2}, {"ID": 3}, "LexicalEntry")]))
    entry = await _ensure(cache, fake_project, fake_generator, runner=runner,
                          id_source=copy)
    sidecar = json.loads(entry.lcm_ids_path.read_text(encoding="utf-8"))
    assert sidecar["valid"] is True and set(sidecar["ids"]) == {"2", "3"}
    # The copy's parameters, not the live file's.
    assert entry.hc_parameters["max_roots"] == 3
    inputs = cache.key_inputs(fake_project.fwdata, fake_generator.path)
    assert entry.key == cache.compute_key(inputs)  # neither addition is in the key


async def test_live_source_moving_during_build_gives_invalid_map(
        sandbox_root, fake_project, fake_generator):
    cache = _cache()

    def touch():
        text = fake_project.fwdata.read_text(encoding="utf-8")
        fake_project.fwdata.write_text(text + "\n", encoding="utf-8")

    runner = _IdConfigScript(_config_with([({"ID": 2}, {"ID": 3}, "LexicalEntry")]),
                             touch=touch)
    entry = await _ensure(cache, fake_project, fake_generator, runner=runner)
    sidecar = json.loads(entry.lcm_ids_path.read_text(encoding="utf-8"))
    assert sidecar["valid"] is False and sidecar["error"] == "source_changed"
    assert entry.hc_parameters is None and entry.meta["hc_parameters"] is None


def test_entry_predating_the_keys_reads_none(tmp_path):
    cache = _cache()
    entry = cache.CacheEntry(project="P", key="0" * 16, path=tmp_path, meta={"schema": "x"})
    assert entry.lcm_ids_path is None and entry.hc_parameters is None
