#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Driving FieldWorks' own `ParseFiler` headlessly (parser-check CP4, FR-018,
FR-019; research R-03).

WHY THE REAL FILER. Filing must give each analysis the parser's honest
provenance -- created or re-approved under the HermitCrab agent, exactly as
FLEx's Parse Words in Text does -- so the MCP does not write analyses itself:
it hands each parse result to `ParseFiler`, the class that menu uses.

WHY A REAL, PAUSED IDLE QUEUE, PUMPED BY HAND. `ParseFiler.ProcessParse` does
not file anything; it enqueues the work and asks its `IdleQueue` to run the
private `UpdateWordforms` later, when WinForms reports the application idle
(`ParseFiler.cs:128-133`). A headless worker has no message loop, so nothing
would ever run. Passing a null queue only appears to work because a
`Debug.Assert` is compiled out of release builds. So the worker builds a REAL
`IdleQueue`, sets `IsPaused = true` (which unhooks it from `Application.Idle`),
and runs the queued task itself -- exactly how FieldWorks' own tests drive it
(`ParserCoreTests/ParseFilerProcessingTests.cs:97-102, 143-144`).

WHY ONE FILER PER WORD. `UpdateWordforms` returns false when a unit of work is
already open (`CanStartUow`, `:165-166`), and leaves the word's work in the
filer's private queue. On the next `ProcessParse` that stale work would be
filed silently -- later, out of order, and outside its own liveness check. So
the filer is built afresh for every word and dropped after its pump: a decline
is a property of THAT word alone, reported `filer_declined` (FR-019). FLEx
would retry on its next idle cycle; this path does not, and says so
(`wording.DECLINED_DIVERGENCE`).

EVERY BOUND MEMBER IS PROBED, NOT ASSUMED (R-03, constitution Principle II).
Two probes, at two points:

  * `probe_filing_surface()` -- in the SERVER, at preview time (contracts row
    6): the write spine's surface of `ParserCore.dll`, through the same
    `parser_probe.probe_parser_core(WRITE_REQUIRED_MEMBERS)` `flextools_health`
    runs. A missing surface refuses before any preview is built.
  * `probe_bound_members(namespace)` -- in the FILING WORKER, before it opens
    the project for writing: every member this module binds, by name and
    arity. A miss fails the run as `parser_core_missing` /
    `incompatible_surface` with nothing filed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "BOUND_MEMBERS",
    "SurfaceProbe",
    "probe_filing_surface",
    "probe_bound_members",
    "PumpOutcome",
    "file_one",
    "ClrFilerSurface",
]


@dataclass
class SurfaceProbe:
    """Whether the write spine's surface is present, shaped for a refusal."""

    ok: bool
    signal: Optional[str] = None
    expected_path: str = "ParserCore.dll"
    detected_version: Optional[str] = None
    missing_members: List[str] = field(default_factory=list)
    load_error: Optional[str] = None

    def refusal_detail(self) -> Dict[str, Any]:
        """`parser_core_missing`'s detail fields, in the model's order."""
        return {
            "signal": self.signal or "incompatible_surface",
            "expected_path": self.expected_path,
            "detected_version": self.detected_version,
            "missing_members": list(self.missing_members),
            "lcmodel_install_path": None,
            "install_hint": (
                "Filing needs FieldWorks' own parse filer (ParserCore.dll, and "
                "FwUtils.dll for its idle queue) from the same FieldWorks install "
                "the project is opened with. Run flextools_health to see which "
                "parser components this machine has."
            ),
            "load_error": self.load_error,
        }


def probe_filing_surface() -> SurfaceProbe:
    """The preview's surface check (contracts row 6), in the server process.

    Reuses `parser_probe.probe_parser_core(WRITE_REQUIRED_MEMBERS)` -- the
    read spine's `HCParser` members plus `ParseFiler.ProcessParse` -- rather
    than a second reflection over the same DLL. Never raises.
    """
    try:
        from ..parser_probe import WRITE_REQUIRED_MEMBERS, probe_parser_core

        result = probe_parser_core(WRITE_REQUIRED_MEMBERS)
    except Exception as exc:  # noqa: BLE001 -- a probe that dies tells nobody anything
        return SurfaceProbe(ok=False, signal="load_failed", load_error=str(exc))
    return SurfaceProbe(
        ok=bool(result.ok),
        signal=result.signal,
        expected_path=result.expected_path or "ParserCore.dll",
        detected_version=result.detected_version,
        missing_members=list(result.missing_members or []),
        load_error=result.load_error,
    )


#: Every member `file_one` and the classifier bind, as `Type.Member(arity)`.
#: Checked in the filing worker before the writable open (R-03).
BOUND_MEMBERS = (
    "ParseFiler..ctor(5)",
    "ParseFiler.ProcessParse(4)",
    "IdleQueue..ctor(0)",
    "IdleQueue.IsPaused",
    "IdleQueue.Remove(1)",
    "IdleQueue.GetEnumerator(0)",
    "IdleQueueTask.Delegate",
    "IdleQueueTask.Parameter",
    "ParseAnalysis.MatchesIWfiAnalysis(1)",
    "ParseResult.IsValid",
)


def probe_bound_members(namespace: Dict[str, Any]) -> List[str]:
    """The members of `BOUND_MEMBERS` missing from the loaded CLR types.

    `namespace` maps a simple type name to its CLR `Type` (or a fake with the
    same reflection surface). Arity is compared by parameter COUNT, never by
    resolving parameter types: resolving `ParseFiler`'s constructor would
    pull in XCore's `PropertyTable` for no gain. Returns [] when every member
    is present.
    """
    missing: List[str] = []
    for spec in BOUND_MEMBERS:
        type_name, _, member = spec.partition(".")
        clr_type = namespace.get(type_name)
        if clr_type is None:
            missing.append(spec)
            continue
        try:
            if not _has_member(clr_type, member):
                missing.append(spec)
        except Exception:  # noqa: BLE001 -- unreadable counts as missing
            missing.append(spec)
    return missing


def _has_member(clr_type: Any, member: str) -> bool:
    name, _, arity_text = member.partition("(")
    arity = int(arity_text.rstrip(")")) if arity_text else None
    if name == ".ctor":
        return any(len(list(c.GetParameters())) == arity for c in clr_type.GetConstructors())
    if arity is None:
        return clr_type.GetProperty(name) is not None or clr_type.GetField(name) is not None
    return any(
        m.Name == name and len(list(m.GetParameters())) == arity for m in clr_type.GetMethods()
    )


# ---------------------------------------------------------------------------
# The per-word pump (FR-018, FR-019; R-03)
# ---------------------------------------------------------------------------


@dataclass
class PumpOutcome:
    """What happened to one word's filing: `filed` or `filer_declined`."""

    outcome: str
    tasks_run: int = 0


def file_one(
    *,
    surface: Any,
    cache: Any,
    agent: Any,
    wordform: Any,
    parse_result: Any,
) -> PumpOutcome:
    """File ONE word's parse result through a fresh filer and a paused queue.

    `surface` supplies the CLR constructors: `IdleQueue()`, `ParseFiler(...)`,
    `ParserPriority`, and `task_report_handler()` -- a non-null
    `Action[TaskReport]`, because `TaskReport`'s constructor calls it straight
    away (`TaskReport.cs:37-42`). In the worker it is `ClrFilerSurface`; in the
    offline tests, a fake that records every call.

      1. a NEW `IdleQueue`, `IsPaused = True` -- never a null (FR-018);
      2. a NEW `ParseFiler(cache, None, handler, queue, agent)` -- a null
         property table makes `CheckParserUpdatesAnalyses` default to true
         (`ParseFiler.cs:193`);
      3. `ProcessParse(wordform, Low, result, False)` -- which only enqueues;
      4. the pump: snapshot the queue, and for each task remove it, then call
         `task.Delegate(task.Parameter)`. `False` means `CanStartUow` was false
         and the word is `filer_declined` (FR-019). The filer is dropped here,
         so its unrun work cannot leak into the next word.

    Must be called with NO unit of work open: the filer opens its own
    (`NonUndoableUnitOfWorkHelper.Do`). That is why the filing worker opens
    the project in flexicon's per-operation mode, never inside a session-long
    task.
    """
    queue = surface.IdleQueue()
    queue.IsPaused = True
    handler = surface.task_report_handler()
    parse_filer = surface.ParseFiler(cache, None, handler, queue, agent)
    parse_filer.ProcessParse(wordform, surface.ParserPriority.Low, parse_result, False)

    tasks = list(queue)
    if not tasks:
        # ProcessParse always enqueues; an empty queue means the surface did
        # not behave as probed. Nothing was filed, and nothing is claimed.
        return PumpOutcome(outcome="filer_declined", tasks_run=0)
    ok = True
    for task in tasks:
        queue.Remove(task)
        ok = bool(task.Delegate(task.Parameter)) and ok
    return PumpOutcome(outcome="filed" if ok else "filer_declined", tasks_run=len(tasks))


class ClrFilerSurface:
    """The real FieldWorks surface `file_one` drives. FILING WORKER ONLY.

    Loads `ParserCore` (the filer, the parse result, `ParserPriority`,
    `TaskReport`) and `FwUtils` (the idle queue) into the process that has the
    project open for writing. Never constructed in the server or the read
    worker: loading `ParseFiler` resolves XCore's `PropertyTable`, which the
    read worker's standing no-XCore test forbids there.
    """

    def __init__(self) -> None:
        import clr  # type: ignore[import-not-found]

        clr.AddReference("ParserCore")
        clr.AddReference("FwUtils")
        from SIL.FieldWorks.Common.FwUtils import IdleQueue, IdleQueueTask  # type: ignore
        from SIL.FieldWorks.WordWorks.Parser import (  # type: ignore
            ParseAnalysis,
            ParseFiler,
            ParseResult,
            ParserPriority,
            TaskReport,
        )
        from System import Action  # type: ignore

        self._IdleQueue = IdleQueue
        self._ParseFiler = ParseFiler
        self._Action = Action
        self._TaskReport = TaskReport
        self.ParserPriority = ParserPriority
        self._types = {
            "ParseFiler": clr.GetClrType(ParseFiler),
            "IdleQueue": clr.GetClrType(IdleQueue),
            "IdleQueueTask": clr.GetClrType(IdleQueueTask),
            "ParseAnalysis": clr.GetClrType(ParseAnalysis),
            "ParseResult": clr.GetClrType(ParseResult),
        }

    def namespace(self) -> Dict[str, Any]:
        """The CLR `Type`s `probe_bound_members` checks."""
        return dict(self._types)

    def IdleQueue(self) -> Any:  # noqa: N802 -- mirrors the CLR constructor
        return self._IdleQueue()

    def ParseFiler(self, *args: Any) -> Any:  # noqa: N802
        return self._ParseFiler(*args)

    def task_report_handler(self) -> Any:
        """A no-op `Action[TaskReport]`: progress text has nowhere to go."""
        return self._Action[self._TaskReport](lambda _report: None)
