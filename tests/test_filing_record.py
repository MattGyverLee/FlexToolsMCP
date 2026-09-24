#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
What a filing run's record says afterwards (parser-check CP4, US6; FR-032,
FR-033, FR-041; data-model sections 7 and 9; SC-011 offline half).

Days later, the linguist asks what that filing run changed. The record
answers from disk -- `flextools_parse_log`, which never touches a worker:

  * the `summary` section's `filing` block: every count of data-model
    section 7, projected deletions BESIDE actual ones, the backup or the
    no-recovery warning, the confirmed plan and its id (FR-032);
  * the in-use approvals, counted and worded as recorded-for-anything-in-use
    -- verbatim, never as the user having reviewed them (FR-033);
  * every human disapproval filing overwrote, listed with the PRIOR
    evaluation captured before the overwrite (FR-041, D-2);
  * a `deletions` section serving the pre-deletion captures; on a read-only
    run it is a typed not-applicable, never an empty section.

And nothing a filing run emits labels an analysis `tacit`, `unreviewed`,
`auto_approved` or `auto-approved` (FR-033, contracts section 3). The scan
covers every filing response and the record's filing section; the one
exemption is FR-017's own mandated sentence (see `filing/wording.py`).
"""

import asyncio
import json

import filing_fakes
from filing_fakes import FakeFilingWorker, FakeReadWorker, analysis, call, filing_args
from flextoolsmcp.server.filing import wording
from flextoolsmcp.server.handlers import parse as parse_handler

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env

COUNT_KEYS = {"created", "reapproved", "duplicated", "deleted", "unchanged",
              "errored_words", "errored_word_deletions", "skipped"}

CAPTURE = {"kind": "pre_deletion", "analysis_guid": "gone",
           "morph_bundles": [{"morph_guid": "m", "msa_guid": "s", "infl_type_guid": None,
                              "form": "pukul"}],
           "glosses": [{"guid": "g", "form_by_ws": {"1": "hit"}}],
           "evaluations": [], "category": "v"}
OVERWRITE = {"kind": "disapproval_overwrite", "analysis_guid": "d1",
             "prior_user_opinion": "disapproves",
             "morph_bundles": [], "glosses": [],
             "evaluations": [{"agent_guid": "u", "agent_name": "User", "human": True,
                              "opinion": "disapproves", "date": "2026-01-01"}],
             "category": ""}


def _outcomes():
    counts = {"created": 1, "reapproved": 1, "deleted": 1}
    return {
        "pukul": {"wordform": "pukul", "outcome": "filed", "counts": counts,
                  "deleted": ["gone"], "created": ["new"], "overwritten": ["d1"],
                  "in_use_approvals_recorded": 2, "captures": [CAPTURE, OVERWRITE]},
        "kirim": {"wordform": "kirim", "outcome": "skipped", "skip_reason": "outside_projection",
                  "counts": {"skipped": {"outside_projection": 1}}},
    }


async def _file(filing_env):
    filing_env.install(
        FakeReadWorker(facts={"pukul": [analysis("gone"),
                                        analysis("d1", opinion="disapproves", in_segment=True)]}),
        FakeFilingWorker(outcomes=_outcomes()),
    )
    responses = []
    first = await call(filing_args())
    responses.append(first)
    started = await call(filing_args(confirmed=True, plan_id=first["plan_id"]))
    responses.append(started)
    handle = filing_env.runner.get(started["run_id"])
    await asyncio.wait_for(handle.done.wait(), timeout=10)
    return started["run_id"], responses


async def _log(run_id, section="summary", **extra):
    response = await parse_handler.handle_flextools_parse_log(
        {"run_id": run_id, "section": section, **extra})
    return json.loads(response[0].text)


async def test_the_summary_carries_every_count_and_projected_beside_actual(filing_env):
    run_id, _ = await _file(filing_env)
    filing = (await _log(run_id))["content"]["filing"]
    assert set(filing["counts"]) == COUNT_KEYS
    assert filing["counts"]["created"] == 1 and filing["counts"]["deleted"] == 1
    assert filing["counts"]["skipped"]["outside_projection"] == 1
    assert filing["projected_deletions"] == 1 and filing["actual_deletions"] == 1
    assert filing["state"] == "completed" and filing["persisted"] is True
    assert filing["filed_words"] == ["pukul"]
    assert filing["plan_id"] and filing["confirmed_plan"]["deletion_projection"]
    assert filing["backup"]["path"] or filing["no_recovery_warning"]


async def test_in_use_approvals_are_counted_and_worded_verbatim(filing_env):
    run_id, _ = await _file(filing_env)
    filing = (await _log(run_id))["content"]["filing"]
    assert filing["in_use_approvals_recorded"] == 2
    assert filing["in_use_approvals_note"] == (
        "2 analyses in use in a text were given a user approval by filing. Approval is "
        "recorded for anything left in use; this does not mean anyone reviewed them."
    )


async def test_every_overwritten_disapproval_is_listed_with_the_prior_evaluation(filing_env):
    run_id, _ = await _file(filing_env)
    filing = (await _log(run_id))["content"]["filing"]
    assert [d["analysis_guid"] for d in filing["disapprovals_overwritten"]] == ["d1"]
    assert filing["disapprovals_overwritten"][0]["prior_user_opinion"] == "disapproves"
    deletions = await _log(run_id, "deletions")
    overwrite = next(line for line in deletions["items"] if line["kind"] == "disapproval_overwrite")
    assert overwrite["evaluations"][0]["opinion"] == "disapproves"


async def test_the_deletions_section_serves_the_captures(filing_env):
    run_id, _ = await _file(filing_env)
    deletions = await _log(run_id, "deletions")
    assert deletions["applicable"] is True
    capture = next(line for line in deletions["items"] if line["kind"] == "pre_deletion")
    assert capture["analysis_guid"] == "gone" and capture["wordform"] == "pukul"
    assert capture["morph_bundles"] and capture["glosses"]


async def test_on_a_read_only_run_deletions_is_typed_not_applicable_never_empty(filing_env):
    filing_env.install(FakeReadWorker())
    submitted = await call({"scope_kind": "words", "scope_value": ["a"]})
    await asyncio.wait_for(filing_env.runner.get(submitted["run_id"]).done.wait(), timeout=5)
    payload = await _log(submitted["run_id"], "deletions")
    assert payload["status"] == "ok"
    assert payload["applicable"] is False
    assert payload["reason"] == "not_applicable_for_this_run"
    assert "filing runs only" in payload["note"]


async def test_a_filing_run_with_no_captures_says_so(filing_env):
    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1", opinion="approves")]}),
                       FakeFilingWorker())
    first = await call(filing_args())
    started = await call(filing_args(confirmed=True, plan_id=first["plan_id"]))
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=10)
    payload = await _log(started["run_id"], "deletions")
    assert payload["applicable"] is True and payload["items"] == []
    assert payload["note"], "an empty section always says why"


# ---------------------------------------------------------------------------
# FR-033 -- the forbidden words, in every filing output
# ---------------------------------------------------------------------------


def _scrub(text):
    for exempt in wording.FORBIDDEN_SCAN_EXEMPT:
        text = text.replace(exempt, "")
    return text.lower()


async def test_no_filing_output_says_tacit_unreviewed_or_auto_approved(filing_env):
    run_id, responses = await _file(filing_env)
    emitted = [json.dumps(r) for r in responses]
    emitted.append(json.dumps((await _log(run_id))["content"]["filing"]))
    emitted.append(json.dumps(await _log(run_id, "deletions")))
    status = await parse_handler.handle_flextools_parse_status({"run_id": run_id})
    emitted.append(status[0].text)
    meta = json.loads((filing_env.record_dir / run_id / "meta.json").read_text("utf-8"))
    emitted.append(json.dumps(meta["filing"]))
    for text in emitted:
        scrubbed = _scrub(text)
        for word in wording.FORBIDDEN_WORDS:
            assert word not in scrubbed, (word, text[:300])


def test_the_exemption_is_exactly_the_mandated_sentences():
    """FR-017's errored-word rule and CP3's two counter-divergence statements
    (which deny the label rather than apply it) -- and nothing else."""
    from flextoolsmcp.server.parse.record import COUNTER_DIVERGENCES

    assert wording.FORBIDDEN_SCAN_EXEMPT == (wording.ERRORED_WORD_RULE,) + tuple(COUNTER_DIVERGENCES)
    assert len(wording.FORBIDDEN_SCAN_EXEMPT) == 3
