"""
flextools_try_word: one word, any level (CP2b).
"""

import uuid
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ...models import MorphSpec
from ...parse.measure import (
    MeasurementFailed,
    measure_word,
)
from ...parse.priority import Priority
from ...parse.stages import RunStage
from ...parse.worker_client import WorkerError

try:
    from ....response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

from . import common
from .common import (
    MorphResolutionRefused,
    _grammar_scan_rung,
    _refusal_from_failure,
    _resolve_restriction,
    _rung,
    _trace_after_scan_rung,
    get_runner,
    json_response,
)
from .filing import (
    _read_refused_during_filing,
)
from .summary import (
    _failure_rungs,
    _worker_error_response,
)


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

    project_name, project_error = common._resolve_project(args.get("project_name"))
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

        # The three-way outcome (worker_analysis.py `_summarize_trace`), copied
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
