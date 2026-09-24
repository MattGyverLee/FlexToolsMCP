#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_parse_log -- reading a run back (parser-check CP3, US3; FR-028,
FR-029, FR-024, SC-007).

  * The seven section names, exactly, transcribed from contracts/tools.md
    (read from the contract file, not typed here).
  * 0 sections return empty content (SC-007): every section is real content,
    a typed not-applicable, or an explained absence.
  * The three sandbox sections name the spine and the checkpoint that fills
    them (FR-028).
  * An unreadable trace comes back raw and labelled raw (FR-029).
  * The log tool never calls the engine check -- it reads the artifact
    (FR-024). Asserted with a runner whose worker explodes if touched.

Run with:
    python -m pytest tests/test_parse_log_sections.py -q
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.models import PARSE_LOG_SECTIONS, ParseLogInput  # noqa: E402
from flextoolsmcp.server.parse.record import RunRecord  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402

CONTRACT = REPO_ROOT / "specs" / "parser-check-cp3" / "contracts" / "tools.md"

A_REAL_TRACE = """<Wordform form="membuat">
  <Analysis/>
  <WordAnalysisTrace>
    <InputWord>membuat</InputWord>
    <MorphologicalRuleAnalysisTrace>
      <MorphologicalRule id="7">meN- prefix</MorphologicalRule>
      <FailureReason type="environment"><Environment>/ _ b</Environment></FailureReason>
    </MorphologicalRuleAnalysisTrace>
    <MorphologicalRuleSynthesisTrace>
      <MorphologicalRule id="7">meN- prefix</MorphologicalRule>
      <FailureReason type="environment"><Environment>/ _ p</Environment></FailureReason>
    </MorphologicalRuleSynthesisTrace>
    <MorphologicalRuleSynthesisTrace>
      <MorphologicalRule id="9">-kan suffix</MorphologicalRule>
      <FailureReason type="pos"><Pos>n</Pos><RequiredPos>v</RequiredPos></FailureReason>
    </MorphologicalRuleSynthesisTrace>
    <ParseCompleteTrace success="true"/>
  </WordAnalysisTrace>
</Wordform>"""


class ExplodingPool:
    """Any attempt to reach a worker -- and so the engine -- fails the test."""

    async def get(self, name):
        raise AssertionError("flextools_parse_log reached a worker (FR-024)")

    def peek(self, name):
        raise AssertionError("flextools_parse_log reached a worker (FR-024)")

    async def aclose(self):
        pass


@pytest.fixture
def record_dir(tmp_path):
    runner = ParseRunner(pool=ExplodingPool(), record_dir=tmp_path / "runs")
    parse_handler.set_runner(runner)
    yield tmp_path / "runs"
    parse_handler.set_runner(None)


def _completed_run(record_dir, *, trace=A_REAL_TRACE):
    record = RunRecord.create(
        project_name="P", words_total=2, record_dir=record_dir, words=["membuat", "buat"],
        scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
    )
    record.append_result({"index": 0, "wordform": "membuat",
                          "parse": {"parsed": True, "analysis_count": 1, "analyses": []}})
    record.append_result({"index": 1, "wordform": "buat",
                          "parse": {"parsed": True, "analysis_count": 1, "analyses": []}})
    if trace is not None:
        record.write_trace(0, trace)
    record.set_stage(RunStage.PARSING)
    record.set_stage(RunStage.COMPLETED, words_completed=2)
    return record


async def _log(run_id, section, **extra):
    response = await parse_handler.handle_flextools_parse_log(
        ParseLogInput(run_id=run_id, section=section, **extra).model_dump()
    )
    return json.loads(response[0].text)


def _is_empty(payload):
    """What 'empty content' means: nothing to show AND nothing saying why."""
    has_content = any(
        payload.get(key) for key in ("content", "items", "raw", "summary_line")
    )
    return not has_content and not payload.get("note")


# ---------------------------------------------------------------------------
# T054 -- the seven names, and SC-007's 0 empty sections
# ---------------------------------------------------------------------------


def test_the_seven_section_names_match_the_contract_exactly():
    text = CONTRACT.read_text(encoding="utf-8")
    block = text.split("Sections, exactly these:", 1)[1].split("```", 2)[1]
    contract = tuple(name.strip() for name in block.strip().split("|"))
    assert PARSE_LOG_SECTIONS == contract
    schema = ParseLogInput.model_json_schema()["properties"]["section"]["enum"]
    assert tuple(schema) == contract


async def test_no_section_of_a_completed_run_is_empty(record_dir):
    record = _completed_run(record_dir)
    empties = []
    for section in PARSE_LOG_SECTIONS:
        payload = await _log(record.run_id, section)
        assert payload["status"] == "ok", (section, payload)
        if _is_empty(payload):
            empties.append(section)
    assert empties == [], f"sections returned empty content: {empties}"


async def test_no_section_of_a_run_that_died_before_its_first_word_is_empty(record_dir):
    record = RunRecord.create(
        project_name="P", words_total=3, record_dir=record_dir, words=["a", "b", "c"],
        scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
    )
    record.set_stage(RunStage.LOADING_GRAMMAR)
    record.set_stage(RunStage.FAILED, failure={"stage_at_failure": "loading_grammar",
                                               "message": "out of memory"})
    for section in PARSE_LOG_SECTIONS:
        payload = await _log(record.run_id, section)
        assert not _is_empty(payload), (section, payload)
    results = await _log(record.run_id, "results")
    assert results["items"] == []
    assert "loading_grammar" in results["note"]


async def test_summary_carries_the_run_record(record_dir):
    record = _completed_run(record_dir)
    payload = await _log(record.run_id, "summary")
    content = payload["content"]
    assert content["stage"] == "completed"
    assert content["engine_at_submission"] == "HC"
    assert content["counter_divergences"]
    assert content["results_recorded"] == 2
    assert content["traces_recorded"] == [0]


async def test_words_and_results_are_paged(record_dir):
    record = _completed_run(record_dir)
    first = await _log(record.run_id, "words", offset=0, limit=1)
    assert first["items"] == ["membuat"] and first["next_offset"] == 1
    assert first["source"] == "words.txt"
    second = await _log(record.run_id, "results", offset=1, limit=1)
    assert [line["wordform"] for line in second["items"]] == ["buat"]
    assert second["next_offset"] is None


async def test_a_single_word_run_serves_words_from_its_results(record_dir):
    record = RunRecord.create(project_name="P", words_total=1, record_dir=record_dir)
    record.append_result({"index": 0, "wordform": "solo", "parse": {"parsed": False}})
    payload = await _log(record.run_id, "words")
    assert payload["items"] == ["solo"]
    assert "results.jsonl" in payload["source"]


async def test_an_unknown_run_is_parse_run_not_found(record_dir):
    payload = await _log("f" * 32, "summary")
    assert payload["error_code"] == "parse_run_not_found"
    malformed = await _log("../../etc", "summary")
    assert malformed["error_code"] == "parse_run_not_found"


# ---------------------------------------------------------------------------
# T055 -- sandbox sections are typed not-applicable, naming spine + checkpoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("section", ["config_generation", "hc_stdout", "hc_output"])
async def test_sandbox_sections_are_typed_not_applicable(record_dir, section):
    record = _completed_run(record_dir)
    payload = await _log(record.run_id, section)
    assert payload["applicable"] is False
    assert payload["reason"] == "not_applicable_for_this_spine"
    assert payload["run_spine"] == "in_process"
    assert payload["section_spine"] == "sandbox"
    assert payload["filled_by"] == "CP5"
    assert "CP5" in payload["note"] and "not empty" in payload["note"]
    assert "items" not in payload and "content" not in payload


# ---------------------------------------------------------------------------
# T056 -- FR-029: a readable trace gets one line; an unreadable one is raw
# ---------------------------------------------------------------------------


async def test_a_readable_trace_names_the_most_frequent_rejection(record_dir):
    record = _completed_run(record_dir)
    payload = await _log(record.run_id, "trace", trace_index=0)
    assert payload["format"] == "parsed"
    assert payload["rejections"] == 3
    assert payload["rejections_by_type"] == {"environment": 2, "pos": 1}
    line = payload["summary_line"]
    assert "'environment' (2)" in line
    assert "meN- prefix" in line
    assert "\n" not in line, "one line"


async def test_an_unreadable_trace_is_returned_raw_and_labelled_raw(record_dir):
    garbage = "HC exploded <<< not xml at all"
    record = _completed_run(record_dir, trace=garbage)
    payload = await _log(record.run_id, "trace", trace_index=0)
    assert payload["format"] == "raw"
    assert payload["raw"] == garbage
    assert "raw" in payload["note"]
    for invented in ("summary_line", "rejections", "rejections_by_type"):
        assert invented not in payload, f"{invented} invented for an unreadable trace"


async def test_xml_that_is_not_a_trace_is_also_raw(record_dir):
    record = _completed_run(record_dir, trace="<trace stub='1' word='x'></trace>")
    payload = await _log(record.run_id, "trace", trace_index=0)
    assert payload["format"] == "raw"


async def test_a_run_with_no_trace_says_why(record_dir):
    record = _completed_run(record_dir, trace=None)
    payload = await _log(record.run_id, "trace")
    assert payload["available_traces"] == []
    assert "never traced in bulk" in payload["note"]


async def test_asking_for_a_trace_that_was_not_taken_names_the_ones_that_were(record_dir):
    record = _completed_run(record_dir)
    payload = await _log(record.run_id, "trace", trace_index=1)
    assert payload["available_traces"] == [0]
    assert "raw" not in payload


async def test_a_long_raw_trace_is_capped_and_says_so(record_dir):
    record = _completed_run(record_dir, trace="x" * 5000)
    payload = await _log(record.run_id, "trace", trace_index=0, max_trace_chars=1000)
    assert len(payload["raw"]) == 1000
    assert payload["raw_truncated"] is True
    assert payload["trace_chars"] == 5000


# ---------------------------------------------------------------------------
# T057 -- FR-024: the log tool never calls the engine check
# ---------------------------------------------------------------------------


async def test_every_section_is_served_without_touching_a_worker(record_dir):
    """ExplodingPool raises on any worker access; every section still answers."""
    record = _completed_run(record_dir)
    for section in PARSE_LOG_SECTIONS:
        payload = await _log(record.run_id, section)
        assert payload["status"] == "ok", section


def test_the_log_handler_source_never_names_the_engine_check():
    import inspect

    for function in (
        parse_handler.handle_flextools_parse_log,
        parse_handler._trace_section,
        parse_handler.summarize_trace_xml,
        parse_handler._log_record,
    ):
        source = inspect.getsource(function)
        for forbidden in ("check_engine", "check_active_parser", "preflight", "pool.get"):
            assert forbidden not in source, f"{function.__name__} names {forbidden}"


async def test_a_run_from_an_earlier_server_process_is_readable(record_dir):
    """The artifact, not the in-memory handle, is what the log tool reads."""
    record = _completed_run(record_dir)
    # A fresh runner that has never heard of this run.
    parse_handler.set_runner(ParseRunner(pool=ExplodingPool(), record_dir=record_dir))
    try:
        payload = await _log(record.run_id, "summary")
        assert payload["content"]["stage"] == "completed"
    finally:
        parse_handler.set_runner(None)
