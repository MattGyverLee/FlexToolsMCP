# CP-B casting gate fix -- programmer report

Commit: `b5f41d8` on `feat/shared-mode-access` (not pushed).

## Files + lines changed

- `validators.py`: new branch-aware resolver block after
  `_find_cast_alias_property_writes` (`_direct_cast_call_interface`,
  `_scan_backward_for_cast`, `_find_enclosing_stmt_list`, `_build_parent_map`,
  `_resolve_cast_type_at`, ~140 lines). Wired into
  `detect_interface_attribute_typos` and into `detect_casting_needs` (AST
  alias-tracking + `typed_chain_segments` + the regex advanced
  `casting_index` loop, via new `line_var_cast_types` map replacing flat
  `cast_aliases.get(obj_var)`).
- `execution.py`, `handle_run_module` casting decision (was `:2858`): added
  `_has_error_severity_casting_issue`; downgrade branch sets
  `_casting_readonly_warnings` + records a success signal; unchanged reject
  logic moved into `else:`. New `warnings`-list entry surfaces downgraded
  issues.
- `tests/evals/preflight_runner.py`: Gate 5 mirrors the same check.
- `docs/TOOL-CONTRACT.md`: new "Read-only casting severity downgrade"
  section + updated row.
- New: `tests/test_issue40_casting_severity.py`,
  `tests/evals/corpus/issue40_warning_tier_readonly_proceeds.yaml`.

## Gate-locality proof

The downgrade lives entirely inside `handle_run_module`'s
`if casting_check["has_casting_issues"]:` block. `write_enabled` is read
identically everywhere else pre/post diff -- `unprotected_writes`
(`certify_script_readonly`), `hvo_literal_write_risk`, `nested_unit_of_work`
untouched. `_resolve_alias_maps` (used by mutation detection and
`detect_hvo_literal_args`) is untouched; the branch-aware resolver is a
PARALLEL function, only rewired at two casting-gate call sites.

## Branch/assignment-aware typing

`_resolve_cast_type_at` walks outward through enclosing
`body`/`orelse`/`finalbody` lists, scanning backward for the nearest
assignment; each if/elif/else arm lives in its own list so a sibling arm's
cast is structurally invisible. Chained rebinds (`b = a`) resolve
recursively at the rebind's own position. Verified against #97 Bug 2's
verbatim 4-branch MSA repro: 0 false positives (vs. 4/4 false positives
with the fix reverted). Pre-existing chained-rebind/wrong-cast/typed-chain
tests in `test_issue40_casting_whitelist.py` / `test_validator_casting_chains.py`
pass unchanged.

## Per-fixture table

| Fixture/test | Change | Tier | Reason |
|---|---|---|---|
| `06_reject_casting_issues_headword.yaml` | none | error | `.Owner.HeadWord` is `KNOWN_CASTING_PATTERNS`. |
| `20_reject_casting_lexeme_form_no_cast.yaml` | none | error | `LexemeForm` is `KNOWN_CASTING_PATTERNS`. |
| `issue15_cast_alias_satisfies_chain.yaml` | none | n/a | No issue produced (`_alias_satisfies` short-circuits). |
| `issue30_receiver_suffix_naming_skip.yaml` | none | skip:true | About rewrite content, not gate decision. |
| `issue40_cast_alias_category_not_reflagged.yaml` | none | n/a | No issue produced. |
| `issue40_operations_alias_arg_not_flagged.yaml` | none | n/a | No issue produced. |
| `issue40_negative_control_uncast_category_rejected.yaml` | `write_enabled: false->true`, notes updated | warning | Only issue is warning-tier -> read-only would now proceed. Flipped the SCENARIO, not the outcome, so it still proves detection stays active AND write-runs still reject every severity. |
| `issue40_warning_tier_readonly_proceeds.yaml` (new) | added | warning | Covers the new read-only "ok"-with-advisory path. |
| `test_partial_auto_fix_reports_only_residual_casting_issue` | none | mixed | First-call issues include an "error" one, so the (single, pre-auto-fix) downgrade check takes the unchanged `else` branch; auto-fix's own residual-reject contract deliberately untouched. |
| `test_response_contract.py`, `test_diagnostic_report_foundation.py`, golden JSONs, `make_golden.py` | none | n/a | Pure model/telemetry-signature tests, never call `handle_run_module`. |

## Retry-loop interaction

Downgrade path calls `session_state.record_op_signal(error_code=None, ...)`,
matching that function's own documented contract ("On success: pass
error_code=None ... acts as a reset"). `test_retry_loop_detection.py`
drives `SessionState` directly, never `execution.py` -- no changes needed,
still passes.

## Suite

`python -m pytest -q`: **1100 passed, 4 skipped, 12 subtests passed.**
`test_flextools_health.py::...test_new_exact_file_visible_after_write`
failed once in ~5 runs (standalone AND full-suite), passed on immediate
rerun both times -- genuinely flaky (mtime race), unrelated (versioning
cache test, no casting/validators/execution.py involvement). Unlike last
cycle it DID manifest -- confirmed-flaky now, not unconfirmed.

## Out of scope, noted not fixed

`_handle_validate_only`'s casting check (`:1771`, unrelated line) still
reports `passed: False` for ANY issue regardless of severity/write_enabled
-- no longer matches what a real read-only `run_module` call would do
post-B-1. Not touched: separate report-only function outside the CP-B
ruling, needs its own fixture triage in `test_issue49_validate_only.py`.
