# Project Status

Active feature: **diagnostic-report** ("send this to the maintainer" flow).
Spec: `specs/diagnostic-report/SPEC.md` (APPROVED-WITH-EDITS).
Checkpoint plan: `specs/diagnostic-report/tasks.md`.

## Where we are

**CP1 -- Foundation: COMPLETE and green (2026-07-13).** All six checklist items
landed; both cycle-2 P1s resolved (`save_store` fail-open fixed in cycle 3;
casting-recurrence heuristic deferred into CP2 and now closed there). See
`specs/diagnostic-report/tasks.md` CP1 checkpoint for detail.

**CP2 -- Reconstruction + normalization: COMPLETE and green (2026-07-13, spurt 2,
cycles 4-6).**

All six CP2 line-items landed: slice reconstruction, rotation stitching,
`MAX_REPORT_OPS` summarize-not-drop, path-scoped machine-hygiene normalization,
report rendering, and casting-recurrence signature precision. Gate results:

- **Verification PASS.** Full suite **511 passed / 0 failed** (+1 from the 510
  baseline, no regressions). All six spec section-12 Reconstruction clauses are
  test-backed; zero forbidden imports.
- **Domain E2 privacy gate PASS** -- home-dir / OS-username substitution is
  anchored on path-shaped tokens only, never a document-wide username
  find/replace.
- **Cycle-2 casting-recurrence P1 CLOSED** -- real `casting_signature` threaded
  into the JSONL schema; recurrence keys on it, not the bare code.
- **Cycle-6 post-auto-fix stale-`issues` P1 FIXED + verified.** Cycle 5 found
  that `handlers/execution.py` left `issues` bound to the pre-auto-fix casting
  set after the Issue #46 auto-fix reran `detect_casting_needs`, so a partial
  auto-fix reported the stale (resolved+residual) set instead of only the
  residual issue. Fixed by re-deriving `issues` right after the post-fix
  `casting_check` reassignment; regression test
  `test_partial_auto_fix_reports_only_residual_casting_issue` confirmed failing
  pre-fix and passing post-fix. See `reviews/cycle5-*` and `reviews/cycle6-*`.

**CP2 carryover (P2, non-blocking):** two P2s deferred to harden during CP3 --
`reconstruct.py` mismatched-`End` silent truncation, and `render.py`
`_CODE_STOP_MARKERS` substring false-positive.

**CP3 -- Surface + transport + guard: CODE COMPLETE and green, but NOT called
done -- blocked on one human decision (2026-07-13, spurt 3, cycles 7-8).**

All five CP3 line-items landed and are green: `flextools_prepare_report` tool,
the `diagnostic_report` advisory block on `RunModuleSuccess`, the three
transports (`gh` CLI / prefilled issue URL / `mailto:`), the
`likely_contains_lexical_data` code-shape flag, and the two-layer
no-transmission guard. Cycle-8 gates:

- **Verification PASS.** Full suite **577 passed / 0 failed** (511 + 66 new,
  matches exactly, no regressions). Two-layer no-transmission guard confirmed
  (static AST ban unconditional across all socket import styles; dynamic layer
  drives all three transports with zero invocations, exactly one write each).
- **QC 92/100 APPROVE, 0 P0 / 0 P1.** Fail-open contract on
  `build_advisory_for_success_close` verified total. Five P2s recorded as CP3
  carryover in `tasks.md`.
- **Domain 4/5 PASS.** Items 1-4 pass (sensitivity-by-shape, path-scoped
  normalization, structural never-auto-send, preview fidelity).

## Next pickup -- HUMAN DECISION REQUIRED before CP3 closes

**Domain item 5 FAIL (not a code defect -- a scope decision inside Q5).** The
`diagnostic_report` auto-offer attaches only at a same-turn `ok` (success)
close, never at the failing/reject close. So a turn that fails reportably (§6.1)
then is **abandoned** (no same-turn `ok` close) never surfaces an automatic
offer -- the canonical unreported-inconsistency case from §1. The bundle content
already handles abandonment; only the surface can't reach it automatically.
This is an implicit consequence of maintainer-resolved Q5 (advisory on
`RunModuleSuccess` only), so the fix reopens/extends a maintainer-resolved spec
question on the feature's central motivation -- a product call, not a lead call.

Pick one (full detail + file refs in `tasks.md` CP3 BLOCKER):
  - (a) also attach a best-effort/fail-open/non-contract advisory on the failing
    response (shifts trigger timing vs §6.2/§6.3; adds an off-contract surface);
  - (b) add a `flextools_start` preceding-turn lookback (new mechanism, needs
    spec + design);
  - (c) accept as a documented v1 limitation and rely on the explicit
    `flextools_prepare_report` tool as the recovery path (update SPEC.md
    §6.5/§10 + `tasks.md`).

Once decided: if (a)/(b), run a cycle-9 fix + re-verify, then close CP3 and move
to CP4 (docs + demo). If (c), document and close CP3, move to CP4. The five QC
P2s + one domain P2 (`_short_body_text` un-normalized `report_path`) are
non-blocking carryover for CP4 or a follow-up -- see `tasks.md`.

## Housekeeping note (not part of diagnostic-report)

The working tree carries unrelated pre-existing changes to
`src/flextoolsmcp/server/validators.py` and
`tests/test_validator_cluster_fixes.py`. These are NOT part of the
diagnostic-report feature -- do not sweep them into a diagnostic-report commit;
commit or revert them deliberately on their own.
