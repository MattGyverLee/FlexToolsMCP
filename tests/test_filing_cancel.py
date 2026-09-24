#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cancelling a filing run, and the cancel tool (parser-check CP4, FR-034, M-3;
contracts/tools.md section 1, `flextools_parse_cancel`).

A filing run cancelled part way stops at a WORD BOUNDARY: the word in flight
finishes, nothing after it starts. Everything filed before the cancel stays
filed -- filing cannot be undone -- so the record states exactly which words
were filed and says, verbatim, that the way back is the backup (or, for a
Send/Receive project, the discard-and-re-download route).

`flextools_parse_cancel` is a new tool rather than an action on
`flextools_parse_status`, whose read-only annotation callers rely on:
unknown handle -> `parse_run_not_found`; already-ended run ->
`parse_job_cancelled`; otherwise `{run_id, cancel_requested: true}`. It works
on read-only runs too -- the runner always supported that.
"""

import asyncio
import json

import filing_fakes
from filing_fakes import FakeFilingWorker, FakeReadWorker, analysis, call, filing_args
from flextoolsmcp.server.filing import wording
from flextoolsmcp.server.handlers import parse as parse_handler

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env

WORDS = ["w1", "w2", "w3", "w4", "w5", "w6"]


async def _cancel(run_id):
    response = await parse_handler.handle_flextools_parse_cancel({"run_id": run_id})
    return json.loads(response[0].text)


async def _start_filing(filing_env, *, delay=0.2):
    filing_env.install(
        FakeReadWorker(facts={w: [analysis(f"a-{w}")] for w in WORDS}),
        FakeFilingWorker(delay=delay),
        grace_window=0.05,
    )
    first = await call(filing_args(scope_value=WORDS))
    assert first["error_code"] == "confirmation_required", first
    started = await call(filing_args(scope_value=WORDS, confirmed=True, plan_id=first["plan_id"]))
    assert started["filing"] == "started", started
    return started


async def test_a_cancelled_filing_run_stops_at_a_word_boundary_and_says_what_was_filed(filing_env):
    started = await _start_filing(filing_env)
    handle = filing_env.runner.get(started["run_id"])
    while handle.words_completed < 2:
        await asyncio.sleep(0.02)

    answer = await _cancel(started["run_id"])
    assert answer["cancel_requested"] is True
    assert answer["filing_note"] == wording.CANCEL_NOTE
    await asyncio.wait_for(handle.done.wait(), timeout=5)

    meta = json.loads((filing_env.record_dir / started["run_id"] / "meta.json").read_text("utf-8"))
    assert meta["stage"] == "cancelled"
    filing = meta["filing"]
    assert filing["state"] == "cancelled"
    assert filing["filed_words"] == filing_env.filing.words[: len(filing["filed_words"])]
    assert 2 <= len(filing["filed_words"]) < len(WORDS), "stopped part way, at a boundary"
    assert filing["cancel_note"] == wording.CANCEL_NOTE


def test_the_cancel_note_is_verbatim():
    assert wording.CANCEL_NOTE == (
        "Cancellation stops the run at its next word boundary. Every word filed "
        "before that stays filed: filing cannot be undone except by restoring the "
        "backup (or, for a project in Send/Receive, by discarding this copy and "
        "re-downloading it). The run's record lists exactly which words were filed."
    )


async def test_the_claim_clears_when_the_cancelled_run_ends(filing_env):
    from flextoolsmcp.server.filing import claims

    started = await _start_filing(filing_env)
    assert claims.lookup(filing_fakes.PROJECT) is not None
    await _cancel(started["run_id"])
    await asyncio.wait_for(filing_env.runner.get(started["run_id"]).done.wait(), timeout=5)
    assert claims.lookup(filing_fakes.PROJECT) is None


# ---------------------------------------------------------------------------
# The tool's three answers
# ---------------------------------------------------------------------------


async def test_an_unknown_handle_is_parse_run_not_found(filing_env):
    filing_env.install(FakeReadWorker())
    answer = await _cancel("0" * 32)
    assert answer["error_code"] == "parse_run_not_found"
    assert answer["available_runs"] == []


async def test_an_ended_run_is_parse_job_cancelled(filing_env):
    filing_env.install(FakeReadWorker())
    submitted = await call({"scope_kind": "words", "scope_value": ["a"]})
    handle = filing_env.runner.get(submitted["run_id"])
    await asyncio.wait_for(handle.done.wait(), timeout=5)
    answer = await _cancel(submitted["run_id"])
    assert answer["error_code"] == "parse_job_cancelled"
    assert answer["state_at_cancel"] == "completed"


async def test_a_read_only_batch_can_be_cancelled_too(filing_env):
    class SlowRead(FakeReadWorker):
        async def parse_word(self, **kwargs):
            await asyncio.sleep(0.2)
            return await super().parse_word(**kwargs)

    filing_env.install(SlowRead(), grace_window=0.05)
    submitted = await call({"scope_kind": "words", "scope_value": WORDS})
    answer = await _cancel(submitted["run_id"])
    assert answer["cancel_requested"] is True
    assert "filing_note" not in answer, "a read-only run filed nothing to warn about"
    handle = filing_env.runner.get(submitted["run_id"])
    await asyncio.wait_for(handle.done.wait(), timeout=5)
    assert handle.stage.value == "cancelled"


def test_the_cancel_tool_is_not_read_only_and_not_destructive():
    from flextoolsmcp.server.tool_definitions import TOOLS

    annotations = TOOLS["flextools_parse_cancel"].annotations
    assert annotations.readOnlyHint is False
    assert annotations.destructiveHint is False
    assert annotations.idempotentHint is True
    assert TOOLS["flextools_parse_status"].annotations.readOnlyHint is True
