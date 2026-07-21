#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tier-1 eval harness: drives the FlexToolsMCP preflight validator chain
DIRECTLY against corpus entries (issue #51), without opening a real
FieldWorks project and without an LLM in the loop.

TODO(#49): once `run_module`'s `validate_only` mode lands, prefer calling
that entry point instead of re-implementing the gate order here -- it will
be the single source of truth and can't drift from the real handler. Until
then this module mirrors the ordered gate sequence in
`flextoolsmcp.server.handlers.execution.handle_run_module` (see that
function's body for the authoritative order). Keep the two in sync when
either changes.

Scope / simplifications (documented, not hidden):
- `api_index` is a small hand-built `_FakeAPIIndex` (a handful of Operations
  classes with a few methods each), not the real generated flexicon index.
  Gates that only activate against a populated index (e.g. the advanced
  casting_index-driven loop in `detect_casting_needs`, or fuzzy accessor
  matching against the FULL real accessor list) are exercised only to the
  extent the fake index models them. Entries that need the real index are
  marked `skip: true` with a reason pointing at the validator unit tests
  that DO use the real index (test_validator_casting_chains.py etc).
- Read-only auto-discovery / graceful-discovery-redirect nuance (issues #47,
  #80) is NOT modeled: this runner treats any undiscovered entity as a
  straight `undiscovered_entity` preflight_reject regardless of
  `write_enabled`. That is intentionally conservative for a regression
  corpus -- corpus authors should populate `session.validated_apis` /
  `session.discovered_apis` (or rely on the "importing satisfies discovery"
  rule, issue #31) for any entity a corpus entry's code touches when the
  expected outcome is "ok".
- Auto-fix (issue #46) is NOT simulated. `expect.auto_fixes` is currently
  only sanity-checked to be 0; entries exercising auto-fix should be
  `skip: true` until this runner grows that capability.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Set

from server.validators import (
    validate_server_state,
    detect_partial_module_structure,
    certify_script_readonly,
    detect_casting_needs,
    detect_undiscovered_entities,
    detect_undefined_variables,
    detect_missing_operations_imports,
    detect_wrong_library_imports,
    detect_invalid_project_chains,
    detect_getall_unsafe_idiom,
)
from server import kernel


# ---------------------------------------------------------------------------
# Fake API index: a handful of entities/methods, enough to exercise the
# index-aware branches of certify_script_readonly / detect_invalid_project_chains
# without depending on the real generated flexicon index (which may not be
# present in a bare CI checkout).
# ---------------------------------------------------------------------------

class _FakeAPIIndex:
    def __init__(self) -> None:
        self.flexicon: Dict[str, Any] = {
            "entities": {
                "FLExProject": {
                    "properties": [
                        {"name": "LexEntry", "return_type": "LexEntryOperations"},
                        {"name": "POS", "return_type": "POSOperations"},
                        {"name": "Senses", "return_type": "LexSenseOperations"},
                        {"name": "Segments", "return_type": "SegmentOperations"},
                    ],
                    "methods": [
                        {"name": "LexiconGetSense"},
                    ],
                },
                "LexEntryOperations": {
                    "methods": [
                        # return_type wording retained for historical parity with
                        # the real index; detect_getall_unsafe_idiom no longer
                        # reads it (cycle-4 reversal: the detector is now
                        # flexlibs_stable-only and index-independent).
                        {"name": "GetAll", "is_mutating": False, "return_type": "EnumerableWrapper[ILexEntry]"},
                        {"name": "GetLexemeForm", "is_mutating": False},
                        {"name": "Create", "is_mutating": True},
                        {"name": "SetLexemeForm", "is_mutating": True},
                    ],
                },
                "POSOperations": {
                    "methods": [
                        {"name": "GetAll", "is_mutating": False, "return_type": "EnumerableWrapper[IPartOfSpeech]"},
                        {"name": "GetSyncableProperties", "is_mutating": False},
                        # Issue #38 regression: ApplySyncableProperties is a
                        # real, correctly-indexed mutating method (it used to
                        # be missing from the generated index entirely, which
                        # caused a false invalid_api_chain reject).
                        {"name": "ApplySyncableProperties", "is_mutating": True},
                        {"name": "Create", "is_mutating": True},
                    ],
                },
                "LexSenseOperations": {
                    "methods": [
                        {"name": "GetAll", "is_mutating": False, "return_type": "EnumerableWrapper[ILexSense]"},
                        {"name": "GetGloss", "is_mutating": False},
                        {"name": "SetGloss", "is_mutating": True},
                    ],
                },
                "SegmentOperations": {
                    "methods": [
                        {"name": "GetAll", "is_mutating": False, "return_type": "EnumerableWrapper[ISegment]"},
                        {"name": "IsLabel", "is_mutating": False},
                        {"name": "GetFreeTranslation", "is_mutating": False},
                    ],
                },
                "WordformOperations": {
                    "methods": [
                        {"name": "GetAll", "is_mutating": False, "return_type": "EnumerableWrapper[IWfiWordform]"},
                    ],
                },
            }
        }
        # Minimal fake casting_index: `detect_casting_needs`'s advanced,
        # index-driven loop (issue #40 safe-member / operations-alias-arg /
        # cast-alias-satisfies skips) is entirely gated behind a truthy
        # casting_index, independent of what properties it actually lists.
        # Only "CategoryRA" is populated as a property that genuinely
        # requires casting, so this only affects corpus entries that
        # reference CategoryRA -- everything else is unaffected by turning
        # the advanced loop on.
        self.casting_index: Optional[Dict[str, Any]] = {
            "properties": {
                "CategoryRA": {
                    "requires_cast_from": ["ICmObject"],
                    "defined_on": ["IWfiAnalysis"],
                },
            },
            "polymorphic_collections": {},
        }

    def ensure_casting_index_loaded(self) -> None:
        pass


FAKE_API_INDEX = _FakeAPIIndex()


@dataclass
class _FakeSession:
    """Minimal stand-in for server.session.SessionState.

    Only the attributes `detect_undiscovered_entities` actually reads.
    """

    validated_apis: Set[str] = field(default_factory=set)
    discovered_apis: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

@dataclass
class PreflightResult:
    outcome: str  # "ok" | "preflight_reject"
    error_code: Optional[str]
    gate: Optional[str]
    detail: str = ""
    # getall-contract SPEC §6 Level 3: non-blocking advisory codes attached
    # to an "ok" outcome (never changes outcome/error_code). Empty for
    # preflight_reject results (the chain returns before the advisory check
    # runs) and for any "ok" result with no flagged GetAll() idiom.
    advisories: list = field(default_factory=list)


_ORDERED_GATES = (
    "project_name_required",
    "syntax_error",
    "server_state_error",
    "partial_module_structure",
    "unprotected_writes",
    "casting_issues_detected",
    "api_discovery_required",
    "undiscovered_entity",
    "undefined_variables",
    "missing_imports",
    "wrong_library_imports",
    "invalid_api_chain",
)


def run_preflight_chain(entry: Dict[str, Any]) -> PreflightResult:
    """Run the ordered preflight gate chain against one corpus entry.

    `entry` is a parsed corpus YAML dict; see tests/evals/corpus/*.yaml for
    the schema (intent, api_mode, write_enabled, code, session, expect, ...).
    """
    code: str = entry.get("code") or ""
    api_mode: str = entry.get("api_mode", "flexicon")
    write_enabled: bool = bool(entry.get("write_enabled", False))
    project_name: str = entry.get("project_name", "TestProject")
    skip_module_check: bool = bool(entry.get("skip_module_check", False))
    force_server_unhealthy: bool = bool(entry.get("force_server_unhealthy", False))

    session_cfg = entry.get("session") or {}
    session = _FakeSession(
        validated_apis=set(session_cfg.get("validated_apis") or []),
        discovered_apis=set(session_cfg.get("discovered_apis") or []),
    )

    # Gate 0: project_name_required. Checked before anything else in the real
    # handler -- an empty project name means there's no "operation" to log.
    if not project_name:
        return PreflightResult("preflight_reject", "project_name_required", "project_name_required")

    # Gate 1: syntax_error.
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return PreflightResult(
            "preflight_reject", "syntax_error", "syntax_error", f"line {exc.lineno}: {exc.msg}"
        )

    # Gate 2: server_state_error. In the real server this fires when the
    # operations logger / kernel modules aren't initialized. We drive it here
    # via the `force_server_unhealthy` corpus flag rather than the ambient
    # test-process kernel state (which a parallel test file might have already
    # initialized).
    if force_server_unhealthy:
        prior_logger = kernel.get_operations_logger()
        kernel.operations_logger = None
        try:
            health = validate_server_state()
        finally:
            kernel.operations_logger = prior_logger
    else:
        # Ensure the logger is initialized so unrelated entries don't spuriously
        # trip server_state_error just because no other test has run yet.
        if kernel.get_operations_logger() is None:
            kernel.init_operations_logger()
        health = validate_server_state()

    if not health["is_healthy"]:
        return PreflightResult(
            "preflight_reject", "server_state_error", "server_state_error", str(health["issues"])
        )

    # Gate 3: partial_module_structure.
    if not skip_module_check:
        partial = detect_partial_module_structure(code, tree)
        if partial["is_partial_module"]:
            return PreflightResult(
                "preflight_reject",
                "partial_module_structure",
                "partial_module_structure",
                str(partial["missing_elements"]),
            )

    # Gate 4: unprotected_writes.
    cert = certify_script_readonly(code, FAKE_API_INDEX, tree)
    if not cert["is_certified_readonly"]:
        return PreflightResult(
            "preflight_reject",
            "unprotected_writes",
            "unprotected_writes",
            str(cert["mutating_calls"] + cert["unprotected_liblcm_calls"]),
        )

    # Gate 5: casting_issues_detected.
    casting = detect_casting_needs(code, FAKE_API_INDEX.casting_index, tree)
    if casting["has_casting_issues"]:
        return PreflightResult(
            "preflight_reject",
            "casting_issues_detected",
            "casting_issues_detected",
            str(casting["casting_issues"]),
        )

    # Gate 6: api_discovery_required (WRITE runs only -- hard gate, no
    # auto-discovery exception; see module docstring re issues #47/#80 scope).
    # Mirrors the real gate exactly: it checks ONLY discovered_apis (populated
    # by search_by_capability), not validated_apis (populated by
    # get_object_api) -- corpus entries relying on discovery for a WRITE run
    # must populate session.discovered_apis, not just validated_apis.
    if write_enabled and len(session.discovered_apis) == 0:
        return PreflightResult(
            "preflight_reject", "api_discovery_required", "api_discovery_required"
        )

    # Gate 7: undiscovered_entity (per-entity gate). Simplified: any
    # undiscovered entity is a reject regardless of write_enabled (real
    # server offers a graceful read-only redirect instead -- out of scope
    # here, see module docstring).
    undiscovered = detect_undiscovered_entities(tree, session, FAKE_API_INDEX)
    if undiscovered["has_undiscovered"]:
        return PreflightResult(
            "preflight_reject",
            "undiscovered_entity",
            "undiscovered_entity",
            str(undiscovered["undiscovered"]),
        )

    # Gate 8: undefined_variables.
    undef = detect_undefined_variables(code, tree)
    if undef["has_undefined"]:
        return PreflightResult(
            "preflight_reject", "undefined_variables", "undefined_variables", str(undef["undefined_vars"])
        )

    # Gate 9: missing_imports.
    missing = detect_missing_operations_imports(code, api_mode)
    if missing["has_missing"]:
        return PreflightResult(
            "preflight_reject", "missing_imports", "missing_imports", str(missing["missing_imports"])
        )

    # Gate 10: wrong_library_imports.
    wrong = detect_wrong_library_imports(code, api_mode)
    if wrong["has_wrong_imports"]:
        return PreflightResult(
            "preflight_reject", "wrong_library_imports", "wrong_library_imports", str(wrong["wrong_imports"])
        )

    # Gate 11: invalid_api_chain.
    chain = detect_invalid_project_chains(tree, FAKE_API_INDEX)
    if chain["has_invalid"]:
        return PreflightResult(
            "preflight_reject", "invalid_api_chain", "invalid_api_chain", str(chain["issues"])
        )

    # Non-blocking advisory (getall-contract SPEC §6 Level 3): never rejects,
    # so it only runs once every reject-gate above has already passed --
    # mirrors execution.handle_run_module, which computes it right before
    # building the response `warnings` list.
    advisories = []
    getall_check = detect_getall_unsafe_idiom(tree, api_mode, FAKE_API_INDEX)
    if getall_check["has_unsafe_idiom"]:
        advisories.append("getall_unsafe_idiom")

    return PreflightResult("ok", None, None, advisories=advisories)
