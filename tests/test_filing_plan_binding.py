#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The mutation plan, and the confirmation bound to it (parser-check CP4,
FR-006, FR-010, FR-016; R-08).

Plan-shape half (tasks.md T031):
  * every data-model section 2 key is present (FR-010);
  * CP3's `duplicate_projection` is carried through, unchanged (FR-016);
  * `plan_id` is sha256 over the canonical JSON of the BOUND fields: stable
    under key order, blind to display-only wording, moved by any count.

Binding half (tasks.md T032, a TRIPWIRE): a confirmation reaches filing only
with a `plan_id` this session issued AND equal to the plan recomputed at
confirm time. A bare `confirmed=True` -- the naive reading of `run_module`'s
rung -- fails here.
"""

import asyncio
import re

import pytest

import filing_fakes
from filing_fakes import (
    FakeReadWorker,
    analysis,
    call,
    filing_args,
)
from flextoolsmcp.server.filing import plan as plan_mod
from flextoolsmcp.server.filing import projection
from flextoolsmcp.server.signals.projections import duplicate_projection

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env

#: data-model.md section 2, every key.
PLAN_KEYS = {
    "scope", "scope_fingerprint_key", "words_in_scope", "gate",
    "deletion_projection", "disapproval_overwrites", "in_use_approvals_projected",
    "duplicate_disclosure", "errored_word_rule", "backup", "access",
    "send_receive", "recovery_route", "side_effects", "confirmation_setting",
    "estimate_note",
}

STATE = {"parser_has_ever_run": True, "analyses_total": 2, "parser_created_analyses": 2,
         "human_opinion_analyses": 0, "indeterminate_analyses": 0, "truncated": False}

CLEAN_GATE = {
    "status": "clean", "signal": None, "load_error_count": 0, "pre_existing_error_count": 0,
    "new_errors": [], "resolved_error_count": 0, "eligible_count": 2,
    "baseline_eligible_count": 2, "dropped_entries": [], "baseline_source": "absent",
    "hypothesis_note": "x",
}


def _facts(**words):
    return {w: {"wordform": w, "found": True, "analyses": a} for w, a in words.items()}


def _build(**overrides):
    kwargs = dict(
        scope={"kind": "words", "value": ["a", "b"], "limit": None},
        scope_fingerprint_key="0123456789abcdef",
        words_in_scope=2,
        gate=dict(CLEAN_GATE),
        projection=projection.project(_facts(a=[analysis("g1")], b=[analysis("g2")]), STATE),
        duplicate_disclosure={"count": 0, "basis": "absent"},
        backup={"outcome": "will_be_taken", "reason": None},
        access={"verdict": "free"},
        send_receive=False,
        require_write_confirmation=True,
    )
    kwargs.update(overrides)
    return plan_mod.build_plan(**kwargs)


def test_every_data_model_key_is_present():
    plan, plan_id = _build()
    assert set(plan) == PLAN_KEYS
    assert re.fullmatch(r"[0-9a-f]{64}", plan_id)


def test_the_plan_carries_the_projection_and_its_counts():
    plan, _ = _build()
    assert plan["deletion_projection"]["upper_bound"] == 2
    assert plan["deletion_projection"]["by_wordform"] == {"a": ["g1"], "b": ["g2"]}
    assert plan["disapproval_overwrites"] == {"count": 0, "by_wordform": {}}
    assert plan["in_use_approvals_projected"] == 0


def test_the_duplicate_disclosure_is_cp3s_projection_carried_through():
    lines = [{
        "wordform": "rumah",
        "parse": {
            "analyses": [{"signature": [["f", "m", None]], "morph_glosses": ["house"]}],
            "human_analyses": [{"analysis_guid": "h", "opinion": "approves", "bundle_count": 0,
                                "complete_bundle_count": 0, "gloss": "house",
                                "signature": [], "parser_evaluated": False}],
        },
    }]
    disclosed = plan_mod.duplicate_disclosure(lines, basis="prior_run:" + "a" * 32)
    assert disclosed["count"] == duplicate_projection(lines)["count"]
    assert disclosed["basis"] == "prior_run:" + "a" * 32


def test_with_no_prior_run_the_duplicate_count_is_unknown_not_zero():
    disclosed = plan_mod.duplicate_disclosure(None, basis="absent")
    assert disclosed["count"] is None
    assert disclosed["basis"] == "absent"


def test_plan_id_is_stable_under_key_order():
    first = _build()[1]
    scope = {"limit": None, "value": ["a", "b"], "kind": "words"}
    assert _build(scope=scope)[1] == first


def test_plan_id_ignores_display_only_wording():
    plan, plan_id = _build()
    assert plan_mod.plan_id_for(dict(plan, estimate_note="reworded")) == plan_id
    assert plan_mod.plan_id_for(dict(plan, recovery_route="reworded")) == plan_id
    assert plan_mod.plan_id_for(dict(plan, side_effects=["x"])) == plan_id


@pytest.mark.parametrize("change", [
    {"words_in_scope": 3},
    {"send_receive": True},
    {"access": {"verdict": "open_shared"}},
    {"backup": {"outcome": "not_expected", "reason": "insufficient_disk_space"}},
    {"gate": dict(CLEAN_GATE, status="pre_existing_errors", pre_existing_error_count=1)},
])
def test_plan_id_moves_with_every_bound_field(change):
    assert _build(**change)[1] != _build()[1]


def test_plan_id_moves_when_one_more_analysis_is_deletable():
    more = projection.project(
        _facts(a=[analysis("g1"), analysis("g9")], b=[analysis("g2")]), STATE
    )
    assert _build(projection=more)[1] != _build()[1]


def test_the_confirmation_setting_is_disclosed_never_honoured():
    plan, _ = _build(require_write_confirmation=False)
    assert plan["confirmation_setting"] == {
        "require_write_confirmation": False, "effective_for_filing": True,
    }


def test_the_errored_word_rule_is_the_fixed_sentence():
    plan, _ = _build()
    assert plan["errored_word_rule"] == (
        "A word whose parse ends in an error is filed as FLEx files it: its parser "
        "opinions are cleared and its unshielded, unreviewed analyses are deleted."
    )


# ===========================================================================
# Binding half (T032) -- the TRIPWIRE. A bare `confirmed` flag must fail.
# ===========================================================================


def _preview(filing_env, **extra):
    payload = asyncio.run(call(filing_args(**extra)))
    assert payload["error_code"] == "confirmation_required", payload
    return payload


def test_confirmed_without_a_plan_id_re_previews(filing_env):
    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1")]}))
    payload = _preview(filing_env, confirmed=True)
    assert re.fullmatch(r"[0-9a-f]{64}", payload["plan_id"])
    assert filing_env.pool.spawned == [], "nothing may start without a bound confirmation"


def test_confirmed_with_a_foreign_plan_id_re_previews(filing_env):
    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1")]}))
    foreign = "f" * 64
    payload = _preview(filing_env, confirmed=True, plan_id=foreign)
    assert payload["plan_id"] != foreign
    assert filing_env.pool.spawned == []


def test_a_plan_that_changed_since_the_preview_re_previews_with_a_new_id(filing_env):
    worker = FakeReadWorker(facts={"pukul": [analysis("a1")]})
    filing_env.install(worker)
    first = _preview(filing_env)
    assert first["plan"]["deletion_projection"]["upper_bound"] == 1

    worker.facts["pukul"].append(analysis("a2"))  # one more deletable analysis
    second = _preview(filing_env, confirmed=True, plan_id=first["plan_id"])

    assert second["plan_id"] != first["plan_id"]
    assert second["plan"]["deletion_projection"]["upper_bound"] == 2
    assert filing_env.pool.spawned == []


def test_a_plan_issued_for_another_scope_does_not_confirm_this_one(filing_env):
    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1")]}))
    other = _preview(filing_env, scope_value=["pukul"])
    payload = _preview(filing_env, confirmed=True, plan_id=other["plan_id"])
    assert payload["plan_id"] != other["plan_id"]
    assert filing_env.pool.spawned == []


def test_the_matching_plan_id_starts_the_run(filing_env):
    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1")]}))
    first = _preview(filing_env)
    started = asyncio.run(call(filing_args(confirmed=True, plan_id=first["plan_id"])))
    assert started.get("filing") == "started", started
    assert started["plan_id"] == first["plan_id"]
    assert filing_env.pool.spawned == ["filing"]
