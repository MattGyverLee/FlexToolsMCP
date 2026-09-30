# Cycle 3 - lex-programmer report

## Scope

CP1 (Foundation) close-out: fix the one remaining P1 in
`src/flextoolsmcp/server/diagnostic/offered_store.py` -- `save_store()`'s
unguarded `path_fn()` call could let a `RuntimeError` from the default
`default_store_path -> get_reports_dir -> Path.home()` chain escape into
the op path, violating the module's fail-open contract. No other
diagnostic-report code was touched. The unrelated working-tree changes in
`src/flextoolsmcp/server/validators.py` and
`tests/test_validator_cluster_fixes.py` were left untouched (verified via
`git status`/`git diff --stat` before and after -- no changes made by me
to either file).

## Fix (file:line)

`src/flextoolsmcp/server/diagnostic/offered_store.py:100-121` (function
`save_store`):

- Split the single `try/except OSError` that wrapped `path_fn()` +
  mkdir/open/dump into two guarded steps, mirroring `load_store()`
  (lines 76-79):
  1. `path = path_fn()` now has its own `try: ... except Exception: return`
     -- swallows *any* exception (including `RuntimeError` from
     `Path.home()`) and returns early, best-effort/silent.
  2. The mkdir/open/`json.dump` body keeps its own `try: ... except OSError:
     pass`, unchanged in scope/behavior from before.
- Updated the docstring: dropped the now-inaccurate "mirrors
  op_telemetry's `_write_jsonl_line` convention" line (that convention
  only ever handled `OSError`) and added a paragraph explaining why
  `path_fn()` needs its own broader guard, referencing `load_store()`'s
  equivalent step for symmetry.

No other lines in the file were touched. `prune`, `get_entry`,
`should_offer`, `record_offer`, `record_decision` are unchanged.

## New test

`tests/test_diagnostic_report_foundation.py` --
`test_save_store_path_fn_runtime_error_fails_open` (inserted before
`test_prune_caps_entries_by_lru_last_seen`, after
`test_missing_offered_json_is_treated_as_empty`).

Injects a `path_fn` that unconditionally raises `RuntimeError` and
asserts:
- `offered_store.save_store(...)` returns without raising.
- `offered_store.record_offer(...)` (which calls `save_store()`
  unconditionally) also returns without raising, and still returns the
  upserted in-memory entry dict (`state == STATE_OFFERED`) even though
  the disk write was skipped.

This closes Verification's cycle-2 P2 note #1 (no automated test for
this fail-open path).

## Test results

```
python -m pytest tests/test_diagnostic_report_foundation.py -q
37 passed in 1.98s

python -m pytest tests -q
487 passed in 47.36s
```

Both counts match the expected targets (37 foundation, 487 full suite).

## Verification of scope isolation

`git status` / `git diff --stat` confirm `src/flextoolsmcp/server/validators.py`
and `tests/test_validator_cluster_fixes.py` retain exactly the same
pre-existing diff they had before this task started -- I made no edits to
either file.
