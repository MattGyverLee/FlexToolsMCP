# Live verification -- issue #223

**Project:** IndonesianHC-Complete (live FieldWorks 9.3.11) | also Sena 3 (negative case, not re-run here)
**Command:** `.venv/Scripts/python.exe -m pytest tests/test_parse_live.py -q -m requires_flex`
**run_mode:** live (real SIL.LCModel / pythonnet, real .fwdata)
**Date:** 2026-09-24

## Claim under test
Idle parse worker releases `<project>.fwdata.lock` immediately after results
are returned (`_release_if_idle`); a following request reopens and still
parses correctly with caches invalidated; no lexicon writes/re-saves occur.

## Live check: direct lock/mtime probe (custom script, both try_word calls
through the real `ParseRunner`/`handle_flextools_try_word`)
```
BEFORE:            lock exists: False   fwdata mtime: 1722320572.0
CALL1 (cold, HC):  status ok, elapsed 3.343s
AFTER CALL1:       lock exists: True
AFTER CALL1 +1s:   lock exists: False   <- released while worker idle
fwdata mtime:      unchanged (no re-save)
CALL2 (warm-ish):  status ok, elapsed 0.801s, parsed correctly
AFTER CALL2:       lock exists: True
fwdata mtime:      still unchanged from BEFORE
AFTER TEARDOWN:    lock exists: False
```
Confirms: lock is released on idle, a second request reopens and parses
correctly, and no write/re-save touches the `.fwdata` mtime.

## `tests/test_parse_live.py -m requires_flex` (unmodified by this PR)
**Fix branch (fca894e):** 23 passed, **3 failed**:
- `test_scenario_1_a_second_call_does_not_reload_the_grammar` -- FAIL:
  "the second call re-entered loading_grammar ... the grammar is supposed
  to be held between calls (FR-042)"
- `test_fr043_currency_is_confirmed_before_every_reuse` -- FAIL: "an
  unchanged model triggered a reload"
- `test_scenario_6_cancel_stops_at_a_boundary_and_keeps_what_finished` --
  FAIL: 10 words completed but only 9 readable on disk

**Baseline (`origin/main`, same venv, same live project, verified via a
second worktree):** all 3 of the above **pass**.

Root cause: `_release_if_idle` drops the project between requests, and
`_ensure_project_open`'s reopen forces `ParserOperations` to rebuild the
grammar every time (`_parser_cache is not cache`) -- even when nothing
changed. This directly contradicts FR-042/043's "grammar stays held,
reload only when stale" guarantee, which `test_parse_live.py` already
enforces live. Reproduced deterministically twice on the fix branch,
absent on baseline.

## Cleanup
Temp `origin/main` worktree removed (`git worktree remove --force`).
No lexicon writes; `.fwdata` mtime unchanged throughout. Scratch run-record
dir under Temp, not inside the FieldWorks project folder.

## Result
[FAIL] -- lock-release requirement (item 1) is genuinely live-verified and
works, but the chosen implementation (reopen-on-demand) breaks an existing,
live-tested spec guarantee (FR-042/043: grammar held between calls, no
reload). Not flagged as a known regression by the programmer's Cycle 1b
notes (framed as a positive self-healing property, not a broken invariant).
