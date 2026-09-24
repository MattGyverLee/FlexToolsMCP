#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The mutation plan and its identity (parser-check CP4, FR-006, FR-010, FR-016;
R-08; data-model section 2).

THE PLAN IS THE PREVIEW. It is what `confirmation_required` carries: the words
in scope, the grammar's standing, how many analyses MAY be deleted and which
(per wordform), the human disapprovals filing will overwrite, the in-use
analyses it will record an approval on, the duplicate disclosure, whether a
backup is expected, the access verdict, Send/Receive participation and the
recovery route -- all computed from the project, never an abstract warning
(FR-013).

THE PLAN_ID BINDS A CONFIRMATION TO WHAT WAS SHOWN (FR-006). It is sha256 over
the canonical JSON of the plan's BOUND fields: every field a human could base
the decision on. Display-only wording -- the estimate note, the recovery
route's prose, the side-effect sentences, the disclosure of the confirmation
setting -- is left out, so rewording a sentence never invalidates a plan
while any count, set, verdict or outcome changing does. The handler recomputes
the plan at confirm time; a different id means the human is looking at a plan
that no longer describes what would happen, and gets a new preview instead of
a filing run.

THE HONEST LIMIT (constitution Principle I): the id proves that this plan was
issued and is unchanged. Nothing in a stdio tool can prove a person read it.
That is a safety property, not a security boundary, and the plan says so.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Optional, Tuple

from . import wording
from .paths import treats_as_send_receive
from .projection import ProjectionResult
from ..signals.projections import duplicate_projection

__all__ = [
    "BOUND_FIELDS",
    "build_plan",
    "plan_id_for",
    "canonical_json",
    "duplicate_disclosure",
]

#: The fields `plan_id` is computed over (data-model section 2, "Bound into
#: plan_id?"). `backup` and `access` are bound by outcome / verdict only.
BOUND_FIELDS = (
    "scope",
    "scope_fingerprint_key",
    "words_in_scope",
    "gate",
    "deletion_projection",
    "disapproval_overwrites",
    "in_use_approvals_projected",
    "duplicate_disclosure",
    "backup",
    "access",
    "send_receive",
)


def canonical_json(value: Any) -> str:
    """Sorted keys, no whitespace, ASCII: one byte string per value."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      default=str)


def _bound_view(plan: Dict[str, Any]) -> Dict[str, Any]:
    view = {name: plan.get(name) for name in BOUND_FIELDS}
    view["backup"] = {"outcome": (plan.get("backup") or {}).get("outcome")}
    view["access"] = {"verdict": (plan.get("access") or {}).get("verdict")}
    return view


def plan_id_for(plan: Dict[str, Any]) -> str:
    """sha256 over the canonical JSON of the bound fields, 64 lowercase hex."""
    return hashlib.sha256(canonical_json(_bound_view(plan)).encode("ascii")).hexdigest()


def duplicate_disclosure(
    lines: Optional[Iterable[Dict[str, Any]]], *, basis: str
) -> Dict[str, Any]:
    """FR-016: how many projected creations would duplicate a gloss-only record.

    CP3's `duplicate_projection`, reused as is, over the result lines of the
    most recent read-only run of this scope. That count needs the parser's
    analyses, and the preview parses nothing; so with no prior run the count
    is UNKNOWN (`None`), never 0 -- a 0 would claim nothing duplicates. The
    basis names where the number came from. Merging is out of scope.
    """
    if lines is None:
        return {"count": None, "basis": basis}
    return {"count": duplicate_projection(lines)["count"], "basis": basis}


def build_plan(
    *,
    scope: Dict[str, Any],
    scope_fingerprint_key: str,
    words_in_scope: int,
    gate: Dict[str, Any],
    projection: ProjectionResult,
    duplicate_disclosure: Dict[str, Any],
    backup: Dict[str, Any],
    access: Dict[str, Any],
    send_receive: Any,
    require_write_confirmation: bool,
) -> Tuple[Dict[str, Any], str]:
    """Assemble the plan (data-model section 2) and compute its `plan_id`."""
    backup_block = {
        "outcome": backup.get("outcome"),
        "reason": backup.get("reason"),
    }
    if backup.get("peer_caveat"):
        backup_block["peer_caveat"] = backup["peer_caveat"]
    if backup_block["outcome"] != "will_be_taken":
        backup_block["no_recovery_warning"] = wording.no_recovery_warning(
            backup_block["reason"], send_receive
        )

    access_block = {"verdict": access.get("verdict")}
    for key in ("shared_mode_advisory", "remedy", "refused_on_confirm", "note"):
        if access.get(key) is not None:
            access_block[key] = access[key]

    upper_bound = int(projection.deletion.get("upper_bound") or 0)
    plan: Dict[str, Any] = {
        "scope": dict(scope),
        "scope_fingerprint_key": scope_fingerprint_key,
        "words_in_scope": int(words_in_scope),
        "gate": dict(gate),
        "deletion_projection": dict(projection.deletion),
        "disapproval_overwrites": dict(projection.disapproval_overwrites),
        "in_use_approvals_projected": int(projection.in_use_approvals_projected),
        "duplicate_disclosure": dict(duplicate_disclosure),
        "errored_word_rule": wording.ERRORED_WORD_RULE,
        "backup": backup_block,
        "access": access_block,
        "send_receive": send_receive,
        "recovery_route": (
            wording.SEND_RECEIVE_ROUTE if treats_as_send_receive(send_receive)
            else wording.RESTORE_ROUTE
        ),
        "side_effects": [
            wording.PROBLEM_ANNOTATIONS_SIDE_EFFECT,
            wording.LOWERCASE_DIVERGENCE,
        ],
        "confirmation_setting": {
            "require_write_confirmation": bool(require_write_confirmation),
            "effective_for_filing": True,
        },
        "estimate_note": wording.estimate_note(upper_bound, words_in_scope),
    }
    return plan, plan_id_for(plan)
