#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin handler functions for FlexToolsMCP.

These handlers manage session configuration and provide admin tools:
- start: Initialize session with mode and project settings
- manage_config: Get/set/delete/list persistent configuration (Feature 2)
- get_session_history: View operation history (Feature 3)
- get_module_template: Return the official FlexTools module template
- refresh_indexes: Rebuild the bundled API indexes (the refresh pipeline)
"""

import asyncio
import contextlib
import io

from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps, safe_import_session_state, safe_import_logging_helpers
from ..response_keys import (
    KEY_MESSAGE, KEY_STATUS, KEY_SESSION, KEY_ERROR, KEY_SOURCE,
    KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED, KEY_HISTORY,
    KEY_TEMPLATE, KEY_WARNINGS
)

try:
    from ...response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

try:
    from ..progress import get_progress_reporter, progress_heartbeat
except (ImportError, ValueError):
    from server.progress import get_progress_reporter, progress_heartbeat

try:
    from ...file_utils import get_bundled_templates_dir
except (ImportError, ValueError):
    from file_utils import get_bundled_templates_dir

try:
    from ...workspace_check import get_workspace_notice, warning_line as _workspace_warning_line
except (ImportError, ValueError):
    from workspace_check import get_workspace_notice, warning_line as _workspace_warning_line


def _ops_logger():
    """Return the shared operations logger (or None before init).

    Routes template-resolution diagnostics into the same operations.log /
    per-session trace as [TOOL CALL] records, instead of a detached
    module-level logger that would never reach those file handlers.
    """
    try:
        from ..kernel import get_operations_logger
    except ImportError:
        from server.kernel import get_operations_logger
    return get_operations_logger()

try:
    from ..project_discovery import (
        normalize_project_name,
        project_not_found_fields,
        resolve_or_explain,
    )
except (ImportError, ValueError):
    from server.project_discovery import (
        normalize_project_name,
        project_not_found_fields,
        resolve_or_explain,
    )

try:
    from ..startup_notices import get_index_refresh_failures
except (ImportError, ValueError):
    from server.startup_notices import get_index_refresh_failures

try:
    from ..diagnostic import transports as _transports
except (ImportError, ValueError):
    from server.diagnostic import transports as _transports

try:
    from ..constants import API_MODES, API_MODES_DEFAULT, EXECUTION_API_MODE, normalize_api_mode
except ImportError:
    from server.constants import API_MODES, API_MODES_DEFAULT, EXECUTION_API_MODE, normalize_api_mode

# Import kernel dependencies with fallback support
json_response, session_state, get_log_dir, get_api_index = safe_import_kernel_deps()
rotate_logging_to_session, _ = safe_import_logging_helpers()
SessionState = safe_import_session_state()

# Do NOT recreate session_state on a failed isinstance check. Dual-path
# imports (server.session vs flextoolsmcp.server.session) can briefly make
# the same object look like a different class; replacing it here reintroduces
# the #10 split-brain this module is supposed to share with the kernel.


# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
# Shared constants imported from response_keys:
# - KEY_MESSAGE, KEY_STATUS, KEY_SESSION, KEY_ERROR, KEY_SOURCE
# - KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED, KEY_HISTORY
# - KEY_TEMPLATE, KEY_WARNINGS (above)

# Admin-specific constants
KEY_ACTION = "action"
KEY_KEY = "key"
KEY_VALUE = "value"
KEY_CONFIG = "config"
KEY_INITIALIZED = "session_initialized"
KEY_API_MODE = "api_mode"
KEY_OPERATIONS = "operations"
KEY_INCLUDE_OPERATIONS = "include_operations"
KEY_NEXT_STEPS = "next_steps"
KEY_MODE_INFO = "mode_info"
KEY_FLAVOR = "flavor"
KEY_GUIDANCE = "guidance"
KEY_STYLE_GUIDE = "style_guide"

# Template flavors mapping
TEMPLATE_MAP = {
    "flexicon": "2-flexicon-template.py",
    "flexlibs_stable": "1-flexlibs-stable-template.py",
    "liblcm": "3-liblcm-template.py",
    "stable": "1-flexlibs-stable-template.py",  # Alias
    "advanced": "3-liblcm-template.py",  # Alias
    "flexlibs2": "2-flexicon-template.py",  # Deprecated alias for 'flexicon'
}

# Template guidance (static data, not rebuilt per request)
FLAVOR_GUIDANCE = {
    "flexicon": {
        "description": "Recommended - Best documented, 90% API coverage",
        "use_when": "For most projects with FieldWorks 9.0+",
        "advantages": [
            "Automatic '***' multistring normalization",
            "Better error messages",
            "Comprehensive coverage (~200 functions)",
            "Well documented with many examples"
        ]
    },
    "flexlibs_stable": {
        "description": "Legacy - Limited but stable",
        "use_when": "For FieldWorks < 9.0 or when flexicon not available",
        "advantages": [
            "Works with older FieldWorks versions",
            "Limited API (~40 functions) but stable",
            "Good for simple read-only operations"
        ]
    },
    "liblcm": {
        "description": "Advanced - Full API access",
        "use_when": "For edge cases not covered by flexicon",
        "advantages": [
            "100% API coverage",
            "Direct C# access for complex operations",
            "Performance-critical code"
        ],
        "warning": "Complex code, hard to maintain. Use flexicon first."
    }
}

# Mode guidance for API initialization
MODE_GUIDANCE = {
    "flexicon": {
        "description": "Flexicon - Pythonic wrapper with Operations classes",
        "example": "project.LexEntries.GetAll(), project.Wordforms.GetForm(wf)",
        "note": "Recommended mode - best documentation and examples"
    },
    "flexlibs_stable": {
        "description": "FlexLibs Stable - Original wrapper with LibLCM fallback",
        "example": "project.LexiconAllEntries(), entry.SensesOS",
        "note": "Use when compatibility with existing scripts needed"
    },
    "liblcm": {
        "description": "Pure LibLCM - Direct C# API access via pythonnet",
        "example": "entry.SensesOS, sense.Gloss.get_String(wsHandle)",
        "note": "Low-level access - requires understanding of LCM suffixes (OS/OC/OA/RS/RC/RA)"
    }
}

_EXECUTION_API_MODE_NOTE = (
    "flextools_run_module always executes with flexicon imports regardless of "
    "api_mode. Use flexlibs_stable or liblcm here to steer API discovery "
    "(search_by_capability, get_object_api) and preflight import checks; write "
    "flexicon-compatible code for execution."
)


def _build_mode_info(api_mode: str) -> dict:
    """Return mode guidance plus an explicit execution seam (issue #164)."""
    info = dict(MODE_GUIDANCE[api_mode])
    info["selected_api_mode"] = api_mode
    info["execution_api_mode"] = EXECUTION_API_MODE
    info["execution_note"] = _EXECUTION_API_MODE_NOTE
    return info

# Runtime invariants - true for both lightweight ops (bare snippets) and full
# FlexTools modules. Emitted in start()'s response so the assistant sees these
# BEFORE writing any code. Saves a Dennis-style debugging arc where the AI
# reinvents reporters, write guards, or '***' placeholder handling because it
# never learned the runtime contract.
RUNTIME_PRIMER = {
    "output": {
        "description": "Use report.* for all user-facing output. Both lightweight ops and modules use the same API.",
        "methods": [
            "report.Info(msg, ref=None)",
            "report.Warning(msg, ref=None)",
            "report.Error(msg, ref=None)",
            "report.Blank()",
        ],
        "example": 'report.Info(f"Updated {entry_hw}", project.BuildGotoURL(sense))',
        "note": "Plain print() also works but bypasses message counts and ref links. Prefer report.*",
        "do_not_rebind": (
            "Do NOT redefine `report` or `project` (e.g. `report = SafeReporter(report)`). "
            "The runner already handles unicode-safe stdout; wrappers are unnecessary and "
            "obscure the contract. The injected `report` and `project` are the canonical "
            "objects - use them directly."
        ),
    },
    "clickable_refs": {
        "description": "Pass a goto URL as the second argument to make a message clickable in FlexTools UI.",
        "pattern": "project.BuildGotoURL(obj) -> str",
        "example": 'report.Info("Found match", project.BuildGotoURL(sense))',
        "note": "obj must be a concrete LCM object (entry, sense, example, ...) - not an HVO or string.",
    },
    "write_protection": {
        "description": "Every database mutation MUST be guarded by `if modifyAllowed:`. Unguarded mutations are refused at validation time before execution.",
        "lightweight_op_form": (
            "modifyAllowed is exposed as a top-level namespace variable. "
            "Use:  if modifyAllowed:  sense.Gloss.set_String(ws, 'new gloss')"
        ),
        "module_form": (
            "modifyAllowed is the third positional parameter of Main. "
            "Use:  def Main(project, report, modifyAllowed):  if modifyAllowed:  sense.Gloss.set_String(ws, 'new gloss')"
        ),
        "note": "modifyAllowed reflects the write_enabled flag set in start(). False by default (dry-run safe).",
    },
    "multistring_placeholder": {
        "description": "FLEx stores '***' as the placeholder for unset multilingual string fields (Gloss, Definition, Form, ...).",
        "wrapper_behavior": (
            "Flexicon wrapper getters normalize '***' to '' so `if not gloss:` works. "
            "Use:  gloss = LexSenseOperations(project).GetGloss(sense)  # '' if empty"
        ),
        "raw_csharp_behavior": (
            "Direct C# property access still returns '***'. Check explicitly: "
            "raw = sense.Gloss.BestAnalysisAlternative.Text; "
            "if raw == '***': raw = ''"
        ),
        "note": "Prefer wrapper getters. Mixing the two styles in one script is the most common source of empty-string bugs.",
    },
    "hvo_stability": {
        "description": (
            "An hvo is valid only WITHIN a single flextools_run_module call. It is "
            "a session-scoped handle, not a durable identifier -- liblcm renumbers "
            "it on every cache load. To refer to an object ACROSS calls, carry its "
            "GUID and re-resolve -- liblcm guarantees identity only by GUID."
        ),
        "why": (
            "liblcm says this outright, verbatim, in three files including "
            "src/SIL.LCModel/Application/Impl/DomainDataByFlid.cs:40-44: "
            "\"The hvo values are true 'handles' in that they are valid for one "
            "session, but may not be the same integer for another session for the "
            "'same' object. Therefore, one should not use them for multi-session "
            "identity. CmObject identity can only be guaranteed by using their "
            "Guids (or using '==' in code).\" Field evidence (issue #103): 2440/2440 "
            "entry hvos changed between two consecutive READ-ONLY run_module calls "
            "with zero writes between them; 0/2440 guids changed. A stale hvo does "
            "NOT raise an error -- it resolves to a real, different, live object, so "
            "a write built on it silently lands on the wrong entry."
        ),
        "round_trip": (
            "GetGuid(obj) -> str is the forward direction (already documented per-"
            "Operations-class). project.Object(hvo_or_guid) is the INVERSE -- it "
            "accepts an int (hvo, same-run only), a str GUID, or a System.Guid, and "
            "resolves to the live CmObject. Prefer the str-GUID form when crossing "
            "a call boundary: project.Object(guid_str). project.Object(guid_str) "
            "returns an uncast ICmObject -- cast it to the concrete interface "
            "(e.g. ILexEntry(obj)) before raw property access, or pass it to an "
            "operations method."
        ),
        "pattern": (
            "Call 1: guid = project.LexEntry.GetGuid(entry); report.Info(headword, "
            "project.BuildGotoURL(entry))  # stash the GUID string, not entry.Hvo\n"
            "Call 2: entry = project.Object(guid_str)  # NOT project.Object(stale_hvo_int)"
        ),
        "note": (
            "An hvo read and used WITHIN the same run_module call (e.g. "
            "`entry.Hvo` passed straight into another call in the same script) is "
            "fine -- the cache load is stable for the life of one call. The risk is "
            "specifically an integer literal or a value carried in from a PRIOR "
            "call or the FLEx UI."
        ),
    },
    "shared_mode_read_back": {
        "description": (
            "In FLEx's shared-mode setup, a fresh read-only session under a live "
            "FLEx master shows the last master save, not your write."
        ),
        "why": (
            "FieldWorks project sharing uses a shared commit log "
            "(SharedXMLBackendProvider). Exactly one peer is the 'master', "
            "responsible for writing the on-disk .fwdata file; every other peer's "
            "commit lands only in the shared commit log, not on disk. A brand-new "
            "session's startup reads the .fwdata file (ReadInSurrogates) and never "
            "replays commit-log records -- it registers at the file's last-written "
            "generation and stops there. So a write made by a non-master peer is "
            "durable and visible to other LIVE peers as soon as each of them next "
            "commits, but it is invisible to any FRESH, independent session until "
            "the master itself flushes the file. The master's own flush "
            "(SaveOnIdle) is gated on human actions in the FLEx UI (an idle period "
            "with no open edit and no pending-reconciliation prompt), so there is "
            "NO reliable interval and NO retry count that guarantees the write has "
            "become visible -- the window is unbounded, not merely long."
        ),
        "note": (
            "Do not treat a stale read-back as a dropped write: the data is safely "
            "in the shared commit log the whole time. Do not paper over this by "
            "polling a fresh session and waiting N seconds -- there is no N that is "
            "safe. In live testing (2026-10-01, exclusive-access-gate V5) a fresh "
            "session -- read-only, write-enabled, or write-enabled after "
            "SaveChanges() -- did see an MCP write, but only because FLEx sat idle "
            "and the master flushed the .fwdata right after the commit; that is "
            "the favourable case, not a guarantee, and SaveChanges() in the "
            "reading session made no difference. Instead, check "
            "the FLEx UI on the master peer -- it sees the write through its own "
            "live cache (Commit / ReconcileForeignChanges), not through a fresh "
            "read. If the write must be confirmed programmatically, that requires a "
            "session that stays open and calls Commit again; run_module cannot "
            "provide one."
        ),
    },
    "namespace_helpers": {
        "description": "These helpers are pre-injected into the execution namespace. No import required.",
        "available": [
            "is_empty_multistring(text) -> bool  # True for None, '', or '***'; "
            "also accepts a raw multistring object (resolves .Text, then "
            "BestAnalysisAlternative.Text, then BestVernacularAlternative.Text)",
            "FLEX_EMPTY_PLACEHOLDER  # the literal '***' constant",
            "find_writing_system(project, query) -> ws_handle | None  # substring search by name/tag",
            "list_writing_systems(project) -> [{'name', 'tag'}, ...]",
        ],
        "note": "Always available; do NOT redefine these at the top of your script.",
        "scope_warning": "MCP-runner only. If this code is saved as a FlexTools module file, the helpers will NOT exist when FlexTools loads it - inline copies or do not use them.",
    },
}

# Template cache (loaded once at module init, not per request)
_TEMPLATE_CACHE: dict[str, str] = {}


# ============================================================
# Helpers
# ============================================================
def _get_flavor_guidance(flavor: str) -> dict:
    """Get guidance for a flavor, handling aliases."""
    # Handle aliases
    if flavor in ["flexlibs_stable", "stable"]:
        flavor = "flexlibs_stable"
    elif flavor in ["liblcm", "advanced"]:
        flavor = "liblcm"
    return FLAVOR_GUIDANCE.get(flavor, FLAVOR_GUIDANCE["flexicon"])


_TESTED_AGAINST_LINE = '_TESTED_AGAINST = "unknown"'


def _stamp_tested_against(content: str) -> str:
    """Record the flexicon version this module is being generated against.

    The template ships with ``_TESTED_AGAINST = "unknown"``; this replaces it
    with the version actually installed here. The emitted module then carries
    a note about which version it was written against, and warns (never
    refuses) if it later runs somewhere older.

    Best-effort and non-fatal by design: if the line is absent (another
    flavor), or the version cannot be detected, the content is returned
    unchanged and the module simply skips its version note. A generated module
    must never fail to generate over a diagnostic nicety.
    """
    if _TESTED_AGAINST_LINE not in content:
        return content

    try:
        from ..versioning import detect_installed_library_version

        version = detect_installed_library_version(
            "Flexicon", import_path="flexicon", package_name="pyflexicon"
        )
    except Exception:
        version = None

    if not version:
        return content

    # Keep the stamp a plain literal: the template parses it with str.isdigit()
    # and skips the comparison on anything it cannot read.
    safe = str(version).strip().replace('"', "").replace("\\", "")
    if not safe:
        return content

    return content.replace(
        _TESTED_AGAINST_LINE, '_TESTED_AGAINST = "%s"' % safe, 1
    )


def _get_template(flavor: str) -> str | None:
    """Load and cache template file content (O(1) lookup after first call).

    Args:
        flavor: Template flavor (e.g., 'flexicon')

    Returns:
        Template file content, or None if not found

    Impact:
        Eliminates 50-100ms disk I/O on repeated requests by caching
        template files at module initialization instead of per-request read.
    """
    # Return cached result if available (O(1) lookup)
    if flavor in _TEMPLATE_CACHE:
        return _TEMPLATE_CACHE[flavor]

    # Not cached yet - load from disk and cache
    if flavor not in TEMPLATE_MAP:
        return None

    templates_dir = get_bundled_templates_dir()
    template_file = templates_dir / TEMPLATE_MAP[flavor]

    _log = _ops_logger()
    if not template_file.exists():
        if _log:
            _log.warning(
                "[TEMPLATE MISS] flavor='%s' not found on disk: %s "
                "(bundled templates dir: %s, exists=%s)",
                flavor, template_file, templates_dir, templates_dir.exists(),
            )
        return None

    try:
        with open(template_file, "r", encoding="utf-8") as f:
            content = f.read()
        _TEMPLATE_CACHE[flavor] = content
        return content
    except Exception:
        if _log:
            _log.exception("[TEMPLATE READ ERROR] %s", template_file)
        return None


def _resolve_inherited_flag(
    field: str,
    args: dict,
    user_provided: set,
    same_project: bool,
    default: bool = False,
):
    """Resolve a boolean session flag with explicit/inherit/default precedence.

    Used for write_enabled (and any future flag that should persist across
    same-project re-inits). Returns
    (value, inherited, downgraded) where:
        inherited  = prior session value was kept because no explicit value given
        downgraded = explicit value flipped a previously-True flag to False
                     (worth surfacing as a warning so the LLM can confirm intent)
    """
    explicit = field in user_provided
    prior = bool(getattr(session_state, field, default))
    if explicit or not same_project:
        value = args.get(field, default)
    else:
        value = prior
    inherited = same_project and not explicit and prior
    downgraded = explicit and prior and not value
    return value, inherited, downgraded


# Issue #318: keys handle_start acts on, plus the handler-level project
# alias and dispatch-injected bookkeeping keys. Anything else the caller
# passed is reported as ignored rather than silently dropped.
_START_KNOWN_PARAMS = frozenset({
    "api_mode", "task", "session_id", "project_name", "project",
    "output_type", "write_enabled", "user_request", "_user_provided_keys",
})


def _ignored_start_params(args: dict) -> list:
    """Caller-passed keys flextools_start does not act on (issue #318)."""
    return sorted(
        k for k in args
        if k not in _START_KNOWN_PARAMS and not k.startswith("_")
    )


def _build_index_health_offers() -> list[dict]:
    """Turn stashed index-refresh-failure notices into user-facing bug-report offers.

    Each offer carries a plain-language explanation plus prefilled GitHub and
    mailto links (built with the diagnostic transport helpers, so encoding,
    size-capping, and path normalization stay consistent). Empty list when the
    installed libraries all had a matching index -- the common case.
    """
    offers = []
    for note in get_index_refresh_failures():
        lib = note["library_name"]
        installed = note["installed_version"]
        served = note["served_version"] or "unknown"
        title = f"[index] {lib} v{installed} installed but no matching index (serving v{served})"
        summary = (
            f"{lib} v{installed} is installed, but the MCP has no index for that "
            f"version and auto-refresh could not generate one, so it is serving the "
            f"shipped v{served} index as a fallback. Documented APIs may not match "
            f"the installed library.\n\n"
            f"To help fix this, please include: your OS, how {lib} is installed "
            f"(pip/uvx/repo), and the output of "
            f"`python -m flextoolsmcp.refresh`."
        )
        github = _transports.build_github_issue_url(title, summary)
        mailto = _transports.build_mailto(title, summary)
        offers.append({
            "library": lib,
            "installed_version": installed,
            "served_version": note["served_version"],
            "message": summary,
            "report_github_url": github.get("url"),
            "report_mailto": mailto.get("uri"),
            "refresh_command": "python -m flextoolsmcp.refresh",
        })
    return offers


async def handle_start(args: dict) -> list[TextContent]:
    """Initialize a FlexTools MCP session with mode and project settings.

    This sets up the session for subsequent API discovery and operations.
    After calling start(), discuss the goal with the user, then use
    search_by_capability() or get_object_api() to discover the correct APIs.

    If project_name is provided, queries the project to list:
    - Available writing systems and their language tags
    - Number of entries in the project
    """
    raw_api_mode = args.get(KEY_API_MODE, API_MODES_DEFAULT)
    api_mode = normalize_api_mode(raw_api_mode)
    if api_mode not in API_MODES:
        return error_response(
            "invalid_api_mode",
            f"Unknown api_mode {raw_api_mode!r}. "
            f"Choose one of: {', '.join(API_MODES)}.",
            hint=(
                "Use api_mode='flexicon' for execution. flexlibs_stable and "
                "liblcm affect API discovery and preflight only until "
                "mode-conditional execution returns (#163)."
            ),
            allowed_modes=list(API_MODES),
            received=raw_api_mode,
            session=session_state.summary(),
        )
    # Note: Pydantic model uses 'project_name', not 'project'
    # Issue #311: a punctuation-only name ("``") means "no project yet", and
    # "`Sena 3`" is unwrapped to "Sena 3".
    project_name = (
        normalize_project_name(args.get("project_name") or args.get(KEY_PROJECT))
        or ""
    )
    # Diagnostic-report feature (spec section 4): verbatim human request text,
    # turn-level. Reset (not inherited) on every flextools_start call -- see
    # session.SessionState.configure().
    # Issue #318: `task` is an alias for `user_request` -- a caller passing
    # task="..." gets it honored instead of silently dropped. An explicit
    # user_request wins when both are given.
    task_value = args.get("task")
    user_request = args.get("user_request") or task_value or ""
    task_aliased = bool(task_value) and not args.get("user_request")

    # Fuzzy resolution: autocorrect case/whitespace-only typos, return a helpful
    # error (with suggestions) for bigger mismatches. Skipped when no name was
    # given -- that's a separately-valid "no project yet" state. Must run before
    # same_project so capitalization differences don't break session continuity.
    if project_name:
        resolved, err = resolve_or_explain(project_name)
        if err:
            return error_response(
                err["error_code"],
                err["message"],
                session=session_state.summary(),
                **project_not_found_fields(err),
            )
        if resolved and resolved != project_name:
            try:
                from ..kernel import get_operations_logger
            except ImportError:
                from server.kernel import get_operations_logger
            _autocorrect_logger = get_operations_logger()
            if _autocorrect_logger:
                _autocorrect_logger.info(
                    f"[SESSION-START] project_name autocorrected: "
                    f"{project_name!r} -> {resolved!r} (case/whitespace only)"
                )
            project_name = resolved

    user_provided = args.get("_user_provided_keys", set())
    same_project = (
        bool(session_state.initialized)
        and getattr(session_state, "project_name", "") == project_name
        and project_name != ""
    )

    # #9 fix: write_enabled persists across re-init on the same project.
    write_enabled, write_enabled_inherited, write_enabled_downgraded = (
        _resolve_inherited_flag("write_enabled", args, user_provided, same_project)
    )

    # Installed vs index-loaded snapshot (issue #149) -- not APIIndex.*_version,
    # which is the index file label and misreports under fallback_latest.
    try:
        from .diagnostic_health import build_session_api_versions
    except ImportError:
        from server.handlers.diagnostic_health import build_session_api_versions
    api_versions = build_session_api_versions()

    # Let configure() own session identity.  Passing project_name lets it
    # detect genuine project changes (new session boundary) vs re-starts on
    # the same project (session continuation -- discovery state preserved).
    # Do NOT pass a per-call timestamp as session_id; that minted a fresh uuid
    # on every restart and incorrectly wiped discovery state (P0 fix).
    # Issue #318: an explicit session_id token lets concurrent agents sharing
    # this process keep per-agent turn state (user_request); None (the common
    # case) leaves identity detection exactly as before.
    session_state.configure(
        api_mode=api_mode,
        output_type="auto",
        project_name=project_name,
        write_enabled=write_enabled,
        api_versions=api_versions,
        user_request=user_request,
        session_id=args.get("session_id"),
    )
    session_id = session_state.session_id

    # Diagnostic for #10: record identity of the configured session_state so
    # the next "Session not initialized" log line can be compared against this.
    try:
        from ..kernel import get_operations_logger, is_stateless_client_mode
    except ImportError:
        from server.kernel import get_operations_logger, is_stateless_client_mode
    _op_logger = get_operations_logger()
    if _op_logger:
        _op_logger.info(
            f"[SESSION-CONFIGURED] session_state_id={id(session_state)} "
            f"session_id={session_id} project={project_name!r} "
            f"api_mode={api_mode} write_enabled={write_enabled} "
            f"initialized={session_state.initialized}"
        )

    # Rotate logging to session-specific log file
    rotate_logging_to_session(session_id)

    # Note: Project metadata query removed from start handler
    # The FieldWorks registry access causes issues in start context but works fine
    # during execution. Users can discover project metadata by running:
    #   for ws_info in list_writing_systems(project):
    #       report.Info(f"{ws_info['name']} ({ws_info['tag']})")

    # Build response
    result = {
        KEY_STATUS: "session_initialized",
        KEY_SESSION: session_state.summary(),
        KEY_MESSAGE: "Session configured. Now discuss the goal with the user.",
        KEY_NEXT_STEPS: [
            "1. Discuss the task/goal with the user to understand requirements",
            "2. Use search_by_capability(query='...') to find relevant APIs",
            "3. Use get_object_api(object_type='...') to get detailed API info",
            "4. Write code using ONLY the discovered APIs",
            "5. Use run_module() to execute (accepts bare snippets and full Main-shaped modules)"
        ]
    }

    result[KEY_MODE_INFO] = _build_mode_info(api_mode)
    result["runtime_primer"] = RUNTIME_PRIMER

    # Warnings
    warnings = []
    # Issue #318: surface what the call asked for but this tool did not act on,
    # instead of silently dropping it.
    if task_aliased:
        warnings.append(
            "`task` is an alias for `user_request`; its value was used as this "
            "turn's user_request. Prefer `user_request` directly."
        )
    ignored_params = _ignored_start_params(args)
    if ignored_params:
        warnings.append(
            "Ignored unknown parameter(s): "
            + ", ".join(ignored_params)
            + ". They have no effect; check the spelling against the "
            "flextools_start schema."
        )
        result["ignored_params"] = ignored_params
    if api_mode != EXECUTION_API_MODE:
        warnings.append(
            f"api_mode={api_mode!r} sets documentation/preflight context only; "
            f"flextools_run_module executes with {EXECUTION_API_MODE!r}. "
            "Write flexicon-compatible code for execution."
        )

    # Workspace sanity first: if cwd is a library/MCP source checkout, every
    # later instruction in this response competes with a tempting pile of
    # readable source. Reported on every start (not once per process) -- the
    # session boundary is exactly where the setup can still be changed.
    workspace_notice = get_workspace_notice()
    if workspace_notice:
        warnings.append(_workspace_warning_line(workspace_notice))
        result["workspace_notice"] = workspace_notice

    if not project_name:
        warnings.append("No project_name set - will need to specify when running operations")
    if write_enabled:
        warnings.append("WRITE MODE ENABLED - operations will modify the database")
    if write_enabled_inherited:
        warnings.append(
            "write_enabled=True inherited from prior session on this project "
            "(no value was explicitly provided in this call)."
        )
    if write_enabled_downgraded:
        warnings.append(
            "write_enabled was downgraded True -> False on re-init. "
            "Was this intentional?"
        )
    # Index/version health: an installed library with no matching index that
    # auto-refresh could not regenerate. Surface a bug-report offer so the user
    # can report it (refresh is not yet fully reliable across environments).
    index_offers = _build_index_health_offers()
    for offer in index_offers:
        warnings.append(
            f"{offer['library']} v{offer['installed_version']}: no matching index "
            f"and auto-refresh failed; serving shipped v"
            f"{offer['served_version'] or '?'} (ballpark). Re-run "
            f"`{offer['refresh_command']}`, or report it: "
            f"{offer['report_github_url']} (or email: {offer['report_mailto']})."
        )
    if index_offers:
        result["index_health"] = index_offers

    if is_stateless_client_mode():
        warnings.append(
            "FLEXTOOLS_STATELESS=1: API discovery gates are skipped for every "
            "flextools_run_module call in this process (issue #142). Write-safety, "
            "casting, syntax, and unprotected_writes gates are unchanged."
        )
        result[KEY_MESSAGE] = (
            "Session configured (stateless client mode). flextools_start is "
            "optional for API discovery; flextools_run_module works without prior "
            "get_object_api when FLEXTOOLS_STATELESS=1 is set in the server env."
        )

    if warnings:
        result[KEY_WARNINGS] = warnings

    return json_response(result)


async def handle_manage_config(args: dict) -> list[TextContent]:
    """Manage persistent configuration (Feature 2).

    Actions:
    - get: Retrieve a config value by dotted key
    - set: Set a config value
    - delete: Delete a config key
    - list: List entire configuration
    """
    try:
        from ..config import config_get, config_set, config_delete, config_list
    except ImportError:
        from config import config_get, config_set, config_delete, config_list

    action = args.get(KEY_ACTION, "list")
    key = args.get(KEY_KEY, "")
    value = args.get(KEY_VALUE, None)

    try:
        if action == "get":
            if not key:
                return error_response(
                    "invalid_input",
                    "key parameter required for 'get' action",
                    action=action,
                    hint="Pass key='dotted.config.path' with action='get'.",
                )

            value = config_get(key)
            result = {
                KEY_STATUS: "ok",
                KEY_ACTION: action,
                KEY_SUCCESS: True,
                KEY_KEY: key,
                KEY_VALUE: value,
                KEY_MESSAGE: f"Retrieved config: {key}",
            }

        elif action == "set":
            if not key:
                return error_response(
                    "invalid_input",
                    "key parameter required for 'set' action",
                    action=action,
                    hint="Pass key='dotted.config.path' and value=... with action='set'.",
                )

            config_set(key, value)
            result = {
                KEY_STATUS: "ok",
                KEY_ACTION: action,
                KEY_SUCCESS: True,
                KEY_KEY: key,
                KEY_VALUE: value,
                KEY_MESSAGE: f"Set config: {key} = {value}",
            }

        elif action == "delete":
            if not key:
                return error_response(
                    "invalid_input",
                    "key parameter required for 'delete' action",
                    action=action,
                    hint="Pass key='dotted.config.path' with action='delete'.",
                )

            deleted = config_delete(key)
            result = {
                KEY_STATUS: "ok",
                KEY_ACTION: action,
                KEY_SUCCESS: deleted,
                KEY_KEY: key,
                KEY_MESSAGE: (
                    f"Deleted config key: {key}" if deleted else f"Config key not found: {key}"
                ),
            }

        elif action == "list":
            cfg = config_list()
            result = {
                KEY_STATUS: "ok",
                KEY_ACTION: action,
                KEY_SUCCESS: True,
                KEY_CONFIG: cfg,
                KEY_MESSAGE: f"Config contains {len(cfg)} root keys",
            }

        else:
            return error_response(
                "invalid_input",
                f"Unknown action: {action}. Use 'get', 'set', 'delete', or 'list'.",
                action=action,
                allowed_actions=["get", "set", "delete", "list"],
            )

    except Exception as e:
        return error_response(
            "server_state_error",
            f"Config operation failed: {e}",
            action=action,
        )

    return json_response(build_response_with_context(result))


async def handle_get_session_history(args: dict) -> list[TextContent]:
    """Get session history (Feature 3)."""
    result = {
        KEY_INITIALIZED: session_state.initialized,
        KEY_API_MODE: session_state.api_mode,
        KEY_PROJECT: session_state.project_name or "(not set)",
        KEY_WRITE_ENABLED: session_state.write_enabled,
    }

    # Add history summary
    history_summary = session_state.get_history_summary()
    result[KEY_HISTORY] = history_summary

    # Add operation list if requested
    if args.get(KEY_INCLUDE_OPERATIONS, False):
        result[KEY_OPERATIONS] = session_state.export_history()

    # Add helpful next steps
    if not session_state.initialized:
        result[KEY_NEXT_STEPS] = ["Call start() to initialize session"]
    else:
        result[KEY_NEXT_STEPS] = ["Run operations to build history"]

    return json_response(result)


async def handle_get_module_template(args: dict) -> list[TextContent]:
    """Return the official FlexTools module template from templates/ directory.

    This reads from the authoritative template files so they stay in sync with
    the style guide and documentation. Users get the recommended best practices
    directly, not a generic fallback.

    Uses module-level template cache to avoid repeated disk I/O (50-100ms savings).
    """
    flavor = args.get(KEY_FLAVOR, "flexicon")

    if flavor not in TEMPLATE_MAP:
        return json_response({
            KEY_ERROR: "invalid_flavor",
            KEY_MESSAGE: f"Unknown flavor '{flavor}'",
            "available_flavors": list(TEMPLATE_MAP.keys()),
            "recommended": "flexicon"
        })

    # Use cached template (O(1) lookup after first request)
    template_content = _get_template(flavor)

    # Stamp the generated module with the flexicon version it is being written
    # against, so a later bug report starts from that fact. The cache keeps the
    # raw file; only the emitted copy is stamped.
    if template_content is not None:
        template_content = _stamp_tested_against(template_content)

    if template_content is None:
        templates_dir = get_bundled_templates_dir()
        template_file = templates_dir / TEMPLATE_MAP[flavor]
        _log = _ops_logger()
        if _log:
            _log.error(
                "[TEMPLATE NOT FOUND] flavor=%s expected bundled file at %s "
                "(dir exists=%s)",
                flavor, template_file, templates_dir.exists(),
            )
        return json_response({
            KEY_ERROR: "template_not_found",
            KEY_MESSAGE: f"Template file not found: {template_file}",
            "hint": (
                "Templates ship as package data inside flextoolsmcp/templates. "
                "If this is a pip/uvx install, the wheel may be missing the "
                "bundled templates (reinstall or upgrade flextools-mcp)."
            ),
        })

    # Get guidance using helper (handles aliases cleanly)
    guidance = _get_flavor_guidance(flavor)

    result = {
        KEY_STATUS: "success",
        KEY_FLAVOR: flavor,
        KEY_TEMPLATE: template_content,
        KEY_SOURCE: f"templates/{TEMPLATE_MAP[flavor]} (authoritative)",
        KEY_GUIDANCE: guidance,
        KEY_STYLE_GUIDE: {
            "reference": "docs/FLEXTOOLS-STYLE-GUIDE.md",
            "key_sections": [
                "Section 1: Choose the Right Flavor",
                "Section 7: Write Permission Checking - CRITICAL (if modifyAllowed:)",
                "Section 8: Helper Functions",
                "Section 9: Ensure-or-Create Catalog Lookups (bulk imports: Find once, create under if modifyAllowed:, never per-row raise)",
                "Pattern: Always check modifyAllowed before ANY write"
            ]
        },
        KEY_NEXT_STEPS: [
            "1. Copy the template code above",
            "2. Replace [Placeholders] with your logic",
            "3. Pay special attention to 'if modifyAllowed:' guards",
            "4. Test in read-only mode first (modifyAllowed=False)",
            "5. Run flextools_run_module() when ready"
        ]
    }

    return json_response(result)




def _load_refresh_module():
    """Import flextoolsmcp.refresh lazily, inside the caller's stdout guard.

    refresh.py loads .env at import time and prints while doing so, and
    every pipeline step narrates to stdout. The MCP server never writes to
    stdout while serving (it is the JSON-RPC channel), so this module must
    not be imported at handler-module import time, and in-process callers
    must capture stdout around the import as well as the run.
    """
    try:
        from ... import refresh as refresh_module
    except (ImportError, ValueError):
        import refresh as refresh_module
    return refresh_module


async def handle_refresh_indexes(args: dict) -> list[TextContent]:
    """Rebuild the bundled API indexes (issue #369, Phase 3 follow-up).

    Runs refresh.run_refresh -- the exact pipeline behind the
    flextools-mcp-refresh CLI -- in a worker thread: its steps spawn
    blocking subprocesses, and its stdout narration is captured under a
    scoped redirect so none of it can reach the MCP stdio channel (the
    captured tail rides the response as evidence). Step milestones bridge
    back to this loop in order and go through the ambient progress
    reporter, so a client without a progressToken sees an ordinary tool
    call, and the shared heartbeat covers long single steps.

    Step-level failures are a normal outcome (the CLI exits 1 the same
    way) and are reported in the payload; only a failure of the pipeline
    machinery itself becomes an error_response.
    """
    reporter = get_progress_reporter()
    loop = asyncio.get_running_loop()

    def _on_step(completed: int, total: int, description: str) -> None:
        # Fires in the worker thread. Bridge to the loop and wait for the
        # report to land so milestones stay in plan order; the reporter
        # itself never raises, and bridge failures drop the milestone,
        # never the refresh.
        if not reporter.enabled:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(
                reporter.report(completed, total=total, message=description),
                loop,
            )
            future.result(timeout=30)
        except Exception:
            pass

    def _run_pipeline() -> tuple[dict, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            refresh_module = _load_refresh_module()
            result = refresh_module.run_refresh(
                flexicon_path=args.get("flexicon_path"),
                flexlibs_path=args.get("flexlibs_path"),
                dll_path=args.get("dll_path"),
                skip_categorization=bool(args.get("skip_categorization", False)),
                skip_postprocess=bool(args.get("skip_postprocess", False)),
                on_step=_on_step,
            )
        return result, buffer.getvalue()

    try:
        async with progress_heartbeat("index refresh"):
            result, log_text = await asyncio.to_thread(_run_pipeline)
    except Exception as exc:
        return error_response(
            "refresh_failed",
            f"Index refresh failed before completing: {exc}",
            hint=(
                "The same pipeline is available from the command line as "
                "`python -m flextoolsmcp.refresh`."
            ),
            tool="flextools_refresh_indexes",
        )

    steps = result["steps"]
    total_steps = len(steps)
    await reporter.report(
        total_steps,
        total=total_steps,
        message=(
            "Index refresh complete"
            if result["success"]
            else "Index refresh finished with failures"
        ),
    )

    if result["any_refresh_succeeded"]:
        # Mirror startup's _try_refresh_once: the file-discovery cache
        # stores negative results, so files the refresh just wrote would
        # stay invisible to later lookups without this clear. Fail-open:
        # the refresh itself already succeeded.
        try:
            try:
                from ..versioning import clear_file_discovery_cache
            except (ImportError, ValueError):
                from server.versioning import clear_file_discovery_cache
            clear_file_discovery_cache()
        except Exception:
            pass

    refreshed = [s["step"] for s in steps if s["status"] == "ok"]
    skipped = [s["step"] for s in steps if s["status"] == "skipped"]
    failed = [s["step"] for s in steps if s["status"] == "failed"]
    log_lines = [line for line in log_text.splitlines() if line.strip()]

    data = {
        KEY_STATUS: "ok" if result["success"] else "partial",
        "summary": (
            f"Index refresh {'complete' if result['success'] else 'finished with failures'}: "
            f"{len(refreshed)} step(s) ok, {len(skipped)} skipped, "
            f"{len(failed)} failed."
        ),
        "steps": steps,
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "note": (
            "The running server keeps serving the indexes it loaded at "
            "startup; restart the server to pick up the rebuilt index "
            "files. Semantic-search embeddings are not rebuilt by this "
            "tool."
        ),
        "log_tail": log_lines[-20:],
    }
    return json_response(build_response_with_context(data))
