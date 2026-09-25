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
    payload = await _log(record.run_id, "summary")
    assert payload["content"]["stage"] == "completed"


# ===========================================================================
# CP5 T075 (FR-038, SC-009; US5; contracts/tools.md section 7; data-model
# 6.2-6.3) -- the three sandbox sections, filled for sandbox runs.
#
# The response shape these tests require, for a SANDBOX run (meta.spine ==
# "sandbox"; applicability comes from the recorded spine, never from the
# section name alone):
#
#   {"status": "ok", "run_id", "section", "applicable": true,
#    "run_spine": "sandbox",
#    "source": "sandbox/<file>",        # generate-config.log | hc-stdout.txt
#                                       # | hc-output.txt
#    "content": "<the file's text, verbatim>"      -- when the file has text
#    "note": _empty_note(meta, <what>)             -- instead of content when
#                                       # the file is empty or was never
#                                       # written (never an empty section)
#    # config_generation only, from meta.sandbox.generation:
#    "reused_cache": bool, "load_error_count": int, "load_errors": [...]}
#
# For an IN-PROCESS run (spine null or "in_process") every sandbox section is
# today's typed not-applicable response, unchanged (golden below). The
# summary's `run_spine` is read from the meta (`effective_spine`).
# ===========================================================================

_SANDBOX_SECTION_FILES = {
    "config_generation": "generate-config.log",
    "hc_stdout": "hc-stdout.txt",
    "hc_output": "hc-output.txt",
}

_GEN_LOG = (
    "Loading project...\n"
    "Exporting grammar...\n"
    "Writing HermitCrab configuration...\n"
    "Writing completed.\n"
)
_REUSE_LINE = (
    "Reused the cached HermitCrab configuration 3f2a9c0d11e4b7a8 "
    "(generated 2026-09-24T10:00:00Z); the generator did not run.\n"
)
_LOAD_ERRORS = [
    "The allomorph 'xx' of entry 'baca' has an invalid environment '/ _ #['.",
    "The affix template 'Verb slots' refers to a missing slot.",
]
_BANNER = (
    'Reading configuration file "hc-config.xml"... done.\n'
    "Compiling rules... done.\n"
    "Sena Fake loaded.\n"
    "\n"
)
_BLOCKS = (
    'Parsing "membaca"\nParse 1\nMorphs: mem baca\nGloss:  ACT read\n'
    "Parse time: 3ms\n\n"
    'Parsing "xyz"\nNo valid parses.\nParse time: 0ms\n\n'
)


def _sandbox_section_meta(*, reused=False, load_errors=(), mode="parse"):
    return {
        "mode": mode,
        "config_source": {"kind": "project_cache", "cache_key": "3f2a9c0d11e4b7a8"},
        "versions": {"hc_tool": "3.8.1", "fieldworks_hermitcrab": "3.8.2.0",
                     "generate_hc_config": "9.3.11", "hcparse": "5.0.0"},
        "version_skew": False,
        "hc_source": "path",
        "generation": {"reused_cache": reused, "cache_key": "3f2a9c0d11e4b7a8",
                       "load_error_count": len(load_errors),
                       "load_errors": list(load_errors)},
        "copy": {"bytes": 0, "cleanup": "not_made" if reused else "deleted",
                 "path_if_failed": None},
        "hc": {"exit_code": 0, "timed_out": False, "in_flight_index": None,
               "duration_ms": 12, "counters": "ok"},
        "truncated_by_limit": False,
        "advisories": ["grammar_load_errors"] if load_errors else [],
    }


def _sandbox_record(record_dir, words, *, files, results=(), stage="completed",
                    failure=None, **meta):
    record = RunRecord.create(
        project_name="P", words_total=len(words), record_dir=record_dir,
        words=list(words),
        scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
        spine="sandbox", sandbox=_sandbox_section_meta(**meta),
    )
    for name, text in files.items():
        record.write_sandbox_file(name, text)
    for index, word in enumerate(results):
        record.append_result({"index": index, "wordform": word, "parse": {
            "parsed": True, "analysis_count": 1, "outcome": "parsed",
            "analyses": [{"signature": None, "rendered_morphs": [word],
                          "morphs": [{"form": word, "gloss": "X"}],
                          "readable": True, "raw": None}],
            "position": None, "flags": [], "parse_time_ms": 1}})
    record.set_stage(RunStage.LOADING_GRAMMAR)
    if stage == "failed":
        record.set_stage(RunStage.FAILED, failure=failure)
    elif stage == "timed_out":
        record.set_stage(RunStage.PARSING)
        record.set_stage(RunStage.FAILED, failure=failure,
                         words_completed=len(results))
    else:
        record.set_stage(RunStage.PARSING)
        record.set_stage(RunStage.COMPLETED, words_completed=len(results))
    return record


def _four_runs(record_dir):
    """US5's matrix: success, load errors, timeout, broken sandbox."""
    success = _sandbox_record(
        record_dir, ["membaca", "xyz"], results=["membaca", "xyz"],
        files={"generate-config.log": _GEN_LOG,
               "hc-stdout.txt": _BANNER + _BLOCKS + "# of parses: 2, successful: 1, "
               "failed: 1, error: 0\n\n",
               "hc-output.txt": _BLOCKS + "# of parses: 2, successful: 1, failed: 1, "
               "error: 0\n\n"},
    )
    load_errors = _sandbox_record(
        record_dir, ["membaca", "xyz"], results=["membaca", "xyz"],
        load_errors=_LOAD_ERRORS,
        files={"generate-config.log": "Loading project...\n" + "\n".join(_LOAD_ERRORS)
               + "\nWriting completed.\n",
               "hc-stdout.txt": _BANNER + _BLOCKS, "hc-output.txt": _BLOCKS},
    )
    timeout = _sandbox_record(
        record_dir, ["membaca", "xyz", "zzz"], results=["membaca", "xyz"],
        stage="timed_out",
        failure={"stage_at_failure": "parsing", "error_code": "parser_timeout",
                 "message": "hc did not finish within 10 seconds"},
        files={"generate-config.log": _GEN_LOG,
               "hc-stdout.txt": _BANNER + _BLOCKS + 'Parsing "zzz"\n',
               "hc-output.txt": _BLOCKS + 'Parsing "zzz"\n'},
    )
    broken = _sandbox_record(
        record_dir, ["membaca"], stage="failed",
        failure={"stage_at_failure": "loading_grammar", "error_code": "parser_job_failed",
                 "message": "Load Error: The feature 'bogus' is not defined."},
        files={"generate-config.log": _GEN_LOG,
               "hc-stdout.txt": 'Reading configuration file "hc-config.xml"... \n'
               "Load Error: The feature 'bogus' is not defined.\n",
               "hc-output.txt": ""},
    )
    return {"success": success, "load_errors": load_errors, "timeout": timeout,
            "broken": broken}


@pytest.fixture
def quiet_context(monkeypatch):
    """Drop environment-dependent extras from golden responses.

    Clears any prior test's session so ``build_response_with_context`` does
    not append ``session_context`` (and suppresses the workspace notice).
    """
    from flextoolsmcp.server.kernel import reset_session

    monkeypatch.setenv("FLEXTOOLSMCP_NO_WORKSPACE_CHECK", "1")
    reset_session()
    yield
    reset_session()


async def test_every_section_of_the_four_sandbox_runs_is_real_or_typed(record_dir):
    runs = _four_runs(record_dir)
    empties = []
    for label, record in runs.items():
        for section in PARSE_LOG_SECTIONS:
            payload = await _log(record.run_id, section)
            assert payload["status"] == "ok", (label, section, payload)
            if _is_empty(payload):
                empties.append((label, section))
            if section in _SANDBOX_SECTION_FILES:
                assert payload["applicable"] is True, (label, section, payload)
                assert payload.get("reason") != "not_applicable_for_this_spine"
    assert empties == [], f"sections returned empty content: {empties}"


@pytest.mark.parametrize("section", list(_SANDBOX_SECTION_FILES))
async def test_a_sandbox_section_serves_its_file_verbatim(record_dir, section):
    record = _four_runs(record_dir)["success"]
    payload = await _log(record.run_id, section)
    name = _SANDBOX_SECTION_FILES[section]
    assert payload["applicable"] is True
    assert payload["run_spine"] == "sandbox"
    assert payload["source"] == "sandbox/" + name
    assert payload["content"] == record.read_sandbox_file(name)
    assert "section_spine" not in payload and "filled_by" not in payload


async def test_config_generation_itemises_and_counts_load_errors(record_dir):
    record = _four_runs(record_dir)["load_errors"]
    payload = await _log(record.run_id, "config_generation")
    assert payload["load_error_count"] == 2
    assert payload["load_errors"] == _LOAD_ERRORS
    assert payload["reused_cache"] is False
    for error in _LOAD_ERRORS:
        assert error in payload["content"]


async def test_config_generation_with_no_load_errors_says_zero(record_dir):
    record = _four_runs(record_dir)["success"]
    payload = await _log(record.run_id, "config_generation")
    assert payload["load_error_count"] == 0
    assert payload["load_errors"] == []


async def test_a_warm_run_shows_the_reuse_line_first(record_dir):
    record = _sandbox_record(
        record_dir, ["membaca"], results=["membaca"], reused=True,
        files={"generate-config.log": _REUSE_LINE + _GEN_LOG,
               "hc-stdout.txt": _BANNER + _BLOCKS, "hc-output.txt": _BLOCKS},
    )
    payload = await _log(record.run_id, "config_generation")
    assert payload["reused_cache"] is True
    assert payload["content"].splitlines()[0] == _REUSE_LINE.rstrip("\n")
    assert payload["content"].endswith(_GEN_LOG)


async def test_the_timed_out_run_keeps_its_in_flight_header_and_results(record_dir):
    record = _four_runs(record_dir)["timeout"]
    stdout = await _log(record.run_id, "hc_stdout")
    assert stdout["content"].endswith('Parsing "zzz"\n')
    output = await _log(record.run_id, "hc_output")
    assert not output["content"].startswith("Reading configuration file")
    results = await _log(record.run_id, "results")
    assert [line["wordform"] for line in results["items"]] == ["membaca", "xyz"]


async def test_the_broken_sandbox_shows_hc_load_error(record_dir):
    record = _four_runs(record_dir)["broken"]
    stdout = await _log(record.run_id, "hc_stdout")
    assert "Load Error: The feature 'bogus' is not defined." in stdout["content"]
    # hc printed no result blocks: an explained absence, never an empty section.
    output = await _log(record.run_id, "hc_output")
    assert output["applicable"] is True
    assert "content" not in output or output["content"]
    meta = record.read_meta()
    assert output["note"]
    assert output["note"].startswith("No ")
    assert output["note"] == parse_handler._empty_note(meta, output["note"][3:].split(
        " are recorded")[0])


@pytest.mark.parametrize("section", list(_SANDBOX_SECTION_FILES))
async def test_an_empty_or_missing_sandbox_file_gives_the_empty_note(record_dir, section):
    name = _SANDBOX_SECTION_FILES[section]
    empty = _sandbox_record(record_dir, ["a"], results=["a"], files={name: ""})
    missing = _sandbox_record(record_dir, ["a"], results=["a"], files={})
    for record in (empty, missing):
        payload = await _log(record.run_id, section)
        assert payload["applicable"] is True
        assert payload["source"] == "sandbox/" + name
        assert "content" not in payload or payload["content"]
        note = payload["note"]
        assert note.startswith("No ") and "(stage 'completed')" in note
        what = note[3:].split(" are recorded")[0]
        assert note == parse_handler._empty_note(record.read_meta(), what)
        assert not _is_empty(payload)


async def test_a_failed_sandbox_run_explains_a_missing_file_with_its_stage(record_dir):
    record = _sandbox_record(
        record_dir, ["a"], stage="failed", files={},
        failure={"stage_at_failure": "loading_grammar", "message": "generator crashed"},
    )
    payload = await _log(record.run_id, "hc_stdout")
    assert payload["applicable"] is True
    assert "loading_grammar" in payload["note"]


async def test_summary_run_spine_is_read_from_the_meta(record_dir):
    sandbox = _four_runs(record_dir)["success"]
    payload = await _log(sandbox.run_id, "summary")
    assert payload["content"]["run_spine"] == "sandbox"
    assert payload["content"]["spine"] == "sandbox"
    in_process = _completed_run(record_dir)
    payload = await _log(in_process.run_id, "summary")
    assert payload["content"]["run_spine"] == "in_process"


# -- in-process runs: byte-identical to today (FR-038) -----------------------


def _golden_not_applicable(run_id, section):
    """Today's typed not-applicable response, transcribed from the CP3 handler."""
    holds = {
        "config_generation": "the HermitCrab configuration generated from the "
                             "project for a sandboxed run",
        "hc_stdout": "the standard output of a sandboxed HermitCrab process",
        "hc_output": "the output file a sandboxed HermitCrab process writes",
    }[section]
    return {
        "status": "ok",
        "run_id": run_id,
        "section": section,
        "applicable": False,
        "reason": "not_applicable_for_this_spine",
        "run_spine": "in_process",
        "section_spine": "sandbox",
        "filled_by": "CP5",
        "note": (
            f"This section holds {holds}. This run used the in_process spine, "
            "where the parser runs inside the worker and no such file exists, so "
            "the section is not applicable -- it is not empty. The sandbox spine "
            "that produces it arrives at CP5."
        ),
        "_contract": "tool-responses/1.0",
    }


@pytest.mark.parametrize("section", list(_SANDBOX_SECTION_FILES))
@pytest.mark.parametrize("spine", [None, "in_process"])
async def test_in_process_sandbox_sections_are_unchanged(record_dir, quiet_context,
                                                         section, spine):
    record = RunRecord.create(
        project_name="P", words_total=1, record_dir=record_dir, words=["a"],
        scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
        spine=spine,
    )
    payload = await _log(record.run_id, section)
    golden = _golden_not_applicable(record.run_id, section)
    assert list(payload.items()) == list(golden.items())


async def test_a_sandbox_named_run_with_in_process_spine_is_not_filled(record_dir):
    """Applicability is the recorded spine, not the presence of files."""
    record = _completed_run(record_dir)
    record.write_sandbox_file("hc-stdout.txt", "stray\n")
    payload = await _log(record.run_id, "hc_stdout")
    assert payload["applicable"] is False
    assert payload["reason"] == "not_applicable_for_this_spine"


async def test_a_long_sandbox_file_is_capped_and_says_so(record_dir, monkeypatch):
    """Like a raw trace (max_trace_chars): capped inline, the file path given."""
    monkeypatch.setattr(parse_handler, "SANDBOX_LOG_MAX_CHARS", 10)
    record = _sandbox_record(record_dir, ["a"], results=["a"],
                             files={"hc-stdout.txt": _BANNER + _BLOCKS})
    payload = await _log(record.run_id, "hc_stdout")
    full = record.read_sandbox_file("hc-stdout.txt")
    assert payload["content"] == full[:10]
    assert payload["content_truncated"] is True
    assert payload["content_chars"] == len(full)
    assert payload["source_path"].endswith("hc-stdout.txt")


# -- CP5 pattern audit sweep 6: an unreadable meta.json is not absence --------


@pytest.mark.parametrize("section", ["summary", "words", "hc_stdout", "config_generation"])
async def test_an_unreadable_meta_is_a_retryable_error_not_absence(record_dir, monkeypatch,
                                                                  section):
    from flextoolsmcp.server.parse import record as record_mod

    monkeypatch.setattr(record_mod, "META_RETRY_DELAY_SECONDS", 0)
    record = _completed_run(record_dir)
    record.meta_path.write_text("{not json", encoding="utf-8")
    payload = await _log(record.run_id, section)
    assert payload["status"] == "error", payload
    assert payload["error_code"] == "server_state_error"
    assert payload["server_state"] == "run_record_unreadable"
    assert payload.get("applicable") is None  # never "not applicable"
    rungs = payload["next_step"]
    assert rungs and rungs[0]["tool"] == "flextools_parse_log"
    assert rungs[0]["args"]["run_id"] == record.run_id
    assert rungs[0]["args"]["section"] == section
