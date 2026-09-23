#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The ONE read-only project-state probe (parser-check CP3, FR-004).

WHY THIS MODULE EXISTS AS A MODULE. Three separate places need to know the
same thing -- whether the parser has ever run against this project, and how
much of the analysis record is machine-made -- and each of them, left to
itself, would answer it with its own traversal. Three traversals of the same
data give three subtly different answers the first time one of them is
optimised, and the disagreement surfaces as a report that contradicts itself.
FR-004 therefore says the probe is built EXACTLY ONCE and that CP4 consumes
it rather than growing a second one. A second probe at CP4 is a review
finding, not a refactor.

THE THREE CONSUMERS, named here because FR-004 requires them named:

  1. The never-parsed warning (FR-041)
     A project the parser has never run against has no parser output to
     compare the human record against. Without the warning, the diagnosis
     still renders -- and renders every analysis as though the parser
     declined to produce one, which reads as a corpus-wide failure rather
     than as a parse that never happened.

  2. The oracle precondition (FR-041)
     Same fact, opposite use. The oracle reports what the human record
     affirms. On a never-parsed project it must be reported ABSENT, with its
     own sentence, rather than emitting a report in which every analysis
     reads as unreviewed.

  3. CP4's deletion-projection precondition (FR-050)
     The deletion projection counts analyses that are parser-created AND
     carry no user opinion AND are not referenced by any segment. The first
     of those three conjuncts is this probe's ``parser_created_analyses``.
     CP4 consumes this module; it does not write its own.

EVERYTHING HERE IS READ-ONLY, and that is asserted rather than intended:
``tests/test_parse_project_state.py`` drives the probe with a double that
raises on any mutating call, and the standing
``tests/test_parse_no_project_writes.py`` (FR-063) covers the checkpoint as a
whole. Only ``Get*``/``Is*`` reads appear below. Nothing here creates,
deletes, approves, rejects or sets anything.

WHAT "PARSER-CREATED" MEANS HERE. An analysis is treated as machine-made when
it carries a computer/agent evaluation and no human one. That is a read of
the stored evaluation record, not an inference from shape: an analysis with
three morph bundles is not "obviously" machine-made, and guessing would
misclassify exactly the careful hand-built analyses a linguist most wants
left alone. Where the evaluation record cannot be read at all the analysis is
counted as INDETERMINATE and is excluded from both counts -- never silently
folded into the machine-made side, which would inflate a deletion projection
with analyses a human made.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


# Probing every analysis in a large project is a full traversal. The cap
# below keeps the probe bounded; `truncated` says when it was hit, so a
# consumer reports a bounded observation rather than presenting a partial
# count as a total.
DEFAULT_PROBE_LIMIT = 50_000


@dataclass(frozen=True)
class ProjectParseState:
    """What one read-only pass over the analysis record establishes.

    ``parser_has_ever_run`` is the single fact all three consumers turn on.
    It is deliberately *not* derived from "are there any analyses at all":
    a project can be richly analysed entirely by hand, and reporting the
    oracle as present there would compare the human record against parser
    output that does not exist.

    ``indeterminate_analyses`` is carried rather than dropped. A count that
    silently excludes what it could not read is indistinguishable from a
    count that found nothing, and the two call for different responses.
    """

    parser_has_ever_run: bool
    analyses_total: int
    parser_created_analyses: int
    human_opinion_analyses: int
    indeterminate_analyses: int
    truncated: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class _Unreadable(Exception):
    """Internal: this analysis's evaluation record could not be read."""


def _has_human_opinion(project: Any, analysis: Any) -> bool:
    """True when a human has recorded an opinion on this analysis.

    Tries the explicit human-evaluation read first and falls back to the
    approval predicate. Both are reads. If neither can be established the
    caller is told so rather than being handed a default -- see the module
    docstring on why an unreadable evaluation is not counted as machine-made.
    """
    for reader in (
        lambda: project.WfiAnalysis.GetHumanEvaluation(analysis) is not None,
        lambda: bool(project.WfiAnalysis.IsHumanApproved(analysis)),
    ):
        try:
            return bool(reader())
        except Exception:
            continue
    raise _Unreadable()


def _has_machine_opinion(project: Any, analysis: Any) -> bool:
    """True when the parser (a computer agent) evaluated this analysis."""
    for reader in (
        lambda: project.WfiAnalysis.GetAgentEvaluation(analysis) is not None,
        lambda: bool(project.WfiAnalysis.IsComputerApproved(analysis)),
    ):
        try:
            return bool(reader())
        except Exception:
            continue
    raise _Unreadable()


def probe_project_state(
    project: Any,
    *,
    limit: Optional[int] = DEFAULT_PROBE_LIMIT,
) -> ProjectParseState:
    """One read-only pass over the analysis record. The only probe (FR-004).

    Args:
        project: an open flexicon ``FLExProject``. Opened read-only by every
            CP3 caller; this function would still not write if it were not.
        limit: stop after this many analyses and set ``truncated``. ``None``
            means no cap. The cap exists so a diagnosis on a very large
            project stays bounded, not because a partial answer is as good --
            hence ``truncated`` rather than a silent stop.

    Returns:
        ProjectParseState. Never raises for an unreadable individual
        analysis; those land in ``indeterminate_analyses``.
    """
    analyses_total = 0
    parser_created = 0
    human_opinion = 0
    indeterminate = 0
    truncated = False

    for analysis in project.WfiAnalysis.GetAll():
        if limit is not None and analyses_total >= limit:
            truncated = True
            break
        analyses_total += 1

        try:
            human = _has_human_opinion(project, analysis)
        except _Unreadable:
            indeterminate += 1
            continue

        if human:
            human_opinion += 1
            continue

        # No human opinion. Machine-made only if the machine actually
        # evaluated it -- absence of a human opinion is not presence of a
        # parser one.
        try:
            machine = _has_machine_opinion(project, analysis)
        except _Unreadable:
            indeterminate += 1
            continue

        if machine:
            parser_created += 1
        else:
            # Neither side has an opinion on record. That is a real state,
            # not a read failure, and it belongs in neither count.
            indeterminate += 1

    return ProjectParseState(
        parser_has_ever_run=parser_created > 0,
        analyses_total=analyses_total,
        parser_created_analyses=parser_created,
        human_opinion_analyses=human_opinion,
        indeterminate_analyses=indeterminate,
        truncated=truncated,
    )


# ---------------------------------------------------------------------------
# The three consumers (FR-004). Each is a thin read of ONE probe result.
#
# They take a ProjectParseState rather than a project on purpose: a consumer
# that took a project could quietly re-probe, which is the duplication FR-004
# exists to prevent. Taking the state makes a second traversal impossible to
# write by accident.
# ---------------------------------------------------------------------------

def never_parsed_warning(state: ProjectParseState) -> Optional[str]:
    """Consumer 1 (FR-041): the warning, or None when the parser has run."""
    if state.parser_has_ever_run:
        return None
    return (
        "The parser has not run against this project, so there is no parser "
        "output to compare the human analysis record against. What follows "
        "describes the human record only."
    )


def oracle_is_available(state: ProjectParseState) -> bool:
    """Consumer 2 (FR-041): may the oracle be reported at all?

    False means the oracle is reported ABSENT with its own sentence -- not
    that it is reported empty. An empty oracle reads as "nothing is
    approved"; an absent one reads as "this was never measured", and only the
    second is true on a project the parser has never run against.
    """
    return state.parser_has_ever_run


def deletion_projection_precondition(state: ProjectParseState) -> bool:
    """Consumer 3 (FR-050, consumed at CP4): is the projection meaningful?

    The projection's first conjunct is "parser-created". With no parser-created
    analyses the projection is necessarily empty, and reporting an empty
    projection invites the reading that there is nothing to tidy -- when in
    fact nothing was ever measured.

    CP4 CONSUMES THIS. It does not grow its own probe (FR-004).
    """
    return state.parser_created_analyses > 0
