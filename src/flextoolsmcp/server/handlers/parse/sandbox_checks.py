"""
flextools_parse_sandbox (CP5): the plan and check-order steps 1-7.

Every helper here that a test patches (`_sandbox_engine_check`,
`_sandbox_space_check`, `_sandbox_fwdata_path`, `_sandbox_config_path`) is
called from `sandbox.py` as `sandbox_checks.<name>(...)`, so one patch on
this module reaches both.
"""

import json
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ...models import ParseSandboxInput
from ...filing import paths as filing_paths

try:
    from ....response_utils import error_response
except (ImportError, ValueError):
    from response_utils import error_response

from . import common
from .common import (
    _rung,
    get_runner,
)
from .filing import (
    _holder_is_own_read_worker,
)


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

from ... import parser_probe  # noqa: E402 -- grouped with the CP5 section it serves
from ...response_models import (  # noqa: E402
    ParserToolMissingDetail,
    ParseSandboxRefusedDetail,
)
from ...sandbox import paths as sandbox_paths  # noqa: E402

#: contracts/tools.md section 4, verbatim. Both sandbox components --
#: FieldWorks' bundled HermitCrab and GenerateHCConfig.exe -- come from the
#: FieldWorks install and are repaired the same way, so they share one hint
#: (CP5 re-plan: there is no `hc` console tool to install any more).
FIELDWORKS_HERMITCRAB_INSTALL_HINT = parser_probe.FIELDWORKS_REPAIR_HINT
GENERATE_HC_CONFIG_INSTALL_HINT = parser_probe.FIELDWORKS_REPAIR_HINT
#: Fallback `expected_path`s when discovery reports none (the field is a str).
_GENERATE_HC_CONFIG_DEFAULT_PATH = (
    r"C:\Program Files\SIL\FieldWorks 9\GenerateHCConfig.exe"
)
_FIELDWORKS_HERMITCRAB_DEFAULT_PATH = (
    r"C:\Program Files\SIL\FieldWorks 9\SIL.Machine.Morphology.HermitCrab.dll"
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


def split_words(text: str) -> List[str]:
    """FR-014's split: `text` on runs of commas and whitespace, empties dropped.

    The one place a word-list string is split. It used to live in
    `hcparse.ps1`'s Parse mode; the sandbox worker receives the result as a
    JSON list, so no word is ever re-split or quoted downstream (T113).
    Apostrophes and every other non-separator character stay inside a word.
    """
    return [word for word in _WORD_SPLIT_RE.split(text) if word]

#: contracts/tools.md section 5.1, advisory codes and their fixed notes.
_ADVISORY_NOTES = {
    "sandbox_predates_project_grammar": (
        "This sandbox was made from an earlier state of the project's grammar; it "
        "was used exactly as it is."
    ),
    "grammar_load_errors": (
        "{n} grammar objects failed to load during export and are missing from "
        "this configuration."
    ),
    # FR-050: a config source older than the id-map sidecar. (The former
    # `leading_dash_unverified` is retired with the hc script's quoting.)
    "shaping_not_applied": (
        "This sandbox predates the id map, so FLEx's Try A Word display rules were "
        "not applied; morphs are shown unshaped. Re-create the sandbox from the "
        "current project to restore them."
    ),
}

#: Terminal failure codes re-emitted as their own envelopes (section 3, step 8).
_SANDBOX_FAILURE_CODES = ("parser_timeout", "parser_job_failed", "parser_config_failed",
                          "sandbox_unavailable")



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
    #: FieldWorks' bundled HermitCrab (`parser_probe.EngineDiscovery`, D7).
    engine: Any = None
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
        from ...sandbox import client as sandbox_client
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
    name, refusal = common._resolve_project(plan.request.project_name)
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
    from ...sandbox import store as sandbox_store

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
        return split_words(text), None
    words = request.words
    if isinstance(words, str):
        return split_words(words), None
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
    return [
        _rung(
            action="Repair or reinstall FieldWorks 9.",
            tool=None,
            args=None,
            rationale=(
                f"{component} is required for this action and was not found in "
                "the FieldWorks install. Nothing was copied or created."
            ),
            est_cost="minutes",
        ),
        _rung(
            action="Check the sandbox components' status.",
            tool="flextools_health",
            args={"verbose": True},
            rationale=(
                "flextools_health reports each sandbox component "
                "(fieldworks_hermitcrab, GenerateHCConfig.exe) with where it "
                "was looked for."
            ),
            est_cost="seconds",
        ),
    ]


def _tool_missing(component: str, expected_path: str, message: str) -> List[TextContent]:
    detail = ParserToolMissingDetail(
        component=component,
        expected_path=expected_path,
        install_hint=(
            FIELDWORKS_HERMITCRAB_INSTALL_HINT
            if component == parser_probe.COMPONENT_FIELDWORKS_HERMITCRAB
            else GENERATE_HC_CONFIG_INSTALL_HINT
        ),
    )
    return error_response(
        "parser_tool_missing",
        message,
        **_sandbox_detail_kwargs(detail),
        next_step=_tool_missing_rungs(component),
    )


def _sandbox_check_tools(plan: _SandboxPlan) -> Optional[List[TextContent]]:
    """Step 3: the engine check (D6/D7, FR-007). FieldWorks' bundled
    HermitCrab first, then GenerateHCConfig.exe.

    A presence-plus-`FileVersion` read only: nothing is spawned and the
    engine is not loaded (an engine that will not load fails the run's
    first parse as `engine_unavailable`). GenerateHCConfig.exe is looked up
    only when generation may run, so a named sandbox's parse never blames
    it.
    """
    engine = parser_probe.discover_fieldworks_hermitcrab()
    if not getattr(engine, "found", getattr(engine, "ok", False)):
        expected = getattr(engine, "expected_path", None) or _FIELDWORKS_HERMITCRAB_DEFAULT_PATH
        reason = getattr(engine, "reason", None)
        message = (
            "FieldWorks' HermitCrab engine (SIL.Machine.Morphology.HermitCrab.dll) "
            "was not found" + (f": {reason}." if reason else ".")
        )
        return _tool_missing(parser_probe.COMPONENT_FIELDWORKS_HERMITCRAB, str(expected), message)
    plan.engine = engine

    if _sandbox_generation_may_run(plan.request):
        ghc = parser_probe.discover_generate_hc_config()
        if not getattr(ghc, "ok", False):
            expected = getattr(ghc, "expected_path", None) or _GENERATE_HC_CONFIG_DEFAULT_PATH
            return _tool_missing(
                "GenerateHCConfig.exe",
                str(expected),
                "GenerateHCConfig.exe was not found; it is needed to export the "
                "project's grammar for the sandbox.",
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
    from ...sandbox import engine as sandbox_engine

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
                action="Switch the project's parser to HermitCrab in FLEx.",
                tool=None,
                args=None,
                rationale=(
                    "The engine check reads the project's saved parser setting; "
                    "a grammar for another engine cannot be exported for HermitCrab."
                ),
                est_cost="minutes",
            ),
            _sandbox_list_rung(plan.project_name),
        ],
    )


# -- step 5 ----------------------------------------------------------------


def _sandbox_access(plan: _SandboxPlan) -> None:
    """Step 5 (FR-040, R-13): lock metadata only. NEVER refuses."""
    access = common._probe_access(plan.project_name)
    verdict = getattr(access, "verdict", None)
    plan.project_state = {"access": verdict}
    if verdict == "held_by_other" and _sandbox_holder_is_own_worker(plan.project_name, access):
        # Pattern audit sweep 3: the holder is this server's own read-only
        # worker, which has no unsaved edits -- the .fwdata on disk is what
        # it read, so the run's grammar is not unverifiable.
        return None
    if verdict in SANDBOX_STALENESS_VERDICTS:
        from ...parse.diff import SHARED_MODE_STALENESS

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
    from ...sandbox import cache as sandbox_cache
    from ...sandbox import workdir as sandbox_workdir

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
