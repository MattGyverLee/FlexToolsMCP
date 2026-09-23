#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The CP3 quickstart scenarios, against live FieldWorks projects
(parser-check CP3; specs/parser-check-cp3/quickstart.md).

EVERYTHING HERE IS READ-ONLY. CP3 ships no write path at all -- not a guarded
one, not a confirmed one. That is a standing guarantee (FR-063) asserted
separately and by test in `tests/test_parse_no_project_writes.py`; this module
must never become the exception that makes that test a lie.

WHY THESE SCENARIOS NEED A LIVE PROJECT. The offline suite covers the shapes:
that a diff classifies on signature sets rather than counts, that ranking only
promotes, that a projection needs all three conjuncts. What a double cannot
settle is whether the things being doubled are *true of the data model* --
and CP3's plan rests on two facts that are live-only:

  * ANALYSIS IDENTIFIER STABILITY across sessions. `DurableAnalysisSignature`
    (FR-031) is a sequence of identifier triples. If those identifiers are not
    stable across a close/reopen, the whole comparison silently degrades and
    the FR-033 rendered-form fallback has to be activated instead. T125
    records the verdict; only a live run can produce it.
  * SHARED-MODE STALENESS. FR-034 downgrades a `no_change` to
    `no_change_unverifiable` when the project is open elsewhere. Whether the
    probe can see that at all, and what it reports, is a property of a real
    open project.

THE DESIGNATED PROJECTS, and why `Sena 3` is not one of them:

    IndonesianHC-Complete           correctness. Scenarios 1-6, the
                                    break-then-revert cycle (SC-009) and the
                                    kill-mid-batch (SC-004).
    Malay Parsing-20230810withHC    scale. The scale scenarios only.

    Sena 3                          EXCLUDED BY NAME. It reports engine
                                    `XAmple`, and this feature's own engine
                                    gate (FR-024) refuses it before a parser
                                    is constructed. It is not a smaller
                                    stand-in for a HermitCrab project; it is a
                                    project CP3 declines to run against, and
                                    substituting it would test the refusal
                                    rather than the feature. Do not swap it in
                                    when a designated project is unavailable
                                    -- skip instead.

Scenario-to-task mapping (specs/parser-check-cp3/tasks.md Phase 9):

    T122    Scenarios 1-3 on IndonesianHC-Complete, with pre/post evidence
            captured to the same discipline a write path would get
    T123    Scenarios 4-6 on IndonesianHC-Complete, including the
            break-then-revert cycle (SC-009) and the kill-mid-batch (SC-004)
    T124    the scale scenarios on Malay Parsing-20230810withHC (SC-022)
    T125    the identifier-stability verdict, read out of T122's evidence

Deselect on a machine without FieldWorks with `-m "not requires_flex"`, the
same way `tests/test_parse_live.py` is deselected.
"""

import os

import pytest

pytestmark = pytest.mark.requires_flex


# The correctness project. Scenarios 1-6 and both SC-004 and SC-009 run here.
HC_PROJECT = os.environ.get("FLEXTOOLSMCP_LIVE_HC_PROJECT", "IndonesianHC-Complete")

# The scale project. The scale scenarios only (T124, SC-022).
SCALE_PROJECT = os.environ.get(
    "FLEXTOOLSMCP_LIVE_SCALE_PROJECT", "Malay Parsing-20230810withHC"
)

# Named here so the exclusion is greppable and survives a refactor that loses
# the docstring. Nothing in this module may open it.
EXCLUDED_XAMPLE_PROJECT = "Sena 3"


def test_the_excluded_project_is_never_a_substitute():
    """`Sena 3` must not be reachable as either designated project.

    This is a guard on the test module itself rather than on the server. The
    failure it exists to catch is a maintainer setting
    `FLEXTOOLSMCP_LIVE_HC_PROJECT=Sena 3` to get a red live suite green on a
    machine that lacks the real project -- which would silently convert every
    scenario below into an assertion about the engine refusal.
    """
    assert HC_PROJECT != EXCLUDED_XAMPLE_PROJECT
    assert SCALE_PROJECT != EXCLUDED_XAMPLE_PROJECT
