#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 T040 (FR-011, FR-016..FR-020, FR-023, FR-035, SC-004,
SC-008): `server/sandbox/client.py` -- the per-run SANDBOX client -- driven
through a REAL `ParseRunner._execute_run` against the fake `hc`, the fake
GenerateHCConfig and the real packaged `hcparse.ps1` (Windows only where the
script runs).

The API this file specifies
---------------------------
``sandbox.client``::

    SANDBOX_ROLE = "sandbox"          # the runner's worker_role for this spine
    POLL_INTERVAL_SECONDS = 0.1       # hc-stdout.txt is tailed this often
    WATCHDOG_GRACE_SECONDS = 30       # watchdog = TimeoutSeconds + this

    SandboxLaunch(fwdata_path, hc_path, generate_hc_config_path=None,
                  config_path=None, timeout_seconds=600,
                  generate_timeout_seconds=600, watchdog_grace_seconds=30,
                  check_engine=True, active_parser="HC", versions=None,
                  hc_invoke_argv=None)
        .from_value(SandboxLaunch | Mapping) -> SandboxLaunch  (unknown keys
        ignored; None values take the defaults)
        config_path None = the project cache (engine check + generation on a
        miss); a path = a named sandbox's hc-config.xml, no generation.

    SandboxClient(project_name, *, run_id, record, wordforms, launch)
        the worker-client interface the runner already calls:
        start(), parse_word(*, request_id, run_id, wordform, index_in_run, ...)
        -> {"parse": <data-model 6.4 parse section>}, cancel_run(run_id),
        is_running(), listen_to_run(run_id, cb), stop_listening(run_id),
        terminate(), aclose(); plus finalize() (fold run.json into
        meta.sandbox, write hc-output.txt, reconcile counters, delete the
        copy -- idempotent, called by the runner before any terminal stage).

    SandboxRunError(WorkerError) with .error_code and .facts.

    _parse_argv(launch, *, config, word_file, run_dir) -> list[str]
        the `-Mode Parse` argv (module-level; the watchdog test patches it).

``ParseRunner.start_run(..., worker_role=SANDBOX_ROLE, spine="sandbox",
sandbox={...}, sandbox_launch=SandboxLaunch | dict)`` builds a FRESH client
per run (never `WorkerPool.get`, F-13), kept on ``handle.sandbox_client``.
Terminal states:

  * completed -- one results.jsonl line per word (SC-004); a mid-list hc
    crash gives `error_no_output` for the word in flight and `not_reached`
    after it, never `not_parsed` (FR-018);
  * generation failed -> failure.error_code `parser_config_failed`, detail
    ParserConfigFailedDetail with `run_id` = the run;
  * hc could not load the config -> `parser_job_failed`, failure `crashed`,
    zero results, `sandbox/hc-stdout.txt` holding hc's `Load Error:` line;
  * timeout (the script's own or the Python watchdog) -> `parser_timeout`,
    detail fields in order timeout_seconds, words_completed, run_id, hint;
    only the completed words are in results.jsonl; the word in flight is
    named in meta.sandbox.hc (in_flight_index, in_flight_word) (SC-008);
  * cancel -> the existing `cancelled` state; the tree is killed, partial
    results kept.

After EVERY terminal path the `work/` root holds nothing (FR-011, R-11).
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import List

import pytest

from flextoolsmcp.server.parse.runner import ParseRunner
from flextoolsmcp.server.parse.stages import RunStage
from flextoolsmcp.server.sandbox import cache, engine, paths, workdir

PROJECT = "FakeProj"
RUN_WAIT = 90

GRAMMAR = {
    "language": "Fake Lang",
    "words": {
        "membaca": [[["mem", "ACT"], ["baca", "read"]]],
        "baca": [[["baca", "read"]], [["baca", "book"]]],
        "xyz": [],
        "q#": {"invalid_segment": 2},
        "-an": [[["-an", "NMLZ"]]],
    },
    "default": [],
}

TIMEOUT_FIELDS = ["timeout_seconds", "words_completed", "run_id", "hint"]


def client_mod():
    import importlib

    return importlib.import_module("flextoolsmcp.server.sandbox.client")


# ---------------------------------------------------------------------------
# Process helpers (Windows)
# ---------------------------------------------------------------------------


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


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
        stdin=subprocess.DEVNULL, capture_output=True, env=env, timeout=60,
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
    assert not alive, "a process is still running after the kill: %r" % alive


# ---------------------------------------------------------------------------
# Fixtures and drivers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_module_state():
    cache.reset_state()
    engine.clear_engine_cache()
    yield
    cache.reset_state()
    engine.clear_engine_cache()


@pytest.fixture
def env(tmp_path, sandbox_root, fake_hc, fake_generator, fake_project, monkeypatch):
    monkeypatch.setenv("FAKE_PYTHON", sys.executable)
    fake_generator.set(grammar=json.dumps(GRAMMAR))
    runner = ParseRunner(record_dir=tmp_path / "parse-runs", grace_window=0.0, stub=True)
    named = paths.sandbox_dir(PROJECT, "x") / "hc-config.xml"
    fake_hc.write_config(named, GRAMMAR)

    class Env:
        pass

    e = Env()
    e.tmp_path, e.root, e.hc, e.gen, e.project = tmp_path, sandbox_root, fake_hc, fake_generator, fake_project
    e.runner, e.named_config = runner, named

    def launch(*, named=True, timeout=30, **extra):
        value = {
            "fwdata_path": str(fake_project.fwdata),
            "generate_hc_config_path": str(fake_generator.path),
            "hc_path": str(fake_hc.path),
            "hc_invoke_argv": [str(fake_hc.path)],
            "config_path": str(e.named_config) if named else None,
            "timeout_seconds": timeout,
        }
        value.update(extra)
        return value

    e.launch = launch
    yield e
    # Never leak a sleeping fake into later tests.
    if sys.platform == "win32":
        for pid in processes_with(str(tmp_path)):
            _kill_tree(pid)


async def start(e, words, launch, *, config_kind="named_sandbox"):
    mod = client_mod()
    return await e.runner.start_run(
        project_name=PROJECT,
        wordforms=list(words),
        level="batch",
        scope_fingerprint={"scope_kind": "words", "engine": "HC",
                           "word_count": len(words), "limit": None, "truncated": False},
        engine_at_submission="HC",
        worker_role=mod.SANDBOX_ROLE,
        spine="sandbox",
        sandbox={"mode": "parse", "config_source": {"kind": config_kind},
                 "truncated_by_limit": False, "advisories": []},
        sandbox_launch=launch,
        grace_window=0.0,
    )


async def run(e, words, launch, **kw):
    handle = await start(e, words, launch, **kw)
    await asyncio.wait_for(handle.done.wait(), timeout=RUN_WAIT)
    return handle


def results(handle):
    return list(handle.record.iter_results())


def outcomes(handle):
    return [line["parse"]["outcome"] for line in results(handle)]


def meta_sandbox(handle):
    return handle.record.read_meta().sandbox or {}


def assert_work_empty():
    root = paths.work_root()
    left = list(root.iterdir()) if root.exists() else []
    assert left == [], "work/ must be empty after every terminal path (FR-011): %r" % left


async def wait_for(predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# Module surface (no script needed)
# ---------------------------------------------------------------------------


def test_module_constants():
    mod = client_mod()
    assert mod.SANDBOX_ROLE == "sandbox"
    assert mod.POLL_INTERVAL_SECONDS == pytest.approx(0.1)
    assert mod.WATCHDOG_GRACE_SECONDS == 30
    launch = mod.SandboxLaunch.from_value(
        {"fwdata_path": "a.fwdata", "hc_path": "hc.exe", "timeout_seconds": None,
         "hc_invoke_argv": ["hc.exe"], "unknown": 1})
    assert launch.timeout_seconds == 600
    assert launch.watchdog_grace_seconds == 30
    assert launch.config_path is None


def test_client_never_reads_the_script_stdout_for_data():
    """FR-023: run.json is the hand-off; the console is never parsed (AST)."""
    source = Path(client_mod().__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in ("communicate", "PIPE"), (
                "client.py must not pipe or communicate with the script (line %d)" % node.lineno)
            if node.attr in ("stdout", "stderr"):
                base = node.value
                ok = (isinstance(base, ast.Attribute) and base.attr == "subprocess") or (
                    isinstance(base, ast.Name) and base.id in ("subprocess", "sys"))
                assert ok, "client.py reads a process stream (line %d)" % node.lineno
        if isinstance(node, ast.keyword) and node.arg in ("stdout", "stderr"):
            value = node.value
            assert isinstance(value, ast.Attribute) and value.attr == "DEVNULL", (
                "the script's %s must go to DEVNULL (line %d)" % (node.arg, value.lineno))
        if isinstance(node, ast.Name):
            assert node.id != "PIPE"


async def test_watchdog_backstops_a_script_that_ignores_its_timeout(env, monkeypatch):
    """The Python watchdog fires at TimeoutSeconds + grace and kills the tree."""
    mod = client_mod()
    token = "watchdog-sleeper-%s" % env.tmp_path.name

    def sleeper_argv(launch, *, config, word_file, run_dir):
        return [sys.executable, "-c", "import time  # %s\ntime.sleep(120)" % token]

    monkeypatch.setattr(mod, "_parse_argv", sleeper_argv)
    started = time.monotonic()
    handle = await run(env, ["membaca", "xyz"], env.launch(timeout=1, watchdog_grace_seconds=1))
    elapsed = time.monotonic() - started

    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_timeout"
    detail = handle.failure.detail
    assert [k for k in detail if k != "error_code"] == TIMEOUT_FIELDS
    assert detail["words_completed"] == 0 and detail["run_id"] == handle.run_id
    assert detail["timeout_seconds"] == 1
    assert elapsed < 30, "the watchdog must fire near TimeoutSeconds + grace"
    assert meta_sandbox(handle)["hc"]["timed_out"] is True
    if sys.platform == "win32":
        assert_tree_killed(token)
    assert_work_empty()


async def test_client_exception_after_copy_still_deletes_it(env, monkeypatch):
    """The client's own finally deletes the copy on an unexpected exception."""
    made = []
    real_create = workdir.create

    def create(run_id, **kw):
        made.append(real_create(run_id, **kw))
        return made[-1]

    async def boom(*a, **kw):
        assert any(p.exists() for p in made), "the copy dir exists during generation"
        raise RuntimeError("boom")

    monkeypatch.setattr(workdir, "create", create)
    monkeypatch.setattr(cache, "ensure_entry", boom)
    handle = await run(env, ["membaca"], env.launch(named=False), config_kind="project_cache")
    assert handle.stage is RunStage.FAILED
    assert made and not any(p.exists() for p in made)
    assert meta_sandbox(handle)["copy"]["cleanup"] == "deleted"
    assert_work_empty()


# ---------------------------------------------------------------------------
# The real script (Windows)
# ---------------------------------------------------------------------------

win = pytest.mark.windows_only


@win
async def test_named_sandbox_run_completes_and_folds_run_json(env):
    words = ["membaca", "baca", "xyz", "q#", 'a"b\'c', "-an"]
    handle = await run(env, words, env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    lines = results(handle)
    assert [line["wordform"] for line in lines] == words
    assert [line["index"] for line in lines] == list(range(len(words)))
    assert outcomes(handle) == ["parsed", "parsed", "not_parsed", "invalid_segment",
                                "not_expressible", "parsed"]
    assert lines[0]["parse"]["analyses"][0]["rendered_morphs"] == ["mem", "baca"]
    assert lines[1]["parse"]["analysis_count"] == 2
    assert lines[3]["parse"]["position"] == 2
    assert "leading_dash_unverified" in lines[5]["parse"]["flags"]

    sb = meta_sandbox(handle)
    assert sb["mode"] == "parse" and sb["truncated_by_limit"] is False
    assert sb["versions"]["hcparse"]
    assert sb["hc"]["exit_code"] == 0 and sb["hc"]["timed_out"] is False
    assert sb["hc"]["counters"] == "ok"
    assert sb["copy"]["cleanup"] == "not_made"
    # hc-output.txt = hc-stdout.txt minus the load banner
    stdout = handle.record.read_sandbox_file("hc-stdout.txt")
    output = handle.record.read_sandbox_file("hc-output.txt")
    assert "loaded." in stdout and "loaded." not in output
    assert output.lstrip().startswith('Parsing "membaca"')
    assert handle.record.read_sandbox_file("run.json")
    assert handle.record.read_sandbox_file("generate-config.log")
    # A fresh client per run, outside the pool (F-13).
    assert handle.sandbox_client is not None
    assert env.runner.pool.active_workers() == []
    assert_work_empty()


@win
async def test_streaming_advances_words_completed_live(env):
    env.hc.set(word_delay_ms=250)
    words = ["membaca", "baca", "xyz"] * 4
    handle = await start(env, words, env.launch())
    seen = set()
    deadline = time.monotonic() + RUN_WAIT
    while not handle.is_terminal and time.monotonic() < deadline:
        seen.add(handle.words_completed)
        persisted = handle.record.read_meta().words_completed
        assert persisted <= handle.words_completed
        await asyncio.sleep(0.05)
    await asyncio.wait_for(handle.done.wait(), timeout=RUN_WAIT)
    assert handle.stage is RunStage.COMPLETED, handle.failure
    live = {n for n in seen if 0 < n < len(words)}
    assert len(live) >= 3, "words_completed must advance while hc runs: %r" % sorted(seen)
    assert len(results(handle)) == len(words)


@win
async def test_timeout_mid_list_is_parser_timeout_with_partial_results(env):
    env.hc.set(sleep_on_word=40, sleep_seconds=600)
    words = ["w%03d" % i for i in range(100)]
    handle = await run(env, words, env.launch(timeout=8))

    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_timeout"
    detail = handle.failure.detail
    assert [k for k in detail if k != "error_code"] == TIMEOUT_FIELDS
    assert detail["timeout_seconds"] == 8
    assert detail["words_completed"] == 40
    assert detail["run_id"] == handle.run_id
    assert detail["hint"].isascii() and "w040" not in detail["hint"]
    assert handle.words_completed == 40
    lines = results(handle)
    assert len(lines) == 40
    assert [line["wordform"] for line in lines] == words[:40]
    hc = meta_sandbox(handle)["hc"]
    assert hc["timed_out"] is True
    assert hc["in_flight_index"] == 40 and hc["in_flight_word"] == "w040"
    assert hc["counters"] == "unavailable_timeout"
    assert_tree_killed(str(env.named_config))
    assert_work_empty()


@win
async def test_cancel_kills_the_tree_and_keeps_partial_results(env):
    env.hc.set(sleep_on_word=3, sleep_seconds=600)
    words = ["membaca", "baca", "xyz", "membaca", "baca"]
    handle = await start(env, words, env.launch(timeout=120))
    assert await wait_for(lambda: handle.words_completed == 3, timeout=60)
    await env.runner.cancel_run(handle.run_id)
    await asyncio.wait_for(handle.done.wait(), timeout=30)
    assert handle.stage is RunStage.CANCELLED
    assert len(results(handle)) == 3
    assert_tree_killed(str(env.named_config))
    assert_work_empty()


@win
async def test_crash_mid_list_is_error_no_output_then_not_reached(env):
    env.hc.set(crash_on_word=2)
    words = ["membaca", "xyz", "baca", "xyz", "membaca"]
    handle = await run(env, words, env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    got = outcomes(handle)
    assert got == ["parsed", "not_parsed", "error_no_output", "not_reached", "not_reached"]
    assert "not_parsed" not in got[2:], "a word with no output is never not_parsed (FR-018)"
    assert results(handle)[2]["parse"]["analyses"] is None
    assert meta_sandbox(handle)["hc"]["exit_code"] not in (0, None)


@win
async def test_randomised_words_sent_equals_results(env):
    rng = random.Random(5)
    pool = ["membaca", "baca", "xyz", "q#", "-an", 'a"b\'c', "zzz", "don't", 'say "hi"']
    for trial in range(3):
        words = [rng.choice(pool) + ("" if rng.random() < 0.5 else str(i))
                 for i in range(rng.randint(5, 25))]
        words = list(dict.fromkeys(words))
        crash = rng.choice([None, rng.randrange(len(words))])
        env.hc.set(crash_on_word=crash)
        handle = await run(env, words, env.launch())
        assert handle.stage is RunStage.COMPLETED, (trial, handle.failure)
        lines = results(handle)
        assert [line["wordform"] for line in lines] == words, trial
        assert [line["index"] for line in lines] == list(range(len(words)))
        assert handle.words_completed == len(words)
        env.hc.set(crash_on_word=None)


@win
async def test_hc_load_error_is_a_crashed_job_with_zero_results(env):
    env.hc.set(mode="load_error", load_error="The morpher could not be built.")
    handle = await run(env, ["membaca", "baca"], env.launch())
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_job_failed"
    detail = handle.failure.detail
    assert detail["failure"] == "crashed"
    assert detail["run_id"] == handle.run_id
    assert detail["words_completed"] == 0 and detail["words_total"] == 2
    keys = [k for k in detail if k != "error_code"]
    assert keys == ["state_at_failure", "failure", "words_completed", "words_total",
                    "run_id", "log_path", "load_error"]
    assert detail["load_error"].startswith("Load Error:")
    assert results(handle) == []
    assert "Load Error:" in handle.record.read_sandbox_file("hc-stdout.txt")
    assert_work_empty()


@win
async def test_counter_divergence_is_recorded_not_resolved(env):
    env.hc.set(parse_stats="3,3,0,0")
    handle = await run(env, ["membaca", "xyz", "baca"], env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    divergences = handle.record.read_meta().counter_divergences
    assert any("successful" in text for text in divergences)
    assert outcomes(handle) == ["parsed", "not_parsed", "parsed"]


# -- the project-cache path (Generate mode) ----------------------------------


@win
async def test_cold_then_warm_generation(env):
    cold = await run(env, ["membaca"], env.launch(named=False), config_kind="project_cache")
    assert cold.stage is RunStage.COMPLETED, cold.failure
    sb = meta_sandbox(cold)
    assert sb["generation"]["reused_cache"] is False
    assert sb["config_source"]["kind"] == "project_cache" and sb["config_source"]["cache_key"]
    assert sb["copy"]["cleanup"] == "deleted" and sb["copy"]["bytes"] > 0
    assert_work_empty()

    warm = await run(env, ["membaca"], env.launch(named=False), config_kind="project_cache")
    assert warm.stage is RunStage.COMPLETED, warm.failure
    wsb = meta_sandbox(warm)
    assert wsb["generation"]["reused_cache"] is True
    assert wsb["generation"]["cache_key"] == sb["config_source"]["cache_key"]
    assert wsb["copy"]["cleanup"] == "not_made"
    log = warm.record.read_sandbox_file("generate-config.log")
    first, _, rest = log.partition("\n")
    assert sb["config_source"]["cache_key"] in first and "reuse" in first.lower()
    entry = cache.lookup(PROJECT, sb["config_source"]["cache_key"], touch=False)
    assert rest == entry.log_path.read_text(encoding="utf-8")
    assert_work_empty()


@win
async def test_generation_failure_is_parser_config_failed_with_run_id(env):
    env.gen.set(mode="crash")
    handle = await run(env, ["membaca"], env.launch(named=False), config_kind="project_cache")
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_config_failed"
    detail = handle.failure.detail
    assert detail["run_id"] == handle.run_id
    assert Path(detail["log_path"]) == handle.record.sandbox_path("generate-config.log")
    assert results(handle) == []
    assert_work_empty()


@win
async def test_two_concurrent_jobs_get_distinct_clients_and_copies(env, monkeypatch):
    env.gen.set(sleep_seconds=1)
    made = []
    real_create = workdir.create

    def create(run_id, **kw):
        made.append(real_create(run_id, **kw))
        return made[-1]

    monkeypatch.setattr(workdir, "create", create)
    a, b = await asyncio.gather(
        start(env, ["membaca"], env.launch(named=False), config_kind="project_cache"),
        start(env, ["baca"], env.launch(named=False), config_kind="project_cache"),
    )
    await asyncio.wait_for(asyncio.gather(a.done.wait(), b.done.wait()), timeout=RUN_WAIT)
    assert a.stage is RunStage.COMPLETED and b.stage is RunStage.COMPLETED
    assert a.sandbox_client is not b.sandbox_client
    assert len(made) == 2 and made[0] != made[1]
    assert env.runner.pool.active_workers() == []
    assert_work_empty()


# -- the terminal-path matrix: work/ is empty after every one (FR-011) --------


@win
@pytest.mark.parametrize("path", ["success", "generator_fail", "hc_load_fail",
                                  "timeout", "cancel_during_generation", "client_exception"])
async def test_work_is_empty_after_every_terminal_path(env, monkeypatch, path):
    launch = env.launch(named=False, timeout=6)
    words = ["membaca", "baca", "xyz"]
    expected = RunStage.COMPLETED
    if path == "generator_fail":
        env.gen.set(mode="crash")
        expected = RunStage.FAILED
    elif path == "hc_load_fail":
        env.hc.set(mode="load_error")
        expected = RunStage.FAILED
    elif path == "timeout":
        env.hc.set(sleep_on_word=1, sleep_seconds=600)
        expected = RunStage.FAILED
    elif path == "cancel_during_generation":
        env.gen.set(sleep_seconds=600)
        expected = RunStage.CANCELLED
    elif path == "client_exception":
        from flextoolsmcp.server.sandbox import classify

        def broken(*a, **kw):
            raise RuntimeError("client bug")

        monkeypatch.setattr(classify, "word_result_to_line", broken)
        expected = RunStage.FAILED

    handle = await start(env, words, launch, config_kind="project_cache")
    if path == "cancel_during_generation":
        root = paths.work_root()
        assert await wait_for(lambda: root.exists() and any(root.iterdir())), "copy dir made"
        assert await wait_for(lambda: bool(env.gen.invocations())), "generator started"
        await env.runner.cancel_run(handle.run_id)
    await asyncio.wait_for(handle.done.wait(), timeout=RUN_WAIT)
    assert handle.stage is expected, (path, handle.failure)
    assert_work_empty()
    if path == "cancel_during_generation":
        # The generator ran on the copy under work/, so its command line
        # names the work root: nothing may survive the cancel.
        assert_tree_killed(str(paths.work_root()))


# ---------------------------------------------------------------------------
# Test mode (T072, US4): `-Mode Test -AssertionFile`, assertion lines
# ---------------------------------------------------------------------------

CORPUS_ASSERTIONS = [
    {"word": "membaca", "expected": [[{"form": "mem", "gloss": "ACT"},
                                      {"form": "baca", "gloss": "read"}]]},   # pass
    {"word": "baca", "expected": [[{"form": "baca", "gloss": "read"}]]},      # new_ambiguity
    {"word": "xyz", "expected": []},                                          # pass (no parse)
    {"word": "zzz", "expected": [[{"form": "zzz", "gloss": "Z"}]]},           # regression
    {"word": "q#", "expected": []},                                           # error: invalid_segment
    {"word": 'a"b\'c', "expected": []},                                       # error: not_expressible
]


def write_corpus(e, assertions=CORPUS_ASSERTIONS):
    path = paths.corpus_path(PROJECT, "baseline")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "flextoolsmcp.hc-corpus/1", "name": "baseline", "project": PROJECT,
        "created_at": "2026-09-24T00:00:00Z", "assertions": assertions,
    }, ensure_ascii=False), encoding="utf-8")
    return path


async def run_corpus(e, corpus, launch, assertions=CORPUS_ASSERTIONS):
    words = [a["word"] for a in assertions]
    mod = client_mod()
    handle = await e.runner.start_run(
        project_name=PROJECT, wordforms=words, level="batch",
        scope_fingerprint={"scope_kind": "corpus", "engine": "HC", "word_count": len(words),
                           "limit": None, "truncated": False},
        engine_at_submission="HC", worker_role=mod.SANDBOX_ROLE, spine="sandbox",
        sandbox={"mode": "test", "config_source": {"kind": "named_sandbox"},
                 "corpus": {"name": "baseline", "assertion_count": len(words)},
                 "truncated_by_limit": False, "advisories": []},
        sandbox_launch=launch, grace_window=0.0,
    )
    await asyncio.wait_for(handle.done.wait(), timeout=RUN_WAIT)
    return handle


def test_launch_accepts_assertion_file_or_its_alias():
    mod = client_mod()
    a = mod.SandboxLaunch.from_value({"fwdata_path": "f", "hc_path": "h", "assertion_file": "c.json"})
    b = mod.SandboxLaunch.from_value({"fwdata_path": "f", "hc_path": "h", "corpus_path": "c.json"})
    assert a.assertion_file == b.assertion_file == "c.json"
    assert a.mode == "test"
    argv = mod._parse_argv(a, config="cfg.xml", word_file="w.txt", run_dir="rd")
    assert argv[argv.index("-Mode") + 1] == "Test"
    assert argv[argv.index("-AssertionFile") + 1] == "c.json"
    assert "-WordFile" not in argv
    plain = mod.SandboxLaunch.from_value({"fwdata_path": "f", "hc_path": "h"})
    assert plain.mode == "parse"


def test_launch_names_undeclared_keys_in_a_warning(caplog):
    """Pattern audit sweep 5: an unknown key is logged by name, never raised."""
    mod = client_mod()
    with caplog.at_level("WARNING", logger=mod.__name__):
        launch = mod.SandboxLaunch.from_value(
            {"fwdata_path": "f", "hc_path": "h", "surprise_key": 1, "corpus_path": "c.json"})
    assert launch.fwdata_path == "f"
    warned = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("surprise_key" in m for m in warned), warned
    assert not any("corpus_path" in m for m in warned), warned


def test_update_sandbox_never_writes_back_after_an_unreadable_read(tmp_path, monkeypatch, caplog):
    """Pattern audit sweep 6: a meta.json that stays unreadable skips the
    update (logged) instead of merging into {} and erasing meta.sandbox."""
    import types

    from flextoolsmcp.server.parse import record as record_mod

    mod = client_mod()
    monkeypatch.setattr(record_mod, "META_RETRY_DELAY_SECONDS", 0)
    rec = record_mod.RunRecord.create(
        project_name="P", words_total=0, record_dir=tmp_path / "runs", spine="sandbox",
        sandbox={"mode": "parse", "config_source": {"kind": "project_cache"},
                 "versions": {"hcparse": "5.0.0"}},
    )
    good = rec.meta_path.read_text(encoding="utf-8")
    calls = []
    real_read = record_mod.RunRecord.read_meta_strict

    def flaky_read(self):
        # Unreadable for the client's read; readable again for set_section's,
        # which is exactly the window where a {} merge would be written back.
        calls.append(1)
        if len(calls) == 1:
            raise record_mod.MetaUnreadable("meta.json held by a scanner")
        return real_read(self)

    monkeypatch.setattr(record_mod.RunRecord, "read_meta_strict", flaky_read)
    fake_self = types.SimpleNamespace(_record=rec, run_id=rec.run_id)
    with caplog.at_level("WARNING", logger=mod.__name__):
        mod.SandboxClient._update_sandbox(fake_self, hc={"exit_code": 0})
    assert rec.meta_path.read_text(encoding="utf-8") == good
    assert any("skipped" in r.getMessage() for r in caplog.records)
    # Readable again: the next update merges into the recorded section.
    mod.SandboxClient._update_sandbox(fake_self, hc={"exit_code": 0})
    section = rec.read_meta().sandbox
    assert section["config_source"] == {"kind": "project_cache"}
    assert section["hc"] == {"exit_code": 0}


def test_every_key_the_handler_passes_is_declared(monkeypatch):
    """Pattern audit sweep 5: `_sandbox_launch`'s keys all reach `SandboxLaunch`."""
    import types
    from dataclasses import fields

    from flextoolsmcp.server.handlers import parse as parse_handler

    mod = client_mod()
    monkeypatch.setattr(parse_handler, "_sandbox_fwdata_path", lambda project: Path("p.fwdata"))
    monkeypatch.setattr(parse_handler, "_sandbox_config_path",
                        lambda project, name: Path("sb") / name / "hc-config.xml")
    plan = types.SimpleNamespace(
        request=types.SimpleNamespace(sandbox="x", timeout_seconds=60),
        project_name="P",
        generator=types.SimpleNamespace(expected_path="ghc.exe"),
        hc=types.SimpleNamespace(path="hc.exe", invoke_argv=["hc.exe"]),
        corpus=types.SimpleNamespace(path=Path("c.json")),
    )
    keys = set(parse_handler._sandbox_launch(plan))
    declared = {f.name for f in fields(mod.SandboxLaunch)}
    assert keys <= declared, sorted(keys - declared)


@win
async def test_corpus_run_classifies_each_assertion_and_reconciles_stats_t(env):
    corpus = write_corpus(env)
    handle = await run_corpus(env, corpus, env.launch(assertion_file=str(corpus)))
    assert handle.stage is RunStage.COMPLETED, handle.failure
    lines = results(handle)
    assert [line["wordform"] for line in lines] == [a["word"] for a in CORPUS_ASSERTIONS]
    got = [(line["assertion"]["classification"], line["assertion"]["error_reason"])
           for line in lines]
    assert got == [("pass", None), ("new_ambiguity", None), ("pass", None),
                   ("regression", None), ("error", "invalid_segment"),
                   ("error", "not_expressible")]
    assert lines[1]["assertion"]["unexpected"] == [[{"form": "baca", "gloss": "book"}]]
    assert lines[3]["assertion"]["missing"] == [[{"form": "zzz", "gloss": "Z"}]]
    hc = meta_sandbox(handle)["hc"]
    assert hc["counters"] == "ok"
    assert hc["hc_counters"] == {"tests": 5, "passed": 2, "failed": 2, "error": 1}
    assert hc["counter_agreement"] is True
    assert meta_sandbox(handle)["corpus"] == {"name": "baseline", "assertion_count": 6}
    assert "Testing" in handle.record.read_sandbox_file("hc-output.txt")
    assert_work_empty()


@win
async def test_corpus_counter_divergence_is_recorded(env):
    corpus = write_corpus(env)
    env.hc.set(test_stats="5,5,0,0")
    handle = await run_corpus(env, corpus, env.launch(assertion_file=str(corpus)))
    assert handle.stage is RunStage.COMPLETED, handle.failure
    assert meta_sandbox(handle)["hc"]["counter_agreement"] is False
    assert any("passed" in t for t in handle.record.read_meta().counter_divergences)


@win
async def test_corpus_timeout_is_parser_timeout_with_counters_unavailable(env):
    corpus = write_corpus(env)
    env.hc.set(sleep_on_word=2, sleep_seconds=600)
    handle = await run_corpus(env, corpus, env.launch(assertion_file=str(corpus), timeout=6))
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_timeout"
    assert handle.failure.detail["words_completed"] == 2
    assert len(results(handle)) == 2
    hc = meta_sandbox(handle)["hc"]
    assert hc["counters"] == "unavailable_timeout"
    assert hc["in_flight_word"] == "xyz"
    assert_tree_killed(str(env.named_config))
    assert_work_empty()


@win
async def test_corpus_crash_gives_error_lines_never_a_classification(env):
    corpus = write_corpus(env)
    env.hc.set(crash_on_word=1)
    handle = await run_corpus(env, corpus, env.launch(assertion_file=str(corpus)))
    assert handle.stage is RunStage.COMPLETED, handle.failure
    reasons = [line["assertion"]["error_reason"] for line in results(handle)]
    assert reasons == [None, "error_no_output", "not_reached", "not_reached",
                       "not_reached", "not_expressible"]


# ---------------------------------------------------------------------------
# The soak (T083, US6): 30 runs, including killed ones
# ---------------------------------------------------------------------------

SOAK_KINDS = ("cold", "warm", "crash", "timeout", "cancel", "cancel_generation")


@win
async def test_soak_thirty_runs_leaves_no_copies_three_entries_and_retention(env):
    """After 30 runs of every terminal kind: work/ is empty, the project keeps
    at most `cache.DEFAULT_KEEP` (3) entries, and run retention keeps exactly
    the newest `retention.DEFAULT_RUNS_PER_PROJECT` (20) run directories."""
    from flextoolsmcp.server.parse import retention

    words = ["membaca", "baca", "xyz", "q#"]
    stamp = [time.time() - 10_000]

    def new_grammar_state():
        # A new fwdata mtime is a new cache key: a cold run.
        stamp[0] += 10
        os.utime(env.project.fwdata, (stamp[0], stamp[0]))

    handles = []
    for i in range(30):
        kind = SOAK_KINDS[i % len(SOAK_KINDS)]
        env.hc.set(sleep_on_word=None, sleep_seconds=None, crash_on_word=None)
        env.gen.set(sleep_seconds=None)
        timeout = 30
        if kind in ("cold", "cancel_generation"):
            new_grammar_state()
        if kind == "crash":
            env.hc.set(crash_on_word=1)
        elif kind == "timeout":
            env.hc.set(sleep_on_word=1, sleep_seconds=600)
            timeout = 4
        elif kind == "cancel":
            env.hc.set(sleep_on_word=2, sleep_seconds=600)
        elif kind == "cancel_generation":
            env.gen.set(sleep_seconds=600)
        before = len(env.gen.invocations())
        handle = await start(env, words, env.launch(named=False, timeout=timeout),
                             config_kind="project_cache")
        if kind == "cancel":
            assert await wait_for(lambda h=handle: h.words_completed == 2, timeout=60), i
            await env.runner.cancel_run(handle.run_id)
        elif kind == "cancel_generation":
            assert await wait_for(lambda b=before: len(env.gen.invocations()) > b, timeout=60), i
            await env.runner.cancel_run(handle.run_id)
        await asyncio.wait_for(handle.done.wait(), timeout=RUN_WAIT)
        expected = {"cold": RunStage.COMPLETED, "warm": RunStage.COMPLETED,
                    "crash": RunStage.COMPLETED, "timeout": RunStage.FAILED,
                    "cancel": RunStage.CANCELLED,
                    "cancel_generation": RunStage.CANCELLED}[kind]
        assert handle.stage is expected, (i, kind, handle.failure)
        if kind in ("cold", "warm", "crash"):
            assert len(results(handle)) == len(words), (i, kind)
        assert_work_empty()
        handles.append(handle)

    assert_work_empty()
    cache_dir = paths.config_cache_dir(PROJECT)
    entries = [p for p in cache_dir.iterdir() if p.is_dir()] if cache_dir.exists() else []
    assert all(len(p.name) == 16 for p in entries), "no .partial survives: %r" % entries
    assert 1 <= len(entries) <= cache.DEFAULT_KEEP, entries

    record_dir = env.tmp_path / "parse-runs"
    kept = sorted(p.name for p in record_dir.iterdir() if p.is_dir())
    newest = sorted(h.run_id for h in handles[-retention.DEFAULT_RUNS_PER_PROJECT:])
    assert kept == newest, "retention keeps exactly the newest 20 runs"
    assert_tree_killed(str(paths.work_root()))
    assert_tree_killed(str(env.tmp_path / "parse-runs"))


# ---------------------------------------------------------------------------
# Attribution hardening (SC-004, FR-018): a block is attributed to a sent
# word only when hc's header names that word. Driven through the real
# runner with a stand-in script (patched `_parse_argv`) that writes the
# script's hand-off files verbatim, so these run on every platform.
# ---------------------------------------------------------------------------


def _stand_in_script(monkeypatch, files, exit_code=0):
    """Patch `_parse_argv` to a Python one-liner writing `files` into RunDir."""
    mod = client_mod()
    payload = json.dumps(files, ensure_ascii=True)

    def argv(launch, *, config, word_file, run_dir):
        code = (
            "import json, os, sys\n"
            "files = json.loads(sys.argv[1]); run_dir = sys.argv[2]\n"
            "order = ['dispatch.json', 'hc-script.txt', 'hc-stdout.txt', 'run.json']\n"
            "for name in order:\n"
            "    if name in files:\n"
            "        open(os.path.join(run_dir, name), 'w', encoding='utf-8', newline='')"
            ".write(files[name])\n"
            "sys.exit(%d)\n" % exit_code
        )
        return [sys.executable, "-c", code, payload, str(run_dir)]

    monkeypatch.setattr(mod, "_parse_argv", argv)


def _hand_off(words, blocks, *, script_words=None):
    items = [{"index": i, "word": w, "sent": True, "line": 'parse "%s"' % w,
              "reason": None, "flags": []} for i, w in enumerate(words)]
    script_lines = ['parse "%s"' % w for w in (words if script_words is None else script_words)]
    stdout = ['Reading configuration file "hc-config.xml"... done.',
              "Compiling rules... done.", "Fake Lang loaded.", ""]
    for w in blocks:
        stdout += ['Parsing "%s"' % w, "No valid parses.", "Parse time: 0ms", ""]
    stdout += ["# of parses: %d, successful: 0, failed: %d, error: 0" % (len(blocks), len(blocks)), ""]
    return {
        "dispatch.json": json.dumps({"schema": "flextoolsmcp.hc-dispatch/1", "mode": "parse",
                                     "items": items}, ensure_ascii=False),
        "hc-script.txt": "\n".join(script_lines + ["stats -p"]) + "\n",
        "hc-stdout.txt": "\r\n".join(stdout) + "\r\n",
        "run.json": json.dumps({"schema": "flextoolsmcp.hcparse-run/1", "hcparse_version": "5.0.0",
                                "mode": "parse", "exit_code": 0,
                                "hc": {"exit_code": 0, "timed_out": False, "killed": False,
                                       "in_flight_index": None, "stdout_bom": False},
                                "items": items}),
    }


async def test_a_block_naming_another_word_is_never_shifted_onto_it(env, monkeypatch):
    """hc skipped `b`: its block, and every later one, is not attributed."""
    words = ["a", "b", "c", "d"]
    _stand_in_script(monkeypatch, _hand_off(words, ["a", "c", "d"]))
    handle = await run(env, words, env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    lines = results(handle)
    assert [line["wordform"] for line in lines] == words
    assert [line["parse"]["outcome"] for line in lines] == [
        "not_parsed", "error_no_output", "error_no_output", "error_no_output"]
    assert "attribution_mismatch" not in lines[0]["parse"]["flags"]
    assert all("attribution_mismatch" in line["parse"]["flags"] for line in lines[1:])
    notes = handle.record.read_meta().counter_divergences
    assert any("attribution" in n.lower() and "dispatch index 1" in n for n in notes)
    assert not any('"c"' in n or "'c'" in n for n in notes), "words stay in data fields"
    mismatch = meta_sandbox(handle)["hc"]["attribution_mismatch"]
    assert mismatch == {"index": 1, "sent_word": "b", "hc_word": "c"}
    assert 'Parsing "c"' in handle.record.read_sandbox_file("hc-output.txt")
    assert_work_empty()


async def test_an_nfc_equivalent_header_is_the_same_word(env, monkeypatch):
    composed, decomposed = "été", "été"
    words = [composed, "x"]
    _stand_in_script(monkeypatch, _hand_off(words, [decomposed, "x"]))
    handle = await run(env, words, env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    assert outcomes(handle) == ["not_parsed", "not_parsed"]
    assert "attribution_mismatch" not in (meta_sandbox(handle).get("hc") or {})


async def test_script_commands_must_equal_sent_items(env, monkeypatch):
    """dispatch.json says 4 sent, hc-script.txt holds 3: failed, nothing attributed."""
    words = ["a", "b", "c", "d"]
    _stand_in_script(monkeypatch, _hand_off(words, ["a", "c", "d"],
                                            script_words=["a", "c", "d"]))
    handle = await run(env, words, env.launch())
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_job_failed"
    assert handle.failure.detail["failure"] == "crashed"
    assert handle.failure.detail["log_path"].endswith("hc-script.txt")
    assert results(handle) == []
    assert meta_sandbox(handle)["hc"]["dispatch_mismatch"] == {"sent": 4, "script_commands": 3}
    assert_work_empty()
