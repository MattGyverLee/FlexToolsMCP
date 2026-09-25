#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 T042 (FR-042, FR-043, SC-001): the sandbox spine never
writes inside a FieldWorks project folder.

What this file pins
-------------------
1. FR-042 matrix (thin; tests/test_sandbox_paths.py owns the detail): with
   FLEXTOOLSMCP_PARSE_SANDBOX_DIR pointing inside a project folder, the root
   and each of the four areas (`config-cache`, `sandboxes`, `corpora`,
   `work`) raise `filing.paths.ArtifactInsideProject`; so does the root
   pointing AT the project folder. Through the real handler, such a root
   never starts a tool (a refusal, or a run that fails before any tool
   starts) and a `word_file` inside a project
   folder is refused; the project folder is byte-identical afterwards.

2. SC-001 end to end (Windows only): `handle_flextools_parse_sandbox` ->
   the real `ParseRunner` -> the real per-run `SandboxClient` -> the real
   packaged `hcparse.ps1` (Generate) and the fake GenerateHCConfig -> a real
   `--stub --sandbox` parse worker (re-plan T108), on the project's
   cached-config source (so the copy and generation happen). Only project
   resolution, tool discovery and the worker's engine are stubbed; the stub
   engine takes its script from the fake config's payload (`stub` key). For
   every terminal path -- success, generator failure, engine load failure,
   timeout, cancel during generation, cancel during parsing -- the fake
   project folder hashes identically before and after (every path, every
   file's bytes, size and mtime; no new file, no new `*.lock`), and `work/`
   is empty.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List

import pytest

from flextoolsmcp.server import parser_probe
from flextoolsmcp.server.filing import paths as filing_paths
from flextoolsmcp.server.handlers import parse as parse_handler
from flextoolsmcp.server.parse.runner import ParseRunner
from flextoolsmcp.server.parse.stages import RunStage
from flextoolsmcp.server.sandbox import cache, engine, paths

PROJECT = "FakeProj"
RUN_WAIT = 120

GRAMMAR = {
    "language": "Fake Lang",
    "words": {
        "membaca": [[["mem", "ACT"], ["baca", "read"]]],
        "baca": [[["baca", "read"]], [["baca", "book"]]],
        "xyz": [],
    },
    "default": [],
}
WORDS = ["membaca", "baca", "xyz"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def project_fingerprint(directory: Path) -> Dict[str, tuple]:
    """Every path under the project folder: kind, size, mtime, sha256."""
    result = {}
    for path in sorted(directory.rglob("*")):
        rel = path.relative_to(directory).as_posix()
        if path.is_dir():
            result[rel] = ("dir",)
            continue
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result[rel] = ("file", stat.st_size, stat.st_mtime_ns, digest)
    return result


def assert_project_untouched(project, before: Dict[str, tuple]) -> None:
    after = project_fingerprint(project.dir)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(after) & set(before) if after[k] != before[k])
    assert not (added or removed or changed), (
        "the project folder changed (SC-001): added=%r removed=%r changed=%r"
        % (added, removed, changed)
    )
    locks = sorted(p.name for p in project.dir.rglob("*.lock"))
    assert locks == [project.lock.name], locks


def assert_work_empty() -> None:
    root = paths.work_root()
    left = sorted(p.name for p in root.iterdir()) if root.exists() else []
    assert left == [], "work/ must be empty after every terminal path (FR-011): %r" % left


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def processes_with(token: str) -> List[int]:
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


async def wait_for(predicate, timeout=60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


async def call(tool, args) -> dict:
    response = await tool(args)
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _fresh_module_state():
    cache.reset_state()
    engine.clear_engine_cache()
    yield
    cache.reset_state()
    engine.clear_engine_cache()


@pytest.fixture
def e2e(tmp_path, sandbox_root, fake_project, fake_generator, monkeypatch):
    """The real handler, runner, client, script and worker process; a fake
    generator, project and engine."""
    monkeypatch.setenv("FAKE_PYTHON", sys.executable)
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: fake_project.dir.parent)
    monkeypatch.setattr(parse_handler, "_resolve_project", lambda name: (name or PROJECT, None))

    dll = tmp_path / "fw" / parser_probe.FIELDWORKS_HERMITCRAB_DLL
    engine_probe = parser_probe.EngineDiscovery(
        ok=True, signal=None, expected_path=str(dll), found=True, file_version="3.8.2.0")
    ghc = SimpleNamespace(
        ok=True, signal=None, expected_path=str(fake_generator.path),
        detected_version=None, load_error=None, missing_members=[],
    )
    monkeypatch.setattr(parser_probe, "discover_fieldworks_hermitcrab",
                        lambda *a, **k: engine_probe)
    monkeypatch.setattr(parser_probe, "discover_generate_hc_config", lambda *a, **k: ghc)
    # The worker runs as `--stub --sandbox`: everything but the engine calls.
    real_launch = parse_handler._sandbox_launch
    monkeypatch.setattr(parse_handler, "_sandbox_launch",
                        lambda plan: dict(real_launch(plan), worker_stub=True))

    def stub(**script):
        fake_generator.set(grammar=json.dumps(dict(GRAMMAR, stub=script)))

    stub()
    runner = ParseRunner(record_dir=tmp_path / "parse-runs", grace_window=0.0, stub=True)
    parse_handler.set_runner(runner)
    env = SimpleNamespace(tmp=tmp_path, root=sandbox_root, project=fake_project,
                          gen=fake_generator, runner=runner, stub=stub)
    try:
        yield env
    finally:
        parse_handler.set_runner(None)
        if sys.platform == "win32":
            for pid in processes_with(str(tmp_path)):
                _kill_tree(pid)


async def start_parse(env, **extra) -> str:
    args = {"action": "parse", "project_name": PROJECT, "words": list(WORDS)}
    args.update(extra)
    payload = await call(parse_handler.handle_flextools_parse_sandbox, args)
    run_id = payload.get("run_id")
    assert run_id, "no run was started: %r" % payload
    return run_id


async def finish(env, run_id):
    handle = env.runner.get(run_id)
    assert handle is not None
    await asyncio.wait_for(handle.done.wait(), timeout=RUN_WAIT)
    return handle


# ---------------------------------------------------------------------------
# 1. FR-042: no root, area or input inside a project folder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("area", ["config-cache", "sandboxes", "corpora", "work"])
@pytest.mark.parametrize("where", ["inside", "at"])
def test_every_area_under_a_root_in_a_project_is_refused(
    fake_project, monkeypatch, area, where
):
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: fake_project.dir.parent)
    root = fake_project.dir / "parse-root" if where == "inside" else fake_project.dir
    monkeypatch.setenv(paths.ENV_VAR, str(root))
    before = project_fingerprint(fake_project.dir)

    with pytest.raises(filing_paths.ArtifactInsideProject):
        paths.sandbox_root()
    with pytest.raises(filing_paths.ArtifactInsideProject):
        paths.area_root(area)

    assert_project_untouched(fake_project, before)


async def test_handler_refuses_a_sandbox_root_inside_a_project(e2e, monkeypatch):
    monkeypatch.setenv(paths.ENV_VAR, str(e2e.project.dir / "parse-root"))
    before = project_fingerprint(e2e.project.dir)

    payload = await call(parse_handler.handle_flextools_parse_sandbox,
                         {"action": "parse", "project_name": PROJECT, "words": list(WORDS)})

    # Either a refusal, or a run that fails before any tool starts: the spec
    # (FR-042) fixes the outcome -- nothing written in the project -- not the
    # step at which the guard fires.
    if payload.get("run_id"):
        handle = await finish(e2e, payload["run_id"])
        assert handle.stage is RunStage.FAILED, (handle.stage, handle.failure)
    else:
        assert payload.get("status") != "ok", payload
    assert e2e.gen.invocations() == []
    assert_project_untouched(e2e.project, before)


async def test_handler_refuses_a_word_file_inside_a_project(e2e):
    word_file = e2e.project.dir / "words.txt"
    word_file.write_text("membaca\n", encoding="utf-8")
    before = project_fingerprint(e2e.project.dir)

    payload = await call(parse_handler.handle_flextools_parse_sandbox,
                         {"action": "parse", "project_name": PROJECT,
                          "word_file": str(word_file)})

    assert payload.get("error_code") == "parse_sandbox_refused", payload
    assert payload.get("reason") == "word_file_invalid", payload
    assert e2e.runner.known_run_ids() == []
    assert_project_untouched(e2e.project, before)


# ---------------------------------------------------------------------------
# 2. SC-001: the project folder is byte-identical after every terminal path
# ---------------------------------------------------------------------------


TERMINAL_PATHS = [
    "success",
    "generator_failure",
    "engine_load_failure",
    "timeout",
    "cancel_during_generation",
    "cancel_during_parse",
]


@pytest.mark.windows_only
@pytest.mark.parametrize("path", TERMINAL_PATHS)
async def test_project_is_byte_identical_after_every_terminal_path(e2e, path):
    extra = {"timeout_seconds": 30}
    expected_stage, expected_code = RunStage.COMPLETED, None
    if path == "generator_failure":
        e2e.gen.set(mode="crash")
        expected_stage, expected_code = RunStage.FAILED, "parser_config_failed"
    elif path == "engine_load_failure":
        e2e.stub(load_fail="The morpher could not be built.")
        expected_stage, expected_code = RunStage.FAILED, "parser_job_failed"
    elif path == "timeout":
        e2e.stub(words={"xyz": {"sleep": 600}})
        extra = {"timeout_seconds": 10}  # the tool's minimum
        expected_stage, expected_code = RunStage.FAILED, "parser_timeout"
    elif path == "cancel_during_generation":
        e2e.gen.set(sleep_seconds=600)
        expected_stage = RunStage.CANCELLED
    elif path == "cancel_during_parse":
        e2e.stub(words={"xyz": {"sleep": 600}})
        expected_stage = RunStage.CANCELLED
    before = project_fingerprint(e2e.project.dir)

    run_id = await start_parse(e2e, **extra)
    if path == "cancel_during_generation":
        assert await wait_for(lambda: bool(e2e.gen.invocations())), "generator started"
        await call(parse_handler.handle_flextools_parse_cancel, {"run_id": run_id})
    elif path == "cancel_during_parse":
        handle = e2e.runner.get(run_id)
        assert await wait_for(lambda: handle.words_completed >= 1), "parsing started"
        await asyncio.sleep(0.5)
        await call(parse_handler.handle_flextools_parse_cancel, {"run_id": run_id})
    handle = await finish(e2e, run_id)

    assert handle.stage is expected_stage, (path, handle.stage, handle.failure)
    if expected_code is not None:
        assert handle.failure is not None and handle.failure.error_code == expected_code, (
            path, handle.failure)
    if path == "success":
        assert handle.words_completed == len(WORDS)
    assert_project_untouched(e2e.project, before)
    assert_work_empty()
    # Nothing the run started is still running (and so could still write).
    deadline = time.monotonic() + 8
    alive = processes_with(str(e2e.tmp))
    while alive and time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        alive = processes_with(str(e2e.tmp))
    assert not alive, "a process of the run survived: %r" % alive
