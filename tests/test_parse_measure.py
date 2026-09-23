#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The bounded single-word measurement (parser-check CP3, US6; FR-051..FR-055;
SC-017; data-model.md section 15; research.md R-05).

WHAT THIS FILE PROTECTS, in two sentences: a measurement stopped at its bound
is the FINDING -- "this grammar did not finish one word in N seconds" -- and
must come back as a result carrying its wall-clock measurement, never as an
error and never with an invented engine step count. And the bound is enforced
by killing a process tree, so the measurement must live in a worker of its
own: in the batch's worker, the kill would take the batch with it.

These run against REAL stub workers (subprocesses), not doubles, because the
thing under test is a process being killed. `--parse-delay` makes the stub's
parse slow enough to outlive a bound; the stub cannot fail for parser
reasons, so every outcome below is the machinery's.

Run with:
    python -m pytest tests/test_parse_measure.py -q
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.models import TryWordInput  # noqa: E402
from flextoolsmcp.server.parse.measure import (  # noqa: E402
    BoundedMeasurement,
    measure_word,
    summarize_parser_parameters,
)
from flextoolsmcp.server.parse.priority import Priority  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402
from flextoolsmcp.server.parse.worker_client import (  # noqa: E402
    MEASUREMENT_ROLE,
    SHARED_ROLE,
    WorkerPool,
)

#: The fields data-model.md section 15 names. Every one must be present.
_SECTION_15_FIELDS = {
    "wordform", "bound_seconds", "elapsed_seconds", "exceeded_bound",
    "missed_fast_path_by", "outcome",
}

#: What an invented engine count would be called. `analysis_count` is the
#: parse's own answer and is not one of these.
_INVENTED_COUNT_KEYS = ("step", "node", "iteration", "rule_applications")


def _invented_counts(node, path="$"):
    """Every key anywhere in the payload that names an engine step/node count."""
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).lower()
            if lowered != "next_step" and any(k in lowered for k in _INVENTED_COUNT_KEYS):
                found.append(f"{path}.{key}")
            found.extend(_invented_counts(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_invented_counts(value, f"{path}[{index}]"))
    return found


class RolePool:
    """Two real stub pools behind one pool interface: one per role.

    The shared worker and the measurement worker need DIFFERENT speeds -- a
    batch that keeps moving and a measurement that blows its bound -- and a
    stub's parse delay is per process. Routing by role is exactly the pool's
    own keying, so this double adds no behaviour the real pool lacks.
    """

    def __init__(self, *, shared_delay: float, measurement_delay: float) -> None:
        self.pools = {
            SHARED_ROLE: WorkerPool(stub=True, parse_delay=shared_delay),
            MEASUREMENT_ROLE: WorkerPool(stub=True, parse_delay=measurement_delay),
        }

    async def get(self, project_name, *, role=SHARED_ROLE):
        return await self.pools[role].get(project_name, role=role)

    def peek(self, project_name, *, role=SHARED_ROLE):
        return self.pools[role].peek(project_name, role=role)

    async def release(self, project_name, *, role=None):
        for key, pool in self.pools.items():
            if role is None or role == key:
                await pool.release(project_name, role=key)

    async def terminate(self, project_name, *, role):
        return await self.pools[role].terminate(project_name, role=role)

    async def aclose(self):
        for pool in self.pools.values():
            await pool.aclose()


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """The handler over a runner whose pool the test supplies."""
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    made = []

    def make(pool, grace_window=0.5):
        runner = ParseRunner(pool=pool, record_dir=tmp_path / "runs", grace_window=grace_window)
        parse_handler.set_runner(runner)
        made.append(runner)
        return runner

    yield make
    parse_handler.set_runner(None)


async def _measure(**args):
    payload = {"project_name": "P", "level": "plain"}
    payload.update(args)
    response = await parse_handler.handle_flextools_try_word(payload)
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# T101 -- FR-053, FR-054, SC-017: stopped at the bound is a RESULT
# ---------------------------------------------------------------------------


async def test_a_measurement_stopped_at_its_bound_is_a_result_not_an_error(wired):
    runner = wired(RolePool(shared_delay=0.0, measurement_delay=60.0))
    try:
        payload = await _measure(word="pukul", bound_seconds=1.5)
    finally:
        await runner.aclose()

    assert payload["status"] == "ok", (
        f"a measurement that blew its bound was reported as an error: {payload}"
    )
    assert "error_code" not in payload
    measurement = payload["measurement"]
    assert measurement["outcome"] == "terminated_at_bound"
    assert measurement["exceeded_bound"] is True
    # It carries its measurement: wall-clock, at least the bound, and not the
    # 60 seconds the parse would have taken.
    assert measurement["elapsed_seconds"] >= 1.5
    assert measurement["elapsed_seconds"] < 30, "the bound was not enforced"
    assert measurement["missed_fast_path_by"] is not None
    assert measurement["missed_fast_path_by"] > 0
    assert _SECTION_15_FIELDS <= set(measurement)
    assert measurement["parse"] is None, "a terminated word has no answer to report"
    assert "did not finish one word" in payload["finding"]


async def test_a_terminated_measurement_reports_zero_invented_engine_counts(wired):
    """SC-017's second half: 0 invented step or node counts, anywhere."""
    runner = wired(RolePool(shared_delay=0.0, measurement_delay=60.0))
    try:
        payload = await _measure(word="pukul", bound_seconds=1.0)
    finally:
        await runner.aclose()

    assert payload["measurement"]["outcome"] == "terminated_at_bound"
    offenders = _invented_counts(payload)
    assert offenders == [], (
        f"the measurement reports an engine count that does not exist: {offenders}"
    )


async def test_the_bound_is_enforced_by_killing_the_measurement_worker(wired):
    """FR-052: process level. The run ends CANCELLED -- the user's bound, not
    a failure -- and its worker is gone rather than still parsing."""
    pool = RolePool(shared_delay=0.0, measurement_delay=60.0)
    runner = wired(pool)
    try:
        payload = await _measure(word="pukul", bound_seconds=1.0)
        handle = runner.get(payload["measurement"]["run_id"])

        assert handle.stage is RunStage.CANCELLED, handle.stage
        assert handle.failure is None, "the bound was recorded as a failure"
        assert pool.peek("P", role=MEASUREMENT_ROLE) is None, (
            "the measurement's worker survived its bound"
        )
    finally:
        await runner.aclose()


async def test_a_fast_word_completes_inside_its_bound(wired):
    runner = wired(RolePool(shared_delay=0.0, measurement_delay=0.0), grace_window=30.0)
    try:
        payload = await _measure(word="pukul", bound_seconds=30)
    finally:
        await runner.aclose()

    measurement = payload["measurement"]
    assert payload["status"] == "ok"
    assert measurement["outcome"] == "completed"
    assert measurement["exceeded_bound"] is False
    assert measurement["missed_fast_path_by"] is None
    assert measurement["elapsed_seconds"] < 30


async def test_the_stored_parser_parameters_are_read_as_context(wired):
    """FR-055: read and reported. The stub's document comes back summarised."""
    runner = wired(RolePool(shared_delay=0.0, measurement_delay=0.0), grace_window=30.0)
    try:
        payload = await _measure(word="pukul", bound_seconds=30)
    finally:
        await runner.aclose()

    parameters = payload["measurement"]["parser_parameters"]
    assert parameters["active_parser"] == "HC"
    assert parameters["hc"] == {"GuessRoots": "false", "MaxCompoundRules": "4"}


def test_parameters_are_summarised_without_interpretation():
    """Each HC setting by its own tag and text; nothing renamed or defaulted."""
    summary = summarize_parser_parameters(
        "<ParserParameters><ActiveParser>HC</ActiveParser>"
        "<HC><DelReapps>0</DelReapps></HC></ParserParameters>"
    )
    assert summary == {
        "stored": True, "parseable": True, "active_parser": "HC",
        "hc": {"DelReapps": "0"},
    }
    assert summarize_parser_parameters(None) is None
    assert summarize_parser_parameters("") == {"stored": False}
    broken = summarize_parser_parameters("<ParserParameters><HC>")
    assert broken["parseable"] is False and broken["raw"].startswith("<Parser")


def test_the_missed_window_is_measured_not_guessed():
    inside = BoundedMeasurement(
        wordform="w", bound_seconds=10, elapsed_seconds=0.2, exceeded_bound=False,
        missed_fast_path_by=None, outcome="completed", fast_path_window_seconds=5,
        run_id="r", stage_at_end="completed",
    )
    assert "inside the 5-second fast-path window" in inside.finding
    assert _invented_counts(inside.to_dict()) == []


@pytest.mark.parametrize("level", ["explain", "restricted"])
def test_a_bound_on_a_trace_level_is_refused(level):
    """A trace would time the tracer as well as the grammar."""
    extra = {"morphs": [{"headword": "makan"}]} if level == "restricted" else {}
    with pytest.raises(ValidationError, match="bound_seconds"):
        TryWordInput(word="makan", level=level, bound_seconds=10, **extra)


def test_the_bound_is_itself_bounded():
    with pytest.raises(ValidationError):
        TryWordInput(word="makan", level="plain", bound_seconds=0)
    with pytest.raises(ValidationError):
        TryWordInput(word="makan", level="plain", bound_seconds=601)


# ---------------------------------------------------------------------------
# T102 -- FR-051, R-05: its own worker, never the batch's
# ---------------------------------------------------------------------------


FINGERPRINT = {
    "scope_kind": "words", "scope_value": None, "text_ids": [], "word_count": 40,
    "limit": None, "truncated": False, "engine": "HC", "vernacular_ws": "id",
}


async def test_terminating_a_measurement_does_not_take_a_running_batch_with_it(wired):
    """The reason the pool has a second key.

    A batch is running in project P's shared worker. A measurement on the SAME
    project blows its bound and is killed. The batch must still be running,
    in the same process, and must go on to complete every word.
    """
    pool = RolePool(shared_delay=0.05, measurement_delay=60.0)
    runner = wired(pool, grace_window=0.2)
    words = [f"w{n}" for n in range(200)]
    try:
        batch = await runner.start_run(
            project_name="P",
            wordforms=words,
            level="batch",
            priority=Priority.LOW,
            scope_fingerprint=FINGERPRINT,
            engine_at_submission="HC",
            vernacular_ws="id",
        )
        # Wait until the batch is genuinely under way in its worker: the grace
        # window closes before a stub worker has even finished starting.
        for _ in range(600):
            if batch.words_completed >= 1:
                break
            await asyncio.sleep(0.05)
        assert batch.words_completed >= 1, "the batch never started parsing"
        assert not batch.is_terminal, "the batch finished before it could be interrupted"
        batch_worker = pool.peek("P", role=SHARED_ROLE)
        batch_pid = batch_worker.pid

        measurement = await measure_word(
            runner, project_name="P", wordform="pukul", bound_seconds=1.0
        )
        assert measurement.outcome == "terminated_at_bound"
        measured = runner.get(measurement.run_id)
        assert not batch.is_terminal, (
            "the batch ended before the measurement was killed, so this test "
            "proved nothing about the kill reaching it"
        )

        # Never the same process, and the kill did not reach the batch's.
        assert measured.worker_role == MEASUREMENT_ROLE
        assert batch.worker_role == SHARED_ROLE
        assert batch_worker.is_running(), "killing the measurement killed the batch's worker"
        assert pool.peek("P", role=SHARED_ROLE).pid == batch_pid
        assert batch.stage not in (RunStage.FAILED, RunStage.CANCELLED), batch.stage
        # A measurement in another worker shares no word boundary with the
        # batch, so it never shows as having interleaved it.
        assert batch.interleaved_by != measurement.run_id

        await asyncio.wait_for(batch.done.wait(), timeout=60)
        assert batch.stage is RunStage.COMPLETED
        assert batch.words_completed == len(words)
    finally:
        await runner.aclose()


async def test_the_runner_refuses_to_terminate_a_shared_worker_run(wired):
    """The one method that kills a tree is refused for the batch's worker, so
    "a measurement never kills a batch" is the runner's property, not a
    promise each caller keeps."""
    runner = wired(RolePool(shared_delay=0.2, measurement_delay=0.0), grace_window=0.05)
    try:
        batch = await runner.start_run(
            project_name="P", wordforms=["a", "b", "c"], priority=Priority.LOW
        )
        with pytest.raises(ValueError, match="FR-051"):
            await runner.terminate_run(batch.run_id)
        await asyncio.wait_for(batch.done.wait(), timeout=30)
        assert batch.stage is RunStage.COMPLETED
    finally:
        await runner.aclose()


async def test_the_measurement_worker_is_not_left_holding_a_grammar(wired):
    """After a completed measurement its worker is released: one word does
    not leave a second long-lived grammar holder behind."""
    pool = RolePool(shared_delay=0.0, measurement_delay=0.0)
    runner = wired(pool, grace_window=30.0)
    try:
        await measure_word(runner, project_name="P", wordform="pukul", bound_seconds=30)
        assert pool.peek("P", role=MEASUREMENT_ROLE) is None
    finally:
        await runner.aclose()


async def test_the_real_pool_keys_workers_by_project_and_role():
    pool = WorkerPool(stub=True)
    try:
        shared = await pool.get("P")
        measuring = await pool.get("P", role=MEASUREMENT_ROLE)
        assert shared is not measuring
        assert shared.pid != measuring.pid
        assert pool.active_projects() == ["P"], "one project, named once"
        assert sorted(pool.active_workers()) == [("P", MEASUREMENT_ROLE), ("P", SHARED_ROLE)]

        assert await pool.terminate("P", role=MEASUREMENT_ROLE) is True
        assert not measuring.is_running()
        assert shared.is_running(), "terminating one key reached the other"
    finally:
        await pool.aclose()


async def test_two_measurements_on_one_project_each_get_their_own_bound(wired):
    """One measurement key per project, so concurrent measurements are
    serialised: the first one's kill never lands on the second one's word,
    and both come back as results rather than a bare worker error."""
    pool = RolePool(shared_delay=0.0, measurement_delay=60.0)
    runner = wired(pool)
    try:
        first, second = await asyncio.gather(
            measure_word(runner, project_name="P", wordform="pukul", bound_seconds=1.0),
            measure_word(runner, project_name="P", wordform="kirim", bound_seconds=1.0),
        )
    finally:
        await runner.aclose()
    assert first.outcome == second.outcome == "terminated_at_bound"
    assert first.run_id != second.run_id
    assert first.elapsed_seconds >= 1.0 and second.elapsed_seconds >= 1.0
