#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ParserCore capability probe (parser-check, CP1).

SPEC 5.4's "gate is two checks, neither of which reads a version":

    1. **Same install.** ``ParserCore.dll`` must resolve from the same
       FieldWorks directory that already supplies ``SIL.LCModel.dll``
       (``versioning.get_resolved_fieldworks_dir()``). A ParserCore from a
       *different* install is refused -- mixing two FieldWorks versions
       across an in-process boundary is the failure no version floor would
       have caught.
    2. **The surface we bind exists.** Reflect over exactly the members
       this feature calls -- ``HCParser(LcmCache)``, ``Update()``,
       ``ParseWord(string)``, ``TraceWordXml(string, IEnumerable<int>)``,
       ``ParseWordXml(string)``, and (write spine only)
       ``ParseFiler.ProcessParse`` -- and refuse if any is absent.

This module combines two existing precedents rather than reusing either
wholesale (SPEC 5.4):

    - the plain ``Assembly.LoadFile`` + ``GetName().Version`` read already
      used by ``versioning.py`` (``detect_liblcm_version_from_disk``,
      around line 262) for a version-only disk read of ``SIL.LCModel.dll``;
    - the ``GetMembers``/generic-argument-unwrapping reflection pattern
      ``liblcm_extractor.py`` uses (from ~line 330 on) to walk a LibLCM
      type's method surface, generalized here from "every type in a
      namespace" to "exactly the members SPEC 5.4 names".

**Binding convention (for future callers, not this module).** SPEC 5.4:
``IParser`` names its parameters ``word`` while ``HCParser`` implements
them as ``form`` (``IParser.cs:23,25``), so any code that later *calls*
these members (T024/T025) must bind positionally, never by keyword --
keyword binding through pythonnet would break on that interface/impl
mismatch. This module never calls a bound member (see CP1 boundary below),
so the convention has nothing to violate here; it is recorded so the next
task that does call them does not rediscover it the hard way.

**``detected_version`` is reported, never compared.** No code path in this
module -- or any module this feeds -- may test it against a floor. SPEC 16
carries a standing regression test for exactly this; see
``tests/test_parser_probe.py::TestDetectedVersionNeverCompared``.

**CP1 boundary.** This module is reflection-only: ``Assembly.LoadFile`` +
``GetTypes``/``GetMethods``/``GetConstructors``. It never constructs an
``LcmCache``, never loads a grammar and never parses a word. A later task
(T026) runs a static + dynamic scan asserting no ``HCParser(`` construction
exists anywhere under ``src/flextoolsmcp/server/**`` except this module's
reflection over the *type*, never an *instance*.

**Scope note.** This file is the landing module for the rest of SPEC 5.4's
MCP-side placement: T010 adds ``hc`` / ``GenerateHCConfig.exe`` discovery,
T011 adds the ``ParserDetector`` aggregate, and T024/T025 add the engine
gate and the agent probe. Only ``ProbeResult`` and ``probe_parser_core()``
(plus their private helpers) land here now.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, Iterable, List, Literal, Optional, Tuple, Union

try:
    from .versioning import get_resolved_fieldworks_dir, locate_liblcm_dll
except ImportError:
    from server.versioning import get_resolved_fieldworks_dir, locate_liblcm_dll


# ---------------------------------------------------------------------------
# Closed signal vocabulary (data-model.md / contracts/error-codes.md's
# parser_core_missing.signal). Shared with the health block's read.reason /
# write.reason -- that sharing is what keeps health and error envelopes
# from drifting (contracts/error-codes.md).
# ---------------------------------------------------------------------------

SIGNAL_ABSENT = "absent"
SIGNAL_FOREIGN_INSTALL = "foreign_install"
SIGNAL_INCOMPATIBLE_SURFACE = "incompatible_surface"
SIGNAL_LOAD_FAILED = "load_failed"

CLOSED_SIGNALS: FrozenSet[str] = frozenset(
    {SIGNAL_ABSENT, SIGNAL_FOREIGN_INSTALL, SIGNAL_INCOMPATIBLE_SURFACE, SIGNAL_LOAD_FAILED}
)


# ---------------------------------------------------------------------------
# The bound member surface (SPEC 5.4). Member-identifier strings use the
# same format the probe reflects into: a bare constructor/method signature
# for HCParser's own members, and "TypeName.MethodName" (no signature) for
# ParseFiler's, matching tests/fixtures/parser_check.py.
# ---------------------------------------------------------------------------

HCPARSER_MEMBERS: FrozenSet[str] = frozenset(
    {
        "HCParser(LcmCache)",  # ctor -- HCParser.cs:50
        "Update()",  # HCParser.cs:67
        "ParseWord(string)",  # HCParser.cs:84 -> ParseResult
        "TraceWordXml(string, IEnumerable<int>)",  # HCParser.cs:120 -> XDocument
        "ParseWordXml(string)",  # HCParser.cs:127 -> XDocument
    }
)
"""The read spine's required member set."""

PARSE_FILER_MEMBERS: FrozenSet[str] = frozenset({"ParseFiler.ProcessParse"})
"""Additional member required by the write spine only (spine 2, SPEC 5.2)."""

WRITE_REQUIRED_MEMBERS: FrozenSet[str] = HCPARSER_MEMBERS | PARSE_FILER_MEMBERS
"""The write spine's required member set -- HCParser's surface plus the filer."""

# ---------------------------------------------------------------------------
# THE OTHER CAPABILITY CHECK, AND WHAT IT COVERS THAT THIS ONE DOES NOT.
#
# There are two parser capability checks, and they are DIFFERENT AND
# OVERLAPPING -- not one simply larger than the other. The other one is
# `ParserOperations.GetAvailability()` in the flexicon package. Each probes
# the surface IT binds, which is why the member lists differ; they are not
# drifting apart by accident, and neither is a stale copy of the other.
#
#   This check covers, and flexicon's does NOT:
#       HCParser(LcmCache)          -- the ctor; flexicon never constructs one
#       Update()                    -- reached only through its Reload()
#       ParseFiler.ProcessParse     -- FILING. flexicon deliberately does not
#                                      wrap the write path at all, so its
#                                      check has nothing to say about it.
#                                      This is the important one: the write
#                                      spine is gated here and nowhere else.
#
#   flexicon's check covers, and this one does NOT:
#       IsUpToDate()                -- the held grammar's currency
#       Reset()                     -- the first half of its Reload()
#                                      (Reload is Reset-then-Update, and the
#                                      order is load-bearing)
#
# So a contributor editing the lists above should expect them to disagree
# with flexicon's, and should NOT "fix" the disagreement by copying one into
# the other -- that would make this probe demand members no caller here
# binds, and would make flexicon's demand the filing member it has no use
# for. If you add a member to THIS list, add it because a call site in THIS
# repository binds it.
#
# Required by FR-041, which asks that each check state, where a contributor
# will read it, what the other has that it lacks -- an unexplained
# divergence between two checks is indistinguishable from drift within a
# release or two. flexicon's side carries the mirror image of this note.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ProbeResult (data-model.md)
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    """The atom of parser detection -- one per probed capability.

    Fields verbatim from data-model.md's ``ProbeResult`` table, plus
    ``load_error`` (this module's addition, carried on the ``load_failed``
    path so the throw that caused it is not discarded).

    **Invariant.** ``ok=True`` implies ``missing_members == []`` and
    ``signal is None`` -- enforced by construction in ``probe_parser_core``
    below, not merely documented here.
    """

    ok: bool
    signal: Optional[str] = None
    expected_path: Optional[str] = None
    missing_members: List[str] = field(default_factory=list)
    detected_version: Optional[str] = None
    load_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Reflective member probe
# ---------------------------------------------------------------------------

_CLR_PRIMITIVE_NAMES = {
    "String": "string",
    "Int32": "int",
    "Boolean": "bool",
    "Double": "double",
    "Object": "object",
    "Void": "void",
}


def _format_clr_type(clr_type) -> str:
    """Render a .NET ``System.Type`` the way SPEC 5.4's member list spells
    it -- ``string`` rather than ``String``, ``IEnumerable<int>`` rather
    than the backtick-generic CLR name -- so the reflected signature can be
    diffed directly against ``HCPARSER_MEMBERS`` / ``WRITE_REQUIRED_MEMBERS``.

    Mirrors ``liblcm_extractor.py``'s ``clean_type_name`` /
    ``get_element_type`` precedent (generic-argument unwrapping), but
    formats a *usable* signature string instead of only the bare type name,
    which is what a bound-member surface diff needs.
    """
    try:
        if clr_type.IsGenericType:
            base = re.sub(r"`\d+", "", clr_type.Name)
            args = ", ".join(_format_clr_type(a) for a in clr_type.GetGenericArguments())
            return f"{base}<{args}>"
    except Exception:
        pass

    try:
        if clr_type.IsArray:
            elem = clr_type.GetElementType()
            return f"{_format_clr_type(elem)}[]"
    except Exception:
        pass

    name = getattr(clr_type, "Name", str(clr_type))
    return _CLR_PRIMITIVE_NAMES.get(name, name)


#: Directories whose assemblies the resolver below already serves.
_RESOLVER_DIRS: set = set()


def _install_directory_resolver(directory: Path) -> None:
    """Resolve ParserCore's dependencies from its OWN folder. Best-effort.

    `Assembly.LoadFile` does not probe the loaded file's directory, so in a
    process that has not yet imported flexicon (which sets up FieldWorks'
    assembly resolution), `GetTypes()` throws `ReflectionTypeLoadException`
    for every type touching SIL.Core / SIL.LCModel / SIL.Machine -- `HCParser`
    among them -- and a present, healthy install probes as `load_failed`.
    Found live by the CP4 L-0 run (evidence/l0-coexistence.json): the probe's
    verdict depended on whether anything had imported flexicon first.
    Installed once per directory; a failure to install leaves the probe
    exactly as it was.
    """
    key = str(directory).lower()
    if key in _RESOLVER_DIRS:
        return
    try:
        import System  # type: ignore

        def _resolve(_sender, args):
            name = System.Reflection.AssemblyName(args.Name).Name
            candidate = Path(directory) / f"{name}.dll"
            if candidate.is_file():
                return System.Reflection.Assembly.LoadFrom(str(candidate))
            return None

        System.AppDomain.CurrentDomain.AssemblyResolve += System.ResolveEventHandler(_resolve)
        _RESOLVER_DIRS.add(key)
    except Exception:  # noqa: BLE001 -- no CLR, or a test double: probe as before
        pass


def _load_parser_core_members(dll_path: Path) -> Tuple[FrozenSet[str], Optional[str]]:
    """Reflectively load ``ParserCore.dll`` and enumerate its member surface.

    Combines the ``Assembly.LoadFile`` precedent (``versioning.py`` around
    line 262, currently used only for a version read) with the
    ``GetMembers``/generic-unwrapping precedent (``liblcm_extractor.py``
    around line 330 on, currently used to walk whole LibLCM namespaces) --
    narrowed here to exactly the ``HCParser`` and ``ParseFiler`` types SPEC
    5.4 names, rather than every type in the assembly.

    Returns a frozenset of member-identifier strings in the same format
    ``HCPARSER_MEMBERS`` / ``PARSE_FILER_MEMBERS`` use, plus the assembly's
    informational version string (``detected_version`` -- reported, never
    compared; see the module docstring).

    Raises on any reflection failure -- a mismatched transitive dependency
    resolving during ``Assembly.LoadFile`` is the documented case (SPEC
    5.4) -- and deliberately does not catch: ``probe_parser_core`` is the
    seam that maps a throw here to ``signal="load_failed"``.

    Requires pythonnet; not importable/callable without a CLR available,
    which is exactly why every caller in this module reaches it only after
    the same-install gate has already passed (a cheap, pythonnet-free
    filesystem check) -- CP1 never pays the reflection cost for an install
    that was already going to be refused.
    """
    import clr  # type: ignore  # noqa: F401 -- availability probe; raises ImportError if pythonnet is absent  # pyright: ignore[reportUnusedImport]
    import System  # type: ignore
    from System.Reflection import BindingFlags  # type: ignore

    _install_directory_resolver(Path(dll_path).parent)
    assembly = System.Reflection.Assembly.LoadFile(str(dll_path))

    asm_version = assembly.GetName().Version
    detected_version = f"{asm_version.Major}.{asm_version.Minor}.{asm_version.Build}"

    flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly

    members: set = set()
    for clr_type in assembly.GetTypes():
        if clr_type.Name == "HCParser":
            for ctor in clr_type.GetConstructors(flags):
                params = ", ".join(_format_clr_type(p.ParameterType) for p in ctor.GetParameters())
                members.add(f"HCParser({params})")
            for method in clr_type.GetMethods(flags):
                params = ", ".join(_format_clr_type(p.ParameterType) for p in method.GetParameters())
                members.add(f"{method.Name}({params})")
        elif clr_type.Name == "ParseFiler":
            for method in clr_type.GetMethods(flags):
                if method.Name == "ProcessParse":
                    members.add("ParseFiler.ProcessParse")

    return frozenset(members), detected_version


def probe_parser_core(
    required_members: Union[FrozenSet[str], Iterable[str]],
    *,
    search_paths: Optional[List[Path]] = None,
) -> ProbeResult:
    """Probe ``ParserCore.dll``'s member surface against ``required_members``.

    Call once per spine: ``probe_parser_core(HCPARSER_MEMBERS)`` for the
    read spine, ``probe_parser_core(WRITE_REQUIRED_MEMBERS)`` for the write
    spine (data-model.md's "read and write are separate probes over one
    DLL... differ by exactly one member").

    Two gates, in order (SPEC 5.4):

    1. **Same install**, via ``get_resolved_fieldworks_dir()`` --
       recomputed on every call here, no binding retained, matching that
       function's own documented contract. ``ParserCore.dll`` not found at
       all -> ``signal="absent"``; found but resolved from a directory
       other than the one supplying ``SIL.LCModel.dll`` ->
       ``signal="foreign_install"``. Neither branch reflects into the DLL,
       so a bad install is refused before any CLR load is attempted.
    2. **The surface we bind exists** -- reflect (``_load_parser_core_members``)
       and diff ``required_members`` against what was found. Any absent ->
       ``signal="incompatible_surface"``, naming each in ``missing_members``.

    A throw from the reflective load itself -- a mismatched transitive
    dependency, SPEC 5.4's documented ``Assembly.LoadFile`` failure mode --
    is caught here and mapped to ``signal="load_failed"`` with
    ``load_error`` carrying the throw; it is never allowed to propagate out
    of this function (a probe that dies mid-call tells the caller nothing).

    Returns a ``ProbeResult`` satisfying the invariant: ``ok=True`` implies
    ``missing_members == []`` and ``signal is None``.
    """
    required = frozenset(required_members)

    fieldworks_dir = get_resolved_fieldworks_dir(search_paths=search_paths)
    parser_core_path = locate_liblcm_dll(dll_name="ParserCore.dll", search_paths=search_paths)

    if parser_core_path is None:
        expected_path = (
            str(Path(fieldworks_dir) / "ParserCore.dll") if fieldworks_dir else "ParserCore.dll"
        )
        return ProbeResult(
            ok=False,
            signal=SIGNAL_ABSENT,
            expected_path=expected_path,
            missing_members=[],
            detected_version=None,
            load_error=None,
        )

    parser_core_path = Path(parser_core_path)

    if fieldworks_dir is None or parser_core_path.parent != Path(fieldworks_dir):
        return ProbeResult(
            ok=False,
            signal=SIGNAL_FOREIGN_INSTALL,
            expected_path=str(parser_core_path),
            missing_members=[],
            detected_version=None,
            load_error=None,
        )

    try:
        found_members, detected_version = _load_parser_core_members(parser_core_path)
    except Exception as exc:
        return ProbeResult(
            ok=False,
            signal=SIGNAL_LOAD_FAILED,
            expected_path=str(parser_core_path),
            missing_members=[],
            detected_version=None,
            load_error=str(exc),
        )

    missing = sorted(required - frozenset(found_members))
    if missing:
        return ProbeResult(
            ok=False,
            signal=SIGNAL_INCOMPATIBLE_SURFACE,
            expected_path=str(parser_core_path),
            missing_members=missing,
            detected_version=detected_version,
            load_error=None,
        )

    return ProbeResult(
        ok=True,
        signal=None,
        expected_path=str(parser_core_path),
        missing_members=[],
        detected_version=detected_version,
        load_error=None,
    )


# ---------------------------------------------------------------------------
# Sandbox tool discovery: `hc` and `GenerateHCConfig.exe` (T010)
#
# `sandbox_probe` (data-model.md's `ParserDetector` return shape) is
# `{hc: ProbeResult, generate_config: ProbeResult}` -- two independent
# probes, because the two tools fail independently and a caller must know
# which one to install (contracts/flextools_health-parser-block.md).
#
# Closed component-name enum, shared with `parser_tool_missing`'s
# `component` field (contracts/error-codes.md) and
# `sandbox.components[].component` in the health block.
# ---------------------------------------------------------------------------

COMPONENT_HC = "hc"
COMPONENT_GENERATE_HC_CONFIG = "GenerateHCConfig.exe"

SANDBOX_COMPONENTS: FrozenSet[str] = frozenset({COMPONENT_HC, COMPONENT_GENERATE_HC_CONFIG})

#: Literal install hint (SPEC 13 H1 / contracts/error-codes.md). Exact
#: string -- tests/test_parser_health_block.py asserts on it verbatim.
HC_INSTALL_HINT = "dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool"

#: `expected_path` used whenever `hc` was looked for but not resolved to a
#: concrete file (PATH miss, `dotnet tool list -g` miss or timeout).
#: Matches tests/test_parser_health_block.py's own `HC_EXPECTED_PATH` fixture
#: string, so T011's wiring and this module's own defaults read the same way.
HC_EXPECTED_PATH_DESCRIPTION = "hc (dotnet global tool, PATH / `dotnet tool list -g`)"

#: `hc` discovery signals. Deliberately **not** merged into `CLOSED_SIGNALS`
#: above -- that vocabulary is `parser_core_missing`'s (ParserCore member
#: probe); `parser_tool_missing` (contracts/error-codes.md) has no `signal`
#: field at all, so these values are this module's own bookkeeping, kept
#: separate so a `hc` probe result can never be mistaken for a ParserCore one.
SANDBOX_SIGNAL_NOT_FOUND = "not_found"
SANDBOX_SIGNAL_TIMEOUT = "timeout"
"""Distinct from SANDBOX_SIGNAL_NOT_FOUND on purpose (tasks.md T010 / SPEC
open question 8): a hung `dotnet tool list -g` call must be recorded as a
*timeout*, not silently folded into an indistinguishable "not found". The
`hc -h` probe (CP5 R-03) reuses it for a probe that outlives its bound --
there it means "found, but could not be seen to start"."""
SANDBOX_SIGNAL_RUNTIME_MISSING = "runtime_missing"
"""CP5 FR-004: `hc` is present and is HermitCrab, but the .NET host cannot
start it (the runtime it targets is not installed, or -- for the ``.dll``
form -- there is no ``dotnet`` host at all). "Found but cannot start"."""
SANDBOX_SIGNAL_NOT_HERMITCRAB = "not_hermitcrab"
"""CP5 FR-003: something named `hc` ran, but its `-h` output is not
HermitCrab's usage text. Counts as not found."""

#: Where a hit came from (CP5 FR-001) -- `HcToolDiscovery.source`, and the
#: health block's `detected.hc_source`. Closed, in discovery order.
HC_SOURCE_OVERRIDE = "override"
HC_SOURCE_PATH = "path"
HC_SOURCE_DOTNET_TOOLS_DIR = "dotnet_tools_dir"
HC_SOURCE_DOTNET_TOOL_LIST = "dotnet_tool_list"

HC_SOURCES: FrozenSet[str] = frozenset(
    {HC_SOURCE_OVERRIDE, HC_SOURCE_PATH, HC_SOURCE_DOTNET_TOOLS_DIR, HC_SOURCE_DOTNET_TOOL_LIST}
)

#: The NuGet package id of the `hc` global tool, as `dotnet tool list -g`
#: prints it and as the tool store's folder is named (lower-case).
HC_TOOL_PACKAGE_ID = "sil.machine.morphology.hermitcrab.tool"

#: Env var carrying the T010 "config override" (SPEC 13 H1): an explicit
#: path to the `hc` executable that bypasses PATH and `dotnet` entirely.
#: Mirrors `versioning.py`'s `FIELDWORKS_DLL_PATH` precedent -- for machines
#: where `hc` is installed somewhere PATH doesn't reach (a service account,
#: a restricted shell), and for tests that must not depend on a real
#: `dotnet` install being present.
HC_PATH_ENV_VAR = "HC_TOOL_PATH"

#: Bound on the `dotnet tool list -g` subprocess call (SPEC open question 8,
#: specified here). A slow or hanging call must never block the health
#: response -- this is the module-level constant that enforces that bound.
HC_DISCOVERY_TIMEOUT_SECONDS = 5.0

#: Bound on the `hc -h` identity/startability probe (CP5 R-03).
HC_PROBE_TIMEOUT_SECONDS = 5.0

#: The two usage lines that identify HermitCrab's `hc` (research F-3,
#: Program.cs:164-167). `hc` has no version option; identity is these lines.
_HC_USAGE_LINES: Tuple[str, str] = (
    "Usage: hc [OPTIONS]",
    "HermitCrab.NET is a phonological and morphological parser.",
)

#: .NET host exit codes meaning "cannot start" (research R-03 [LIVE L-5]):
#: FrameworkMissingFailure and the related host-resolution failure. Compared
#: as unsigned DWORDs, since the process may report them signed.
_HOST_FAILURE_EXIT_CODES: FrozenSet[int] = frozenset({0x80008096, 0x8000809A})

_FRAMEWORK_LINE_RE = re.compile(r"Framework:\s*'([^']+)',\s*version\s*'([^']+)'")


def _hc_override_from_env() -> Optional[str]:
    """Read the ``HC_TOOL_PATH`` config override, if set."""
    return os.environ.get(HC_PATH_ENV_VAR)


def _find_hc_via_path() -> Optional[Path]:
    """Look for the ``hc`` dotnet global tool shim on PATH.

    The common case: `dotnet tool install -g` adds its shim directory
    (``~/.dotnet/tools``) to PATH, so once installed, ``hc`` behaves like
    any other console tool.
    """
    found = shutil.which(COMPONENT_HC)
    return Path(found) if found else None


def _dotnet_tools_dir() -> Path:
    """The default dotnet global-tools folder: ``<USERPROFILE>\\.dotnet\\tools``.

    ``USERPROFILE`` first (it is what the dotnet CLI itself uses on Windows),
    falling back to ``Path.home()``.
    """
    profile = os.environ.get("USERPROFILE")
    base = Path(profile) if profile else Path.home()
    return base / ".dotnet" / "tools"


def _find_hc_in_dotnet_tools_dir() -> Optional[Path]:
    """CP5 FR-001 source 3: ``<USERPROFILE>\\.dotnet\\tools\\hc.exe``, checked
    directly -- US1 scenario 2, a server whose PATH predates the install."""
    candidate = _dotnet_tools_dir() / "hc.exe"
    return candidate if candidate.is_file() else None


def _find_hc_via_dotnet_tool_list(*, timeout: float) -> Tuple[Optional[str], Optional[str], bool]:
    """Run ``dotnet tool list -g`` under a bounded ``timeout``, looking for
    the ``hc`` global tool (``SIL.Machine.Morphology.HermitCrab.Tool``).

    Confirms the tool is installed even when its shim isn't (yet) on PATH
    -- e.g. a shell opened before the install ran. Needs a .NET **SDK**; on
    an SDK-less machine it fails, which is why it is the LAST source and
    runs only when the direct checks missed (CP5 R-03).

    A row matches when its package id is ``HC_TOOL_PACKAGE_ID`` or its
    ``Commands`` column names ``hc`` (real output puts the package id first:
    ``sil.machine.morphology.hermitcrab.tool  3.8.2  hc``).

    Output is decoded with an explicit UTF-8 encoding (pattern-audit sweep
    4) -- never the locale's ANSI code page.

    Returns ``(version, error_detail, timed_out)``:

    - ``version``: the version string from the tool-list row, when ``hc``
      is found; ``None`` otherwise.
    - ``error_detail``: diagnostic text for the ``version is None`` case
      -- always present when ``version`` is ``None``.
    - ``timed_out``: ``True`` only when the call was cut off by ``timeout``.

    Never raises: a hanging or failing ``dotnet`` must report "not found",
    not crash the health response.
    """
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return None, "dotnet not found on PATH", False

    try:
        result = subprocess.run(
            [dotnet, "tool", "list", "-g"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"dotnet tool list -g exceeded {timeout}s timeout", True
    except Exception as exc:
        return None, f"dotnet tool list -g failed: {exc}", False

    for line in (result.stdout or "").splitlines():
        parts = line.split()
        if not parts:
            continue
        package = parts[0].lower()
        commands = [p.lower() for p in parts[2:]]
        if package in (HC_TOOL_PACKAGE_ID, COMPONENT_HC) or COMPONENT_HC in commands:
            version = parts[1] if len(parts) > 1 else None
            return version, None, False

    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-1:]
        detail = f"dotnet tool list -g exited {result.returncode}"
        if tail:
            detail += f": {tail[0]}"
        return None, detail, False
    return None, "hc not listed by dotnet tool list -g", False


# ---------------------------------------------------------------------------
# The `hc -h` identity + startability probe (CP5 T030, R-03, FR-003/FR-004)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HcProbe:
    """The outcome of ONE bounded ``hc -h`` run (``probe_hc``).

    ``found``: the output identifies HermitCrab's ``hc`` (or, for a host
    failure, the file is taken to be it -- nothing else fails that way).
    ``starts``: ``True`` when the usage text printed, ``False`` when the
    host could not start it or the run timed out, ``None`` when it was not
    HermitCrab. ``signal``: ``None`` or a ``SANDBOX_SIGNAL_*`` value.
    ``exit_code``: the process's exit code as reported (``None`` if it
    never exited).
    """

    found: bool
    starts: Optional[bool]
    signal: Optional[str] = None
    reason: Optional[str] = None
    exit_code: Optional[int] = None


#: ``probe_hc`` memo: ``(path, size, mtime_ns) -> HcProbe``, process life.
_HC_PROBE_CACHE: dict = {}


def clear_hc_probe_cache() -> None:
    """Forget every memoised ``hc -h`` probe (tests; a reinstall is also
    noticed on its own, since size/mtime change the key)."""
    _HC_PROBE_CACHE.clear()


def hc_invoke_argv(path: Union[str, Path]) -> Optional[List[str]]:
    """How to run the ``hc`` at ``path``, without arguments.

    ``[str(path)]`` for an ``hc.exe`` shim (or any other executable); for
    an ``hc.dll``, ``[<dotnet>, str(path)]`` -- the form the maintainer's
    original script used and the one R-15's no-SDK route produces. Returns
    ``None`` for a ``.dll`` when there is no ``dotnet`` host on PATH.
    """
    path = Path(path)
    if path.suffix.lower() == ".dll":
        dotnet = shutil.which("dotnet")
        if dotnet is None:
            return None
        return [str(dotnet), str(path)]
    return [str(path)]


def _decode_hc_stdout(data) -> str:
    """hc writes UTF-16LE (Console.Out with Encoding.Unicode), BOM optional."""
    if isinstance(data, str):
        return data
    data = data or b""
    if data.startswith(b"\xff\xfe"):
        data = data[2:]
    return data.decode("utf-16-le", errors="replace")


def _decode_hc_stderr(data) -> str:
    """The .NET host writes its failures to stderr as UTF-8."""
    if isinstance(data, str):
        return data
    return (data or b"").decode("utf-8", errors="replace")


def _is_host_failure(exit_code: Optional[int], stderr: str) -> bool:
    if exit_code is not None and (exit_code & 0xFFFFFFFF) in _HOST_FAILURE_EXIT_CODES:
        return True
    lowered = stderr.lower()
    return bool(
        _FRAMEWORK_LINE_RE.search(stderr)
        or "you must install or update .net" in lowered
        or ("framework" in lowered and ("not found" in lowered or "missing" in lowered))
    )


def classify_hc_help(exit_code: Optional[int], stdout, stderr) -> HcProbe:
    """R-03's classification table over one ``hc -h`` run's raw output.

    Pure: ``stdout`` is decoded UTF-16LE (BOM tolerated) and ``stderr``
    UTF-8 when given as bytes.
    """
    out = _decode_hc_stdout(stdout)
    err = _decode_hc_stderr(stderr)

    lines = {line.strip() for line in out.splitlines()}
    if all(usage in lines for usage in _HC_USAGE_LINES):
        return HcProbe(found=True, starts=True, exit_code=exit_code)

    if _is_host_failure(exit_code, err):
        match = _FRAMEWORK_LINE_RE.search(err)
        if match:
            reason = (
                f"hc needs the .NET runtime {match.group(1)} {match.group(2)}, "
                "which is not installed"
            )
        elif exit_code is not None:
            reason = (
                "hc could not start: the .NET host reported a missing runtime "
                f"(exit 0x{exit_code & 0xFFFFFFFF:08X})"
            )
        else:
            reason = "hc could not start: the .NET host reported a missing runtime"
        return HcProbe(
            found=True,
            starts=False,
            signal=SANDBOX_SIGNAL_RUNTIME_MISSING,
            reason=reason,
            exit_code=exit_code,
        )

    first = next((line.strip() for line in out.splitlines() if line.strip()), "")
    detail = f"; it printed {first!r}" if first else ""
    return HcProbe(
        found=False,
        starts=None,
        signal=SANDBOX_SIGNAL_NOT_HERMITCRAB,
        reason=f"`hc -h` did not print HermitCrab's usage text{detail}",
        exit_code=exit_code,
    )


def probe_hc(path: Union[str, Path], *, timeout: float = HC_PROBE_TIMEOUT_SECONDS) -> HcProbe:
    """Run ``hc -h`` once -- identity (FR-003) and startability (FR-004).

    ``hc -h`` prints usage and exits before any ``-i`` is read (research
    F-2), so this loads no grammar and parses nothing (the CP1 invariant,
    narrowed by R-04 to exactly this argv). Stdin is closed, the run is
    bounded by ``timeout``, and output is captured as bytes: stdout is
    UTF-16LE, stderr UTF-8, so no single ``encoding=`` could serve both.

    Memoised for the process on ``(path, size, mtime_ns)``, so a reinstall
    is re-probed. A timeout or a missing ``dotnet`` host is not memoised
    (both are about the machine, not the file).
    """
    path = Path(path)
    try:
        st = path.stat()
        key: Optional[tuple] = (str(path), st.st_size, st.st_mtime_ns)
    except OSError:
        key = None
    if key is not None and key in _HC_PROBE_CACHE:
        return _HC_PROBE_CACHE[key]

    argv = hc_invoke_argv(path)
    if argv is None:
        return HcProbe(
            found=True,
            starts=False,
            signal=SANDBOX_SIGNAL_RUNTIME_MISSING,
            reason=f"cannot run {path.name}: dotnet host not found on PATH",
        )

    try:
        completed = subprocess.run(
            argv + ["-h"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return HcProbe(
            found=True,
            starts=False,
            signal=SANDBOX_SIGNAL_TIMEOUT,
            reason=f"`hc -h` did not finish within {timeout}s",
        )
    except OSError as exc:
        result = HcProbe(
            found=False,
            starts=None,
            signal=SANDBOX_SIGNAL_NOT_HERMITCRAB,
            reason=f"`hc -h` could not be run: {exc}",
        )
    else:
        result = classify_hc_help(completed.returncode, completed.stdout, completed.stderr)

    if key is not None:
        _HC_PROBE_CACHE[key] = result
    return result


# ---------------------------------------------------------------------------
# Discovery (T010, extended by CP5 T030/T031)
# ---------------------------------------------------------------------------


@dataclass
class HcToolDiscovery(ProbeResult):
    """``discover_hc_tool``'s result: a ``ProbeResult`` (so every existing
    reader keeps working) plus CP5's discovery facts.

    - ``ok`` -- ``found and starts is True``.
    - ``signal`` -- ``None`` or one of ``not_found`` / ``timeout`` /
      ``runtime_missing`` / ``not_hermitcrab``.
    - ``expected_path`` -- the path found, or the one looked at, or
      ``HC_EXPECTED_PATH_DESCRIPTION`` when there is no single file.
    - ``detected_version`` -- the hc tool version (T031); reported, never
      compared.
    - ``load_error`` -- the same text as ``reason`` (kept for back-compat).
    - ``found`` -- a HermitCrab ``hc`` was located and identified.
    - ``starts`` -- from the ``hc -h`` probe; ``None`` when not observed
      (a ``dotnet tool list`` hit has no file to run).
    - ``source`` -- one of ``HC_SOURCES``; ``None`` only when nothing hit.
    - ``path`` -- the concrete file (``None`` for a listing hit or a miss).
    - ``reason`` -- human text for any not-ready outcome.
    - ``invoke_argv`` -- how to run it: ``[path]`` or ``[dotnet, path]``.
    """

    found: bool = False
    starts: Optional[bool] = None
    source: Optional[str] = None
    path: Optional[str] = None
    reason: Optional[str] = None
    invoke_argv: Optional[List[str]] = None


def _discovery_from_file(path: Path, source: str) -> HcToolDiscovery:
    """Probe one file hit and shape it into an ``HcToolDiscovery``."""
    probe = probe_hc(path)
    if not probe.found:
        return HcToolDiscovery(
            ok=False,
            signal=probe.signal,
            expected_path=str(path),
            load_error=probe.reason,
            found=False,
            starts=None,
            source=source,
            path=None,
            reason=probe.reason,
        )
    return HcToolDiscovery(
        ok=probe.starts is True,
        signal=probe.signal,
        expected_path=str(path),
        detected_version=_hc_tool_version(path),
        load_error=probe.reason,
        found=True,
        starts=probe.starts,
        source=source,
        path=str(path),
        reason=probe.reason,
        invoke_argv=hc_invoke_argv(path),
    )


def discover_hc_tool(
    *,
    override_path: Optional[Path] = None,
    timeout: float = HC_DISCOVERY_TIMEOUT_SECONDS,
) -> HcToolDiscovery:
    """Locate, identify and start-check the ``hc`` tool (SPEC 13 H1, CP5 FR-001..FR-005).

    ``hc`` is a **dotnet global tool** (``PackAsTool=true``,
    ``ToolCommandName=hc``, on nuget.org), installed by
    ``dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool`` into
    the user's dotnet tools shim directory. It is emphatically **not** at
    ``%LOCALAPPDATA%\\HermitCrabTool\\hc.dll`` -- an earlier, wrong draft of
    the spec assumed that path; do not reintroduce it.

    Four sources, in order (FR-001); the one that succeeded is ``source``:

    1. ``"override"`` -- ``override_path``, else the ``HC_TOOL_PATH`` env
       var. Final: a missing file, or one that is not HermitCrab, never
       falls through to the other sources.
    2. ``"path"`` -- ``shutil.which("hc")``.
    3. ``"dotnet_tools_dir"`` -- ``<USERPROFILE>\\.dotnet\\tools\\hc.exe``,
       checked directly (a server whose PATH predates the install).
    4. ``"dotnet_tool_list"`` -- ``dotnet tool list -g``, bounded by
       ``timeout``; it runs only when 1-3 found nothing HermitCrab. Its
       timeout is ``signal="timeout"``, never folded into "not found".

    A file hit (1-3) is accepted as ``hc.exe`` or as ``hc.dll`` (run as
    ``dotnet hc.dll``) and is checked by one bounded ``hc -h`` run
    (``probe_hc``). A ``not_hermitcrab`` hit at 2 or 3 falls through; if
    nothing later finds hc, the first such rejection is returned. A
    listing hit (4) names the HermitCrab package, which is its identity
    check, but has no file to run: ``found=True``, ``starts=None``, so it
    never reads as ready.
    """
    override = override_path if override_path is not None else _hc_override_from_env()
    if override is not None:
        override = Path(override)
        if not override.is_file():
            reason = f"{HC_PATH_ENV_VAR} override does not exist: {override}"
            return HcToolDiscovery(
                ok=False,
                signal=SANDBOX_SIGNAL_NOT_FOUND,
                expected_path=str(override),
                load_error=reason,
                found=False,
                source=HC_SOURCE_OVERRIDE,
                reason=reason,
            )
        return _discovery_from_file(override, HC_SOURCE_OVERRIDE)

    first_rejected: Optional[HcToolDiscovery] = None
    for source, find in (
        (HC_SOURCE_PATH, _find_hc_via_path),
        (HC_SOURCE_DOTNET_TOOLS_DIR, _find_hc_in_dotnet_tools_dir),
    ):
        candidate = find()
        if candidate is None:
            continue
        result = _discovery_from_file(candidate, source)
        if result.found:
            return result
        if first_rejected is None:
            first_rejected = result

    version, error_detail, timed_out = _find_hc_via_dotnet_tool_list(timeout=timeout)
    if version is not None:
        reason = (
            "hc is listed by `dotnet tool list -g`, but no hc executable was found "
            f"to run (not on PATH, not at {_dotnet_tools_dir() / 'hc.exe'})"
        )
        return HcToolDiscovery(
            ok=False,
            signal=None,
            expected_path=HC_EXPECTED_PATH_DESCRIPTION,
            detected_version=version,
            load_error=reason,
            found=True,
            starts=None,
            source=HC_SOURCE_DOTNET_TOOL_LIST,
            reason=reason,
        )

    if first_rejected is not None:
        return first_rejected

    return HcToolDiscovery(
        ok=False,
        signal=SANDBOX_SIGNAL_TIMEOUT if timed_out else SANDBOX_SIGNAL_NOT_FOUND,
        expected_path=HC_EXPECTED_PATH_DESCRIPTION,
        load_error=error_detail,
        found=False,
        reason=error_detail,
    )


# ---------------------------------------------------------------------------
# Versions (CP5 T031, FR-005, R-03) -- reported, never compared to a floor
# ---------------------------------------------------------------------------

#: FieldWorks' bundled HermitCrab library (and the one beside an unpacked
#: ``hc.dll``). Its ``FileVersion`` is the HermitCrab engine version.
FIELDWORKS_HERMITCRAB_DLL = "SIL.Machine.Morphology.HermitCrab.dll"

#: Advisory code (contracts/tools.md section 5.1): the sandbox's HermitCrab
#: differs from FieldWorks' own. A warning, never a refusal (Q3).
ADVISORY_HC_ENGINE_VERSION_SKEW = "hc_engine_version_skew"

_VS_FIXEDFILEINFO_SIGNATURE = 0xFEEF04BD


def read_file_version(path: Union[str, Path, None]) -> Optional[str]:
    """A file's Win32 ``FileVersion`` as ``"a.b.c.d"``, or ``None``.

    Read through ``GetFileVersionInfoW`` / ``VerQueryValueW`` via ``ctypes``
    (the fixed ``VS_FIXEDFILEINFO`` block) -- no pythonnet and no assembly
    load, so health stays cheap. ``None`` for a missing file, a file with no
    version resource, or a non-Windows host. Never raises.

    Every version read in this module goes through this one name, so tests
    monkeypatch it.
    """
    if path is None or sys.platform != "win32":
        return None
    try:
        target = str(path)
        if not os.path.isfile(target):
            return None

        import ctypes
        from ctypes import wintypes

        version_dll = ctypes.WinDLL("version")
        get_size = version_dll.GetFileVersionInfoSizeW
        get_size.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        get_size.restype = wintypes.DWORD
        get_info = version_dll.GetFileVersionInfoW
        get_info.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
        get_info.restype = wintypes.BOOL
        query = version_dll.VerQueryValueW
        query.argtypes = [
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.UINT),
        ]
        query.restype = wintypes.BOOL

        size = get_size(target, None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not get_info(target, 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = wintypes.UINT()
        if not query(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)):
            return None
        if not pointer.value or length.value < 16:
            return None
        # VS_FIXEDFILEINFO: dwSignature, dwStrucVersion, dwFileVersionMS, dwFileVersionLS, ...
        fixed = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32 * 4)).contents
        if fixed[0] != _VS_FIXEDFILEINFO_SIGNATURE:
            return None
        ms, ls = fixed[2], fixed[3]
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception:  # noqa: BLE001 -- a version is informational; never fail health on it
        return None


def _safe_file_version(path: Union[str, Path, None]) -> Optional[str]:
    """``read_file_version`` with a backstop, for a patched or failing reader."""
    try:
        return read_file_version(path)
    except Exception:  # noqa: BLE001
        return None


def _numeric_version(value: str) -> Optional[Tuple[int, ...]]:
    parts = value.strip().split(".")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return None
    while len(numbers) < 4:
        numbers.append(0)
    return tuple(numbers)


def hermitcrab_versions_differ(a: Optional[str], b: Optional[str]) -> bool:
    """The skew flag: do two HermitCrab versions differ?

    ``False`` when either is unknown. Dotted numeric versions compare as
    4-part tuples padded with zeros (``"3.8.2"`` equals ``"3.8.2.0"``);
    anything else compares as the raw strings. Only ever a warning
    (``ADVISORY_HC_ENGINE_VERSION_SKEW``) -- never a floor, never a refusal.
    """
    if a is None or b is None:
        return False
    left, right = _numeric_version(a), _numeric_version(b)
    if left is not None and right is not None:
        return left != right
    return a.strip() != b.strip()


def _version_sort_key(name: str) -> Tuple[int, Tuple[int, ...], str]:
    numeric = _numeric_version(name)
    return (1, numeric, name) if numeric is not None else (0, (), name)


def _hc_tool_version(path: Union[str, Path]) -> Optional[str]:
    """The hc tool's version, for a file hit (R-03). Reported, never compared.

    1. The ``<ver>`` segment right after ``.store\\<HC_TOOL_PACKAGE_ID>\\``
       when ``path`` lies inside the tool store (a ``.dll`` hit there).
    2. A shim's sibling store: ``<shim dir>\\.store\\<package>\\<ver>\\``
       (the highest version, if several are left behind).
    3. For a ``.dll`` outside the store, the ``FileVersion`` of
       ``SIL.Machine.Morphology.HermitCrab.dll`` beside it.

    (A ``dotnet tool list -g`` hit carries the row's version instead; see
    ``discover_hc_tool``.)
    """
    path = Path(path)
    parts = path.parts
    lowered = [part.lower() for part in parts]
    for index in range(len(lowered) - 2):
        if lowered[index] == ".store" and lowered[index + 1] == HC_TOOL_PACKAGE_ID:
            return parts[index + 2]

    store = path.parent / ".store" / HC_TOOL_PACKAGE_ID
    try:
        versions = [child.name for child in store.iterdir() if child.is_dir()]
    except OSError:
        versions = []
    if versions:
        return max(versions, key=_version_sort_key)

    if path.suffix.lower() == ".dll":
        return _safe_file_version(path.parent / FIELDWORKS_HERMITCRAB_DLL)
    return None


def discover_generate_hc_config(*, search_paths: Optional[List[Path]] = None) -> ProbeResult:
    """Locate ``GenerateHCConfig.exe`` (SPEC 13 H1 / tasks.md T010).

    Unlike ``hc``, ``GenerateHCConfig.exe`` ships *with* FieldWorks itself
    rather than as a separately-installed dotnet tool, so it is looked up
    the same way ``probe_parser_core`` looks up ``ParserCore.dll``: as a
    plain filesystem check in the FieldWorks directory resolved by
    ``get_resolved_fieldworks_dir()`` / ``locate_liblcm_dll()`` -- never on
    PATH, never via ``dotnet tool list -g``, and with no timeout, since
    there is no subprocess call to bound.

    Returns a ``ProbeResult``. Not found: ``ok=False``,
    ``signal=SANDBOX_SIGNAL_NOT_FOUND``, ``expected_path`` naming the
    resolved FieldWorks directory it would live in (or the bare filename if
    no FieldWorks install resolves at all -- mirrors
    ``probe_parser_core``'s ``SIGNAL_ABSENT`` formatting for
    ``ParserCore.dll``). Found: ``ok=True``, ``expected_path`` is the
    resolved file path.
    """
    fieldworks_dir = get_resolved_fieldworks_dir(search_paths=search_paths)
    exe_path = locate_liblcm_dll(dll_name=COMPONENT_GENERATE_HC_CONFIG, search_paths=search_paths)

    if exe_path is None:
        expected_path = (
            str(Path(fieldworks_dir) / COMPONENT_GENERATE_HC_CONFIG)
            if fieldworks_dir
            else COMPONENT_GENERATE_HC_CONFIG
        )
        return ProbeResult(
            ok=False,
            signal=SANDBOX_SIGNAL_NOT_FOUND,
            expected_path=expected_path,
        )

    return ProbeResult(ok=True, expected_path=str(exe_path))


# ---------------------------------------------------------------------------
# ParserDetector aggregate (T011)
#
# The seam ``handlers/diagnostic_health.py`` consumes (data-model.md
# "ParserDetector return shape"). This section composes T009's member probe
# and T010's tool discovery; it introduces no new location or reflection
# logic of its own -- that stays owned by the probes it calls.
# ---------------------------------------------------------------------------


@dataclass
class SandboxProbe:
    """``sandbox_probe`` -- the two sandbox-tool probes, bundled.

    Two independent ``ProbeResult``s rather than one combined boolean: `hc`
    and ``GenerateHCConfig.exe`` fail independently (T010), and a caller
    needs to know which one to install (contracts/flextools_health-parser-block.md
    ``sandbox.components``).
    """

    hc: ProbeResult
    generate_config: ProbeResult


#: ``AgentProbeState`` (data-model.md / tasks.md T025 -- "pin these names
#: exactly"). Three-valued on purpose -- ``skipped`` is a distinct outcome
#: from ``present``/``absent``, never collapsible into either, so it can
#: never be misread as a pass. Exposed both as the plain string constants
#: below (for internal comparisons) and as the ``Literal`` type alias
#: (``AgentProbeState`` itself) tests/test_parser_agent_probe.py introspects
#: via ``typing.get_args`` -- a closed, three-valued *type*, not a class that
#: also carries the probe's companion fields (that is ``AgentProbeResult``,
#: below). Keeping the vocabulary and the result payload as two separate
#: names is what lets ``AgentProbeResult`` skip an ``ok`` field entirely
#: (see its docstring) instead of needing one to disambiguate ``skipped``
#: from a pass.
AGENT_STATE_PRESENT = "present"
AGENT_STATE_ABSENT = "absent"
AGENT_STATE_SKIPPED = "skipped"

AGENT_STATES: FrozenSet[str] = frozenset(
    {AGENT_STATE_PRESENT, AGENT_STATE_ABSENT, AGENT_STATE_SKIPPED}
)

AgentProbeState = Literal["present", "absent", "skipped"]
"""The closed vocabulary itself (data-model.md's ``AgentProbeState``), as a
type alias rather than an ``Enum`` -- matching ``response_models.py``'s own
``Literal["bootstrap_absent", "lookup_failed"]``-style closed vocabularies
elsewhere in this feature, and giving ``typing.get_args(AgentProbeState)``
the exact three values above."""


#: ``probe_source`` (contracts/error-codes.md's ``parser_agent_missing``).
#: Two-valued and closed, case-sensitive. ``bootstrap_absent`` is reported
#: when the caught ``KeyNotFoundException``'s own message names
#: ``HC_AGENT_GUID`` -- the documented, ordinary cause (SPEC 12.7 /
#: contracts/error-codes.md: ``BootstrapNewLanguageProject.SetupAgents``
#: creates three agents and *not* ``kguidAgentHermitCrabParser``, so a
#: lookup naming exactly that GUID is confidently attributed to "never
#: bootstrapped" rather than some other repository fault).
#: ``lookup_failed`` is the safe fallback for any other ``KeyNotFoundException``
#: shape -- one that does not name our GUID -- where the mechanism (the
#: lookup failed) is all ``probe_hc_agent`` can confidently report.
PROBE_SOURCE_BOOTSTRAP_ABSENT = "bootstrap_absent"
PROBE_SOURCE_LOOKUP_FAILED = "lookup_failed"

PROBE_SOURCES: FrozenSet[str] = frozenset(
    {PROBE_SOURCE_BOOTSTRAP_ABSENT, PROBE_SOURCE_LOOKUP_FAILED}
)

#: The HermitCrab parser agent's identity (SPEC 12.7 / contracts/error-codes.md).
#: ``HC_AGENT_GUID`` is the C# symbol name (``CmAgentTags.kguidAgentHermitCrabParser``),
#: not a raw UUID -- matches tests/test_parser_health_block.py's own fixture
#: precedent for the ``agent_guid`` value. ``HC_AGENT_NAME`` is literally
#: ``"HermitCrab"`` (tasks.md T025: "agent_name is literally 'HermitCrab'").
HC_AGENT_GUID = "kguidAgentHermitCrabParser"
HC_AGENT_NAME = "HermitCrab"


@dataclass
class AgentProbeResult:
    """The HC-agent probe's return payload -- ``AgentProbeState`` (the
    closed vocabulary above) plus its companion fields, bundled the way the
    ``ParserDetector`` table describes ("agent_probe: AgentProbeState plus
    {agent_guid, active_engine} when absent"), extended with
    ``agent_name``/``probe_source``/``hint`` so a caller can build a
    ``parser_agent_missing`` payload (contracts/error-codes.md) straight off
    this object with no reshaping.

    **Deliberately carries no ``ok`` field**, unlike ``ProbeResult``. That is
    the whole reason this is modelled as its own class rather than reusing
    ``ProbeResult``: a caller checking ``result.ok`` on a ``skipped`` probe
    would have to know to also check ``state`` first, and a *missing*
    attribute forces that -- ``skipped`` can never be flattened into a pass
    by truthiness alone (data-model.md's ``AgentProbeState`` invariant; SPEC
    16 tests this directly, see ``tests/test_parser_agent_probe.py``'s
    ``TestSkippedNeverAPass``).

    At CP1, every ``ParserDetector`` still reports ``state=AGENT_STATE_SKIPPED``
    with every companion left ``None`` -- ``flextools_health`` never opens a
    project (research D2). ``probe_hc_agent`` below is the real,
    project-aware implementation, shipped for CP2 callers but not wired into
    ``ParserDetector``/any handler at CP1.
    """

    state: str
    agent_guid: Optional[str] = None
    agent_name: Optional[str] = None
    active_engine: Optional[str] = None
    probe_source: Optional[str] = None
    hint: Optional[str] = None


@dataclass
class ParserVersions:
    """``versions`` -- reported, never compared (see module docstring's
    ``detected_version`` note; the same rule applies here)."""

    parser_core_version: Optional[str] = None
    lcmodel_install_path: Optional[str] = None
    hc_tool_version: Optional[str] = None
    #: CP5 FR-005: FieldWorks' bundled HermitCrab (``FIELDWORKS_HERMITCRAB_DLL``).
    fieldworks_hermitcrab_version: Optional[str] = None
    #: CP5 FR-005: ``GenerateHCConfig.exe``'s own ``FileVersion``.
    generate_hc_config_version: Optional[str] = None
    #: ``hermitcrab_versions_differ(hc_tool_version, fieldworks_hermitcrab_version)``
    #: -- a warning (``ADVISORY_HC_ENGINE_VERSION_SKEW``), never a refusal.
    hc_engine_version_skew: bool = False


# ---------------------------------------------------------------------------
# Engine gate: check_active_parser (T024, SPEC 3.2 / 12.7)
#
# The shared preflight helper (SPEC.md:1663-1674): called as the **first
# statement** of each spine-executing handler (`try_word`, `parse_text`,
# `parse_sandbox`), before any `HCParser`/config-export construction, so a
# project on the wrong engine is refused before any parser work starts.
# `parse_diff`/`parse_log`/`parse_status` never call it -- they read prior
# artifacts, not the live engine. Not wired into any handler at CP1 (that
# wiring is CP2's); this module ships the helper correct and tested with no
# caller yet.
# ---------------------------------------------------------------------------


class ParserEngineMismatchError(Exception):
    """Raised by ``check_active_parser`` on an engine mismatch.

    ``detail`` is a plain dict shaped exactly like
    ``response_models.ParserEngineMismatchDetail`` (``error_code``,
    ``configured_engine``, ``supported_engines``, ``hint``) so a caller can
    round-trip it through ``response_models.validate_detail()`` without any
    reshaping -- the same discriminated-union path T006 already covers for
    every other per-code detail model.
    """

    def __init__(self, detail: dict) -> None:
        self.detail = detail
        super().__init__(detail.get("hint", "parser_engine_mismatch"))


def check_active_parser(project, *, supported_engines: Tuple[str, ...] = ("HC",)) -> None:
    """Refuse before any parser work if ``project``'s active engine is not
    in ``supported_engines`` (SPEC 3.2 / 12.7).

    Reads ``project.MorphologicalDataOA.ActiveParser`` -- already a resolved
    plain string in production, computed inside FieldWorks' own C# getter
    (``OverridesLing_MoClasses.cs:4213``, ``ParserWorker.cs:65``). This
    function does no XML parsing itself and never constructs an
    ``HCParser``/``LcmCache``/anything CLR-side; it only reads one property
    off an already-open project object and compares a string. That is also
    why the fail-safe-on-corruption property (SPEC 3.2) holds here without
    this function doing any extra work: the corrupt-XML -> ``"XAmple"``
    default lives entirely in the C# getter this reads, so a corrupt
    ``ParserParameters`` value can never surface here as anything other than
    the literal string ``"XAmple"`` -- there is no local fallback path that
    could be miswired to default to ``"HC"`` instead.

    Comparison is a **case-sensitive, closed-set membership test**
    (``configured_engine in supported_engines``) against whatever string
    ``ActiveParser`` returns -- no ``.lower()``/``.casefold()``/``.strip()``
    normalisation. FieldWorks only ever yields exactly ``"XAmple"`` or
    ``"HC"``; recasing a mismatch into an accidental match would be a
    contract violation (SPEC 3.2), not a convenience.

    **Live re-read, every call, deliberately uncached.** The property is
    read exactly once per call, directly off ``project.MorphologicalDataOA``,
    with no module-level dict, no ``functools.lru_cache``, no per-project or
    per-session memo of any kind -- ``ActiveParser`` is user-flippable
    mid-session (Words > Parser > Choose Parser, SPEC 5.6), so caching it
    across calls would let a stale verdict survive a live flip.

    Raises ``ParserEngineMismatchError`` on mismatch, carrying a ``detail``
    dict with ``configured_engine`` (the raw string read, uppercase/lowercase
    included -- never normalised even in the error payload),
    ``supported_engines`` (as a plain ``list``) and a non-empty ``hint``.
    Returns ``None`` on a match; never raises in that case.
    """
    configured_engine = project.MorphologicalDataOA.ActiveParser

    if configured_engine in supported_engines:
        return None

    supported_list = list(supported_engines)
    hint = (
        f"This project's active parser is {configured_engine!r}, but this "
        f"operation requires one of {supported_list!r}. Switch the active "
        "parser in FieldWorks via Words > Parser > Choose Parser, or run "
        "this operation against a project configured for a supported engine."
    )
    raise ParserEngineMismatchError(
        {
            "error_code": "parser_engine_mismatch",
            "configured_engine": configured_engine,
            "supported_engines": supported_list,
            "hint": hint,
        }
    )


def probe_hc_agent(project, active_engine: Optional[str]) -> AgentProbeResult:
    """The HC-agent probe (T025, SPEC 12.7): resolve the HermitCrab parser
    agent from an already-open project's agent repository, never letting the
    documented ``KeyNotFoundException`` escape.

    Reads exactly one property off an already-open project --
    ``project.LangProject.DefaultParserAgent`` -- which SPEC 12.7 documents
    as resolving ``ICmAgentRepository.GetObject(CmAgentTags.
    kguidAgentHermitCrabParser)`` when ``ActiveParser == "HC"``, and whose
    own XML doc comment declares ``<exception cref="KeyNotFoundException"/>``
    as expected .NET behaviour when that agent was never created. This
    function does no XML parsing, constructs no ``HCParser``/``LcmCache``,
    loads no grammar and parses no word -- it is a single property read on
    an object the caller already holds open (CP1 boundary).

    ``project=None`` -- the normal ``flextools_health`` case, since that
    handler never opens a project (research D2) -- short-circuits to
    ``state=AGENT_STATE_SKIPPED`` before touching ``project`` at all.
    **Never reads as a pass**: ``AgentProbeResult`` carries no ``ok`` field
    (see its docstring), so a ``skipped`` result cannot be mistaken for one.

    **Independent of ``probe_parser_core`` by construction.** This function
    never calls, imports, or otherwise touches ``probe_parser_core`` (or
    anything that does) -- resolving the agent is a read entirely separate
    from the ``ParserCore.dll`` member-surface probe that decides
    ``read``/``write`` spine status. A missing/dead agent must never blank
    the read spine (contracts/error-codes.md: "flextools_try_word neither
    files nor resolves an agent").

    **Catching ``KeyNotFoundException`` without importing it.** The real
    exception is a .NET type (``System.Collections.Generic.
    KeyNotFoundException``) surfaced through pythonnet; importing it here
    would require a CLR runtime to be loadable on every call, including the
    ``state=AGENT_STATE_PRESENT`` path where no exception is thrown at all.
    Instead this catches broadly and checks the caught instance's own class
    name -- ``type(exc).__name__ == "KeyNotFoundException"`` -- which needs
    no CLR import and works whether pythonnet is loaded or not; anything
    else re-raises unchanged, so this function only ever suppresses the one
    documented exception SPEC 12.7 names, never an unrelated bug.

    **``probe_source`` mapping (contracts/error-codes.md's two closed
    values).** The caught exception's own message is inspected for
    ``HC_AGENT_GUID``: when present, the lookup failure is confidently
    attributed to the documented, ordinary cause (SPEC 12.7:
    ``BootstrapNewLanguageProject.SetupAgents`` creates three agents and not
    this one) and reported as ``PROBE_SOURCE_BOOTSTRAP_ABSENT``; any other
    ``KeyNotFoundException`` shape -- one that does not name our GUID --
    reports the more conservative ``PROBE_SOURCE_LOOKUP_FAILED``, since only
    the mechanism (the lookup failed), not the semantic cause, is known.

    Returns an ``AgentProbeResult``:

    - ``state=AGENT_STATE_SKIPPED`` when ``project is None``.
    - ``state=AGENT_STATE_ABSENT`` on a caught ``KeyNotFoundException``, with
      ``agent_guid``/``agent_name``/``active_engine``/``probe_source``/``hint``
      all populated -- this shape round-trips through
      ``response_models.validate_detail()`` as a ``parser_agent_missing``
      payload with no reshaping.
    - ``state=AGENT_STATE_PRESENT`` when the property read succeeds, with
      ``agent_guid``/``agent_name``/``active_engine`` populated and
      ``probe_source``/``hint`` left ``None`` (nothing to explain).

    Never raises for the documented failure mode; any other exception from
    the property read propagates unchanged (a probe that silently swallows
    an unrelated bug tells the caller nothing).
    """
    if project is None:
        return AgentProbeResult(state=AGENT_STATE_SKIPPED)

    try:
        _ = project.LangProject.DefaultParserAgent
    except Exception as exc:
        if type(exc).__name__ != "KeyNotFoundException":
            raise

        probe_source = (
            PROBE_SOURCE_BOOTSTRAP_ABSENT
            if HC_AGENT_GUID in str(exc)
            else PROBE_SOURCE_LOOKUP_FAILED
        )
        hint = (
            f"The {HC_AGENT_NAME} parser agent ({HC_AGENT_GUID}) was not "
            f"found in this project's agent repository, but the active "
            f"parser is {active_engine!r}. FieldWorks does not create this "
            "agent when a project is bootstrapped; open the project in "
            "FieldWorks with the HC parser active (Words > Parser > Choose "
            "Parser) and run Try a Word once so FieldWorks creates it, then "
            "retry this operation."
        )
        return AgentProbeResult(
            state=AGENT_STATE_ABSENT,
            agent_guid=HC_AGENT_GUID,
            agent_name=HC_AGENT_NAME,
            active_engine=active_engine,
            probe_source=probe_source,
            hint=hint,
        )

    return AgentProbeResult(
        state=AGENT_STATE_PRESENT,
        agent_guid=HC_AGENT_GUID,
        agent_name=HC_AGENT_NAME,
        active_engine=active_engine,
    )


def _safe_probe(compute, *, expected_path: Optional[str] = None) -> ProbeResult:
    """Run one probe's ``compute`` thunk, converting any unexpected throw
    into a ``ProbeResult(ok=False, signal=SIGNAL_LOAD_FAILED, ...)`` instead
    of letting it propagate.

    This is the structural guarantee behind "one dead spine must not blank
    the others" (contracts/flextools_health-parser-block.md): every spine
    computed by ``ParserDetector.__init__`` below is wrapped in its own call
    to ``_safe_probe``, on its own statement, so a throw while computing one
    spine cannot prevent the statements computing the other spines from
    running at all -- there is no shared early-return or try/except spanning
    more than one spine's computation. ``probe_parser_core``,
    ``discover_hc_tool`` and ``discover_generate_hc_config`` already catch
    internally and never raise in practice; this wrapper is an additional,
    independent backstop so that invariant holds even if a future change to
    one of them regresses that.
    """
    try:
        return compute()
    except Exception as exc:
        return ProbeResult(
            ok=False,
            signal=SIGNAL_LOAD_FAILED,
            expected_path=expected_path,
            missing_members=[],
            detected_version=None,
            load_error=str(exc),
        )


class ParserDetector:
    """The CP1 detection aggregate -- the seam ``diagnostic_health.py``
    consumes (data-model.md "ParserDetector return shape").

    Composes, and adds no location or reflection logic beyond, T009's
    ``probe_parser_core`` and T010's ``discover_hc_tool`` /
    ``discover_generate_hc_config``. Detection is eager: every field below
    is a plain attribute populated by ``__init__``, not a property computed
    lazily on first access -- constructing a ``ParserDetector`` with no
    required positional args is itself the detection call.

    Attributes (data-model.md's ``ParserDetector`` return shape, field names
    pinned verbatim -- do not rename):

    - ``read_probe``: ``ProbeResult`` over ``HCPARSER_MEMBERS``.
    - ``write_probe``: ``ProbeResult`` over ``WRITE_REQUIRED_MEMBERS``
      (``HCPARSER_MEMBERS`` plus ``ParseFiler.ProcessParse``). Decided by
      the member probe **alone** -- never influenced by ``agent_probe``.
    - ``sandbox_probe``: ``SandboxProbe(hc, generate_config)``.
    - ``agent_probe``: ``AgentProbeResult`` (whose ``.state`` is an
      ``AgentProbeState``), unconditionally ``state=AGENT_STATE_SKIPPED`` at
      CP1 (D2 -- no project is ever open in this code path; T025's real,
      project-aware ``probe_hc_agent`` is not called here). Never flattened
      into ``ok=True`` or a ``ready`` status -- see ``AgentProbeResult``'s
      docstring.
    - ``active_engine``: unconditionally ``None`` at CP1 (research D8 --
      same premise as ``agent_probe``: reading ``ActiveParser`` needs an
      open project). Informational only; never an input to any status
      decision, here or in ``diagnostic_health.py``.
    - ``versions``: ``ParserVersions(parser_core_version,
      lcmodel_install_path, hc_tool_version)`` -- reported, never compared.

    **One dead spine must not blank the others.** Each of ``read_probe``,
    ``write_probe`` and ``sandbox_probe`` is computed by its own statement
    in ``__init__``, each wrapped independently by ``_safe_probe`` (see its
    docstring) -- there is no shared early-return or enclosing try/except
    that could let a failure computing one spine swallow the rest.
    """

    def __init__(self, *, search_paths: Optional[List[Path]] = None) -> None:
        self.read_probe: ProbeResult = _safe_probe(
            lambda: probe_parser_core(HCPARSER_MEMBERS, search_paths=search_paths)
        )
        self.write_probe: ProbeResult = _safe_probe(
            lambda: probe_parser_core(WRITE_REQUIRED_MEMBERS, search_paths=search_paths)
        )

        hc_probe: ProbeResult = _safe_probe(
            discover_hc_tool, expected_path=HC_EXPECTED_PATH_DESCRIPTION
        )
        generate_config_probe: ProbeResult = _safe_probe(
            lambda: discover_generate_hc_config(search_paths=search_paths)
        )
        self.sandbox_probe: SandboxProbe = SandboxProbe(
            hc=hc_probe, generate_config=generate_config_probe
        )

        # CP1: no project is ever open in this code path (D2), so the
        # agent probe is unconditionally skipped and active_engine is
        # unconditionally null (D8) -- neither may read as a pass.
        self.agent_probe: AgentProbeResult = AgentProbeResult(state=AGENT_STATE_SKIPPED)
        self.active_engine: Optional[str] = None

        fieldworks_dir = get_resolved_fieldworks_dir(search_paths=search_paths)
        # CP5 FR-005: three versions, reported and never compared to a floor.
        # Only the two HermitCrab versions are compared -- with each other,
        # for the skew advisory -- and that never touches any status.
        hc_tool_version = hc_probe.detected_version
        fieldworks_hermitcrab_version = (
            _safe_file_version(Path(fieldworks_dir) / FIELDWORKS_HERMITCRAB_DLL)
            if fieldworks_dir
            else None
        )
        generate_hc_config_version = (
            _safe_file_version(generate_config_probe.expected_path)
            if generate_config_probe.ok and generate_config_probe.expected_path
            else None
        )
        self.versions: ParserVersions = ParserVersions(
            parser_core_version=self.read_probe.detected_version
            or self.write_probe.detected_version,
            lcmodel_install_path=str(fieldworks_dir) if fieldworks_dir else None,
            hc_tool_version=hc_tool_version,
            fieldworks_hermitcrab_version=fieldworks_hermitcrab_version,
            generate_hc_config_version=generate_hc_config_version,
            hc_engine_version_skew=hermitcrab_versions_differ(
                hc_tool_version, fieldworks_hermitcrab_version
            ),
        )
