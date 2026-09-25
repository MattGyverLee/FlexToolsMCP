#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The filing preview stays a readable size on a large scope.

An all_texts preview of 26k words once returned every projected GUID inline
(24k GUIDs, 3.4 MB). Past a threshold the RESPONSE now carries a sample and a
summary of each long list, and the full plan goes to a file. What the session
stores and `plan_id` binds is the full plan, unchanged: confirming a compact
preview still starts the run, and the file holds exactly the bound plan.
"""

import asyncio
import json
import os
from pathlib import Path

import filing_fakes
from filing_fakes import FakeReadWorker, analysis, call, filing_args
from flextoolsmcp.server.filing import plan as plan_mod
from flextoolsmcp.server.handlers import parse as parse_handler

filing_env = filing_fakes.filing_env

_WORDS = [f"w{i:04d}" for i in range(parse_handler._PREVIEW_INLINE_GUIDS + 50)]


def _preview(**extra):
    payload = asyncio.run(call(filing_args(**extra)))
    assert payload["error_code"] == "confirmation_required", payload
    return payload


def test_a_small_preview_carries_the_whole_plan_inline(filing_env):
    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1")]}))
    payload = _preview()
    deletion = payload["plan"]["deletion_projection"]
    assert deletion["by_wordform"] == {"pukul": ["a1"]}
    assert "by_wordform_sample" not in deletion
    assert "detail" not in payload["plan"]
    assert not (filing_env.record_dir / "plans").exists()


def test_a_large_preview_is_compact_and_names_the_full_plan_file(filing_env):
    filing_env.install(FakeReadWorker(facts={w: [analysis(f"g-{w}")] for w in _WORDS}))
    payload = _preview(scope_value=_WORDS)
    plan = payload["plan"]
    deletion = plan["deletion_projection"]

    assert "by_wordform" not in deletion
    assert len(deletion["by_wordform_sample"]) == parse_handler._PREVIEW_SAMPLE_WORDFORMS
    assert deletion["by_wordform_summary"] == {
        "wordforms": len(_WORDS), "analyses": len(_WORDS),
        "sample_wordforms": parse_handler._PREVIEW_SAMPLE_WORDFORMS,
    }
    assert deletion["upper_bound"] == len(_WORDS)

    path = Path(plan["detail"]["full_plan_path"])
    assert path.parent == filing_env.record_dir / "plans"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["plan_id"] == payload["plan_id"]
    assert len(stored["plan"]["deletion_projection"]["by_wordform"]) == len(_WORDS)
    # The file holds the BOUND plan: it hashes to the plan_id the preview gave.
    assert plan_mod.plan_id_for(stored["plan"]) == payload["plan_id"]


def test_confirming_a_compact_preview_starts_the_run(filing_env):
    filing_env.install(FakeReadWorker(facts={w: [analysis(f"g-{w}")] for w in _WORDS}))
    first = _preview(scope_value=_WORDS)
    started = asyncio.run(call(filing_args(scope_value=_WORDS, confirmed=True,
                                           plan_id=first["plan_id"])))
    assert started.get("filing") == "started", started
    assert filing_env.pool.spawned == ["filing"]


def test_a_failed_plan_file_write_does_not_fail_the_preview(filing_env, monkeypatch):
    filing_env.install(FakeReadWorker(facts={w: [analysis(f"g-{w}")] for w in _WORDS}))

    def refuse(path, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(parse_handler.filing_paths, "assert_outside_project", refuse)
    payload = _preview(scope_value=_WORDS)
    detail = payload["plan"]["detail"]
    assert "full_plan_path" not in detail
    assert detail["full_plan_unavailable"] == "OSError: disk full"


def test_only_the_newest_plan_files_are_kept(filing_env, monkeypatch):
    monkeypatch.setattr(parse_handler, "_PREVIEW_PLANS_KEPT", 2)
    plans = filing_env.record_dir / "plans"
    plans.mkdir(parents=True)
    for i in range(3):
        old = plans / f"{i:064x}.json"
        old.write_text("{}", encoding="utf-8")
        os.utime(old, (1_000_000 + i, 1_000_000 + i))
    filing_env.install(FakeReadWorker(facts={w: [analysis(f"g-{w}")] for w in _WORDS}))
    payload = _preview(scope_value=_WORDS)
    kept = sorted(p.name for p in plans.glob("*.json"))
    assert kept == sorted([f"{payload['plan_id']}.json", f"{2:064x}.json"])
