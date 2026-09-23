#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The batch's on-disk artifact (parser-check CP3, US2; FR-015, FR-016, FR-020,
FR-021, SC-004; contracts/artifact.md).

Two properties, each of which a plausible implementation gets wrong without
any test noticing:

  * PARTIAL STREAMS (FR-020, SC-004). A run killed after its first word leaves
    that word readable, and a reader tolerates the half-written line a kill
    mid-write leaves behind. A buffered writer, or a reader that raises on a
    bad line, loses exactly the tail -- the part a run is usually killed over.

  * THE SHAPE (FR-015, FR-021). A batch writes meta.json, results.jsonl and
    words.txt, and nothing else: no sandbox-spine file, not even an empty one
    (an empty file reads as "that step ran and produced nothing"). And no live
    data-model object is serialized anywhere -- identifiers and text only.

Offline: runner-level tests use an in-process fake worker, and the one
worker-side test feeds `_structured_analysis` fake CLR objects.

Run with:
    python -m pytest tests/test_parse_batch_artifact.py -q
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.priority import Priority  # noqa: E402
from flextoolsmcp.server.parse.record import RunRecord  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402
from flextoolsmcp.server.parse.worker_client import WorkerError  # noqa: E402

FINGERPRINT = {
    "scope_kind": "words",
    "scope_value": ["a", "b", "c"],
    "text_ids": [],
    "word_count": 3,
    "limit": None,
    "truncated": False,
    "engine": "HC",
    "vernacular_ws": "id",
}


def _batch_parse(word):
    return {
        "parsed": True,
        "analysis_count": 1,
        "analyses": [
            {
                "signature": [[f"form-{word}", f"msa-{word}", None]],
                "rendered_morphs": [word],
                "category_labels": ["v"],
                "has_guessed_form": False,
            }
        ],
        "human_analyses": [],
        "error_message": None,
        "parse_time_ms": 3,
    }


class BatchWorker:
    """Answers batch words; can die after N words, the way a killed worker does."""

    def __init__(self, *, die_after=None):
        self.die_after = die_after
        self.parsed = 0
        self.running = True
        self.listeners = {}

    def listen_to_run(self, run_id, listener):
        self.listeners[run_id] = listener

    def stop_listening(self, run_id):
        self.listeners.pop(run_id, None)

    def is_running(self):
        return self.running

    async def parse_word(self, **kwargs):
        if self.die_after is not None and self.parsed >= self.die_after:
            # What `_fail_pending` raises when the worker's stdout closes.
            self.running = False
            raise WorkerError("Parse worker for 'P' closed its channel before answering.")
        self.parsed += 1
        return {"parse": _batch_parse(kwargs["wordform"]), "trace_xml": None}

    async def cancel_run(self, run_id):
        pass


class Pool:
    def __init__(self, worker):
        self.worker = worker

    async def get(self, project_name):
        return self.worker

    def peek(self, project_name):
        return self.worker

    async def aclose(self):
        pass


async def _run_batch(tmp_path, worker, words=("a", "b", "c")):
    runner = ParseRunner(pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=5)
    handle = await runner.start_run(
        project_name="P",
        wordforms=list(words),
        level="batch",
        priority=Priority.LOW,
        scope_fingerprint=FINGERPRINT,
        engine_at_submission="HC",
        vernacular_ws="id",
    )
    await asyncio.wait_for(handle.done.wait(), timeout=5)
    return runner, handle


# ---------------------------------------------------------------------------
# T031 -- FR-020 / SC-004: a killed run leaves every completed word readable
# ---------------------------------------------------------------------------


async def test_a_run_killed_after_its_first_word_leaves_that_word_readable(tmp_path):
    worker = BatchWorker(die_after=1)
    _, handle = await _run_batch(tmp_path, worker)

    assert handle.stage is RunStage.FAILED
    # Read back from DISK, through a fresh record object -- the in-memory
    # handle surviving proves nothing about what a later reader sees.
    record = RunRecord(handle.run_id, record_dir=tmp_path / "runs")
    lines = list(record.iter_results())
    assert [line["wordform"] for line in lines] == ["a"], lines
    assert lines[0]["parse"]["analyses"][0]["signature"] == [["form-a", "msa-a", None]]

    meta = record.read_meta()
    assert meta.words_completed == 1, "meta must agree with the stream it describes"
    assert meta.words_total == 3
    assert meta.stage == RunStage.FAILED.value
    assert meta.failure["stage_at_failure"] == RunStage.PARSING.value


async def test_progress_is_persisted_per_word_not_only_on_stage_change(tmp_path):
    """FR-016: written incrementally. A poll mid-batch reads real progress."""
    seen = []

    class Watching(BatchWorker):
        async def parse_word(self, **kwargs):
            meta = RunRecord(kwargs["run_id"], record_dir=tmp_path / "runs").read_meta()
            seen.append(meta.words_completed)
            return await super().parse_word(**kwargs)

    await _run_batch(tmp_path, Watching())
    assert seen == [0, 1, 2], seen


def test_iter_results_tolerates_a_malformed_trailing_line(tmp_path):
    record = RunRecord.create(project_name="P", words_total=2, record_dir=tmp_path)
    record.append_result({"index": 0, "wordform": "a", "parse": _batch_parse("a")})
    # A kill mid-write: half a JSON object and no newline.
    with open(record.results_path, "a", encoding="utf-8") as handle:
        handle.write('{"index": 1, "wordform": "b", "par')

    lines = list(record.iter_results())
    assert [line["wordform"] for line in lines] == ["a"]


async def test_a_word_that_throws_does_not_end_the_batch(tmp_path):
    """One word failing is recorded; the batch carries on (data-model s.5)."""

    class OneBadWord(BatchWorker):
        async def parse_word(self, **kwargs):
            if kwargs["wordform"] == "b":
                raise WorkerError("RuntimeError: the parser threw on this word")
            return await super().parse_word(**kwargs)

    _, handle = await _run_batch(tmp_path, OneBadWord())
    assert handle.stage is RunStage.COMPLETED
    lines = list(RunRecord(handle.run_id, record_dir=tmp_path / "runs").iter_results())
    assert [line["wordform"] for line in lines] == ["a", "b", "c"]
    assert lines[1]["error"]["message"].startswith("RuntimeError")
    assert handle.counters.NumParseErrors == 1


# ---------------------------------------------------------------------------
# T037 -- FR-015 / FR-021: the shape, and no live references
# ---------------------------------------------------------------------------

SANDBOX_SPINE_NAMES = ("config_generation", "hc_stdout", "hc_output", "config", "stdout")


async def test_a_batch_writes_exactly_the_in_process_files(tmp_path):
    _, handle = await _run_batch(tmp_path, BatchWorker())
    names = sorted(p.name for p in handle.record.root.iterdir())
    assert names == ["meta.json", "results.jsonl", "words.txt"], names


async def test_no_sandbox_spine_file_is_written_or_created_empty(tmp_path):
    _, handle = await _run_batch(tmp_path, BatchWorker())
    for path in handle.record.root.rglob("*"):
        stem = path.stem.lower()
        assert not any(name in stem for name in SANDBOX_SPINE_NAMES), path
        if path.is_file():
            assert path.stat().st_size > 0, f"{path.name} was created empty"


async def test_words_txt_is_the_resolved_list_nfc_one_per_line(tmp_path):
    decomposed = "café"          # e + combining acute
    _, handle = await _run_batch(tmp_path, BatchWorker(), words=("b", decomposed, "a"))
    raw = handle.record.words_path.read_bytes().decode("utf-8")
    assert raw == "b\ncafé\na\n", repr(raw)
    assert handle.record.read_meta().words_path == "words.txt"


def test_a_single_word_run_writes_no_word_list(tmp_path):
    """An empty words.txt would read as 'this run resolved to no words'."""
    record = RunRecord.create(project_name="P", words_total=1, record_dir=tmp_path)
    assert not record.words_path.exists()
    assert record.read_meta().words_path is None


_LIVE_REFERENCE = re.compile(
    r"SIL\.LCModel|System\.__ComObject|<[\w.]+ object at 0x|Python\.Runtime", re.I
)


async def test_no_live_object_reference_is_serialized_anywhere(tmp_path):
    _, handle = await _run_batch(tmp_path, BatchWorker())
    for path in handle.record.root.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        assert not _LIVE_REFERENCE.search(text), f"{path.name}: {text[:200]}"
        if path.suffix == ".json":
            json.loads(text)
        elif path.suffix == ".jsonl":
            for line in text.splitlines():
                json.loads(line)


class _Guid:
    def __init__(self, value):
        self._value = value

    def __str__(self):
        return self._value


class _Obj:
    """A stand-in for a live LCM object: it has a Guid and nothing JSON-able."""

    def __init__(self, guid, **attrs):
        self.Guid = _Guid(guid)
        for key, value in attrs.items():
            setattr(self, key, value)


class _Multi:
    def __init__(self, text):
        self._text = text

    def get_String(self, ws):
        return type("TsString", (), {"Text": self._text})()


def test_the_structured_result_is_reduced_to_identifiers_and_text():
    """The worker side of FR-021: live references in, plain data out."""
    from flextoolsmcp.server.parse.worker_main import _structured_analysis

    form = _Obj("AAAA-1", Form=_Multi("pukul"))
    msa = _Obj("BBBB-2", InterlinearAbbr="v")
    infl = _Obj("CCCC-3")
    morph = type("ParseMorph", (), {
        "Form": form, "Msa": msa, "InflType": infl, "GuessedString": None,
    })()
    analysis = type("ParseAnalysis", (), {"Morphs": [morph]})()

    record = _structured_analysis(analysis, ws=1)

    assert record == {
        "signature": [["aaaa-1", "bbbb-2", "cccc-3"]],
        "rendered_morphs": ["pukul"],
        "category_labels": ["v"],
        "has_guessed_form": False,
    }
    json.dumps(record)  # nothing un-serializable survived


def test_a_guessed_form_is_recorded_not_dropped():
    """FR-031a's residue is carried on the record, per analysis."""
    from flextoolsmcp.server.parse.worker_main import _structured_analysis

    morph = type("ParseMorph", (), {
        "Form": _Obj("f", Form=_Multi("x")), "Msa": _Obj("m"),
        "InflType": None, "GuessedString": "pukul",
    })()
    record = _structured_analysis(type("A", (), {"Morphs": [morph]})(), ws=1)
    assert record["has_guessed_form"] is True
    assert record["signature"] == [["f", "m", None]]
    assert record["rendered_morphs"] == ["pukul"]


# ---------------------------------------------------------------------------
# T053 -- the frozen contract and the shipped record agree
# ---------------------------------------------------------------------------


def test_meta_json_fields_match_the_frozen_artifact_contract():
    """contracts/artifact.md section 3 lists every meta.json field; RunMeta
    ships exactly those. A field added to one and not the other fails here,
    before CP4 or CP5 reads a shape nobody documented."""
    from dataclasses import fields

    from flextoolsmcp.server.parse.record import RunMeta

    contract = (REPO_ROOT / "specs" / "parser-check-cp3" / "contracts" / "artifact.md")
    text = contract.read_text(encoding="utf-8")
    section = text.split("## 3. `meta.json`", 1)[1].split("\n## 4.", 1)[0]
    listed = set()
    for label in ("**CP2b fields**", "**CP3 additions**"):
        paragraph = section.split(label, 1)[1].split("\n\n", 1)[0]
        listed |= set(re.findall(r"`(\w+)`", paragraph))

    assert listed == {f.name for f in fields(RunMeta)}
