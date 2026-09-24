#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The fixed sentences filing says (parser-check CP4, data-model section 8).

TRANSCRIBED, NOT PARAPHRASED. Each sentence below is copied from
`specs/parser-check-cp4/data-model.md` section 8 (or, where noted, the plan or
research), and the tests assert them byte for byte. CP2's field-order
divergence happened during transcription, which is why every string a caller
reads is defined once, here, and rendered by substitution only.

FORBIDDEN WORDS (FR-033, contracts section 3). No filing output labels an
analysis `tacit`, `unreviewed`, `auto_approved` or `auto-approved`: approval is
recorded for anything left in use in a text, so an approval says nothing about
whether a person looked. Three mandated sentences contain one of those words
without labelling any analysis: FR-017's errored-word rule ("its unshielded,
unreviewed analyses", describing FLEx's deletion rule), and CP3's two
counter-divergence statements, carried by every batch record, one of which
says a counter "is NOT a count of unreviewed analyses". `FORBIDDEN_SCAN_EXEMPT`
names exactly those, verbatim, so the scan exempts them and nothing else.
"""

from __future__ import annotations

from typing import Optional

__all__ = [
    "NO_RECOVERY_WARNING",
    "SEND_RECEIVE_ROUTE",
    "SHARED_MODE_ADVISORY",
    "ERRORED_WORD_RULE",
    "IN_USE_APPROVALS",
    "HYPOTHESIS_NOTE",
    "LOWERCASE_DIVERGENCE",
    "DECLINED_DIVERGENCE",
    "PROBLEM_ANNOTATIONS_SIDE_EFFECT",
    "RESTORE_ROUTE",
    "PLAN_ID_LIMIT",
    "FORBIDDEN_WORDS",
    "FORBIDDEN_SCAN_EXEMPT",
    "no_recovery_warning",
    "in_use_approvals_sentence",
    "estimate_note",
]

#: FR-009. `[reason]` is substituted.
NO_RECOVERY_WARNING = (
    "NO BACKUP WAS TAKEN ([reason]). Filing cannot be undone, and no recovery "
    "point exists for this run."
)

#: FR-043. Appended to the no-backup warning and to the plan when the project
#: takes part in Send/Receive (or when that cannot be determined).
SEND_RECEIVE_ROUTE = (
    "This project takes part in Send/Receive. If filing damages it, do not "
    "Send/Receive; delete this local copy and re-download the project from its "
    "repository. A local backup, where one exists, is a convenience for this "
    "machine, not a way to revert the shared project."
)

#: FR-030.
SHARED_MODE_ADVISORY = (
    "FLEx has this project open with sharing enabled; filing will run as a "
    "non-master peer. Make sure FLEx's own parser is not running on this "
    "project. The MCP cannot detect whether it is, and filing by both at once "
    "is not prevented."
)

#: FR-017.
ERRORED_WORD_RULE = (
    "A word whose parse ends in an error is filed as FLEx files it: its parser "
    "opinions are cleared and its unshielded, unreviewed analyses are deleted."
)

#: FR-033. `[N]` is substituted.
IN_USE_APPROVALS = (
    "[N] analyses in use in a text were given a user approval by filing. "
    "Approval is recorded for anything left in use; this does not mean anyone "
    "reviewed them."
)

#: data-model section 4 (the spec's Assumptions: "a working hypothesis").
HYPOTHESIS_NOTE = (
    "pre-existing load errors are treated as benign; that is a working "
    "hypothesis, not an established fact"
)

#: R-06.
LOWERCASE_DIVERGENCE = (
    "FLEx's menu also files the lowercase form of a capitalised word; this run does not."
)

#: R-03 / FR-019: declined is not deferred.
DECLINED_DIVERGENCE = (
    "When FieldWorks' filer declines to start a word's update because a write "
    "is already in progress, FLEx retries it on its next idle cycle; this run "
    "does not, and reports that word as not filed."
)

#: FR-010 (the edge case "Project-wide side effect").
PROBLEM_ANNOTATIONS_SIDE_EFFECT = (
    "Each word filed makes FieldWorks' filer remove every parser-sourced problem "
    "annotation in the whole project. No current code path creates them."
)

#: The non-Send/Receive recovery route.
RESTORE_ROUTE = (
    "If filing damages this project, the way back is to restore the backup taken "
    "before the run (docs/RECOVERY.md). Filing itself cannot be undone."
)

#: FR-034: what a cancelled filing run says, in the response and the record.
CANCEL_NOTE = (
    "Cancellation stops the run at its next word boundary. Every word filed "
    "before that stays filed: filing cannot be undone except by restoring the "
    "backup (or, for a project in Send/Receive, by discarding this copy and "
    "re-downloading it). The run's record lists exactly which words were filed."
)

#: R-08, constitution Principle I: the honest limit of the binding.
PLAN_ID_LIMIT = (
    "The plan_id proves that this plan was issued and has not changed since; it "
    "cannot prove that anyone read it."
)

FORBIDDEN_WORDS = ("tacit", "unreviewed", "auto_approved", "auto-approved")


def _cp3_counter_divergences() -> tuple:
    from ..parse.record import COUNTER_DIVERGENCES

    return tuple(COUNTER_DIVERGENCES)


#: The mandated sentences the forbidden-word scan exempts, verbatim, and
#: nothing else: FR-017's errored-word rule (see the module docstring), and
#: CP3's two counter-divergence statements, which every batch record carries
#: and one of which says a counter is "NOT a count of unreviewed analyses" --
#: denying the label, not applying it (CP3 FR-017, FR-042).
FORBIDDEN_SCAN_EXEMPT = (ERRORED_WORD_RULE,) + _cp3_counter_divergences()


def no_recovery_warning(reason: Optional[str], send_receive: object) -> str:
    """FR-009's warning, with FR-043's route appended for an S/R project.

    `send_receive` is True, False or "unknown"; anything but False is worded
    as Send/Receive (R-14).
    """
    text = NO_RECOVERY_WARNING.replace("[reason]", str(reason or "reason not recorded"))
    if send_receive is not False:
        text = f"{text} {SEND_RECEIVE_ROUTE}"
    return text


def in_use_approvals_sentence(count: int) -> str:
    return IN_USE_APPROVALS.replace("[N]", str(int(count)))


def estimate_note(upper_bound: int, words: int) -> str:
    """The projection is an upper bound, never a prediction (data-model s.2)."""
    return (
        f"This run may delete up to {int(upper_bound)} "
        f"analys{'is' if int(upper_bound) == 1 else 'es'} across {int(words)} "
        f"word{'' if int(words) == 1 else 's'}. That is an upper bound, not a "
        f"prediction: every word is parsed fresh, and only analyses the new parse "
        f"does not produce again -- and that nobody has approved or disapproved, "
        f"and that no text uses -- can be deleted."
    )
