#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The oracle's wording (parser-check CP3, US5; FR-040..FR-042, SC-011..SC-013).

  * All six mandated sentences, and the population sentence, render
    BYTE-EXACT -- read from contracts/tools.md section 3 itself, not typed
    here, so drift between the code and the contract fails (T076).
  * "invalid", "incorrect", "rejected", "flagged" appear 0 times in
    connection with an analysis carrying no stored opinion, scanned over
    every emitted response rather than asserted by review (T077).
  * 0 analyses are labelled tacit / unreviewed / auto_approved anywhere, and
    the split is exactly {affirmed, indeterminate} (T078).
  * An OFFLINE fixture for a never-parsed project: the oracle is absent with
    its own sentence, and 0 degenerate all-unreviewed reports (T079).

Run with:
    python -m pytest tests/test_signals_oracle_wording.py -q
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.signals import oracle  # noqa: E402
from flextoolsmcp.server.signals.oracle import (  # noqa: E402
    build_oracle,
    describe_analysis,
    segment_occurrence,
)
from fixtures.signals_runs import (  # noqa: E402
    NEVER_PARSED_STATE,
    PARSED_STATE,
    every_case_lines,
    find_report,
    line,
    parser_analysis,
    stored,
    summary_response,
    walk,
    write_run,
)

CONTRACT = REPO_ROOT / "specs" / "parser-check-cp3" / "contracts" / "tools.md"

FORBIDDEN = ("invalid", "incorrect", "rejected", "flagged")
FORBIDDEN_LABELS = ("tacit", "unreviewed", "auto_approved")


def _contract_sentences():
    """{heading: sentence} from section 3's fenced blocks, in order."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = text.split("## 3. Mandated oracle wording", 1)[1].split("### Forbidden words", 1)[0]
    section = section.replace("\r\n", "\n")
    pairs = re.findall(r"^\*\*([^*\n]+?):\*\*\n```\n(.+?)\n```", section, flags=re.S | re.M)
    return {heading: body for heading, body in pairs}


EXPECTED = {
    "Approved and not in any segment": "SENTENCE_APPROVED",
    "Approved but occurring in a segment": "SENTENCE_APPROVED_IN_TEXT",
    "Disapproved": "SENTENCE_DISAPPROVED",
    "No stored opinion": "SENTENCE_NO_OPINION",
    "Meaning only": "SENTENCE_MEANING_ONLY",
    "Sketched but unlinked": "SENTENCE_SKETCHED",
    "Mandatory population sentence": "SENTENCE_POPULATION",
}


@pytest.fixture
def record_dir(tmp_path):
    class NoPool:
        async def get(self, name):
            raise AssertionError("the report reached a worker")

        def peek(self, name):
            raise AssertionError("the report reached a worker")

        async def aclose(self):
            pass

    parse_handler.set_runner(ParseRunner(pool=NoPool(), record_dir=tmp_path / "runs"))
    parse_handler.reset_drill_down()
    yield tmp_path / "runs"
    parse_handler.set_runner(None)
    parse_handler.reset_drill_down()


# ---------------------------------------------------------------------------
# T076 -- byte-exact against the contract file
# ---------------------------------------------------------------------------


def test_the_contract_holds_exactly_the_seven_blocks_we_transcribe():
    assert set(_contract_sentences()) == set(EXPECTED)


@pytest.mark.parametrize("heading, constant", sorted(EXPECTED.items()))
def test_each_template_is_byte_exact_with_the_contract(heading, constant):
    assert getattr(oracle, constant) == _contract_sentences()[heading]


def _expected(heading, **values):
    out = _contract_sentences()[heading]
    for key, value in values.items():
        out = out.replace(f"[{key}]", str(value))
    return out


def test_all_six_cases_render_the_contract_sentence_substituted():
    by_guid = {}
    for l in every_case_lines():
        for record in l["parse"]["human_analyses"]:
            by_guid[record["analysis_guid"]] = describe_analysis(record)["sentence"]

    who = {"user": "Ana", "date": "2026-03-01"}
    assert by_guid["g-affirmed"] == _expected("Approved and not in any segment", **who)
    assert by_guid["g-inuse"] == _expected("Approved but occurring in a segment", **who)
    assert by_guid["g-disliked"] == _expected("Disapproved", **who)
    assert by_guid["g-unchecked"] == _expected("No stored opinion")
    assert by_guid["g-meaning"] == _expected("Meaning only")
    assert by_guid["g-sketched"] == _expected("Sketched but unlinked", N=2, M=3)


def test_the_population_sentence_is_rendered_with_its_counts():
    block = build_oracle(every_case_lines(), PARSED_STATE)
    assert block["population_sentence"] == _expected("Mandatory population sentence", N=2, M=1)


def test_the_rendered_sentences_reach_the_caller_unchanged(record_dir):
    record = write_run(record_dir, every_case_lines())
    report = find_report(summary_response(record.run_id))
    text = json.dumps(report, ensure_ascii=False)
    for heading in ("No stored opinion", "Meaning only"):
        assert json.dumps(_expected(heading), ensure_ascii=False) in text
    assert json.dumps(_expected("Sketched but unlinked", N=2, M=3), ensure_ascii=False) in text


# ---------------------------------------------------------------------------
# T077 -- the forbidden words, over every emitted response
# ---------------------------------------------------------------------------


def _no_opinion_lines():
    return [
        line(i, f"w{i}", [parser_analysis(f"p{i}")],
             [stored(f"n{i}", opinion="noopinion", parser_evaluated=True, in_segment=seg)])
        for i, seg in enumerate((True, False, None))
    ]


def _scan(text):
    return [w for w in FORBIDDEN if re.search(rf"\b{w}\b", text, flags=re.I)]


def _responses(record_dir, lines):
    record = write_run(record_dir, lines)
    return [
        summary_response(record.run_id),
        summary_response(record.run_id, drill_down_cap=12),
    ]


def test_no_forbidden_word_in_any_response_about_no_opinion_analyses(record_dir):
    for response in _responses(record_dir, _no_opinion_lines()):
        assert _scan(json.dumps(response)) == []


def test_no_forbidden_word_near_any_no_opinion_entry_in_a_mixed_run(record_dir):
    """Beside a disapproval ('Marked incorrect by'), the no-opinion entries stay clean."""
    for response in _responses(record_dir, every_case_lines() + _no_opinion_lines()):
        report = find_report(response)
        entries = [
            v for _, _, v in walk(report)
            if isinstance(v, dict) and v.get("opinion") == "noopinion"
        ]
        assert entries, "the fixture must reach the no-opinion entries"
        for entry in entries:
            assert _scan(json.dumps(entry)) == [], entry
        # And the only place a forbidden word appears at all is the mandated
        # disapproval sentence, on an analysis that DOES carry an opinion.
        text = json.dumps(response)
        text = text.replace(_expected("Disapproved", user="Ana", date="2026-03-01"), "")
        assert _scan(text) == []


# ---------------------------------------------------------------------------
# T078 -- no individual analysis is labelled; the split is exact
# ---------------------------------------------------------------------------


def test_no_analysis_is_labelled_tacit_unreviewed_or_auto_approved(record_dir):
    for response in _responses(record_dir, every_case_lines() + _no_opinion_lines()):
        for _, key, value in walk(response):
            assert key not in FORBIDDEN_LABELS
            if isinstance(value, str):
                assert value.strip().lower() not in FORBIDDEN_LABELS, value


def test_the_split_is_affirmed_and_indeterminate_never_tacit():
    block = build_oracle(every_case_lines(), PARSED_STATE)
    assert set(block["provenance_split"]) == {"affirmed", "indeterminate"}
    assert block["provenance_split"] == {"affirmed": 1, "indeterminate": 1}
    assert oracle.PROVENANCE_SPLIT == ("affirmed", "indeterminate")
    provenances = {a.get("provenance") for a in block["analyses"]} - {None}
    assert provenances <= {"affirmed", "indeterminate"}


def test_unknown_segment_use_is_never_promoted_to_affirmed():
    record = stored("g", opinion="approves", in_segment=None)
    assert describe_analysis(record)["provenance"] == "indeterminate"
    block = build_oracle([line(0, "w", [parser_analysis("a")], [record])], PARSED_STATE)
    assert block["provenance_split"] == {"affirmed": 0, "indeterminate": 1}
    assert block["segment_use_unknown"] == 1


def test_meaning_only_and_sketched_are_named_not_counted_or_dropped():
    block = build_oracle(every_case_lines(), PARSED_STATE)
    assert [e["wordform"] for e in block["meaning_only"]] == ["glossed", "understand"]
    assert [e["wordform"] for e in block["sketched"]] == ["begun"]
    assert block["sketched"][0]["unlinked_morphs"] == 2
    compared = {a["analysis_guid"] for a in block["analyses"]}
    assert not compared & {"g-meaning", "g-sketched", "g-lex"}
    for entry in block["meaning_only"] + block["sketched"]:
        assert entry["enters_approval_comparison"] is False
        assert "parser_produced" not in entry  # never rendered as disagreement


# ---------------------------------------------------------------------------
# T079 -- the absent oracle, offline
# ---------------------------------------------------------------------------


def _never_parsed_lines():
    # What a hand-analysed, never-parsed project looks like: human records,
    # some with no opinion, and not one parser evaluation among them.
    return [
        line(0, "rumah", [parser_analysis("r")],
             [stored("h1", opinion="noopinion"), stored("h2", bundles=0, gloss="house")]),
        line(1, "makan", [parser_analysis("m")], [stored("h3", opinion="noopinion")]),
    ]


def test_a_never_parsed_project_reports_the_oracle_absent():
    block = build_oracle(_never_parsed_lines(), NEVER_PARSED_STATE)
    assert block["status"] == "absent"
    assert block["sentence"] == oracle.SENTENCE_ORACLE_ABSENT
    assert "analyses" not in block
    assert "population_sentence" not in block
    # Human meaning is still named: absent is not "dropped".
    assert [e["analysis_guid"] for e in block["meaning_only"]] == ["h2"]


def test_a_never_parsed_project_emits_no_degenerate_report(record_dir):
    record = write_run(record_dir, _never_parsed_lines(), project_state=NEVER_PARSED_STATE)
    response = summary_response(record.run_id)
    text = json.dumps(response, ensure_ascii=False)
    assert json.dumps(oracle.SENTENCE_ORACLE_ABSENT, ensure_ascii=False) in text
    assert oracle.SENTENCE_NO_OPINION not in text
    assert find_report(response)["oracle"]["status"] == "absent"


def test_the_absent_sentence_is_its_own_and_uses_no_forbidden_word():
    assert oracle.SENTENCE_ORACLE_ABSENT not in _contract_sentences().values()
    assert _scan(oracle.SENTENCE_ORACLE_ABSENT) == []
    for label in FORBIDDEN_LABELS:
        assert label not in oracle.SENTENCE_ORACLE_ABSENT.lower()


# ---------------------------------------------------------------------------
# The segment-occurrence join (FR-043) -- the one implementation
# ---------------------------------------------------------------------------


class _Obj:
    def __init__(self, kind, guid, owner=None):
        self.ClassName, self.Guid, self.Owner = kind, guid, owner


class _Segment:
    def __init__(self, *items):
        self.AnalysesRS = list(items)


def test_the_join_resolves_glosses_to_their_analysis_and_ignores_wordforms():
    analysis = _Obj("WfiAnalysis", "AAAA")
    glossed = _Obj("WfiAnalysis", "BBBB")
    occurrence = segment_occurrence([
        _Segment(analysis, _Obj("WfiWordform", "CCCC")),
        _Segment(_Obj("WfiGloss", "DDDD", owner=glossed), _Obj("PunctuationForm", "EEEE")),
    ])
    assert occurrence.contains("aaaa") is True
    assert occurrence.contains("bbbb") is True
    assert occurrence.contains("cccc") is False  # a wordform names no analysis
    assert occurrence.contains("ffff") is False


def test_an_unbuildable_join_is_unknown_not_empty():
    occurrence = segment_occurrence(None)
    assert occurrence.known is False
    assert occurrence.contains("aaaa") is None
