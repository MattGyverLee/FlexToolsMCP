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
MCP-side placement: T010 adds sandbox component discovery (since the CP5
re-plan, FieldWorks' bundled HermitCrab DLL and ``GenerateHCConfig.exe``),
T011 adds the ``ParserDetector`` aggregate, and T024/T025 add the engine
gate and the agent probe. Only ``ProbeResult`` and ``probe_parser_core()``
(plus their private helpers) land here now.
"""

from __future__ import annotations

import os
import re
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
# Sandbox engine discovery: FieldWorks' bundled HermitCrab and
# `GenerateHCConfig.exe` (T010; CP5 re-plan T104, D7)
#
# `sandbox_probe` (data-model.md's `ParserDetector` return shape) is
# `{engine: ProbeResult, generate_config: ProbeResult}` -- two independent
# probes, because the two files can go missing independently and a caller
# must know which one is gone (contracts/flextools_health-parser-block.md).
#
# CP5 re-plan (HANDOFF.md, D7): the sandbox no longer shells out to an `hc`
# console tool. Its parse worker loads the HermitCrab engine FieldWorks
# ships, so discovery is a presence-plus-`FileVersion` read of that DLL in
# the resolved FieldWorks directory -- it never spawns a process and never
# loads the assembly. An engine that is present but will not load surfaces
# on the sandbox's first `parse` instead (`parser_job_failed`,
# `engine_unavailable`), never at health time.
#
# Closed component-name enum, shared with `parser_tool_missing`'s
# `component` field (contracts/tools.md section 4) and
# `sandbox.components[].component` in the health block.
# ---------------------------------------------------------------------------

COMPONENT_FIELDWORKS_HERMITCRAB = "fieldworks_hermitcrab"
COMPONENT_GENERATE_HC_CONFIG = "GenerateHCConfig.exe"

SANDBOX_COMPONENTS: FrozenSet[str] = frozenset(
    {COMPONENT_FIELDWORKS_HERMITCRAB, COMPONENT_GENERATE_HC_CONFIG}
)

#: FieldWorks' bundled HermitCrab library: the engine the sandbox worker
#: loads, and the one Try A Word uses. Its ``FileVersion`` is the engine
#: version reported in health and in every sandbox run record.
FIELDWORKS_HERMITCRAB_DLL = "SIL.Machine.Morphology.HermitCrab.dll"

#: The repair hint for either missing component (contracts/tools.md section
#: 4, verbatim). Both come from the same FieldWorks installation and are
#: repaired the same way, so the `fieldworks_hermitcrab` hint is literally
#: GenerateHCConfig's own sentence.
FIELDWORKS_REPAIR_HINT = (
    "GenerateHCConfig.exe ships with FieldWorks 9; repair or reinstall FieldWorks."
)

#: Discovery signal for a component that is not where FieldWorks puts it.
#: Deliberately **not** merged into `CLOSED_SIGNALS` above -- that
#: vocabulary is `parser_core_missing`'s (ParserCore member probe);
#: `parser_tool_missing` has no `signal` field at all.
SANDBOX_SIGNAL_NOT_FOUND = "not_found"
SANDBOX_SIGNAL_NOT_HERMITCRAB = "not_hermitcrab"
"""A path exists where the DLL should be, but it is not a file (a corrupt
or mismatched FieldWorks install, data-model.md section 7). Counts as not
found."""


# ---------------------------------------------------------------------------
# Versions (CP5 T031/T104, FR-005) -- reported, never compared to a floor
# ---------------------------------------------------------------------------

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


@dataclass
class EngineDiscovery(ProbeResult):
    """``discover_fieldworks_hermitcrab``'s result: a ``ProbeResult`` (so
    every existing reader keeps working) plus the engine's facts.

    - ``ok`` / ``found`` -- the DLL is a file in the FieldWorks directory.
    - ``signal`` -- ``None``, ``not_found`` or ``not_hermitcrab``.
    - ``expected_path`` -- the DLL's path in the resolved FieldWorks
      directory, or the bare DLL name when no FieldWorks install resolves.
    - ``file_version`` (also ``detected_version``) -- its ``FileVersion``;
      reported, never compared.
    - ``reason`` (also ``load_error``) -- human text for a not-found result.
    """

    found: bool = False
    file_version: Optional[str] = None
    reason: Optional[str] = None


def discover_fieldworks_hermitcrab(
    *, search_paths: Optional[List[Path]] = None
) -> EngineDiscovery:
    """Locate FieldWorks' bundled HermitCrab engine (CP5 D7, FR-001, FR-004, FR-005).

    A plain filesystem check in the directory ``get_resolved_fieldworks_dir()``
    resolves -- the same install that supplies ``SIL.LCModel.dll`` -- plus a
    ``FileVersion`` read. No process is spawned and the assembly is never
    loaded, so this is safe on the health path; whether the engine actually
    loads is the sandbox worker's first-``parse`` question. Never raises.
    """
    fieldworks_dir = get_resolved_fieldworks_dir(search_paths=search_paths)
    if not fieldworks_dir:
        reason = (
            f"No FieldWorks installation was found, so {FIELDWORKS_HERMITCRAB_DLL} "
            "could not be located"
        )
        return EngineDiscovery(
            ok=False,
            signal=SANDBOX_SIGNAL_NOT_FOUND,
            expected_path=FIELDWORKS_HERMITCRAB_DLL,
            load_error=reason,
            reason=reason,
        )
    dll = Path(fieldworks_dir) / FIELDWORKS_HERMITCRAB_DLL
    if dll.is_file():
        version = _safe_file_version(dll)
        return EngineDiscovery(
            ok=True,
            expected_path=str(dll),
            detected_version=version,
            found=True,
            file_version=version,
        )
    if dll.exists():
        signal = SANDBOX_SIGNAL_NOT_HERMITCRAB
        reason = f"{dll} exists but is not a file; the FieldWorks install looks damaged"
    else:
        signal = SANDBOX_SIGNAL_NOT_FOUND
        reason = f"{FIELDWORKS_HERMITCRAB_DLL} is missing from {fieldworks_dir}"
    return EngineDiscovery(
        ok=False,
        signal=signal,
        expected_path=str(dll),
        load_error=reason,
        reason=reason,
    )


def discover_generate_hc_config(*, search_paths: Optional[List[Path]] = None) -> ProbeResult:
    """Locate ``GenerateHCConfig.exe`` (SPEC 13 H1 / tasks.md T010).

    Like the bundled HermitCrab engine, ``GenerateHCConfig.exe`` ships
    *with* FieldWorks itself, so it is looked up the same way
    ``probe_parser_core`` looks up ``ParserCore.dll``: as a
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
    """``sandbox_probe`` -- the two sandbox component probes, bundled.

    Two independent ``ProbeResult``s rather than one combined boolean: the
    bundled HermitCrab engine (``engine``, an ``EngineDiscovery``) and
    ``GenerateHCConfig.exe`` can go missing independently, and a caller
    needs to know which one is gone (contracts/flextools_health-parser-block.md
    ``sandbox.components``).
    """

    engine: ProbeResult
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
    #: CP5 FR-005: FieldWorks' bundled HermitCrab (``FIELDWORKS_HERMITCRAB_DLL``),
    #: the one engine the sandbox runs -- so there is no second version to
    #: skew against (D7).
    fieldworks_hermitcrab_version: Optional[str] = None
    #: CP5 FR-005: ``GenerateHCConfig.exe``'s own ``FileVersion``.
    generate_hc_config_version: Optional[str] = None


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
    ``discover_fieldworks_hermitcrab`` and ``discover_generate_hc_config`` already catch
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
    ``probe_parser_core`` and the sandbox's ``discover_fieldworks_hermitcrab``
    / ``discover_generate_hc_config``. Detection is eager: every field below
    is a plain attribute populated by ``__init__``, not a property computed
    lazily on first access -- constructing a ``ParserDetector`` with no
    required positional args is itself the detection call.

    Attributes (data-model.md's ``ParserDetector`` return shape, field names
    pinned verbatim -- do not rename):

    - ``read_probe``: ``ProbeResult`` over ``HCPARSER_MEMBERS``.
    - ``write_probe``: ``ProbeResult`` over ``WRITE_REQUIRED_MEMBERS``
      (``HCPARSER_MEMBERS`` plus ``ParseFiler.ProcessParse``). Decided by
      the member probe **alone** -- never influenced by ``agent_probe``.
    - ``sandbox_probe``: ``SandboxProbe(engine, generate_config)``.
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
      lcmodel_install_path, fieldworks_hermitcrab_version,
      generate_hc_config_version)`` -- reported, never compared.

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

        engine_probe: ProbeResult = _safe_probe(
            lambda: discover_fieldworks_hermitcrab(search_paths=search_paths),
            expected_path=FIELDWORKS_HERMITCRAB_DLL,
        )
        generate_config_probe: ProbeResult = _safe_probe(
            lambda: discover_generate_hc_config(search_paths=search_paths)
        )
        self.sandbox_probe: SandboxProbe = SandboxProbe(
            engine=engine_probe, generate_config=generate_config_probe
        )

        # CP1: no project is ever open in this code path (D2), so the
        # agent probe is unconditionally skipped and active_engine is
        # unconditionally null (D8) -- neither may read as a pass.
        self.agent_probe: AgentProbeResult = AgentProbeResult(state=AGENT_STATE_SKIPPED)
        self.active_engine: Optional[str] = None

        fieldworks_dir = get_resolved_fieldworks_dir(search_paths=search_paths)
        # CP5 FR-005: versions are reported and never compared -- to a floor
        # or to each other (D7: one engine, so no skew to compute).
        fieldworks_hermitcrab_version = engine_probe.detected_version
        generate_hc_config_version = (
            _safe_file_version(generate_config_probe.expected_path)
            if generate_config_probe.ok and generate_config_probe.expected_path
            else None
        )
        self.versions: ParserVersions = ParserVersions(
            parser_core_version=self.read_probe.detected_version
            or self.write_probe.detected_version,
            lcmodel_install_path=str(fieldworks_dir) if fieldworks_dir else None,
            fieldworks_hermitcrab_version=fieldworks_hermitcrab_version,
            generate_hc_config_version=generate_hc_config_version,
        )
