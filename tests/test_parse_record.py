#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The durable run record (parser-check CP2b, FR-029, SC-008).

Four things are pinned, and they are pinned because each one is a promise
that fails silently rather than loudly when it breaks.

(1) PER-WORD FLUSH, NOT BUFFERED WRITES. SC-008's case is a killed run whose
completed work must still be readable. Buffering loses the tail -- the
results most likely to matter, since a run is usually killed over what it
was doing at the end. `test_each_result_is_readable_from_another_handle_
immediately` is the direct assertion: a second reader sees result N before
result N+1 is written, which buffering would make false.

(2) KILL SURVIVAL. Simulated by reading the on-disk record from a fresh
RunRecord instance after an abrupt stop, with no clean shutdown having run.

(3) THE SIZE CAP. `skeleton_storage` records unbounded growth as known debt
and gets away with it because its payloads are a few lines of Python. A
record of parse traces cannot inherit that (R-07), so the cap is asserted to
exist and to RAISE rather than truncate. Silent truncation would make a
partial run look complete, which is the opposite of what FR-029 is for.

(4) NO CALLER STRING REACHES A PATH COMPONENT. Run ids are server-minted.
The traversal attempts below are the ones a tool argument could actually
carry.

Run with:
    python -m pytest tests/test_parse_record.py -q
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.record import (  # noqa: E402
    InvalidRunId,
    RecordSizeExceeded,
    RunRecord,
    is_valid_run_id,
    new_run_id,
)
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402


@pytest.fixture
def record_dir(tmp_path):
    return tmp_path / "parse-runs"


@pytest.fixture
def record(record_dir):
    return RunRecord.create(
        project_name="TestProject", words_total=3, record_dir=record_dir
    )


# ---------------------------------------------------------------------------
# (1) Per-word flush
# ---------------------------------------------------------------------------


def test_each_result_is_readable_from_another_handle_immediately(record, record_dir):
    """
    The direct assertion that writes are not buffered.

    A second RunRecord over the same directory must see result N before
    result N+1 has been written. Under buffering this is false, and the
    difference only shows up when something dies -- which is why it is
    asserted here rather than left to be discovered by SC-008 failing in
    the field.
    """
    reader = RunRecord(record.run_id, record_dir=record_dir)

    record.append_result({"word": "alpha", "parsed": True})
    assert [r["word"] for r in reader.iter_results()] == ["alpha"], (
        "A separate reader could not see the first result before the second "
        "was written. Results must be flushed per word, not buffered."
    )

    record.append_result({"word": "beta", "parsed": False})
    assert [r["word"] for r in reader.iter_results()] == ["alpha", "beta"]


def test_results_are_appended_in_order(record):
    for word in ("alpha", "beta", "gamma"):
        record.append_result({"word": word})

    assert [r["word"] for r in record.iter_results()] == ["alpha", "beta", "gamma"]


def test_results_file_is_jsonl_one_object_per_line(record):
    record.append_result({"word": "alpha"})
    record.append_result({"word": "beta"})

    lines = record.results_path.read_text(encoding="utf-8").strip().splitlines()

    assert len(lines) == 2
    assert [json.loads(line)["word"] for line in lines] == ["alpha", "beta"]


def test_result_count_matches_what_was_written(record):
    for index in range(5):
        record.append_result({"word": f"w{index}"})

    assert record.result_count() == 5


# ---------------------------------------------------------------------------
# (2) Kill survival -- SC-008
# ---------------------------------------------------------------------------


def test_everything_completed_survives_an_abrupt_stop(record, record_dir):
    """
    The run dies with no clean shutdown; prior results stay readable.

    Modelled by abandoning the writing instance entirely and reading the
    directory fresh -- no close, no flush-on-exit, no teardown.
    """
    for word in ("alpha", "beta", "gamma"):
        record.append_result({"word": word, "parsed": True})

    del record  # nothing runs on the way out

    survivor = RunRecord(_only_run_id(record_dir), record_dir=record_dir)

    assert [r["word"] for r in survivor.iter_results()] == [
        "alpha",
        "beta",
        "gamma",
    ], "Completed results did not survive an abrupt stop (SC-008)."


def test_a_truncated_final_line_does_not_lose_the_earlier_results(
    record, record_dir
):
    """
    A run killed mid-write leaves a partial last line.

    Everything BEFORE it must still read. Raising on the malformed line
    would throw away exactly the results this module exists to preserve --
    the failure would be total rather than partial, which is strictly worse
    than the situation it is reporting.
    """
    record.append_result({"word": "alpha"})
    record.append_result({"word": "beta"})
    with open(record.results_path, "a", encoding="utf-8") as handle:
        handle.write('{"word": "gam')  # killed mid-write

    reader = RunRecord(record.run_id, record_dir=record_dir)

    assert [r["word"] for r in reader.iter_results()] == ["alpha", "beta"]


def test_meta_survives_and_reports_the_stage_it_died_in(record, record_dir):
    record.set_stage(RunStage.LOADING_GRAMMAR)

    reader = RunRecord(record.run_id, record_dir=record_dir)

    assert reader.read_meta().stage == "loading_grammar"


def test_meta_is_rewritten_not_appended(record):
    """Current state, not history -- status polls must stay O(1)."""
    record.set_stage(RunStage.LOADING_GRAMMAR)
    record.set_stage(RunStage.PARSING)

    data = json.loads(record.meta_path.read_text(encoding="utf-8"))

    assert data["stage"] == "parsing"
    assert isinstance(data, dict), "meta.json must be one object, not a log"


def test_partial_progress_is_recorded_alongside_a_cancel(record):
    record.append_result({"word": "alpha"})
    record.set_stage(
        RunStage.CANCELLED, words_completed=1, stage_at_cancel="parsing"
    )

    meta = record.read_meta()
    assert meta.stage == "cancelled"
    assert meta.words_completed == 1
    assert meta.stage_at_cancel == "parsing"
    assert record.result_count() == 1, (
        "A cancelled run must leave its completed work readable (FR-029)."
    )


# ---------------------------------------------------------------------------
# (3) The size cap
# ---------------------------------------------------------------------------


def test_size_cap_raises_rather_than_truncating(record_dir):
    """
    Silent truncation would make a partial run look complete.

    That is the opposite of FR-029's guarantee, so the cap is loud.
    """
    record = RunRecord.create(record_dir=record_dir, max_bytes=2048)

    with pytest.raises(RecordSizeExceeded) as excinfo:
        for index in range(1000):
            record.append_result({"word": f"w{index}", "padding": "x" * 200})

    assert "size cap" in str(excinfo.value)
    assert "truncated" in str(excinfo.value)


def test_results_written_before_the_cap_remain_readable(record_dir):
    """Hitting the cap must not invalidate what was already recorded."""
    record = RunRecord.create(record_dir=record_dir, max_bytes=2048)

    with pytest.raises(RecordSizeExceeded):
        for index in range(1000):
            record.append_result({"word": f"w{index}", "padding": "x" * 200})

    assert record.result_count() > 0, (
        "Hitting the size cap discarded the results already written."
    )


def test_trace_writes_are_also_capped(record_dir):
    """Traces are the large payload; the cap would be pointless otherwise."""
    record = RunRecord.create(record_dir=record_dir, max_bytes=4096)

    with pytest.raises(RecordSizeExceeded):
        for index in range(100):
            record.write_trace(index, "<trace>" + "x" * 500 + "</trace>")


def test_a_cap_of_zero_disables_the_check(record_dir):
    """An explicit opt-out, for a caller that has its own bound."""
    record = RunRecord.create(record_dir=record_dir, max_bytes=0)

    for index in range(50):
        record.append_result({"word": f"w{index}", "padding": "x" * 200})

    assert record.result_count() == 50


# ---------------------------------------------------------------------------
# (4) No caller string reaches a path component
# ---------------------------------------------------------------------------


def test_run_ids_are_server_minted_hex():
    run_id = new_run_id()

    assert is_valid_run_id(run_id)
    assert len(run_id) == 32
    assert all(c in "0123456789abcdef" for c in run_id)


def test_two_run_ids_differ():
    assert new_run_id() != new_run_id()


@pytest.mark.parametrize(
    "hostile",
    [
        "../../etc/passwd",
        "..\\..\\windows\\system32",
        "/absolute/path",
        "C:\\Windows",
        "run id with spaces",
        "",
        "../" + "a" * 29,
        "NOTHEX" + "0" * 26,
        "0" * 31,  # right alphabet, wrong length
        "0" * 33,
    ],
)
def test_a_caller_string_is_refused_as_a_run_id(hostile, record_dir):
    """
    The traversal guard, exercised with what a tool argument could carry.

    `flextools_parse_status` takes a run_id straight from the caller, so
    this is not hypothetical: it is the one place a caller string is
    adjacent to a filesystem path.
    """
    assert not is_valid_run_id(hostile)
    with pytest.raises(InvalidRunId):
        RunRecord(hostile, record_dir=record_dir)


def test_the_run_directory_stays_inside_the_record_root(record, record_dir):
    assert record.root.parent == record_dir
    assert record.root.name == record.run_id


def test_trace_index_is_coerced_to_an_int(record):
    """A trace filename is built from an int, never a string."""
    path = record.write_trace(7, "<trace/>")

    assert path.name == "7.xml"
    assert path.parent == record.traces_dir


# ---------------------------------------------------------------------------
# Traces out of line
# ---------------------------------------------------------------------------


def test_traces_are_written_out_of_line(record):
    """
    Not inlined into results.jsonl.

    A full trace is XML in the tens or hundreds of kilobytes; inlining one
    into a response makes it unreadable and may overflow the transport.
    """
    record.write_trace(0, "<trace>big payload</trace>")
    record.append_result({"word": "alpha", "trace_index": 0})

    results_text = record.results_path.read_text(encoding="utf-8")

    assert "big payload" not in results_text, (
        "The trace payload was inlined into results.jsonl. Traces are stored "
        "out of line and referenced by index."
    )
    assert record.read_trace(0) == "<trace>big payload</trace>"


def test_reading_a_missing_trace_is_none_not_an_error(record):
    assert record.read_trace(99) is None


# ---------------------------------------------------------------------------
# Basic lifecycle
# ---------------------------------------------------------------------------


def test_a_new_record_starts_at_stage_starting(record):
    assert record.read_meta().stage == "starting"
    assert record.exists()


def test_create_records_the_project_and_word_total(record):
    meta = record.read_meta()

    assert meta.project_name == "TestProject"
    assert meta.words_total == 3
    assert meta.words_completed == 0


def test_reading_meta_for_a_run_with_no_record_is_none(record_dir):
    assert RunRecord(new_run_id(), record_dir=record_dir).read_meta() is None


def _only_run_id(record_dir: Path) -> str:
    """The single run id under a fresh record dir."""
    ids = [p.name for p in record_dir.iterdir() if p.is_dir()]
    assert len(ids) == 1, f"Expected exactly one run record, found {ids}"
    return ids[0]
