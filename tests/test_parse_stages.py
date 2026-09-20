#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The parse run stage enum and its transition table (parser-check CP2b,
FR-027).

Three things are pinned here, and the third is the one that matters most.

(1) THE SEVEN NAMES, VERBATIM. `starting | loading_grammar | parsing |
filing | completed | failed | cancelled`. These cross the tool boundary into
callers' hands, so a rename is a contract break rather than a refactor. The
names are asserted as a set AND individually, so a failure says which one
moved rather than only that the set differs.

(2) THE TRANSITION GRAPH, including that terminal stages absorb. Nothing
leaves `completed` / `failed` / `cancelled`; a cancel against a run already
there is reported as `parse_job_cancelled`, not as a stage change (FR-036).

(3) THAT NO CP2b CODE PATH CAN PRODUCE `filing`. This is the assertion the
whole file exists for. `filing` is the stage at which results are recorded
back into the project, and CP2b records nothing -- FR-002 says the parser
area exposes no way to write. The stage is defined anyway, because the enum
is a published contract and adding a member later is a wider change than
declaring one early.

That leaves `filing` as the single member with no producer, which is exactly
the state that decays silently. "Defined but unreachable" and "we forgot to
wire it up" look identical in a passing test run and differ only in intent.
So unreachability is asserted two ways: structurally, that no edge in the
transition table leads to it, and by AST sweep, that no module under
`server/parse/` names it outside the enum declaration itself. The sweep is
what catches a future runner that sets a stage by string rather than through
the table.

Run with:
    python -m pytest tests/test_parse_stages.py -q
"""

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.stages import (  # noqa: E402
    ALLOWED_TRANSITIONS,
    InvalidStageTransition,
    RunStage,
    TERMINAL_STAGES,
    can_transition,
    is_terminal,
)

PARSE_PKG = REPO_ROOT / "src" / "flextoolsmcp" / "server" / "parse"

#: Bound once so the nested parametrize below reads a plain list.
_SORTED_TERMINAL_STAGES = sorted(TERMINAL_STAGES, key=lambda stage: stage.value)

#: The names, verbatim from the specification's Verbatim Constraints.
EXPECTED_STAGE_VALUES = {
    "starting",
    "loading_grammar",
    "parsing",
    "filing",
    "completed",
    "failed",
    "cancelled",
}


# ---------------------------------------------------------------------------
# (1) The seven names
# ---------------------------------------------------------------------------


def test_exactly_seven_stages():
    assert len(RunStage) == 7, (
        f"RunStage has {len(RunStage)} members, expected 7. The set is closed "
        f"and the names cross the tool boundary -- adding or removing one is "
        f"a contract change."
    )


def test_stage_values_are_verbatim():
    actual = {stage.value for stage in RunStage}
    assert actual == EXPECTED_STAGE_VALUES, (
        f"Stage names diverged from the Verbatim Constraints.\n"
        f"  unexpected: {sorted(actual - EXPECTED_STAGE_VALUES)}\n"
        f"  missing:    {sorted(EXPECTED_STAGE_VALUES - actual)}"
    )


@pytest.mark.parametrize("expected", sorted(EXPECTED_STAGE_VALUES))
def test_each_expected_stage_exists(expected):
    """Named individually so a failure says WHICH stage moved."""
    assert any(stage.value == expected for stage in RunStage), (
        f"Stage {expected!r} is gone from RunStage. Callers receive this "
        f"string; renaming it breaks them."
    )


def test_stage_serializes_as_its_own_name():
    """The str mixin is load-bearing across the tool boundary."""
    assert RunStage.LOADING_GRAMMAR == "loading_grammar"
    assert f"{RunStage.PARSING}" in ("parsing", "RunStage.PARSING")
    assert RunStage("cancelled") is RunStage.CANCELLED


# ---------------------------------------------------------------------------
# (2) The transition graph
# ---------------------------------------------------------------------------


def test_every_stage_has_a_transition_entry():
    """No member may be missing from the table -- that would read as 'no edges'."""
    missing = [s.value for s in RunStage if s not in ALLOWED_TRANSITIONS]
    assert not missing, (
        f"Stages absent from ALLOWED_TRANSITIONS: {missing}. An absent entry "
        f"is indistinguishable from a deliberate dead end."
    )


@pytest.mark.parametrize(
    "source,target",
    [
        (RunStage.STARTING, RunStage.LOADING_GRAMMAR),
        (RunStage.LOADING_GRAMMAR, RunStage.PARSING),
        (RunStage.PARSING, RunStage.COMPLETED),
    ],
)
def test_happy_path_edges(source, target):
    assert can_transition(source, target)


@pytest.mark.parametrize(
    "source",
    [RunStage.STARTING, RunStage.LOADING_GRAMMAR, RunStage.PARSING],
)
def test_every_non_terminal_stage_can_fail(source):
    """A death is possible anywhere; the stage it died in is the diagnosis."""
    assert can_transition(source, RunStage.FAILED), (
        f"{source.value!r} cannot reach 'failed'. A real failure there would "
        f"have to be reported as something it was not, and memory exhaustion "
        f"during loading_grammar is exactly the case FR-034's guidance is for."
    )


@pytest.mark.parametrize(
    "source",
    [RunStage.STARTING, RunStage.LOADING_GRAMMAR, RunStage.PARSING],
)
def test_every_non_terminal_stage_can_be_cancelled(source):
    """Including `starting` -- a run can be cancelled before it is picked up."""
    assert can_transition(source, RunStage.CANCELLED)


def test_terminal_stages_are_exactly_the_three():
    assert TERMINAL_STAGES == frozenset(
        {RunStage.COMPLETED, RunStage.FAILED, RunStage.CANCELLED}
    )
    for stage in TERMINAL_STAGES:
        assert is_terminal(stage)
    for stage in (RunStage.STARTING, RunStage.LOADING_GRAMMAR, RunStage.PARSING):
        assert not is_terminal(stage)


@pytest.mark.parametrize("terminal", _SORTED_TERMINAL_STAGES)
@pytest.mark.parametrize("target", list(RunStage))
def test_terminal_stages_absorb(terminal, target):
    """Nothing leaves a terminal stage, to anywhere, ever."""
    assert not can_transition(terminal, target), (
        f"{terminal.value!r} -> {target.value!r} is reachable, but terminal "
        f"stages absorb. A cancel against a finished run is reported as "
        f"parse_job_cancelled carrying its final state, NOT as a stage "
        f"change (FR-036)."
    )


def test_invalid_transition_error_explains_terminality():
    err = InvalidStageTransition(RunStage.COMPLETED, RunStage.PARSING)
    assert "terminal" in str(err)
    assert "parse_job_cancelled" in str(err)


def test_invalid_transition_error_explains_filing():
    err = InvalidStageTransition(RunStage.PARSING, RunStage.FILING)
    assert "unreachable in CP2b" in str(err)


# ---------------------------------------------------------------------------
# (3) `filing` is unreachable -- the assertion this file exists for
# ---------------------------------------------------------------------------


def test_filing_exists_in_the_enum():
    """Unreachable is not the same as absent. The contract commitment stands."""
    assert RunStage.FILING.value == "filing"


def test_no_transition_leads_to_filing():
    """Structural half: `filing` has no inbound edge anywhere in the table."""
    inbound = [
        source.value
        for source, targets in ALLOWED_TRANSITIONS.items()
        if RunStage.FILING in targets
    ]
    assert not inbound, (
        f"Stages that can reach 'filing': {inbound}. CP2b records nothing "
        f"back into the project (FR-002), so no run may enter the filing "
        f"stage. An inbound edge means a write path was introduced."
    )


def test_filing_is_not_terminal_and_has_no_outbound_edges():
    """It is isolated in the graph -- neither entered nor left."""
    assert RunStage.FILING not in TERMINAL_STAGES
    assert ALLOWED_TRANSITIONS[RunStage.FILING] == frozenset()


def _parse_package_modules():
    """Every module under server/parse/, except the enum's own home."""
    return [p for p in PARSE_PKG.rglob("*.py") if p.name != "stages.py"]


def test_no_parse_module_names_the_filing_stage():
    """
    AST sweep: the half that catches a stage set by string.

    The structural assertion above only constrains code that goes THROUGH
    the transition table. A runner that assigned `stage = "filing"`
    directly, or referenced `RunStage.FILING`, would sail past it. This
    sweep is what makes "no CP2b code path can produce filing" a statement
    about the package rather than about one dictionary.

    It reads the AST rather than the raw text so that the word appearing in
    a comment or docstring -- which is legitimate and in fact expected --
    does not trip it.
    """
    offenders: list[str] = []
    for module in _parse_package_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "FILING":
                offenders.append(
                    f"{module.relative_to(REPO_ROOT)}:{node.lineno} "
                    f"references RunStage.FILING"
                )
            elif isinstance(node, ast.Constant) and node.value == "filing":
                offenders.append(
                    f"{module.relative_to(REPO_ROOT)}:{node.lineno} "
                    f"uses the literal 'filing'"
                )
    assert not offenders, (
        "CP2b code names the 'filing' stage:\n  "
        + "\n  ".join(offenders)
        + "\n\nCP2b records nothing back into the project (FR-002). 'filing' "
        "is a contract commitment for a later checkpoint and must have no "
        "producer here."
    )


def test_the_filing_sweep_is_not_vacuous():
    """
    Guard the guard.

    `test_no_parse_module_names_the_filing_stage` passes trivially if it
    sweeps an empty file list -- which is exactly what happens early in the
    checkpoint, or if the package is ever moved. An empty sweep reporting
    success is the failure mode that would let `filing` acquire a producer
    unnoticed.
    """
    modules = _parse_package_modules()
    assert modules, (
        f"The filing sweep found no modules under {PARSE_PKG} to inspect, so "
        f"it passes vacuously. Either the package moved or nothing is built "
        f"yet -- in both cases the guarantee is unproven, not satisfied."
    )
