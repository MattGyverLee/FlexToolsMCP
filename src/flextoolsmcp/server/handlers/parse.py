#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_try_word and flextools_parse_status (parser-check CP2b), and
flextools_parse_text (parser-check CP3, US2).

Authority: specs/parser-check-cp2b/contracts/tools.md (levels, ordering
guarantees, refusal table, the run contract), specs/parser-check-cp2/spec.md
FR-012 .. FR-016 and FR-026 .. FR-036, data-model.md sections 1-4.

WHAT THIS MODULE DOES NOT DO, and why that is the point:

  * It never constructs a parser, opens a project, or loads a grammar. Every
    one of those happens in the parse worker, a separate process addressed
    through `server/parse/worker_client.py`. The MCP server process holding
    an LCM cache is the failure CP1's boundary test exists to prevent, and
    `tests/test_cp1_boundary.py` asserts that no handler reaches the parser
    facade outside `server/parse/` (T060).
  * It never runs the engine gate itself. `check_active_parser(project,
    supported_engines=("HC",))` is the **first statement of the worker's
    request handler** (worker_main.py `_RealBackend.preflight`), which is
    what makes FR-015's "before any parser is constructed" true of the
    process that would do the constructing. Running a second copy here
    would read `ActiveParser` from a project this process does not have
    open -- it would have to open one to do it, which is the thing
    forbidden above. The refusal arrives over the worker channel with its
    `parser_engine_mismatch` detail intact and is re-emitted unchanged.
  * It never starts a parse by any route other than `ParseRunner`. FR-026
    says all parser execution goes through one mechanism and that there is
    no second synchronous path; a "just this once" direct call here is
    exactly how a second one appears.

THE BATCH'S ENGINE CHECK IS DIFFERENT, AND DELIBERATELY SO (FR-024). For
`flextools_parse_text` the gate fires ONCE, at submission, as the handler's
first project-touching statement -- `runner.check_engine`, which asks the
worker to run `check_active_parser` and nothing else -- before the scope is
resolved and before any word is queued. From then on the batch's words
observe the engine rather than gate on it, so a user flipping the active
parser mid-batch gets a warning on the run, not a batch that dies at word
four thousand.

THE GRACE WINDOW IS A REPORTING BOUNDARY, NOT A TIMEOUT (FR-028, SC-010).
`ParseRunner.start_run` returns when the run finishes *or* when the window
closes, whichever comes first. This handler tells the two apart with
`handle.is_terminal` and does nothing else about it: a run still going is
left going, untouched, and the caller gets a handle to poll. Nothing on this
path cancels a run, shortens one, or passes a deadline downstream.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps
from ..models import MorphSpec, ParseSandboxInput, ParseTextInput, ResolvedScope
from ..parse.fingerprint import build_fingerprint
from ..parse.measure import (
    DEFAULT_BOUND_SECONDS,
    MeasurementFailed,
    measure_word,
)
from ..parse.priority import Priority
from ..parse.record import MetaUnreadable
from ..parse.runner import ParseRunner
from ..parse.stages import RunStage
from ..parse.worker_client import SHARED_ROLE, WorkerError

try:
    from ...response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

# json_response / session_state come from the shared kernel helper; the other
# two returned slots are unused here and intentionally discarded.
json_response, session_state, _get_log_dir, _get_api_index = safe_import_kernel_deps()


# ---------------------------------------------------------------------------
# The one runner
# ---------------------------------------------------------------------------
#
# Module-level and lazy, for two reasons that pull the same way. FR-026's
# "one mechanism" is only observable if there is literally one object: two
# runners would each hold their own worker pool, so "one worker per project"
# would quietly become two, and two processes would hold the same `.fwdata`
# (issue #57). And `flextools_parse_status` has to find runs started by
# `flextools_try_word`, which it can only do if both reach the same
# instance.
#
# Lazy rather than constructed at import because building it touches asyncio
# and spawns nothing until a run is actually started -- importing this module
# during tool-schema generation must stay free.
# ---------------------------------------------------------------------------

_runner: Optional[ParseRunner] = None


def get_runner() -> ParseRunner:
    """The server process's single `ParseRunner`, created on first use."""
    global _runner
    if _runner is None:
        _runner = ParseRunner()
    return _runner


def peek_runner() -> Optional[ParseRunner]:
    """The server's `ParseRunner` if one already exists, without creating it.

    For call sites that only want to check for an existing worker (the
    `run_module` write gate's own-worker detection, and
    `flextools_parse_release`, #223) -- `get_runner()` would spin one up
    just to find it empty, which would spawn a subprocess nobody asked for
    and then immediately have nothing to release.
    """
    return _runner


def set_runner(runner: Optional[ParseRunner]) -> None:
    """Replace the runner. For tests only.

    Exists so a test can inject a stub-backed runner (`ParseRunner(stub=True)`)
    without monkeypatching a module global by name, and so `None` restores
    the lazy default between tests. Production code calls `get_runner()`.
    """
    global _runner
    _runner = runner


async def aclose_runner() -> None:
    """Reap the runner's workers, if one was ever built.

    Called from server shutdown. Idempotent, and deliberately does not build
    a runner just to close it -- a server that never parsed has nothing to
    reap and must not spawn a worker on its way out.
    """
    global _runner
    runner, _runner = _runner, None
    if runner is not None:
        await runner.aclose()


# ---------------------------------------------------------------------------
# next_step rungs -- SPEC 10.1's shape, matching handlers/diagnostic_health.py
# ---------------------------------------------------------------------------


def _rung(
    action: str,
    rationale: str,
    est_cost: str,
    tool: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One structured rung: `{action, tool, args, rationale, est_cost}`.

    Same shape as `diagnostic_health._parser_next_step`, kept identical on
    purpose -- SC-011's sweep asserts that no emitted rung names a tool that
    does not exist, and a second rung shape would need a second sweep.
    """
    return {
        "action": action,
        "tool": tool,
        "args": args,
        "rationale": rationale,
        "est_cost": est_cost,
    }


# ---------------------------------------------------------------------------
# Next-step proposals (CP3, US6; FR-056, FR-057; data-model.md section 14)
# ---------------------------------------------------------------------------
#
# The same rung shape as every other `next_step` -- `args` is the proposal's
# directly usable arguments and `est_cost` its mandatory cost estimate, where
# "unbounded" is a legitimate value. One shape, so SC-019's sweep over every
# response the feature can emit is one sweep.
#
# THE GRAMMAR SCAN FIRES ON EXACTLY FOUR CONDITIONS (FR-056): a single word
# that misses the fast-path window; a batch that enters grammar loading and
# stays there; a terminal failure; a bounded measurement that exceeds its
# bound. Never on a request answered inline, and never on every response --
# a suggestion seen on success and failure alike teaches nothing on failure.
#
# Where a trace and the static scan are both candidates, the scan comes
# FIRST: it costs no parse time and may make the trace unnecessary (FR-057).
# No proposal names a filing step -- at CP3 every session is read-only.


def _grammar_scan_rung(project_name: Optional[str]) -> Dict[str, Any]:
    """The static grammar scan: CP1's instrument, finally given a caller."""
    return _rung(
        action="Scan this project's grammar for path-multiplying properties.",
        tool="flextools_grammar_health",
        args={"project_name": project_name},
        rationale=(
            "A static scan that runs no parse. It names the grammar properties "
            "that multiply the search space -- the usual reason a load or a "
            "parse is slow enough to notice -- and is cheaper than any trace "
            "it may make unnecessary."
        ),
        est_cost="seconds to a minute",
    )


def _measurement_rung(
    project_name: Optional[str], word: str, bound_seconds: float = DEFAULT_BOUND_SECONDS
) -> Dict[str, Any]:
    """Spend one word finding out whether the grammar is the problem."""
    return _rung(
        action="Measure one word to completion under a hard time bound.",
        tool="flextools_try_word",
        args={
            "word": word,
            "level": "plain",
            "bound_seconds": bound_seconds,
            "project_name": project_name,
        },
        rationale=(
            "Runs this one word in a worker of its own and stops it at the "
            "bound. A grammar that cannot finish one short word will not "
            "finish a corpus, and finding that out costs one word, not one "
            "night. Blowing the bound is reported as the finding, not an error."
        ),
        est_cost=f"at most {bound_seconds:g} seconds",
    )


def _trace_after_scan_rung(project_name: Optional[str], word: str) -> Dict[str, Any]:
    """The full trace, proposed only AFTER the scan (FR-057)."""
    return _rung(
        action="If the scan names nothing, trace this word at the explaining level.",
        tool="flextools_try_word",
        args={"word": word, "level": "explain", "project_name": project_name},
        rationale=(
            "The parser's own trace, with no hypothesis to narrow it. On a "
            "grammar that has just failed to finish one word it may not "
            "finish either, which is why the static scan comes first."
        ),
        est_cost="unbounded",
    )


def _read_run_rung(run_id: str, why: str) -> Dict[str, Any]:
    """Read a run back from disk (FR-058: `flextools_parse_log` now exists)."""
    return _rung(
        action="Read this run's record back.",
        tool="flextools_parse_log",
        args={"run_id": run_id, "section": "summary"},
        rationale=why,
        est_cost="instant",
    )


def _stuck_loading(handle) -> bool:
    """A batch that entered grammar loading and has stayed there (FR-056).

    "Stayed" means longer than the fast-path window: a load that outlives the
    window a single word is answered in is a load worth a static look.
    """
    if not getattr(handle, "is_batch", False):
        return False
    if handle.stage is not RunStage.LOADING_GRAMMAR:
        return False
    entered = getattr(handle, "stage_entered_at", None)
    if entered is None:
        return False
    return (time.monotonic() - entered) > get_runner().grace_window


# ---------------------------------------------------------------------------
# Restriction resolution -- the seam the restricted level runs through
# ---------------------------------------------------------------------------


class MorphResolutionRefused(Exception):
    """A piece of the decomposition did not resolve. Carries the refusal.

    Raised rather than returned so there is no code path on which an
    unresolved piece can be skipped and the remaining pieces parsed anyway:
    a partially-resolved decomposition is a *different* hypothesis from the
    one the caller wrote, and tracing it would answer a question nobody
    asked (FR-019).
    """

    def __init__(self, detail: Dict[str, Any]) -> None:
        super().__init__(detail.get("hint") or "A morph did not resolve.")
        self.detail = detail


async def _resolve_restriction(
    project_name: str, morphs: List[MorphSpec]
) -> tuple[int, ...]:
    """Turn a decomposition into the MSA identifiers the parser requires.

    RESOLUTION COMPLETES BEFORE ANY PARSE IS ENQUEUED. That ordering is the
    requirement, not an optimisation: FR-019 says an unresolvable piece
    refuses with **no parse run**, and SC-005 asserts it as a negative --
    zero recorded parses. Resolving lazily inside the run would satisfy the
    wording and break the guarantee.

    The lookup itself happens in the worker, because the worker is the only
    process with a project open (research.md R-02). It is its own request on
    the channel and parses nothing: `ParseWorker._drain_resolves` answers it
    from a lexicon index without touching the parser area at all. So "before
    the worker is asked for anything" is true of the thing that matters --
    no parse -- while the lexicon read reaches the only process that can
    perform it.

    A piece that already carries `msa_hvo` still goes through the resolver.
    It is not a shortcut worth taking: an identifier is a session-scoped
    handle that liblcm renumbers on every cache load, so one carried over
    from an earlier session resolves to a real but DIFFERENT object (issue
    #103). The resolver checks it against the index and refuses an unknown
    one rather than handing it to the parser.

    Returns a non-empty tuple, or raises. It never returns an empty one:
    `TraceWordXml` reads an empty selection as "admit nothing" rather than
    "no restriction", and the setting outlives the call, so an empty tuple
    escaping here would corrupt the *next* parse as well as this one
    (contracts/tools.md, "Never widen"; spec.md Delta 2).
    """
    runner = get_runner()
    worker = await runner.pool.get(project_name)

    answer = await worker.resolve_morphs(
        request_id=f"resolve:{uuid.uuid4().hex[:12]}",
        run_id="resolve",
        morphs=[_morph_payload(m) for m in morphs],
    )

    resolved: List[int] = []
    for row in answer.get("resolutions") or []:
        if row.get("outcome") != "ok":
            # THE FIRST FAILURE REFUSES, AND NOTHING IS PARSED. Not "the
            # pieces that did resolve are traced": a partially-resolved
            # decomposition is a DIFFERENT hypothesis from the one the
            # caller wrote, and tracing it would answer a question nobody
            # asked while looking like an answer to the one they did.
            raise MorphResolutionRefused(_refusal_from_row(row))
        resolved.extend(int(h) for h in (row.get("msa_hvos") or []))

    if not resolved:
        # Unreachable through `TryWordInput`, which already refuses an empty
        # `morphs` at validation, and unreachable again through the loop
        # above, since an `ok` row carries at least one identifier. Asserted
        # anyway because this is the last point at which an empty selection
        # is still cheap to stop, and because the cost of being wrong is a
        # corrupted subsequent parse rather than a bad answer to this one.
        raise MorphResolutionRefused(
            {
                "error_code": "parse_morph_unresolved",
                "morph": None,
                "position": None,
                "resolved_to": "none",
                "candidates": [],
                "hint": (
                    "The decomposition resolved to no analyses at all. This is "
                    "a refusal, not an unrestricted parse: an empty restriction "
                    "means 'admit nothing' to the parser, not 'no restriction'. "
                    "Use level='explain' to trace without a hypothesis."
                ),
            }
        )

    # De-duplicated with order preserved. Two pieces resolving to the same
    # analysis is ordinary (a reduplicated affix, a caller repeating an
    # identifier); handing the parser the same hvo twice is not.
    seen: set = set()
    unique: List[int] = []
    for hvo in resolved:
        if hvo not in seen:
            seen.add(hvo)
            unique.append(hvo)
    return tuple(unique)


def _morph_payload(morph: MorphSpec) -> Dict[str, Any]:
    """One `MorphSpec` as the four plain fields the worker reads."""
    return {
        "headword": morph.headword,
        "sense": morph.sense,
        "msa_hvo": morph.msa_hvo,
        "position": morph.position,
    }


def _refusal_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Build `parse_morph_unresolved` from one failed resolution.

    FIVE FIELDS, IN THIS EXACT ORDER: `morph`, `position`, `resolved_to`,
    `candidates`, `hint` (T037). The hint comes from
    `resolver.refusal_detail`, which writes a different one per outcome --
    `none`, `ambiguous` and `no_msa` call for three different actions from
    the caller, and a shared hint would undo the distinction the outcomes
    exist to draw.
    """
    from ..parse.resolver import Resolution, refusal_detail

    class _Spec:
        headword = row.get("morph") if isinstance(row.get("morph"), str) else None
        msa_hvo = row.get("morph") if isinstance(row.get("morph"), int) else None
        position = row.get("position")
        sense = None

    resolution = Resolution(spec=_Spec(), outcome=str(row.get("outcome") or "none"))
    detail = refusal_detail(resolution)
    # The candidates come from the worker, which is what actually looked
    # them up; `refusal_detail` only had the empty list this side built.
    detail["candidates"] = list(row.get("candidates") or [])
    return detail


# ---------------------------------------------------------------------------
# Project resolution -- the same two steps every project-touching tool takes
# ---------------------------------------------------------------------------


def _resolve_project(project_name: Optional[str]):
    """Session fallback, then fuzzy resolution. Returns `(name, error)`.

    Lifted from `handlers/grammar_health.py` rather than reinvented so that
    `project_not_found`, `project_name_required` and their suggestion
    payloads stay one implementation across every tool that names a project.
    """
    try:
        from .execution import _available_projects_payload
    except (ImportError, ValueError):
        from server.handlers.execution import _available_projects_payload

    name = project_name or session_state.get_project()
    if not name:
        return None, error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or "
            "provide it directly.",
            session=session_state.summary(),
            **_available_projects_payload(),
        )

    try:
        from ..project_discovery import resolve_or_explain
    except (ImportError, ValueError):
        from server.project_discovery import resolve_or_explain

    resolved, resolve_err = resolve_or_explain(name)
    if resolve_err:
        return None, error_response(
            resolve_err["error_code"],
            resolve_err["message"],
            suggestions=resolve_err["suggestions"],
            reason=resolve_err["reason"],
            hint=resolve_err["hint"],
            session=session_state.summary(),
        )
    if resolved:
        try:
            from ...project_adoption import adopt_resolved_project
        except ImportError:
            from project_adoption import adopt_resolved_project
        name = adopt_resolved_project(
            session_state,
            resolved,
            log_context="flextools_try_word",
        )
    return name, None


# ---------------------------------------------------------------------------
# Worker failures -> the contract's refusal table
# ---------------------------------------------------------------------------


def _refusal_from_failure(failure) -> Optional[List[TextContent]]:
    """Re-emit a worker-side refusal, or None if this was a plain failure.

    The detail dict is passed through **unchanged**. The worker already
    shapes it exactly like the matching `response_models` detail model
    (research.md R-03), so rewriting it here is precisely where the field
    names would drift apart -- and `parser_engine_mismatch`'s field order is
    pinned by the parent spec, which a round-trip through this function
    would not preserve.
    """
    error_code = getattr(failure, "error_code", None)
    if not error_code:
        return None
    detail = dict(getattr(failure, "detail", None) or {})
    detail.pop("error_code", None)
    message = detail.pop("message", None) or failure.message
    return error_response(error_code, message, **detail)


# ---------------------------------------------------------------------------
# flextools_try_word
# ---------------------------------------------------------------------------


async def handle_flextools_try_word(args: dict) -> List[TextContent]:
    """Parse one word at one of three levels (FR-012).

    Read-only. The project is opened `writeEnabled=False` in the worker and
    nothing on this path records, files or writes a parse result -- which is
    what backs the tool's `READ_ONLY_SAFE` annotation (contracts/tools.md,
    "What backs the READ_ONLY_SAFE annotation").

    Args:
        args: validated `TryWordInput` dump -- `word`, `level`, `morphs`
            (restricted only), `project_name` (optional; falls back to the
            session).

    Returns:
        The complete result when the run finished inside the grace window,
        a bare handle when it did not, or one of the contract's refusals.
    """
    word: str = args["word"]
    level: str = args.get("level") or "plain"
    raw_morphs = args.get("morphs")

    project_name, project_error = _resolve_project(args.get("project_name"))
    if not project_name:
        # `_resolve_project` always pairs a missing name with its refusal;
        # the fallback exists so a future edit that breaks that pairing
        # fails as a refusal rather than as a `None` project reaching the
        # worker.
        return project_error or error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or "
            "provide it directly.",
        )

    refused = _read_refused_during_filing(project_name)
    if refused is not None:
        return refused

    bound_seconds = args.get("bound_seconds")
    if bound_seconds is not None:
        # US6: the bounded single-word measurement. `TryWordInput` has
        # already refused it on any level but plain.
        return await _measurement_response(project_name, word, float(bound_seconds))

    restricted_to: Optional[tuple] = None
    if level == "restricted":
        morphs = [
            m if isinstance(m, MorphSpec) else MorphSpec(**m)
            for m in (raw_morphs or [])
        ]
        # `TryWordInput` fills `position` from list order, but this handler
        # must not depend on that validator having run: `position` is what
        # the refusal uses to say WHICH piece failed, and a refusal that
        # cannot name the piece is one the caller can only retry. Filling it
        # here costs a loop and removes the dependency.
        for index, morph in enumerate(morphs):
            if morph.position is None:
                morph.position = index
        try:
            restricted_to = await _resolve_restriction(project_name, morphs)
        except MorphResolutionRefused as refused:
            # No parse has run and none will. That is the requirement
            # (FR-019) and the thing SC-005 asserts as a negative.
            detail = dict(refused.detail)
            detail.pop("error_code", None)
            hint = detail.get("hint") or str(refused)
            return error_response("parse_morph_unresolved", hint, **detail)

    runner = get_runner()
    try:
        handle = await runner.start_run(
            project_name=project_name,
            wordforms=[word],
            level=level,
            restricted_to=restricted_to,
            priority=Priority.TRY_A_WORD,
        )
    except WorkerError as exc:
        # The worker refused or died before the run existed -- an engine
        # mismatch on startup, a project that will not open, pythonnet
        # missing. Its detail is carried through unchanged.
        error_code = getattr(exc, "error_code", None)
        if error_code:
            detail = dict(getattr(exc, "detail", None) or {})
            detail.pop("error_code", None)
            message = detail.pop("message", None) or str(exc)
            return error_response(error_code, message, **detail)
        return error_response(
            "runtime_error",
            str(exc),
            error_type=type(exc).__name__,
        )

    if not handle.is_terminal:
        return _overflow_response(handle, word, level, project_name)

    if handle.stage is RunStage.FAILED and handle.failure is not None:
        return _failed_run_response(handle)

    result = _inline_response(handle, word, level, project_name, restricted_to)

    # FR-021, and only where it can be offered honestly: the caller has no
    # decomposition, the word did not parse, and the lexicon index is
    # already warm. On agreement -- a word that parsed -- nothing is
    # offered, for the same reason FR-025 forbids congratulating a correct
    # hypothesis.
    #
    # Gated on the PRESENCE of `parsed`, not its truthiness with a falsy
    # default. `restricted` never carries `parsed` at all (it answers a
    # different question -- see `_inline_response`), and `parse_error` means
    # the parse threw rather than failed, so neither is a "word did not
    # parse" fact this assist may act on. `result.get("parsed", False)`
    # used to stand in for "did this parse fail", but that default fires
    # just as readily when `parsed` was never set -- which was exactly
    # `explain`'s case before this fix, and is exactly the defect class
    # this whole file is being corrected for: a missing key must never
    # read as a definite negative.
    is_definite_parse_failure = (
        level in ("plain", "explain")
        and "parsed" in result
        and result["parsed"] is False
        and "parse_error" not in result
    )
    if is_definite_parse_failure:
        proposal = await _propose_decomposition(project_name, word)
        if proposal is not None:
            result["proposed_decomposition"] = proposal

    return json_response(build_response_with_context(result))


def _failed_run_response(handle) -> List[TextContent]:
    """A single-word run that FAILED: its refusal, or the failure itself.

    A terminal failure is one of FR-056's four triggers, so a plain failure
    carries the structured failure rungs -- the static scan first -- as its
    top-level `next_step`. Additive: the run record's own `failure.next_step`
    prose, which `flextools_parse_status` reports, is unchanged in shape.
    """
    refusal = _refusal_from_failure(handle.failure)
    if refusal is not None:
        return refusal
    return error_response(
        "runtime_error",
        handle.failure.message,
        error_type=handle.failure.error_type,
        stage_at_failure=handle.failure.stage_at_failure,
        next_step=_failure_rungs(handle),
    )


async def _measurement_response(
    project_name: str, word: str, bound_seconds: float
) -> List[TextContent]:
    """The bounded measurement's response (FR-051..FR-056).

    Terminating at the bound is a SUCCESSFUL response carrying its
    measurement (FR-054), and it is the fourth of FR-056's triggers: the
    static scan, then the trace. A measurement that finished inside the bound
    carries no proposal -- there is nothing to route.
    """
    runner = get_runner()
    try:
        measurement = await measure_word(
            runner,
            project_name=project_name,
            wordform=word,
            bound_seconds=bound_seconds,
        )
    except MeasurementFailed as failed:
        return _failed_run_response(failed.handle)
    except WorkerError as exc:
        return _worker_error_response(exc)

    result: Dict[str, Any] = {
        "status": "ok",
        "project": project_name,
        "word": word,
        "level": "plain",
        "measurement": measurement.to_dict(),
        "finding": measurement.finding,
        "next_step": None,
    }
    if measurement.exceeded_bound:
        result["next_step"] = [
            _grammar_scan_rung(project_name),
            _trace_after_scan_rung(project_name, word),
        ]
    return json_response(build_response_with_context(result))


def _overflow_response(
    handle, word: str, level: str, project_name: str
) -> List[TextContent]:
    """The grace window closed first: hand back a handle, touch nothing.

    The run is **still going**. Nothing here cancels it, and the response
    says so in as many words, because a caller who reads a handle as "it
    gave up" will resubmit the word and pay for the grammar load twice.
    """
    result: Dict[str, Any] = {
        "status": "ok",
        "project": project_name,
        "word": word,
        "level": level,
        "run_id": handle.run_id,
        "stage": handle.stage.value,
        "words_completed": handle.words_completed,
        "words_total": handle.words_total,
        "note": (
            "This word is taking longer than the grace window, so here is a "
            "handle. The parse is still running -- it was not cancelled, "
            "slowed or throttled. Poll the handle for the result."
        ),
        "next_step": [
            _rung(
                action="Poll this run for its result.",
                tool="flextools_parse_status",
                args={"run_id": handle.run_id},
                rationale=(
                    "The run outlived the reporting window and is still "
                    "going. Its stage distinguishes a slow grammar load "
                    "from slow parsing."
                ),
                est_cost="instant",
            ),
            # FR-056: a single word that missed the fast-path window.
            _grammar_scan_rung(project_name),
        ],
    }
    return json_response(build_response_with_context(result))


def _inline_response(
    handle, word: str, level: str, project_name: str, restricted_to
) -> Dict[str, Any]:
    """The run finished inside the window: the complete answer, in one call.

    Trace payloads are reported by PATH, never inlined. A trace runs to tens
    or hundreds of kilobytes; the parent spec calls its size "a design
    decision rather than a detail", and an inlined one is both unreadable
    and liable to overflow the transport (data-model.md section 5, R-07).
    """
    entry = handle.results[0] if handle.results else {}
    parse = entry.get("parse") or {}

    result: Dict[str, Any] = {
        "status": "ok",
        "project": project_name,
        "word": word,
        "level": level,
        "run_id": handle.run_id,
        "stage": handle.stage.value,
    }

    if level == "plain":
        result["parsed"] = bool(parse.get("parsed"))
        result["analysis_count"] = int(parse.get("analysis_count") or 0)
    else:
        trace_path = entry.get("trace_path")
        result["trace_available"] = trace_path is not None
        if trace_path is not None:
            result["trace_path"] = str(handle.record.root / trace_path)
            result["trace_bytes"] = _trace_bytes(handle, trace_path)

        # The three-way outcome (worker_main.py `_summarize_trace`), copied
        # over by NAME rather than defaulted, so a missing key stays
        # missing instead of reading as a fact nobody established.
        #
        #   explain    -> `parsed` + `analysis_count` -- the same
        #                 unrestricted question `plain` asks, and the count
        #                 is provably identical (both filter through the
        #                 same GetMorphs, HCParser.cs:104-113/213-215).
        #   restricted -> `hypothesis_held` + `restricted_analysis_count`,
        #                 NEVER `parsed`. A restriction narrows the search
        #                 before the parse runs (HCParser.cs:186-199,211),
        #                 so its survivors answer "does my restriction
        #                 still admit an analysis" -- never "does this word
        #                 parse" -- and reusing `parsed`'s vocabulary would
        #                 let a caller compare a restricted `False` against
        #                 a genuine unrestricted failure as the same fact.
        #   either level, on <Error> -> `parse_error` alone. The trace
        #                 threw; this response explains nothing about
        #                 whether the word parses, so it asserts neither of
        #                 the pairs above.
        if "parse_error" in parse:
            result["parse_error"] = parse["parse_error"]
        elif level == "explain":
            result["parsed"] = bool(parse.get("parsed"))
            result["analysis_count"] = int(parse.get("analysis_count") or 0)
        elif level == "restricted":
            result["hypothesis_held"] = bool(parse.get("hypothesis_held"))
            result["restricted_analysis_count"] = int(
                parse.get("restricted_analysis_count") or 0
            )

        if level == "restricted":
            # Echoed so the caller can see exactly what was traced. It is
            # what they gave, resolved -- never widened, never reordered
            # and never re-scored (FR-023).
            # `list(restricted_to)`, never `restricted_to or ()`. This
            # branch only runs for `restricted`, where the selection is
            # guaranteed non-empty -- but an or-default here would echo an
            # unrestricted parse as `restricted_to: []`, and in this
            # domain's vocabulary `[]` means "admit nothing", which is the
            # opposite. The idiom is removed rather than argued about.
            result["restricted_to"] = list(restricted_to)

    result.update(_level_guidance(level, result))
    return result


def _trace_bytes(handle, trace_path: str) -> Optional[int]:
    """Size of a written trace, or None if it cannot be stat'd.

    Reported rather than the payload so a caller can decide whether to open
    it. Failing soft: a missing size is a worse answer, not a failed parse.
    """
    try:
        return (handle.record.root / trace_path).stat().st_size
    except Exception:  # noqa: BLE001 -- see docstring
        return None


#: FR-014's steer, in one sentence, reused by every rung that offers a
#: level. Named rather than repeated so the two halves cannot drift into
#: contradicting each other: restricted **when you have a hypothesis**,
#: explain **only when you do not**.
_LEVEL_CHOICE = (
    "Use level='restricted' when you have a decomposition in mind -- it is the "
    "fastest, because the selection collapses the search space before any "
    "tracing cost is paid. Use level='explain' only when you have no "
    "hypothesis to offer: it is the slowest and the one under a budget cap."
)


def _restricted_rung(word: str) -> Dict[str, Any]:
    """Offer the restricted level, with a worked shape for `morphs`.

    The shape is spelled out because `morphs` takes headwords, not surface
    strings: a caller who writes the pieces of the word as they appear in it
    gets a refusal, and "see the docs" is a worse answer than an example.
    """
    return _rung(
        action=(
            "Re-ask with your proposed decomposition to get a trace restricted "
            "to it."
        ),
        tool="flextools_try_word",
        args={
            "word": word,
            "level": "restricted",
            "morphs": [
                {"headword": "<entry headword>"},
                {"headword": "<entry headword>", "sense": "<gloss or sense number>"},
            ],
        },
        rationale=(
            "You have a hypothesis, so this is both the cheapest answer and "
            "the one that tells you whether YOUR analysis is what fails. "
            "Pieces are named by entry headword -- there is no free-text form "
            "field, because this tool ships no segmenter."
        ),
        est_cost="fastest of the three levels",
    )


#: The ONLY way to reach lexicon data from this server, and the reason
#: FR-022 constrains every `next_step` this slice emits. There is no
#: lexicon-query tool to point at -- every other tool here is API discovery,
#: codegen or admin -- so a "look up the headwords" rung has to be a snippet
#: the caller runs, not a tool call. A rung naming a tool that does not exist
#: is the failure SC-011 counts, and CP1 shipped two of them by pointing at
#: `flextools_try_word` a checkpoint before it was built.
_LOOKUP_SNIPPET = """from flexicon import FLExProject

# Read-only: find the headwords to name in `morphs`.
for entry in project.LexEntry.GetAll():
    headword = project.LexEntry.GetHeadword(entry)
    if {word!r}.startswith(headword) or {word!r}.endswith(headword):
        senses = [project.Senses.GetGloss(s)
                  for s in project.LexEntry.GetAllSenses(entry)]
        report.Info(f"{{headword}}  {{senses}}")"""


def _lookup_rung(word: str) -> Dict[str, Any]:
    """How to find the headwords, given that no tool can be pointed at.

    The snippet is a crude prefix/suffix match on purpose, and the rationale
    says so: it is a way of listing candidate entries to read, not a
    segmentation. Dressing it up as one would be the same overclaim the
    proposal assist is careful not to make.
    """
    return _rung(
        action=(
            "List lexicon entries whose headwords could be pieces of this "
            "word, so you can write a decomposition."
        ),
        tool="flextools_run_module",
        args={"code": _LOOKUP_SNIPPET.format(word=word)},
        rationale=(
            "There is no lexicon-query tool to call: reading lexicon data "
            "means running Python against the project. This snippet lists "
            "entries whose headword is a prefix or suffix of the word -- a "
            "string match to read, not a segmentation, and it knows nothing "
            "about phonological rules."
        ),
        est_cost="one read-only module run",
    )


def _explain_rung(word: str) -> Dict[str, Any]:
    """Offer the explain level -- deliberately second, and hedged.

    Second because FR-014 steers to `explain` only in the absence of a
    hypothesis. Putting it first would make the expensive level the default
    reading of "how do I find out why", which is the most common way this
    feature will feel slow.
    """
    return _rung(
        action="Re-ask at the explaining level to get the parser's own trace.",
        tool="flextools_try_word",
        args={"word": word, "level": "explain"},
        rationale=(
            "Use this when you have no decomposition to propose. It searches "
            "without a restriction, so it is the slowest level and the one "
            "under a budget cap."
        ),
        est_cost="slowest of the three levels",
    )


async def _propose_decomposition(
    project_name: str, word: str
) -> Optional[Dict[str, Any]]:
    """A proposed `morphs`, or None. Best-effort, and bounded twice over.

    FR-021 is a MAY, and this implementation takes both bounds the wording
    allows:

      * **Only when every piece has exactly one unambiguous candidate.** The
        only decomposition this tool can offer without a segmenter -- which
        it does not ship -- is the one-piece case: the word itself is a
        headword in the lexicon. Anything more would require deciding where
        the boundaries fall, which is the parser's job and the reason the
        caller is here.
      * **Only from an index that is already warm.** Asked with
        `only_if_indexed`, so a plain yes/no never silently becomes a full
        lexicon walk. On a large project building the index dominates the
        call, and paying that for an optional courtesy would make the tool
        worse at the thing it was asked to do.

    A LEXICON STRING MATCH IS NOT A PARSE. That is why the return value is
    labelled rather than returned bare: it knows nothing about phonological
    rules or environments, and a caller who mistakes it for an analysis has
    been misled by this tool rather than helped by it.
    """
    try:
        runner = get_runner()
        worker = runner.pool.peek(project_name)
        if worker is None:
            return None
        answer = await worker.resolve_morphs(
            request_id=f"propose:{uuid.uuid4().hex[:12]}",
            run_id="propose",
            morphs=[{"headword": word, "sense": None, "msa_hvo": None,
                     "position": 0}],
            only_if_indexed=True,
            timeout=15.0,
        )
    except Exception:  # noqa: BLE001 -- a courtesy must never fail a parse
        return None

    if not answer.get("index_ready"):
        return None
    rows = answer.get("resolutions") or []
    if len(rows) != 1 or rows[0].get("outcome") != "ok":
        return None

    return {
        "status": "proposed, unverified",
        "basis": "lexicon string match",
        "caveat": (
            "This is a headword that matches the word exactly. It is NOT a "
            "parse: it knows nothing about phonological rules or "
            "environments, and it has not been traced. Pass it as `morphs` "
            "at level='restricted' to find out whether it holds."
        ),
        "morphs": [{"headword": word, "position": 0}],
    }


def _level_guidance(level: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """The level-appropriate guidance block (FR-013, FR-014).

    `explains_failure` is a field rather than a matter of wording so FR-013
    is machine-checkable: the plain level reports **that** nothing parsed and
    nothing more, and `tests/test_try_word_handler.py` asserts the flag is
    False on every plain response and that no reason-bearing key rides along
    with it. A prose-only promise here would be one refactor away from a
    plain response that quietly starts explaining itself.

    Note what a SUCCESSFUL plain parse gets: no rungs at all. The word
    parsed; there is nothing to diagnose, and offering the expensive level
    anyway would train callers to skim the guidance field -- the same reason
    FR-025 forbids congratulating a correct hypothesis.
    """
    word = str(result.get("word") or "")

    if level == "plain":
        if result.get("parsed"):
            return {"explains_failure": False, "next_step": None}
        return {
            "explains_failure": False,
            "guidance": (
                "This level reports only THAT nothing parsed. It does not know "
                "why, and nothing in this response is a reason. " + _LEVEL_CHOICE
            ),
            "next_step": [
                _restricted_rung(word),
                # The decomposition is the MISSING INPUT (FR-022), so the
                # rung that says how to obtain one comes before the
                # expensive level that needs none.
                _lookup_rung(word),
                _explain_rung(word),
            ],
        }

    if level == "explain":
        # On <Error> the trace threw, so this response explains nothing
        # about the word either way -- `explains_failure` is omitted
        # entirely rather than set to a value in either direction, the same
        # "presence of the key is the fact" discipline as the guard in
        # `handle_flextools_try_word` (FR-013/FR-025 do not apply to a
        # question this response never actually answered).
        if "parse_error" in result:
            return {"next_step": None}

        # A SUCCESSFUL explain, mirroring the plain branch above: nothing
        # to diagnose, so no rungs and no failure-flavoured guidance. Before
        # this fix `parsed` was never set for explain, so this branch was
        # unreachable and every explain response -- including one for a
        # word that parsed -- got the failure guidance below (FR-025).
        if result.get("parsed"):
            return {"explains_failure": False, "next_step": None}

        return {
            "explains_failure": True,
            "guidance": (
                "This is the unrestricted trace -- the slowest level. "
                + _LEVEL_CHOICE
            ),
            "next_step": [_restricted_rung(word), _lookup_rung(word)],
        }

    # restricted: the caller already had a hypothesis and used the right
    # level for it, so `next_step` is None in every case -- there is
    # nowhere else to steer them. `explains_failure` is NOT unconditional
    # though: this is the same defect class as the explain branch above,
    # five lines away, and gets the same success gate.
    if "parse_error" in result:
        # The trace threw; this response explains nothing about the
        # hypothesis either way -- omit the flag entirely, same as explain.
        return {"next_step": None}

    if result.get("hypothesis_held"):
        # A held hypothesis is agreement, not a failure to diagnose.
        # FR-025 and contracts/tools.md:97 forbid commentary on it, the
        # same as a successful plain/explain above.
        return {"explains_failure": False, "next_step": None}

    # The hypothesis did not hold. The trace ran and reports why, so this
    # response DOES explain the failure -- unchanged from before this fix.
    return {"explains_failure": True, "next_step": None}


# ---------------------------------------------------------------------------
# flextools_parse_text (CP3, US2)
# ---------------------------------------------------------------------------

#: Carried on every READ-ONLY parse_text response (CP4 R-16, contracts s.1):
#: the tool is annotated destructive, and a caller deserves to know that this
#: call filed nothing. A filing run carries "started" instead.
FILING_NOT_REQUESTED = "not_requested"


def _worker_error_response(exc: Exception) -> List[TextContent]:
    """Re-emit a worker refusal under its own code, detail unchanged (R-03)."""
    error_code = getattr(exc, "error_code", None)
    if error_code:
        detail = dict(getattr(exc, "detail", None) or {})
        detail.pop("error_code", None)
        message = detail.pop("message", None) or detail.get("hint") or str(exc)
        return error_response(error_code, message, **detail)
    return error_response("runtime_error", str(exc), error_type=type(exc).__name__)


async def handle_flextools_parse_text(args: dict) -> List[TextContent]:
    """Submit a batch parse over a resolved scope (FR-014, FR-024, FR-025).

    ORDER, and why each step is where it is:

      1. Arguments and project name -- pure validation, touches nothing.
      2. THE ENGINE GATE -- the first project-touching statement (FR-024).
         Nothing about the scope is read and nothing is queued before it.
      3. Scope resolution -- in the worker, which is where the project is
         open. `parse_scope_empty` / `parse_scope_ambiguous` refuse here,
         with nothing parsed.
      4. The fingerprint -- the resolved scope plus the engine that passed
         step 2. Nothing describing the grammar (FR-011).
      5. The run -- `ParseRunner.start_run` at `Priority.LOW`, the existing
         runner's lower-priority path. No second execution model (FR-014).

    A scope that resolves to NO WORDS is not `parse_scope_empty` when texts
    matched: a text with paragraphs but no wordforms may simply never have
    been opened for interlinear work (FR-002), so the response says what was
    observed, starts no run, and does not claim the text is empty.
    """
    # Already validated at the dispatch boundary; rebuilt here for the typed
    # scope. `ParseTextInput` validates kind and value together.
    request = ParseTextInput(**args)
    scope = request.to_scope()

    project_name, project_error = _resolve_project(request.project_name)
    if not project_name:
        return project_error or error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or "
            "provide it directly.",
        )

    if request.apply:
        # CP4: filing. Its own path, in its own check order (contracts/tools.md
        # section 1); `apply` absent or false never reaches it (FR-001).
        return await _handle_filing_request(request, scope, project_name)

    refused = _read_refused_during_filing(project_name)
    if refused is not None:
        return refused

    runner = get_runner()

    # (2) FR-024 -- the gate, once, at submission, before anything else is
    # asked of the project.
    try:
        engine = await runner.check_engine(project_name)
    except WorkerError as exc:
        return _worker_error_response(exc)

    # (3) Resolution. Parses nothing.
    try:
        raw = dict(await runner.resolve_scope(project_name, scope.model_dump()))
    except WorkerError as exc:
        return _worker_error_response(exc)
    # The one project-state probe (FR-004) rides with the resolution; it is
    # the oracle's precondition and is recorded on the run.
    project_state = raw.pop("project_state", None)
    resolved = ResolvedScope(**raw)

    scope_block = {
        "kind": resolved.scope_kind,
        "value": resolved.scope_value,
        "text_ids": resolved.text_ids,
        "words_resolved": resolved.count_before_limit,
        "limit": resolved.limit,
        "truncated": resolved.truncated,
        "vernacular_ws": resolved.vernacular_ws,
    }

    if not resolved.words:
        # FR-002: not parse_scope_empty, and no claim that the texts are
        # empty. Only what was observed.
        result: Dict[str, Any] = {
            "status": "ok",
            "project": project_name,
            "run_id": None,
            "run_started": False,
            "scope": scope_block,
            "never_tokenized_text_ids": resolved.never_tokenized_text_ids,
            "unreadable_wordform_count": resolved.unreadable_wordform_count,
            "notes": resolved.notes or [
                "The selected texts yielded no words to parse, so no run was "
                "started."
            ],
            "filing": FILING_NOT_REQUESTED,
            "next_step": None,
        }
        return json_response(build_response_with_context(result))

    # (4) The fingerprint.
    fingerprint = build_fingerprint(resolved, engine)

    # (5) The run -- the one runner, at its lower-priority path.
    try:
        handle = await runner.start_run(
            project_name=project_name,
            wordforms=list(resolved.words),
            level="batch",
            priority=Priority.LOW,
            scope_fingerprint=fingerprint.to_dict(),
            engine_at_submission=engine,
            vernacular_ws=resolved.vernacular_ws,
            project_state=project_state,
        )
    except WorkerError as exc:
        return _worker_error_response(exc)

    result = {
        "status": "ok",
        "project": project_name,
        "run_id": handle.run_id,
        "run_started": True,
        "stage": handle.stage.value,
        "words_completed": handle.words_completed,
        "words_total": handle.words_total,
        "scope": scope_block,
        "scope_fingerprint": fingerprint.to_dict(),
        "engine_at_submission": engine,
        "record_dir": str(handle.record.root),
        "notes": resolved.notes,
        "filing": FILING_NOT_REQUESTED,
    }
    if handle.is_terminal:
        if handle.stage is RunStage.FAILED and handle.failure is not None:
            result["failure"] = handle.failure.to_dict()
        else:
            result["result_summary"] = _result_summary(handle)
        result.update(_batch_block(handle))
        result["next_step"] = _status_next_step(handle)
    else:
        result["note"] = (
            "The batch is running in the background and was not slowed or "
            "limited by this call returning. Poll the run for progress; single "
            "words you try meanwhile go ahead of it and it resumes where it was."
        )
        result["next_step"] = _status_next_step(handle)
    return json_response(build_response_with_context(result))


def _batch_block(handle) -> Dict[str, Any]:
    """What a batch run adds to a status or submission response."""
    if not getattr(handle, "is_batch", False):
        return {}
    block: Dict[str, Any] = {
        "scope_fingerprint": handle.scope_fingerprint,
        "engine_at_submission": handle.engine_at_submission,
        "engine_changed_midjob": handle.engine_changed_midjob,
    }
    if handle.counters is not None:
        from ..parse.record import COUNTER_DIVERGENCES

        block["counters"] = handle.counters.to_dict()
        block["counter_divergences"] = list(COUNTER_DIVERGENCES)
    warnings: List[str] = []
    if handle.engine_changed_midjob:
        # FR-024: a warning on the summary, never a refusal.
        warnings.append(
            f"The project's active parser changed while this batch was running "
            f"(submitted on {handle.engine_at_submission!r}, now "
            f"{handle.engine_now!r}). The batch carried on and its results are "
            f"labelled with the engine it was submitted on."
        )
    if warnings:
        block["warnings"] = warnings
    return block


# ---------------------------------------------------------------------------
# flextools_parse_text(apply=true) -- filing (CP4)
# ---------------------------------------------------------------------------
#
# THE CHECK ORDER IS THE CONTRACT (contracts/tools.md section 1). Each row is a
# refusal that stops the call; nothing below a refusal runs:
#
#    0  input validation                  (dispatch boundary)
#    1  project resolved                  project_name_required
#    2  filing claim held                 parser_filing_in_progress   FR-026
#    3  session write_enabled             server_state_error          FR-002
#    4  engine gate                       parser_engine_mismatch
#    5  HermitCrab agent probe            parser_agent_missing        FR-025
#    6  filing surface probe              parser_core_missing
#    7  scope resolution                  parse_scope_empty / _ambiguous
#    8  access PROBE, data only           (verdict into the plan)     FR-030
#    9  refuse-to-file gate               grammar_load_unclean        FR-020..FR-024
#   10  CONFIRMATION, bound to plan_id    confirmation_required       FR-005, FR-006
#   11  access GATE (confirmed call)      project_locked / project_drive_unavailable
#   12  gate again (confirmed call)       grammar_load_unclean        FR-024
#   13  backup, best-effort               never refuses               FR-007, FR-008
#   14  claim, run, run_id                                            FR-003
#
# THE RUNG ORDER IS run_module's, LITERALLY (FR-002): write_enabled (3), then
# confirmation (10), then the access gate (11), then backup (13). So an
# unconfirmed request against a project FLEx holds exclusively gets the
# preview -- whose `access` field already says the confirmed call will be
# refused and what the remedy is -- exactly as run_module's does. Rows 4-9 are
# filing's own preflights; each refuses before a preview exists because a
# preview cannot be built without it.
#
# CONFIRMATION IS UNCONDITIONAL FOR FILING (R-08). `require_write_confirmation`
# is read only to be disclosed in the plan; it never lowers this rung. And a
# confirmation counts only with a `plan_id` this session issued that is equal
# to the plan recomputed now: a bare `confirmed=True`, a plan_id from another
# scope, or a plan that has changed since it was shown gets a new preview.
# ---------------------------------------------------------------------------

try:
    from ...config import (
        config_get as _config_get,
        REQUIRE_WRITE_CONFIRMATION_KEY as _REQUIRE_CONFIRMATION_KEY,
        REQUIRE_WRITE_CONFIRMATION_DEFAULT as _REQUIRE_CONFIRMATION_DEFAULT,
    )
except (ImportError, ValueError):
    from config import (  # type: ignore[no-redef]
        config_get as _config_get,
        REQUIRE_WRITE_CONFIRMATION_KEY as _REQUIRE_CONFIRMATION_KEY,
        REQUIRE_WRITE_CONFIRMATION_DEFAULT as _REQUIRE_CONFIRMATION_DEFAULT,
    )

from .. import write_ladder  # noqa: E402 -- grouped with the CP4 section it serves
from ..filing import claims as filing_claims  # noqa: E402
from ..filing import filer as filing_filer  # noqa: E402
from ..filing import paths as filing_paths  # noqa: E402
from ..filing import plan as filing_plan  # noqa: E402
from ..filing import projection as filing_projection  # noqa: E402
from ..filing import wording as filing_wording  # noqa: E402

#: A filing run's `filing` value once it has started.
FILING_STARTED = "started"


def _filing_in_progress(claim) -> List[TextContent]:
    """Row 2 (FR-026): refused before anything heavy, four fields."""
    return error_response(
        "parser_filing_in_progress",
        f"A filing job is already running on project {claim.project!r}; a second "
        f"one is not started. Nothing was previewed, backed up or parsed.",
        run_id=claim.run_id,
        started_at=claim.started_at,
        words_completed=claim.words_completed,
        hint=filing_claims.in_progress_hint(claim),
    )


def _read_refused_during_filing(project_name: str) -> Optional[List[TextContent]]:
    """FR-027 (amended after L-0): a READ refused while filing, sharing off only.

    On a project with sharing off, the filing job is the only opener: a
    read-only open takes the project lock and a second, writable open then
    fails (L-0, evidence/l0-coexistence.json). So reads on such a project
    wait for its job (`claims.READS_REFUSED_ON_NON_SHARED_DURING_FILING`).
    Projects with sharing on are never restricted, and the run-reading tools
    (status, log, diff) never consult the claim at all -- they read disk.
    """
    claim = filing_claims.reads_refused(project_name)
    if claim is None:
        return None
    return error_response(
        "parser_filing_in_progress",
        f"A filing job is running on project {project_name!r}, which has sharing "
        f"turned off, so read-only parses of it wait until the job ends: on such a "
        f"project only one process can have it open, and the filing job has it. "
        f"Turning on project sharing in FieldWorks lets reads continue during "
        f"filing. Nothing was parsed.",
        run_id=claim.run_id,
        started_at=claim.started_at,
        words_completed=claim.words_completed,
        hint=filing_claims.in_progress_hint(claim),
    )


def _filing_needs_write_session() -> List[TextContent]:
    """Row 3: filing cannot quietly degrade to a read-only parse.

    `run_module` has no refusal here -- a disabled session simply runs its
    script read-only. `apply=true` cannot do that without lying about what
    it did, so it refuses, with an existing code (contracts row 3).
    """
    return error_response(
        "server_state_error",
        "Filing writes to the project, and this session was started read-only. "
        "Nothing was parsed.",
        server_state="write_disabled",
        component="session",
        state_description=(
            "The session's write_enabled is false. Start it with "
            "flextools_start(write_enabled=true) and resubmit; filing still asks "
            "for confirmation before anything is written."
        ),
    )


#: The verdict the plan states when the lock's holder is THIS server's own
#: read-only worker (the preview itself opens it). Not a collision: that
#: worker is released before the writable open (L-0: the two cannot coexist
#: on a non-shared project), and access is probed again after the release.
#:
#: Re-exported from `parse/own_worker.py`, the module both filing and
#: `run_module` share so the two write gates cannot answer "is this ours?"
#: differently (#223). Kept as a module attribute here too since existing
#: imports and tests read it from `handlers.parse`.
from ..parse.own_worker import (  # noqa: E402
    HELD_BY_OWN_READ_WORKER,
    own_worker_role,
    busy_own_worker_guidance,
    busy_own_worker_run_note,
)


def _held_by_own_read_worker(runner, project_name: str, decision) -> bool:
    """Is the lock that refuses this project held by our own READ worker?

    Filing's own writable open only ever collides with `SHARED_ROLE` (the
    preview's read worker) -- `run_module`'s write gate uses the more
    general `own_worker_role` directly, since a measurement worker can hold
    its project's lock too (#223).
    """
    return own_worker_role(runner, project_name, decision) == SHARED_ROLE


def _holder_is_own_read_worker(runner, project_name: str, access) -> bool:
    """Is `access`'s lock holder one of THIS server's own parse workers?

    The probe answers `held_by_other` for any live non-FieldWorks holder,
    and our own workers are such holders. This is the sandbox staleness
    check's form of `own_worker_role`: it starts from a bare access probe
    rather than a refusal decision, but answers "is this ours?" through the
    same `runner.own_worker_role_for_pid` (any role, #223).
    """
    if runner is None:
        return False
    holder = getattr(access, "holder", None)
    pid = getattr(holder, "pid", None)
    if pid is None:
        return False
    lookup = getattr(runner, "own_worker_role_for_pid", None)
    if lookup is not None:
        return lookup(project_name, pid) is not None
    read_worker_pid = getattr(runner, "read_worker_pid", None)
    if read_worker_pid is None:
        return False
    own = read_worker_pid(project_name)
    return own is not None and pid == own


def _access_block(decision) -> Dict[str, Any]:
    """Row 8: the access verdict as the plan states it (FR-030)."""
    verdict = decision.verdict
    block: Dict[str, Any] = {"verdict": verdict}
    if verdict == HELD_BY_OWN_READ_WORKER:
        if getattr(decision.access, "sharing_enabled", False):
            block["note"] = (
                "This server's own read-only worker has the project open. Sharing is "
                "enabled, so it stays open alongside filing, and single-word tries "
                "keep answering while the run goes."
            )
        else:
            block["note"] = (
                "This server's own read-only worker has the project open. It is closed "
                "before filing opens the project for writing, and access is checked "
                "again at that moment."
            )
    elif verdict == "open_shared":
        block["shared_mode_advisory"] = filing_wording.SHARED_MODE_ADVISORY
    elif decision.refusal is not None:
        block["remedy"] = decision.refusal.get("remedy") or decision.refusal.get("guidance")
        block["refused_on_confirm"] = True
    elif verdict == "unknown":
        block["remedy"] = (
            "The FieldWorks projects directory could not be located, so whether "
            "FieldWorks holds this project could not be checked. Set FW_PROJECTS_DIR "
            "or check the FieldWorks installation; the confirmed call is refused "
            "until access can be checked."
        )
        block["refused_on_confirm"] = True
    return block


async def _evaluate_filing_gate(
    runner, project_name: str, resolved: ResolvedScope, scope_key: str
) -> Dict[str, Any]:
    """Rows 9 and 12: the refuse-to-file gate, on THIS load (FR-020..FR-024, FR-039).

    Asks the read worker for this load's facts (a current grammar, its errors,
    a probe parse, the eligible forms), finds the MCP's own baseline for the
    project and scope, and compares. Returns the plan's `gate` slot; a refusal
    comes back under `status: "refused"` with its response in `refusal`. The
    raw facts and the baseline ride along (`current`, `baseline`) for the
    confirmed call to hand the filing worker as its job-time reference.
    """
    from ..filing import gate as filing_gate

    try:
        current = await runner.filing_gate(
            project_name, probe_word=resolved.words[0], vernacular_ws=resolved.vernacular_ws
        )
    except WorkerError as exc:
        return {"status": "refused", "refusal": _worker_error_response(exc)}
    baseline = filing_gate.find_baseline(project_name, scope_key, record_dir=runner.record_dir)
    standing = filing_gate.evaluate(current, baseline)
    if standing.refused:
        return {
            "status": "refused",
            "refusal": error_response(
                "grammar_load_unclean", standing.message(), **standing.refusal_detail()
            ),
        }
    slot = standing.to_dict()
    slot["baseline"] = (
        {"run_id": baseline.run_id, "lines": list(baseline.lines() or [])}
        if baseline is not None else None
    )
    slot["current"] = current
    return slot


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _confirmation_required(
    plan: Dict[str, Any], plan_id: str, request: ParseTextInput, *, reason: str
) -> List[TextContent]:
    """Row 10: the preview. Carries the plan and its id; writes nothing."""
    deletion = plan["deletion_projection"]
    upper_bound = int(deletion.get("upper_bound") or 0)
    words = int(plan.get("words_in_scope") or 0)
    overwrites = int((plan.get("disapproval_overwrites") or {}).get("count") or 0)
    unreadable = list(deletion.get("words_unreadable") or [])
    message = (
        f"Filing would change this project, and nothing has been written yet. It "
        f"may delete up to {upper_bound} "
        f"analys{'is' if upper_bound == 1 else 'es'} across {words} "
        f"word{'' if words == 1 else 's'}"
        + (f", and would overwrite {overwrites} human disapproval(s) of analyses in "
           f"use in a text with an approval" if overwrites else "")
        + (f". The analyses of {len(unreadable)} word(s) could not be read, so that "
           f"bound does not cover them; filing will delete nothing for them that this "
           f"plan does not name" if unreadable else "")
        + f". {reason} Read the plan, then resubmit the same call with "
        f"confirmed=true and plan_id to file. Filing cannot be undone."
    )
    backup = plan["backup"]
    note = (
        "A backup will be attempted on the CONFIRMED call, before the project is "
        "opened for writing -- not on this preview."
        if backup.get("outcome") == "will_be_taken"
        else backup.get("no_recovery_warning")
    )
    resubmit = {
        "scope_kind": request.scope_kind,
        "scope_value": request.scope_value,
        "limit": request.limit,
        "vernacular_ws": request.vernacular_ws,
        "project_name": request.project_name,
        "apply": True,
        "confirmed": True,
        "plan_id": plan_id,
    }
    return error_response(
        "confirmation_required",
        message,
        plan=plan,
        plan_id=plan_id,
        backup={"intent": backup.get("outcome"), "note": note},
        plan_id_limit=filing_wording.PLAN_ID_LIMIT,
        next_step=[
            _rung(
                action="Confirm this exact plan to file.",
                tool="flextools_parse_text",
                args={k: v for k, v in resubmit.items() if v is not None},
                rationale=(
                    "The plan is recomputed on the confirmed call; if anything in "
                    "it has changed you get a new preview instead of a filing run."
                ),
                est_cost="the whole scope: every word is parsed and filed",
            )
        ],
    )


async def _handle_filing_request(
    request: ParseTextInput, scope, project_name: str
) -> List[TextContent]:
    """`flextools_parse_text(apply=true)`: the preview, or -- bound to it -- the run.

    See the section comment above for the check order; the row numbers below
    are contracts/tools.md section 1's.
    """
    # (2) FR-026 -- the claim first, before anything heavy (SC-006).
    claim = filing_claims.lookup(project_name)
    if claim is not None:
        return _filing_in_progress(claim)

    # (3) FR-002 rung 1 -- the session, not the call, grants writing (R-15).
    if not session_state.is_write_enabled():
        return _filing_needs_write_session()

    runner = get_runner()

    # (4) The engine gate.
    try:
        engine = await runner.check_engine(project_name)
    except WorkerError as exc:
        return _worker_error_response(exc)

    # (5) FR-025 -- the HermitCrab agent, before any preview is built.
    try:
        agent = await runner.probe_agent(project_name)
    except WorkerError as exc:
        return _worker_error_response(exc)
    if agent.get("state") != "present":
        detail = {k: agent.get(k) for k in
                  ("agent_guid", "agent_name", "active_engine", "probe_source", "hint")}
        detail["active_engine"] = detail.get("active_engine") or engine
        return error_response(
            "parser_agent_missing",
            detail.get("hint") or "The HermitCrab parser agent was not found.",
            **detail,
        )

    # (6) R-03 -- the write spine's surface.
    import asyncio

    surface = await asyncio.to_thread(filing_filer.probe_filing_surface)
    if not surface.ok:
        detail = surface.refusal_detail()
        return error_response(
            "parser_core_missing",
            "Filing is unavailable: FieldWorks' parse filer could not be reached. "
            "Nothing was previewed or written.",
            **detail,
        )

    # (7) Scope resolution.
    try:
        raw = dict(await runner.resolve_scope(project_name, scope.model_dump()))
    except WorkerError as exc:
        return _worker_error_response(exc)
    project_state = raw.pop("project_state", None)
    resolved = ResolvedScope(**raw)
    if not resolved.words:
        return json_response(build_response_with_context({
            "status": "ok",
            "project": project_name,
            "run_id": None,
            "run_started": False,
            "filing": "nothing_to_file",
            "never_tokenized_text_ids": resolved.never_tokenized_text_ids,
            "notes": resolved.notes or [
                "The selected texts yielded no words to parse, so nothing would be "
                "filed and no preview was built."
            ],
            "next_step": None,
        }))
    fingerprint = build_fingerprint(resolved, engine)
    from ..parse.fingerprint import fingerprint_key

    scope_key = fingerprint_key(fingerprint.to_dict())

    # (8) FR-030 -- the access PROBE. Data for the plan; refused only at row 11.
    decision = write_ladder.probe_write_access(project_name)
    # Sharing is the PROJECT's setting, not the lock verdict: the probe answers
    # `held_by_other` for any Python holder, sharing or not, so "shared" read
    # off the verdict alone missed every shared project the MCP itself had
    # open (found live; evidence/shared-coexistence.json).
    sharing = bool(getattr(decision.access, "sharing_enabled", False))
    held_by_self = _held_by_own_read_worker(runner, project_name, decision)
    if held_by_self:
        # The holder is us (L-0, evidence/l0-coexistence.json): no refusal here;
        # the confirmed call releases the worker and probes again (row 11).
        decision = write_ladder.AccessDecision(
            project_name=project_name, access=decision.access,
            verdict=HELD_BY_OWN_READ_WORKER)

    # (9) FR-020..FR-024 -- the refuse-to-file gate, on this load.
    standing = await _evaluate_filing_gate(runner, project_name, resolved, scope_key)
    if standing.get("status") == "refused":
        return standing["refusal"]
    baseline_run = standing.pop("baseline", None)
    # The raw facts are the job-time reference (R-05), not part of the plan a
    # human reads -- and the eligible-entry list is too long to show anyway.
    gate_current = standing.pop("current", None)

    # The plan: computed from the project, never an abstract warning (FR-013).
    try:
        facts = await runner.filing_preview(
            project_name, words=list(resolved.words), vernacular_ws=resolved.vernacular_ws
        )
    except WorkerError as exc:
        return _worker_error_response(exc)
    word_facts = facts.get("words") if isinstance(facts, dict) else None
    missing = (sorted(set(resolved.words) - set(word_facts))
               if isinstance(word_facts, dict) else list(resolved.words))
    if missing:
        # An incomplete answer is not "nothing to delete" for the missing words.
        return error_response(
            "runtime_error",
            f"The preview's read of the project did not answer for {len(missing)} "
            f"word(s) in scope, so no plan can bound them. Nothing was written.",
            error_type="IncompletePreview", missing_words=missing[:20],
        )
    projected = filing_projection.project(word_facts, project_state)
    intent = write_ladder.backup_intent(
        project_name,
        session_state=session_state,
        config_get=_config_get,
        session_key=write_ladder.FILING_BACKUP_KEY,
        once_per_session=False,
        predict_skips=True,
        live_peer=decision.live_peer,
    )
    send_receive = filing_paths.send_receive_status(project_name)
    plan, plan_id = filing_plan.build_plan(
        scope={"kind": scope.kind, "value": scope.value, "limit": scope.limit},
        scope_fingerprint_key=scope_key,
        words_in_scope=len(resolved.words),
        gate=standing,
        projection=projected,
        duplicate_disclosure=filing_plan.duplicate_disclosure(
            baseline_run.get("lines") if baseline_run else None,
            basis=f"prior_run:{baseline_run['run_id']}" if baseline_run else "absent",
        ),
        backup={"outcome": intent.outcome, "reason": intent.reason,
                "peer_caveat": intent.peer_caveat},
        access=_access_block(decision),
        send_receive=send_receive,
        require_write_confirmation=bool(
            _config_get(_REQUIRE_CONFIRMATION_KEY, _REQUIRE_CONFIRMATION_DEFAULT)
        ),
    )

    # (10) FR-005 / FR-006 / R-08 -- confirmation, unconditional and bound.
    issued = session_state.issued_filing_plan(project_name, scope_key)
    bound = (
        request.confirmed
        and request.plan_id is not None
        and issued is not None
        and issued["plan_id"] == request.plan_id
        and plan_id == request.plan_id
    )
    if not bound:
        if not request.confirmed:
            reason = "This is the preview."
        elif request.plan_id is None:
            reason = ("confirmed=true was sent without a plan_id; a confirmation "
                      "must name the plan it confirms.")
        elif issued is None or issued["plan_id"] != request.plan_id:
            reason = ("The plan_id sent was not issued by this session for this "
                      "scope, so this is a new preview.")
        else:
            reason = ("The plan changed since it was previewed (the recomputed plan "
                      "differs), so this is a new preview of what filing would do now.")
        session_state.issue_filing_plan(project_name, scope_key, plan_id, plan, _now_iso())
        return _confirmation_required(plan, plan_id, request, reason=reason)

    # (11) FR-002 rung 3 / FR-030 -- the access GATE, now that it is confirmed.
    if held_by_self and not sharing:
        # L-0: a writable open cannot coexist with our read-only one on a
        # non-shared project, so the worker is released FIRST and access is
        # decided on what remains. Anyone else holding it now is a refusal.
        # On a SHARED project the two coexist (live), so the worker stays.
        from ..parse.worker_client import SHARED_ROLE

        await runner.release_worker(project_name, role=SHARED_ROLE)
        decision = write_ladder.probe_write_access(project_name)
    if decision.refusal is not None:
        return error_response(
            "project_locked",
            f"Project '{project_name}' is held for exclusive access (verdict: "
            f"{decision.verdict}), and filing writes to it. Nothing was written.",
            **decision.refusal,
        )
    if decision.verdict == "unknown":
        # #118: run_module proceeds on `unknown`; filing refuses it -- a
        # disclosed divergence (contracts row 11). Whether FieldWorks holds
        # the project could not be checked, and a write here cannot be undone.
        return error_response(
            "project_drive_unavailable",
            "The FieldWorks projects directory could not be located, so whether "
            "FieldWorks holds this project could not be checked. Filing refuses "
            "rather than write blind. Nothing was written.",
            attempted_path=None,
            hint=_access_block(decision)["remedy"],
        )

    # (12) FR-024 -- the gate again, on the confirmed call. After a self-lock
    # release this re-opens a read worker; it is released again below (FR-027).
    again = await _evaluate_filing_gate(runner, project_name, resolved, scope_key)
    if again.get("status") == "refused":
        return again["refusal"]
    gate_current = again.get("current") or gate_current

    # FR-042 -- the run record lives outside every project folder. Refused
    # here, before the backup and before anything is created.
    from ..parse.record import get_record_dir

    record_root = runner.record_dir or get_record_dir()
    try:
        filing_paths.assert_outside_project(record_root)
    except filing_paths.ArtifactInsideProject as refused:
        return error_response(
            "server_state_error",
            "Filing refused: the run-record directory is inside the FieldWorks "
            "projects directory. Nothing was written.",
            server_state="record_dir_inside_project",
            component="filing",
            state_description=str(refused),
        )

    # (13) FR-007 / FR-008 -- the backup, best-effort, before the writable open.
    backup_block, no_recovery = _take_filing_backup(project_name, decision, send_receive)
    # SC-004: the record holds what was promised beside what happened.
    backup_block["intent"] = plan["backup"]["outcome"]

    # On a non-shared project the read worker is released before the writable
    # open: L-0 showed the two CANNOT hold it at once (FP_FileLockedError;
    # evidence/l0-coexistence.json). Not a flag -- the open would fail.
    # `claims.READS_REFUSED_ON_NON_SHARED_DURING_FILING` governs only whether
    # reads are refused while the run holds the project.
    shared = sharing or decision.verdict == "open_shared"
    if not shared:
        from ..parse.worker_client import SHARED_ROLE

        await runner.release_worker(project_name, role=SHARED_ROLE)

    # (14) FR-003 -- the claim, then the run, then (only now) a run_id.
    token = f"pending-{uuid.uuid4().hex}"
    for _attempt in range(3):
        if filing_claims.acquire(project_name, token, shared=shared) is not None:
            break
        claim = filing_claims.lookup(project_name)
        if claim is not None:
            return _filing_in_progress(claim)
        # The holder released between the two calls: try again.
    else:
        # Never start a job without holding the claim (FR-026).
        return error_response(
            "runtime_error",
            "The filing claim for this project could not be taken. Nothing was written.",
            error_type="FilingClaimUnavailable",
        )
    from ..filing.client import FILING_ROLE
    from ..filing.observer import FilingObserver

    observer = FilingObserver(
        project_name=project_name,
        plan=plan,
        plan_id=plan_id,
        backup=backup_block,
        no_recovery_warning=no_recovery,
        send_receive=send_receive,
        access_verdict=decision.verdict,
        claim_token=token,
    )
    setup = {
        "projection": plan["deletion_projection"]["by_wordform"],
        "overwrites": plan["disapproval_overwrites"]["by_wordform"],
        "gate_reference": gate_current,
    }
    try:
        handle = await runner.start_run(
            project_name=project_name,
            wordforms=list(resolved.words),
            level="file",
            priority=Priority.LOW,
            scope_fingerprint=fingerprint.to_dict(),
            engine_at_submission=engine,
            vernacular_ws=resolved.vernacular_ws,
            project_state=project_state,
            worker_role=FILING_ROLE,
            filing=True,
            filing_setup=setup,
            observer=observer,
            record_guard=filing_paths.assert_outside_project,
        )
    except Exception as exc:  # noqa: BLE001 -- the claim must not outlive a failed start
        filing_claims.release(project_name)
        if isinstance(exc, WorkerError):
            return _worker_error_response(exc)
        raise

    result: Dict[str, Any] = {
        "status": "ok",
        "project": project_name,
        "run_id": handle.run_id,
        "run_started": True,
        "stage": handle.stage.value,
        "words_completed": handle.words_completed,
        "words_total": handle.words_total,
        "scope": {"kind": resolved.scope_kind, "value": resolved.scope_value,
                  "limit": resolved.limit, "truncated": resolved.truncated,
                  "vernacular_ws": resolved.vernacular_ws},
        "scope_fingerprint": fingerprint.to_dict(),
        "engine_at_submission": engine,
        "record_dir": str(handle.record.root),
        "filing": FILING_STARTED,
        "plan_id": plan_id,
        "notes": resolved.notes,
    }
    if backup_block.get("created"):
        result["backup"] = backup_block
    else:
        result["no_recovery_warning"] = no_recovery
        result["backup"] = {"created": False, "reason": backup_block.get("reason")}
    if shared:
        result["shared_mode_advisory"] = filing_wording.SHARED_MODE_ADVISORY
    elif decision.verdict == "stale_lock" and decision.advisory:
        result["stale_lock_advisory"] = decision.advisory.get("note")
    if handle.is_terminal and handle.failure is not None:
        result["failure"] = handle.failure.to_dict()
    result["next_step"] = _status_next_step(handle) or [
        _read_run_rung(handle.run_id, "The filing record: counts, captures, and the backup.")
    ]
    return json_response(build_response_with_context(result))


def _take_filing_backup(project_name: str, decision, send_receive):
    """Row 13: the backup, through run_module's rung (FR-002, FR-007, FR-008).

    Best-effort and never refusing (constitution Principle I). Filing backs up
    before EVERY run -- not once per session, as run_module does -- under its
    own session key, so a run_module backup never satisfies it. A backup root
    that would land inside the projects directory is not written at all
    (FR-042). Returns `(backup_block, no_recovery_warning_or_None)`.
    """
    from .. import backup as backup_mod

    try:
        filing_paths.assert_outside_project(backup_mod.BACKUP_ROOT)
    except filing_paths.ArtifactInsideProject:
        reason = "backup_root_inside_projects_directory"
        return ({"created": False, "reason": reason, "path": None},
                filing_wording.no_recovery_warning(reason, send_receive))
    outcome = write_ladder.take_backup(
        project_name,
        session_state=session_state,
        live_peer=decision.live_peer,
        session_key=write_ladder.FILING_BACKUP_KEY,
        once_per_session=False,
    ) or {"path": None, "created": False, "skipped_reason": "backup_not_attempted"}
    if outcome.get("created"):
        block = {"created": True, "path": outcome.get("path")}
        if outcome.get("note"):
            block["note"] = outcome["note"]
        if filing_paths.treats_as_send_receive(send_receive):
            block["send_receive_note"] = (
                "A local backup is a convenience for this machine, not a way to "
                "revert the shared project."
            )
        return block, None
    reason = outcome.get("skipped_reason") or "reason not recorded"
    return ({"created": False, "reason": reason, "path": None},
            filing_wording.no_recovery_warning(reason, send_receive))


# ---------------------------------------------------------------------------
# flextools_parse_log (CP3, US3)
# ---------------------------------------------------------------------------
#
# READS THE ARTIFACT, NEVER THE ENGINE (FR-024). Nothing in this section
# reaches a worker, a project or a parser: every section is served from the
# run directory on disk. That is also what makes a run from an earlier server
# process as readable as a live one -- the artifact is the thing CP4 and CP5
# read, so it is the thing this tool reads too.
#
# NO SECTION IS EVER EMPTY (FR-028, SC-007). An empty section reads as
# "nothing happened", which for a sandbox-spine section is false (it was
# never run) and for a real section may be false too (the run died before
# its first word). Every response therefore says what it is: real content,
# a typed not-applicable naming the spine and the checkpoint that fills it,
# or an explicit statement of why there is nothing to show.
# ---------------------------------------------------------------------------

#: The spine this checkpoint runs. Named in every not-applicable response.
IN_PROCESS_SPINE = "in_process"

#: The three sandbox-spine sections: what each would hold, and who fills it.
_SANDBOX_SECTIONS: Dict[str, str] = {
    "config_generation": "the HermitCrab configuration generated from the project for a sandboxed run",
    "hc_stdout": "the standard output of a sandboxed HermitCrab process",
    "hc_output": "the output file a sandboxed HermitCrab process writes",
}
SANDBOX_SPINE = "sandbox"
SANDBOX_CHECKPOINT = "CP5"


def _not_applicable(section: str, run_id: str) -> Dict[str, Any]:
    """The typed not-applicable response for a sandbox section (FR-028)."""
    return {
        "status": "ok",
        "run_id": run_id,
        "section": section,
        "applicable": False,
        "reason": "not_applicable_for_this_spine",
        "run_spine": IN_PROCESS_SPINE,
        "section_spine": SANDBOX_SPINE,
        "filled_by": SANDBOX_CHECKPOINT,
        "note": (
            f"This section holds {_SANDBOX_SECTIONS[section]}. This run used "
            f"the {IN_PROCESS_SPINE} spine, where the parser runs inside the "
            f"worker and no such file exists, so the section is not "
            f"applicable -- it is not empty. The {SANDBOX_SPINE} spine that "
            f"produces it arrives at {SANDBOX_CHECKPOINT}."
        ),
    }


#: CP5 (FR-038): each sandbox section's file under `<run>/sandbox/`, and what
#: its empty note calls the missing lines.
_SANDBOX_SECTION_FILES: Dict[str, str] = {
    "config_generation": "generate-config.log",
    "hc_stdout": "hc-stdout.txt",
    "hc_output": "hc-output.txt",
}
_SANDBOX_SECTION_WHAT: Dict[str, str] = {
    "config_generation": "configuration-generation log lines",
    "hc_stdout": "hc console lines",
    "hc_output": "hc result blocks",
}

#: The most characters of one sandbox file served inline, like a trace's
#: `max_trace_chars` default. A longer file is served from its start, marked
#: truncated, with the file's path for the rest.
SANDBOX_LOG_MAX_CHARS = 200_000


def _sandbox_log_section(record, meta, section: str) -> Dict[str, Any]:
    """One sandbox section, served verbatim from the run's `sandbox/` file.

    An empty or never-written file is an explained absence (`_empty_note`),
    never an empty section. `config_generation` also carries the generation
    facts from `meta.sandbox.generation`.
    """
    name = _SANDBOX_SECTION_FILES[section]
    result: Dict[str, Any] = {
        "status": "ok",
        "run_id": record.run_id,
        "section": section,
        "applicable": True,
        "run_spine": SANDBOX_SPINE,
        "source": f"sandbox/{name}",
    }
    text = record.read_sandbox_file(name)
    if text:
        if len(text) > SANDBOX_LOG_MAX_CHARS:
            result["content"] = text[:SANDBOX_LOG_MAX_CHARS]
            result["content_truncated"] = True
            result["content_chars"] = len(text)
            result["source_path"] = str(record.sandbox_path(name))
        else:
            result["content"] = text
    else:
        result["note"] = _empty_note(meta, _SANDBOX_SECTION_WHAT[section])
    if section == "config_generation":
        sandbox = meta.sandbox if isinstance(meta.sandbox, dict) else {}
        generation = sandbox.get("generation") if isinstance(sandbox.get("generation"), dict) else {}
        load_errors = list(generation.get("load_errors") or [])
        result["reused_cache"] = generation.get("reused_cache")
        result["load_error_count"] = int(generation.get("load_error_count") or len(load_errors))
        result["load_errors"] = load_errors
    return result


def _log_record(run_id: str):
    """The run's on-disk record, or None if no such run exists."""
    from ..parse.record import RunRecord, is_valid_run_id

    if not is_valid_run_id(run_id):
        return None
    runner = _runner
    record_dir = runner.record_dir if runner is not None else None
    record = RunRecord(run_id, record_dir=record_dir)
    return record if record.exists() else None


def _run_not_found(run_id: str) -> List[TextContent]:
    from ..parse.record import list_run_ids

    runner = _runner
    known = list(runner.known_run_ids()) if runner is not None else []
    record_dir = runner.record_dir if runner is not None else None
    on_disk = [r for r in list_run_ids(record_dir) if r not in known]
    available = known + on_disk[:20]
    return error_response(
        "parse_run_not_found",
        f"No parse run with handle {run_id!r}.",
        run_id=run_id,
        available_runs=available,
        hint=(
            "Run handles are issued by flextools_parse_text and "
            "flextools_try_word, and their records stay on disk (the newest 20 "
            "per project). "
            + (f"Runs with records: {', '.join(available)}." if available
               else "No run records exist yet.")
        ),
    )


#: `server_state` for a run record whose meta.json exists but stays
#: unreadable (pattern audit sweep 6): transient, never "not found".
RUN_RECORD_UNREADABLE = "run_record_unreadable"


def _run_record_unreadable(
    run_id: str, exc: BaseException, *, tool: str, args: Dict[str, Any]
) -> List[TextContent]:
    """A run record that exists but could not be read: retry, not absence.

    `RunRecord.read_meta_strict` already retried briefly before raising
    `MetaUnreadable`; on Windows this is usually a virus scanner or indexer
    holding meta.json. The record is intact, so the answer is the same call
    again in a moment -- never `parse_run_not_found` or "not applicable".
    """
    return error_response(
        "server_state_error",
        f"Run {run_id}'s record exists but could not be read just now. "
        "Nothing was changed.",
        server_state=RUN_RECORD_UNREADABLE,
        component="parse_record",
        state_description=str(exc),
        hint=(
            "Another process (often a virus scanner or search indexer) is holding "
            "the run's meta.json. The record is intact; retry in a moment."
        ),
        next_step=[
            _rung(
                action="Retry the same call in a moment.",
                tool=tool,
                args=args,
                rationale="The record exists; the read failure is transient.",
                est_cost="instant",
            )
        ],
    )


def _page(items: List[Any], offset: int, limit: int) -> Dict[str, Any]:
    page = items[offset:offset + limit]
    return {
        "total": len(items),
        "offset": offset,
        "returned": len(page),
        "items": page,
        "next_offset": offset + len(page) if offset + len(page) < len(items) else None,
    }


def _empty_note(meta, what: str) -> str:
    """Why a real section has nothing to show -- never left unexplained."""
    if meta is None:
        return f"No {what} are recorded for this run."
    stage = meta.stage
    if meta.failure:
        where = (meta.failure or {}).get("stage_at_failure") or stage
        return (
            f"No {what} are recorded: the run failed during {where!r} before "
            f"completing a word."
        )
    if stage in ("starting", "loading_grammar"):
        return f"No {what} yet: the run is still in {stage!r}."
    return f"No {what} are recorded for this run (stage {stage!r})."


# The session's drill-down budget (FR-047, SC-016). A user-chosen figure in
# 10-20, set once by the first report request that names one; later requests
# read the same budget, so a session cannot be walked past its cap by asking
# again. Nothing traces automatically -- the budget bounds what the report
# RECOMMENDS, and every trace remains one flextools_try_word call for one word.
_drill_down: Optional["DrillDownBudget"] = None  # noqa: F821


def _drill_down_budget(cap: Optional[int]):
    """The session's budget, created on the first request that names a cap."""
    global _drill_down
    if _drill_down is None and cap is not None:
        from ..signals.clustering import DrillDownBudget

        _drill_down = DrillDownBudget(int(cap))
    return _drill_down


def reset_drill_down() -> None:
    """Forget the session's drill-down budget (tests; a new session)."""
    global _drill_down
    _drill_down = None


async def handle_flextools_parse_log(args: dict) -> List[TextContent]:
    """Serve one section of a run's artifact (FR-028, FR-029).

    Read-only. Starts nothing and never calls the engine check (FR-024).
    """
    run_id = str(args.get("run_id") or "")
    section = str(args.get("section") or "summary")
    offset = int(args.get("offset") or 0)
    limit = int(args.get("limit") or 50)

    if section in _SANDBOX_SECTIONS:
        # Answered for any existing run: whether the section applies is a
        # fact about the RECORDED spine (never the section name, never the
        # presence of a file), not about how far the run got.
        record = _log_record(run_id)
        if record is None:
            return _run_not_found(run_id)
        try:
            meta = record.read_meta_strict()
        except MetaUnreadable as exc:
            return _run_record_unreadable(run_id, exc, tool="flextools_parse_log", args=dict(args))
        if meta is not None and meta.effective_spine == SANDBOX_SPINE:
            return json_response(build_response_with_context(
                _sandbox_log_section(record, meta, section)
            ))
        return json_response(build_response_with_context(_not_applicable(section, run_id)))

    record = _log_record(run_id)
    if record is None:
        return _run_not_found(run_id)
    try:
        meta = record.read_meta_strict()
    except MetaUnreadable as exc:
        return _run_record_unreadable(run_id, exc, tool="flextools_parse_log", args=dict(args))

    result: Dict[str, Any] = {"status": "ok", "run_id": run_id, "section": section,
                              "applicable": True}

    if section == "summary":
        from dataclasses import asdict

        summary = asdict(meta) if meta is not None else {}
        summary["results_recorded"] = record.result_count()
        summary["traces_recorded"] = sorted(_trace_indices(record))
        summary["run_spine"] = meta.effective_spine if meta is not None else IN_PROCESS_SPINE
        if meta is not None and meta.words_path is not None:
            # A batch run: the US5 report, computed from the artifact alone.
            from ..signals.report import build_report

            summary["report"] = build_report(
                record.iter_results(),
                meta.project_state,
                budget=_drill_down_budget(args.get("drill_down_cap")),
                offset=offset,
                limit=limit,
            )
        if summary.get("engine_changed_midjob"):
            summary["warnings"] = [
                "The project's active parser changed while this run was going. "
                "Its results are labelled with the engine it was submitted on."
            ]
        result["content"] = summary

    elif section == "words":
        words = record.read_words()
        source = "words.txt"
        if words is None:
            # A single-word run writes no word list (an empty one would read
            # as "resolved to nothing"); its words are its result lines.
            words = [line.get("wordform") for line in record.iter_results()]
            source = "results.jsonl (this run has no resolved word list)"
        result["source"] = source
        result.update(_page(words, offset, limit))
        if not words:
            result["note"] = _empty_note(meta, "words")

    elif section == "results":
        lines = list(record.iter_results())
        result.update(_page(lines, offset, limit))
        if not lines:
            result["note"] = _empty_note(meta, "results")

    elif section == "deletions":
        # CP4 (FR-031, FR-041): a filing run's captures, read from disk like
        # every other section. A read-only run has none to have: it is
        # reported not applicable -- never as an empty section (FR-028).
        if meta is None or not meta.filing:
            result = {
                "status": "ok", "run_id": run_id, "section": section,
                "applicable": False, "reason": "not_applicable_for_this_run",
                "note": (
                    "This section holds a filing run's pre-deletion captures -- "
                    "filing runs only. This run was read-only: it filed nothing, so "
                    "nothing was captured. It is not applicable, not empty."
                ),
            }
        else:
            lines = list(record.iter_jsonl(filing_paths.DELETIONS_RELPATH))
            result.update(_page(lines, offset, limit))
            if not lines:
                result["note"] = (
                    "No analysis was captured: this filing run deleted nothing and "
                    "overwrote no human disapproval (or stopped before its first "
                    "word -- see the summary's filing block)."
                )

    else:  # trace
        result.update(_trace_section(record, args, meta))

    return json_response(build_response_with_context(result))


def _trace_indices(record) -> List[int]:
    if not record.traces_dir.is_dir():
        return []
    indices = []
    for path in record.traces_dir.glob("*.xml"):
        if path.stem.isdigit():
            indices.append(int(path.stem))
    return indices


def _trace_section(record, args: dict, meta) -> Dict[str, Any]:
    """One trace: a one-line reading if it parses, the raw slice if not (FR-029)."""
    available = sorted(_trace_indices(record))
    if not available:
        return {
            "available_traces": [],
            "note": (
                "No trace was recorded for this run. Traces are written only "
                "where a drill-down was taken; a batch is never traced in bulk."
            ),
        }
    index = args.get("trace_index")
    if index is None:
        index = available[0]
    index = int(index)
    if index not in available:
        return {
            "available_traces": available,
            "trace_index": index,
            "note": f"No trace was recorded for word {index}. Traces exist for: {available}.",
        }
    xml = record.read_trace(index) or ""
    cap = int(args.get("max_trace_chars") or 20000)
    out: Dict[str, Any] = {"available_traces": available, "trace_index": index,
                           "trace_path": f"traces/{index}.xml",
                           "trace_chars": len(xml)}
    reading = summarize_trace_xml(xml)
    if reading is None:
        # FR-029: returned raw, labelled raw, nothing invented about it.
        out["format"] = "raw"
        out["raw"] = xml[:cap]
        out["raw_truncated"] = len(xml) > cap
        out["note"] = (
            "This trace could not be read as a parser trace document, so it is "
            "returned exactly as recorded and labelled raw. No explanation is "
            "offered for output this tool could not read."
        )
    else:
        out["format"] = "parsed"
        out.update(reading)
    return out


def summarize_trace_xml(xml: str) -> Optional[Dict[str, Any]]:
    """A one-line reading of a HermitCrab trace, or None if it is unreadable.

    Reads only what the trace states (FwXmlTraceManager.cs): `FailureReason`
    elements and their `type`, the rule element beside each one, and the
    `ParseCompleteTrace` successes. It names the most frequent rejection and
    where it first occurred; it does not guess at a cause the trace does not
    record. A document that is not XML, or not a trace, returns None and the
    caller labels it raw (FR-029).
    """
    import xml.etree.ElementTree as ET
    from collections import Counter

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    traces = [e for e in root.iter() if e.tag.endswith("Trace")]
    if not traces and root.tag != "Wordform":
        return None

    parent = {child: node for node in root.iter() for child in node}
    reasons = []
    for element in root.iter("FailureReason"):
        owner = parent.get(element)
        rule = None
        if owner is not None:
            for sibling in owner:
                if sibling.tag.endswith("Rule") and (sibling.text or "").strip():
                    rule = sibling.text.strip()
                    break
        reasons.append({
            "type": element.get("type") or "unspecified",
            "stage": owner.tag if owner is not None else None,
            "rule": rule,
        })
    successes = sum(
        1 for e in root.iter("ParseCompleteTrace") if (e.get("success") or "").lower() == "true"
    )
    analyses = sum(1 for e in root if e.tag == "Analysis")

    if not reasons:
        line = (
            f"The trace records {successes} successful parse path(s) and no "
            f"rejection reason."
        )
        return {"summary_line": line, "rejections": 0, "successful_paths": successes,
                "analyses": analyses, "rejections_by_type": {}}

    counts = Counter(r["type"] for r in reasons)
    top_type, top_count = counts.most_common(1)[0]
    first = next(r for r in reasons if r["type"] == top_type)
    where = []
    if first["rule"]:
        where.append(f"rule {first['rule']!r}")
    if first["stage"]:
        where.append(first["stage"])
    line = (
        f"The trace records {len(reasons)} rejection(s); the most frequent is "
        f"'{top_type}' ({top_count})"
        + (f", first at {' in '.join(where)}" if where else "")
        + "."
    )
    return {
        "summary_line": line,
        "rejections": len(reasons),
        "rejections_by_type": dict(counts),
        "first_of_most_frequent": first,
        "successful_paths": successes,
        "analyses": analyses,
    }


# ---------------------------------------------------------------------------
# flextools_parse_diff (CP3, US4)
# ---------------------------------------------------------------------------


def _probe_access(project_name: Optional[str]):
    """The shared-mode probe (FR-034, R-06). Never fails the comparison.

    Reads a lock file's metadata only; it opens no project and does not
    touch the engine, which is why FR-024 permits it here.
    """
    if not project_name:
        return None
    try:
        try:
            from ..project_access import probe_project_access
        except (ImportError, ValueError):
            from server.project_access import probe_project_access
        return probe_project_access(project_name)
    except Exception:  # noqa: BLE001 -- an unknown access state is not a failure
        return None


async def handle_flextools_parse_diff(args: dict) -> List[TextContent]:
    """Compare two runs: fixed, broken, changed, unchanged (FR-030).

    Read-only. Reads two run records; never reaches a worker or the engine
    check (FR-024).
    """
    from ..parse.diff import RunNotComparable, compare_runs
    from ..parse.fingerprint import ScopeMismatch

    baseline_id = str(args.get("baseline_run_id") or "")
    current_id = str(args.get("current_run_id") or "")
    force = bool(args.get("force"))

    baseline = _log_record(baseline_id)
    if baseline is None:
        return _run_not_found(baseline_id)
    current = _log_record(current_id)
    if current is None:
        return _run_not_found(current_id)

    current_meta = current.read_meta()
    access = _probe_access(current_meta.project_name if current_meta else None)

    try:
        comparison = compare_runs(baseline, current, force=force, access=access)
    except ScopeMismatch as refused:
        detail = dict(refused.detail)
        detail.pop("error_code", None)
        return error_response("parse_scope_mismatch", detail.get("hint") or str(refused), **detail)
    except RunNotComparable as exc:
        return error_response("runtime_error", str(exc), reason="not_a_batch_run")

    result: Dict[str, Any] = {"status": "ok"}
    result.update(comparison.to_dict())
    return json_response(build_response_with_context(result))


# ---------------------------------------------------------------------------
# flextools_parse_status
# ---------------------------------------------------------------------------


def _live_run_not_found(runner, run_id: str) -> List[TextContent]:
    """`parse_run_not_found` for a handle this server process does not hold.

    Shared by `flextools_parse_status` and `flextools_parse_cancel`: both act
    on the LIVE run (a cancel cannot reach a run from an earlier server
    process -- nothing is executing it any more).
    """
    available = runner.known_run_ids()
    return error_response(
        "parse_run_not_found",
        f"No parse run with handle {run_id!r}.",
        run_id=run_id,
        # Named, not counted. A handle is an opaque 32-character string;
        # told only that theirs is wrong, a caller cannot tell a typo
        # from a run this server has forgotten (FR-035).
        available_runs=available,
        hint=(
            "Handles are issued by flextools_try_word when a parse "
            "outlives the grace window, and by flextools_parse_text for "
            "every batch; they live as long as this server process does. "
            + (
                f"Runs this server knows about: {', '.join(available)}."
                if available
                else "This server has no runs at all, so the handle is "
                "either from an earlier server process or mistyped."
            )
        ),
    )


async def handle_flextools_parse_status(args: dict) -> List[TextContent]:
    """Report on a parse run by its handle (FR-033 .. FR-036).

    Read-only. Starts nothing, cancels nothing, and touches no parser.

    THE ONE ASYMMETRY THAT IS EASY TO IMPLEMENT BACKWARDS. A terminal
    `failed` or `cancelled` run is reported as a **SUCCESSFUL response**.
    Asking about a dead run is a successful query, not a failed request: the
    run's death is a fact about the run, and reporting it as an error would
    conflate "your question was wrong" with "the thing you asked about went
    wrong". A caller polling a batch would then see their poll fail rather
    than learn that their batch did.

    So `parse_run_not_found` is the ONLY refusal this tool issues -- for a
    handle corresponding to no run at all, which is the one case where the
    request itself is wrong (FR-035).

    `parse_job_cancelled` does **not** fire here. It is for something trying
    to ACT on a run that has already ended; asking about one is not acting
    on it. Both directions are tested.

    Args:
        args: validated `ParseStatusInput` dump -- a single `run_id`.

    Returns:
        The run's stage, progress and outcome, or `parse_run_not_found`.
    """
    run_id = str(args.get("run_id") or "")
    runner = get_runner()
    handle = runner.get(run_id)

    if handle is None:
        return _live_run_not_found(runner, run_id)

    result: Dict[str, Any] = {
        "status": "ok",
        "run_id": handle.run_id,
        "project": handle.project_name,
        "stage": handle.stage.value,
        "words_completed": handle.words_completed,
        "words_total": handle.words_total,
        # The run currently occupying the worker, or null. Without it a
        # batch paused by an urgent word looks stalled, and SC-009's
        # "reported progress accounts for the interleave" has no observable
        # (data-model.md section 1).
        "interleaved_by": handle.interleaved_by,
    }

    # CP3: a batch's fingerprint, engine, counters and warnings. Empty for a
    # single-word run, so CP2b's response is unchanged.
    result.update(_batch_block(handle))
    if handle.interleaved_by:
        # FR-026: progress that has paused says why, rather than stalling.
        result["progress_note"] = (
            f"Paused behind run {handle.interleaved_by}, a more urgent request "
            f"on the same grammar. This run resumes at its next word with its "
            f"position intact; {handle.words_pending} word(s) remain."
        )

    if handle.stage is RunStage.COMPLETED:
        result["result_summary"] = _result_summary(handle)
    elif handle.stage is RunStage.FAILED and handle.failure is not None:
        # Reported, not raised. The run failed; the question did not.
        result["failure"] = handle.failure.to_dict()

    sandbox = _sandbox_meta_of(handle)
    if sandbox is not None:
        # CP5 (SC-008, data-model 6.6): where a sandbox run stopped, and its
        # summary on every terminal stage -- a failed run's words are real.
        result["spine"] = SANDBOX_SPINE
        failure = handle.failure
        if (handle.stage is RunStage.FAILED and failure is not None
                and failure.error_code == "parser_timeout"):
            hc = sandbox.get("hc") if isinstance(sandbox.get("hc"), dict) else {}
            result["in_flight"] = hc.get("in_flight_word")
            result["in_flight_index"] = hc.get("in_flight_index")
        if handle.is_terminal:
            summary = result.get("result_summary") or _result_summary(handle)
            summary.update(_sandbox_summary_block(handle, sandbox))
            result["result_summary"] = summary
    elif handle.stage is RunStage.CANCELLED:
        # `words_completed` above is the count that survived, and the stage
        # at cancel says where it stopped (FR-036). The partial results are
        # on disk and readable (FR-029).
        result["state_at_cancel"] = handle.stage_at_cancel
        result["partial_results_available"] = handle.words_completed > 0

    result["next_step"] = _status_next_step(handle)
    return json_response(build_response_with_context(result))


# ---------------------------------------------------------------------------
# flextools_parse_cancel (CP4, FR-034; M-3)
# ---------------------------------------------------------------------------

#: What a cancelled FILING run tells its caller (FR-034). Filed words stay
#: filed; the only way back is the backup, or for a Send/Receive project the
#: discard-and-re-download route.
FILING_CANCEL_NOTE = (
    "Cancellation stops the run at its next word boundary. Every word filed "
    "before that stays filed: filing cannot be undone except by restoring the "
    "backup (or, for a project in Send/Receive, by discarding this copy and "
    "re-downloading it). The run's record lists exactly which words were filed."
)


async def handle_flextools_parse_cancel(args: dict) -> List[TextContent]:
    """Ask a run to stop at its next word boundary (FR-034).

    A thin tool over `ParseRunner.cancel_run`, which existed from CP2b with
    no caller. It works on read-only runs too -- the runner always supported
    that; this only exposes it. Writes nothing to the project.

      * an unknown handle             -> `parse_run_not_found`;
      * a run that has already ended  -> `parse_job_cancelled`;
      * otherwise                     -> `{run_id, cancel_requested: true}`,
        returned at once. The run is `cancelled` only when the worker has
        actually stopped, which `flextools_parse_status` reports.
    """
    from ..parse.runner import RunAlreadyTerminal

    run_id = str(args.get("run_id") or "")
    runner = get_runner()
    try:
        handle = await runner.cancel_run(run_id)
    except RunAlreadyTerminal as ended:
        detail = dict(ended.detail)
        detail.pop("error_code", None)
        return error_response("parse_job_cancelled", detail.get("hint") or str(ended), **detail)
    if handle is None:
        return _live_run_not_found(runner, run_id)

    result: Dict[str, Any] = {
        "status": "ok",
        "run_id": handle.run_id,
        "cancel_requested": True,
        "stage": handle.stage.value,
        "words_completed": handle.words_completed,
        "words_total": handle.words_total,
        "note": (
            "The run will stop at its next word boundary; the word in flight "
            "finishes first. Poll flextools_parse_status for 'cancelled'."
        ),
        "next_step": [
            _rung(
                action="Poll this run until it reports 'cancelled'.",
                tool="flextools_parse_status",
                args={"run_id": handle.run_id},
                rationale="Cancellation is cooperative: it lands at a word boundary.",
                est_cost="instant",
            )
        ],
    }
    if getattr(handle, "is_filing", False):
        result["filing_note"] = FILING_CANCEL_NOTE
    return json_response(build_response_with_context(result))


# ---------------------------------------------------------------------------
# flextools_parse_sandbox (CP5, FR-034) -- check order (contracts/tools.md s.3)
# ---------------------------------------------------------------------------
#
# ONE HELPER PER CHECK-ORDER STEP. Each takes the request's `_SandboxPlan`,
# returns `None` to continue or a finished refusal envelope, and may record
# what it learnt on the plan for the steps after it. The handler runs them in
# order and returns the first refusal.
#
#   1  project            `_sandbox_resolve_project`
#   2  config source      `_sandbox_resolve_source` (name, existence)
#   2b word list          `_sandbox_read_words`     (parse; FR-014, FR-015)
#   3  tool discovery     `_sandbox_check_tools`    (FR-007)
#   4  engine check       `_sandbox_engine_check`   (generation only; FR-036)
#   5  access probe       `_sandbox_access`         (never refuses; R-13)
#   6  corpus load        (run_corpus -- US4)
#   7  free space         `_sandbox_space_check`    (cache miss only; FR-012)
#   8  the run            `_sandbox_start_parse`    (run id exists from here)
#
# NOTHING BEFORE STEP 8 CREATES A FILE: no copy, no mkdir under the sandbox
# root, no `sandbox.paths.work_dir`, no subprocess beyond the two discovery
# functions (T029's `untouched_root`).
#
# Discovery, the engine check and the access probe are looked up AT CALL
# TIME (module attributes, never names imported into this module), so the
# tests' patches -- and any later override -- are honoured.
# ---------------------------------------------------------------------------

import re  # noqa: E402
import unicodedata  # noqa: E402
from collections import Counter  # noqa: E402
from dataclasses import dataclass, field as dc_field  # noqa: E402
from pathlib import Path  # noqa: E402

from .. import parser_probe  # noqa: E402 -- grouped with the CP5 section it serves
from ..response_models import (  # noqa: E402
    ParserToolMissingDetail,
    ParseSandboxRefusedDetail,
)
from ..sandbox import paths as sandbox_paths  # noqa: E402

#: contracts/tools.md section 4, verbatim: the command, one space, one sentence.
HC_INSTALL_HINT = (
    "dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool Installing it "
    "needs a .NET SDK, and hc 3.8 and later need the .NET 10 runtime to run."
)
GENERATE_HC_CONFIG_INSTALL_HINT = (
    "GenerateHCConfig.exe ships with FieldWorks 9; repair or reinstall FieldWorks."
)
#: Fallback `expected_path` when discovery reports none (the field is a str).
_GENERATE_HC_CONFIG_DEFAULT_PATH = (
    r"C:\Program Files\SIL\FieldWorks 9\GenerateHCConfig.exe"
)

#: contracts/tools.md section 5.1: fixed text, on every parse response (US2).
SANDBOX_RESULTS_LABEL = (
    "These are the sandbox's results from an exported copy of the grammar, not "
    "the project's own parser results."
)

#: R-13: the access verdicts that make a sandbox run's staleness unverifiable.
#: Wider than `diff.shared_mode_active` on purpose (held_by_other too); the
#: in-process rule is left unchanged. Exception: a `held_by_other` whose holder
#: is this server's own read worker is not stale (`_sandbox_access`).
SANDBOX_STALENESS_VERDICTS = frozenset({"open_shared", "open_exclusive", "held_by_other"})

#: The one engine the sandbox spine runs (R-14: recorded in the fingerprint).
SANDBOX_ENGINE = "HC"

#: FR-014: a word list that arrives as one string is split on this, verbatim.
_WORD_SPLIT_RE = re.compile(r"[,\s]+")

#: contracts/tools.md section 5.1, advisory codes and their fixed notes.
_ADVISORY_NOTES = {
    "hc_engine_version_skew": (
        "hc uses HermitCrab {a}; FieldWorks bundles {b}. Results may differ from "
        "FLEx's own parser."
    ),
    "sandbox_predates_project_grammar": (
        "This sandbox was made from an earlier state of the project's grammar; it "
        "was used exactly as it is."
    ),
    "grammar_load_errors": (
        "{n} grammar objects failed to load during export and are missing from "
        "this configuration."
    ),
    "leading_dash_unverified": (
        "These words begin with '-'. Whether hc receives such a word intact has "
        "not been verified; treat their results with care."
    ),
}

#: Terminal failure codes re-emitted as their own envelopes (section 3, step 8).
_SANDBOX_FAILURE_CODES = ("parser_timeout", "parser_job_failed", "parser_config_failed")



@dataclass
class _SandboxPlan:
    """What the check-order steps learn, handed forward to the run."""

    request: ParseSandboxInput
    project_name: Optional[str] = None
    #: FR-015-ordered words (parse), and what the ordering recorded.
    words: List[str] = dc_field(default_factory=list)
    word_count: int = 0
    scope_value: List[str] = dc_field(default_factory=list)
    truncated: bool = False
    hc: Any = None
    generator: Any = None
    project_state: Dict[str, Any] = dc_field(default_factory=dict)
    staleness: Optional[str] = None
    #: The named sandbox's store status (US3): edited / predates, or None.
    sandbox_status: Optional[Dict[str, Any]] = None
    #: run_corpus (US4): the loaded `store.Corpus`, after step 6.
    corpus: Any = None


def _sandbox_role() -> str:
    """`sandbox.client.SANDBOX_ROLE`, or its value while the client is unbuilt."""
    try:
        from ..sandbox import client as sandbox_client
    except ImportError:
        return "sandbox"
    return getattr(sandbox_client, "SANDBOX_ROLE", "sandbox")


def _sandbox_detail_kwargs(model) -> Dict[str, Any]:
    """A detail model as `error_response` kwargs, in the model's field order."""
    detail = model.model_dump()
    detail.pop("error_code", None)
    return detail


def _sandbox_list_rung(project_name: Optional[str]) -> Dict[str, Any]:
    return _rung(
        action="See the sandboxes and corpora that exist for this project.",
        tool="flextools_parse_sandbox",
        args={"action": "list", "project_name": project_name},
        rationale="Lists existing sandbox and corpus names; nothing is created.",
        est_cost="instant",
    )


def _sandbox_refused(
    reason: str,
    message: str,
    *,
    hint: str,
    next_step: List[Dict[str, Any]],
    name: Optional[str] = None,
    path: Optional[str] = None,
    needed_bytes: Optional[int] = None,
    free_bytes: Optional[int] = None,
) -> List[TextContent]:
    """`parse_sandbox_refused`, fields in contract order, with a next_step."""
    detail = ParseSandboxRefusedDetail(
        reason=reason,
        name=name,
        path=path,
        hint=hint,
        needed_bytes=needed_bytes,
        free_bytes=free_bytes,
    )
    return error_response(
        "parse_sandbox_refused",
        message,
        **_sandbox_detail_kwargs(detail),
        next_step=next_step,
    )


def _ensure_next_step(
    envelope: List[TextContent], rungs: List[Dict[str, Any]]
) -> List[TextContent]:
    """Re-emit `envelope` with `next_step` added when it has none.

    `_resolve_project` is shared with tools whose refusals predate the
    "every refusal carries a next_step" rule; this tool's contract requires
    one, so it is added here rather than changing the shared helper.
    """
    try:
        data = json.loads(envelope[0].text)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
        return envelope
    if data.get("next_step"):
        return envelope
    code = data.get("error_code") or "runtime_error"
    message = data.get("message") or ""
    extra = {
        k: v
        for k, v in data.items()
        if k not in ("_contract", "status", "error_code", "message", "error")
    }
    extra["next_step"] = rungs
    return error_response(code, message, **extra)


# -- step 1 ----------------------------------------------------------------


def _sandbox_resolve_project(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    """Step 1: resolve the project (every action)."""
    name, refusal = _resolve_project(plan.request.project_name)
    if refusal is None:
        plan.project_name = name
        return None
    return _ensure_next_step(
        refusal,
        [
            _rung(
                action="List the projects this machine has, then retry with an exact name.",
                tool="flextools_list_projects",
                args=None,
                rationale="The project named could not be resolved to one project.",
                est_cost="instant",
            )
        ],
    )


# -- step 1b: the sandbox root is outside every project (FR-042) -------------


def _sandbox_check_root(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    """Refuse early when the sandbox root resolves inside a project folder.

    Every action reads or writes under the root, and `paths.sandbox_root()`
    raises `ArtifactInsideProject` there. Surfaced the way CP4's filing path
    surfaces a record directory inside a project: `server_state_error`, with
    a `server_state` naming what is misplaced -- before anything is created.
    """
    try:
        sandbox_paths.sandbox_root()
    except filing_paths.ArtifactInsideProject as refused:
        return error_response(
            "server_state_error",
            "The parse sandbox root is inside the FieldWorks projects directory, "
            "so the sandbox spine refuses to run. Nothing was created.",
            server_state="sandbox_root_inside_project",
            component="sandbox",
            state_description=str(refused),
            hint=(
                f"Point {sandbox_paths.ENV_VAR} at a folder outside the FieldWorks "
                "projects directory (or unset it to use the default), then retry."
            ),
            next_step=[
                _rung(
                    action=f"Move {sandbox_paths.ENV_VAR} outside the projects directory.",
                    tool=None,
                    args=None,
                    rationale=(
                        "Sandbox files inside a project folder would be committed by "
                        "Send/Receive (FR-042)."
                    ),
                    est_cost="minutes",
                )
            ],
        )
    return None


# -- step 2 ----------------------------------------------------------------


def _sandbox_name_refusal(name: object, detail: str, project_name) -> List[TextContent]:
    return _sandbox_refused(
        "name_invalid",
        f"Invalid sandbox name {name!r}: {detail}.",
        name=name if isinstance(name, str) else None,
        hint=(
            f"Sandbox names {detail}. Pick a name of letters, digits, '.', '_' "
            "or '-' and retry."
        ),
        next_step=[_sandbox_list_rung(project_name)],
    )


def _sandbox_config_path(project_name: str, name: str) -> Path:
    """`sandboxes/<project>/<name>/hc-config.xml`. Computes; creates nothing."""
    return sandbox_paths.sandbox_dir(project_name, name) / "hc-config.xml"


def _sandbox_resolve_source(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    """Step 2: resolve the config source.

    A named sandbox (parse / run_corpus) must have a valid name and exist; the
    NEW sandbox's name (create_sandbox) must be valid and not exist. No
    sandbox means the project's cached config, which needs no check here.
    Existence is a `stat` of the sandbox's `hc-config.xml` -- nothing is
    created. For a named run the store's status (`edited`,
    `predates_project_grammar`, both derived by `stat` alone) is recorded on
    the plan; a status that cannot be read never refuses the run.
    """
    request, project_name = plan.request, plan.project_name
    if request.sandbox is None:
        if request.action == "create_sandbox":
            return _sandbox_name_refusal(
                None, sandbox_paths.validate_name(None) or "a name is required",
                project_name,
            )
        return None
    detail = sandbox_paths.validate_name(request.sandbox)
    if detail is not None:
        return _sandbox_name_refusal(request.sandbox, detail, project_name)
    config = _sandbox_config_path(project_name, request.sandbox)
    exists = config.is_file()
    if request.action == "create_sandbox":
        if exists:
            return _sandbox_refused(
                "sandbox_exists",
                f"A sandbox named {request.sandbox!r} already exists for this project.",
                name=request.sandbox,
                path=str(config),
                hint="Pick a new name, or parse against the existing sandbox.",
                next_step=[_sandbox_list_rung(project_name)],
            )
        return None
    if not exists:
        return _sandbox_refused(
            "sandbox_not_found",
            f"No sandbox named {request.sandbox!r} exists for this project.",
            name=request.sandbox,
            path=str(config),
            hint=(
                "Create it with action='create_sandbox', pick an existing name, or "
                "omit sandbox to parse against the project's cached config."
            ),
            next_step=[_sandbox_list_rung(project_name)],
        )
    plan.sandbox_status = _sandbox_store_status(project_name, request.sandbox)
    return None


def _sandbox_store():
    """`sandbox.store`, imported at call time (tests stand a fake in)."""
    from ..sandbox import store as sandbox_store

    return sandbox_store


def _sandbox_store_status(project_name: str, name: str) -> Optional[Dict[str, Any]]:
    try:
        status = _sandbox_store().sandbox_status(project_name, name)
    except Exception:  # noqa: BLE001 -- a status read never refuses a run
        return None
    return status if isinstance(status, dict) else None


# -- step 2b: the word list (parse) -----------------------------------------


def _word_file_refusal(message: str, path: str, hint: str, project_name) -> List[TextContent]:
    return _sandbox_refused(
        "word_file_invalid",
        message,
        path=path,
        hint=hint,
        next_step=[
            _rung(
                action="Pass the words inline with `words` instead of a file.",
                tool="flextools_parse_sandbox",
                args={"action": "parse", "project_name": project_name},
                rationale=(
                    "An inline list needs no file; a file must be UTF-8, one word "
                    "per line, outside every project folder."
                ),
                est_cost="seconds",
            )
        ],
    )


def _sandbox_raw_words(plan: _SandboxPlan):
    """The words as supplied (FR-014), or a refusal envelope."""
    request = plan.request
    if request.word_file is not None:
        path = request.word_file
        try:
            filing_paths.assert_outside_project(path)
        except filing_paths.ArtifactInsideProject:
            return None, _word_file_refusal(
                "The word file is inside a FieldWorks project folder.",
                path,
                "Move the word file outside the FieldWorks projects directory "
                "and retry; the sandbox never reads from a project folder.",
                plan.project_name,
            )
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return None, _word_file_refusal(
                "The word file is not valid UTF-8.",
                path,
                "Save the word file as UTF-8, one word per line, and retry.",
                plan.project_name,
            )
        except OSError:
            return None, _word_file_refusal(
                "The word file could not be read.",
                path,
                "Check the path exists and is a readable file, then retry.",
                plan.project_name,
            )
        return [line.strip() for line in text.splitlines()], None
    words = request.words
    if isinstance(words, str):
        return _WORD_SPLIT_RE.split(words), None
    return list(words or []), None


def _sandbox_read_words(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    """FR-015: NFC, count within the list, order `(-count, word)`, then limit.

    An EMPTY list -- from `words` or `word_file` -- is refused here as
    `word_file_invalid` (the closed enum's only word-list reason): the input
    model cannot see a file's contents, and one rule for both sources is the
    simpler one to state.
    """
    if plan.request.action != "parse":
        return None
    raw, refusal = _sandbox_raw_words(plan)
    if refusal is not None:
        return refusal
    counts: Counter = Counter()
    for word in raw:
        form = unicodedata.normalize("NFC", str(word or ""))
        if form.strip():
            counts[form] += 1
    if not counts:
        source = plan.request.word_file
        return _word_file_refusal(
            "The word list is empty.",
            source,
            "Give at least one word: a list, a comma- or space-separated string, "
            "or a UTF-8 file with one word per line.",
            plan.project_name,
        )
    ordered = sorted(counts, key=lambda w: (-counts[w], w))
    plan.word_count = len(ordered)
    plan.scope_value = sorted(counts)
    limit = plan.request.limit
    plan.truncated = limit is not None and len(ordered) > limit
    plan.words = ordered[:limit] if plan.truncated else ordered
    return None


# -- step 3 ----------------------------------------------------------------


def _sandbox_generation_may_run(request: ParseSandboxInput) -> bool:
    """GenerateHCConfig.exe is needed only when generation may run (FR-007)."""
    return request.action == "create_sandbox" or request.sandbox is None


def _tool_missing_rungs(component: str) -> List[Dict[str, Any]]:
    install = (
        "Install hc with the dotnet tool command in install_hint, then retry."
        if component == "hc"
        else "Repair or reinstall FieldWorks 9, then retry."
    )
    return [
        _rung(
            action=install,
            tool=None,
            args=None,
            rationale=(
                f"{component} is required for this action and was not found or "
                "could not start. Nothing was copied or created."
            ),
            est_cost="minutes",
        ),
        _rung(
            action="Check the sandbox components' status.",
            tool="flextools_health",
            args={"verbose": True},
            rationale=(
                "flextools_health reports each sandbox component (hc, "
                "GenerateHCConfig.exe) with where it was looked for."
            ),
            est_cost="seconds",
        ),
    ]


def _tool_missing(component: str, expected_path: str, message: str) -> List[TextContent]:
    detail = ParserToolMissingDetail(
        component=component,
        expected_path=expected_path,
        install_hint=(
            HC_INSTALL_HINT if component == "hc" else GENERATE_HC_CONFIG_INSTALL_HINT
        ),
    )
    return error_response(
        "parser_tool_missing",
        message,
        **_sandbox_detail_kwargs(detail),
        next_step=_tool_missing_rungs(component),
    )


def _sandbox_check_tools(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    """Step 3: tool discovery (FR-007). `hc` first, then GenerateHCConfig.exe.

    `hc` must be found AND start (`starts is True`). GenerateHCConfig.exe is
    looked up only when generation may run, so a named sandbox's parse never
    blames it.
    """
    hc = parser_probe.discover_hc_tool()
    if not (getattr(hc, "found", False) and getattr(hc, "starts", None) is True):
        expected = (
            getattr(hc, "path", None)
            or getattr(hc, "expected_path", None)
            or parser_probe.HC_EXPECTED_PATH_DESCRIPTION
        )
        reason = getattr(hc, "reason", None)
        what = "was found but could not start" if getattr(hc, "found", False) else "was not found"
        message = f"The hc tool {what}" + (f": {reason}." if reason else ".")
        return _tool_missing("hc", str(expected), message)
    plan.hc = hc

    if _sandbox_generation_may_run(plan.request):
        ghc = parser_probe.discover_generate_hc_config()
        if not getattr(ghc, "ok", False):
            expected = getattr(ghc, "expected_path", None) or _GENERATE_HC_CONFIG_DEFAULT_PATH
            return _tool_missing(
                "GenerateHCConfig.exe",
                str(expected),
                "GenerateHCConfig.exe was not found; it is needed to export the "
                "project's grammar for hc.",
            )
        plan.generator = ghc
    return None


# -- step 4 ----------------------------------------------------------------


def _sandbox_fwdata_path(project_name: str) -> Optional[Path]:
    """`<projects>/<P>/<P>.fwdata`, by the server's own discovery. No LCM open."""
    project_dir = filing_paths.project_dir_for(project_name)
    if project_dir is None:
        return None
    return project_dir / f"{project_name}.fwdata"


def _sandbox_engine_check(project_name: str) -> Optional[Dict[str, Any]]:
    """Step 4 (FR-036): the `.fwdata` stream read (R-02), never LCM.

    None when the project's active parser is HC; otherwise the
    `parser_engine_mismatch` detail (configured_engine, supported_engines,
    hint). An unreadable or unlocatable `.fwdata` fails safe to a mismatch
    with the engine module's "could not be read" hint. Creates no file.
    """
    from ..sandbox import engine as sandbox_engine

    fwdata = _sandbox_fwdata_path(project_name)
    if fwdata is None:
        fwdata = Path(f"{project_name}.fwdata")  # unreadable: fails safe
    try:
        sandbox_engine.check_engine(fwdata, supported_engines=(SANDBOX_ENGINE,))
    except parser_probe.ParserEngineMismatchError as exc:
        detail = dict(exc.detail)
        detail.pop("error_code", None)
        return detail
    return None


def _sandbox_run_engine_check(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    if not _sandbox_generation_may_run(plan.request):
        return None  # a named sandbox is used exactly as it is
    detail = _sandbox_engine_check(plan.project_name)
    if detail is None:
        return None
    ordered = {
        "configured_engine": detail.get("configured_engine"),
        "supported_engines": detail.get("supported_engines") or [SANDBOX_ENGINE],
        "hint": detail.get("hint") or "",
    }
    return error_response(
        "parser_engine_mismatch",
        f"The project's active parser is {ordered['configured_engine']!r}; the "
        "sandbox spine exports and runs HermitCrab (HC) grammars only.",
        **ordered,
        next_step=[
            _rung(
                action="Switch the project's parser to HermitCrab in FLEx, then retry.",
                tool=None,
                args=None,
                rationale=(
                    "The engine check reads the project's saved parser setting; "
                    "a grammar for another engine cannot be exported for hc."
                ),
                est_cost="minutes",
            ),
            _sandbox_list_rung(plan.project_name),
        ],
    )


# -- step 5 ----------------------------------------------------------------


def _sandbox_access(plan: _SandboxPlan) -> None:
    """Step 5 (FR-040, R-13): lock metadata only. NEVER refuses."""
    access = _probe_access(plan.project_name)
    verdict = getattr(access, "verdict", None)
    plan.project_state = {"access": verdict}
    if verdict == "held_by_other" and _sandbox_holder_is_own_worker(plan.project_name, access):
        # Pattern audit sweep 3: the holder is this server's own read-only
        # worker, which has no unsaved edits -- the .fwdata on disk is what
        # it read, so the run's grammar is not unverifiable.
        return None
    if verdict in SANDBOX_STALENESS_VERDICTS:
        from ..parse.diff import SHARED_MODE_STALENESS

        plan.staleness = SHARED_MODE_STALENESS
        plan.project_state["staleness"] = SHARED_MODE_STALENESS
    return None


def _sandbox_holder_is_own_worker(project_name: str, access) -> bool:
    """Step 5 helper: never raises (step 5 never refuses)."""
    try:
        return _holder_is_own_read_worker(get_runner(), project_name, access)
    except Exception:  # noqa: BLE001 -- unknown means "not ours": keep the staleness
        return False


# -- step 7 ----------------------------------------------------------------


def _sandbox_space_check(request: ParseSandboxInput, project_name: str) -> Optional[List[TextContent]]:
    """Step 7 (FR-012): free space for the copy, only on a cache miss.

    Only when generation may run AND the cache has no usable entry for the
    project's current inputs (looked up with `touch=False`: a precheck never
    refreshes an entry). Then `workdir.check_free_space(fwdata)` -- 2x the
    allowlist size on the `work/` volume, through the shared
    `disk_space_ok` rule. Nothing is created to measure it, and anything
    unmeasurable is fail-open: the copy step reports its own failure.

    The orphan sweep (the runner, once) and the LRU prune (the client, per
    job) are not this step's (T050/T051).
    """
    if not _sandbox_generation_may_run(request):
        return None
    from ..sandbox import cache as sandbox_cache
    from ..sandbox import workdir as sandbox_workdir

    fwdata = _sandbox_fwdata_path(project_name)
    ghc = parser_probe.discover_generate_hc_config()
    if fwdata is None or not getattr(ghc, "ok", False):
        return None
    try:
        inputs = sandbox_cache.key_inputs(fwdata, ghc.expected_path)
        key = sandbox_cache.compute_key(inputs)
        if sandbox_cache.lookup(project_name, key, touch=False) is not None:
            return None
        shortfall = sandbox_workdir.check_free_space(fwdata)
    except Exception:  # noqa: BLE001 -- unmeasurable is fail-open
        return None
    if shortfall is None:
        return None
    try:
        work_root = str(sandbox_paths.work_root())
    except Exception:  # noqa: BLE001
        work_root = None
    required, free = shortfall.needed_bytes, shortfall.free_bytes
    return _sandbox_refused(
        "insufficient_disk_space",
        "Not enough free disk space to copy the project for export.",
        path=work_root,
        needed_bytes=required,
        free_bytes=free,
        hint=(
            "Free space on the volume holding the sandbox root, or point "
            "FLEXTOOLSMCP_PARSE_SANDBOX_DIR at a volume with room, then retry."
        ),
        next_step=[
            _rung(
                action="Free disk space, then retry.",
                tool=None,
                args=None,
                rationale=(
                    "The copy needs twice the project file's size free; nothing "
                    "was copied."
                ),
                est_cost="minutes",
            )
        ],
    )


# -- step 8 and the section 5.1 envelope ------------------------------------


def _sandbox_fingerprint(plan: _SandboxPlan) -> Dict[str, Any]:
    """R-14: `scope_kind="words"`, `engine="HC"`, comparable with in-process.

    `vernacular_ws` is not known without opening the project; it is left
    empty rather than guessed (a diff reconciles it -- US6).
    """
    from ..parse.fingerprint import ScopeFingerprint

    return ScopeFingerprint(
        scope_kind="words",
        scope_value=list(plan.scope_value),
        text_ids=(),
        word_count=plan.word_count,
        limit=plan.request.limit,
        truncated=plan.truncated,
        engine=SANDBOX_ENGINE,
        vernacular_ws="",
    ).to_dict()


def _sandbox_config_source(plan: _SandboxPlan) -> Dict[str, Any]:
    if plan.request.sandbox is None:
        return {"kind": "project_cache"}
    status = plan.sandbox_status or {}
    return {
        "kind": "named_sandbox",
        "name": plan.request.sandbox,
        "edited": status.get("edited"),
        "predates_project_grammar": bool(status.get("predates_project_grammar")),
    }


def _sandbox_submitted_advisories(plan: _SandboxPlan) -> List[str]:
    """Advisories the handler already knows at submission (FR-029)."""
    codes: List[str] = []
    if (plan.sandbox_status or {}).get("predates_project_grammar"):
        codes.append("sandbox_predates_project_grammar")
    return codes


def _sandbox_versions(plan: _SandboxPlan) -> Dict[str, Any]:
    from ..sandbox import script as sandbox_script

    try:
        hcparse = sandbox_script.read_hcparse_version()
    except Exception:  # noqa: BLE001
        hcparse = None
    return {
        "hc_tool": getattr(plan.hc, "detected_version", None),
        "fieldworks_hermitcrab": None,
        "generate_hc_config": None,
        "hcparse": hcparse,
    }


def _sandbox_launch(plan: _SandboxPlan) -> Dict[str, Any]:
    """What the client needs to launch the script (T050/T051 reconcile)."""
    request, project_name = plan.request, plan.project_name
    fwdata = _sandbox_fwdata_path(project_name)
    config_path = (
        str(_sandbox_config_path(project_name, request.sandbox))
        if request.sandbox is not None else None
    )
    return {
        "fwdata_path": str(fwdata) if fwdata is not None else None,
        "generate_hc_config_path": (
            getattr(plan.generator, "expected_path", None) if plan.generator else None
        ),
        "hc_path": getattr(plan.hc, "path", None),
        "hc_invoke_argv": getattr(plan.hc, "invoke_argv", None),
        "config_path": config_path,
        "timeout_seconds": request.timeout_seconds,
        # run_corpus (Test mode, T072): the corpus JSON the script reads.
        "assertion_file": str(plan.corpus.path) if plan.corpus is not None else None,
    }


def _sandbox_recorded(handle, fallback: Dict[str, Any]) -> Dict[str, Any]:
    """`meta.sandbox` as the run recorded it, over what was submitted."""
    merged = dict(fallback)
    try:
        meta = handle.record.read_meta()
        recorded = getattr(meta, "sandbox", None) if meta is not None else None
    except Exception:  # noqa: BLE001 -- a record not yet readable is not a failure
        recorded = None
    if isinstance(recorded, dict):
        for key, value in recorded.items():
            if value is None:
                continue
            if key == "advisories":
                # A union, in order: what the run found never erases what
                # the handler knew at submission.
                seen = list(merged.get("advisories") or [])
                for item in value or []:
                    if item not in seen:
                        seen.append(item)
                merged[key] = seen
            else:
                merged[key] = value
    return merged


def _leading_dash_words(handle) -> List[str]:
    words = []
    for entry in getattr(handle, "results", None) or []:
        flags = (entry.get("parse") or {}).get("flags") or []
        if "leading_dash_unverified" in flags:
            words.append(entry.get("wordform"))
    return words


def _sandbox_advisories(sandbox: Dict[str, Any], handle) -> List[Dict[str, Any]]:
    """Advisory codes (a list in meta) as `{code, note}` with the fixed notes."""
    versions = sandbox.get("versions") or {}
    generation = sandbox.get("generation") or {}
    out: List[Dict[str, Any]] = []
    for item in sandbox.get("advisories") or []:
        if isinstance(item, dict):
            out.append(item)
            continue
        code = str(item)
        template = _ADVISORY_NOTES.get(code)
        note = None
        if template is not None:
            note = template.format(
                a=versions.get("hc_tool"),
                b=versions.get("fieldworks_hermitcrab"),
                n=generation.get("load_error_count") or 0,
            )
        advisory: Dict[str, Any] = {"code": code, "note": note}
        if code == "leading_dash_unverified":
            advisory["words"] = _leading_dash_words(handle)  # data, not prose
        out.append(advisory)
    return out


def _has_load_errors(sandbox: Dict[str, Any], advisories: List[Dict[str, Any]]) -> bool:
    generation = sandbox.get("generation") or {}
    if (generation.get("load_error_count") or 0) > 0:
        return True
    return any(a.get("code") == "grammar_load_errors" for a in advisories)


def _with_grammar_scan(rungs: List[Dict[str, Any]], project_name) -> List[Dict[str, Any]]:
    """FR-041: load errors point at the static scan; first, and once."""
    if any(r.get("tool") == "flextools_grammar_health" for r in rungs):
        return rungs
    return [_grammar_scan_rung(project_name)] + rungs


def _sandbox_staleness_fields(plan: _SandboxPlan) -> Dict[str, Any]:
    if plan.staleness is None:
        return {}
    from ..parse.diff import SHARED_MODE_NOTE

    return {"staleness": plan.staleness, "staleness_note": SHARED_MODE_NOTE}


async def _sandbox_start_parse(plan: _SandboxPlan) -> List[TextContent]:
    """Step 8: the run id exists from here on; later failures are run states.

    Serves `parse` (mode "parse") and `run_corpus` (mode "test"); a test run
    records its corpus in `meta.sandbox.corpus` and hands the corpus file to
    the client as `sandbox_launch.assertion_file`.
    """
    fingerprint = _sandbox_fingerprint(plan)
    config_source = _sandbox_config_source(plan)
    mode = "test" if plan.corpus is not None else "parse"
    submitted = {
        "mode": mode,
        "config_source": config_source,
        "versions": _sandbox_versions(plan),
        "hc_source": getattr(plan.hc, "source", None),
        "generation": None,
        "truncated_by_limit": plan.truncated,
        "advisories": _sandbox_submitted_advisories(plan),
    }
    if plan.corpus is not None:
        submitted["corpus"] = {"name": plan.corpus.name,
                               "assertion_count": len(plan.corpus.assertions)}
    runner = get_runner()
    try:
        handle = await runner.start_run(
            project_name=plan.project_name,
            wordforms=list(plan.words),
            level="batch",
            scope_fingerprint=fingerprint,
            engine_at_submission=SANDBOX_ENGINE,
            project_state=plan.project_state,
            worker_role=_sandbox_role(),
            spine="sandbox",
            sandbox=submitted,
            sandbox_launch=_sandbox_launch(plan),
        )
    except WorkerError as exc:
        return _worker_error_response(exc)

    sandbox = _sandbox_recorded(handle, submitted)
    advisories = _sandbox_advisories(sandbox, handle)
    common: Dict[str, Any] = {
        "spine": "sandbox",
        "config_source": sandbox.get("config_source") or config_source,
        "versions": sandbox.get("versions"),
        "advisories": advisories,
        "generation": sandbox.get("generation"),
        **_sandbox_staleness_fields(plan),
        "results_label": SANDBOX_RESULTS_LABEL,
    }

    failure = getattr(handle, "failure", None)
    if (
        handle.is_terminal
        and handle.stage is RunStage.FAILED
        and failure is not None
        and failure.error_code in _SANDBOX_FAILURE_CODES
    ):
        detail = dict(failure.detail or {})
        detail.pop("error_code", None)
        message = detail.pop("message", None) or failure.message
        detail.setdefault("run_id", handle.run_id)
        for key in list(common):
            detail.pop(key, None)
        return error_response(
            failure.error_code,
            message,
            **detail,
            **common,
            project_state=plan.project_state,
            next_step=_with_grammar_scan(_failure_rungs(handle), plan.project_name),
        )

    result: Dict[str, Any] = {
        "status": "ok",
        "action": plan.request.action,
        "project": plan.project_name,
        "run_id": handle.run_id,
        "run_started": True,
        "stage": handle.stage.value,
        "words_completed": handle.words_completed,
        "words_total": handle.words_total,
        "truncated_by_limit": plan.truncated,
        "scope_fingerprint": fingerprint,
        "engine_at_submission": SANDBOX_ENGINE,
        "record_dir": str(handle.record.root),
        "project_state": plan.project_state,
        **common,
    }
    if handle.is_terminal:
        if handle.stage is RunStage.FAILED and failure is not None:
            result["failure"] = failure.to_dict()
        else:
            result["result_summary"] = _result_summary(handle)
            result["result_summary"].update(_sandbox_summary_block(handle, sandbox))
        result.update({k: v for k, v in _batch_block(handle).items() if k not in result})
    else:
        result["note"] = (
            "The run is going in the background and was not slowed or limited "
            "by this call returning. Poll the run for progress."
        )
    rungs = list(_status_next_step(handle) or [])
    if _has_load_errors(sandbox, advisories):
        rungs = _with_grammar_scan(rungs, plan.project_name)
    if not rungs:
        rungs = [
            _read_run_rung(
                handle.run_id,
                "This run's record -- per-word results and the hc output -- is on disk.",
            )
        ]
    result["next_step"] = rungs
    return json_response(build_response_with_context(result))


# -- create_sandbox (US3, contracts section 5.2) -----------------------------


async def _sandbox_create(plan: _SandboxPlan) -> List[TextContent]:
    """Make the named sandbox from the project's cache entry, synchronously.

    If no cache entry is usable one is built first (`cache.ensure_entry`),
    in a copy folder this function makes and ALWAYS deletes -- cache.py never
    creates or deletes work folders. No run id exists: a generation failure
    is `parser_config_failed` with `run_id: null` (section 5.2).
    """
    from ..sandbox import cache as sandbox_cache
    from ..sandbox import workdir as sandbox_workdir

    request, project_name = plan.request, plan.project_name
    name = request.sandbox
    fwdata = _sandbox_fwdata_path(project_name) or Path(f"{project_name}.fwdata")
    generator = getattr(plan.generator, "expected_path", None)

    op_id = uuid.uuid4().hex
    work = sandbox_workdir.create(op_id, source_fwdata=fwdata)
    try:
        entry = await sandbox_cache.ensure_entry(
            project_name,
            fwdata,
            generator,
            work_dir=work,
            run_id=None,
            versions=_sandbox_versions(plan),
            timeout_seconds=request.timeout_seconds,
        )
    except sandbox_cache.ParserConfigFailed as failed:
        detail = failed.detail
        kwargs = (
            _sandbox_detail_kwargs(detail) if hasattr(detail, "model_dump")
            else {k: v for k, v in dict(detail or {}).items() if k != "error_code"}
        )
        kwargs["run_id"] = None  # no run exists for create_sandbox
        return error_response(
            "parser_config_failed",
            "GenerateHCConfig could not export the project's grammar, so no "
            "sandbox was created.",
            **kwargs,
            next_step=[
                _grammar_scan_rung(project_name),
                _rung(
                    action="Check the environment and the sandbox components.",
                    tool="flextools_health",
                    args={"verbose": True},
                    rationale=(
                        "The generator's own output is in log_path; health reports "
                        "where GenerateHCConfig.exe was found."
                    ),
                    est_cost="seconds",
                ),
            ],
        )
    finally:
        sandbox_workdir.delete(work)

    try:
        created = _sandbox_store().create_sandbox(project_name, name, entry)
    except FileExistsError:
        return _sandbox_refused(
            "sandbox_exists",
            f"A sandbox named {name!r} already exists for this project.",
            name=name,
            path=str(_sandbox_config_path(project_name, name)),
            hint="Pick a new name, or parse against the existing sandbox.",
            next_step=[_sandbox_list_rung(project_name)],
        )

    load_error_count = int(getattr(entry, "load_error_count", 0) or 0)
    rungs = [
        _rung(
            action="Edit the XML, then run words against the sandbox.",
            tool="flextools_parse_sandbox",
            args={"action": "parse", "project_name": project_name, "sandbox": name},
            rationale=(
                "The sandbox is a user-owned copy of the exported grammar at path; "
                "edit it with ordinary file tools. No cache refresh or grammar "
                "change overwrites it."
            ),
            est_cost="minutes",
        )
    ]
    result: Dict[str, Any] = {
        "status": "ok",
        "action": "create_sandbox",
        "project": project_name,
        "name": created.get("name", name),
        "path": created.get("path"),
        "origin": created.get("origin"),
        "generation": {
            "reused_cache": not bool(getattr(entry, "built", False)),
            "load_error_count": load_error_count,
        },
    }
    if load_error_count:
        result["advisories"] = [{
            "code": "grammar_load_errors",
            "note": _ADVISORY_NOTES["grammar_load_errors"].format(
                a=None, b=None, n=load_error_count
            ),
        }]
        rungs = _with_grammar_scan(rungs, project_name)
    result["next_step"] = rungs
    return json_response(build_response_with_context(result))


# -- list (contracts section 5.4) --------------------------------------------


def _sandbox_list(plan: _SandboxPlan) -> List[TextContent]:
    """Synchronous and read-only: the project's sandboxes and corpora."""
    project_name = plan.project_name
    store = _sandbox_store()
    sandboxes = list(store.list_sandboxes(project_name) or [])
    list_corpora = getattr(store, "list_corpora", None)
    corpora = list(list_corpora(project_name) or []) if callable(list_corpora) else []
    if sandboxes:
        rung = _rung(
            action="Run words against one of these sandboxes.",
            tool="flextools_parse_sandbox",
            args={"action": "parse", "project_name": project_name,
                  "sandbox": sandboxes[0].get("name")},
            rationale="Each sandbox is used exactly as it is on disk.",
            est_cost="minutes",
        )
    else:
        rung = _rung(
            action="Create a sandbox from the project's current grammar.",
            tool="flextools_parse_sandbox",
            args={"action": "create_sandbox", "project_name": project_name,
                  "sandbox": None},
            rationale="A sandbox is a named, user-owned copy of the exported grammar.",
            est_cost="seconds to a minute",
        )
    result = {
        "status": "ok",
        "action": "list",
        "project": project_name,
        "sandboxes": sandboxes,
        "corpora": corpora,
        "next_step": [rung],
    }
    return json_response(build_response_with_context(result))


# -- step 6: the corpus (run_corpus) -----------------------------------------


def _sandbox_load_corpus(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    """Step 6: load and validate the whole corpus file (data-model 5).

    `corpus_not_found` / `corpus_invalid` (naming the JSON path of the first
    fault). An assertion hc cannot express is NOT a fault here (FR-027): the
    script marks it `not_expressible` and the run goes ahead.
    """
    store = _sandbox_store()
    name = plan.request.corpus
    try:
        corpus = store.load_corpus(plan.project_name, name)
    except sandbox_paths.SandboxNameError as bad:
        return _sandbox_name_refusal(name, bad.detail, plan.project_name)
    except store.CorpusNotFound as missing:
        return _sandbox_refused(
            "corpus_not_found",
            f"No corpus named {name!r} exists for this project.",
            name=name,
            path=missing.path,
            hint=(
                "Seed one from a completed sandbox parse run with "
                "action='seed_corpus', or pick an existing corpus name."
            ),
            next_step=[_sandbox_list_rung(plan.project_name)],
        )
    except store.CorpusInvalid as invalid:
        refusal = _sandbox_refused(
            "corpus_invalid",
            f"The corpus {name!r} is not valid at {invalid.json_path}.",
            name=name,
            path=invalid.path,
            hint=(
                f"Fix the corpus file at {invalid.json_path}: {invalid.detail}. "
                "The whole file is checked before anything runs."
            ),
            next_step=[_sandbox_list_rung(plan.project_name)],
        )
        return _with_extra(refusal, json_path=invalid.json_path)
    plan.corpus = corpus
    plan.words = [a["word"] for a in corpus.assertions]
    plan.word_count = len(plan.words)
    plan.scope_value = sorted(plan.words)
    plan.truncated = False
    return None


def _with_extra(envelope: List[TextContent], **extra: Any) -> List[TextContent]:
    """Re-emit an error envelope with data fields appended after its own."""
    data = json.loads(envelope[0].text)
    fields = {k: v for k, v in data.items()
              if k not in ("_contract", "status", "error_code", "message", "error")}
    fields.update(extra)
    return error_response(data["error_code"], data["message"], **fields)


def _sandbox_meta_of(handle) -> Optional[Dict[str, Any]]:
    """`meta.sandbox` for a SANDBOX_ROLE run, `{}` if unreadable; None otherwise."""
    if getattr(handle, "worker_role", None) != _sandbox_role():
        return None
    try:
        meta = handle.record.read_meta()
        sandbox = getattr(meta, "sandbox", None) if meta is not None else None
    except Exception:  # noqa: BLE001 -- a record not yet readable is not a failure
        sandbox = None
    return sandbox if isinstance(sandbox, dict) else {}


def _sandbox_summary_block(handle, sandbox: Dict[str, Any]) -> Dict[str, Any]:
    """data-model 6.6: counts by outcome (parse) or by classification (test)."""
    if sandbox.get("mode") == "test":
        return _sandbox_test_summary(handle, sandbox)
    from ..sandbox import classify as sandbox_classify

    lines = [r for r in (getattr(handle, "results", None) or [])
             if isinstance(r, dict) and isinstance(r.get("parse"), dict)
             and r["parse"].get("outcome")]
    try:
        outcomes = sandbox_classify.tally_outcomes(lines)
    except KeyError:
        outcomes = None
    hc = sandbox.get("hc") if isinstance(sandbox.get("hc"), dict) else {}
    return {"outcomes": outcomes, "counters": hc.get("counters")}


def _sandbox_test_summary(handle, sandbox: Dict[str, Any]) -> Dict[str, Any]:
    """data-model 6.6's test block: classifications, hc_counters, agreement."""
    from ..sandbox import classify as sandbox_classify
    from ..sandbox import hc_output as sandbox_hc_output

    lines = [r for r in (getattr(handle, "results", None) or [])
             if isinstance(r, dict) and isinstance(r.get("assertion"), dict)]
    classifications = sandbox_classify.tally_classifications(lines)
    hc = sandbox.get("hc") if isinstance(sandbox.get("hc"), dict) else {}
    counters = hc.get("hc_counters") if isinstance(hc.get("hc_counters"), dict) else None
    agreement: Optional[bool] = None
    if counters is not None:
        try:
            divergences = sandbox_classify.reconcile_test_counters(
                lines, sandbox_hc_output.TestCounters(**counters)
            )
            agreement = not divergences
        except Exception:  # noqa: BLE001 -- unreadable counters: agreement unknown
            agreement = None
    return {
        "classifications": classifications,
        "hc_counters": counters,
        "counter_agreement": agreement,
    }


# -- seed_corpus (contracts sections 3 and 5.3) -------------------------------


def _sandbox_seed(plan: _SandboxPlan) -> List[TextContent]:
    """Seed a corpus from a completed sandbox parse run. Synchronous; no run.

    The store checks, in order: the run exists (`parse_run_not_found`); it is
    a completed sandbox PARSE run of this project (`run_not_seedable`); the
    name is valid and new (`name_invalid` / `corpus_exists`).
    """
    from ..parse.record import RunRecord

    request, project_name = plan.request, plan.project_name
    run_id = request.from_run_id
    search_rung = _rung(
        action="See which runs have records on disk.",
        tool="flextools_parse_status",
        args=None,
        rationale="Seed from the run id of a completed sandbox parse run.",
        est_cost="instant",
    )
    if not run_id:
        return _ensure_next_step(_run_not_found(""), [search_rung])
    store = _sandbox_store()
    runner = _runner
    record = RunRecord(run_id, record_dir=runner.record_dir if runner is not None else None)
    name = request.corpus
    try:
        seeded = store.seed_corpus(project_name, name, record)
    except MetaUnreadable as exc:
        # Pattern audit sweep 6: the run exists but its meta.json stayed
        # unreadable -- transient, so not `parse_run_not_found`.
        return _run_record_unreadable(
            run_id, exc, tool="flextools_parse_sandbox",
            args={"action": "seed_corpus", "project_name": project_name,
                  "from_run_id": run_id, "corpus": name})
    except store.RunNotFound:
        return _ensure_next_step(_run_not_found(run_id), [search_rung])
    except store.RunNotSeedable as refused:
        return _sandbox_refused(
            "run_not_seedable",
            f"Run {run_id} cannot seed a corpus: {refused.detail}.",
            name=name if isinstance(name, str) else None,
            hint=(
                "A corpus is seeded from a COMPLETED sandbox parse run of this "
                "project (action='parse'), not a corpus run or an in-process run."
            ),
            next_step=[
                _rung(
                    action="Parse the words with the sandbox spine first.",
                    tool="flextools_parse_sandbox",
                    args={"action": "parse", "project_name": project_name},
                    rationale="Its completed run can then seed the corpus.",
                    est_cost="minutes",
                )
            ],
        )
    except sandbox_paths.SandboxNameError as bad:
        return _sandbox_name_refusal(name, bad.detail, project_name)
    except store.CorpusExists as exists:
        return _sandbox_refused(
            "corpus_exists",
            f"A corpus named {name!r} already exists for this project.",
            name=name,
            path=exists.path,
            hint="Pick a new corpus name; an existing corpus is never overwritten.",
            next_step=[_sandbox_list_rung(project_name)],
        )
    result = {
        "status": "ok",
        "action": "seed_corpus",
        "project": project_name,
        **{k: seeded.get(k) for k in ("name", "path", "assertion_count",
                                      "no_parse_count", "excluded", "from_run_id")},
        "next_step": [
            _rung(
                action="Run the corpus against the project's grammar or a sandbox.",
                tool="flextools_parse_sandbox",
                args={"action": "run_corpus", "project_name": project_name,
                      "corpus": seeded.get("name")},
                rationale=(
                    "Each assertion is then classified pass, regression, "
                    "new_ambiguity, changed or error."
                ),
                est_cost="minutes",
            )
        ],
    }
    return json_response(build_response_with_context(result))


async def handle_flextools_parse_sandbox(args: dict) -> List[TextContent]:
    """The sandbox spine's entry point (contracts/tools.md sections 1-3).

    Runs the check order one step helper at a time; the first refusal wins.
    Every action is built: `parse` and `run_corpus` (steps 1-8; step 6 is
    run_corpus's corpus load), `create_sandbox` (steps 1-4, 7, then a
    synchronous export), and `seed_corpus` / `list` (step 1, then their own
    synchronous checks; no run).
    """
    # Already validated at the dispatch boundary; rebuilt here for the typed
    # model, as `flextools_parse_text` does, so a direct call validates too.
    request = ParseSandboxInput(**args)
    plan = _SandboxPlan(request=request)

    refusal = _sandbox_resolve_project(plan) or _sandbox_check_root(plan)
    if refusal is not None:
        return refusal

    if request.action == "list":
        return _sandbox_list(plan)                                  # read-only
    if request.action == "seed_corpus":
        return _sandbox_seed(plan)                                  # sync, no run

    for step in (
        _sandbox_resolve_source,     # 2
        _sandbox_read_words,         # 2b (parse)
        _sandbox_check_tools,        # 3
    ):
        refusal = step(plan)
        if refusal is not None:
            return refusal

    refusal = _sandbox_run_engine_check(plan)                       # 4
    if refusal is not None:
        return refusal

    if request.action == "create_sandbox":
        refusal = _sandbox_space_check(request, plan.project_name)  # 7
        if refusal is not None:
            return refusal
        return await _sandbox_create(plan)                          # sync, no run

    _sandbox_access(plan)                                           # 5 (never refuses)
    if request.action == "run_corpus":
        refusal = _sandbox_load_corpus(plan)                        # 6
        if refusal is not None:
            return refusal
    refusal = _sandbox_space_check(request, plan.project_name)      # 7
    if refusal is not None:
        return refusal
    return await _sandbox_start_parse(plan)                         # 8


# ---------------------------------------------------------------------------
# flextools_parse_release (issue #223)
# ---------------------------------------------------------------------------


async def handle_flextools_parse_release(args: dict) -> List[TextContent]:
    """Release this server's own idle parse worker(s) for a project (#223).

    `flextools_try_word` / `flextools_parse_text` leave their shared read
    worker running (idle timeout: `DEFAULT_IDLE_TIMEOUT_SECONDS`), and it
    keeps the project's fwdata lock held until then. `flextools_run_module`'s
    write gate already releases that worker automatically when it finds
    its own idle worker holding the lock -- this tool exists for the case
    nothing else prompts that release: a caller that wants the lock
    dropped on purpose, without also submitting a write.

    Never kills a live run. If any of the project's workers (the shared
    read worker, or the bounded measurement worker) is mid-run, this
    refuses with `project_locked` and points at `flextools_parse_cancel`
    rather than tearing down work in progress.

    No worker running at all is a SUCCESS, not an error -- there was
    nothing holding the lock in the first place, so there is nothing to do.

    Args:
        args: validated `ParseReleaseInput` dump -- `project_name`
            (optional; falls back to the session).

    Returns:
        `{status: ok, released: [...]}` naming the role(s) released (or an
        empty list if there was nothing to release), or `project_locked`
        naming the live run blocking release.
    """
    project_name, project_error = _resolve_project(args.get("project_name"))
    if not project_name:
        return project_error or error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or "
            "provide it directly.",
        )

    runner = peek_runner()
    if runner is None:
        return json_response(build_response_with_context({
            "status": "ok",
            "project": project_name,
            "released": [],
            "note": (
                "This server process has started no parse worker at all, "
                "so there is nothing to release."
            ),
        }))

    workers = runner.pool.workers_for(project_name)
    if not workers:
        return json_response(build_response_with_context({
            "status": "ok",
            "project": project_name,
            "released": [],
            "note": (
                f"No parse worker is running for '{project_name}' in this "
                "server process; nothing to release."
            ),
        }))

    busy_roles = sorted(
        role for role in workers if runner.worker_busy(project_name, role=role)
    )
    if busy_roles:
        role = busy_roles[0]
        run_ids = runner.active_run_ids(project_name, role=role)
        run_note = busy_own_worker_run_note(run_ids)
        guidance = busy_own_worker_guidance("retry flextools_parse_release")
        return error_response(
            "project_locked",
            f"Project '{project_name}' has a live parse run on this "
            f"server's own worker{run_note}. Releasing now would end work "
            f"in progress, so this refuses. {guidance}",
            guidance=guidance,
            remedy=guidance,
            verdict="held_by_mcp_read_worker",
            sharing_enabled=None,
            holder_pid=None,
            holder_process="this server's own parse worker",
        )

    # THE PER-ROLE RELEASE IS ATOMIC, CHECK-AND-POP UNDER ONE LOCK (#223 QC
    # P1). `busy_roles` above is a point-in-time snapshot, taken purely so
    # the common case can be refused in one clear message rather than one
    # role at a time; the loop below is what actually tears a worker down,
    # and it re-checks busyness (via `release_worker_if_idle`) at the
    # instant of the pop, so a run that starts using one of these roles
    # between the snapshot above and this loop reaching it is never torn
    # down out from under it -- it is left running, and reported as such
    # rather than silently counted as released.
    released = []
    raced_busy = []
    for role in sorted(workers.keys()):
        if await runner.release_worker_if_idle(project_name, role=role):
            released.append(role)
        else:
            raced_busy.append(role)

    note = (
        f"Released this server's parse worker(s) for '{project_name}' "
        f"({', '.join(released)}). Any lock this worker held on the "
        "project's .fwdata is now dropped."
    ) if released else (
        f"No idle parse worker for '{project_name}' was found to release."
    )
    if raced_busy:
        note += (
            f" {', '.join(raced_busy)} started a new run just as this "
            "call reached it and was left running rather than torn down "
            "mid-parse; retry flextools_parse_release once it finishes."
        )
    return json_response(build_response_with_context({
        "status": "ok",
        "project": project_name,
        "released": released,
        "note": note,
    }))


def _result_summary(handle) -> Dict[str, Any]:
    """What a completed run produced, summarised rather than inlined.

    Counts and paths, never the traces themselves: a single trace runs to
    tens or hundreds of kilobytes, and a completed batch of four thousand
    words would not fit in a response at all (data-model.md section 5).

    TWO QUESTIONS, TWO COUNTERS. `plain`/`explain` entries carry `parsed`;
    `restricted` entries carry `hypothesis_held` instead, never `parsed`
    (worker_main.py's `BackendFacade.parse()` renames it there, at the one
    place that already knows which question that run's level asked). Before
    this fix, every entry's `parse` was `{}` for `explain`/`restricted`
    (the worker returned `{"parse": None, ...}` for both), so
    `parse.get("parsed")` was always falsy and a poll on ANY completed
    explain/restricted run reported `parsed: 0` unconditionally --
    indistinguishable from "every word failed to parse". Counting each
    question separately, over the entries that actually carry its key,
    is what keeps a `restricted` run's held hypotheses from being
    conflated with -- or silently erased by -- an unrestricted `parsed`
    count that was never asked about them.
    """
    parsed = 0
    hypotheses_held = 0
    traced = 0
    for entry in handle.results:
        parse = entry.get("parse") or {}
        if parse.get("parsed"):
            parsed += 1
        if parse.get("hypothesis_held"):
            hypotheses_held += 1
        if entry.get("trace_path"):
            traced += 1
    return {
        "words": len(handle.results),
        "parsed": parsed,
        "hypotheses_held": hypotheses_held,
        "traces_written": traced,
        "record_dir": str(handle.record.root),
    }


def _failure_rungs(handle) -> List[Dict[str, Any]]:
    """A FAILED run's rungs: the instruments, never a retry (FR-034).

    The static scan comes first (FR-057): it runs no parse, and the
    commonest failure -- memory exhausted while loading the grammar -- is the
    one it speaks to. No rung names `flextools_try_word`: repeating the run
    repeats the step that exhausted it. Words that completed before the
    failure are readable, and CP3 ships the tool that reads them (FR-058).
    """
    rungs = [
        _grammar_scan_rung(handle.project_name),
        _rung(
            action="Check the environment and the project's grammar.",
            tool="flextools_health",
            args={"verbose": True},
            rationale=(
                "A run that died while loading the grammar has usually "
                "exhausted memory. Repeating it repeats the step that "
                "exhausted it; the diagnostics say what the project needs."
            ),
            est_cost="seconds",
        ),
    ]
    if handle.words_completed > 0:
        rungs.append(
            _read_run_rung(
                handle.run_id,
                f"{handle.words_completed} word(s) completed before the "
                f"failure; their results were written as they were produced.",
            )
        )
    return rungs


def _status_next_step(handle) -> Optional[List[Dict[str, Any]]]:
    """What to do next, or nothing when there is nothing useful to say.

    A still-running run gets "poll again" -- plus the static scan when it is
    a batch that entered grammar loading and has stayed there (FR-056). A
    FAILED run gets the diagnostic instruments and never a retry (FR-034).

    FR-058's revisit: a cancelled run with partial results, and a completed
    BATCH, point at `flextools_parse_log` -- rows that had no tool to name
    before CP3 shipped one. A completed single word still gets `None`: its
    answer is already in the response.
    """
    if handle.stage is RunStage.FAILED:
        return _failure_rungs(handle)

    if not handle.is_terminal:
        rungs = [
            _rung(
                action="Poll again for this run.",
                tool="flextools_parse_status",
                args={"run_id": handle.run_id},
                rationale=(
                    f"The run is in {handle.stage.value!r} and is still "
                    f"going. It was not slowed or throttled by being polled."
                ),
                est_cost="instant",
            )
        ]
        if _stuck_loading(handle):
            rungs.append(_grammar_scan_rung(handle.project_name))
        return rungs

    if handle.stage is RunStage.CANCELLED and handle.words_completed > 0:
        return [
            _read_run_rung(
                handle.run_id,
                f"{handle.words_completed} word(s) completed before the cancel "
                f"and are on disk.",
            )
        ]

    if handle.stage is RunStage.COMPLETED and getattr(handle, "is_batch", False):
        return [
            _read_run_rung(
                handle.run_id,
                "The batch report -- signals, the oracle, clusters to trace -- "
                "is in this run's summary section.",
            )
        ]

    return None
