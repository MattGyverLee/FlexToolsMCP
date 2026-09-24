#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The refuse-to-file gate (parser-check CP4, FR-020..FR-024, FR-039; R-12; D-1).

A wrong-implementation TRIPWIRE, written red first (tasks.md T040). Filing
against a grammar that silently lost entries deletes every analysis those
entries used to license, with no error anywhere in the chain -- the worst
realistic failure of the feature. So:

  * a parser that could not be built (`ParseWord` returns null) is always
    refused, `morpher_null`, with no override (FR-020);
  * errors in THIS load that the baseline did not have refuse, `new_load_errors`,
    and the message names the one way past: a read-only parse of the same
    scope, which re-baselines (FR-021);
  * with no baseline, every error is pre-existing, counted, not blocking, and
    the source is `absent` (FR-022);
  * FLEx's own load-error file is never a prior state: a stale file with a
    foreign mtime plays no part (FR-023);
  * an entry whose only lexeme form was emptied is dropped by the loader
    WITHOUT logging anything (`HCLoader.IsValidLexEntryForm`, D-1). The
    eligibility comparison must refuse it, `eligible_forms_dropped`, naming
    the entry. A gate that compares load errors alone PASSES this fixture --
    which is exactly how it fails this test.
"""

import asyncio
import os
import time

import pytest

import filing_fakes
from filing_fakes import (
    FakeReadWorker,
    PROJECT,
    analysis,
    call,
    clean_gate,
    filing_args,
)
from flextoolsmcp.server.filing import gate
from flextoolsmcp.server.parse.fingerprint import fingerprint_key
from flextoolsmcp.server.parse.record import RunRecord

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env

ERR_A = {"type": "InvalidShape", "Form": "-ber"}
ERR_B = {"type": "InvalidShape", "Form": "-kan"}
ERR_C = {"type": "InvalidEnvironment", "Form": "-i", "Env": "/_#"}
ERR_D = {"type": "InvalidShape", "Form": "meN-"}
ERR_E = {"type": "InvalidShape", "Form": "di-"}

PUKUL = {"entry_guid": "e1", "headword": "pukul"}
KIRIM = {"entry_guid": "e2", "headword": "kirim"}


def _current(errors=(), eligible=(PUKUL, KIRIM), *, morpher_null=False, captured=True,
             eligible_known=True):
    load = {"captured": captured, "errors": list(errors), "source": "C:/tmp/DemoHCLoadErrors.xml"}
    if not captured:
        load["reason"] = "the load-error file predates this worker's grammar load"
    return {"morpher_null": morpher_null, "load": load,
            "eligible": {"known": eligible_known, "entries": list(eligible)}}


def _baseline(errors=(), eligible=(PUKUL, KIRIM), run_id="b" * 32):
    return gate.Baseline(run_id=run_id, created_at="2026-09-24T10:00:00+00:00",
                         errors=list(errors),
                         eligible=list(eligible) if eligible is not None else None)


# ---------------------------------------------------------------------------
# FR-020 -- morpher null
# ---------------------------------------------------------------------------


def test_a_null_parse_is_morpher_null():
    standing = gate.evaluate(_current(morpher_null=True), _baseline())
    assert standing.refused and standing.signal == "morpher_null"


def test_morpher_null_refuses_even_with_no_baseline_and_no_errors():
    standing = gate.evaluate(_current(morpher_null=True), None)
    assert standing.refused and standing.signal == "morpher_null"


# ---------------------------------------------------------------------------
# FR-021 / FR-022 -- the load-error diff
# ---------------------------------------------------------------------------


def test_three_then_five_errors_is_two_new_errors():
    standing = gate.evaluate(
        _current([ERR_A, ERR_B, ERR_C, ERR_D, ERR_E]), _baseline([ERR_A, ERR_B, ERR_C])
    )
    assert standing.refused and standing.signal == "new_load_errors"
    detail = standing.refusal_detail()
    assert detail["new_error_count"] == 2
    assert detail["baseline_error_count"] == 3
    assert detail["baseline_source"] == "prior_run:" + "b" * 32
    assert sorted(e["Form"] for e in detail["new_errors"]) == ["di-", "meN-"]


def test_the_refusal_names_the_read_only_re_baseline_and_no_override():
    standing = gate.evaluate(_current([ERR_A]), _baseline([]))
    message = standing.message()
    assert "read-only flextools_parse_text of the same scope" in message
    assert "re-baseline" in message
    assert "There is no override." in message
    # ...and no argument that would be one is offered.
    for bypass in ("force=", "override=", "skip_", "confirmed=", "ignore_"):
        assert bypass not in message.lower()


def test_errors_already_in_the_baseline_are_counted_and_do_not_block():
    standing = gate.evaluate(_current([ERR_A, ERR_B]), _baseline([ERR_A, ERR_B]))
    assert not standing.refused
    assert standing.status == "pre_existing_errors"
    assert standing.pre_existing_error_count == 2 and standing.new_errors == []


def test_resolved_errors_are_reported_and_do_not_block():
    standing = gate.evaluate(_current([ERR_A]), _baseline([ERR_A, ERR_B]))
    assert not standing.refused
    assert standing.resolved_error_count == 1


def test_a_duplicate_error_is_a_new_one_multiset_not_set():
    standing = gate.evaluate(_current([ERR_A, ERR_A]), _baseline([ERR_A]))
    assert standing.refused and standing.refusal_detail()["new_error_count"] == 1


def test_a_first_run_treats_every_error_as_pre_existing():
    standing = gate.evaluate(_current([ERR_A, ERR_B, ERR_C]), None)
    assert not standing.refused
    assert standing.status == "pre_existing_errors"
    assert standing.pre_existing_error_count == 3
    assert standing.baseline_source == "absent"
    assert standing.baseline_eligible_count is None


def test_a_clean_load_against_a_clean_baseline_is_clean():
    standing = gate.evaluate(_current([]), _baseline([]))
    assert standing.status == "clean" and not standing.refused


def test_the_hypothesis_is_stated_as_a_hypothesis():
    standing = gate.evaluate(_current([ERR_A]), None)
    assert standing.to_dict()["hypothesis_note"] == (
        "pre-existing load errors are treated as benign; that is a working "
        "hypothesis, not an established fact"
    )


# ---------------------------------------------------------------------------
# FR-023 -- FLEx's load-error file is never a prior state
# ---------------------------------------------------------------------------


def test_a_stale_load_error_file_with_a_foreign_mtime_plays_no_part(tmp_path, monkeypatch):
    """The worker reads only the file ITS load wrote; an older one is ignored."""
    import tempfile

    from flextoolsmcp.server.parse.worker_main import _RealBackend

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    stale = tmp_path / f"{PROJECT}HCLoadErrors.xml"
    stale.write_text("<LoadErrors><LoadError type='InvalidShape'><Form>-x</Form>"
                     "</LoadError></LoadErrors>", encoding="utf-8")
    old = time.time() - 3600
    os.utime(stale, (old, old))

    backend = _RealBackend.__new__(_RealBackend)
    backend._project_name = PROJECT
    read = backend.load_error_baseline(load_started=time.time())
    assert read["captured"] is False and read["errors"] == []

    # And a load whose errors could not be read cannot be shown clean: the
    # gate refuses rather than trusting either the stale file or silence.
    standing = gate.evaluate({"morpher_null": False, "load": read,
                              "eligible": {"known": True, "entries": [PUKUL]}}, None)
    assert standing.refused and standing.signal == "new_load_errors"
    assert "-x" not in str(standing.refusal_detail())


# ---------------------------------------------------------------------------
# FR-039 / D-1 -- the silent drop. THE TRIPWIRE.
# ---------------------------------------------------------------------------


def test_an_emptied_lexeme_form_is_refused_and_named():
    """No load error is logged -- a load-error-only gate passes this."""
    standing = gate.evaluate(_current([], eligible=[PUKUL]), _baseline([], eligible=[PUKUL, KIRIM]))
    assert standing.refused, "the loader dropped 'kirim' silently; the gate must see it"
    assert standing.signal == "eligible_forms_dropped"
    detail = standing.refusal_detail()
    assert detail["dropped_entries"] == [KIRIM]
    assert detail["baseline_eligible_count"] == 2 and detail["eligible_count"] == 1
    assert detail["new_error_count"] == 0
    assert "kirim" in standing.message()
    assert "read-only flextools_parse_text of the same scope" in standing.message()


def test_a_baseline_without_eligibility_compares_load_errors_only_and_says_so():
    standing = gate.evaluate(_current([], eligible=[PUKUL]), _baseline([], eligible=None))
    assert not standing.refused
    assert standing.baseline_eligible_count is None
    assert "no eligibility baseline" in standing.to_dict()["eligibility_note"]


def test_an_unreadable_current_eligibility_against_a_baseline_refuses():
    standing = gate.evaluate(_current([], eligible=[], eligible_known=False), _baseline([]))
    assert standing.refused and standing.signal == "eligible_forms_dropped"


def test_a_newly_eligible_entry_does_not_block():
    extra = {"entry_guid": "e3", "headword": "baru"}
    standing = gate.evaluate(_current([], eligible=[PUKUL, KIRIM, extra]), _baseline([]))
    assert not standing.refused


# ---------------------------------------------------------------------------
# The detail validates as the contract's model
# ---------------------------------------------------------------------------


def test_the_refusal_detail_validates_as_grammar_load_unclean():
    from flextoolsmcp.server.response_models import GrammarLoadUncleanDetail

    standing = gate.evaluate(_current([ERR_A]), _baseline([]))
    GrammarLoadUncleanDetail(**standing.refusal_detail())


# ---------------------------------------------------------------------------
# find_baseline -- by created_at, this project and scope, captured only
# ---------------------------------------------------------------------------

FINGERPRINT = {"scope_kind": "words", "scope_value": ["pukul"], "text_ids": [],
               "word_count": 1, "limit": None, "truncated": False, "engine": "HC",
               "vernacular_ws": "id"}


def _record(record_dir, *, created_at, errors, project=PROJECT, key=None, captured=True,
            filing=None, eligible=None):
    record = RunRecord.create(project_name=project, words_total=1, record_dir=record_dir,
                              words=["pukul"], scope_fingerprint=FINGERPRINT)
    baseline = {"captured": captured, "source": "x", "errors": errors,
                "scope_fingerprint_key": key or fingerprint_key(FINGERPRINT)}
    if eligible is not None:
        baseline["eligible_entries"] = eligible
    meta = record.read_meta()
    meta.created_at = created_at
    meta.load_error_baseline = baseline
    meta.filing = filing
    meta.stage = "completed"
    record.write_meta(meta)
    return record


def test_the_newest_by_created_at_is_the_baseline_not_the_newest_by_name(tmp_path):
    key = fingerprint_key(FINGERPRINT)
    newer = _record(tmp_path, created_at="2026-09-24T12:00:00+00:00", errors=[ERR_A])
    older = _record(tmp_path, created_at="2026-09-24T09:00:00+00:00", errors=[])
    # Touch the older one last, so mtime order disagrees with created_at.
    os.utime(older.meta_path, None)
    found = gate.find_baseline(PROJECT, key, record_dir=tmp_path)
    assert found.run_id == newer.run_id and found.errors == [ERR_A]


def test_another_project_scope_or_an_uncaptured_baseline_is_not_used(tmp_path):
    key = fingerprint_key(FINGERPRINT)
    _record(tmp_path, created_at="2026-09-24T12:00:00+00:00", errors=[], project="Other")
    _record(tmp_path, created_at="2026-09-24T12:01:00+00:00", errors=[], key="0" * 16)
    _record(tmp_path, created_at="2026-09-24T12:02:00+00:00", errors=[], captured=False)
    assert gate.find_baseline(PROJECT, key, record_dir=tmp_path) is None


def test_a_filing_run_never_re_baselines(tmp_path):
    """Only a READ-ONLY run re-baselines (FR-021). A filing run refused mid-run
    loaded the very grammar the gate refused; it must not whitewash it."""
    key = fingerprint_key(FINGERPRINT)
    _record(tmp_path, created_at="2026-09-24T09:00:00+00:00", errors=[])
    _record(tmp_path, created_at="2026-09-24T12:00:00+00:00", errors=[ERR_A],
            filing={"requested": True, "state": "refused_midrun"})
    assert gate.find_baseline(PROJECT, key, record_dir=tmp_path).errors == []


def test_the_baseline_carries_its_eligible_entries(tmp_path):
    key = fingerprint_key(FINGERPRINT)
    _record(tmp_path, created_at="2026-09-24T09:00:00+00:00", errors=[], eligible=[PUKUL])
    assert gate.find_baseline(PROJECT, key, record_dir=tmp_path).eligible == [PUKUL]


# ---------------------------------------------------------------------------
# Wired into the preview (row 9) -- refused before any plan exists
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("current,signal", [
    (clean_gate(morpher_null=True), "morpher_null"),
    (clean_gate(eligible=[{"entry_guid": "e1", "headword": "pukul"}]), "eligible_forms_dropped"),
])
def test_the_preview_refuses_on_the_gate_and_issues_no_plan(filing_env, current, signal):
    worker = FakeReadWorker(facts={"pukul": [analysis("a1")]}, gate=current)
    runner = filing_env.install(worker)
    key = None
    _seed_baseline(filing_env, runner, worker)
    payload = asyncio.run(call(filing_args()))
    assert payload["error_code"] == "grammar_load_unclean", payload
    assert payload["signal"] == signal
    assert "filing_preview" not in worker.calls, "no plan is built for a refused grammar"
    assert filing_env.pool.spawned == []
    assert key is None and not any(filing_env.tmp_path.joinpath("backups").glob("*"))


def test_the_preview_counts_pre_existing_errors_in_the_plan(filing_env):
    worker = FakeReadWorker(facts={"pukul": [analysis("a1")]}, gate=clean_gate([ERR_A]))
    filing_env.install(worker)
    payload = asyncio.run(call(filing_args()))
    assert payload["error_code"] == "confirmation_required"
    assert payload["plan"]["gate"]["status"] == "pre_existing_errors"
    assert payload["plan"]["gate"]["baseline_source"] == "absent"
    assert payload["plan"]["gate"]["pre_existing_error_count"] == 1


def _seed_baseline(filing_env, runner, worker):
    """A prior read-only run of the scope, recording a clean two-entry baseline."""
    from flextoolsmcp.server.parse.fingerprint import build_fingerprint
    from flextoolsmcp.server.models import ResolvedScope
    from filing_fakes import resolved_words

    resolved = ResolvedScope(**resolved_words(["pukul", "kirim"]))
    fp = build_fingerprint(resolved, "HC").to_dict()
    record = RunRecord.create(project_name=PROJECT, words_total=2,
                              record_dir=filing_env.record_dir, words=["pukul", "kirim"],
                              scope_fingerprint=fp)
    meta = record.read_meta()
    meta.stage = "completed"
    meta.load_error_baseline = {
        "captured": True, "source": "x", "errors": [],
        "scope_fingerprint_key": fingerprint_key(fp),
        "eligible_entries": [{"entry_guid": "e1", "headword": "pukul"},
                             {"entry_guid": "e2", "headword": "kirim"}],
    }
    record.write_meta(meta)
    return record
