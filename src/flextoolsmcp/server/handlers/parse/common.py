"""
Shared plumbing for the parse tools: the one `ParseRunner`, the next_step
rung builders, morph-restriction resolution, project resolution, and the
refusal envelope a worker failure maps to.

`_resolve_project` and `_probe_access` are called from the other modules as
`common.<name>(...)` -- looked up at call time -- so a test patch on this
module reaches every tool.
"""

import time
import uuid
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from .._import_helper import safe_import_kernel_deps
from ...models import MorphSpec
from ...parse.measure import DEFAULT_BOUND_SECONDS
from ...parse.runner import ParseRunner
from ...parse.stages import RunStage

try:
    from ....response_utils import error_response
except (ImportError, ValueError):
    from response_utils import error_response


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
    from ...parse.resolver import Resolution, refusal_detail

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
        from ..execution import _available_projects_payload
    except (ImportError, ValueError):
        from server.handlers.execution import _available_projects_payload
    try:
        from ...project_discovery import normalize_project_name, project_not_found_fields
    except (ImportError, ValueError):
        from server.project_discovery import normalize_project_name, project_not_found_fields

    # Issue #311: a punctuation-only name ("``") is treated as omitted and
    # falls back to the session; "`Sena 3`" is unwrapped to "Sena 3".
    name = normalize_project_name(project_name) or session_state.get_project()
    if not name:
        return None, error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or "
            "provide it directly.",
            session=session_state.summary(),
            **_available_projects_payload(),
        )

    try:
        from ...project_discovery import resolve_or_explain
    except (ImportError, ValueError):
        from server.project_discovery import resolve_or_explain

    resolved, resolve_err = resolve_or_explain(name)
    if resolve_err:
        return None, error_response(
            resolve_err["error_code"],
            resolve_err["message"],
            session=session_state.summary(),
            **project_not_found_fields(resolve_err),
        )
    if resolved:
        try:
            from ....project_adoption import adopt_resolved_project
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


def _probe_access(project_name: Optional[str]):
    """The shared-mode probe (FR-034, R-06). Never fails the comparison.

    Reads a lock file's metadata only; it opens no project and does not
    touch the engine, which is why FR-024 permits it here.
    """
    if not project_name:
        return None
    try:
        try:
            from ...project_access import probe_project_access
        except (ImportError, ValueError):
            from server.project_access import probe_project_access
        return probe_project_access(project_name)
    except Exception:  # noqa: BLE001 -- an unknown access state is not a failure
        return None
