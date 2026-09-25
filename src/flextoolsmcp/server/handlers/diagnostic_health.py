#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_health: composed diagnostic snapshot (issue #56).

"Why is this API missing?" and "which versions am I actually running?" were
previously answerable only by reading server logs. This module is pure
COMPOSITION of existing detectors -- it introduces no new detection logic:

- detect_installed_library_version() / detect_liblcm_version_from_disk()
  (server/versioning.py) for installed-vs-index version comparison
- find_versioned_api_file() / find_latest_versioned_api_file()
  (server/versioning.py) for the "exact | fallback_latest | missing" index
  match state (recomputed fresh on every call, so a refresh that happened
  since server startup -- in this process or another -- is reflected; see
  the directory-mtime cache key in versioning.py)
- get_index_dir() / get_log_dir() for filesystem locations
- session_state for the current session snapshot
- sweep_stale_locks() (server/project_discovery.py), re-invoked on every
  call (issue #145) rather than replaying the startup snapshot, for lock
  warnings
- op_telemetry's JSONL loader for the last-5-operations verbose block
"""

import json
import os
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps

try:
    from ...response_utils import build_response_with_context
except (ImportError, ValueError):
    from response_utils import build_response_with_context

# session_state / get_log_dir / get_api_index come from the shared helper;
# json_response is also provided but re-imported explicitly for clarity.
json_response, session_state, get_log_dir, get_api_index = safe_import_kernel_deps()

try:
    from ...file_utils import get_index_dir
except (ImportError, ValueError):
    from file_utils import get_index_dir

try:
    from ...workspace_check import get_workspace_notice, warning_line as workspace_warning_line
except (ImportError, ValueError):
    from workspace_check import get_workspace_notice, warning_line as workspace_warning_line

try:
    from ..versioning import (
        detect_installed_library_version,
        detect_liblcm_version_from_disk,
        get_resolved_fieldworks_dir,
        find_versioned_api_file,
        find_latest_versioned_api_file,
        extract_version_string,
    )
except ImportError:
    from server.versioning import (
        detect_installed_library_version,
        detect_liblcm_version_from_disk,
        get_resolved_fieldworks_dir,
        find_versioned_api_file,
        find_latest_versioned_api_file,
        extract_version_string,
    )

try:
    from ..project_access import probe_project_access
except (ImportError, ValueError):
    from server.project_access import probe_project_access

try:
    from ..parser_probe import ParserDetector, ADVISORY_HC_ENGINE_VERSION_SKEW
    from ..project_discovery import sweep_stale_locks
except (ImportError, ValueError):
    from server.parser_probe import ParserDetector, ADVISORY_HC_ENGINE_VERSION_SKEW
    from server.project_discovery import sweep_stale_locks

try:
    from . import op_telemetry
except ImportError:
    from server.handlers import op_telemetry


# ============================================================
# Library detection (mirrors server.py's get_installed_*_version() helpers --
# duplicated here rather than imported, since server.py imports the handler
# package and importing back would create a cycle).
# ============================================================

_LIBRARY_SPECS: List[Dict[str, Any]] = [
    {
        "key": "flexicon",
        "display_name": "Flexicon",
        "prefix": "flexicon_api",
        "lib_subdir": "python",
        "detect_kwargs": {"import_path": "flexicon", "package_name": "pyflexicon"},
    },
    {
        "key": "liblcm",
        "display_name": "LibLCM",
        "prefix": "liblcm_api",
        "lib_subdir": "liblcm",
        "detect_kwargs": {"assembly_name": "SIL.LCModel"},
    },
    {
        "key": "flexlibs_stable",
        "display_name": "FlexLibs stable",
        "prefix": "flexlibs_api",
        "lib_subdir": "python",
        "detect_kwargs": {"import_path": "flexlibs", "package_name": "flexlibs"},
    },
]


def _detect_installed_version(spec: Dict[str, Any]) -> Optional[str]:
    """Detect the installed version for one library spec."""
    return detect_installed_library_version(
        spec["display_name"], **spec["detect_kwargs"]
    )


def compute_library_match(
    lib_dir: Path,
    prefix: str,
    installed_version: Optional[str],
) -> Dict[str, Any]:
    """Compute {installed, index_loaded, match} for one library.

    Pure with respect to its inputs (lib_dir contents + installed_version) --
    kept as a standalone function so tests can point it at a fixture
    directory instead of the real index tree.

    match values:
        "exact"           -- a versioned index file matches installed_version exactly
        "fallback_latest" -- no exact match; serving the latest shipped/refreshed index
        "missing"         -- no versioned index file found for this library at all
    """
    index_loaded: Optional[str] = None
    match = "missing"

    if installed_version:
        exact_path = find_versioned_api_file(lib_dir, prefix, installed_version)
        if exact_path is not None:
            index_loaded = installed_version
            match = "exact"

    if match != "exact":
        latest_path = find_latest_versioned_api_file(lib_dir, prefix)
        if latest_path is not None:
            index_loaded = extract_version_string(latest_path.name)
            match = "fallback_latest"
        else:
            match = "missing"

    return {
        "installed": installed_version,
        "index_loaded": index_loaded,
        "match": match,
    }


def _build_libraries_block(index_dir: Path) -> Dict[str, Dict[str, Any]]:
    libraries: Dict[str, Dict[str, Any]] = {}
    for spec in _LIBRARY_SPECS:
        installed_version = _detect_installed_version(spec)
        lib_dir = index_dir / spec["lib_subdir"]
        libraries[spec["key"]] = compute_library_match(lib_dir, spec["prefix"], installed_version)
    return libraries


def build_session_api_versions() -> Dict[str, Dict[str, Any]]:
    """Installed vs index-loaded versions for session state (issue #149).

    Uses the same ``compute_library_match`` path as ``flextools_health`` so
    ``fallback_latest`` is explicit instead of replaying index-file versions
    as if they were the installed library.
    """
    return _build_libraries_block(get_index_dir())


def _build_fieldworks_block() -> Dict[str, Any]:
    """FieldWorks install detection + on-disk LibLCM version (server.py doesn't
    have this loaded into the CLR until a project is open, so we read the DLL
    off disk -- same approach as the session-header log line)."""
    fieldworks_dir = get_resolved_fieldworks_dir()
    liblcm_version_on_disk = detect_liblcm_version_from_disk()
    return {
        "install_path": str(fieldworks_dir) if fieldworks_dir else None,
        "detected": fieldworks_dir is not None,
        "liblcm_version_on_disk": liblcm_version_on_disk,
    }


def _build_probe_reason(probe: Any, lcmodel_install_path: Optional[str]) -> Dict[str, Any]:
    """Shape one ``parser_probe.ProbeResult`` into a reason dict's base
    fields -- ``parser_core_missing``'s detail shape verbatim
    (contracts/flextools_health-parser-block.md), reused for both
    ``read.reason`` and the base of ``write.reason`` so health and the
    error envelope never drift apart. Pure reshaping of fields the probe
    already computed; no new detection here."""
    return {
        "signal": probe.signal,
        "expected_path": probe.expected_path,
        "detected_version": probe.detected_version,
        "missing_members": list(probe.missing_members),
        "lcmodel_install_path": lcmodel_install_path,
    }


def _build_parser_block() -> Dict[str, Any]:
    """ParserCore/HC capability snapshot for the top-level ``parser`` key
    (contracts/flextools_health-parser-block.md), shaped the way
    ``_build_fieldworks_block()`` shapes FieldWorks detection above.

    Pure composition, no new detection logic: every fact here already
    exists on the ``parser_probe.ParserDetector`` instance this function
    constructs (T009-T011); this function only reshapes those fields into
    the contract's JSON. No location or reflection logic enters this
    module.

    Exactly two states per spine (``ready`` / ``unavailable``), never a
    third ``degraded`` value -- degradation lives in ``reason`` /
    ``components``. Each spine (``read``, ``write``, ``sandbox``) is read
    from its own probe independently, so one dead spine can never blank
    the others (``ParserDetector`` already isolates them; see its
    docstring).

    ``write``'s status is decided by the member probe **alone** -- because
    ``flextools_health`` never opens a project (research D2),
    ``ParserDetector.agent_probe`` is unconditionally ``"skipped"`` here,
    and a skipped probe must never be read as a pass *nor* veto an
    otherwise-ready write. It is always recorded, verbatim, in
    ``write.reason["agent_probe"]`` -- visible, never silently folded into
    a bare ``"ready"``.

    ``active_engine`` is unconditionally ``None`` at CP1 (research D8,
    same premise as the agent probe) and is never read by any status
    decision in this function.
    """
    detector = ParserDetector()

    lcmodel_install_path = detector.versions.lcmodel_install_path

    read_reason: Optional[Dict[str, Any]] = None
    if not detector.read_probe.ok:
        read_reason = _build_probe_reason(detector.read_probe, lcmodel_install_path)

    # write.reason is always built, whether or not write is "ready" -- the
    # skipped agent_probe must stay visible either way (see docstring).
    write_reason = _build_probe_reason(detector.write_probe, lcmodel_install_path)
    write_reason["agent_probe"] = detector.agent_probe.state
    if detector.agent_probe.state == "absent":
        write_reason["agent_guid"] = detector.agent_probe.agent_guid
        write_reason["active_engine"] = detector.agent_probe.active_engine

    hc = detector.sandbox_probe.hc
    generate_config = detector.sandbox_probe.generate_config
    hc_component = _build_hc_component(hc)
    generate_component = _build_generate_config_component(generate_config)
    # FR-004: ready only if hc is found AND answered its `-h` probe AND
    # GenerateHCConfig.exe is present. A `dotnet tool list`-only hit
    # (starts None) was never probed, so it is not a start.
    sandbox_ready = (
        hc_component["found"] is True
        and hc_component["starts"] is True
        and generate_component["found"] is True
    )
    # FR-005: a version skew warns, never refuses -- it never enters status.
    advisories: List[str] = []
    if getattr(detector.versions, "hc_engine_version_skew", False):
        advisories.append(ADVISORY_HC_ENGINE_VERSION_SKEW)

    return {
        "read": {
            "status": "ready" if detector.read_probe.ok else "unavailable",
            "reason": read_reason,
        },
        "write": {
            "status": "ready" if detector.write_probe.ok else "unavailable",
            "reason": write_reason,
        },
        "sandbox": {
            "status": "ready" if sandbox_ready else "unavailable",
            "components": [hc_component, generate_component],
            "advisories": advisories,
        },
        # Informational only -- never a status input (D8).
        "active_engine": detector.active_engine,
        "detected": {
            "parser_core_version": detector.versions.parser_core_version,
            "lcmodel_install_path": lcmodel_install_path,
            "hc_tool_version": detector.versions.hc_tool_version,
            "hc_path": hc.expected_path if hc.ok else None,
            "generate_hc_config_path": generate_config.expected_path if generate_config.ok else None,
            # CP5 (FR-005): reported verbatim, never compared to a floor.
            "fieldworks_hermitcrab_version": getattr(
                detector.versions, "fieldworks_hermitcrab_version", None
            ),
            "generate_hc_config_version": getattr(
                detector.versions, "generate_hc_config_version", None
            ),
            "hc_source": hc_component["source"],
        },
    }


def _build_hc_component(hc: Any) -> Dict[str, Any]:
    """The `hc` entry of parser.sandbox.components (data-model section 7).

    Copies the discovery fields verbatim. `getattr` with defaults because
    `ParserDetector._safe_probe` may hand back a plain ProbeResult (a probe
    that raised) rather than an HcToolDiscovery; then `found` falls back to
    `ok` and the discovery-only fields are null."""
    return {
        "component": "hc",
        "found": bool(getattr(hc, "found", hc.ok)),
        "expected_path": hc.expected_path,
        "starts": getattr(hc, "starts", None),
        "signal": hc.signal,
        "source": getattr(hc, "source", None),
        "reason": getattr(hc, "reason", None),
    }


def _build_generate_config_component(generate_config: Any) -> Dict[str, Any]:
    """The GenerateHCConfig.exe entry. Health never executes it (that would
    be new detection work), so `starts` is always null; when found it lives
    under the FieldWorks install."""
    found = bool(generate_config.ok)
    return {
        "component": "GenerateHCConfig.exe",
        "found": found,
        "expected_path": generate_config.expected_path,
        "starts": None,
        "signal": generate_config.signal,
        "source": "fieldworks_dir" if found else None,
        "reason": None if found else (
            "GenerateHCConfig.exe was not found in the FieldWorks install"
        ),
    }


# The `hc` install hint is a literal, quoted verbatim from SPEC H1 -- `hc` is a
# dotnet GLOBAL tool, located via PATH / `dotnet tool list -g`, not a file under
# %LOCALAPPDATA%. Never reword this command; a caller pastes it.
_HC_INSTALL_HINT = "dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool"

# The full hint the "install the hc dotnet tool" rung carries (FR-004): the
# command above plus what it needs to install and to run afterwards.
_HC_INSTALL_FULL_HINT = (
    _HC_INSTALL_HINT + " Installing it needs a .NET SDK, and hc 3.8 and later "
    "need the .NET 10 runtime to run."
)

#: The one tool the sandbox spine proposes -- only when it is ready (FR-006).
_SANDBOX_TOOL = "flextools_parse_sandbox"

# CP1 replacement action text for the `write: unavailable` / `read: ready` row.
# The contract's own wording ("use read-only Try A Word; filing unavailable")
# names flextools_try_word in prose, and SPEC 10.1 forbids proposing a tool that
# does not exist -- nulling `tool` alone would leave the tool named in the
# action. This wording names no tool. It deliberately does NOT claim the grammar
# loads: nothing at CP1 loads a grammar, so `read: ready` means only that
# ParserCore's read surface is reachable.
#: The contract's own wording for this row (SPEC 10.2, copied into
#: `contracts/flextools_health-parser-block.md:91`). It names the tool,
#: which is the point: filing is what is unavailable, and a caller should
#: be told that the read spine is still fully usable and by what.
#:
#: CP1 could not say this. `flextools_try_word` did not exist, SPEC 10.1
#: forbids proposing a tool that does not exist, and naming it in prose is
#: the same violation as naming it in the `tool` field -- so CP1 shipped a
#: replacement that named nothing. **CP2b is when the row lands in full**,
#: which is exactly what the CP1 caveat said would happen.
_WRITE_UNAVAILABLE_READ_READY_ACTION = (
    "use read-only Try A Word; filing unavailable"
)


def _parser_next_step(
    action: str,
    rationale: str,
    est_cost: str,
    tool: Optional[str] = None,
    args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One structured rung in SPEC 10.1's shape ({action, tool, args,
    rationale, est_cost}).

    ``tool`` still defaults to None, because most rungs here ARE external --
    "install/repair FieldWorks", "install the hc dotnet tool". The two rows
    that name ``flextools_try_word`` pass it explicitly from CP2b on; before
    that they could not, since the tool did not exist."""
    return {
        "action": action,
        "tool": tool,
        "args": args,
        "rationale": rationale,
        "est_cost": est_cost,
    }


def _build_parser_next_steps(parser: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The `next_step` rungs for whichever parser spines are unhealthy
    (contracts/flextools_health-parser-block.md, "next_step per unhealthy
    state"; SPEC 10.1 for the rung shape).

    Takes the already-composed `parser` block rather than a detector, so
    detection still happens exactly once per health call and this function
    stays what `_build_parser_block()` is: reshaping of facts already
    computed. No new detection logic enters this module.

    CP1's degradation is OVER (CP2b, FR-038). The two rows that name
    `flextools_try_word` now do so -- in the `tool` field and in the
    contract's own action wording -- because the tool exists. CP1 degraded
    them to `tool: None` with replacement prose precisely because SPEC 10.1
    forbids proposing a tool that does not exist, and the CP1 caveat said
    they would land in full "at CP2, when the tool they name is real".

    `flextools_parse_sandbox` is named only when the sandbox spine is
    `ready` (FR-006): then exactly one rung proposes it, with usable args.
    When the spine is `unavailable` it is never named -- not in `tool`, not
    in any prose -- and each cause gets its own tool-less repair rung (hc
    not found, hc found but cannot start, GenerateHCConfig.exe missing).

    A registry sweep in `tests/test_parser_health_block.py` asserts that
    every tool named anywhere in the emitted guidance is a registered tool,
    so the next row to be released cannot be released early.

    `active_engine` mismatch has no rung here: `flextools_health` never
    opens a project (research D2/D8), so `active_engine` is always None and
    the mismatch gate lives in the per-call preflight, not in health.
    """
    steps: List[Dict[str, Any]] = []

    read = parser["read"]
    write = parser["write"]

    if read["status"] == "unavailable":
        steps.append(_parser_next_step(
            action="install/repair FieldWorks so ParserCore is reachable",
            rationale=(
                "ParserCore's read surface could not be resolved on this "
                "install, so no parser spine is callable."
            ),
            est_cost="n/a",
        ))

    if write["status"] == "unavailable":
        write_signal = (write.get("reason") or {}).get("signal")
        if write_signal == "parser_agent_missing":
            steps.append(_parser_next_step(
                action=(
                    "this project has never run HermitCrab; run it once from "
                    "FLEx's Parser menu, then retry filing"
                ),
                # Names the tool from CP2b on. A missing recording agent
                # does NOT make reading unavailable -- reading neither
                # records nor needs one (FR-016) -- so pointing at the read
                # tool here is the whole substance of the row.
                tool="flextools_try_word",
                rationale=(
                    "kguidAgentHermitCrabParser is absent from the project's "
                    "agent repository, so filed results would have no owning "
                    "agent. Reading is unaffected: it neither records nor "
                    "needs an agent."
                ),
                est_cost="inline",
            ))
        elif read["status"] == "ready":
            steps.append(_parser_next_step(
                action=_WRITE_UNAVAILABLE_READ_READY_ACTION,
                tool="flextools_try_word",
                rationale=(
                    "ParseFiler.ProcessParse is missing from this ParserCore, "
                    "so parse results cannot be filed back; read: ready means "
                    "ParserCore's read surface is reachable, and the read "
                    "spine is fully usable."
                ),
                est_cost="inline",
            ))

    # sandbox (contracts/tools.md section 6): one rung per cause while
    # unavailable, never naming the sandbox tool; exactly one rung naming it
    # when ready. Keyed on found/starts, not on the signal.
    sandbox = parser["sandbox"]
    components = {c["component"]: c for c in sandbox["components"]}
    hc = components.get("hc")
    generate = components.get("GenerateHCConfig.exe")

    if sandbox["status"] == "ready":
        steps.append(_parser_next_step(
            action="rehearse a grammar change on an exported copy",
            tool=_SANDBOX_TOOL,
            args={"action": "parse", "words": []},
            rationale=(
                "hc starts and GenerateHCConfig.exe is present, so a grammar "
                "change can be rehearsed on an exported copy of the project "
                "without touching the project itself."
            ),
            est_cost="minutes",
        ))
    else:
        if hc is not None and not hc["found"]:
            steps.append(_parser_next_step(
                action="install the hc dotnet tool",
                rationale=(
                    "hc is a dotnet global tool, located via PATH / "
                    "`dotnet tool list -g`. Install it with: {}".format(
                        _HC_INSTALL_FULL_HINT
                    )
                ),
                est_cost="n/a",
            ))
        elif hc is not None and hc["starts"] is False:
            reason = (hc.get("reason") or "no reason was reported").rstrip(".")
            if hc.get("signal") == "timeout":
                lead = (
                    "hc was found but did not answer `-h` within the probe "
                    "bound, which usually means it cannot start"
                )
            else:
                lead = "hc was found but cannot start"
            steps.append(_parser_next_step(
                action="install the .NET runtime hc needs",
                rationale="{} ({}).".format(lead, reason),
                est_cost="n/a",
            ))
        if generate is not None and not generate["found"]:
            steps.append(_parser_next_step(
                action="repair or reinstall FieldWorks (GenerateHCConfig.exe missing)",
                rationale=(
                    "GenerateHCConfig.exe ships with FieldWorks and exports the "
                    "grammar hc loads; it was not found in the FieldWorks install."
                ),
                est_cost="n/a",
            ))

    return steps


def _read_index_file_meta(path: Path) -> Dict[str, Any]:
    """Read {name, schema, entities} from a versioned API JSON file."""
    meta: Dict[str, Any] = {"name": path.name, "schema": None, "entities": 0}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        meta["schema"] = data.get("_schema") or data.get("schema")
        entities = data.get("entities")
        if isinstance(entities, dict):
            meta["entities"] = len(entities)
        elif isinstance(entities, list):
            meta["entities"] = len(entities)
    except (OSError, json.JSONDecodeError):
        pass
    return meta


def _build_indexes_block(index_dir: Path, libraries: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    for spec in _LIBRARY_SPECS:
        lib_status = libraries[spec["key"]]
        if lib_status["match"] == "missing":
            continue
        lib_dir = index_dir / spec["lib_subdir"]
        version = lib_status["index_loaded"]
        path = find_versioned_api_file(lib_dir, spec["prefix"], version) if version else None
        if path is None:
            path = find_latest_versioned_api_file(lib_dir, spec["prefix"])
        if path is not None:
            files.append(_read_index_file_meta(path))

    api_index = get_api_index()
    casting_loaded = bool(api_index and api_index.casting_index)
    navigation_loaded = bool(api_index and api_index.navigation_graph)

    return {
        "dir": str(index_dir),
        "overlay_dir": str(Path.home() / ".flextoolsmcp" / "index"),
        "files": files,
        "casting_index": {
            "loaded": casting_loaded,
            "schema": (api_index.casting_index or {}).get("_schema") if casting_loaded else None,
        },
        "navigation_graph": {
            "loaded": navigation_loaded,
            "schema": (api_index.navigation_graph or {}).get("_schema") if navigation_loaded else None,
        },
    }


def _build_warnings(libraries: Dict[str, Dict[str, Any]]) -> List[str]:
    warnings: List[str] = []
    for spec in _LIBRARY_SPECS:
        status = libraries[spec["key"]]
        if status["match"] == "fallback_latest" and status["installed"]:
            warnings.append(
                f"Index fallback active: installed {spec['display_name']} "
                f"{status['installed']} has no matching index; using "
                f"{status['index_loaded'] or '?'} (stale). Run refresh with "
                f"'python -m flextoolsmcp.refresh'."
            )
    # Issue #145: re-scan for stale locks on every call instead of replaying
    # the startup snapshot -- a lock held at server startup may have been
    # released since (or a new one taken) by the time flextools_health runs.
    # Not once-per-process gated: health is explicitly diagnostic, so it
    # always reports current state.
    warnings.extend(sweep_stale_locks())

    # "Why is the assistant behaving oddly?" is exactly what this tool is for,
    # and a checkout-as-workspace is one answer. Not once-per-process gated:
    # health is explicitly diagnostic, so it always reports current state.
    notice = get_workspace_notice()
    if notice:
        warnings.append(workspace_warning_line(notice))
    return warnings


# ============================================================
# Verbose-only diagnostics
# ============================================================

def _check_flexinit_importable() -> Dict[str, Any]:
    try:
        from flexicon import FLExInitialize  # noqa: F401
        return {"importable": True, "error": None}
    except Exception as exc:
        return {"importable": False, "error": str(exc)}


def _check_pythonnet_available() -> Dict[str, Any]:
    try:
        import clr  # type: ignore  # noqa: F401
        return {"available": True, "error": None}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _build_project_access_block() -> Dict[str, Any]:
    """Composed shared-mode access probe (issue #93 CP2, T2.7).

    Pure composition of project_access.probe_project_access(): filesystem +
    stdlib only, never opens the project, no side effects. Replaces the old
    "locked: bool" block with the full verdict (free / open_shared /
    open_exclusive / stale_lock / held_by_other / unknown) plus the facts it
    was composed from, so a human reading flextools_health(verbose=True) can see
    *why* a project is or isn't accessible without guessing.
    """
    project_name = session_state.project_name or ""
    if not project_name:
        return {
            "project": None,
            "verdict": None,
            "sharing_enabled": None,
            "holder": None,
            "lock_age_seconds": None,
        }

    access = probe_project_access(project_name)
    holder = None
    if access.holder is not None:
        holder = {
            "pid": access.holder.pid,
            "process_name": access.holder.process_name,
            "timestamp_ticks": access.holder.timestamp_ticks,
        }
    return {
        "project": access.project_name,
        "verdict": access.verdict,
        "probed": access.probed,
        "sharing_enabled": access.sharing_enabled,
        "holder": holder,
        "lock_age_seconds": access.lock_age_seconds,
        "lock_note": (
            "verdict is from probe_project_access(); it is not inferred from "
            "bare lock-file existence alone."
        ),
    }


def _build_recent_operations(limit: int = 5) -> List[Dict[str, Any]]:
    try:
        log_dir = get_log_dir()
        records = op_telemetry._load_jsonl_records(log_dir)
    except Exception:
        return []
    recent = records[-limit:]
    return [
        {
            "ts": r.get("ts"),
            "outcome": r.get("outcome"),
            "error_code": r.get("error_code") or None,
            "project": r.get("project"),
        }
        for r in recent
    ]


def _build_verbose_block() -> Dict[str, Any]:
    return {
        "project_access": _build_project_access_block(),
        "flexinit_importable": _check_flexinit_importable(),
        "pythonnet_available": _check_pythonnet_available(),
        "recent_operations": _build_recent_operations(5),
    }


# ============================================================
# Handler
# ============================================================

async def handle_flextools_health(args: dict) -> List[TextContent]:
    """Composed read-only diagnostic snapshot for flextools_health (issue #56).

    No side effects: never mutates session state, never opens a FieldWorks
    project, never writes files. Safe to call at any point in a session
    (even before flextools_start -- see server.py's _SESSION_INDEPENDENT_TOOLS
    if this tool is later added there).
    """
    verbose = bool(args.get("verbose", False))

    index_dir = get_index_dir()
    libraries = _build_libraries_block(index_dir)
    # Detect once; the rungs are shaped from the composed block, not from a
    # second ParserDetector() pass.
    parser = _build_parser_block()

    try:
        from ..kernel import is_stateless_client_mode
    except ImportError:
        from server.kernel import is_stateless_client_mode

    result: Dict[str, Any] = {
        "server": {
            "version": _server_version(),
            "python": platform.python_version(),
            "pid": os.getpid(),
            "stateless_client_mode": is_stateless_client_mode(),
        },
        "fieldworks": _build_fieldworks_block(),
        "parser": parser,
        # Sibling of "parser" rather than a key inside it: the block's shape is
        # copied verbatim from SPEC 10.2 and carries exactly five keys.
        "parser_next_steps": _build_parser_next_steps(parser),
        "libraries": libraries,
        "indexes": _build_indexes_block(index_dir, libraries),
        "session": session_state.summary(),
        "logs": {
            "operations_log": str(get_log_dir() / "operations.log"),
            "operations_jsonl": str(get_log_dir() / "operations.jsonl"),
        },
        "warnings": _build_warnings(libraries),
    }

    if verbose:
        result["verbose"] = _build_verbose_block()

    result = build_response_with_context(result, include_session=False)
    return json_response(result)


def _server_version() -> str:
    try:
        try:
            from ... import __version__
        except (ImportError, ValueError):
            from flextoolsmcp import __version__
        return __version__
    except Exception:
        return "unknown"
