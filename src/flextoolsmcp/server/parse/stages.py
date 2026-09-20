#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The closed stage enum for a parse run, and its transition table
(parser-check CP2b, FR-027; data-model.md section 2).

A run reports exactly one of seven stages. The set is CLOSED and the names
are verbatim from the specification's Verbatim Constraints -- they cross the
tool boundary into callers' hands, so renaming one is a contract break, not
a refactor.

WHY loading_grammar IS ITS OWN STAGE. It would be simpler to report
"running" and be done. Two things argue against it, both observed rather
than theoretical:

  * Loading the grammar is the step that most often exhausts memory. A run
    that dies is diagnosable only if the stage it died in is recorded, which
    is why `RunFailure` guidance points at the diagnostic instruments
    instead of suggesting a retry (FR-034).
  * On a large project the load dominates the run before a single word is
    parsed. A caller shown only "running" for minutes concludes the tool is
    hung and kills it.

WHY filing IS HERE BUT UNREACHABLE. `filing` is the stage at which parse
results are recorded back into the project. CP2b does not record anything --
FR-002 says the parser area exposes no way to write, and this checkpoint
keeps that promise. The stage is nonetheless defined now, because the enum
is a published contract and adding a member later is a wider change than
declaring one early.

That makes `filing` the one member with no producer, so its absence is
asserted rather than assumed: `tests/test_parse_stages.py` fails if any CP2b
code path can reach it. Without that test, "defined but unreachable" is
indistinguishable from "we forgot to wire it up".
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "RunStage",
    "TERMINAL_STAGES",
    "ALLOWED_TRANSITIONS",
    "is_terminal",
    "can_transition",
    "InvalidStageTransition",
]


class RunStage(str, Enum):
    """The seven stages a run can report.

    `str` mixin so a stage serializes as its own name across the tool
    boundary without a caller needing to know it was an enum.
    """

    STARTING = "starting"
    LOADING_GRAMMAR = "loading_grammar"
    PARSING = "parsing"
    # Defined, and deliberately unreachable in CP2b. See module docstring.
    FILING = "filing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


#: Stages nothing leaves. A cancel against a run already here is reported as
#: `parse_job_cancelled` -- a refusal carrying the run's final state -- and
#: NOT as a stage change (FR-036). Merely *asking* about a run in one of
#: these stages is a successful query, not a refusal; that asymmetry is the
#: subject of its own test in tests/test_parse_status_handler.py.
TERMINAL_STAGES: frozenset[RunStage] = frozenset(
    {RunStage.COMPLETED, RunStage.FAILED, RunStage.CANCELLED}
)

#: The transition table from data-model.md section 2.
#:
#: Four properties worth stating because each is a decision:
#:   * `starting -> cancelled` is reachable. A run can be cancelled before
#:     the worker ever picks it up, and that must not require inventing a
#:     pass through `loading_grammar`.
#:   * `starting -> parsing` is reachable, and this is the WARM PATH. The
#:     data-model diagram drew only the cold one, so the first live run of
#:     scenario 1 found a second call re-entering `loading_grammar` against
#:     a grammar that was already held -- announcing a multi-second load
#:     that never happened. That is not a cosmetic slip: the stage exists
#:     precisely because it is the expensive step (FR-027), and the
#:     quickstart requires a second call not to re-enter it. A run that
#:     reuses a held grammar therefore goes straight to `parsing`, and the
#:     edge has to exist for it to say so.
#:   * Every non-terminal stage can reach `failed`. A death is possible
#:     anywhere; pretending otherwise would force a real failure to be
#:     reported as something it was not.
#:   * `filing` has NO inbound edge. It is unreachable by construction here,
#:     not merely unreached by the current code -- so the guarantee holds
#:     under future edits to the runner rather than depending on them.
ALLOWED_TRANSITIONS: dict[RunStage, frozenset[RunStage]] = {
    RunStage.STARTING: frozenset(
        {
            RunStage.LOADING_GRAMMAR,
            # The warm path -- see above. NOT a shortcut around the load:
            # the worker reports `loading_grammar` whenever one happens, so
            # taking this edge is the worker saying none did.
            RunStage.PARSING,
            RunStage.FAILED,
            RunStage.CANCELLED,
        }
    ),
    RunStage.LOADING_GRAMMAR: frozenset(
        {RunStage.PARSING, RunStage.FAILED, RunStage.CANCELLED}
    ),
    RunStage.PARSING: frozenset(
        {RunStage.COMPLETED, RunStage.FAILED, RunStage.CANCELLED}
    ),
    # No outbound edges: CP2b never reaches filing, and if some future
    # checkpoint does, it adds the inbound edge deliberately.
    RunStage.FILING: frozenset(),
    RunStage.COMPLETED: frozenset(),
    RunStage.FAILED: frozenset(),
    RunStage.CANCELLED: frozenset(),
}


class InvalidStageTransition(ValueError):
    """Raised when a run is asked to move between stages that do not connect.

    This is a programming error in the runner, not a user-facing refusal, so
    it is a plain exception rather than one of the tool-contract error
    codes. It exists so that a wrong transition fails where it is made
    instead of producing a run record whose stage history is not a path
    through the graph.
    """

    def __init__(self, source: RunStage, target: RunStage) -> None:
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS.get(source, frozenset()))
        if is_terminal(source):
            detail = (
                f"{source.value!r} is terminal -- nothing leaves it. A cancel "
                f"against a run already in a terminal stage is reported as "
                f"parse_job_cancelled, not as a stage change (FR-036)."
            )
        elif target is RunStage.FILING:
            detail = (
                "'filing' is defined but unreachable in CP2b: this checkpoint "
                "records nothing back into the project (FR-002). Reaching it "
                "means a write path was introduced."
            )
        else:
            detail = f"Allowed from {source.value!r}: {allowed or '(none)'}."
        super().__init__(
            f"Cannot move a run from {source.value!r} to {target.value!r}. {detail}"
        )
        self.source = source
        self.target = target


def is_terminal(stage: RunStage) -> bool:
    """Whether a run in this stage is finished, however it finished."""
    return stage in TERMINAL_STAGES


def can_transition(source: RunStage, target: RunStage) -> bool:
    """Whether `source -> target` is an edge in the transition graph."""
    return target in ALLOWED_TRANSITIONS.get(source, frozenset())
