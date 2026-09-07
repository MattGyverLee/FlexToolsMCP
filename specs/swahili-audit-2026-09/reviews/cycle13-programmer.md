# Cycle 13 - Programmer report: PR #114 CI fix

## Repro (Step 1)
Wrote a shadow `flexicon.py` (`raise Exception("64bit FieldWorks 9 not found")`)
into a scratchpad dir, put it first on PYTHONPATH, ran the target file with no
`-m`:
```
PYTHONPATH="$SHADOW_DIR" python -m pytest tests/test_issue84_project_lexsense_accessor.py -v
```
Result: `5 failed, 56 passed` -- the exact 5 tests named in the problem
statement, each with `E   Exception: 64bit FieldWorks 9 not found` escaping
`pytest.importorskip`. Reproduced (CI reports these as ERROR; locally they
surface as FAILED since the raise happens in the test body, not a fixture --
same underlying defect).

## Fix (Step 2)
`tests/test_issue84_project_lexsense_accessor.py` only:
- Added `_require_live_flexicon()` helper (catches bare `Exception`,
  `pytest.skip(...)` with the message; `# noqa` on the except line since the
  broad catch is deliberate).
- Marked `TestTemplateImportsResolve` and `TestAliasTableMatchesLiveInstall`
  with `@pytest.mark.requires_flex` (marker already registered in
  pytest.ini:8).
- Replaced all 3 `pytest.importorskip("flexicon", ...)` calls with
  `_require_live_flexicon()`.
- Added docstring note on `TestAliasTableMatchesLiveInstall` explaining it
  has errored on every Windows CI run since the runtime dep landed, so drift
  protection lives in `scripts/check_project_accessors.py` / local
  `-m requires_flex` runs, not CI.

## Verification (Step 3)
a) No `-m`: `61 passed` (56 pure + 5 requires_flex; FieldWorks present here).
b) `-m "not requires_flex"`: `56 passed, 5 deselected`.
c) `-m requires_flex`: `5 passed, 56 deselected`.
d) Shadow-flexicon repro re-run, no `-m`: `56 passed, 5 skipped` -- 0 errors.
   Load-bearing proof CI is fixed.
e) Full suite `pytest -q`: `2 failed, 1136 passed, 4 skipped, 12 subtests
   passed`. The 2 failures are in `tests/test_issue100_access_path.py`
   (`TestRealIndexPreRefreshState`), unrelated to this file/fix -- confirmed
   pre-existing by restoring `src/flextoolsmcp/index/` to HEAD via
   `git checkout --` and rerunning: identical 2 failures both before and
   after my edit (the checked-in v4.4.1 index already carries `access_path`
   for `MSAOperations`, so that test's premise is stale independent of this
   change). No new failures introduced; the 5 target tests skip cleanly.
f) `ruff check .`: All checks passed. `python scripts/validate_integrity.py
   all`: all 5 phases passed (flexicon 4.5.2 runtime contract OK).

## Commit
`7a75232` "test: skip live-flexicon checks without FieldWorks (pre-existing
main CI failure)" -- 1 file changed
(`tests/test_issue84_project_lexsense_accessor.py`), 33 insertions(+), 8
deletions(-). No close/fix/resolve+#N keyword. Not pushed.

`git status --short` after commit:
```
?? src/flextoolsmcp/index/common_patterns_flexicon-v4.5.2.json
?? src/flextoolsmcp/index/python/flexicon_api_v4.5.2.json
?? src/flextoolsmcp/index/python/flexicon_lcm_bridge_v4.5.2.json
```
(pre-existing untracked v4.5.2 artifacts only, unrelated and untouched; index
dir clean/tracked, nothing staged from it.)
