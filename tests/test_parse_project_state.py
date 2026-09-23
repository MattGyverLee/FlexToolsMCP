#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T011 -- the one read-only project-state probe (parser-check CP3, FR-004).

Two things are asserted here, and they are the two FR-004 actually promises:

  1. THE PROBE WRITES NOTHING. Not "was not observed to write" -- the double
     below raises on every mutating name it carries, so a write is a test
     failure rather than something a reviewer has to notice. This is the
     module-local half of the standing guarantee; the checkpoint-wide half is
     `tests/test_parse_no_project_writes.py` (FR-063).

  2. ALL THREE CONSUMERS RESOLVE THROUGH THE ONE IMPLEMENTATION. The three
     consumer functions take a `ProjectParseState`, not a project, so a
     second traversal cannot be written by accident; the tests below pin that
     signature deliberately rather than incidentally. A CP4 that grows its
     own probe is a review finding (FR-004), and the last test here is what
     makes that finding mechanical instead of a matter of memory.

Everything runs offline. The probe reads through flexicon operation objects,
which are doubled; no FieldWorks install is involved.
"""

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.parse.project_state import (  # noqa: E402
    DEFAULT_PROBE_LIMIT,
    ProjectParseState,
    deletion_projection_precondition,
    never_parsed_warning,
    oracle_is_available,
    probe_project_state,
)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

# Every mutating name on flexicon's WfiAnalysisOperations / WordformOperations.
# Named explicitly rather than pattern-matched: a probe that called
# `ApproveAnalysis` would be caught by a "starts with Set/Add" heuristic only
# by luck.
WRITE_METHODS = (
    "AddGloss", "ApproveAnalysis", "RejectAnalysis", "SetApprovalStatus",
    "SetCategory", "Create", "Delete", "Duplicate", "MoveAfter", "MoveBefore",
    "MoveDown", "MoveToIndex", "MoveUp", "Sort", "Swap",
    "ApplySyncableProperties", "ApproveSpelling", "SetForm",
    "SetSpellingStatus",
)


class ProjectWriteAttempted(AssertionError):
    """Raised by the double the moment the probe touches a write path."""


class FakeAnalysis:
    def __init__(self, human=None, machine=None, human_raises=False,
                 machine_raises=False):
        self.human = human
        self.machine = machine
        self.human_raises = human_raises
        self.machine_raises = machine_raises


class FakeWfiAnalysisOps:
    """Reads answer from the fixture; every write raises."""

    def __init__(self, analyses):
        self._analyses = list(analyses)
        self.get_all_calls = 0
        for name in WRITE_METHODS:
            setattr(self, name, self._refuse(name))

    @staticmethod
    def _refuse(name):
        def _raise(*_a, **_k):
            raise ProjectWriteAttempted(
                "the read-only probe called the write method " + name
            )
        return _raise

    def GetAll(self):
        self.get_all_calls += 1
        return list(self._analyses)

    def GetHumanEvaluation(self, analysis):
        if analysis.human_raises:
            raise RuntimeError("evaluation record unreadable")
        return analysis.human

    def IsHumanApproved(self, analysis):
        if analysis.human_raises:
            raise RuntimeError("evaluation record unreadable")
        return analysis.human is not None

    def GetAgentEvaluation(self, analysis):
        if analysis.machine_raises:
            raise RuntimeError("evaluation record unreadable")
        return analysis.machine

    def IsComputerApproved(self, analysis):
        if analysis.machine_raises:
            raise RuntimeError("evaluation record unreadable")
        return analysis.machine is not None


class FakeProject:
    def __init__(self, analyses):
        self.WfiAnalysis = FakeWfiAnalysisOps(analyses)


def human(n=1):
    return FakeAnalysis(human="human-eval-" + str(n))


def machine(n=1):
    return FakeAnalysis(machine="agent-eval-" + str(n))


def no_opinion():
    return FakeAnalysis()


def unreadable():
    return FakeAnalysis(human_raises=True, machine_raises=True)


# ---------------------------------------------------------------------------
# 1. The probe writes nothing
# ---------------------------------------------------------------------------

class TestProbePerformsNoProjectWrite:

    def test_a_mixed_project_probes_without_any_write(self):
        project = FakeProject([human(1), machine(1), machine(2), no_opinion()])
        state = probe_project_state(project)
        assert state.analyses_total == 4

    def test_the_double_would_actually_catch_a_write(self):
        # Guard on the guard. A double whose write methods silently succeeded
        # would make the test above pass for the wrong reason.
        project = FakeProject([human(1)])
        with pytest.raises(ProjectWriteAttempted):
            project.WfiAnalysis.ApproveAnalysis(object())

    @pytest.mark.parametrize("name", WRITE_METHODS)
    def test_every_write_method_is_armed_on_the_double(self, name):
        project = FakeProject([])
        with pytest.raises(ProjectWriteAttempted):
            getattr(project.WfiAnalysis, name)()

    def test_an_unreadable_evaluation_does_not_provoke_a_write(self):
        # The tempting "repair" for an unreadable record is to re-evaluate it.
        project = FakeProject([unreadable(), unreadable()])
        state = probe_project_state(project)
        assert state.indeterminate_analyses == 2


# ---------------------------------------------------------------------------
# 2. What the probe counts
# ---------------------------------------------------------------------------

class TestProbeCounts:

    def test_empty_project_has_never_been_parsed(self):
        state = probe_project_state(FakeProject([]))
        assert state.parser_has_ever_run is False
        assert state.analyses_total == 0

    def test_hand_analysed_project_has_never_been_parsed(self):
        # The failure this pins: deriving "has been parsed" from "has
        # analyses". A project analysed entirely by hand has many analyses and
        # no parser output, and reporting the oracle there compares the human
        # record against nothing.
        state = probe_project_state(FakeProject([human(1), human(2), human(3)]))
        assert state.parser_has_ever_run is False
        assert state.human_opinion_analyses == 3
        assert state.parser_created_analyses == 0

    def test_one_parser_created_analysis_is_enough(self):
        state = probe_project_state(FakeProject([human(1), machine(1)]))
        assert state.parser_has_ever_run is True
        assert state.parser_created_analyses == 1
        assert state.human_opinion_analyses == 1

    def test_human_opinion_wins_over_a_machine_evaluation(self):
        # An analysis the parser produced and a human then approved is a
        # human-opinion analysis. Counting it as parser-created would put it
        # in a deletion projection, which is exactly the analysis a linguist
        # least wants proposed for deletion.
        both = FakeAnalysis(human="h", machine="m")
        state = probe_project_state(FakeProject([both]))
        assert state.human_opinion_analyses == 1
        assert state.parser_created_analyses == 0

    def test_no_opinion_on_either_side_is_indeterminate(self):
        state = probe_project_state(FakeProject([no_opinion(), no_opinion()]))
        assert state.indeterminate_analyses == 2
        assert state.parser_created_analyses == 0
        assert state.human_opinion_analyses == 0

    def test_unreadable_is_never_folded_into_parser_created(self):
        # Folding unreadable into machine-made inflates a deletion
        # projection with analyses a human may have made.
        state = probe_project_state(FakeProject([unreadable()] * 5))
        assert state.parser_created_analyses == 0
        assert state.indeterminate_analyses == 5
        assert state.parser_has_ever_run is False

    def test_counts_partition_the_total(self):
        project = FakeProject(
            [human(1), human(2), machine(1), no_opinion(), unreadable()]
        )
        s = probe_project_state(project)
        assert (
            s.human_opinion_analyses
            + s.parser_created_analyses
            + s.indeterminate_analyses
        ) == s.analyses_total


class TestProbeBound:

    def test_limit_truncates_and_says_so(self):
        state = probe_project_state(FakeProject([machine(1)] * 10), limit=4)
        assert state.truncated is True
        assert state.analyses_total == 4

    def test_no_limit_reads_everything(self):
        state = probe_project_state(FakeProject([machine(1)] * 10), limit=None)
        assert state.truncated is False
        assert state.analyses_total == 10

    def test_untruncated_run_reports_truncated_false(self):
        state = probe_project_state(FakeProject([machine(1)] * 3), limit=100)
        assert state.truncated is False

    def test_default_limit_is_declared(self):
        assert isinstance(DEFAULT_PROBE_LIMIT, int) and DEFAULT_PROBE_LIMIT > 0


# ---------------------------------------------------------------------------
# 3. All three consumers resolve through the one implementation (FR-004)
# ---------------------------------------------------------------------------

THREE_CONSUMERS = (
    never_parsed_warning,
    oracle_is_available,
    deletion_projection_precondition,
)


class TestThreeConsumersShareOneProbe:

    def test_there_are_exactly_three_named_consumers(self):
        assert len(THREE_CONSUMERS) == 3

    @pytest.mark.parametrize("consumer", THREE_CONSUMERS)
    def test_each_consumer_takes_the_probe_result_not_a_project(self, consumer):
        # This is the structural half of FR-004. A consumer that accepted a
        # project could re-probe inside itself, and the duplication FR-004
        # forbids would be invisible at the call site.
        params = list(inspect.signature(consumer).parameters.values())
        assert len(params) == 1, consumer.__name__
        assert params[0].annotation in (ProjectParseState, "ProjectParseState"), (
            consumer.__name__ + " must take a ProjectParseState"
        )

    def test_one_probe_result_serves_all_three(self):
        project = FakeProject([human(1), machine(1)])
        state = probe_project_state(project)
        before = project.WfiAnalysis.get_all_calls
        for consumer in THREE_CONSUMERS:
            consumer(state)
        # No consumer traversed the project again.
        assert project.WfiAnalysis.get_all_calls == before == 1

    def test_never_parsed_project_drives_all_three_consistently(self):
        state = probe_project_state(FakeProject([human(1)]))
        assert never_parsed_warning(state) is not None
        assert oracle_is_available(state) is False
        assert deletion_projection_precondition(state) is False

    def test_parsed_project_drives_all_three_consistently(self):
        state = probe_project_state(FakeProject([machine(1)]))
        assert never_parsed_warning(state) is None
        assert oracle_is_available(state) is True
        assert deletion_projection_precondition(state) is True


class TestNeverParsedWarningWording:

    def test_warning_does_not_claim_the_project_is_unanalysed(self):
        # A hand-analysed project is richly analysed. The warning is about the
        # parser never having run, not about the project being empty.
        state = probe_project_state(FakeProject([human(1)] * 20))
        text = never_parsed_warning(state).lower()
        assert "parser has not run" in text
        for forbidden in ("unanalysed", "unanalyzed", "no analyses", "empty"):
            assert forbidden not in text

    def test_warning_is_absent_rather_than_empty_when_parser_has_run(self):
        state = probe_project_state(FakeProject([machine(1)]))
        assert never_parsed_warning(state) is None


class TestStateIsSerializable:

    def test_to_dict_round_trips_every_field(self):
        state = probe_project_state(FakeProject([human(1), machine(1)]))
        d = state.to_dict()
        assert set(d) == {
            "parser_has_ever_run",
            "analyses_total",
            "parser_created_analyses",
            "human_opinion_analyses",
            "indeterminate_analyses",
            "truncated",
        }
        assert ProjectParseState(**d) == state
