#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 re-plan T102 (FR-011, FR-016..FR-020, FR-035, FR-038,
FR-047, FR-050, SC-004, SC-008): `server/sandbox/client.py` -- the per-run
SANDBOX client -- driven through a REAL `ParseRunner._execute_run` against a
real `--stub --sandbox` parse worker process (contracts/sandbox-worker.md).

The stub worker is `_SandboxBackend` with only its two engine methods
replaced: `--config` is read as a JSON script (see `_StubSandboxBackend`),
so everything else -- the id map, parameters, shaping, outcome shapes, the
wire protocol and `main()`'s routing -- is production code.

What this file pins
-------------------
  * completed -- one results.jsonl line per word (SC-004); the summary
    counts are the direct sum of the per-word lines (FR-017);
  * a worker that dies mid-list -> `error_no_output` for the word in flight,
    `not_reached` after it, never `not_parsed`; the run completes (FR-018);
  * a config that will not load -> `parser_job_failed`/`engine_unavailable`,
    zero results, the exception text in `worker-stderr.txt` (FR-016);
  * an id map recorded invalid -> `parser_job_failed`/`id_map_invalid`
    BEFORE any worker is spawned; no sidecar -> no `--id-map` and the
    `shaping_not_applied` advisory (FR-050, contracts/tools.md 3 and 5.1);
  * timeout -> the watchdog kills the worker, `parser_timeout` with the
    completed words kept and the word in flight named (FR-020, SC-008);
  * cancel -> the existing `cancelled` state, partial results kept;
  * `meta.sandbox` carries `parser_parameters`, `parameters_applied`,
    `parameters_source`, `engine_version` and `shaping` (FR-047, FR-050);
  * `hc_stdout` / `hc_output` are served from `worker-stderr.txt` and a
    rendered `hc-output.txt` (FR-038);
  * the client never builds a message a sandbox worker refuses (D1).

The project-cache path (Generate mode through the fake GenerateHCConfig) is
Windows-only, like the fake it drives. After EVERY terminal path the
`work/` root holds nothing (FR-011, R-11).
"""

from __future__ import annotations

import ast
import asyncio
import json
import time
from pathlib import Path

import pytest

from flextoolsmcp.server.parse.runner import ParseRunner
from flextoolsmcp.server.parse.stages import RunStage
from flextoolsmcp.server.sandbox import cache, classify, engine, lcm_ids, paths, workdir

PROJECT = "FakeProj"
SANDBOX = "x"
RUN_WAIT = 90

#: The stub engine's script (worker_main._StubSandboxBackend).
SCRIPT = {
    "words": {
        "membaca": [[{"form": "mem", "gloss": "ACT", "form_id": 11, "msa_id": 101},
                     {"form": "baca", "gloss": "read", "form_id": 10, "msa_id": 100}]],
        "baca": [[{"form": "baca", "gloss": "read", "form_id": 10, "msa_id": 100}],
                 [{"form": "baca", "gloss": "book", "form_id": 12, "msa_id": 102}]],
        "tebak": [[{"form": "tebak", "gloss": "tebak", "guessed": True,
                    "form_id": 10, "msa_id": 100}]],
        "xyz": [],
        "q#": {"invalid_segment": 1},
        "boom": {"error": "the engine threw"},
    },
}

#: A valid sidecar covering every id the script uses.
IDS = {
    "10": {"guid": "g10", "class": "MoStemAllomorph", "role": "form",
           "morph_type_guid": "d7f713e5-e8cf-11d3-9764-00c04f186933"},
    "11": {"guid": "g11", "class": "MoAffixAllomorph", "role": "form",
           "morph_type_guid": "d7f713db-e8cf-11d3-9764-00c04f186933"},
    "12": {"guid": "g12", "class": "MoStemAllomorph", "role": "form",
           "morph_type_guid": "d7f713e5-e8cf-11d3-9764-00c04f186933"},
    "100": {"guid": "m100", "class": "MoStemMsa", "role": "msa"},
    "101": {"guid": "m101", "class": "MoInflAffMsa", "role": "msa"},
    "102": {"guid": "m102", "class": "MoStemMsa", "role": "msa"},
}

TIMEOUT_FIELDS = ["timeout_seconds", "words_completed", "run_id", "hint"]
JOB_FAILED_FIELDS = ["state_at_failure", "failure", "words_completed", "words_total",
                     "run_id", "log_path"]


def client_mod():
    import importlib

    return importlib.import_module("flextoolsmcp.server.sandbox.client")


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


class Env:
    pass


@pytest.fixture
def env(tmp_path, sandbox_root, fake_project):
    e = Env()
    e.tmp_path, e.root, e.project = tmp_path, sandbox_root, fake_project
    e.runner = ParseRunner(record_dir=tmp_path / "parse-runs", grace_window=0.0, stub=True)
    e.sandbox_dir = paths.sandbox_dir(PROJECT, SANDBOX)
    e.named_config = e.sandbox_dir / "hc-config.xml"

    def script(value=None, **extra):
        body = dict(SCRIPT if value is None else value)
        body.update(extra)
        e.named_config.parent.mkdir(parents=True, exist_ok=True)
        e.named_config.write_text(json.dumps(body), encoding="utf-8")

    def sidecar(valid=True, ids=None, invalid_ids=()):
        path = e.sandbox_dir / lcm_ids.LCM_IDS_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": lcm_ids.SCHEMA, "valid": valid,
            "ids": IDS if ids is None else ids, "invalid_ids": list(invalid_ids),
        }), encoding="utf-8")
        return path

    def launch(*, named=True, timeout=30, **extra):
        value = {
            "fwdata_path": str(fake_project.fwdata),
            "config_path": str(e.named_config) if named else None,
            "sandbox_name": SANDBOX if named else None,
            "timeout_seconds": timeout,
            "worker_stub": True,
        }
        value.update(extra)
        return value

    e.script, e.sidecar, e.launch = script, sidecar, launch
    script()
    return e


async def start(e, words, launch, *, config_kind="named_sandbox", mode="parse", extra=None):
    mod = client_mod()
    sandbox = {"mode": mode, "config_source": {"kind": config_kind},
               "truncated_by_limit": False, "advisories": []}
    sandbox.update(extra or {})
    return await e.runner.start_run(
        project_name=PROJECT,
        wordforms=list(words),
        level="batch",
        scope_fingerprint={"scope_kind": "words", "engine": "HC",
                           "word_count": len(words), "limit": None, "truncated": False},
        engine_at_submission="HC",
        worker_role=mod.SANDBOX_ROLE,
        spine="sandbox",
        sandbox=sandbox,
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


class SpawnSpy:
    """Wraps the client's `ParseWorkerClient` to record each spawn's argv."""

    def __init__(self, monkeypatch, *, boom=False):
        mod = client_mod()
        real = mod.ParseWorkerClient
        self.spawns = []

        def factory(*args, **kwargs):
            self.spawns.append(kwargs.get("sandbox"))
            if boom:
                raise AssertionError("no worker may be spawned on this path")
            return real(*args, **kwargs)

        monkeypatch.setattr(mod, "ParseWorkerClient", factory)

    @property
    def argv(self):
        assert self.spawns, "no worker was spawned"
        return self.spawns[-1].argv()


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_constants_and_launch_defaults():
    mod = client_mod()
    assert mod.SANDBOX_ROLE == "sandbox"
    assert mod.PARAMETERS_SOURCES == ("cache", "live_project", "flex_defaults")
    launch = mod.SandboxLaunch.from_value({"fwdata_path": "a.fwdata", "timeout_seconds": None})
    assert launch.timeout_seconds == mod.DEFAULT_TIMEOUT_SECONDS == 600
    assert launch.config_path is None and launch.named is False
    assert launch.mode == "parse"
    with pytest.raises(ValueError):
        mod.SandboxLaunch.from_value({"config_path": "c.xml"})


def test_launch_accepts_assertion_file_or_its_alias():
    mod = client_mod()
    a = mod.SandboxLaunch.from_value({"fwdata_path": "f", "assertion_file": "c.json"})
    b = mod.SandboxLaunch.from_value({"fwdata_path": "f", "corpus_path": "c.json"})
    assert a.assertion_file == b.assertion_file == "c.json"
    assert a.mode == b.mode == "test"


def test_launch_names_undeclared_keys_in_a_warning(caplog):
    """Pattern audit sweep 5: an unknown key is logged by name, never raised."""
    mod = client_mod()
    with caplog.at_level("WARNING", logger=mod.__name__):
        launch = mod.SandboxLaunch.from_value(
            {"fwdata_path": "f", "hc_path": "h", "corpus_path": "c.json"})
    assert launch.fwdata_path == "f"
    warned = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any("hc_path" in m for m in warned), warned
    assert not any("corpus_path" in m for m in warned), warned


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
        corpus=types.SimpleNamespace(path=Path("c.json")),
    )
    launch = parse_handler._sandbox_launch(plan)
    declared = {f.name for f in fields(mod.SandboxLaunch)}
    assert set(launch) <= declared, sorted(set(launch) - declared)
    assert "hc_path" not in launch and "hc_invoke_argv" not in launch
    assert launch["sandbox_name"] == "x"


def test_client_never_builds_a_message_a_sandbox_worker_refuses():
    """D1: refusal is the worker's second line of defense; this is the first.

    The client calls only `start`, `parse_word` (batch, never
    `restricted_to`), `terminate`, `aclose` and the listener hooks.
    """
    source = Path(client_mod().__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    refused = {"resolve", "engine_check", "resolve_scope", "parser_parameters",
               "agent_probe", "filing_gate", "filing_preview", "filing_setup",
               "filing_commit"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in refused, (
                "client.py calls %s (line %d)" % (node.func.attr, node.lineno))
            if node.func.attr == "parse_word":
                keywords = {k.arg for k in node.keywords}
                assert "restricted_to" not in keywords, node.lineno


def test_render_results_reads_each_line():
    mod = client_mod()
    lines = [
        classify.worker_parse_to_line(0, "membaca", {"outcome": "parsed", "analyses": [
            {"morphs": [{"form": "mem", "gloss": "ACT"},
                        {"form": "baca", "gloss": "read", "guessed": True}]}]}),
        classify.worker_parse_to_line(1, "q#", {"outcome": "invalid_segment", "position": 1}),
        classify.placeholder_line(2, "zz", classify.OUTCOME_NOT_REACHED),
    ]
    text = mod.render_results(lines)
    assert text.splitlines() == [
        "[1] membaca: parsed",
        "    mem ACT  baca read?",
        "[2] q#: invalid_segment at position 2",
        "[3] zz: not_reached",
    ]
    assert mod.render_results([]) == ""


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
        calls.append(1)
        if len(calls) == 1:
            raise record_mod.MetaUnreadable("meta.json held by a scanner")
        return real_read(self)

    monkeypatch.setattr(record_mod.RunRecord, "read_meta_strict", flaky_read)
    fake_self = types.SimpleNamespace(_record=rec, run_id=rec.run_id)
    with caplog.at_level("WARNING", logger=mod.__name__):
        mod.SandboxClient._update_sandbox(fake_self, worker={"exit_code": 0})
    assert rec.meta_path.read_text(encoding="utf-8") == good
    assert any("skipped" in r.getMessage() for r in caplog.records)
    mod.SandboxClient._update_sandbox(fake_self, worker={"exit_code": 0})
    section = rec.read_meta().sandbox
    assert section["config_source"] == {"kind": "project_cache"}
    assert section["worker"] == {"exit_code": 0}


# ---------------------------------------------------------------------------
# A named-sandbox run through the real stub worker
# ---------------------------------------------------------------------------


async def test_named_run_completes_with_one_line_per_word(env, monkeypatch):
    spy = SpawnSpy(monkeypatch)
    words = ["membaca", "baca", "xyz", "q#", "boom", "tebak"]
    handle = await run(env, words, env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    lines = results(handle)
    assert [line["wordform"] for line in lines] == words
    assert [line["index"] for line in lines] == list(range(len(words)))
    assert outcomes(handle) == ["parsed", "parsed", "not_parsed", "invalid_segment",
                                "error_no_output", "parsed"]
    assert lines[0]["parse"]["analyses"][0]["rendered_morphs"] == ["mem", "baca"]
    assert lines[1]["parse"]["analysis_count"] == 2
    assert lines[3]["parse"]["position"] == 2        # 0-based 1 -> 1-based 2
    assert "the engine threw" in lines[4]["parse"]["error_message"]
    assert lines[5]["parse"]["analyses"][0]["guessed"] is True

    # The spawn: a --sandbox worker on the named config, never pooled (F-13).
    argv = spy.argv
    assert argv[:3] == ["--sandbox", "--config", str(env.named_config)]
    assert "--named-sandbox" in argv and "--hc-params" in argv
    assert "--id-map" not in argv, "no sidecar -> no --id-map (FR-050)"
    assert handle.sandbox_client is not None
    assert env.runner.pool.active_workers() == []

    sb = meta_sandbox(handle)
    assert sb["worker"]["counters"] == "ok" and sb["worker"]["timed_out"] is False
    assert sb["worker"]["exit_code"] == 0
    # FR-017: the counts are the direct sum of the recorded lines.
    tally = classify.tally_outcomes(lines)
    assert sb["worker"]["engine_counters"] == classify.parse_counters_from(tally).to_dict()
    assert sb["worker"]["counter_agreement"] is True
    assert sb["copy"]["cleanup"] == "not_made"
    assert sb["engine_version"] == "stub"
    assert sb["shaping"] == {"applied": False, "id_map": "absent"}
    assert "shaping_not_applied" in sb["advisories"]
    assert sb["parameters_source"] == "flex_defaults"
    assert sb["parser_parameters"] == engine.HC_PARAMETER_DEFAULTS
    assert "max_alternatives" not in sb["parameters_applied"]

    output = handle.record.read_sandbox_file("hc-output.txt")
    assert output.startswith("[1] membaca: parsed\n    mem ACT  baca read\n")
    assert "[4] q#: invalid_segment at position 2" in output
    assert handle.record.read_sandbox_file("run.json")
    assert handle.record.read_sandbox_file("generate-config.log").startswith(
        "No generation ran for this run")
    params = json.loads(handle.record.read_sandbox_file("hc-params.json"))
    assert params == engine.HC_PARAMETER_DEFAULTS
    assert_work_empty()


async def test_a_valid_sidecar_is_passed_and_shaping_applies(env, monkeypatch):
    spy = SpawnSpy(monkeypatch)
    sidecar = env.sidecar()
    handle = await run(env, ["membaca", "baca"], env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    argv = spy.argv
    assert argv[argv.index("--id-map") + 1] == str(sidecar)
    sb = meta_sandbox(handle)
    assert sb["shaping"] == {"applied": True, "id_map": "valid"}
    assert "shaping_not_applied" not in sb["advisories"]
    assert outcomes(handle) == ["parsed", "parsed"]


async def test_an_id_absent_from_the_map_drops_the_analysis(env):
    """Rule (d), end to end: `baca`'s second analysis uses form 12."""
    ids = {k: v for k, v in IDS.items() if k != "12"}
    env.sidecar(ids=ids)
    handle = await run(env, ["baca"], env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    line = results(handle)[0]
    assert line["parse"]["analysis_count"] == 1
    assert line["parse"]["analyses"][0]["morphs"][0]["gloss"] == "read"


async def test_an_invalid_sidecar_is_refused_before_any_spawn(env, monkeypatch):
    """contracts/tools.md section 3: the check order refuses first."""
    spy = SpawnSpy(monkeypatch, boom=True)
    env.sidecar(valid=False, invalid_ids=["77"])
    handle = await run(env, ["membaca"], env.launch())
    assert spy.spawns == [], "a worker was spawned against an invalid sidecar"
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_job_failed"
    detail = handle.failure.detail
    assert [k for k in detail if k != "error_code"] == JOB_FAILED_FIELDS
    assert detail["failure"] == "id_map_invalid"
    assert detail["words_completed"] == 0 and detail["run_id"] == handle.run_id
    assert "77" in handle.failure.message
    assert meta_sandbox(handle)["shaping"] == {"applied": False, "id_map": "invalid"}
    assert results(handle) == []
    assert_work_empty()


async def test_an_unreadable_sidecar_is_invalid_not_absent(env, monkeypatch):
    spy = SpawnSpy(monkeypatch, boom=True)
    (env.sandbox_dir / lcm_ids.LCM_IDS_NAME).write_text("{not json", encoding="utf-8")
    handle = await run(env, ["membaca"], env.launch())
    assert spy.spawns == []
    assert handle.failure.detail["failure"] == "id_map_invalid"


async def test_an_unloadable_config_is_engine_unavailable_with_zero_results(env):
    env.script({"load_fail": "The morpher could not be built."})
    handle = await run(env, ["membaca", "baca"], env.launch())
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_job_failed"
    detail = handle.failure.detail
    assert [k for k in detail if k != "error_code"] == JOB_FAILED_FIELDS
    assert detail["failure"] == "engine_unavailable"
    assert detail["words_completed"] == 0 and detail["words_total"] == 2
    assert detail["log_path"].endswith("worker-stderr.txt")
    assert "The morpher could not be built." in handle.failure.message
    assert results(handle) == []
    # hc_stdout's file carries the load exception's text (FR-038).
    assert "The morpher could not be built." in handle.record.read_sandbox_file(
        "worker-stderr.txt")
    assert_work_empty()


async def test_load_errors_become_the_grammar_load_errors_advisory(env):
    env.script(SCRIPT, load_errors=[{"type": "InvalidAffixProcess", "id": "g11",
                                     "message": "bad rule"}])
    handle = await run(env, ["membaca"], env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    sb = meta_sandbox(handle)
    assert "grammar_load_errors" in sb["advisories"]
    assert sb["generation"]["engine_load_errors"] == [
        {"kind": "engine_load", "line": "InvalidAffixProcess (g11): bad rule"}]


async def test_a_worker_crash_mid_list_is_error_no_output_then_not_reached(env):
    env.script(SCRIPT, words={**SCRIPT["words"], "die": {"crash": 3}})
    words = ["membaca", "xyz", "die", "baca", "membaca"]
    handle = await run(env, words, env.launch())
    assert handle.stage is RunStage.COMPLETED, handle.failure
    got = outcomes(handle)
    assert got == ["parsed", "not_parsed", "error_no_output", "not_reached", "not_reached"]
    assert results(handle)[2]["parse"]["analyses"] is None
    assert handle.words_completed == len(words)
    sb = meta_sandbox(handle)
    assert sb["worker"]["exit_code"] not in (0, None)
    tally = classify.tally_outcomes(results(handle))
    assert sb["worker"]["engine_counters"] == classify.parse_counters_from(tally).to_dict()
    assert "word 3" in handle.record.read_sandbox_file("worker-stderr.txt")


async def test_timeout_kills_the_worker_and_keeps_completed_words(env):
    env.script(SCRIPT, words={**SCRIPT["words"], "slow": {"sleep": 60}})
    words = ["membaca", "baca", "slow", "xyz"]
    started = time.monotonic()
    handle = await run(env, words, env.launch(timeout=3))
    assert time.monotonic() - started < 30, "the watchdog fires near timeout_seconds"
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_timeout"
    detail = handle.failure.detail
    assert [k for k in detail if k != "error_code"] == TIMEOUT_FIELDS
    assert detail["timeout_seconds"] == 3
    assert detail["words_completed"] == 2 and detail["run_id"] == handle.run_id
    assert detail["hint"].isascii() and "slow" not in detail["hint"]
    assert [line["wordform"] for line in results(handle)] == words[:2]
    worker = meta_sandbox(handle)["worker"]
    assert worker["timed_out"] is True and worker["killed"] is True
    assert worker["in_flight_index"] == 2 and worker["in_flight_word"] == "slow"
    assert worker["counters"] == "unavailable_timeout"
    assert handle.sandbox_client.is_running() is False
    assert_work_empty()


async def test_cancel_kills_the_worker_and_keeps_partial_results(env):
    env.script(SCRIPT, words={**SCRIPT["words"], "slow": {"sleep": 60}})
    words = ["membaca", "baca", "slow", "xyz"]
    handle = await start(env, words, env.launch(timeout=120))
    assert await wait_for(lambda: handle.words_completed == 2, timeout=60)
    await env.runner.cancel_run(handle.run_id)
    await asyncio.wait_for(handle.done.wait(), timeout=30)
    assert handle.stage is RunStage.CANCELLED
    assert len(results(handle)) == 2
    assert handle.sandbox_client.is_running() is False
    assert meta_sandbox(handle)["worker"]["counters"] == "unavailable"
    assert_work_empty()


async def test_parameters_come_from_the_originating_project(env, monkeypatch):
    """FR-047 source 2 for a named sandbox: a stream read of its origin."""
    monkeypatch.setattr(engine, "read_parameters",
                        lambda fwdata: {**engine.HC_PARAMETER_DEFAULTS, "max_roots": 4})
    handle = await run(env, ["membaca"], env.launch(
        origin_fwdata_path=str(env.project.fwdata)))
    assert handle.stage is RunStage.COMPLETED, handle.failure
    sb = meta_sandbox(handle)
    assert sb["parameters_source"] == "live_project"
    assert sb["parser_parameters"]["max_roots"] == 4
    assert "max_roots" in sb["parameters_applied"]


async def test_an_unreadable_origin_falls_back_to_flex_defaults(env, monkeypatch):
    monkeypatch.setattr(engine, "read_parameters", lambda fwdata: None)
    handle = await run(env, ["membaca"], env.launch(origin_fwdata_path="gone.fwdata"))
    sb = meta_sandbox(handle)
    assert sb["parameters_source"] == "flex_defaults"
    assert "could not be read" in sb["parameters_note"]


# ---------------------------------------------------------------------------
# Test mode (US4): assertion lines classified from structured analyses
# ---------------------------------------------------------------------------

CORPUS_ASSERTIONS = [
    {"word": "membaca", "expected": [[{"form": "mem", "gloss": "ACT"},
                                      {"form": "baca", "gloss": "read"}]]},   # pass
    {"word": "baca", "expected": [[{"form": "baca", "gloss": "read"}]]},      # new_ambiguity
    {"word": "xyz", "expected": []},                                          # pass (no parse)
    {"word": "zzz", "expected": [[{"form": "zzz", "gloss": "Z"}]]},           # regression
    {"word": "q#", "expected": []},                                           # error
]


def write_corpus(assertions=CORPUS_ASSERTIONS):
    path = paths.corpus_path(PROJECT, "baseline")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "flextoolsmcp.hc-corpus/1", "name": "baseline", "project": PROJECT,
        "created_at": "2026-09-24T00:00:00Z", "assertions": assertions,
    }, ensure_ascii=False), encoding="utf-8")
    return path


async def test_corpus_run_classifies_each_assertion(env):
    env.script(SCRIPT, words={**SCRIPT["words"], "zzz": []})
    corpus = write_corpus()
    words = [a["word"] for a in CORPUS_ASSERTIONS]
    handle = await run(env, words, env.launch(assertion_file=str(corpus)), mode="test",
                       extra={"corpus": {"name": "baseline", "assertion_count": len(words)}})
    assert handle.stage is RunStage.COMPLETED, handle.failure
    lines = results(handle)
    got = [(line["assertion"]["classification"], line["assertion"]["error_reason"])
           for line in lines]
    assert got == [("pass", None), ("new_ambiguity", None), ("pass", None),
                   ("regression", None), ("error", "invalid_segment")]
    assert lines[1]["assertion"]["unexpected"] == [[{"form": "baca", "gloss": "book"}]]
    assert lines[3]["assertion"]["missing"] == [[{"form": "zzz", "gloss": "Z"}]]
    worker = meta_sandbox(handle)["worker"]
    assert worker["counters"] == "ok"
    assert worker["engine_counters"] == {"tests": 5, "passed": 2, "failed": 2, "error": 1}
    assert worker["counter_agreement"] is True
    output = handle.record.read_sandbox_file("hc-output.txt")
    assert "[2] baca: parsed -> new_ambiguity" in output
    assert "    unexpected: baca book" in output


async def test_corpus_crash_gives_error_lines_never_a_classification(env):
    env.script(SCRIPT, words={**SCRIPT["words"], "baca": {"crash": 3}})
    corpus = write_corpus()
    words = [a["word"] for a in CORPUS_ASSERTIONS]
    handle = await run(env, words, env.launch(assertion_file=str(corpus)), mode="test")
    assert handle.stage is RunStage.COMPLETED, handle.failure
    reasons = [line["assertion"]["error_reason"] for line in results(handle)]
    assert reasons == [None, "error_no_output", "not_reached", "not_reached", "not_reached"]


# ---------------------------------------------------------------------------
# The project-cache path (Generate mode, the fake GenerateHCConfig; Windows)
# ---------------------------------------------------------------------------

win = pytest.mark.windows_only


@pytest.fixture
def cache_env(env, fake_generator):
    env.gen = fake_generator
    base = env.launch

    def launch(**extra):
        value = base(named=False, generate_hc_config_path=str(fake_generator.path))
        value.update(extra)
        return value

    env.cache_launch = launch
    return env


@win
async def test_cold_then_warm_generation(cache_env, monkeypatch):
    env = cache_env
    spy = SpawnSpy(monkeypatch)
    cold = await run(env, ["membaca"], env.cache_launch(), config_kind="project_cache")
    assert cold.stage is RunStage.COMPLETED, cold.failure
    sb = meta_sandbox(cold)
    assert sb["generation"]["reused_cache"] is False
    assert sb["config_source"]["kind"] == "project_cache" and sb["config_source"]["cache_key"]
    assert sb["copy"]["cleanup"] == "deleted" and sb["copy"]["bytes"] > 0
    assert sb["parameters_source"] == "cache"
    assert "--named-sandbox" not in spy.argv
    assert len(results(cold)) == 1
    assert_work_empty()

    warm = await run(env, ["membaca"], env.cache_launch(), config_kind="project_cache")
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
async def test_generation_failure_is_parser_config_failed_with_run_id(cache_env):
    env = cache_env
    env.gen.set(mode="crash")
    handle = await run(env, ["membaca"], env.cache_launch(), config_kind="project_cache")
    assert handle.stage is RunStage.FAILED
    assert handle.failure.error_code == "parser_config_failed"
    detail = handle.failure.detail
    assert detail["run_id"] == handle.run_id
    assert Path(detail["log_path"]) == handle.record.sandbox_path("generate-config.log")
    assert results(handle) == []
    assert_work_empty()


@win
async def test_client_exception_after_copy_still_deletes_it(cache_env, monkeypatch):
    """The client's own finally deletes the copy on an unexpected exception."""
    env = cache_env
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
    handle = await run(env, ["membaca"], env.cache_launch(), config_kind="project_cache")
    assert handle.stage is RunStage.FAILED
    assert made and not any(p.exists() for p in made)
    assert meta_sandbox(handle)["copy"]["cleanup"] == "deleted"
    assert_work_empty()


@win
async def test_two_concurrent_jobs_get_distinct_clients_and_copies(cache_env, monkeypatch):
    env = cache_env
    env.gen.set(sleep_seconds=1)
    made = []
    real_create = workdir.create

    def create(run_id, **kw):
        made.append(real_create(run_id, **kw))
        return made[-1]

    monkeypatch.setattr(workdir, "create", create)
    a, b = await asyncio.gather(
        start(env, ["membaca"], env.cache_launch(), config_kind="project_cache"),
        start(env, ["baca"], env.cache_launch(), config_kind="project_cache"),
    )
    await asyncio.wait_for(asyncio.gather(a.done.wait(), b.done.wait()), timeout=RUN_WAIT)
    assert a.stage is RunStage.COMPLETED and b.stage is RunStage.COMPLETED
    assert a.sandbox_client is not b.sandbox_client
    assert len(made) == 2 and made[0] != made[1]
    assert env.runner.pool.active_workers() == []
    assert_work_empty()


@win
@pytest.mark.parametrize("path", ["success", "generator_fail", "load_fail",
                                  "cancel_during_generation", "client_exception"])
async def test_work_is_empty_after_every_terminal_path(cache_env, monkeypatch, path):
    env = cache_env
    words = ["membaca", "baca", "xyz"]
    expected = RunStage.COMPLETED
    if path == "generator_fail":
        env.gen.set(mode="crash")
        expected = RunStage.FAILED
    elif path == "load_fail":
        env.gen.set(mode="empty_config")
        expected = RunStage.FAILED
    elif path == "cancel_during_generation":
        env.gen.set(sleep_seconds=600)
        expected = RunStage.CANCELLED
    elif path == "client_exception":
        def broken(*a, **kw):
            raise RuntimeError("client bug")

        monkeypatch.setattr(classify, "worker_parse_to_line", broken)
        expected = RunStage.FAILED

    handle = await start(env, words, env.cache_launch(timeout=30), config_kind="project_cache")
    if path == "cancel_during_generation":
        root = paths.work_root()
        assert await wait_for(lambda: root.exists() and any(root.iterdir())), "copy dir made"
        assert await wait_for(lambda: bool(env.gen.invocations())), "generator started"
        await env.runner.cancel_run(handle.run_id)
    await asyncio.wait_for(handle.done.wait(), timeout=RUN_WAIT)
    assert handle.stage is expected, (path, handle.failure)
    assert_work_empty()


# ---------------------------------------------------------------------------
# T115: FR-047's `live_project` source for a named sandbox
# ---------------------------------------------------------------------------


def _tree_bytes(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class _NoLcmImports:
    """A meta-path finder that fails any flexicon / LCM import (boom-stub)."""

    BANNED = ("flexicon", "flexlibs", "SIL", "clr")

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.BANNED:
            raise AssertionError("the named-sandbox path imported %s" % name)
        return None


async def test_a_named_sandbox_reads_its_live_project_parameters(
        env, fake_project_factory, monkeypatch):
    """The real stream read: the fake project stores `GuessRoots` false,
    under an XAmple active parser -- a parameters read is never a refusal."""
    import sys

    origin = fake_project_factory(name="Origin", active_parser="XAmple")
    for name in list(sys.modules):
        if name.split(".")[0] in _NoLcmImports.BANNED:
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "meta_path", [_NoLcmImports()] + sys.meta_path)
    sandbox_before = _tree_bytes(env.sandbox_dir)
    project_before = _tree_bytes(origin.dir)

    handle = await run(env, ["membaca"], env.launch(
        origin_project="Origin", origin_fwdata_path=str(origin.fwdata)))
    assert handle.stage is RunStage.COMPLETED, handle.failure
    sb = meta_sandbox(handle)
    assert sb["parameters_source"] == "live_project"
    assert sb["parser_parameters"]["guess_roots"] is False
    assert sb.get("parameters_note") is None
    assert json.loads(handle.record.read_sandbox_file("hc-params.json"))["guess_roots"] is False
    # Nothing under the sandbox or the origin project changed (FR-043).
    assert _tree_bytes(env.sandbox_dir) == sandbox_before
    assert _tree_bytes(origin.dir) == project_before


async def test_no_recorded_origin_project_gives_flex_defaults_with_a_note(env):
    handle = await run(env, ["membaca"], env.launch())
    sb = meta_sandbox(handle)
    assert sb["parameters_source"] == "flex_defaults"
    assert "records no originating project" in sb["parameters_note"]


async def test_an_origin_that_no_longer_resolves_gives_flex_defaults_with_a_note(env):
    handle = await run(env, ["membaca"], env.launch(origin_project="Gone"))
    sb = meta_sandbox(handle)
    assert sb["parameters_source"] == "flex_defaults"
    assert "Gone" in sb["parameters_note"] and "no longer resolves" in sb["parameters_note"]
