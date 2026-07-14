# Cycle 6 - Programmer report (CP2 P1 fix)

## Bug fixed

`src/flextoolsmcp/server/handlers/execution.py`, `handle_run_module`: `issues`
was bound to the pre-auto-fix `casting_check["casting_issues"]` at line 2077
and never re-derived after the Issue #46 auto-fix reran `detect_casting_needs`
on the patched code (line 2108). When auto-fix resolved SOME-but-not-all
casting issues, the still-has-issues rejection branch (signature computation,
per-issue enrichment, `how_to_fix`, and the `error_response` payload) reported
the stale pre-fix issue set instead of only the residual ones.

**Fix:** added `issues = casting_check["casting_issues"]` immediately after
the `casting_check` reassignment at line 2108, inside the
`if _validate_patched_code(...)` success branch only (the failure/fallback
branch at 2112-2115 never reassigns `casting_check`, so it correctly keeps
using the original pre-fix `issues` there -- verified this scope is correct
by tracing both branches).

## Regression test

`tests/test_diagnostic_report_reconstruction.py`:
`test_partial_auto_fix_reports_only_residual_casting_issue` (plus helper
`_stub_execution_preflight`). Monkeypatches `detect_casting_needs`,
`_try_auto_fix_casting`, and `_validate_patched_code` to simulate a two-issue
submission (Gloss, fixable; Definition, residual) where auto-fix resolves
only Gloss. Asserts (a) the `error_response` `casting_issues` payload lists
only `Definition`, not `Gloss`; (b) the JSONL `casting_signature` matches
`compute_casting_signature([residual_issue])`, not the stale two-issue
signature. Verified the test fails against the pre-fix code (via `git stash`)
and passes after the fix.

## Doc correction (item 3)

`specs/diagnostic-report/reviews/cycle4-lex-programmer.md`: corrected the
"only one new import, never diagnostic->handlers" line -- `reconstruct.py:43`
does add a second cross-package import (`handlers.op_telemetry.
group_records_by_intent`, `diagnostic -> handlers`), pure-function/no I/O, per
`cycle5-lex-verification.md`'s discrepancy note. Text-only change.

## Scope

Did not touch `server/validators.py`, `tests/test_validator_cluster_fixes.py`,
`reconstruct.py:280-288`, or `render.py:43-50` (deferred P2s, out of scope).

## Test result

`python -m pytest tests/test_diagnostic_report_reconstruction.py tests/test_diagnostic_report_foundation.py -q`
-> **61 passed**.
