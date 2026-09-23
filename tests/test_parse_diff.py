#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparing two runs (parser-check CP3, US4; FR-012, FR-030, FR-032, FR-034,
FR-024; SC-008, SC-009).

  * SC-008 -- a word going from one analysis to seven is `changed`. The same
    fixture is run through a count-equality classifier, which must get it
    wrong, so the fixture can never quietly stop discriminating.
  * FR-012 -- differing fingerprints refuse with `parse_scope_mismatch`,
    unless forced; a forced comparison covers the intersection and says so.
  * FR-034 / R-06 -- shared or exclusive access marks the result
    `shared_mode_unverifiable`, carries the save-or-close note, downgrades
    `no_change`, and promises no read-back interval anywhere.
  * FR-024 -- the diff tool never reaches a worker or the engine check.

Run with:
    python -m pytest tests/test_parse_diff.py -q
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse import diff as diff_mod  # noqa: E402
from flextoolsmcp.server.parse.diff import BUCKETS, compare_runs  # noqa: E402
from flextoolsmcp.server.parse.fingerprint import ScopeMismatch  # noqa: E402
from flextoolsmcp.server.parse.record import RunRecord  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.signature import SignatureMode  # noqa: E402

CONTRACT = REPO_ROOT / "specs" / "parser-check-cp3" / "contracts" / "tools.md"


def _fp(**overrides):
    base = {
        "scope_kind": "genre", "scope_value": "Folklore", "text_ids": ["g1", "g2"],
        "word_count": 4, "limit": None, "truncated": False, "engine": "HC",
        "vernacular_ws": "id",
    }
    base.update(overrides)
    return base


def _analysis(n, word="w"):
    return {"signature": [[f"form-{word}-{n}", f"msa-{word}-{n}", None]],
            "rendered_morphs": [f"{word}{n}"], "category_labels": ["v"],
            "has_guessed_form": False}


def _run(record_dir, analyses_by_word, *, fingerprint=None, project="P"):
    words = list(analyses_by_word)
    record = RunRecord.create(
        project_name=project, words_total=len(words), record_dir=record_dir, words=words,
        scope_fingerprint=fingerprint or _fp(), engine_at_submission="HC",
    )
    for index, word in enumerate(words):
        analyses = analyses_by_word[word]
        if analyses is None:
            continue     # a word this run never completed
        record.append_result({"index": index, "wordform": word, "parse": {
            "parsed": bool(analyses), "analysis_count": len(analyses),
            "analyses": analyses, "human_analyses": [], "error_message": None,
            "parse_time_ms": 0,
        }})
    return record


def _bucket_of(result, word):
    for name in BUCKETS:
        if any(entry["wordform"] == word for entry in result.buckets[name]):
            return name
    return None


# ---------------------------------------------------------------------------
# T062 -- FR-030 / SC-008: changed is not unchanged; counts alone fail
# ---------------------------------------------------------------------------


def test_the_bucket_names_are_the_contracts_exactly():
    text = CONTRACT.read_text(encoding="utf-8")
    block = text.split("Buckets, exactly these:", 1)[1].split("```", 2)[1]
    assert BUCKETS == tuple(n.strip() for n in block.strip().split("|"))


def test_one_analysis_to_seven_is_changed(tmp_path):
    before = _run(tmp_path, {"lari": [_analysis(0, "lari")]})
    after = _run(tmp_path, {"lari": [_analysis(i, "lari") for i in range(7)]})
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    assert _bucket_of(result, "lari") == "changed"


def test_same_count_different_analyses_is_changed(tmp_path):
    """The case a count-equality classifier calls unchanged."""
    before = _run(tmp_path, {"lari": [_analysis(0, "lari"), _analysis(1, "lari")]})
    after = _run(tmp_path, {"lari": [_analysis(0, "lari"), _analysis(9, "lari")]})
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    assert _bucket_of(result, "lari") == "changed"


def _count_equality_classifier(before_count, after_count):
    """The wrong implementation SC-008 exists to fail."""
    if before_count == 0 and after_count > 0:
        return "fixed"
    if before_count > 0 and after_count == 0:
        return "broken"
    return "unchanged" if before_count == after_count else "changed"


def test_a_count_equality_implementation_fails_this_fixture(tmp_path):
    before = _run(tmp_path, {"lari": [_analysis(0, "lari"), _analysis(1, "lari")]})
    after = _run(tmp_path, {"lari": [_analysis(0, "lari"), _analysis(9, "lari")]})
    ours = _bucket_of(compare_runs(before, after, mode=SignatureMode.IDENTIFIER), "lari")
    theirs = _count_equality_classifier(2, 2)
    assert theirs == "unchanged" and ours == "changed", (
        "the fixture no longer separates signature-set comparison from count equality"
    )


@pytest.mark.parametrize("mode", [SignatureMode.IDENTIFIER, SignatureMode.RENDERED_FALLBACK])
def test_every_bucket(tmp_path, mode):
    before = _run(tmp_path, {
        "baru": [], "rusak": [_analysis(0, "rusak")], "ubah": [_analysis(0, "ubah")],
        "sama": [_analysis(0, "sama")],
    })
    after = _run(tmp_path, {
        "baru": [_analysis(0, "baru")], "rusak": [], "ubah": [_analysis(1, "ubah")],
        "sama": [_analysis(0, "sama")],
    })
    result = compare_runs(before, after, mode=mode)
    assert {w: _bucket_of(result, w) for w in ("baru", "rusak", "ubah", "sama")} == {
        "baru": "fixed", "rusak": "broken", "ubah": "changed", "sama": "unchanged",
    }
    assert result.verdict == "changes_found"


def test_identity_changes_sit_beside_the_buckets_not_in_them(tmp_path):
    relinked = dict(_analysis(0, "sama"))
    relinked["signature"] = [["form-new", "msa-new", None]]
    before = _run(tmp_path, {"sama": [_analysis(0, "sama")]})
    after = _run(tmp_path, {"sama": [relinked]})
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    assert _bucket_of(result, "sama") is None
    assert [e["wordform"] for e in result.identity_changes] == ["sama"]
    assert result.to_dict()["identity_change_count"] == 1


def test_a_word_one_run_never_completed_is_not_compared(tmp_path):
    before = _run(tmp_path, {"a": [_analysis(0, "a")], "b": [_analysis(0, "b")]})
    after = _run(tmp_path, {"a": [_analysis(0, "a")], "b": None})
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    assert _bucket_of(result, "b") is None, "an unfinished word is not 'broken'"
    assert result.not_compared == [
        {"wordform": "b", "reason": "no completed result in the current run"}
    ]


def test_the_fallback_mode_states_its_ambiguity_in_the_result(tmp_path):
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": [_analysis(0, "a")]})
    result = compare_runs(before, after, mode=SignatureMode.RENDERED_FALLBACK)
    assert result.to_dict()["comparison_mode"] == "rendered_fallback"
    assert any("weaker" in note for note in result.notes)


# ---------------------------------------------------------------------------
# T073 -- FR-012: the fingerprint refusal and the forced intersection
# ---------------------------------------------------------------------------


def test_differing_fingerprints_refuse_naming_the_fields(tmp_path):
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": [_analysis(0, "a")]}, fingerprint=_fp(limit=50, truncated=True))
    with pytest.raises(ScopeMismatch) as refused:
        compare_runs(before, after)
    detail = refused.value.detail
    assert detail["error_code"] == "parse_scope_mismatch"
    assert detail["differing_fields"] == ["limit", "truncated"]
    assert list(detail) == [
        "error_code", "baseline_fingerprint", "current_fingerprint", "differing_fields", "hint",
    ]


def test_a_forced_comparison_covers_the_intersection_and_says_so(tmp_path):
    before = _run(tmp_path, {"a": [_analysis(0, "a")], "only_before": []})
    after = _run(tmp_path, {"a": [_analysis(1, "a")], "only_after": []},
                 fingerprint=_fp(text_ids=["g1", "g2", "g3"]))
    result = compare_runs(before, after, force=True, mode=SignatureMode.IDENTIFIER)
    compared = [e["wordform"] for name in BUCKETS for e in result.buckets[name]]
    assert compared == ["a"]
    assert result.forced and result.differing_fields == ["text_ids"]
    assert any("intersection" in note for note in result.notes)


def test_a_grammar_edit_never_causes_a_refusal(tmp_path):
    """The fingerprint carries nothing about the grammar (D-3)."""
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": []})    # the edit broke it
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    assert _bucket_of(result, "a") == "broken"


# ---------------------------------------------------------------------------
# T065 -- FR-034 / R-06: shared mode
# ---------------------------------------------------------------------------


class _Access:
    def __init__(self, verdict):
        self.verdict = verdict


@pytest.mark.parametrize("verdict", ["open_shared", "open_exclusive"])
def test_shared_or_exclusive_access_downgrades_no_change(tmp_path, verdict):
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": [_analysis(0, "a")]})
    result = compare_runs(before, after, access=_Access(verdict), mode=SignatureMode.IDENTIFIER)
    data = result.to_dict()
    assert data["staleness"] == "shared_mode_unverifiable"
    assert data["verdict"] == "no_change_unverifiable"
    assert diff_mod.SHARED_MODE_NOTE in data["notes"]
    assert "Save your work in FieldWorks, or close the project" in diff_mod.SHARED_MODE_NOTE


@pytest.mark.parametrize("verdict", ["free", "stale_lock", "held_by_other", None])
def test_other_access_states_leave_no_change_alone(tmp_path, verdict):
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": [_analysis(0, "a")]})
    access = _Access(verdict) if verdict else None
    data = compare_runs(before, after, access=access, mode=SignatureMode.IDENTIFIER).to_dict()
    assert data["verdict"] == "no_change"
    assert "staleness" not in data


def test_shared_mode_with_changes_keeps_the_changes_but_marks_them(tmp_path):
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": []})
    data = compare_runs(before, after, access=_Access("open_shared"),
                        mode=SignatureMode.IDENTIFIER).to_dict()
    assert data["verdict"] == "changes_found"
    assert data["staleness"] == "shared_mode_unverifiable"


_INTERVAL = re.compile(
    r"\b(wait|after|within)\s+\d+|\d+\s*(ms|milliseconds?|seconds?|secs?|minutes?|mins?)\b"
    r"|safe to (read|compare)|safe interval|read.back interval",
    re.I,
)


def test_no_safe_read_back_interval_is_promised_anywhere(tmp_path):
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": [_analysis(0, "a")]})
    data = compare_runs(before, after, access=_Access("open_shared"),
                        mode=SignatureMode.IDENTIFIER).to_dict()
    for text in [json.dumps(data), diff_mod.SHARED_MODE_NOTE, diff_mod.__doc__]:
        stripped = text.replace("NO SAFE READ-BACK INTERVAL IS PROMISED", "")
        assert not _INTERVAL.search(stripped), _INTERVAL.search(stripped)


# ---------------------------------------------------------------------------
# T074 -- the tool: routed, read-only, never reaches the engine
# ---------------------------------------------------------------------------


class ExplodingPool:
    async def get(self, name):
        raise AssertionError("flextools_parse_diff reached a worker (FR-024)")

    def peek(self, name):
        raise AssertionError("flextools_parse_diff reached a worker (FR-024)")

    async def aclose(self):
        pass


@pytest.fixture
def diff_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(parse_handler, "_probe_access", lambda name: _Access("free"))
    parse_handler.set_runner(ParseRunner(pool=ExplodingPool(), record_dir=tmp_path))
    yield tmp_path
    parse_handler.set_runner(None)


async def _diff(**args):
    response = await parse_handler.handle_flextools_parse_diff(args)
    return json.loads(response[0].text)


async def test_the_tool_compares_two_runs_without_touching_a_worker(diff_tool):
    before = _run(diff_tool, {"a": [_analysis(0, "a")]})
    after = _run(diff_tool, {"a": [_analysis(i, "a") for i in range(7)]})
    payload = await _diff(baseline_run_id=before.run_id, current_run_id=after.run_id)
    assert payload["status"] == "ok"
    assert payload["counts"]["changed"] == 1


async def test_the_tool_refuses_a_scope_mismatch_with_the_contract_code(diff_tool):
    before = _run(diff_tool, {"a": []})
    after = _run(diff_tool, {"a": []}, fingerprint=_fp(engine="XAmple"))
    payload = await _diff(baseline_run_id=before.run_id, current_run_id=after.run_id)
    assert payload["error_code"] == "parse_scope_mismatch"
    assert payload["differing_fields"] == ["engine"]


async def test_the_tool_names_an_unknown_run(diff_tool):
    before = _run(diff_tool, {"a": []})
    payload = await _diff(baseline_run_id=before.run_id, current_run_id="0" * 32)
    assert payload["error_code"] == "parse_run_not_found"


async def test_a_single_word_run_is_not_comparable(diff_tool):
    single = RunRecord.create(project_name="P", words_total=1, record_dir=diff_tool)
    batch = _run(diff_tool, {"a": []})
    payload = await _diff(baseline_run_id=single.run_id, current_run_id=batch.run_id)
    assert payload["reason"] == "not_a_batch_run"


def test_the_diff_source_never_names_the_engine_check():
    import inspect

    for source in (inspect.getsource(diff_mod),
                   inspect.getsource(parse_handler.handle_flextools_parse_diff)):
        for forbidden in ("check_engine", "check_active_parser", "preflight", "pool.get"):
            assert forbidden not in source, forbidden


def test_the_tool_is_read_only_and_routed():
    from flextoolsmcp.server import dispatch
    from flextoolsmcp.server.models import ParseDiffInput
    from flextoolsmcp.server.tool_definitions import TOOLS

    tool = TOOLS["flextools_parse_diff"]
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False
    handler, model = dispatch.DISPATCH_ROUTES["flextools_parse_diff"]
    assert handler is parse_handler.handle_flextools_parse_diff and model is ParseDiffInput
