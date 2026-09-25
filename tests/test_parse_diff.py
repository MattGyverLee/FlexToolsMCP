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


# ===========================================================================
# CP5 T076 (FR-039, FR-040; research R-13, R-14) -- cross-spine diffs,
# either-run staleness. CP5 T074 (FR-032) -- corpus assertion lines.
#
# The API these tests pin (parse/diff.py, parse/signature.py):
#   * `RunComparison.comparison` -- None for an in-process pair (the CP3
#     result is unchanged, no `comparison` key); otherwise a dict
#     {same_spine, same_config_source, same_engine_version, note} rendered as
#     `comparison` in `to_dict()`. `same_engine_version` may be None (unknown).
#     `note` is None when all three are True, else fixed sentences joined by
#     one space (diff.CROSS_SPINE_NOTE, CONFIG_SOURCE_NOTE,
#     ENGINE_VERSION_NOTE, ENGINE_VERSION_UNKNOWN_NOTE, VERNACULAR_WS_NOTE).
#   * A cross-spine pair is compared in RENDERED_FALLBACK by FORMS only
#     (`signature.KEY_FORMS`), a sandbox pair by (form, gloss)
#     (`signature.KEY_MORPHS`); neither reports identity changes.
#     `signature.spine_pair_mode(before_spine, after_spine, mode)` ->
#     (mode, key) decides it.
#   * A sandbox run's empty `vernacular_ws` is tolerated against an
#     in-process run only (disclosed by VERNACULAR_WS_NOTE).
#   * `no_change` -> `no_change_unverifiable` when EITHER run's recorded
#     `project_state.staleness` is `shared_mode_unverifiable`.
#   * A current line carrying `assertion` is bucketed through
#     `sandbox.classify.CLASSIFICATION_BUCKETS`; an `error` goes to
#     not_compared; a baseline assertion line is not compared.
# ===========================================================================

from flextoolsmcp.server.parse import signature as signature_mod  # noqa: E402

_WORDS = ["membaca", "baca"]


def _words_fp(**overrides):
    base = {
        "scope_kind": "words", "scope_value": list(_WORDS), "text_ids": [],
        "word_count": len(_WORDS), "limit": None, "truncated": False, "engine": "HC",
        "vernacular_ws": "id",
    }
    base.update(overrides)
    return base


def _ip_analysis(forms, labels=None, ids=None):
    """An in-process analysis: GUID triples, forms, category labels."""
    return {
        "signature": [[f"form-{f}{ids or ''}", f"msa-{f}", None] for f in forms],
        "rendered_morphs": list(forms),
        "category_labels": list(labels or ["v"] * len(forms)),
        "has_guessed_form": False,
    }


def _sb_analysis(pairs=None, raw=None):
    """A sandbox analysis line (CP5 data-model 6.4)."""
    if pairs is None:
        return {"signature": None, "rendered_morphs": None, "morphs": None,
                "readable": False, "raw": list(raw)}
    return {"signature": None, "rendered_morphs": [f for f, _ in pairs],
            "morphs": [{"form": f, "gloss": g} for f, g in pairs],
            "readable": True, "raw": None}


def _in_process_run(record_dir, analyses_by_word, **fp):
    words = list(analyses_by_word)
    record = RunRecord.create(
        project_name="P", words_total=len(words), record_dir=record_dir, words=words,
        scope_fingerprint=_words_fp(**fp), engine_at_submission="HC",
    )
    for index, word in enumerate(words):
        analyses = analyses_by_word[word]
        record.append_result({"index": index, "wordform": word, "parse": {
            "parsed": bool(analyses), "analysis_count": len(analyses),
            "analyses": analyses, "human_analyses": [], "error_message": None,
            "parse_time_ms": 0,
        }})
    return record


def _sandbox_meta(config_source=None, hc_tool="3.8.1", skew=False):
    return {
        "mode": "parse",
        "config_source": config_source or {"kind": "project_cache", "cache_key": "k1"},
        "versions": {"hc_tool": hc_tool, "fieldworks_hermitcrab": "3.8.2.0",
                     "generate_hc_config": "9.3.11", "hcparse": "5.0.0"},
        "version_skew": skew,
    }


def _sandbox_run(record_dir, by_word, *, staleness=None, lines=None, **meta):
    """by_word: word -> list of sandbox analyses, or an outcome string."""
    words = list(by_word)
    project_state = {"access": "free"}
    if staleness:
        project_state = {"access": "open_shared", "staleness": staleness}
    record = RunRecord.create(
        project_name="P", words_total=len(words), record_dir=record_dir, words=words,
        scope_fingerprint=_words_fp(vernacular_ws=""), engine_at_submission="HC",
        project_state=project_state, spine="sandbox", sandbox=_sandbox_meta(**meta),
    )
    for index, word in enumerate(words):
        if lines is not None:
            record.append_result(dict(lines[word], index=index, wordform=word))
            continue
        value = by_word[word]
        if isinstance(value, str):
            parse = {"parsed": False, "analysis_count": 0, "outcome": value,
                     "analyses": None, "position": 2 if value == "invalid_segment" else None,
                     "flags": [], "parse_time_ms": None}
        else:
            parse = {"parsed": bool(value), "analysis_count": len(value),
                     "outcome": "parsed" if value else "not_parsed", "analyses": value,
                     "position": None, "flags": [], "parse_time_ms": 1}
        record.append_result({"index": index, "wordform": word, "parse": parse})
    return record


MEM = [("mem", "ACT"), ("baca", "read")]
BACA = [("baca", "read")]


# -- cross-spine (FR-039, R-14) ----------------------------------------------


def test_sandbox_against_in_process_diffs_and_discloses_form_only(tmp_path):
    before = _in_process_run(tmp_path, {
        "membaca": [_ip_analysis(["mem", "baca"])], "baca": [_ip_analysis(["baca"])],
    })
    # Same forms, different glosses and no category labels on the sandbox side.
    after = _sandbox_run(tmp_path, {
        "membaca": [_sb_analysis([("mem", "X"), ("baca", "Y")])],
        "baca": [_sb_analysis([("bac", "r"), ("a", "PL")])],
    })
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    data = result.to_dict()
    assert data["comparison_mode"] == "rendered_fallback"  # forced for any cross-spine pair
    assert _bucket_of(result, "membaca") == "unchanged"  # forms only: glosses not compared
    assert _bucket_of(result, "baca") == "changed"
    assert result.identity_changes == []  # no identity dimension across spines
    comparison = data["comparison"]
    assert list(comparison) == ["same_spine", "same_config_source",
                                "same_engine_version", "note"]
    assert comparison["same_spine"] is False
    assert comparison["same_config_source"] is False
    assert comparison["same_engine_version"] is True
    note = comparison["note"]
    assert "compared by morph forms only; glosses and HVO-level identity are not " \
           "compared across spines" in note
    assert "FieldWorks" in note and "hc" in note  # names the two engines
    assert diff_mod.CROSS_SPINE_NOTE in note
    assert diff_mod.VERNACULAR_WS_NOTE in note  # the empty ws was tolerated


def test_cross_spine_is_symmetric(tmp_path):
    before = _sandbox_run(tmp_path, {"membaca": [_sb_analysis(MEM)], "baca": []})
    after = _in_process_run(tmp_path, {"membaca": [_ip_analysis(["mem", "baca"])],
                                       "baca": []})
    result = compare_runs(before, after)
    assert _bucket_of(result, "membaca") == "unchanged"
    assert _bucket_of(result, "baca") == "unchanged"
    assert result.verdict == "no_change"
    assert result.to_dict()["comparison"]["same_spine"] is False


def test_cross_spine_version_skew_and_unknown_are_disclosed(tmp_path):
    before = _in_process_run(tmp_path, {"membaca": [], "baca": []})
    skewed = _sandbox_run(tmp_path, {"membaca": [], "baca": []}, skew=True)
    comparison = compare_runs(before, skewed).to_dict()["comparison"]
    assert comparison["same_engine_version"] is False
    assert diff_mod.ENGINE_VERSION_NOTE in comparison["note"]
    unknown = _sandbox_run(tmp_path, {"membaca": [], "baca": []}, skew=None)
    comparison = compare_runs(before, unknown).to_dict()["comparison"]
    assert comparison["same_engine_version"] is None
    assert diff_mod.ENGINE_VERSION_UNKNOWN_NOTE in comparison["note"]


def test_unreadable_sandbox_analysis_never_matches_across_spines(tmp_path):
    before = _in_process_run(tmp_path, {"membaca": [_ip_analysis(["mem", "baca"])],
                                        "baca": []})
    after = _sandbox_run(tmp_path, {
        "membaca": [_sb_analysis(raw=["Morphs: m   ", "Gloss:  A PL"])], "baca": [],
    })
    result = compare_runs(before, after)
    assert _bucket_of(result, "membaca") == "changed"
    entry = result.buckets["changed"][0]
    assert any("unreadable" in text for text in entry["analyses_added"])


def test_empty_vernacular_ws_does_not_hide_another_mismatch(tmp_path):
    before = _in_process_run(tmp_path, {"membaca": [], "baca": []}, limit=5,
                             truncated=True)
    after = _sandbox_run(tmp_path, {"membaca": [], "baca": []})
    with pytest.raises(ScopeMismatch) as refused:
        compare_runs(before, after)
    assert refused.value.detail["differing_fields"] == ["limit", "truncated"]


def test_empty_vernacular_ws_is_not_tolerated_between_in_process_runs(tmp_path):
    before = _in_process_run(tmp_path, {"membaca": [], "baca": []})
    after = _in_process_run(tmp_path, {"membaca": [], "baca": []}, vernacular_ws="")
    with pytest.raises(ScopeMismatch) as refused:
        compare_runs(before, after)
    assert refused.value.detail["differing_fields"] == ["vernacular_ws"]


def test_a_sandbox_word_hc_produced_nothing_for_is_not_compared(tmp_path):
    before = _in_process_run(tmp_path, {"membaca": [_ip_analysis(["mem", "baca"])],
                                        "baca": [_ip_analysis(["baca"])]})
    after = _sandbox_run(tmp_path, {"membaca": "invalid_segment", "baca": "not_reached"})
    result = compare_runs(before, after)
    assert _bucket_of(result, "membaca") is None, "no output is not 'broken'"
    assert _bucket_of(result, "baca") is None
    assert [e["wordform"] for e in result.not_compared] == ["membaca", "baca"]


# -- sandbox against sandbox (R-14) ------------------------------------------


def test_sandbox_against_sandbox_compares_form_and_gloss(tmp_path):
    before = _sandbox_run(tmp_path, {"membaca": [_sb_analysis(MEM)],
                                     "baca": [_sb_analysis(BACA)]})
    after = _sandbox_run(tmp_path, {"membaca": [_sb_analysis([("mem", "ACT"),
                                                              ("baca", "READ")])],
                                    "baca": [_sb_analysis(BACA)]})
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    data = result.to_dict()
    assert data["comparison_mode"] == "rendered_fallback"
    assert _bucket_of(result, "membaca") == "changed"  # the gloss moved
    assert _bucket_of(result, "baca") == "unchanged"
    entry = result.buckets["changed"][0]
    assert entry["analyses_added"] == ["mem:ACT+baca:READ"]
    assert entry["analyses_removed"] == ["mem:ACT+baca:read"]
    assert data["comparison"] == {"same_spine": True, "same_config_source": True,
                                  "same_engine_version": True, "note": None}


def test_sandbox_pair_with_different_config_or_engine_says_so(tmp_path):
    before = _sandbox_run(tmp_path, {"membaca": [], "baca": []})
    after = _sandbox_run(tmp_path, {"membaca": [], "baca": []},
                         config_source={"kind": "named_sandbox", "name": "tighten-env"},
                         hc_tool="3.9.0")
    comparison = compare_runs(before, after).to_dict()["comparison"]
    assert comparison["same_spine"] is True
    assert comparison["same_config_source"] is False
    assert comparison["same_engine_version"] is False
    assert diff_mod.CONFIG_SOURCE_NOTE in comparison["note"]
    assert diff_mod.ENGINE_VERSION_NOTE in comparison["note"]
    assert diff_mod.CROSS_SPINE_NOTE not in comparison["note"]


def test_spine_pair_mode():
    f = signature_mod.spine_pair_mode
    fb = SignatureMode.RENDERED_FALLBACK
    assert f("in_process", "in_process", SignatureMode.IDENTIFIER) == (
        SignatureMode.IDENTIFIER, None)
    assert f("in_process", "in_process", fb) == (fb, None)
    assert f("in_process", "sandbox", SignatureMode.IDENTIFIER) == (fb, signature_mod.KEY_FORMS)
    assert f("sandbox", "in_process", SignatureMode.IDENTIFIER) == (fb, signature_mod.KEY_FORMS)
    assert f("sandbox", "sandbox", SignatureMode.IDENTIFIER) == (fb, signature_mod.KEY_MORPHS)


def test_signatures_of_null_analyses_is_unknown_not_empty():
    line = {"wordform": "q#", "parse": {"outcome": "invalid_segment", "analyses": None}}
    assert signature_mod.signatures_of(line) is None
    assert signature_mod.signatures_of({"parse": {"analyses": []}}) == []


# -- either-run staleness (FR-040, R-13) -------------------------------------


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_either_run_staleness_downgrades_no_change(tmp_path, side):
    stale = {"staleness": "shared_mode_unverifiable"}
    before = _sandbox_run(tmp_path, {"membaca": [], "baca": []},
                          **(stale if side == "baseline" else {}))
    after = _sandbox_run(tmp_path, {"membaca": [], "baca": []},
                         **(stale if side == "current" else {}))
    data = compare_runs(before, after, access=_Access("free")).to_dict()
    assert data["verdict"] == "no_change_unverifiable"
    assert data["staleness"] == "shared_mode_unverifiable"
    assert data["notes"].count(diff_mod.SHARED_MODE_NOTE) == 1


def test_recorded_staleness_and_live_access_note_once(tmp_path):
    before = _sandbox_run(tmp_path, {"membaca": [], "baca": []},
                          staleness="shared_mode_unverifiable")
    after = _in_process_run(tmp_path, {"membaca": [], "baca": []})
    data = compare_runs(before, after, access=_Access("open_shared")).to_dict()
    assert data["verdict"] == "no_change_unverifiable"
    assert data["notes"].count(diff_mod.SHARED_MODE_NOTE) == 1


def test_no_recorded_staleness_leaves_no_change(tmp_path):
    before = _sandbox_run(tmp_path, {"membaca": [], "baca": []})
    after = _sandbox_run(tmp_path, {"membaca": [], "baca": []})
    data = compare_runs(before, after, access=_Access("held_by_other")).to_dict()
    assert data["verdict"] == "no_change"
    assert "staleness" not in data


def test_shared_mode_active_is_unchanged():
    # R-13: the in-process rule is left as CP3 shipped it.
    assert diff_mod._SHARED_VERDICTS == ("open_shared", "open_exclusive")
    assert diff_mod.shared_mode_active(_Access("held_by_other")) is False


# -- CP3's in-process results are unchanged ----------------------------------


def test_in_process_pair_has_no_comparison_block(tmp_path):
    before = _run(tmp_path, {"a": [_analysis(0, "a")]})
    after = _run(tmp_path, {"a": [_analysis(0, "a")]})
    result = compare_runs(before, after, mode=SignatureMode.IDENTIFIER)
    assert result.comparison is None
    data = result.to_dict()
    assert "comparison" not in data
    assert list(data) == [
        "baseline_run_id", "current_run_id", "verdict", "comparison_mode", "counts",
        "buckets", "identity_changes", "identity_change_count", "not_compared",
        "provisional_words", "notes",
    ]


def test_in_process_identity_change_still_reported(tmp_path):
    # The CP3 identity dimension is untouched for in-process pairs.
    relinked = dict(_analysis(0, "sama"))
    relinked["signature"] = [["form-new", "msa-new", None]]
    before = _run(tmp_path, {"sama": [_analysis(0, "sama")]})
    after = _run(tmp_path, {"sama": [relinked]})
    for mode in (SignatureMode.IDENTIFIER, SignatureMode.RENDERED_FALLBACK):
        result = compare_runs(before, after, mode=mode)
        assert [e["wordform"] for e in result.identity_changes] == ["sama"]


# -- T074: corpus assertion lines through the bucket mapping (FR-032) ---------


def _assertion_line(classification, label=None, reason=None):
    parse = {"parsed": classification != "error", "analysis_count": 1,
             "outcome": "parsed" if classification != "error" else "invalid_segment",
             "analyses": [] if classification != "error" else None,
             "position": None, "flags": [], "parse_time_ms": None}
    return {"parse": parse, "assertion": {
        "classification": classification, "label": label,
        "missing": [[{"form": "mem", "gloss": "ACT"}]] if classification in
        ("regression", "changed") else [],
        "unexpected": [[{"form": "x", "gloss": "Y"}]] if classification in
        ("new_ambiguity", "changed") else [],
        "error_reason": reason,
    }}


_CORPUS = {
    "lulus": _assertion_line("pass"),
    "rusak": _assertion_line("regression"),
    "ganda": _assertion_line("new_ambiguity"),
    "sekarang": _assertion_line("new_ambiguity", label="now_parses"),
    "ubah": _assertion_line("changed"),
    "salah": _assertion_line("error", reason="invalid_segment"),
}


def test_assertion_lines_are_bucketed_through_the_mapping(tmp_path):
    words = {w: [] for w in _CORPUS}
    before = _sandbox_run(tmp_path, words)
    after = _sandbox_run(tmp_path, words, lines=_CORPUS)
    result = compare_runs(before, after)
    got = {w: _bucket_of(result, w) for w in _CORPUS}
    assert got == {
        "lulus": "unchanged", "rusak": "broken", "ganda": "changed",
        "sekarang": "changed", "ubah": "changed", "salah": None,
    }
    assert result.buckets["fixed"] == []  # never "fixed" (FR-033)
    assert result.not_compared == [
        {"wordform": "salah", "reason": "corpus assertion error: invalid_segment"}
    ]
    assert result.verdict == "changes_found"
    now = next(e for e in result.buckets["changed"] if e["wordform"] == "sekarang")
    assert now["classification"] == "new_ambiguity"
    assert now["label"] == "now_parses"
    rusak = result.buckets["broken"][0]
    assert rusak["missing"] == [[{"form": "mem", "gloss": "ACT"}]]


def test_new_ambiguity_is_never_unchanged(tmp_path):
    corpus = {"ganda": _assertion_line("new_ambiguity"), "lulus": _assertion_line("pass")}
    before = _sandbox_run(tmp_path, {w: [] for w in corpus})
    after = _sandbox_run(tmp_path, {w: [] for w in corpus}, lines=corpus)
    result = compare_runs(before, after)
    unchanged = [e["wordform"] for e in result.buckets["unchanged"]]
    assert unchanged == ["lulus"]
    assert result.verdict == "changes_found"


def test_all_pass_corpus_is_no_change(tmp_path):
    corpus = {"a": _assertion_line("pass"), "b": _assertion_line("pass")}
    before = _sandbox_run(tmp_path, {w: [] for w in corpus})
    after = _sandbox_run(tmp_path, {w: [] for w in corpus}, lines=corpus)
    assert compare_runs(before, after).verdict == "no_change"


def test_a_baseline_assertion_line_is_not_compared(tmp_path):
    corpus = {"a": _assertion_line("pass")}
    before = _sandbox_run(tmp_path, {"a": []}, lines=corpus)
    after = _sandbox_run(tmp_path, {"a": [_sb_analysis(BACA)]})
    result = compare_runs(before, after)
    assert _bucket_of(result, "a") is None
    assert result.not_compared[0]["wordform"] == "a"
    assert "corpus" in result.not_compared[0]["reason"]


async def test_the_tool_returns_the_comparison_block(diff_tool):
    before = _in_process_run(diff_tool, {"membaca": [], "baca": []})
    after = _sandbox_run(diff_tool, {"membaca": [], "baca": []})
    payload = await _diff(baseline_run_id=before.run_id, current_run_id=after.run_id)
    assert payload["status"] == "ok"
    assert payload["comparison"]["same_spine"] is False


def test_a_transient_meta_read_failure_does_not_lose_the_spine(tmp_path, monkeypatch):
    """Regression: the spine and the fingerprint come from ONE meta read.

    `RunRecord.read_meta` returns None on any OSError (a Windows sharing
    violation while a scanner holds the freshly written meta.json). The diff
    once read the meta twice -- once for the spine, once for the fingerprint
    -- so a failed first read made a sandbox run look in-process while its
    fingerprint still loaded, and the empty `vernacular_ws` then refused with
    `parse_scope_mismatch`. Order-dependent under load, never alone.
    """
    before = _in_process_run(tmp_path, {"membaca": [], "baca": []})
    after = _sandbox_run(tmp_path, {"membaca": [], "baca": []})
    real = RunRecord.read_meta
    failures = {"left": 1}

    def flaky(self):
        if self.run_id == after.run_id and failures["left"]:
            failures["left"] -= 1
            return None  # what read_meta returns on a transient OSError
        return real(self)

    monkeypatch.setattr(RunRecord, "read_meta", flaky)
    result = compare_runs(before, after)
    assert result.verdict == "no_change"
    assert result.to_dict()["comparison"]["same_spine"] is False


def test_an_unreadable_meta_is_not_comparable_rather_than_in_process(tmp_path, monkeypatch):
    before = _in_process_run(tmp_path, {"membaca": [], "baca": []})
    after = _sandbox_run(tmp_path, {"membaca": [], "baca": []})
    real = RunRecord.read_meta
    monkeypatch.setattr(
        RunRecord, "read_meta",
        lambda self: None if self.run_id == after.run_id else real(self),
    )
    monkeypatch.setattr(diff_mod, "_META_RETRY_DELAY_SECONDS", 0.0)
    with pytest.raises(diff_mod.RunNotComparable):
        compare_runs(before, after)
