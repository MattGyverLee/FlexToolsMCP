#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The bounded single-word measurement (parser-check CP3, US6; FR-051..FR-055;
data-model.md section 15; research.md R-05; spec.md D-4).

"This is taking forever -- is my grammar broken?" costs one word to answer,
not one night: run a single word to completion under a hard bound and report
what it actually cost in wall-clock time. If it blows the bound, THAT IS THE
FINDING. A terminated measurement is a terminal result carrying its
measurement (FR-054), never an error.

THREE THINGS THIS MODULE REFUSES TO PRETEND.

  * No in-parse enforcement. The engine offers no cancellation token,
    timeout or step budget, and the runner's cooperative cancellation lands
    at the next word boundary -- which for a one-word parse is after the
    parse being bounded. The bound is enforced at PROCESS level: the
    measurement's worker is killed through `subprocess_helpers.
    _kill_process_tree` (`ParseWorkerClient.terminate`) (FR-052, D-4).

  * No engine step or node count. None exists to report, and inventing one
    is the failure this campaign names most often. The cost is wall-clock,
    plus whether the fast-path window was missed and by how much (FR-053).

  * No write. The stored parser parameters are READ and reported as context
    for a slow parse; nothing here, or anywhere in CP3, assigns them
    (FR-055, FR-063).

WHY ITS OWN WORKER. The pool keys workers by `(project, role)`. A
measurement runs under `MEASUREMENT_ROLE`, never the shared worker a batch
lives in, because its bound is enforced by killing the process tree and a
shared worker would take the batch with it (FR-051, R-05). It is still a run
through THE runner -- one word at `Priority.TRY_A_WORD`, the highest word
priority -- so there is exactly one execution model (FR-014).

The measurement's worker is fresh, so `elapsed_seconds` covers loading the
grammar AND parsing the word, measured from submission. Worker start-up (the
interpreter, pythonnet, opening the project) happens before the clock starts
and is not charged to the grammar. `stage_at_end` says which of the two the
bound landed in: a measurement terminated in `loading_grammar` never reached
the word at all.
"""

from __future__ import annotations

import contextlib
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .priority import Priority
from .stages import RunStage
from .worker_client import MEASUREMENT_ROLE

__all__ = [
    "DEFAULT_BOUND_SECONDS",
    "MAX_BOUND_SECONDS",
    "MIN_BOUND_SECONDS",
    "BoundedMeasurement",
    "MeasurementFailed",
    "measure_word",
    "summarize_parser_parameters",
]

#: The bound a proposal offers when it has no better figure. Long enough for
#: a healthy grammar to load cold and parse one word; short enough that "it
#: did not finish" arrives while the question is still being asked.
DEFAULT_BOUND_SECONDS = 60.0
MIN_BOUND_SECONDS = 1.0
MAX_BOUND_SECONDS = 600.0

#: The two outcomes. Both are RESULTS (FR-054).
OUTCOME_COMPLETED = "completed"
OUTCOME_TERMINATED = "terminated_at_bound"

#: How much of an unparseable parameters document is echoed back.
_RAW_PARAMETERS_CAP = 2000


class MeasurementFailed(Exception):
    """The measurement's run FAILED -- not the same as blowing the bound.

    An engine refusal, a project that will not open, a worker that died on
    its own: these are failures of the measurement, and the handler reports
    them through the same refusal path a single word uses. Terminating at
    the bound is not among them; that returns a `BoundedMeasurement`.
    """

    def __init__(self, handle: Any) -> None:
        failure = getattr(handle, "failure", None)
        super().__init__(getattr(failure, "message", None) or "The measurement failed.")
        self.handle = handle


@dataclass
class BoundedMeasurement:
    """data-model.md section 15. Wall-clock only -- see the module docstring."""

    wordform: str
    bound_seconds: float
    elapsed_seconds: float
    exceeded_bound: bool
    #: Seconds past the fast-path (grace) window, or None when inside it.
    missed_fast_path_by: Optional[float]
    outcome: str
    fast_path_window_seconds: float
    run_id: str
    #: Where the run was when it ended: `completed`, or the stage the bound
    #: landed in (`loading_grammar` / `parsing`).
    stage_at_end: str
    #: The parse's own answer when it finished: `parsed`, `analysis_count`.
    #: None when terminated -- there is no answer to report.
    parse: Optional[dict[str, Any]] = None
    #: `summarize_parser_parameters` output, READ as context (FR-055).
    parser_parameters: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wordform": self.wordform,
            "bound_seconds": self.bound_seconds,
            "elapsed_seconds": self.elapsed_seconds,
            "exceeded_bound": self.exceeded_bound,
            "missed_fast_path_by": self.missed_fast_path_by,
            "outcome": self.outcome,
            "fast_path_window_seconds": self.fast_path_window_seconds,
            "run_id": self.run_id,
            "stage_at_end": self.stage_at_end,
            "parse": self.parse,
            "parser_parameters": self.parser_parameters,
            "measured": (
                "Wall-clock seconds from submission, in a worker of its own: "
                "loading the grammar and parsing this one word. The engine "
                "exposes no step or node count, so none is reported."
            ),
        }

    @property
    def finding(self) -> str:
        """The one sentence the measurement exists to produce."""
        if self.exceeded_bound:
            where = (
                "while still loading the grammar"
                if self.stage_at_end == RunStage.LOADING_GRAMMAR.value
                else "while parsing it"
            )
            return (
                f"This grammar did not finish one word ({self.wordform!r}) in "
                f"{self.bound_seconds:g} seconds; the measurement was stopped "
                f"{where}. That is the finding, not an error: a grammar that "
                f"cannot finish one short word will not finish a corpus."
            )
        if self.missed_fast_path_by is not None:
            return (
                f"One word ({self.wordform!r}) took {self.elapsed_seconds:.2f} "
                f"seconds including a cold grammar load -- inside the "
                f"{self.bound_seconds:g}-second bound, "
                f"{self.missed_fast_path_by:.2f} seconds past the "
                f"{self.fast_path_window_seconds:g}-second fast-path window."
            )
        return (
            f"One word ({self.wordform!r}) took {self.elapsed_seconds:.2f} "
            f"seconds including a cold grammar load, inside the "
            f"{self.fast_path_window_seconds:g}-second fast-path window."
        )


def summarize_parser_parameters(raw: Optional[str]) -> Optional[dict[str, Any]]:
    """The stored parser-parameters document, summarised without invention.

    Reports what the document says -- the active parser and each child of the
    `HC` element, by its own tag and text -- and nothing it does not. No key
    is interpreted, defaulted or renamed: a setting is context for a human
    reading a slow parse, and a gloss on it here would be a guess dressed as
    a fact. An unparseable document comes back raw (capped), labelled as such.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return {"stored": False}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return {
            "stored": True,
            "parseable": False,
            "raw": text[:_RAW_PARAMETERS_CAP],
            "raw_truncated": len(text) > _RAW_PARAMETERS_CAP,
        }
    active = root.findtext("ActiveParser")
    hc = root.find("HC")
    hc_settings: Optional[dict[str, str]] = None
    if hc is not None:
        hc_settings = {child.tag: (child.text or "").strip() for child in hc}
    return {
        "stored": True,
        "parseable": True,
        "active_parser": active.strip() if isinstance(active, str) else None,
        "hc": hc_settings,
    }


def _missed_by(elapsed: float, window: float) -> Optional[float]:
    return round(elapsed - window, 3) if elapsed > window else None


def _parse_answer(handle: Any) -> Optional[dict[str, Any]]:
    entry = handle.results[0] if getattr(handle, "results", None) else None
    if not entry:
        return None
    parse = entry.get("parse") or {}
    answer: dict[str, Any] = {}
    # Copied by NAME, never defaulted: a missing key stays missing.
    for key in ("parsed", "analysis_count", "parse_error"):
        if key in parse:
            answer[key] = parse[key]
    return answer


async def measure_word(
    runner: Any,
    *,
    project_name: str,
    wordform: str,
    bound_seconds: float = DEFAULT_BOUND_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> BoundedMeasurement:
    """Measure one word under a hard, process-level bound.

    Raises `MeasurementFailed` when the run failed for a reason of its own,
    and lets a `WorkerError` from starting the worker propagate (an engine
    refusal at start-up, a project that will not open) -- the handler turns
    both into the refusal a single word would get. Terminating at the bound
    returns normally.
    """
    bound = float(bound_seconds)
    if not MIN_BOUND_SECONDS <= bound <= MAX_BOUND_SECONDS:
        raise ValueError(
            f"bound_seconds must be between {MIN_BOUND_SECONDS:g} and "
            f"{MAX_BOUND_SECONDS:g}; got {bound:g}."
        )

    # Start the measurement's OWN worker first, so the clock charges the
    # grammar and the word, not the interpreter and the project open.
    worker = await runner.worker(project_name, role=MEASUREMENT_ROLE)

    parameters: Optional[dict[str, Any]] = None
    with contextlib.suppress(Exception):
        # Context, never a gate: a worker that cannot read them still
        # measures. Asked before the parse, while the worker is idle.
        parameters = await worker.parser_parameters(
            request_id=f"params:{uuid.uuid4().hex[:12]}",
            timeout=min(bound, 30.0),
        )

    started = clock()
    handle = await runner.start_run(
        project_name=project_name,
        wordforms=[wordform],
        level="plain",
        priority=Priority.TRY_A_WORD,
        grace_window=bound,
        worker_role=MEASUREMENT_ROLE,
    )

    try:
        if handle.is_terminal:
            elapsed = clock() - started
            if handle.stage is RunStage.FAILED:
                raise MeasurementFailed(handle)
            return BoundedMeasurement(
                wordform=wordform,
                bound_seconds=bound,
                elapsed_seconds=round(elapsed, 3),
                exceeded_bound=False,
                missed_fast_path_by=_missed_by(elapsed, runner.grace_window),
                outcome=OUTCOME_COMPLETED,
                fast_path_window_seconds=runner.grace_window,
                run_id=handle.run_id,
                stage_at_end=handle.stage.value,
                parse=_parse_answer(handle),
                parser_parameters=parameters,
            )

        # The bound. The stage is read BEFORE the kill: after it the run is
        # `cancelled`, and what matters is where the grammar had got to.
        stage_at_bound = handle.stage.value
        await runner.terminate_run(handle.run_id)
        elapsed = clock() - started
        return BoundedMeasurement(
            wordform=wordform,
            bound_seconds=bound,
            elapsed_seconds=round(elapsed, 3),
            exceeded_bound=True,
            missed_fast_path_by=_missed_by(elapsed, runner.grace_window),
            outcome=OUTCOME_TERMINATED,
            fast_path_window_seconds=runner.grace_window,
            run_id=handle.run_id,
            stage_at_end=stage_at_bound,
            parse=None,
            parser_parameters=parameters,
        )
    finally:
        # Never a second long-lived grammar holder: the measurement's worker
        # goes as soon as its one word is done (a no-op once terminated).
        await runner.release_worker(project_name, role=MEASUREMENT_ROLE)
