#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The caller's hypothesis is never overruled
(parser-check CP2b; FR-023, FR-024, FR-025; SC-006; contracts/tools.md,
"The caller's hypothesis is never overruled").

WHAT THIS FILE PROTECTS, in one sentence: a linguist reaches for the
restricted level precisely when the word is irregular and the recorded
analyses are wrong or absent, so a tool that quietly prefers recorded
analyses is useless in exactly the case it was built for.

SC-006 IS SIX ZEROS, and they are asserted as zeros rather than as
behaviour, because each has a plausible-looking implementation that would
pass a "does it work" test:

    0 substitutions   -- "the caller clearly meant this other entry"
    0 widenings       -- "nothing matched, so search everything"
    0 reorderings     -- "canonical order makes the trace easier to read"
    0 scorings        -- "rank the analyses so the best is first"
    0 demotions       -- "this one disagrees with the lexicon, so last"
    0 confidence figures on a user hypothesis
    0 remarks when the proposal agrees with recorded analyses

THE TEST THAT MATTERS MOST is
`test_a_decomposition_disagreeing_with_everything_is_still_traced`. A
ranking-by-agreement implementation -- the most natural wrong thing to
build, because it feels helpful -- passes every other test in this file and
fails that one. It is written so that it cannot be made to pass by
weakening: it asserts the trace happened, with the caller's exact selection,
and that nothing was said about the disagreement.

These run against doubles. The restriction reaching the parser unchanged in
a LIVE run is quickstart scenario 4 (`tests/test_parse_live.py`).

Run with:
    python -m pytest tests/test_parse_proposal.py -q
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402

# The doubles are shared with the handler tests rather than re-declared:
# two stand-ins for one worker drift, and the one in the newer file always
# drifts toward whatever makes its own assertions pass.
from test_try_word_handler import Pool, RecordingWorker  # noqa: E402


#: Any key that would amount to a judgement on the caller's hypothesis.
#: Asserted as an ABSENCE across the whole response, at every nesting level,
#: because the failure mode is additive: someone adds a `confidence` "just
#: for information" and the tool starts grading a linguist's analysis.
_JUDGEMENT_KEYS = re.compile(
    r"confidence|score|rank|probability|likelihood|certainty|"
    r"best|preferred|recommended|quality|grade",
    re.IGNORECASE,
)


def _walk(node, path="$"):
    """Every (path, key, value) in a nested response."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def assert_no_judgement(payload):
    offenders = [
        f"{path}.{key}"
        for path, key, _ in _walk(payload)
        if _JUDGEMENT_KEYS.search(str(key))
    ]
    assert not offenders, (
        "the response grades the caller's hypothesis: "
        + ", ".join(offenders)
        + ". A confidence figure attached to a linguist's own analysis is "
        "the tool substituting its judgement for theirs (FR-024, SC-006)."
    )


@pytest.fixture
def worker():
    return RecordingWorker()


@pytest.fixture
def wired(worker, tmp_path, monkeypatch):
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    parse_handler.set_runner(
        ParseRunner(pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=30.0)
    )
    try:
        yield worker
    finally:
        parse_handler.set_runner(None)


async def call(**kwargs):
    args = {"project_name": "P"}
    args.update(kwargs)
    response = await parse_handler.handle_flextools_try_word(args)
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# FR-023 -- traced exactly as given
# ---------------------------------------------------------------------------


async def test_the_selection_reaching_the_parser_is_the_one_given(wired):
    payload = await call(
        word="makan",
        level="restricted",
        morphs=[{"msa_hvo": 5001}, {"msa_hvo": 5002}],
    )

    assert list(wired.calls[0]["restricted_to"]) == [5001, 5002]
    assert payload["restricted_to"] == [5001, 5002]


async def test_the_order_given_is_the_order_traced(wired):
    """No canonical reordering, however tidy it would look.

    Order is information in a decomposition: it is the caller saying which
    piece comes first. Sorting it would silently answer a different
    question and there would be no way for the caller to see that from the
    response.
    """
    await call(
        word="makan",
        level="restricted",
        morphs=[{"msa_hvo": 5003}, {"msa_hvo": 5001}, {"msa_hvo": 5002}],
    )

    assert list(wired.calls[0]["restricted_to"]) == [5003, 5001, 5002], (
        "the selection was reordered on its way to the parser"
    )


async def test_no_substitution_when_a_similar_entry_exists(wired):
    """`kirim` is ambiguous in the stub lexicon, so it REFUSES.

    It must not quietly pick one of the two. "The caller clearly meant this
    one" is a substitution, and the whole point of the `ambiguous` outcome
    is that the tool does not know which they meant.
    """
    payload = await call(
        word="mengirim", level="restricted", morphs=[{"headword": "kirim"}]
    )

    assert payload["status"] == "error"
    assert payload["error_code"] == "parse_morph_unresolved"
    assert payload["resolved_to"] == "ambiguous"
    assert wired.calls == [], "a substitute was parsed instead of refusing"


async def test_a_refusal_never_widens_to_an_unrestricted_search(wired):
    """Nothing resolved is a refusal, never a fallback to `explain`.

    The underlying component reads an empty restriction as "admit nothing",
    the opposite of "no restriction", and the setting outlives the call --
    so a widening here would not even be contained to this request.
    """
    payload = await call(
        word="makan", level="restricted", morphs=[{"headword": "zzzznotaword"}]
    )

    assert payload["error_code"] == "parse_morph_unresolved"
    assert wired.calls == [], "the refusal widened into a parse"
    assert payload.get("level") != "explain"


# ---------------------------------------------------------------------------
# THE ONE THAT CATCHES RANKING BY AGREEMENT
# ---------------------------------------------------------------------------


async def test_a_decomposition_disagreeing_with_everything_is_still_traced(wired):
    """The case most likely to be implemented wrong, and the reason for it.

    `makan` has nothing to do with `pukul`, so this decomposition disagrees
    with every recorded analysis of the word. It must be traced EXACTLY as
    given: not refused, not widened, not demoted, and not remarked upon as
    a mistake.

    This is not a pedantic case. A proposal diverging from every recorded
    analysis may be the correct analysis of an irregular word -- which is
    precisely when a linguist reaches for this tool. An implementation that
    ranked, demoted or refused by agreement with the lexicon would pass
    every other test in this file and fail here.
    """
    payload = await call(
        word="pukul", level="restricted", morphs=[{"headword": "makan"}]
    )

    assert payload["status"] == "ok", (
        f"a decomposition that disagrees with the lexicon was refused: {payload}"
    )
    assert wired.calls, "nothing was traced"
    assert list(wired.calls[0]["restricted_to"]) == [5004], (
        "the caller's selection was not the one traced"
    )
    assert wired.calls[0]["wordform"] == "pukul"
    assert wired.calls[0]["level"] == "restricted"
    assert_no_judgement(payload)

    # Scanned with the filesystem paths removed: `trace_path` lands under
    # pytest's tmp_path, which embeds the name of THIS test -- so a naive
    # scan matches its own title and fails for a reason that has nothing to
    # do with the response.
    prose = {k: v for k, v in payload.items() if not k.endswith("_path")}
    text = json.dumps(prose).lower()
    for word in ("disagree", "unlikely", "incorrect", "should be", "did you mean"):
        assert word not in text, (
            f"the response editorialises about the caller's hypothesis "
            f"({word!r}); FR-024 allows an observation, not a verdict"
        )


# ---------------------------------------------------------------------------
# FR-024 / FR-025 -- no scoring, and silence on agreement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "morphs",
    [
        [{"msa_hvo": 5001}],
        [{"headword": "makan"}],
        [{"msa_hvo": 5001}, {"msa_hvo": 5002}],
    ],
)
async def test_no_confidence_figure_is_ever_attached(wired, morphs):
    payload = await call(word="makan", level="restricted", morphs=morphs)

    assert payload["status"] == "ok", payload
    assert_no_judgement(payload)


async def test_agreement_produces_no_commentary(wired):
    """The proposal matches a recorded analysis. The tool says nothing.

    A tool that congratulates every correct guess teaches the caller to
    skim the field where the real warnings live -- so the absence here is
    protecting the signal elsewhere, not saving bytes.

    NARROWED (CP2b): before this fix, `wired`'s default worker returned
    `parse: None` for every non-plain level, so this test's "agreement"
    was never actually represented -- the assertions below passed for a
    restriction that held a hypothesis exactly as readily as one that
    didn't, because none of them read `hypothesis_held` at all. Configured
    explicitly here so "agreement" means what the docstring says.
    """
    wired.trace_outcome = "success"

    payload = await call(
        word="makan", level="restricted", morphs=[{"headword": "makan"}]
    )

    assert payload["status"] == "ok"
    assert payload["hypothesis_held"] is True, "this is the agreement case"
    assert "parsed" not in payload
    assert payload["next_step"] is None, (
        "the caller used the right level with a hypothesis that resolved; "
        "there is nothing to steer them toward"
    )
    assert "proposed_decomposition" not in payload, (
        "a decomposition was proposed to a caller who supplied one"
    )
    for key in ("commentary", "observations", "notes", "remarks", "agreement"):
        assert key not in payload, f"agreement produced commentary: {key!r}"


async def test_the_restricted_response_carries_no_alternatives_block(wired):
    """No "you might also have meant" alongside a resolved hypothesis.

    Offering alternatives to a caller who already chose is a demotion
    wearing a helpful hat: it presents the tool's options as peers of the
    caller's analysis.
    """
    payload = await call(
        word="makan", level="restricted", morphs=[{"msa_hvo": 5001}]
    )

    for key in ("alternatives", "candidates", "suggestions", "other_analyses"):
        assert key not in payload, (
            f"{key!r} rides alongside a successful restricted trace; "
            f"candidates belong in a REFUSAL, where they help, not beside a "
            f"result the caller did not question"
        )


# ---------------------------------------------------------------------------
# SC-006 as a count
# ---------------------------------------------------------------------------


async def test_sc006_zeros_across_a_batch_of_hypotheses(wired):
    """The six zeros, counted over a spread of decompositions.

    SC-006 is phrased as "100% of cases" and "0 cases of". A handful of
    individually-passing tests is not a count, so this walks a set and
    tallies, which is also what makes the failure message say how many and
    which.
    """
    cases = [
        ("makan", [{"msa_hvo": 5001}]),
        ("makan", [{"msa_hvo": 5002}, {"msa_hvo": 5001}]),
        ("pukul", [{"headword": "makan"}]),
        ("pukul", [{"headword": "pukul"}]),
        ("mengirim", [{"msa_hvo": 5003}, {"msa_hvo": 5004}]),
    ]

    traced_as_given = 0
    judgements = []
    for word, morphs in cases:
        before = len(wired.calls)
        payload = await call(word=word, level="restricted", morphs=morphs)
        assert payload["status"] == "ok", payload

        expected = [m["msa_hvo"] for m in morphs if "msa_hvo" in m] or None
        recorded = list(wired.calls[before]["restricted_to"])
        if expected is None or recorded == expected:
            traced_as_given += 1

        judgements.extend(
            key for _p, key, _v in _walk(payload) if _JUDGEMENT_KEYS.search(str(key))
        )

    assert traced_as_given == len(cases), (
        f"{len(cases) - traced_as_given} of {len(cases)} decompositions were "
        f"not traced exactly as given"
    )
    assert judgements == [], f"{len(judgements)} confidence figures: {judgements}"



# ===========================================================================
# CP3, US6 -- next-step proposals (FR-056, FR-057, FR-058; SC-018, SC-019)
# ===========================================================================
#
# The grammar-scan proposal fires on EXACTLY four conditions: a single word
# that misses the fast-path window; a batch that enters grammar loading and
# stays there; a terminal failure; a bounded measurement that exceeds its
# bound. These tests pin both halves -- it fires there, and nowhere else --
# and then sweep every response shape this feature can emit for the three
# proposal invariants: the tool exists, the cost estimate is present, and the
# arguments validate against that tool's own input model as given.

import asyncio  # noqa: E402
import time  # noqa: E402

from flextoolsmcp.server.parse.priority import Priority  # noqa: E402
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402
from flextoolsmcp.server.parse.worker_client import WorkerError  # noqa: E402
from flextoolsmcp.server.tool_definitions import TOOLS  # noqa: E402

_SCAN = "flextools_grammar_health"

_BATCH_FINGERPRINT = {
    "scope_kind": "words", "scope_value": ["a", "b"], "text_ids": [], "word_count": 2,
    "limit": None, "truncated": False, "engine": "HC", "vernacular_ws": "id",
}


def _rungs(payload):
    return list(payload.get("next_step") or [])


def _scan_count(payload):
    return sum(1 for rung in _rungs(payload) if rung["tool"] == _SCAN)


class HeldWorker(RecordingWorker):
    """A worker whose parse does not return until released -- a slow word."""

    def __init__(self):
        super().__init__()
        self.release = asyncio.Event()

    async def parse_word(self, **kwargs):
        await self.release.wait()
        return await super().parse_word(**kwargs)

    async def cancel_run(self, run_id):
        self.release.set()


@pytest.fixture
def make_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    made = []

    def make(worker, grace_window=30.0):
        runner = ParseRunner(
            pool=Pool(worker), record_dir=tmp_path / f"runs{len(made)}",
            grace_window=grace_window,
        )
        parse_handler.set_runner(runner)
        made.append(runner)
        return runner

    yield make
    parse_handler.set_runner(None)


async def _status(run_id):
    response = await parse_handler.handle_flextools_parse_status({"run_id": run_id})
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# T103 -- SC-018: inline gets 0 scan proposals; a missed window gets exactly 1
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"word": "makan", "level": "plain"},
        {"word": "makan", "level": "explain"},
        {"word": "makan", "level": "restricted", "morphs": [{"msa_hvo": 5001}]},
    ],
)
async def test_a_word_answered_inline_carries_no_scan_proposal(make_runner, kwargs):
    make_runner(RecordingWorker())
    payload = await call(**kwargs)

    assert payload["status"] == "ok"
    assert "run_id" in payload and payload.get("stage") == "completed"
    assert _scan_count(payload) == 0, (
        f"an inline answer carried a grammar-scan proposal: {_rungs(payload)}"
    )


async def test_a_word_that_misses_the_window_carries_exactly_one_scan_proposal(make_runner):
    worker = HeldWorker()
    make_runner(worker, grace_window=0.05)
    try:
        payload = await call(word="makan", level="plain")
    finally:
        worker.release.set()

    assert payload.get("stage") != "completed", "the word was answered inline"
    assert _scan_count(payload) == 1, _rungs(payload)
    scan = next(r for r in _rungs(payload) if r["tool"] == _SCAN)
    assert scan["args"] == {"project_name": "P"}


async def test_a_successful_completed_word_polled_later_carries_no_scan(make_runner):
    runner = make_runner(RecordingWorker())
    handle = await runner.start_run(project_name="P", wordforms=["makan"])
    assert _scan_count(await _status(handle.run_id)) == 0


async def test_a_batch_that_stays_in_grammar_loading_gets_the_scan(make_runner):
    """Trigger 2. "Stayed" is measured: past the fast-path window in the stage."""
    worker = HeldWorker()
    runner = make_runner(worker, grace_window=0.05)
    try:
        handle = await runner.start_run(
            project_name="P", wordforms=["a", "b"], level="batch",
            priority=Priority.LOW, scope_fingerprint=_BATCH_FINGERPRINT,
            engine_at_submission="HC", vernacular_ws="id",
        )
        handle.stage = RunStage.LOADING_GRAMMAR

        handle.stage_entered_at = time.monotonic()
        assert _scan_count(await _status(handle.run_id)) == 0, (
            "a load that has only just begun is not a load that stayed"
        )

        handle.stage_entered_at = time.monotonic() - 60
        payload = await _status(handle.run_id)
        assert _scan_count(payload) == 1, _rungs(payload)
        assert _rungs(payload)[0]["tool"] == "flextools_parse_status"
    finally:
        worker.release.set()


async def test_a_single_word_run_polled_while_loading_is_not_a_batch_trigger(make_runner):
    """Trigger 2 names a BATCH. A single word's trigger was its overflow."""
    worker = HeldWorker()
    runner = make_runner(worker, grace_window=0.05)
    try:
        handle = await runner.start_run(project_name="P", wordforms=["a"])
        handle.stage = RunStage.LOADING_GRAMMAR
        handle.stage_entered_at = time.monotonic() - 60
        assert _scan_count(await _status(handle.run_id)) == 0
    finally:
        worker.release.set()


async def test_a_terminal_failure_carries_the_scan(make_runner):
    """Trigger 3, on both surfaces: the word's own error and a status poll."""
    runner = make_runner(RecordingWorker(fail_with=WorkerError("out of memory")))
    payload = await call(word="makan", level="plain")

    assert payload["status"] == "error"
    assert _scan_count(payload) == 1, _rungs(payload)
    run_id = next(iter(runner.known_run_ids()))
    assert _scan_count(await _status(run_id)) == 1


# ---------------------------------------------------------------------------
# T104 -- SC-019: across every response, 0 nonexistent tools, 0 missing costs
# ---------------------------------------------------------------------------


async def _every_response(make_runner, tmp_path):
    """One response of every shape this feature emits a `next_step` in."""
    payloads = []

    make_runner(RecordingWorker())
    payloads.append(await call(word="makan", level="plain"))          # failed plain
    payloads.append(await call(word="makan", level="explain"))        # traced
    payloads.append(
        await call(word="makan", level="restricted", morphs=[{"msa_hvo": 5001}])
    )

    worker = HeldWorker()
    runner = make_runner(worker, grace_window=0.05)
    payloads.append(await call(word="makan", level="plain"))          # overflow
    running = await runner.start_run(
        project_name="P", wordforms=["a", "b"], level="batch", priority=Priority.LOW,
        scope_fingerprint=_BATCH_FINGERPRINT, engine_at_submission="HC",
        vernacular_ws="id",
    )
    payloads.append(await _status(running.run_id))                   # running
    running.stage = RunStage.LOADING_GRAMMAR
    running.stage_entered_at = time.monotonic() - 60
    payloads.append(await _status(running.run_id))                   # stuck loading
    running.stage = RunStage.PARSING
    await runner.cancel_run(running.run_id)
    worker.release.set()
    await asyncio.wait_for(running.done.wait(), timeout=10)
    payloads.append(await _status(running.run_id))                   # cancelled

    runner = make_runner(RecordingWorker())
    batch = await runner.start_run(
        project_name="P", wordforms=["a", "b"], level="batch", priority=Priority.LOW,
        scope_fingerprint=_BATCH_FINGERPRINT, engine_at_submission="HC",
        vernacular_ws="id",
    )
    payloads.append(await _status(batch.run_id))                     # completed batch

    runner = make_runner(RecordingWorker(fail_with=WorkerError("out of memory")))
    payloads.append(await call(word="makan", level="plain"))          # failed word
    payloads.append(await _status(next(iter(runner.known_run_ids()))))  # failed poll

    payloads.append(await _terminated_measurement(tmp_path))       # bound blown
    return payloads


async def _terminated_measurement(tmp_path):
    """A real measurement, killed at its bound, through the handler."""
    from test_parse_measure import RolePool

    runner = ParseRunner(
        pool=RolePool(shared_delay=0.0, measurement_delay=60.0),
        record_dir=tmp_path / "measured", grace_window=0.5,
    )
    parse_handler.set_runner(runner)
    try:
        return await call(word="pukul", level="plain", bound_seconds=1.0)
    finally:
        await runner.aclose()
        parse_handler.set_runner(None)


def _args_problem(rung):
    """Why this rung's args are not directly usable, or None."""
    tool = TOOLS.get(rung["tool"])
    if tool is None:
        return "names a tool that does not exist"
    model = getattr(tool, "input_model", None)
    if model is None:
        return None
    try:
        model(**(rung["args"] or {}))
    except Exception as exc:  # noqa: BLE001
        return f"args do not validate as given: {exc}"
    return None


async def test_every_proposal_names_a_real_tool_with_a_cost_and_usable_args(
    make_runner, tmp_path
):
    payloads = await _every_response(make_runner, tmp_path)
    rungs = [rung for payload in payloads for rung in _rungs(payload)]
    assert len(rungs) >= 12, "the sweep did not reach the responses it claims to"

    nonexistent = [r["tool"] for r in rungs if r["tool"] not in TOOLS]
    assert nonexistent == [], f"{len(nonexistent)} proposals name no real tool: {nonexistent}"

    uncosted = [r for r in rungs if not (isinstance(r.get("est_cost"), str) and r["est_cost"])]
    assert uncosted == [], f"{len(uncosted)} proposals carry no cost estimate: {uncosted}"

    unusable = [(r["tool"], _args_problem(r)) for r in rungs if _args_problem(r)]
    assert unusable == [], f"proposals the caller would have to reconstruct: {unusable}"


async def test_no_proposal_names_a_filing_step(make_runner, tmp_path):
    """Unreachable at CP3 in every session: every session is read-only."""
    payloads = await _every_response(make_runner, tmp_path)
    for rung in (r for p in payloads for r in _rungs(p)):
        text = json.dumps(
            {"tool": rung["tool"], "action": rung["action"], "args": rung["args"]}
        ).lower()
        for banned in ("filing", "file_", "write_enabled", "modify"):
            assert banned not in text, f"a proposal reaches for a filing step: {rung}"


async def test_the_measurement_proposed_on_a_failure_is_never_a_retry(make_runner):
    """FR-034 still holds: a failed run is never told to run the word again."""
    make_runner(RecordingWorker(fail_with=WorkerError("out of memory")))
    payload = await call(word="makan", level="plain")
    assert "flextools_try_word" not in [r["tool"] for r in _rungs(payload)]


# ---------------------------------------------------------------------------
# T105 -- FR-057: the static scan before the trace
# ---------------------------------------------------------------------------


async def test_the_static_scan_is_proposed_before_the_trace(make_runner, tmp_path):
    payload = await _terminated_measurement(tmp_path)

    tools = [(r["tool"], (r["args"] or {}).get("level")) for r in _rungs(payload)]
    assert (_SCAN, None) in tools, tools
    traces = [
        i for i, (tool, level) in enumerate(tools)
        if tool == "flextools_try_word" and level in ("explain", "restricted")
    ]
    assert traces, f"no trace was a candidate, so the order was not tested: {tools}"
    assert tools.index((_SCAN, None)) < min(traces), (
        f"the trace is proposed before the cheaper static scan: {tools}"
    )
    trace = _rungs(payload)[min(traces)]
    assert trace["est_cost"] == "unbounded", (
        "a trace on a grammar that just failed to finish one word is unbounded"
    )


async def test_on_a_failure_the_scan_comes_first(make_runner):
    make_runner(RecordingWorker(fail_with=WorkerError("out of memory")))
    payload = await call(word="makan", level="plain")
    assert _rungs(payload)[0]["tool"] == _SCAN


async def test_a_measurement_inside_its_bound_proposes_nothing(make_runner, tmp_path):
    """The known-fast grammar: a measurement that finished routes nowhere."""
    from test_parse_measure import RolePool

    runner = ParseRunner(
        pool=RolePool(shared_delay=0.0, measurement_delay=0.0),
        record_dir=tmp_path / "fast", grace_window=30.0,
    )
    parse_handler.set_runner(runner)
    try:
        payload = await call(word="pukul", level="plain", bound_seconds=30)
    finally:
        await runner.aclose()
        parse_handler.set_runner(None)
    assert payload["measurement"]["outcome"] == "completed"
    assert payload["next_step"] is None
