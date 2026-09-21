#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`flextools_try_word` -- the three levels, the gate, and what plain may not say
(parser-check CP2b; FR-012 .. FR-016; contracts/tools.md).

FIVE REQUIREMENTS, AND THE SHAPE EACH ONE FAILS IN:

  FR-012  three levels, three calls. The failure shape is a level that
          *looks* right and reaches the wrong call -- a `restricted` request
          that quietly traces unrestricted answers the wrong question while
          returning a perfectly well-formed result. So this is asserted at
          both layers: the handler passes the level through untouched, and
          the worker backend binds it to the right facade member.

          It is also asserted POSITIONALLY. The shipped implementation names
          the first parameter `word`; flexicon's own offline double for the
          same facade names it `form`. Keyword binding therefore works
          against exactly one of them and raises `TypeError` against the
          other, so the double below accepts the argument under BOTH names
          and records which form was used -- a keyword binding fails here
          even though it would pass against either single implementation.

  FR-013  plain never explains. The failure shape is enrichment: someone
          adds the analysis list "because we have it", and a level whose
          whole contract is "I do not know why" starts implying it does.
          Asserted as an absence -- no reason-bearing key may appear on a
          plain response at all.

  FR-014  the guidance defaults. The failure shape is an ordering: offering
          `explain` first makes the expensive level read as the default
          answer to "why did this fail", which is how this feature will feel
          slow in practice.

  FR-015  the engine gate is first. Asserted as ZERO RECORDED CALLS INTO THE
          PARSER AREA for an XAmple project -- a positive assertion that the
          refusal happened would also pass if the refusal happened *after* a
          parser was constructed, which is the case the requirement is about.
          `ActiveParser` is also flipped between two calls on one project, so
          a memoized verdict fails.

  FR-016  a missing HC recording agent does NOT mark reading unavailable.
          Reading neither records nor needs an agent. CP1 shipped the agent
          probe with tests and no caller; this is the first caller, and the
          boundary it must not blur.

Everything here runs in-process against doubles. No project is opened, no
grammar is loaded and no child process is spawned -- the real channel is
exercised in `tests/test_parse_worker_lifetime.py`, and a live parser in
`tests/test_parse_live.py`.

Run with:
    python -m pytest tests/test_try_word_handler.py -q
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.resolver import (  # noqa: E402
    LexiconIndex,
    resolve_spec,
)
from flextoolsmcp.server.parse.worker_client import WorkerError  # noqa: E402
from flextoolsmcp.server.parser_probe import (  # noqa: E402
    ParserEngineMismatchError,
    check_active_parser,
)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

#: The stub lexicon the worker's own `--stub` backend serves, reproduced so
#: the handler tests resolve against the same facts the worker would.
#:
#:   pukul   resolves            kirim   ambiguous (two entries)
#:   kosong  no_msa              makan   resolves, two analyses
STUB_ROWS = [
    {"headword": "pukul", "entry_hvo": 101, "senses": ["hit"], "msa_hvos": [5001]},
    {"headword": "kirim", "entry_hvo": 102, "senses": ["send"], "msa_hvos": [5002]},
    {"headword": "kirim", "entry_hvo": 103, "senses": ["deliver"], "msa_hvos": [5003]},
    {"headword": "kosong", "entry_hvo": 104, "senses": ["empty"], "msa_hvos": []},
    {"headword": "makan", "entry_hvo": 105, "senses": ["eat"], "msa_hvos": [5004]},
]


class _RawSpec:
    """A morph payload dict, given the four attributes the resolver reads."""

    def __init__(self, raw):
        self.headword = raw.get("headword")
        self.sense = raw.get("sense")
        self.msa_hvo = raw.get("msa_hvo")
        self.position = raw.get("position")



class RecordingWorker:
    """Answers `parse_word` and records every keyword argument verbatim.

    Verbatim is the point: the level assertions read these dicts, so a
    handler that rewrote, defaulted or normalised a level on its way down
    would show up here as the wrong recorded value rather than as a subtly
    wrong result nobody inspects.
    """

    def __init__(
        self,
        *,
        fail_with=None,
        resolutions=None,
        index_ready=True,
        trace_outcome="failure",
        trace_analysis_count=1,
    ) -> None:
        self.calls: list[dict] = []
        self.fail_with = fail_with
        #: Resolve requests, recorded separately from parses. The separation
        #: is what lets FR-019's negative be asserted precisely: an
        #: unresolvable piece must produce a resolve call and ZERO parse
        #: calls, and one combined list could not tell those apart.
        self.resolve_calls: list[dict] = []
        #: Optional canned outcomes, keyed by position, for the refusal
        #: cases. `None` means the real resolver decides.
        self.resolutions = resolutions
        #: Whether this worker's lexicon index is already built. False is
        #: the cold-start case the proposal assist must decline to warm.
        self.index_ready = index_ready
        #: What `explain`/`restricted` should report, mirroring the real
        #: worker's three-way outcome (worker_main.py `_summarize_trace` /
        #: `BackendFacade.parse()`): "failure" (no <Analysis>, no <Error>),
        #: "success" (one or more <Analysis>), or "error" (<Error> present,
        #: so the response carries `parse_error` and neither `parsed` nor
        #: `hypothesis_held`). Defaults to "failure" -- the shape most of
        #: this file's tests are actually about -- so tests that need
        #: `success`/`error` say so explicitly, either at construction or
        #: by setting `worker.trace_outcome` before the call.
        self.trace_outcome = trace_outcome
        self.trace_analysis_count = trace_analysis_count

    def listen_to_run(self, run_id, listener):
        pass

    def stop_listening(self, run_id):
        pass

    def is_running(self):
        return True

    async def parse_word(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_with is not None:
            raise self.fail_with

        word = kwargs["wordform"]
        level = kwargs.get("level")
        if level == "plain":
            return {
                "parse": {"parsed": False, "analysis_count": 0},
                "trace_xml": None,
            }

        trace_xml = f"<trace word='{word}' level='{level}'/>"
        if self.trace_outcome == "error":
            parse = {"parse_error": f"the parser threw while tracing {word!r}"}
        elif self.trace_outcome == "success":
            if level == "restricted":
                parse = {
                    "hypothesis_held": True,
                    "restricted_analysis_count": self.trace_analysis_count,
                }
            else:
                parse = {
                    "parsed": True,
                    "analysis_count": self.trace_analysis_count,
                }
        else:
            if level == "restricted":
                parse = {"hypothesis_held": False, "restricted_analysis_count": 0}
            else:
                parse = {"parsed": False, "analysis_count": 0}
        return {"parse": parse, "trace_xml": trace_xml}

    async def resolve_morphs(
        self, *, request_id, run_id, morphs, only_if_indexed=False, timeout=120.0
    ):
        """Stand in for the worker's lexicon lookup, over a stub lexicon.

        Runs the REAL resolver over `STUB_ROWS` rather than reimplementing
        its decisions. Two doubles of the same logic drift, and the one in
        the test file always drifts toward whatever makes the test pass --
        so the only thing doubled here is the CHANNEL and the lexicon
        behind it.

        `canned` outcomes still override, for the refusal cases: those need
        an outcome the stub lexicon may not naturally produce for the word
        the test is using, and forcing it is clearer than bending the
        lexicon around each one.

        `only_if_indexed` is honoured the way the worker honours it -- this
        double is always "warm", so it answers -- and `index_ready` is
        reported so the handler's cold-index path has something to read.
        """
        self.resolve_calls.append(
            {"morphs": morphs, "run_id": run_id, "only_if_indexed": only_if_indexed}
        )
        if self.index_ready is False:
            return {"resolutions": [], "index_ready": False, "index_entries": 0}

        index = LexiconIndex(STUB_ROWS)
        rows = []
        for position, morph in enumerate(morphs):
            canned = (self.resolutions or {}).get(position)
            if canned is not None:
                rows.append(dict(canned, position=morph.get("position", position)))
                continue
            resolution = resolve_spec(_RawSpec(morph), index)
            rows.append(
                {
                    "position": morph.get("position", position),
                    "outcome": resolution.outcome,
                    "msa_hvos": list(resolution.msa_hvos),
                    "candidates": [c.to_dict() for c in resolution.candidates],
                    "morph": morph.get("headword") or morph.get("msa_hvo"),
                }
            )
        return {
            "resolutions": rows,
            "index_ready": True,
            "index_entries": len(index),
        }

    async def cancel_run(self, run_id):
        pass


class Pool:
    def __init__(self, worker):
        self.worker = worker

    async def get(self, project_name):
        return self.worker

    def peek(self, project_name):
        return self.worker

    async def aclose(self):
        pass


@pytest.fixture
def worker():
    return RecordingWorker()


@pytest.fixture
def wired(worker, tmp_path, monkeypatch):
    """The handler, wired to a recording worker and a throwaway record dir.

    Also neutralises project resolution: this file is about the parse path,
    and a real `resolve_or_explain` would refuse every name on a machine
    with no FieldWorks projects installed, turning every assertion below
    into the same `project_not_found`.
    """
    monkeypatch.setattr(
        parse_handler,
        "_resolve_project",
        lambda name: (name or "Test Project", None),
    )
    runner = ParseRunner(
        pool=Pool(worker), record_dir=tmp_path / "runs", grace_window=30.0
    )
    parse_handler.set_runner(runner)
    try:
        yield worker
    finally:
        parse_handler.set_runner(None)


async def call(**kwargs):
    """Invoke the handler and return its decoded payload."""
    args = {"project_name": "Test Project"}
    args.update(kwargs)
    response = await parse_handler.handle_flextools_try_word(args)
    return json.loads(response[0].text)


# ---------------------------------------------------------------------------
# FR-012 -- three levels reach three calls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["plain", "explain"])
async def test_the_level_reaches_the_worker_untouched(wired, level):
    """The level the caller asked for is the level the worker is given."""
    await call(word="makan", level=level)

    assert len(wired.calls) == 1, "one word is one call"
    assert wired.calls[0]["level"] == level
    assert wired.calls[0]["wordform"] == "makan"


async def test_restricted_reaches_the_worker_with_its_selection(wired):
    """`restricted` carries the resolved selection, and never an empty one."""
    payload = await call(
        word="makan",
        level="restricted",
        morphs=[{"msa_hvo": 5001}, {"msa_hvo": 5002}],
    )

    assert wired.calls[0]["level"] == "restricted"
    assert list(wired.calls[0]["restricted_to"]) == [5001, 5002], (
        "the selection reaches the worker intact; ParseWorkerClient is what "
        "turns it into a JSON list on the wire"
    )
    assert payload["restricted_to"] == [5001, 5002], (
        "the response echoes what was traced, so a caller can see it was "
        "their decomposition and not a widened one"
    )


async def test_plain_and_explain_send_no_restriction_rather_than_an_empty_one(
    wired,
):
    """`None` and `[]` are DIFFERENT instructions to the parser.

    `None` means "no restriction"; an empty sequence means "admit nothing".
    Normalising one into the other is the widening spec.md Delta 2 forbids,
    and because the setting outlives the call it would corrupt the next
    parse too -- so the distinction is asserted on the wire, not inferred
    from the result.
    """
    await call(word="makan", level="plain")
    await call(word="makan", level="explain")

    for recorded in wired.calls:
        assert recorded["restricted_to"] is None


async def test_duplicate_identifiers_are_collapsed_not_repeated(wired):
    """Two pieces resolving to one analysis is ordinary; sending it twice is not."""
    await call(
        word="makanan",
        level="restricted",
        morphs=[{"msa_hvo": 5001}, {"msa_hvo": 5001}, {"msa_hvo": 5002}],
    )

    assert list(wired.calls[0]["restricted_to"]) == [5001, 5002]


# The positional-binding half of FR-012: the worker backend's own mapping.


class FacadeDouble:
    """Stands in for `project.Parser`, recording HOW it was called.

    Deliberately `*args, **kwargs` rather than a named signature. The
    shipped implementation calls the first parameter `word`; flexicon's own
    offline double for the same facade calls it `form`. A named signature
    here would silently agree with whichever of the two it copied, so this
    records the binding form instead: anything bound by keyword lands in
    `kwargs` and the assertions below fail, whichever name was used.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def ParseWord(self, *args, **kwargs):
        self.calls.append(("ParseWord", args, kwargs))
        return _Analyses(0)

    def TraceWordXml(self, *args, **kwargs):
        self.calls.append(("TraceWordXml", args, kwargs))
        return "<trace/>"


class _Analyses:
    def __init__(self, count):
        self.Analyses = [object()] * count


def _backend_with(facade):
    from flextoolsmcp.server.parse.worker_main import _RealBackend

    backend = _RealBackend("Test Project")
    backend._project = type("P", (), {"Parser": facade})()
    return backend


def test_each_level_binds_to_its_own_facade_member_positionally():
    """restricted -> TraceWordXml(word, analyses); plain -> ParseWord(word);
    explain -> TraceWordXml(word, None)."""
    facade = FacadeDouble()
    backend = _backend_with(facade)

    backend.parse("makan", "plain", None)
    backend.parse("makan", "explain", None)
    backend.parse("makan", "restricted", (101, 202))

    assert [c[0] for c in facade.calls] == [
        "ParseWord",
        "TraceWordXml",
        "TraceWordXml",
    ]

    # EVERY argument positional, nothing bound by name. A keyword binding to
    # either `word=` or `form=` puts the wordform in `kwargs` and fails here,
    # which is the whole point of the double being name-agnostic.
    for name, args, kwargs in facade.calls:
        assert kwargs == {}, f"{name} bound an argument by name: {kwargs}"
        assert args[0] == "makan", f"{name} did not take the wordform first: {args}"

    assert facade.calls[0][1] == ("makan",), "plain passes the word and nothing else"
    assert facade.calls[1][1] == ("makan", None), "explain traces with no restriction"
    assert facade.calls[2][1] == ("makan", [101, 202]), (
        "restricted traces exactly the selection, as the second positional"
    )


def test_an_empty_restriction_never_reaches_the_facade():
    """Defence in depth: the parser is never asked to admit nothing."""
    facade = FacadeDouble()
    backend = _backend_with(facade)

    with pytest.raises(ValueError):
        backend.parse("makan", "restricted", ())

    assert facade.calls == [], "no facade call may be made on the refused path"


# ---------------------------------------------------------------------------
# FR-013 -- the plain level never explains
# ---------------------------------------------------------------------------

#: Every key that would amount to a reason. Asserted as an ABSENCE, because
#: the failure mode is additive: a later edit enriches the plain response
#: "since we already have it", and the level starts implying it knows why.
_REASON_BEARING_KEYS = frozenset(
    {
        "trace",
        "trace_path",
        "trace_xml",
        "trace_available",
        "reason",
        "why",
        "explanation",
        "analyses",
        "failure_reason",
        "diagnosis",
    }
)


async def test_a_failed_plain_parse_reports_only_that_it_failed(wired):
    payload = await call(word="makan", level="plain")

    assert payload["parsed"] is False
    assert payload["analysis_count"] == 0
    assert payload["explains_failure"] is False

    leaked = _REASON_BEARING_KEYS & set(payload)
    assert not leaked, f"the plain level must carry no reason; found {sorted(leaked)}"


async def test_a_failed_plain_parse_points_at_the_explaining_levels(wired):
    payload = await call(word="makan", level="plain")

    offered = [
        rung["args"].get("level")
        for rung in payload["next_step"]
        if rung["tool"] == "flextools_try_word"
    ]
    assert offered == ["restricted", "explain"], (
        "both explaining levels are offered, restricted first (FR-014)"
    )


async def test_a_successful_plain_parse_offers_nothing(wired, worker):
    """Nothing to diagnose, so no rungs.

    Offering the expensive level after a successful parse would train
    callers to skim the guidance field -- the same reason FR-025 forbids
    congratulating a correct hypothesis.
    """

    async def parsed(**kwargs):
        worker.calls.append(kwargs)
        return {"parse": {"parsed": True, "analysis_count": 3}, "trace_xml": None}

    worker.parse_word = parsed
    payload = await call(word="makan", level="plain")

    assert payload["parsed"] is True
    assert payload["analysis_count"] == 3
    assert payload["next_step"] is None
    assert payload["explains_failure"] is False


async def test_the_explaining_levels_say_they_explain_on_failure(wired):
    """NARROWED (CP2b): this used to assert `explains_failure is True` for
    both levels with no success/failure distinction at all -- which passed
    even though `explain`'s success gate did not exist yet, because
    `parsed` was never set for `explain` and the branch always fell through
    to failure guidance. The default `RecordingWorker` now genuinely
    represents the failure case (no <Analysis>, no <Error>), so this test
    is about that case specifically; the success case gets its own test
    below.
    """
    for level, morphs in (("explain", None), ("restricted", [{"msa_hvo": 5001}])):
        kwargs = {"word": "makan", "level": level}
        if morphs is not None:
            kwargs["morphs"] = morphs
        payload = await call(**kwargs)
        assert payload["explains_failure"] is True, level
        assert payload["trace_available"] is True, level


async def test_explain_on_a_successful_parse_offers_nothing(wired, worker):
    """FR-025, at explain: agreement gets no commentary either.

    Before this fix `parsed` was never set for `explain`, so this branch
    was unreachable and every explain response -- including a successful
    one -- got failure-flavoured guidance and a decomposition proposal.
    """
    worker.trace_outcome = "success"
    worker.trace_analysis_count = 2

    payload = await call(word="makan", level="explain")

    assert payload["parsed"] is True
    assert payload["analysis_count"] == 2
    assert payload["explains_failure"] is False
    assert payload["next_step"] is None
    assert "guidance" not in payload
    assert "proposed_decomposition" not in payload


async def test_explain_on_a_parser_error_names_neither_outcome(wired, worker):
    """The <Error> case is BLOCKING, not a silent `parsed: False`.

    A thrown parse is not the same fact as a word that genuinely did not
    parse; asserting `parsed: False` for it would be a false definite
    negative, worse than reporting nothing.
    """
    worker.trace_outcome = "error"

    payload = await call(word="makan", level="explain")

    assert payload["parse_error"]
    assert "parsed" not in payload
    assert "analysis_count" not in payload
    assert "proposed_decomposition" not in payload
    assert "explains_failure" not in payload


async def test_restricted_on_a_parser_error_names_neither_outcome(wired, worker):
    worker.trace_outcome = "error"

    payload = await call(
        word="makan", level="restricted", morphs=[{"msa_hvo": 5001}]
    )

    assert payload["parse_error"]
    assert "hypothesis_held" not in payload
    assert "restricted_analysis_count" not in payload
    assert "parsed" not in payload
    assert "proposed_decomposition" not in payload
    assert "explains_failure" not in payload, (
        "the trace threw; this response explains nothing about the "
        "hypothesis either way, the same as explain's parse_error case"
    )
    assert payload["next_step"] is None


async def test_restricted_never_carries_parsed_even_on_a_held_hypothesis(
    wired, worker
):
    """The contract from cycle 1: restricted answers a different question,
    and must never be spelled with `plain`'s vocabulary -- asserted as an
    absence, because the failure mode is a key that quietly reappears.
    """
    worker.trace_outcome = "success"
    worker.trace_analysis_count = 4

    payload = await call(
        word="makan", level="restricted", morphs=[{"msa_hvo": 5001}]
    )

    assert payload["hypothesis_held"] is True
    assert payload["restricted_analysis_count"] == 4
    assert "parsed" not in payload
    assert "analysis_count" not in payload


async def test_restricted_on_a_held_hypothesis_offers_no_commentary(wired, worker):
    """FR-025/contracts/tools.md:97, at restricted: a held hypothesis is
    agreement, and agreement gets no commentary -- the same success gate
    `explain` already had, applied to the sibling branch five lines away
    (`_level_guidance`'s restricted case previously hardcoded
    `explains_failure: True` regardless of outcome).
    """
    worker.trace_outcome = "success"
    worker.trace_analysis_count = 1

    payload = await call(
        word="makan", level="restricted", morphs=[{"msa_hvo": 5001}]
    )

    assert payload["hypothesis_held"] is True
    assert payload["explains_failure"] is False
    assert payload["next_step"] is None


async def test_a_trace_is_reported_by_path_never_inlined(wired):
    """A trace runs to tens or hundreds of KB; the response carries a path."""
    payload = await call(word="makan", level="explain")

    assert "trace_xml" not in payload
    assert payload["trace_path"].endswith(".xml")
    assert Path(payload["trace_path"]).exists()
    assert payload["trace_bytes"] > 0


# ---------------------------------------------------------------------------
# FR-014 -- the guidance defaults
# ---------------------------------------------------------------------------


async def test_restricted_is_offered_before_explain(wired):
    """Order matters: the cheap level with a hypothesis, then the expensive one.

    Offering `explain` first would make the expensive level read as the
    default answer to "why did this fail", which is how this feature will
    feel slow in practice (FR-014).
    """
    payload = await call(word="makan", level="plain")
    levels = [
        (index, rung)
        for index, rung in enumerate(payload["next_step"])
        if rung["tool"] == "flextools_try_word"
    ]
    (first_index, first), (second_index, second) = levels

    assert first["args"]["level"] == "restricted"
    assert "hypothesis" in first["rationale"].lower()
    assert second["args"]["level"] == "explain"
    assert "slowest" in second["est_cost"] or "slowest" in second["rationale"]
    assert first_index < second_index


async def test_the_restricted_rung_shows_how_morphs_are_written(wired):
    """Headwords, not surface strings -- an example beats "see the docs"."""
    payload = await call(word="makan", level="plain")
    example = payload["next_step"][0]["args"]["morphs"]

    assert example, "the rung offers a worked shape"
    assert all("headword" in piece for piece in example)
    assert not any("form" in piece for piece in example), (
        "there is no free-text form field; offering one would promise a "
        "segmentation this tool cannot perform"
    )


async def test_explain_steers_back_toward_restricted(wired):
    """NARROWED (CP2b): the default worker is the FAILURE case, and this
    guidance is now gated on that (a successful explain drops the rungs
    entirely -- see `test_explain_on_a_successful_parse_offers_nothing`).
    """
    payload = await call(word="makan", level="explain")

    assert payload["explains_failure"] is True, "this is the failure case"
    assert payload["next_step"][0]["args"]["level"] == "restricted"


async def test_restricted_steers_nowhere(wired):
    """The caller already used the right level. There is nothing to say."""
    payload = await call(word="makan", level="restricted", morphs=[{"msa_hvo": 5001}])

    assert payload["next_step"] is None


# ---------------------------------------------------------------------------
# FR-015 -- the engine gate is first, and is re-read live
# ---------------------------------------------------------------------------


class ProjectDouble:
    """A project that records every touch of its parser area.

    `Parser` is a property rather than an attribute so that *reading* it
    counts as a call. The requirement is about what happens before the
    refusal, and constructing a parser begins with reaching for one.
    """

    def __init__(self, active_parser: str) -> None:
        self.lp = self
        self.active_parser = active_parser
        self.parser_area_calls: list[str] = []

    @property
    def MorphologicalDataOA(self):
        return self

    @property
    def ActiveParser(self):
        # Read live off the current value every time, exactly as LCM does.
        return self.active_parser

    @property
    def Parser(self):
        self.parser_area_calls.append("Parser")
        raise AssertionError(
            "the parser area was reached on a project the gate should have "
            "refused"
        )


def test_an_xample_project_is_refused_with_zero_parser_area_calls():
    """The negative assertion. A positive one would pass too late.

    Asserting only that `parser_engine_mismatch` was raised would also pass
    if a parser had been constructed first and the refusal issued after --
    which is the case FR-015 exists to forbid.
    """
    project = ProjectDouble("XAmple")

    with pytest.raises(ParserEngineMismatchError) as caught:
        check_active_parser(project, supported_engines=("HC",))

    assert project.parser_area_calls == [], (
        "a project configured for an unsupported engine must be refused "
        "before anything in the parser area is touched"
    )
    detail = caught.value.detail
    assert detail["error_code"] == "parser_engine_mismatch"
    assert detail["configured_engine"] == "XAmple"
    assert detail["supported_engines"] == ["HC"]
    assert detail["hint"]


def test_active_parser_is_re_read_live_and_never_memoized():
    """A user can flip the engine mid-session, so a cached verdict is stale.

    Both directions are exercised on ONE project object: a memo keyed on
    the project would pass a test that only flipped one way.
    """
    project = ProjectDouble("HC")

    assert check_active_parser(project, supported_engines=("HC",)) is None

    project.active_parser = "XAmple"
    with pytest.raises(ParserEngineMismatchError):
        check_active_parser(project, supported_engines=("HC",))

    project.active_parser = "HC"
    assert check_active_parser(project, supported_engines=("HC",)) is None


def test_the_gate_is_the_first_statement_of_the_workers_request_handler():
    """Structural: `preflight` is the first statement of the per-word path.

    Read off the source rather than inferred from behaviour, because the
    behavioural version passes for a gate that runs first *today* and would
    keep passing if a later edit moved a cheap lookup above it.
    """
    import inspect

    from flextoolsmcp.server.parse import worker_main

    # `_before_parse`, not `handle_message`: the latter runs on the reader
    # thread and only pushes onto the queue. The per-request work -- and so
    # the gate -- happens on the main loop, one word at a time, which is
    # also why the gate still runs when a held grammar is reused.
    source = inspect.getsource(worker_main.ParseWorker._before_parse)
    body = [line.strip() for line in source.splitlines() if line.strip()]
    statements = [
        line
        for line in body
        if not line.startswith(("#", '"""', "'''", "def ", "@"))
    ]
    joined = "\n".join(statements)
    preflight_at = joined.find("preflight()")
    assert preflight_at != -1, "the request handler must run the gate"
    for later in ("parse(", "ensure_grammar(", "GetAvailability("):
        found = joined.find(later)
        assert found == -1 or found > preflight_at, (
            f"{later} appears before the engine gate in _before_parse"
        )


async def test_an_engine_mismatch_reaches_the_caller_as_its_own_refusal(
    worker, tmp_path, monkeypatch
):
    """The worker's detail is re-emitted UNCHANGED, not flattened.

    `parser_engine_mismatch`'s field set is pinned by the parent spec, so a
    handler that rebuilt the payload is where the names would drift.
    """
    mismatch = WorkerError("This project's active parser is 'XAmple'.")
    mismatch.error_code = "parser_engine_mismatch"
    mismatch.detail = {
        "error_code": "parser_engine_mismatch",
        "configured_engine": "XAmple",
        "supported_engines": ["HC"],
        "hint": "Switch the active parser in FieldWorks.",
    }

    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    refusing = RecordingWorker(fail_with=mismatch)
    parse_handler.set_runner(
        ParseRunner(pool=Pool(refusing), record_dir=tmp_path / "runs", grace_window=30.0)
    )
    try:
        payload = await call(word="makan", level="plain")
    finally:
        parse_handler.set_runner(None)

    assert payload["status"] == "error"
    assert payload["error_code"] == "parser_engine_mismatch"
    assert payload["configured_engine"] == "XAmple"
    assert payload["supported_engines"] == ["HC"]
    assert payload["hint"]


async def test_an_unavailable_parser_refuses_as_parser_core_missing(
    tmp_path, monkeypatch
):
    """`GetAvailability()` reports unavailable; its reason is carried through.

    Not `runtime_error`: the contract's refusal table names this code, and
    the reason the facade gave is the only actionable thing in the response.
    """
    unavailable = WorkerError("The parser is not available.")
    unavailable.error_code = "parser_core_missing"
    unavailable.detail = {
        "error_code": "parser_core_missing",
        "signal": "load_failed",
        "expected_path": "",
        "detected_version": None,
        "missing_members": [],
        "lcmodel_install_path": None,
        "install_hint": "Run flextools_health.",
        "load_error": "hc tool not found on PATH",
    }

    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    parse_handler.set_runner(
        ParseRunner(
            pool=Pool(RecordingWorker(fail_with=unavailable)),
            record_dir=tmp_path / "runs",
            grace_window=30.0,
        )
    )
    try:
        payload = await call(word="makan", level="plain")
    finally:
        parse_handler.set_runner(None)

    assert payload["error_code"] == "parser_core_missing"
    assert payload["load_error"] == "hc tool not found on PATH", (
        "the facade's reason is carried through, not summarised away"
    )


def test_the_worker_shapes_an_unavailable_parser_as_a_refusal():
    """The other half: the worker actually raises a detail-carrying error.

    The handler test above proves the refusal is re-emitted; this proves
    one is produced. Split because a payload built only in a test double
    would let the production path keep raising a bare RuntimeError.
    """
    from flextoolsmcp.server.parse.worker_main import ParserUnavailableError

    class Unavailable:
        available = False
        reason = "hc tool not found on PATH"
        version = "1.2.3"

        def GetAvailability(self):
            return self

    backend = _backend_with(Unavailable())

    with pytest.raises(ParserUnavailableError) as caught:
        backend.ensure_grammar("run-1")

    detail = caught.value.detail
    assert detail["error_code"] == "parser_core_missing"
    assert detail["load_error"] == "hc tool not found on PATH"
    assert detail["signal"] == "load_failed"

    # `extra="forbid"`, so a stray key is a validation failure at the far
    # end rather than a tolerated extra. Validated here, where the payload
    # is built.
    from flextoolsmcp.server.response_models import ParserCoreMissingDetail

    ParserCoreMissingDetail.model_validate(detail)


# ---------------------------------------------------------------------------
# FR-016 -- a missing recording agent does not mark reading unavailable
# ---------------------------------------------------------------------------


async def test_a_missing_recording_agent_does_not_block_reading(wired, monkeypatch):
    """Reading neither records nor needs an agent.

    The agent probe is CP1 machinery for the *write* spine. Wiring it into
    this path -- even as a precaution -- would make every read on a project
    with no HermitCrab agent refuse, which is the boundary FR-016 draws.
    """
    from flextoolsmcp.server import parser_probe

    def exploded(*args, **kwargs):
        raise AssertionError(
            "the read path resolved a recording agent; FR-016 says it must not"
        )

    monkeypatch.setattr(parser_probe, "probe_hc_agent", exploded)

    payload = await call(word="makan", level="plain")

    assert payload["status"] == "ok"
    assert payload["parsed"] is False


def test_no_parse_module_reaches_the_agent_probe():
    """Structural companion to the behavioural test above.

    The behavioural test only covers the path it happens to walk; this one
    fails if any module under `server/parse/` or the parse handler so much
    as names the agent probe.
    """
    roots = [
        REPO_ROOT / "src" / "flextoolsmcp" / "server" / "parse",
        REPO_ROOT / "src" / "flextoolsmcp" / "server" / "handlers" / "parse.py",
    ]
    offenders = []
    for root in roots:
        files = sorted(root.rglob("*.py")) if root.is_dir() else [root]
        for path in files:
            text = path.read_text(encoding="utf-8")
            # Skip the prose: the docstrings explain WHY the probe is absent,
            # and a naive substring search would flag the explanation itself.
            code = "\n".join(
                line for line in text.splitlines() if not line.strip().startswith("#")
            )
            for marker in ("probe_hc_agent", "DefaultParserAgent"):
                if marker in code and f'"{marker}' not in code:
                    offenders.append(f"{path.name}: {marker}")
    assert offenders == [], (
        "the read spine must not resolve a recording agent (FR-016): "
        + ", ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Input discipline -- `morphs` is never silently ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["plain", "explain"])
def test_morphs_on_a_non_restricted_level_is_a_usage_error(level):
    """Refused, not dropped.

    Accepting and ignoring it would return an UNRESTRICTED answer that looks
    like a restricted one, and the caller would read a full-search result as
    confirmation of their decomposition.
    """
    from pydantic import ValidationError

    from flextoolsmcp.server.models import TryWordInput

    with pytest.raises(ValidationError):
        TryWordInput(word="makan", level=level, morphs=[{"headword": "makan"}])


def test_restricted_without_morphs_is_refused_rather_than_widened():
    from pydantic import ValidationError

    from flextoolsmcp.server.models import TryWordInput

    with pytest.raises(ValidationError):
        TryWordInput(word="makan", level="restricted")
    with pytest.raises(ValidationError):
        TryWordInput(word="makan", level="restricted", morphs=[])


# ---------------------------------------------------------------------------
# FR-019 / SC-005 -- an unresolvable piece refuses, and NOTHING is parsed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("outcome", ["none", "ambiguous", "no_msa"])
async def test_an_unresolvable_piece_refuses_with_zero_parses(
    worker, tmp_path, monkeypatch, outcome
):
    """The negative, asserted by recorded calls rather than inferred.

    A test that only checked for `parse_morph_unresolved` would pass against
    an implementation that parsed the word first and refused afterwards --
    which is precisely what SC-005's "0 parses are run" forbids. So the
    parse call list is asserted EMPTY.

    Parameterised over all three outcomes because the refusal must happen
    for each of them; an implementation that treated `ambiguous` as "pick
    the first" would pass the `none` case alone.
    """
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    refusing = RecordingWorker(
        resolutions={
            1: {
                "outcome": outcome,
                "msa_hvos": [],
                "candidates": [
                    {
                        "headword": "kirim",
                        "sense": None,
                        "msa_hvo": None if outcome == "no_msa" else 5002,
                        "entry_hvo": 102,
                    }
                ],
                "morph": "kirim",
            }
        }
    )
    parse_handler.set_runner(
        ParseRunner(pool=Pool(refusing), record_dir=tmp_path / "runs", grace_window=30.0)
    )
    try:
        payload = await call(
            word="mengirim",
            level="restricted",
            morphs=[{"msa_hvo": 5001}, {"headword": "kirim"}],
        )
    finally:
        parse_handler.set_runner(None)

    assert payload["status"] == "error"
    assert payload["error_code"] == "parse_morph_unresolved"
    assert payload["resolved_to"] == outcome
    assert payload["position"] == 1, "the refusal names WHICH piece failed"
    assert payload["morph"] == "kirim"
    assert payload["candidates"], (
        "a refusal with no candidates can only be retried, not acted on"
    )
    assert payload["hint"]

    assert refusing.resolve_calls, "resolution must have been attempted"
    assert refusing.calls == [], (
        "a parse ran despite an unresolvable piece; SC-005 requires 0 "
        f"(recorded: {refusing.calls})"
    )


async def test_the_three_outcomes_get_three_different_hints(
    worker, tmp_path, monkeypatch
):
    """Distinct outcomes, distinct advice.

    Collapsing the three into one refusal is the silent-narrowing failure
    the requirement exists to prevent: the caller cannot tell whether to fix
    a spelling, pick a homograph, or conclude the entry has no analysis. A
    shared hint would undo the distinction even with the enum intact, which
    is why the HINTS are compared and not just the codes.
    """
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )

    hints = {}
    for outcome in ("none", "ambiguous", "no_msa"):
        refusing = RecordingWorker(
            resolutions={
                0: {
                    "outcome": outcome,
                    "msa_hvos": [],
                    "candidates": [],
                    "morph": "kirim",
                }
            }
        )
        parse_handler.set_runner(
            ParseRunner(
                pool=Pool(refusing),
                record_dir=tmp_path / f"runs-{outcome}",
                grace_window=30.0,
            )
        )
        try:
            payload = await call(
                word="mengirim", level="restricted", morphs=[{"headword": "kirim"}]
            )
        finally:
            parse_handler.set_runner(None)
        hints[outcome] = payload["hint"]

    assert len(set(hints.values())) == 3, (
        "the three outcomes share a hint, so the caller cannot tell them "
        f"apart in practice: {hints}"
    )
    assert "spelling" in hints["none"].lower()
    assert "homograph" in hints["ambiguous"].lower() or "sense" in hints["ambiguous"].lower()
    assert "analysis" in hints["no_msa"].lower()


async def test_resolution_happens_before_the_parse_is_enqueued(wired):
    """Ordering, on the happy path: resolve first, then parse.

    The refusal tests above show that a failure stops the parse. This shows
    the ordering holds when nothing fails -- otherwise "resolution before
    execution" would be a property only of the error path.
    """
    await call(word="mengirim", level="restricted", morphs=[{"msa_hvo": 5001}])

    assert wired.resolve_calls, "no resolution was attempted"
    assert wired.calls, "no parse was run on the happy path"
    assert list(wired.calls[0]["restricted_to"]) == [5001]


# ---------------------------------------------------------------------------
# FR-022 / SC-011 -- guidance names only actions the caller can perform
# ---------------------------------------------------------------------------


async def test_the_look_it_up_rung_is_a_run_module_snippet_not_a_tool(wired):
    """There is no lexicon-query tool, so no rung may imply one.

    Every other tool on this server is API discovery, codegen or admin; the
    only path to lexicon data is `flextools_run_module` executing Python.
    A rung that named a lexicon tool would be naming something that does not
    exist -- the failure SC-011 counts, and the one CP1 shipped twice by
    pointing at `flextools_try_word` a checkpoint before it was built.
    """
    payload = await call(word="makan", level="plain")

    lookup = [
        rung for rung in payload["next_step"]
        if rung["tool"] == "flextools_run_module"
    ]
    assert lookup, (
        "no rung says how to find the headwords, so the decomposition is "
        "named as the missing input with no way to obtain one (FR-022)"
    )
    snippet = lookup[0]["args"]["code"]
    assert "GetHeadword" in snippet and "LexEntry" in snippet
    assert "report.Info" in snippet, "a snippet that prints nothing helps nobody"
    assert "segment" not in snippet.lower(), (
        "the snippet must not present itself as a segmentation; it is a "
        "string match over headwords"
    )


async def test_every_emitted_rung_names_a_tool_that_exists(wired):
    """The sweep, at this tool's own surface (SC-011).

    Run for each level so a rung reachable only from one of them cannot
    escape it.
    """
    from flextoolsmcp.server.dispatch import get_all_tool_names

    known = set(get_all_tool_names())

    for kwargs in (
        {"word": "makan", "level": "plain"},
        {"word": "makan", "level": "explain"},
        {"word": "makan", "level": "restricted", "morphs": [{"msa_hvo": 5001}]},
    ):
        payload = await call(**kwargs)
        for rung in payload.get("next_step") or []:
            assert rung["tool"] is None or rung["tool"] in known, (
                f"{kwargs['level']} emitted a rung naming {rung['tool']!r}, "
                f"which is not a registered tool"
            )


# ---------------------------------------------------------------------------
# FR-021 -- the proposal, offered only where it can be offered honestly
# ---------------------------------------------------------------------------


async def test_a_proposal_is_labelled_proposed_and_unverified(wired):
    """A lexicon string match is not a parse, and must not read like one."""
    payload = await call(word="pukul", level="plain")

    proposal = payload.get("proposed_decomposition")
    assert proposal is not None, (
        "the index is warm and the word is a headword, so a proposal was "
        "available and not offered"
    )
    assert proposal["status"] == "proposed, unverified"
    assert proposal["basis"] == "lexicon string match"
    assert "NOT a parse" in proposal["caveat"]
    assert proposal["morphs"] == [{"headword": "pukul", "position": 0}]


async def test_no_proposal_is_offered_when_the_word_parsed(wired, worker):
    """Nothing to propose, and silence on success.

    Offering a decomposition for a word that parsed would be commentary on
    a result the caller did not question -- the same reason FR-025 forbids
    remarking on a proposal that agrees with recorded analyses.
    """

    async def parsed(**kwargs):
        worker.calls.append(kwargs)
        return {"parse": {"parsed": True, "analysis_count": 1}, "trace_xml": None}

    worker.parse_word = parsed
    payload = await call(word="pukul", level="plain")

    assert payload["parsed"] is True
    assert "proposed_decomposition" not in payload


async def test_no_proposal_is_offered_when_the_caller_already_gave_one(wired):
    """At `restricted` the caller has a hypothesis. Proposing one is noise.

    NARROWED (CP2b): this used to pass only because the old guard's
    `level != "restricted"` half excluded restricted unconditionally,
    regardless of `parsed` -- a key restricted never carried anyway, even
    before this fix, since `parse` was `None` for the fake worker's
    non-plain levels. Now that `restricted` carries `hypothesis_held`
    instead, `"parsed" not in payload` pins the actual contract (FR-021's
    "no proposal at restricted" AND the naming contract from cycle 1) in
    one assertion, rather than the guard's exclusion alone.
    """
    payload = await call(
        word="pukul", level="restricted", morphs=[{"msa_hvo": 5001}]
    )

    assert "proposed_decomposition" not in payload
    assert "parsed" not in payload


async def test_no_proposal_is_offered_from_a_cold_index(tmp_path, monkeypatch):
    """A plain yes/no must never silently become a full lexicon walk.

    FR-021 is a MAY, and on a large project building the index dominates
    the call. A courtesy that made the tool slower at the thing it was
    asked to do would not be a courtesy.
    """
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )

    cold = RecordingWorker(index_ready=False)
    parse_handler.set_runner(
        ParseRunner(pool=Pool(cold), record_dir=tmp_path / "runs", grace_window=30.0)
    )
    try:
        payload = await call(word="pukul", level="plain")
    finally:
        parse_handler.set_runner(None)

    assert payload["parsed"] is False
    assert "proposed_decomposition" not in payload
    assert cold.resolve_calls, "the proposal did not ask at all"
    assert all(c["only_if_indexed"] for c in cold.resolve_calls), (
        "the proposal asked for an index to be BUILT; a MAY must never make "
        "a plain yes/no pay for a full lexicon walk"
    )



# ---------------------------------------------------------------------------
# Branches the happy paths do not reach (QC follow-up)
# ---------------------------------------------------------------------------


async def test_a_failing_identifier_spec_echoes_an_int_morph(worker, tmp_path, monkeypatch):
    """`morph` carries the identifier when that is what the caller gave.

    Every other refusal test uses a headword, so the `msa_hvo` branch of the
    refusal builder was never exercised -- and a caller who passed an
    identifier would have got `morph: null`, which names nothing and makes
    the refusal unactionable.
    """
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    refusing = RecordingWorker(
        resolutions={
            0: {"outcome": "none", "msa_hvos": [], "candidates": [], "morph": 999999}
        }
    )
    parse_handler.set_runner(
        ParseRunner(pool=Pool(refusing), record_dir=tmp_path / "runs", grace_window=30.0)
    )
    try:
        payload = await call(
            word="makan", level="restricted", morphs=[{"msa_hvo": 999999}]
        )
    finally:
        parse_handler.set_runner(None)

    assert payload["error_code"] == "parse_morph_unresolved"
    assert payload["morph"] == 999999, (
        "an identifier that did not resolve must be echoed as the morph; "
        f"got {payload['morph']!r}"
    )
    assert refusing.calls == [], "a parse ran for an unresolvable identifier"


async def test_a_trace_whose_size_cannot_be_read_still_returns_a_result(wired, monkeypatch):
    """`_trace_bytes` fails soft: a missing size is not a failed parse.

    The size is a courtesy that lets a caller decide whether to open the
    trace. Losing it is strictly better than losing the parse, and this
    pins that -- the branch was otherwise reachable only by an unlucky
    filesystem.
    """
    monkeypatch.setattr(
        parse_handler, "_trace_bytes", lambda handle, path: None
    )

    payload = await call(word="makan", level="explain")

    assert payload["status"] == "ok"
    assert payload["trace_available"] is True
    assert payload["trace_bytes"] is None
    assert payload["trace_path"], "the path survives even when the size does not"
