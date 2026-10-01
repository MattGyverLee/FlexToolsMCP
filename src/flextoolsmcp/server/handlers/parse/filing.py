"""
flextools_parse_text(apply=true): the filing request path (CP4).
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ...models import ParseTextInput, ResolvedScope
from ...parse.fingerprint import build_fingerprint
from ...parse.priority import Priority
from ...parse.worker_client import SHARED_ROLE, WorkerError

try:
    from ....response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

from .common import (
    _read_run_rung,
    _rung,
    get_runner,
    json_response,
    session_state,
)
from .summary import (
    _status_next_step,
    _worker_error_response,
)


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
    from ....config import (
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

from ... import write_ladder  # noqa: E402 -- grouped with the CP4 section it serves
from ...filing import claims as filing_claims  # noqa: E402
from ...filing import filer as filing_filer  # noqa: E402
from ...filing import paths as filing_paths  # noqa: E402
from ...filing import plan as filing_plan  # noqa: E402
from ...filing import projection as filing_projection  # noqa: E402
from ...filing import wording as filing_wording  # noqa: E402

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
from ...parse.own_worker import (  # noqa: E402
    BUSY as OWN_WORKER_BUSY,
    COEXISTS as OWN_WORKER_COEXISTS,
    HELD_BY_OWN_READ_WORKER,
    busy_own_worker_refusal,
    own_worker_role,
    settle_own_worker_hold,
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
    from ...filing import gate as filing_gate

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


# The preview's per-wordform GUID lists grow with the project: an all_texts
# preview of 26k words named 24k GUIDs, 3.4 MB, which no reader reviews and no
# client keeps in context. Past these sizes the RESPONSE carries a sample and a
# summary, and the full plan is written to a file beside the run records. The
# plan itself -- what the session stores and plan_id binds -- is unchanged.
_PREVIEW_INLINE_GUIDS = 200
_PREVIEW_SAMPLE_WORDFORMS = 20
_PREVIEW_INLINE_WORDS = 50
_PREVIEW_PLANS_KEPT = 20


def _write_plan_detail(plan: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
    """Write the full plan to `<record dir>/plans/<plan_id>.json`.

    The plans dir is a sibling of the run dirs; run ids are 32 hex, so
    run-listing never mistakes it for a run.

    `plan_id` is server-computed hex, never caller input, so it is safe as a
    file name. The file is outside any project (FR-042) and only the newest
    `_PREVIEW_PLANS_KEPT` are kept. A failed write is reported, not raised:
    the preview still stands, it just cannot point at the full lists.
    """
    import os
    from ...parse.record import get_record_dir

    try:
        record_root = get_runner().record_dir or get_record_dir()
        plans_dir = filing_paths.assert_outside_project(record_root / "plans")
        plans_dir.mkdir(parents=True, exist_ok=True)
        path = plans_dir / f"{plan_id}.json"
        tmp = plans_dir / f"{plan_id}.json.tmp"
        tmp.write_text(
            json.dumps({"plan_id": plan_id, "plan": plan}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        stale = sorted(plans_dir.glob("*.json"), key=lambda p: p.stat().st_mtime,
                       reverse=True)[_PREVIEW_PLANS_KEPT:]
        for old in stale:
            try:
                old.unlink()
            except OSError:
                pass
        return {"full_plan_path": str(path)}
    except Exception as exc:  # noqa: BLE001 -- the preview must not fail on this
        return {"full_plan_unavailable": f"{type(exc).__name__}: {exc}"}


def _compact_by_wordform(block: Dict[str, Any]) -> Dict[str, Any]:
    """`block` with `by_wordform` replaced by a sample and a summary."""
    by_wordform = block.get("by_wordform") or {}
    sample = dict(list(by_wordform.items())[:_PREVIEW_SAMPLE_WORDFORMS])
    out = {k: v for k, v in block.items() if k != "by_wordform"}
    out["by_wordform_sample"] = sample
    out["by_wordform_summary"] = {
        "wordforms": len(by_wordform),
        "analyses": sum(len(g) for g in by_wordform.values()),
        "sample_wordforms": len(sample),
    }
    return out


def _preview_plan(plan: Dict[str, Any], plan_id: str) -> Dict[str, Any]:
    """The plan as the preview response shows it: whole when small, else compact."""
    deletion = plan["deletion_projection"]
    overwrites = plan.get("disapproval_overwrites") or {}
    unreadable = list(deletion.get("words_unreadable") or [])

    def guids(block: Dict[str, Any]) -> int:
        return sum(len(g) for g in (block.get("by_wordform") or {}).values())

    big_deletion = guids(deletion) > _PREVIEW_INLINE_GUIDS
    big_overwrites = guids(overwrites) > _PREVIEW_INLINE_GUIDS
    big_unreadable = len(unreadable) > _PREVIEW_INLINE_WORDS
    if not (big_deletion or big_overwrites or big_unreadable):
        return plan

    view = dict(plan)
    view_deletion = _compact_by_wordform(deletion) if big_deletion else dict(deletion)
    if big_unreadable:
        view_deletion["words_unreadable"] = unreadable[:_PREVIEW_INLINE_WORDS]
        view_deletion["words_unreadable_count"] = len(unreadable)
    view["deletion_projection"] = view_deletion
    if big_overwrites:
        view["disapproval_overwrites"] = _compact_by_wordform(overwrites)
    view["detail"] = {
        **_write_plan_detail(plan, plan_id),
        "note": ("This response shows a sample of each long list; the full lists "
                 "are in the plan file. plan_id binds the full plan, not the sample."),
    }
    return view


def _confirmation_required(
    plan: Dict[str, Any], plan_id: str, request: ParseTextInput, *, reason: str
) -> List[TextContent]:
    """Row 10: the preview. Carries the plan and its id; writes nothing to the
    project. A large plan is shown compact, its full form in a file (above)."""
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
        plan=_preview_plan(plan, plan_id),
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
            next_step=[
                _rung(
                    action="Run Try a Word once in FieldWorks with HC active, "
                    "then ask for the filing preview again.",
                    tool="flextools_parse_text",
                    args={"project_name": project_name, "apply": True},
                    rationale=(
                        "FieldWorks does not create the HermitCrab agent when a "
                        "project is bootstrapped; running one word in FieldWorks "
                        "creates it. An unconfirmed apply=true call re-runs this "
                        "agent probe and at most returns a preview -- it files "
                        "nothing. flextools_health cannot confirm it: health "
                        "never opens a project, so it never probes the agent."
                    ),
                    est_cost="minutes",
                ),
            ],
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
    from ...parse.fingerprint import fingerprint_key

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
        from ...parse.worker_client import SHARED_ROLE

        await runner.release_worker(project_name, role=SHARED_ROLE)
        decision = write_ladder.probe_write_access(project_name)
    if decision.refusal is not None:
        # Issue #315: the refusal below says the holder is NOT one of our
        # workers, so rule out every role here, not just SHARED_ROLE above
        # (e.g. the measurement worker) -- the same core run_module's write
        # gate uses. Busy: refuse as ours. Idle: release and re-probe.
        # Shared project: coexists, as SHARED_ROLE already does at row 8.
        outcome, role, decision = await settle_own_worker_hold(
            runner, project_name, decision, write_ladder.probe_write_access
        )
        if outcome == OWN_WORKER_BUSY:
            message, fields = busy_own_worker_refusal(
                runner, project_name, role, decision,
                "re-send the confirmed filing call",
                message_suffix=" Nothing was written.",
            )
            return error_response("project_locked", message, **fields)
        if outcome == OWN_WORKER_COEXISTS:
            decision = write_ladder.AccessDecision(
                project_name=project_name, access=decision.access,
                verdict=HELD_BY_OWN_READ_WORKER)
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
    from ...parse.record import get_record_dir

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
        from ...parse.worker_client import SHARED_ROLE

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
    from ...filing.client import FILING_ROLE
    from ...filing.observer import FilingObserver

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
    if decision.verdict == "open_shared":
        result["shared_mode_advisory"] = filing_wording.SHARED_MODE_ADVISORY
    elif shared:
        # Sharing is on but FieldWorks does not hold the project (e.g. only
        # this server's own read worker does): don't claim FLEx has it open.
        result["shared_mode_advisory"] = filing_wording.SHARING_ENABLED_ADVISORY
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
    from ... import backup as backup_mod

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
