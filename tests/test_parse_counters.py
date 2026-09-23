#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The host application's parser-report counters (parser-check CP3, FR-017,
FR-018, FR-019; research.md R-09).

  * FR-017 -- the eight names are adopted VERBATIM, and are checked here
    against the contract file itself, not against a copy typed into this
    test. The deliberate divergences are stated in the ARTIFACT.
  * FR-018 -- TotalUserApprovedAnalysesMissing counts fully linked human
    analyses only. The fixture is built so that the host's own reading (every
    human-approved analysis) gives a different number, and that reading is
    asserted to be wrong here. This is R-09's "trap": the host semantics are
    one line shorter and silently reproduce the category error the tiering
    exists to prevent.
  * FR-019 -- TotalUserNoOpinionAnalyses is never named, presented or
    documented as a count of unreviewed analyses.

Semantics otherwise follow FieldWorks' `ParseReport(IWfiWordform,
ParseResult)` (ParserCore/ParserReport.cs:389-433).

Run with:
    python -m pytest tests/test_parse_counters.py -q
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.record import (  # noqa: E402
    COUNTER_DIVERGENCES,
    HOST_COUNTER_NAMES,
    HostCounters,
    RunRecord,
)

CONTRACT = REPO_ROOT / "specs" / "parser-check-cp3" / "contracts" / "tools.md"


def _contract_counter_names():
    """The fenced block under '## 4. Host counters, verbatim'."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = text.split("## 4. Host counters, verbatim", 1)[1]
    block = section.split("```", 2)[1]
    return tuple(line.strip() for line in block.splitlines() if line.strip())


def _sig(*triples):
    return [list(t) for t in triples]


def _analysis(*triples):
    return {"signature": _sig(*triples), "rendered_morphs": [], "category_labels": [],
            "has_guessed_form": False}


def _human(opinion, *triples, bundle_count=None, complete=None):
    count = len(triples) if bundle_count is None else bundle_count
    return {
        "opinion": opinion,
        "signature": _sig(*triples),
        "bundle_count": count,
        "complete_bundle_count": count if complete is None else complete,
    }


def _line(word, analyses, human=(), error=None, ms=0):
    return {
        "index": 0,
        "wordform": word,
        "parse": {
            "parsed": bool(analyses),
            "analysis_count": len(analyses),
            "analyses": list(analyses),
            "human_analyses": list(human),
            "error_message": error,
            "parse_time_ms": ms,
        },
    }


# ---------------------------------------------------------------------------
# T033 -- FR-017: names verbatim, divergences in the artifact
# ---------------------------------------------------------------------------


def test_the_eight_names_match_the_contract_byte_for_byte():
    assert HOST_COUNTER_NAMES == _contract_counter_names()
    assert list(HostCounters().to_dict()) == list(HOST_COUNTER_NAMES)


def test_counter_divergences_are_written_into_the_artifact(tmp_path):
    record = RunRecord.create(
        project_name="P", words_total=1, record_dir=tmp_path,
        words=["a"], scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
    )
    meta = json.loads(record.meta_path.read_text(encoding="utf-8"))
    assert meta["counter_divergences"] == list(COUNTER_DIVERGENCES)
    assert set(meta["counters"]) == set(HOST_COUNTER_NAMES)
    # Each divergence names the counter it qualifies, first.
    named = [line.split(":", 1)[0] for line in meta["counter_divergences"]]
    assert named == ["TotalUserApprovedAnalysesMissing", "TotalUserNoOpinionAnalyses"]


def test_the_plain_counters_follow_the_host():
    lines = [
        _line("a", [_analysis(("f1", "m1", None)), _analysis(("f2", "m2", None))], ms=5),
        _line("b", [], ms=2),
        _line("c", [], error="Maximum number of analyses reached", ms=1),
    ]
    counters = HostCounters.from_results(lines).to_dict()
    assert counters["NumWords"] == 3
    assert counters["NumParseErrors"] == 1
    assert counters["NumZeroParses"] == 2   # the error word has no analyses either
    assert counters["TotalParseTime"] == 8
    assert counters["TotalAnalyses"] == 2


def test_disapproved_and_no_opinion_follow_the_host_match_rule():
    produced_ok = ("f1", "m1", None)
    produced_bad = ("f2", "m2", None)
    produced_new = ("f3", "m3", None)
    line = _line(
        "a",
        [_analysis(produced_ok), _analysis(produced_bad), _analysis(produced_new)],
        human=[_human("approves", produced_ok), _human("disapproves", produced_bad)],
    )
    counters = HostCounters.from_results([line]).to_dict()
    assert counters["TotalUserDisapprovedAnalyses"] == 1
    assert counters["TotalUserNoOpinionAnalyses"] == 1
    assert counters["TotalUserApprovedAnalysesMissing"] == 0


def test_the_inflection_type_distinguishes_a_match():
    """A two-component match would call these the same analysis."""
    line = _line(
        "a",
        [_analysis(("f", "m", None))],
        human=[_human("approves", ("f", "m", "irregular-past"))],
    )
    counters = HostCounters.from_results([line]).to_dict()
    assert counters["TotalUserApprovedAnalysesMissing"] == 1
    assert counters["TotalUserNoOpinionAnalyses"] == 1


def test_a_result_line_without_analyses_is_not_guessed_at():
    """A CP2b line, or a per-word error, contributes NumWords/NumParseErrors only."""
    lines = [
        {"index": 0, "wordform": "a", "parse": {"parsed": True, "analysis_count": 1}},
        {"index": 1, "wordform": "b", "parse": None, "error": {"message": "boom"}},
    ]
    counters = HostCounters.from_results(lines).to_dict()
    assert counters["NumWords"] == 2
    assert counters["NumParseErrors"] == 1
    assert counters["NumZeroParses"] == 0
    assert counters["TotalAnalyses"] == 0


# ---------------------------------------------------------------------------
# T034 -- FR-018: approved-missing over FULLY LINKED human analyses only
# ---------------------------------------------------------------------------


def _fr018_fixture():
    produced = ("f1", "m1", None)
    return _line(
        "a",
        [_analysis(produced)],
        human=[
            # fully linked, approved, NOT produced -> missing
            _human("approves", ("f9", "m9", None)),
            # meaning only: approved, no decomposition at all
            _human("approves", bundle_count=0),
            # sketched: approved, one of two bundles not linked
            _human("approves", ("f7", None, None), ("f8", "m8", None), complete=1),
            # fully linked, approved, produced -> not missing
            _human("approves", produced),
        ],
    )


def test_approved_missing_counts_fully_linked_analyses_only():
    counters = HostCounters.from_results([_fr018_fixture()]).to_dict()
    assert counters["TotalUserApprovedAnalysesMissing"] == 1


def test_the_host_reading_over_all_human_analyses_is_wrong_here():
    """What an all-human-analyses implementation computes -- and that it fails.

    Mirrors `ParseReport`'s loop exactly: every approved analysis not matched
    by a parser analysis. On this fixture it counts the meaning-only and the
    sketched analyses as parser misses, which they are not.
    """
    line = _fr018_fixture()
    produced = {tuple(map(tuple, a["signature"])) for a in line["parse"]["analyses"]}
    host_reading = sum(
        1
        for record in line["parse"]["human_analyses"]
        if record["opinion"] == "approves"
        and tuple(map(tuple, record["signature"])) not in produced
    )
    ours = HostCounters.from_results([line]).TotalUserApprovedAnalysesMissing
    assert host_reading == 3
    assert ours != host_reading, "an all-human-analyses computation must fail FR-018"


def test_the_divergence_statement_says_fully_linked():
    text = COUNTER_DIVERGENCES[0]
    assert text.startswith("TotalUserApprovedAnalysesMissing:")
    assert "FULLY LINKED" in text


# ---------------------------------------------------------------------------
# T035 -- FR-019: never "unreviewed"
# ---------------------------------------------------------------------------

_UNREVIEWED = re.compile(r"unreviewed|not reviewed|never reviewed|auto.?approved|tacit", re.I)


def test_no_counter_is_named_as_a_review_count():
    for name in HOST_COUNTER_NAMES:
        assert not _UNREVIEWED.search(name), name
        assert "Review" not in name, name


def test_the_no_opinion_divergence_denies_being_an_unreviewed_count():
    text = COUNTER_DIVERGENCES[1]
    assert text.startswith("TotalUserNoOpinionAnalyses:")
    assert "It is NOT a count of unreviewed analyses" in text
    # Every other mention of the idea is inside that denial, never an assertion.
    stripped = text.replace("It is NOT a count of unreviewed analyses", "")
    assert not _UNREVIEWED.search(stripped), stripped


def test_the_split_beside_it_is_affirmed_against_indeterminate():
    """FR-019 / FR-042: the pair is {affirmed, indeterminate}, never tacit."""
    text = COUNTER_DIVERGENCES[1]
    assert "affirmed/indeterminate split" in text
    assert "tacit" not in text.lower()


async def test_a_batch_status_never_labels_the_counter_as_unreviewed(tmp_path):
    """Across the response a caller actually reads, not only the constant."""
    import asyncio

    from flextoolsmcp.server.handlers import parse as parse_handler
    from flextoolsmcp.server.parse.priority import Priority
    from flextoolsmcp.server.parse.runner import ParseRunner

    class Worker:
        def listen_to_run(self, *a):
            pass

        def stop_listening(self, *a):
            pass

        def is_running(self):
            return True

        async def parse_word(self, **kwargs):
            return {"parse": _line("a", [_analysis(("f", "m", None))])["parse"],
                    "trace_xml": None}

    class Pool:
        async def get(self, name):
            return Worker()

        def peek(self, name):
            return None

        async def aclose(self):
            pass

    runner = ParseRunner(pool=Pool(), record_dir=tmp_path / "runs")
    parse_handler.set_runner(runner)
    try:
        handle = await runner.start_run(
            project_name="P", wordforms=["a"], level="batch", priority=Priority.LOW,
            scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
        )
        await asyncio.wait_for(handle.done.wait(), timeout=5)
        response = await parse_handler.handle_flextools_parse_status({"run_id": handle.run_id})
        payload = json.loads(response[0].text)
        assert payload["counters"]["TotalUserNoOpinionAnalyses"] == 1
        body = json.dumps(payload).replace("It is NOT a count of unreviewed analyses", "")
        assert not _UNREVIEWED.search(body), "a response labels no-opinion as unreviewed"
    finally:
        parse_handler.set_runner(None)
