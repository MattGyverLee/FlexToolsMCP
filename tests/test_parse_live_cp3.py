#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The CP3 quickstart scenarios, against live FieldWorks projects
(parser-check CP3; specs/parser-check-cp3/quickstart.md).

EVERYTHING HERE IS READ-ONLY. CP3 ships no write path at all -- not a guarded
one, not a confirmed one. That is a standing guarantee (FR-063) asserted
separately and by test in `tests/test_parse_no_project_writes.py`; this module
must never become the exception that makes that test a lie.

WHY THESE SCENARIOS NEED A LIVE PROJECT. The offline suite covers the shapes:
that a diff classifies on signature sets rather than counts, that ranking only
promotes, that a projection needs all three conjuncts. What a double cannot
settle is whether the things being doubled are *true of the data model* --
and CP3's plan rests on two facts that are live-only:

  * ANALYSIS IDENTIFIER STABILITY across sessions. `DurableAnalysisSignature`
    (FR-031) is a sequence of identifier triples. If those identifiers are not
    stable across a close/reopen, the whole comparison silently degrades and
    the FR-033 rendered-form fallback has to be activated instead. T125
    records the verdict; only a live run can produce it.
  * SHARED-MODE STALENESS. FR-034 downgrades a `no_change` to
    `no_change_unverifiable` when the project is open elsewhere. Whether the
    probe can see that at all, and what it reports, is a property of a real
    open project.

THE DESIGNATED PROJECTS, and why `Sena 3` is not one of them:

    IndonesianHC-Complete           correctness. Scenarios 1-6, the
                                    break-then-revert cycle (SC-009) and the
                                    kill-mid-batch (SC-004).
    Malay Parsing-20230810withHC    scale. The scale scenarios only.

    Sena 3                          EXCLUDED BY NAME. It reports engine
                                    `XAmple`, and this feature's own engine
                                    gate (FR-024) refuses it before a parser
                                    is constructed. It is not a smaller
                                    stand-in for a HermitCrab project; it is a
                                    project CP3 declines to run against, and
                                    substituting it would test the refusal
                                    rather than the feature. Do not swap it in
                                    when a designated project is unavailable
                                    -- skip instead.

Scenario-to-task mapping (specs/parser-check-cp3/tasks.md Phase 9):

    T122    Scenarios 1-3 on IndonesianHC-Complete, with pre/post evidence
            captured to the same discipline a write path would get
    T123    Scenarios 4-6 on IndonesianHC-Complete, including the
            break-then-revert cycle (SC-009) and the kill-mid-batch (SC-004)
    T124    the scale scenarios on Malay Parsing-20230810withHC (SC-022)
    T125    the identifier-stability verdict, read out of T122's evidence

Deselect on a machine without FieldWorks with `-m "not requires_flex"`, the
same way `tests/test_parse_live.py` is deselected.
"""

import os

import pytest

pytestmark = pytest.mark.requires_flex


# The correctness project. Scenarios 1-6 and both SC-004 and SC-009 run here.
HC_PROJECT = os.environ.get("FLEXTOOLSMCP_LIVE_HC_PROJECT", "IndonesianHC-Complete")

# The scale project. The scale scenarios only (T124, SC-022).
SCALE_PROJECT = os.environ.get(
    "FLEXTOOLSMCP_LIVE_SCALE_PROJECT", "Malay Parsing-20230810withHC"
)

# Named here so the exclusion is greppable and survives a refactor that loses
# the docstring. Nothing in this module may open it.
EXCLUDED_XAMPLE_PROJECT = "Sena 3"


def test_the_excluded_project_is_never_a_substitute():
    """`Sena 3` must not be reachable as either designated project.

    This is a guard on the test module itself rather than on the server. The
    failure it exists to catch is a maintainer setting
    `FLEXTOOLSMCP_LIVE_HC_PROJECT=Sena 3` to get a red live suite green on a
    machine that lacks the real project -- which would silently convert every
    scenario below into an assertion about the engine refusal.
    """
    assert HC_PROJECT != EXCLUDED_XAMPLE_PROJECT
    assert SCALE_PROJECT != EXCLUDED_XAMPLE_PROJECT


# ===========================================================================
# The live scenarios (T122-T125). Every one is READ-ONLY.
# ===========================================================================
#
# WHAT IS NOT HERE, and why. Three quickstart steps need a human editing the
# project in FieldWorks: breaking and reverting a grammar rule (SC-009),
# deleting and recreating a morph (SC-010's live half), and holding the
# project open in shared mode (FR-034's live half). Each is a project write
# made outside this server; a test suite that made it would be the write path
# CP3 promises not to have. They are recorded as needs-a-human in the run log.
#
# Neither designated project carries a genre, so the genre halves of Scenario
# 1 (SC-001's second-genre case, the ambiguity refusal) are proven offline by
# `tests/test_parse_scope.py` and not here -- adding a genre is a write.

import asyncio  # noqa: E402
import contextlib  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402
from flextoolsmcp.server.subprocess_helpers import _kill_process_tree  # noqa: E402

EVIDENCE_DIR = REPO_ROOT / "specs" / "parser-check-cp3" / "evidence"

#: The sandbox-spine files a CP3 run must never create, even empty.
_SANDBOX_FILES = (
    "run.json", "trace.txt", "hc-script.txt", "hc-output.txt",
    "hc-stdout.txt", "generate-config.log",
)

_SECTIONS = (
    "summary", "config_generation", "hc_stdout", "hc_output", "trace", "words", "results",
)


def _evidence(name, payload):
    """Write one scenario's evidence, stamped, beside the spec."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(payload, recorded_at=datetime.now(timezone.utc).isoformat())
    (EVIDENCE_DIR / f"{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


class StageLog:
    """Every stage every run enters, in order (the record keeps only the last)."""

    def __init__(self, runner):
        self.stages = []
        original = runner._set_stage

        def recording(handle, stage, **updates):
            self.stages.append((handle.run_id, stage.value))
            return original(handle, stage, **updates)

        runner._set_stage = recording

    def loads(self, *run_ids):
        return sum(1 for rid, s in self.stages if rid in run_ids and s == "loading_grammar")


@contextlib.asynccontextmanager
async def live(tmp_path, grace_window=5.0):
    runner = ParseRunner(record_dir=tmp_path / "runs", grace_window=grace_window)
    log = StageLog(runner)
    parse_handler.set_runner(runner)
    try:
        yield runner, log
    finally:
        parse_handler.set_runner(None)
        await runner.aclose()


async def _tool(handler, **args):
    response = await handler(args)
    return json.loads(response[0].text)


async def _parse_text(project, **args):
    return await _tool(parse_handler.handle_flextools_parse_text, project_name=project, **args)


async def _wait(handle, timeout=1800):
    await asyncio.wait_for(handle.done.wait(), timeout=timeout)


async def _until(handle, words, polls=2400):
    for _ in range(polls):
        if handle.words_completed >= words or handle.is_terminal:
            return
        await asyncio.sleep(0.05)


def _result_lines(handle):
    path = handle.record.root / "results.jsonl"
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        with contextlib.suppress(json.JSONDecodeError):
            lines.append(json.loads(raw))
    return lines


def _signatures(handle):
    """word -> sorted signature tuples, straight from the artifact."""
    out = {}
    for line in _result_lines(handle):
        parse = line.get("parse") or {}
        out[line["wordform"]] = sorted(
            json.dumps(a.get("signature")) for a in parse.get("analyses") or []
        )
    return out


# ---------------------------------------------------------------------------
# T122 -- Scenarios 1-3 on the correctness project
# ---------------------------------------------------------------------------


async def test_t122_scenario_1_scope_resolution_is_deterministic(tmp_path):
    """SC-002 live: order-then-truncate, identical list and fingerprint twice."""
    async with live(tmp_path) as (runner, _):
        first = await runner.resolve_scope(HC_PROJECT, {"kind": "all_texts", "limit": 10})
        second = await runner.resolve_scope(HC_PROJECT, {"kind": "all_texts", "limit": 10})
        full = await runner.resolve_scope(HC_PROJECT, {"kind": "all_texts"})
        missing = await _parse_text(
            HC_PROJECT, scope_kind="genre", scope_value="zz-no-such-genre"
        )

    for resolved in (first, second, full):
        resolved.pop("project_state", None)
    assert first == second, "the same scope resolved to two different lists"
    assert first["truncated"] is True and len(first["words"]) == 10
    assert first["words"] == full["words"][:10], (
        "truncation happened before ordering: the limited list is not the head "
        "of the ordered one"
    )
    assert missing["error_code"] == "parse_scope_empty"
    assert "default analysis writing system" in missing["hint"]
    _evidence("t122-scenario1", {
        "project": HC_PROJECT, "limited": first, "full_word_count": len(full["words"]),
        "missing_genre_refusal": missing,
        "not_live_reachable": "the project has no genres; SC-001 and the ambiguity "
                              "refusal are proven offline (tests/test_parse_scope.py)",
    })


async def test_t122_scenarios_2_and_3_batch_interleave_and_every_section(tmp_path):
    """SC-005/SC-006 live, the artifact layout, and SC-007 on the real run."""
    async with live(tmp_path, grace_window=0.5) as (runner, log):
        submitted = await _parse_text(HC_PROJECT, scope_kind="all_texts")
        assert submitted["status"] == "ok" and submitted["run_started"], submitted
        batch = runner.get(submitted["run_id"])

        # An urgent word while the batch runs: answered without waiting for it.
        await _until(batch, 1)
        batch_was_running = not batch.is_terminal
        started = time.monotonic()
        urgent = await _tool(
            parse_handler.handle_flextools_try_word,
            project_name=HC_PROJECT, word="pukul", level="plain",
        )
        urgent_seconds = time.monotonic() - started
        await _wait(batch)

        sections = {}
        for section in _SECTIONS:
            sections[section] = await _tool(
                parse_handler.handle_flextools_parse_log,
                run_id=batch.run_id, section=section,
            )
        files = sorted(p.name for p in batch.record.root.iterdir())
        loads = log.loads(batch.run_id, urgent.get("run_id"))

    assert batch.stage is RunStage.COMPLETED, batch.stage
    assert urgent["status"] == "ok", urgent
    assert loads == 1, f"the grammar was loaded {loads} times across batch + urgent word"
    assert {"meta.json", "results.jsonl", "words.txt"} <= set(files), files
    assert not set(files) & set(_SANDBOX_FILES), f"sandbox files were created: {files}"
    assert sections["summary"]["content"].get("report"), "a batch summary carries no report"
    for name, payload in sections.items():
        assert payload.get("status") == "ok", (name, payload)
        assert len(json.dumps(payload)) > 60, f"{name} came back empty"
    _evidence("t122-scenarios2-3", {
        "project": HC_PROJECT, "run_id": batch.run_id, "words_total": batch.words_total,
        "words_completed": batch.words_completed, "grammar_loads": loads,
        "batch_was_running_when_urgent_word_sent": batch_was_running,
        "urgent_word_seconds": round(urgent_seconds, 3),
        "urgent_word_stage": urgent.get("stage"), "files": files,
        "section_status": {k: v.get("status") for k, v in sections.items()},
        "sandbox_sections": {
            k: {kk: sections[k].get(kk) for kk in ("applicable", "spine", "checkpoint", "note")}
            for k in ("config_generation", "hc_stdout", "hc_output")
        },
        "summary_report_keys": sorted(
            (sections["summary"]["content"].get("report") or {}).keys()
        ),
        "counters": sections["summary"]["content"].get("counters"),
    })


# ---------------------------------------------------------------------------
# T123 -- the automatable half of Scenarios 4-6
# ---------------------------------------------------------------------------


async def test_t123_a_killed_worker_leaves_every_completed_word_readable(tmp_path):
    """SC-004 live: the worker's process tree is killed mid-batch."""
    async with live(tmp_path, grace_window=0.5) as (runner, _):
        submitted = await _parse_text(HC_PROJECT, scope_kind="all_texts")
        batch = runner.get(submitted["run_id"])
        await _until(batch, 5)
        assert not batch.is_terminal, "the batch finished before it could be killed"
        _kill_process_tree(runner.pool.peek(HC_PROJECT).pid)
        await _wait(batch, timeout=120)
        lines = _result_lines(batch)
        results = await _tool(
            parse_handler.handle_flextools_parse_log,
            run_id=batch.run_id, section="results", limit=500,
        )

    assert batch.stage is RunStage.FAILED, batch.stage
    assert len(lines) == batch.words_completed >= 5, (len(lines), batch.words_completed)
    assert results["status"] == "ok"
    _evidence("t123-kill-mid-batch", {
        "project": HC_PROJECT, "run_id": batch.run_id,
        "words_total": batch.words_total, "words_completed": batch.words_completed,
        "readable_lines": len(lines),
        "failure": batch.failure.to_dict() if batch.failure else None,
    })


async def test_t123_a_cancelled_batch_stops_at_a_word_boundary(tmp_path):
    async with live(tmp_path, grace_window=0.5) as (runner, _):
        submitted = await _parse_text(HC_PROJECT, scope_kind="all_texts")
        batch = runner.get(submitted["run_id"])
        await _until(batch, 3)
        assert not batch.is_terminal, "the batch finished before it could be cancelled"
        await runner.cancel_run(batch.run_id)
        await _wait(batch, timeout=120)
        status = await _tool(parse_handler.handle_flextools_parse_status, run_id=batch.run_id)

    assert batch.stage is RunStage.CANCELLED
    assert len(_result_lines(batch)) == batch.words_completed < batch.words_total
    assert status["status"] == "ok"
    assert status["next_step"][0]["tool"] == "flextools_parse_log"


async def test_t123_and_t125_identifiers_are_stable_across_sessions(tmp_path):
    """Two sessions (the worker is released between them), one scope.

    T125's evidence: every word's signature set -- GUID triples -- is
    identical across a close and reopen of the project. The diff over them
    reports 0 behavioural changes and 0 identity changes. Then a different
    scope is refused naming the differing fields, and forced, compares the
    intersection only.
    """
    async with live(tmp_path, grace_window=0.5) as (runner, _):
        first = await _parse_text(HC_PROJECT, scope_kind="all_texts")
        a = runner.get(first["run_id"])
        await _wait(a)
        await runner.pool.release(HC_PROJECT)   # a new session: close and reopen
        second = await _parse_text(HC_PROJECT, scope_kind="all_texts")
        b = runner.get(second["run_id"])
        await _wait(b)
        narrow = await _parse_text(HC_PROJECT, scope_kind="all_texts", limit=5)
        c = runner.get(narrow["run_id"])
        await _wait(c)

        same = await _tool(parse_handler.handle_flextools_parse_diff,
                           baseline_run_id=a.run_id, current_run_id=b.run_id)
        refused = await _tool(parse_handler.handle_flextools_parse_diff,
                              baseline_run_id=a.run_id, current_run_id=c.run_id)
        forced = await _tool(parse_handler.handle_flextools_parse_diff,
                             baseline_run_id=a.run_id, current_run_id=c.run_id, force=True)

    sig_a, sig_b = _signatures(a), _signatures(b)
    differing = sorted(w for w in sig_a if sig_a.get(w) != sig_b.get(w))
    analysed = sum(1 for v in sig_a.values() if v)
    _evidence("t125-identifier-stability", {
        "project": HC_PROJECT, "sessions": [a.run_id, b.run_id],
        "words": len(sig_a), "words_with_analyses": analysed,
        "signature_sets_differing": differing,
        "verdict": "stable" if analysed and not differing else "unstable_or_untested",
        "same_scope_diff": {k: same.get(k) for k in ("status", "verdict", "comparison_mode",
                                                      "counts", "identity_change_count")},
        "mismatch_refusal": {k: refused.get(k) for k in ("error_code", "differing_fields")},
        "forced": {k: forced.get(k) for k in ("status", "forced", "counts", "notes")},
    })
    assert analysed > 0, "no word produced an analysis, so stability was not tested"
    assert differing == [], f"signatures moved across sessions for {differing}"
    assert same["status"] == "ok"
    assert same["counts"]["fixed"] == same["counts"]["broken"] == same["counts"]["changed"] == 0
    assert same["identity_change_count"] == 0
    assert refused["error_code"] == "parse_scope_mismatch"
    assert refused["differing_fields"], refused
    assert forced["status"] == "ok" and forced.get("forced") is True


async def test_t123_scenario_6_a_live_measurement(tmp_path):
    """SC-017/SC-018 live: a generous bound completes; a one-second bound on a
    cold grammar load is stopped and reported as a result."""
    async with live(tmp_path, grace_window=5.0) as (runner, _):
        fast = await _tool(parse_handler.handle_flextools_try_word,
                           project_name=HC_PROJECT, word="pukul", level="plain",
                           bound_seconds=300)
        tight = await _tool(parse_handler.handle_flextools_try_word,
                            project_name=HC_PROJECT, word="pukul", level="plain",
                            bound_seconds=1)
        active = runner.pool.active_workers()

    _evidence("t123-scenario6-measurement", {
        "project": HC_PROJECT, "generous": fast.get("measurement"),
        "tight": tight.get("measurement"), "tight_finding": tight.get("finding"),
        "tight_next_step": [r["tool"] for r in tight.get("next_step") or []],
    })
    assert fast["status"] == "ok" and fast["measurement"]["outcome"] == "completed", fast
    assert tight["status"] == "ok", tight
    if tight["measurement"]["outcome"] == "terminated_at_bound":
        assert tight["next_step"][0]["tool"] == "flextools_grammar_health"
    else:
        assert tight["next_step"] is None
    assert not [key for key in active if key[1] == "measurement"], active


# ---------------------------------------------------------------------------
# T124 -- the scale project
# ---------------------------------------------------------------------------

_HEADWORDS_SNIPPET = (
    "import sys, json\n"
    "sys.stdout.reconfigure(encoding='utf-8')\n"
    "from flexicon import FLExInitialize, FLExProject, FLExCleanup\n"
    "FLExInitialize()\n"
    "p = FLExProject()\n"
    "p.OpenProject(projectName=sys.argv[1], writeEnabled=False)\n"
    "try:\n"
    "    forms = sorted({(p.LexEntry.GetLexemeForm(e) or '').strip()"
    " for e in p.LexEntry.GetAll()})\n"
    "    print(json.dumps([f for f in forms if f and ' ' not in f]))\n"
    "finally:\n"
    "    p.CloseProject()\n"
    "    FLExCleanup()\n"
)


def _scale_words(limit=2500):
    """Distinct lexeme forms from the scale project, read in a read-only child."""
    out = subprocess.run(
        [sys.executable, "-c", _HEADWORDS_SNIPPET, SCALE_PROJECT],
        capture_output=True, text=True, encoding="utf-8", timeout=600,
        stdin=subprocess.DEVNULL,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])[:limit]


async def test_t124_scale_batch_interleave_and_kill(tmp_path):
    words = _scale_words()
    # The project holds ~260 lexemes and three short texts, so the quickstart's
    # "few thousand words" is not available from its data; the whole lexicon is
    # the largest honest scope it offers, and the evidence says so.
    assert len(words) >= 200, f"the scale project yielded only {len(words)} words"
    async with live(tmp_path, grace_window=0.5) as (runner, log):
        submitted = await _parse_text(SCALE_PROJECT, scope_kind="words", scope_value=words)
        assert submitted.get("run_started"), submitted
        batch = runner.get(submitted["run_id"])
        await _until(batch, 50, polls=12000)
        started = time.monotonic()
        urgent = await _tool(parse_handler.handle_flextools_try_word,
                             project_name=SCALE_PROJECT, word=words[0], level="plain")
        urgent_seconds = time.monotonic() - started
        mid_status = await _tool(parse_handler.handle_flextools_parse_status,
                                 run_id=batch.run_id)

        kill_at = (len(words) * 2) // 3
        await _until(batch, kill_at, polls=72000)
        killed = not batch.is_terminal
        if killed:
            _kill_process_tree(runner.pool.peek(SCALE_PROJECT).pid)
        await _wait(batch, timeout=600)
        lines = _result_lines(batch)
        loads = log.loads(batch.run_id, urgent.get("run_id"))
        summary = await _tool(parse_handler.handle_flextools_parse_log,
                              run_id=batch.run_id, section="summary")

    _evidence("t124-scale", {
        "project": SCALE_PROJECT, "run_id": batch.run_id, "words_submitted": len(words),
        "scale_note": "whole lexicon (the largest scope the project offers); killed at ~2/3",
        "words_total": batch.words_total, "words_completed": batch.words_completed,
        "readable_lines": len(lines),
        "killed_at_word": batch.words_completed if killed else None,
        "final_stage": batch.stage.value, "grammar_loads": loads,
        "urgent_word_seconds": round(urgent_seconds, 3),
        "urgent_status": urgent.get("status"), "urgent_stage": urgent.get("stage"),
        "mid_run_status": {k: mid_status.get(k) for k in
                           ("stage", "words_completed", "interleaved_by")},
        "counters": summary["content"].get("counters"),
        "report_keys": sorted((summary["content"].get("report") or {}).keys()),
    })
    assert urgent["status"] == "ok", urgent
    assert loads == 1, f"grammar loaded {loads} times across the batch and the urgent word"
    assert len(lines) == batch.words_completed
    assert summary["status"] == "ok"
    if killed:
        assert batch.stage is RunStage.FAILED
