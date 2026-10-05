"""
flextools_parse_sandbox (CP5): step 8, the run envelope, and the handler.
"""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ...models import ParseSandboxInput
from ...parse.record import MetaUnreadable
from ...parse.stages import RunStage
from ...parse.worker_client import WorkerError
from ...sandbox import paths as sandbox_paths

try:
    from ....response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

from . import common, sandbox_checks
from .common import (
    _grammar_scan_rung,
    _read_run_rung,
    _rung,
    get_runner,
    json_response,
)
from .run_log import (
    _run_not_found,
    _run_record_unreadable,
)
from .runs import (
    _sandbox_summary_block,
)
from .sandbox_checks import (
    SANDBOX_ENGINE,
    SANDBOX_RESULTS_LABEL,
    _ADVISORY_NOTES,
    _SANDBOX_FAILURE_CODES,
    _SandboxPlan,
    _ensure_next_step,
    _sandbox_access,
    _sandbox_check_root,
    _sandbox_check_tools,
    _sandbox_detail_kwargs,
    _sandbox_list_rung,
    _sandbox_name_refusal,
    _sandbox_read_words,
    _sandbox_refused,
    _sandbox_resolve_project,
    _sandbox_resolve_source,
    _sandbox_role,
    _sandbox_run_engine_check,
    _sandbox_store,
)
from .summary import (
    _batch_block,
    _failure_rungs,
    _result_summary,
    _status_next_step,
    _worker_error_response,
)




# -- step 8 and the section 5.1 envelope ------------------------------------


def _sandbox_fingerprint(plan: _SandboxPlan) -> Dict[str, Any]:
    """R-14: `scope_kind="words"`, `engine="HC"`, comparable with in-process.

    `vernacular_ws` is not known without opening the project; it is left
    empty rather than guessed (a diff reconciles it -- US6).
    """
    from ...parse.fingerprint import ScopeFingerprint

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
    from ...sandbox import script as sandbox_script

    try:
        hcparse = sandbox_script.read_hcparse_version()
    except Exception:  # noqa: BLE001
        hcparse = None
    return {
        "fieldworks_hermitcrab": getattr(plan.engine, "file_version", None),
        "generate_hc_config": None,
        "hcparse": hcparse,
    }


def _sandbox_launch(plan: _SandboxPlan) -> Dict[str, Any]:
    """What the client needs to run: config source, generator, timeout (T102)."""
    request, project_name = plan.request, plan.project_name
    fwdata = sandbox_checks._sandbox_fwdata_path(project_name)
    config_path = (
        str(sandbox_checks._sandbox_config_path(project_name, request.sandbox))
        if request.sandbox is not None else None
    )
    return {
        "fwdata_path": str(fwdata) if fwdata is not None else None,
        "generate_hc_config_path": (
            getattr(plan.generator, "expected_path", None) if plan.generator else None
        ),
        "config_path": config_path,
        "sandbox_name": request.sandbox,
        # FR-047 source 2 for a named sandbox (T115): its origin's project.
        **_sandbox_origin(project_name, request.sandbox),
        "timeout_seconds": request.timeout_seconds,
        # run_corpus (Test mode, T072): the corpus JSON the client classifies against.
        "assertion_file": str(plan.corpus.path) if plan.corpus is not None else None,
        # D6: the FieldWorks folder step 3 found the engine in, for the
        # worker's AssemblyResolve handler.
        "engine_dir": _sandbox_engine_dir(plan),
    }


def _sandbox_engine_dir(plan: _SandboxPlan) -> Optional[str]:
    """The directory holding the bundled HermitCrab DLL step 3 found, or None."""
    engine = getattr(plan, "engine", None)
    path = getattr(engine, "expected_path", None) if engine is not None else None
    if not path or not getattr(engine, "found", getattr(engine, "ok", False)):
        return None
    return str(Path(path).parent)


def _sandbox_origin(project_name: str, name: Optional[str]) -> Dict[str, Any]:
    """A named sandbox's originating project and its live `.fwdata` (T115).

    `origin.json` records the project the sandbox was made from (data-model
    section 4). `origin_fwdata_path` is set only when that project still
    resolves to an existing `.fwdata`; the client stream-reads its
    `ParserParameters/HC` from there (FR-047, `parameters_source:
    "live_project"`), with no LCM, no lock and no engine check. Nothing
    here opens or reads the project. `{}` for a project-cache run.
    """
    if name is None:
        return {}
    from ...sandbox import store as sandbox_store

    origin = sandbox_store.read_origin(project_name, name) or {}
    origin_project = origin.get("project") if isinstance(origin.get("project"), str) else None
    fwdata = sandbox_checks._sandbox_fwdata_path(origin_project) if origin_project else None
    return {
        "origin_project": origin_project,
        "origin_fwdata_path": str(fwdata) if fwdata is not None and fwdata.is_file() else None,
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


def _sandbox_advisories(sandbox: Dict[str, Any], handle) -> List[Dict[str, Any]]:
    """Advisory codes (a list in meta) as `{code, note}` with the fixed notes."""
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
                n=generation.get("load_error_count") or 0,
            )
        out.append({"code": code, "note": note})
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
    from ...parse.diff import SHARED_MODE_NOTE

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
    from ...sandbox import cache as sandbox_cache
    from ...sandbox import script as sandbox_script
    from ...sandbox import workdir as sandbox_workdir

    request, project_name = plan.request, plan.project_name
    name = request.sandbox
    fwdata = sandbox_checks._sandbox_fwdata_path(project_name) or Path(f"{project_name}.fwdata")
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
    except sandbox_script.HcparseVersionError as bad_script:
        # Issue #322: an unreadable hcparse.ps1 (the logged incident was a
        # transient checkout state) means the sandbox engine is unavailable,
        # not that this call is broken -- an envelope, never HANDLER EXCEPTION.
        return error_response(
            "sandbox_unavailable",
            "The sandbox engine is unavailable: the packaged hcparse.ps1 "
            f"could not be read ({bad_script}).",
            script_path=str(sandbox_script.script_path()),
            hint=(
                "The packaged script ships with the flextoolsmcp installation; "
                "reinstall or repair the package. Nothing about the project "
                "needs fixing."
            ),
            run_id=None,  # no run exists for create_sandbox
            next_step=[
                _grammar_scan_rung(project_name),
                _rung(
                    action="Check the environment and the sandbox components.",
                    tool="flextools_health",
                    args={"verbose": True},
                    rationale=(
                        "Health reports where the sandbox components were found; "
                        "a missing packaged script is a broken installation."
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
            path=str(sandbox_checks._sandbox_config_path(project_name, name)),
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


def _sandbox_seed(plan: _SandboxPlan) -> List[TextContent]:
    """Seed a corpus from a completed sandbox parse run. Synchronous; no run.

    The store checks, in order: the run exists (`parse_run_not_found`); it is
    a completed sandbox PARSE run of this project (`run_not_seedable`); the
    name is valid and new (`name_invalid` / `corpus_exists`).
    """
    from ...parse.record import RunRecord

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
    runner = common._runner
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
        refusal = sandbox_checks._sandbox_space_check(request, plan.project_name)  # 7
        if refusal is not None:
            return refusal
        return await _sandbox_create(plan)                          # sync, no run

    _sandbox_access(plan)                                           # 5 (never refuses)
    if request.action == "run_corpus":
        refusal = _sandbox_load_corpus(plan)                        # 6
        if refusal is not None:
            return refusal
    refusal = sandbox_checks._sandbox_space_check(request, plan.project_name)      # 7
    if refusal is not None:
        return refusal
    return await _sandbox_start_parse(plan)                         # 8
