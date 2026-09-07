# Cycle 5 -- P1-1/P1-2 candidate-union fix (programmer report)

Commit: `a1f6897` on `feat/shared-mode-access` (not pushed; message deliberately
does not carry `closes #N` -- #97 Bug 1/B-3 stays open per the campaign file).

## Candidate map -- built locally, `_resolve_alias_maps` untouched

`_build_cast_candidate_set(tree)` (`validators.py`, new, placed right after
`_resolve_cast_type_at`) does its own flat `ast.walk`, matching only direct
`Name = I<Concrete>(...)` assigns. It is called from two places only:
`detect_interface_attribute_typos` (local var `candidates`) and
`detect_casting_needs` (local var `_candidates`, hoisted outside
`if cast_aliases:` for the same B-6 structural reason `_parents` already was).
`git diff` on `_resolve_alias_maps` itself: empty -- confirmed with
`git diff a1f6897^ a1f6897 -- src/flextoolsmcp/server/validators.py | grep -c _resolve_alias_maps`
showing only pre-existing call sites, no new callers, no signature change.

## Did NOT add `ast.If` to `_CAST_SCAN_RECURSE_INTO`

`_CAST_SCAN_RECURSE_INTO = (ast.Try, ast.With)` is unchanged (`validators.py`).
The only edit near it adds an `ExceptHandler`-body loop inside
`_scan_backward_for_cast`'s existing `if isinstance(stmt, _CAST_SCAN_RECURSE_INTO):`
block -- `ast.If` itself is never touched.

## P1-1 shapes -- before/after

Pre-fix (per QC/main-session repro): if-used-after / try-used-in-except /
for-used-after all `has_typos: False` (regression); control `True`.
Post-fix, verified both by a standalone script and by
`tests/test_issue40_casting_severity.py::TestP1_1CandidateUnionFallback`:
all four now `has_typos: True`. QC's P2-1 casting-gate false positives
(if-both-arms-used-after, for-used-after-loop) verified suppressed
(`casting_issues == []`) via the same union mechanism, both by a script and
by two new tests in the same class.

## Bug 2 control

`TestBranchAwareVariableTyping::test_issue97_bug2_if_elif_branches_no_false_positive`
(pre-existing, unmodified) still passes. Added a second, prominently-named
`test_PROMINENT_bug2_msa_repro_still_zero_false_positives_after_p1_fix` that
re-runs the verbatim 4-branch MSA repro through BOTH
`detect_interface_attribute_typos` and `detect_casting_needs` -- `0/4` false
positives in both.

## Shared pipeline: `_compute_casting_decision`

`src/flextoolsmcp/server/handlers/execution.py`, defined right after
`_has_error_severity_casting_issue`. Runs `detect_casting_needs`, merges
`detect_interface_attribute_typos`, forces `severity="error"` on a typo hit,
and stamps `has_error_severity`. Three call sites, all updated:
1. `handle_run_module` (`execution.py`, casting block) -- replaced the
   inline `detect_casting_needs` + typo-merge with one call.
2. `_build_validate_only_checks` Gate 5 (`execution.py:~1828`) -- same call,
   using `casting_check["has_error_severity"]` instead of re-deriving it.
3. `tests/evals/preflight_runner.py` Gate 5 -- imports
   `_compute_casting_decision` directly from `server.handlers.execution` and
   calls it with `FAKE_API_INDEX` as `api_idx`.

## Monkeypatched agreement test

`tests/test_issue49_validate_only.py::test_validate_only_agrees_with_run_module_on_readonly_warning_tier_casting`
previously monkeypatched both `detect_casting_needs` AND
`detect_interface_attribute_typos` to fixed returns. Rewrote it to use a
real-shaped `_RealCastingFakeIndex` (real `liblcm`/`casting_index`) with
NEITHER detector monkeypatched. Added a new
`test_validate_only_agrees_with_run_module_on_readonly_typo_class` (also real
detection) that reproduces P1-2 exactly (`ILexDb.EntriesOC`) and asserts
`run_module` rejects AND `validate_only` reports `validation_failed` with
`casting.passed == False` -- this test fails against the pre-fix code (proved
manually before the execution.py edit) and passes after.

## Per-fixture table

No existing fixture's expected outcome changed. `issue40_negative_control_*`,
`issue40_warning_tier_readonly_proceeds.yaml`, and the rest of the corpus
don't exercise a branch/try/for cast-alias shape (their receivers are either
uncast `for`-loop vars or flat single casts), so none touch the fallback
path -- confirmed by an unchanged eval-corpus pass count.

| File | Change | Reason |
|---|---|---|
| `tests/test_issue40_casting_severity.py` | +2 fixtures (`FakeILexDbIndex`), +2 test classes | New P1-1/P2-1 regression coverage; no existing test's assertion flipped |
| `tests/test_issue49_validate_only.py` | 1 test rewritten (real detection), 1 new test | Rewrite is the "stop stubbing the component under test" fix; new test locks P1-2 |
| `tests/evals/corpus/*.yaml` | none | No fallback path exercised by any existing entry |

## Suite / corpus

`python -m pytest -q`: **1115 passed, 4 skipped, 12 subtests** (baseline 1107
+ 8 new tests; no mtime flake this run). `tests/evals/test_corpus.py`:
**34 passed, 2 skipped** (unchanged from baseline).
