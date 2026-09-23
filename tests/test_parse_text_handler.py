#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_parse_text -- the batch tool's surface (parser-check CP3, US2;
FR-014, FR-024, FR-025, FR-002; D-1).

  * FR-024 -- the engine gate is the handler's FIRST project-touching
    statement: nothing is resolved and nothing is queued before it, and a
    mismatch refuses with no scope read and no run created.
  * FR-025 / D-1 -- annotated destructive from the first release, the filing
    argument ABSENT from the schema (and refused if guessed at), and the
    description's first line states the spine and that filing is not yet
    reachable.
  * FR-002 -- a scope that matched texts but yielded no words starts no run
    and is not reported as `parse_scope_empty`.

Offline: a fake worker behind a real ParseRunner.

Run with:
    python -m pytest tests/test_parse_text_handler.py -q
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.models import ParseTextInput  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.worker_client import WorkerError  # noqa: E402


def _resolved(words, **overrides):
    data = {
        "scope_kind": "words",
        "scope_value": sorted(words),
        "text_ids": [],
        "words": list(words),
        "count_before_limit": len(words),
        "limit": None,
        "truncated": False,
        "vernacular_ws": "id",
        "never_tokenized_text_ids": [],
        "unreadable_wordform_count": 0,
        "notes": [],
    }
    data.update(overrides)
    return data


class Worker:
    def __init__(self, *, engine_error=None, scope_error=None, resolved=None):
        self.calls = []
        self.engine_error = engine_error
        self.scope_error = scope_error
        self.resolved = resolved
        self.parse_kwargs = []

    def listen_to_run(self, *a):
        pass

    def stop_listening(self, *a):
        pass

    def is_running(self):
        return True

    async def check_engine(self, **kwargs):
        self.calls.append("check_engine")
        if self.engine_error:
            raise self.engine_error
        return "HC"

    async def resolve_scope(self, **kwargs):
        self.calls.append("resolve_scope")
        if self.scope_error:
            raise self.scope_error
        return self.resolved or _resolved(kwargs["scope"]["value"])

    async def parse_word(self, **kwargs):
        self.calls.append("parse_word")
        self.parse_kwargs.append(kwargs)
        return {"parse": {"parsed": True, "analysis_count": 0, "analyses": [],
                          "human_analyses": [], "error_message": None,
                          "parse_time_ms": 0}, "trace_xml": None}

    async def cancel_run(self, run_id):
        pass


class Pool:
    def __init__(self, worker):
        self.worker = worker

    async def get(self, name):
        return self.worker

    def peek(self, name):
        return self.worker

    async def aclose(self):
        pass


@pytest.fixture
def runner_for(tmp_path, monkeypatch):
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    made = []

    def make(worker):
        runner = ParseRunner(pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=5)
        parse_handler.set_runner(runner)
        made.append(runner)
        return runner

    yield make
    parse_handler.set_runner(None)


async def _call(args):
    response = await parse_handler.handle_flextools_parse_text(args)
    return json.loads(response[0].text)


def _mismatch():
    exc = WorkerError("engine")
    exc.error_code = "parser_engine_mismatch"
    exc.detail = {
        "error_code": "parser_engine_mismatch",
        "configured_engine": "XAmple",
        "supported_engines": ["HC"],
        "hint": "This project's active parser is 'XAmple'...",
    }
    return exc


# ---------------------------------------------------------------------------
# FR-024 -- the gate first, once
# ---------------------------------------------------------------------------


async def test_the_engine_gate_runs_before_anything_else_is_asked(runner_for):
    worker = Worker()
    runner = runner_for(worker)
    payload = await _call({"scope_kind": "words", "scope_value": ["a", "b"]})
    await asyncio.wait_for(runner.get(payload["run_id"]).done.wait(), timeout=5)

    assert worker.calls[0] == "check_engine"
    assert worker.calls[1] == "resolve_scope"
    assert worker.calls.count("check_engine") == 1, "once, at submission"
    assert worker.calls[2:] == ["parse_word", "parse_word"]


async def test_an_engine_mismatch_refuses_before_the_scope_is_read(runner_for, tmp_path):
    worker = Worker(engine_error=_mismatch())
    runner = runner_for(worker)
    payload = await _call({"scope_kind": "all_texts"})

    assert payload["error_code"] == "parser_engine_mismatch"
    assert payload["configured_engine"] == "XAmple"
    assert worker.calls == ["check_engine"], "nothing resolved, nothing queued"
    assert runner.known_run_ids() == []
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


async def test_batch_words_carry_the_submission_engine(runner_for):
    worker = Worker()
    runner = runner_for(worker)
    payload = await _call({"scope_kind": "words", "scope_value": ["a"]})
    await asyncio.wait_for(runner.get(payload["run_id"]).done.wait(), timeout=5)
    sent = worker.parse_kwargs[0]
    assert sent["engine_at_submission"] == "HC"
    assert sent["level"] == "batch"
    assert sent["vernacular_ws"] == "id"


async def test_the_batch_runs_at_the_low_priority_path(runner_for):
    from flextoolsmcp.server.parse.priority import Priority

    worker = Worker()
    runner = runner_for(worker)
    payload = await _call({"scope_kind": "words", "scope_value": ["a"]})
    handle = runner.get(payload["run_id"])
    await asyncio.wait_for(handle.done.wait(), timeout=5)
    assert handle.priority is Priority.LOW
    assert worker.parse_kwargs[0]["priority"] == int(Priority.LOW)


# ---------------------------------------------------------------------------
# The response
# ---------------------------------------------------------------------------


async def test_a_submission_records_the_fingerprint_and_says_nothing_was_filed(runner_for):
    worker = Worker()
    runner = runner_for(worker)
    payload = await _call({"scope_kind": "words", "scope_value": ["b", "a"]})
    handle = runner.get(payload["run_id"])
    await asyncio.wait_for(handle.done.wait(), timeout=5)

    assert payload["status"] == "ok"
    assert payload["filing"] == parse_handler.FILING_NOT_REACHABLE
    fingerprint = payload["scope_fingerprint"]
    assert fingerprint["engine"] == "HC"
    assert fingerprint["vernacular_ws"] == "id"
    meta = handle.record.read_meta()
    assert meta.scope_fingerprint == fingerprint
    assert meta.engine_at_submission == "HC"
    assert handle.record.read_words() == ["b", "a"]


async def test_scope_refusals_are_re_emitted_unchanged(runner_for):
    exc = WorkerError("empty")
    exc.error_code = "parse_scope_empty"
    exc.detail = {
        "error_code": "parse_scope_empty",
        "scope": {"kind": "genre", "value": "Folklore"},
        "matched_texts": [],
        "hint": "No genre on any text matches 'Folklore'.",
    }
    worker = Worker(scope_error=exc)
    runner = runner_for(worker)
    payload = await _call({"scope_kind": "genre", "scope_value": "Folklore"})

    assert payload["error_code"] == "parse_scope_empty"
    assert payload["matched_texts"] == []
    assert "parse_word" not in worker.calls
    assert runner.known_run_ids() == []


async def test_texts_with_no_words_start_no_run_and_are_not_called_empty(runner_for):
    """FR-002: never parse_scope_empty for a text that matched."""
    worker = Worker(resolved=_resolved(
        [], scope_kind="text", scope_value="Story", text_ids=[7],
        never_tokenized_text_ids=[7],
        notes=["Some selected texts have paragraphs but no wordforms were found."],
    ))
    runner = runner_for(worker)
    payload = await _call({"scope_kind": "text", "scope_value": "Story"})

    assert payload["status"] == "ok"
    assert payload["run_started"] is False
    assert payload["never_tokenized_text_ids"] == [7]
    assert "error_code" not in payload
    assert runner.known_run_ids() == []
    assert "no words" not in json.dumps(payload).lower()


# ---------------------------------------------------------------------------
# FR-025 / D-1 -- schema and annotation
# ---------------------------------------------------------------------------

_FILING_WORDS = ("file", "filing", "write", "commit", "record_to_project", "apply")


def test_the_filing_argument_is_absent_from_the_schema():
    properties = ParseTextInput.model_json_schema()["properties"]
    assert set(properties) == {
        "scope_kind", "scope_value", "limit", "vernacular_ws", "project_name",
    }
    for name in properties:
        assert not any(word in name for word in _FILING_WORDS), name


def test_a_guessed_filing_argument_is_refused_not_ignored():
    with pytest.raises(Exception):
        ParseTextInput(scope_kind="all_texts", file_results=True)


def test_scope_kind_and_value_are_validated_together():
    with pytest.raises(Exception):
        ParseTextInput(scope_kind="genre")
    with pytest.raises(Exception):
        ParseTextInput(scope_kind="all_texts", scope_value="x")


def test_the_tool_is_annotated_at_its_designed_maximum_capability():
    from flextoolsmcp.server.tool_definitions import TOOLS

    tool = TOOLS["flextools_parse_text"]
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is True
    assert tool.input_model is ParseTextInput


def test_the_description_first_line_states_the_spine_and_that_filing_is_unreachable():
    from flextoolsmcp.server.tool_definitions import TOOLS

    first = TOOLS["flextools_parse_text"].description.splitlines()[0]
    assert "In-process" in first and "spine" in first
    assert "filing" in first and "not yet reachable" in first


def test_the_tool_is_routed():
    from flextoolsmcp.server import dispatch

    handler, model = dispatch.DISPATCH_ROUTES["flextools_parse_text"]
    assert handler is parse_handler.handle_flextools_parse_text
    assert model is ParseTextInput
