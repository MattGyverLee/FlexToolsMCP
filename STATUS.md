# Project Status

Active feature: **diagnostic-report** ("send this to the maintainer" flow).
Spec: `specs/diagnostic-report/SPEC.md` (APPROVED-WITH-EDITS).
Checkpoint plan: `specs/diagnostic-report/tasks.md`.

## Where we are

**CP1 -- Foundation: COMPLETE and green (2026-07-13).**

All six CP1 checklist items landed: `user_request` plumbing, trigger predicate,
inferred-workaround signal, code-independent signature, `offered.json` store,
and unit tests. Verification returned PASS (0 P0, 0 P1); QC scored 89/100 and
surfaced two P1s. Both are now resolved:

1. **`save_store` fail-open P1 -- FIXED (cycle 3).** `save_store()`'s `path_fn()`
   call was inside the `except OSError` block, so a `RuntimeError` from the
   default `Path.home()` chain could escape and crash the op path, violating the
   module's fail-open contract. The fix pulls `path_fn()` into its own
   `try/except Exception: return` step, mirroring `load_store()`. Added a
   regression test (`test_save_store_path_fn_runtime_error_fails_open`) injecting
   a `RuntimeError`-raising `path_fn` and asserting both `save_store` and
   `record_offer` return without raising. See
   `specs/diagnostic-report/reviews/cycle3-lex-programmer.md`.

2. **Casting-recurrence heuristic P1 -- DEFERRED to CP2 as a line-item.** The v1
   fallback in `triggers.py:62-77` collapses two unrelated same-turn casting
   issues into one "recurrence." Safe-by-construction for CP1 (only widens the
   offer surface). Now a tracked CP2 task: thread the real `casting_signature`
   into the JSONL schema and key recurrence on it.

Test state: 37/37 foundation tests green; full suite 487 tests green.

## Next pickup

**CP2 -- Reconstruction + normalization.** First task: slice reconstruction --
join `operations.jsonl` lines to session-log `=== Operation #N Start/End
(op_id) ===` blocks by `op_id`/`seq` (spec sections 3, 5). CP2 also carries the
deferred casting-recurrence signature-precision fix. See `tasks.md` CP2 section.

## Housekeeping note (not part of diagnostic-report)

The working tree carries unrelated pre-existing changes to
`src/flextoolsmcp/server/validators.py` and
`tests/test_validator_cluster_fixes.py`. These are NOT part of the
diagnostic-report feature -- do not sweep them into a diagnostic-report commit;
commit or revert them deliberately on their own.
