# CP-B follow-through (B-5, B-6) -- programmer report

Commit: `d1f30da` on `feat/shared-mode-access` (not pushed).

## B-5: validate_only agreement

`_handle_validate_only`'s Gate 5 (`execution.py`) rejected on ANY casting
issue regardless of severity/write_enabled, disagreeing with
`handle_run_module`'s post-`b5f41d8` warning-tier read-only downgrade.
Fixed by extracting the severity check into one module-level function,
`_has_error_severity_casting_issue(issues)`, and calling it from BOTH
sites -- `handle_run_module`'s decision (previously an inline local var of
the same name) and Gate 5. Neither reimplements the severity logic; they
share it, so they cannot drift apart again. Gate 5 now computes
`_downgraded = (not write_enabled) and not _has_error`, sets
`passed=_downgraded`, and adds a `note` explaining the downgrade when it
applies. `issues` and `severity` are unchanged in the response either way
-- detection/reporting stays intact, only the verdict moves.

`validate_only` DOES receive the real `write_enabled` value: it was
already threaded as a parameter through `_handle_validate_only` ->
`_build_validate_only_checks` from the same tool-call args `run_module`
uses, so no default needed inventing.

## B-6: `_parents` binding

Verified line numbers by content (matched the report's ~3638-3672
description exactly; unchanged since cycle 3). Hoisted
`_parents: Dict[ast.AST, ast.AST] = {}` above `if cast_aliases:` in
`detect_casting_needs`; the block still only calls `_build_parent_map()`
when `cast_aliases` is non-empty (short-circuit comment/behavior
untouched). The second walk loop's read of `_parents` is now structurally
bound regardless of `cast_aliases`, not merely safe by correlating two
guards. Confirmed via a TARGETED pytest run first (per the cycle-3
stale-Pyright lesson), then re-ran `pyright` on both touched files: zero
`_parents`/possibly-unbound findings; 3 unrelated pre-existing errors
remain (env_info dict typing at `:1935`, `check_project_locked` import
fallback at `:4139-4140`), neither touched by this change.

## Fixture triage (`test_issue49_validate_only.py`)

| Case | Change | Reason |
|---|---|---|
| `test_multi_fault_reports_every_failure_no_short_circuit` | mocked casting issue gained `"severity": "error"` (was missing entirely) | Without it, `_has_error_severity_casting_issue` saw no error-tier issue and the new severity-aware gate downgraded it under `write_enabled=False`, breaking the no-short-circuit guarantee. Added the field to match real `detect_casting_needs` shape, preserving the original guarantee rather than flipping the assertion. |
| All 14 other existing cases | none | Not casting-mock-dependent, or already carried explicit severities. |

New cases added: `TestCastingGateAgreesWithRealGate` (4: readonly+warning
passes, write+warning still fails, readonly+error still fails,
readonly+mixed still fails) plus one end-to-end
`test_validate_only_agrees_with_run_module_on_readonly_warning_tier_casting`
running both `validate_only=True` and `False` through
`handle_run_module` with identical mocks and asserting agreement. In
`test_issue40_casting_severity.py`: `TestParentsBindingUnderEmptyCastAliases`
(2 cases) -- direct `_resolve_cast_type_at(node, {}, ...)` returns None,
and `detect_casting_needs` on a no-cast-alias multi-level attribute chain
completes cleanly.

## Suite

`python -m pytest -q`: **1107 passed, 4 skipped, 12 subtests** (baseline
1100 + 7 new tests). The known `test_flextools_health.py` mtime flake did
not manifest this run.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NfDCVuW6Sx7tTBeKr5Q2cU
