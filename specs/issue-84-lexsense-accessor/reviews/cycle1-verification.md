# Cycle 1 Verification -- Issue #84 (`project.LexSense` / `project.PhonologicalRule`)

## 1. Sweep completeness -- PASS (with one caveat)

Grep of the whole repo for `project.LexSense`/`project.PhonologicalRule` (regex, incl. strings/JSON/MD) found no bad-idiom **usage as correct/blessed code** outside:
- The 12 in-scope files (fixed) and the NEW `tests/test_issue84_project_lexsense_accessor.py` (24 tests, as claimed).
- `src/flextoolsmcp/server/constants.py:77-78`, `validators.py:565-566,970,1160`, `diagnostic/sensitivity.py:44` -- all **comments** documenting the fix/detection shape, not the bug.
- Pre-existing, unrelated test fixtures (`test_auto_fix.py`, `test_diagnostic_report_demo.py`, `test_diagnostic_report_transport.py`, `test_issue80_graceful_redirect.py`, `test_script_certification.py`, `test_validator_cluster_fixes.py`) that use `project.LexSense` deliberately as *invalid-input* fixtures for unrelated subsystems (typo-fix, redirect suggestions, readonly certification, casting gate). No fix needed.
- `src/flextoolsmcp/index/archive/common_patterns_flexicon-v4.2.1.json` -- 8 hits, deliberately frozen, as noted.

**Caveat:** `server/versioning.py::find_versioned_api_file()` falls back to `index/*/archive/` on an **exact version match** (lines 370-378), and `find_api_files()` includes archive by default (`include_archive=True`). So archived snapshots are **not purely historical** -- if a user's installed Flexicon pins to 4.2.1 (or any archived version), the server will serve that archived (buggy) `common_patterns` file live. Leaving it frozen is safe today (current default is 4.3.0) but is a live latent hazard for pinned-older installs; worth a follow-up issue.

## 2. Test suite -- PASS, but with an environment-integrity flag

First clean `python -m pytest -q` run: **909 passed, 2 skipped** (911 collected). `git diff --stat tests/` is empty -- **no pre-existing tracked test file was modified**, confirmed. 909 total includes the unrelated `test_workspace_check.py` (34 passing, pre-existing dirty work, not part of #84). 909 - 34 = 875, i.e. author's "876 up from 852" claim is directionally consistent (852 baseline + 24 new issue-84 tests) modulo rounding I couldn't independently reproduce to the exact digit.

**Flag:** a second full run, and an isolated run of `tests/test_issue85_navigation_path.py`, produced `FAILED ...test_known_good_query_resolves_post_fix` plus a *growing* collected-test count (911 -> 915) and **new untracked files appearing mid-session** (`tests/test_issue85_navigation_path.py`, `scripts/check_project_accessors.py`, `specs/inheritance-resolution/`, modified `server/handlers/discovery.py`) that were absent from the task's file inventory and from git status at session start. This strongly indicates **concurrent, unrelated work-in-progress (issue #85) landing in this same working tree during verification**, not a regression caused by the #84 sweep. The #84-scoped files and #84 tests are unaffected by this failure. Recommend re-running the suite once the tree is quiescent before treating any run's exact pass count as final.

## 3. Generated artifact -- PASS (regenerable; string-patch was avoidable)

`common_patterns_flexicon-v4.3.0.json` parses as valid JSON; `git diff` shows exactly 10 clean substitutions of `project.LexSense.X` -> `project.Senses.X`/`project.LexEntry.X` inside `"code"` strings, no structural corruption. **It IS regenerable headlessly**: `refresh.py`'s post-process step (`run_postprocess_patterns` -> `extract_patterns.py --update-flexlibs`) imports `CURATED_RECIPES` directly from the now-fixed `curated_recipes.py` and needs only `pyflexicon` importable -- no FieldWorks/pythonnet. The manual patch works but risked divergence from the generator; re-running refresh would have been safer and is a good follow-up.

## 4. Commit scoping -- PASS, in-scope/out-of-scope disjoint

`CLAUDE.md` diff confirmed clean (2 sites, only #84 content). `CHANGELOG.md` diff (46 lines) is 100% the unrelated `workspace_notice` feature -- no #84 content, confirming item 5.

Exact `git add` list for an #84-only commit:
```
git add CLAUDE.md \
  src/flextoolsmcp/templates/2-flexicon-template.py \
  src/flextoolsmcp/curated_recipes.py \
  src/flextoolsmcp/server/worked_examples.py \
  src/flextoolsmcp/templates/00-FLAVOR-GUIDE.md \
  docs/CASTING_SYSTEM.md docs/DIAGNOSTIC-REPORT-DEMO.md \
  docs/FLEXTOOLS-STYLE-GUIDE.md docs/LIBLCM_CONTEXTUAL_ANALYSIS.md \
  src/flextoolsmcp/index/common_patterns_flexicon-v4.3.0.json \
  src/flextoolsmcp/server/constants.py src/flextoolsmcp/server/validators.py \
  tests/test_issue84_project_lexsense_accessor.py
```
**Do NOT** `git add -A`/`.`: current `git status` also shows `discovery.py`, `scripts/check_project_accessors.py`, `specs/inheritance-resolution/`, `tests/test_issue85_navigation_path.py` -- none were in the task's inventory; they appear to be concurrent unrelated work and must be excluded pending review.

## 5. CHANGELOG entry -- CONFIRMED OUTSTANDING
No #84 entry exists under `## [Unreleased]`; only the unrelated workspace-notice entry. Still needs to be written before release.
