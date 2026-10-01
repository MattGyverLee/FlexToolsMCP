"""
The run lifecycle tools: flextools_parse_text (CP3, US2), flextools_parse_status,
flextools_parse_cancel (CP4) and flextools_parse_release (#223), with the
sandbox-run status renderers parse_status needs.
"""

from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ...models import ParseTextInput, ResolvedScope
from ...parse.fingerprint import build_fingerprint
from ...parse.priority import Priority
from ...parse.stages import RunStage
from ...parse.worker_client import WorkerError
from ...parse.own_worker import (
    busy_own_worker_guidance,
    busy_own_worker_next_steps,
    busy_own_worker_run_note,
)

try:
    from ....response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

from . import common
from .common import (
    _rung,
    get_runner,
    json_response,
    peek_runner,
)
from .filing import (
    _handle_filing_request,
    _read_refused_during_filing,
)
from .run_log import (
    SANDBOX_SPINE,
)
from .sandbox_checks import (
    _sandbox_role,
)
from .summary import (
    _batch_block,
    _result_summary,
    _status_next_step,
    _worker_error_response,
)


# ---------------------------------------------------------------------------
# flextools_parse_text (CP3, US2)
# ---------------------------------------------------------------------------

#: Carried on every READ-ONLY parse_text response (CP4 R-16, contracts s.1):
#: the tool is annotated destructive, and a caller deserves to know that this
#: call filed nothing. A filing run carries "started" instead.
FILING_NOT_REQUESTED = "not_requested"


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

    project_name, project_error = common._resolve_project(request.project_name)
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
            worker = _sandbox_worker_section(sandbox)
            result["in_flight"] = worker.get("in_flight_word")
            result["in_flight_index"] = worker.get("in_flight_index")
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
    from ...parse.runner import RunAlreadyTerminal

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
    from ...sandbox import classify as sandbox_classify

    lines = [r for r in (getattr(handle, "results", None) or [])
             if isinstance(r, dict) and isinstance(r.get("parse"), dict)
             and r["parse"].get("outcome")]
    try:
        outcomes = sandbox_classify.tally_outcomes(lines)
    except KeyError:
        outcomes = None
    worker = _sandbox_worker_section(sandbox)
    return {"outcomes": outcomes, "counters": worker.get("counters")}


def _sandbox_worker_section(sandbox: Dict[str, Any]) -> Dict[str, Any]:
    """`meta.sandbox.worker` (data-model 6.2), `{}` when absent."""
    worker = sandbox.get("worker")
    return worker if isinstance(worker, dict) else {}


def _sandbox_test_summary(handle, sandbox: Dict[str, Any]) -> Dict[str, Any]:
    """data-model 6.6's test block: classifications, engine_counters, agreement."""
    from ...sandbox import classify as sandbox_classify

    lines = [r for r in (getattr(handle, "results", None) or [])
             if isinstance(r, dict) and isinstance(r.get("assertion"), dict)]
    classifications = sandbox_classify.tally_classifications(lines)
    worker = _sandbox_worker_section(sandbox)
    counters = worker.get("engine_counters")
    counters = counters if isinstance(counters, dict) else None
    agreement: Optional[bool] = None
    if counters is not None:
        try:
            divergences = sandbox_classify.reconcile_test_counters(
                lines, sandbox_classify.TestCounters(**counters)
            )
            agreement = not divergences
        except Exception:  # noqa: BLE001 -- unreadable counters: agreement unknown
            agreement = None
    return {
        "classifications": classifications,
        "engine_counters": counters,
        "counter_agreement": agreement,
    }


# -- seed_corpus (contracts sections 3 and 5.3) -------------------------------


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
    project_name, project_error = common._resolve_project(args.get("project_name"))
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
            # Issue #315: numbered steps, like every project_locked refusal.
            next_steps=busy_own_worker_next_steps("retry flextools_parse_release"),
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
