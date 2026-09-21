#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_try_word and flextools_parse_status (parser-check CP2b).

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

THE GRACE WINDOW IS A REPORTING BOUNDARY, NOT A TIMEOUT (FR-028, SC-010).
`ParseRunner.start_run` returns when the run finishes *or* when the window
closes, whichever comes first. This handler tells the two apart with
`handle.is_terminal` and does nothing else about it: a run still going is
left going, untouched, and the caller gets a handle to poll. Nothing on this
path cancels a run, shortens one, or passes a deadline downstream.
"""

import uuid
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps
from ..models import MorphSpec
from ..parse.priority import Priority
from ..parse.runner import ParseRunner
from ..parse.stages import RunStage
from ..parse.worker_client import WorkerError

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
    if resolved and resolved != name:
        session_state.project_name = resolved
        name = resolved
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
        refusal = _refusal_from_failure(handle.failure)
        if refusal is not None:
            return refusal
        return error_response(
            "runtime_error",
            handle.failure.message,
            error_type=handle.failure.error_type,
            stage_at_failure=handle.failure.stage_at_failure,
            next_step=handle.failure.next_step,
        )

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
            )
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
# flextools_parse_status
# ---------------------------------------------------------------------------


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
                "outlives the grace window, and they live as long as this "
                "server process does. "
                + (
                    f"Runs this server knows about: {', '.join(available)}."
                    if available
                    else "This server has no runs at all, so the handle is "
                    "either from an earlier server process or mistyped."
                )
            ),
        )

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

    if handle.stage is RunStage.COMPLETED:
        result["result_summary"] = _result_summary(handle)
    elif handle.stage is RunStage.FAILED and handle.failure is not None:
        # Reported, not raised. The run failed; the question did not.
        result["failure"] = handle.failure.to_dict()
    elif handle.stage is RunStage.CANCELLED:
        # `words_completed` above is the count that survived, and the stage
        # at cancel says where it stopped (FR-036). The partial results are
        # on disk and readable (FR-029).
        result["state_at_cancel"] = handle.stage_at_cancel
        result["partial_results_available"] = handle.words_completed > 0

    result["next_step"] = _status_next_step(handle)
    return json_response(build_response_with_context(result))


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


def _status_next_step(handle) -> Optional[List[Dict[str, Any]]]:
    """What to do next, or nothing when there is nothing useful to say.

    A still-running run gets "poll again". A FAILED run gets the diagnostic
    instruments and never a retry: the commonest failure is memory
    exhausted while loading the grammar, and repeating the run repeats the
    step that exhausted it (FR-034).

    A completed or cancelled run gets `None`. There is nothing to advise --
    the results are where the response says they are.
    """
    if handle.stage is RunStage.FAILED:
        return [
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
            _rung(
                action="Scan this project's grammar for path-multiplying properties.",
                tool="flextools_grammar_health",
                args={"project_name": handle.project_name},
                rationale=(
                    "Static scan, no parse. It names the grammar properties "
                    "that multiply the search space, which is what makes a "
                    "load expensive enough to fail."
                ),
                est_cost="seconds to a minute",
            ),
        ]

    if not handle.is_terminal:
        return [
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

    return None

