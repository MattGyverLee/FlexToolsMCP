# Cycle-6 verification -- commit 1e30148

**Verdict: PASS** (with one accurate flake correction, no functional regressions found)

## Suite / corpus
- `python -m pytest -q`: **1120 passed, 1 failed, 4 skipped, 12 subtests** (41.88s).
  The 1 failure is `TestFileDiscoveryCacheInvalidation::test_new_exact_file_visible_after_write`
  (mtime-cache race, see #11). Not a regression from 1e30148 -- reran the same
  class 20x in isolation and it fails there too (see below).
- Eval corpus: `pytest tests/evals/test_corpus.py -q` -> **35 passed, 2 skipped**. Matches programmer's claim.

## (a)-(e), independently reproduced against the REAL liblcm/flexicon index
(`APIIndex.load(get_index_dir())`; `detect_casting_needs` called with
`idx.casting_index`, `detect_interface_attribute_typos` with `idx`.)
- (a) `def a(p): obj=IMoStemMsa(p); obj.Hvo` / `def b(obj): obj.AddComponent`
  -> `has_typos=False`. Matches.
- (b) `def a(x): obj=IWfiAnalysis(x); obj.CategoryRA` / `def b(obj): obj.CategoryRA`
  -> `has_casting_issues=True`, `CategoryRA` flagged, `cast_interface=IWfiAnalysis`. Matches (my first attempt passed the wrong 2nd arg to `detect_casting_needs`, giving a spurious False -- corrected and reran).
- (c) bare snippet `d=ILexDb(project)\nx=d.EntriesOC` -> `has_typos=True`. Tested 5 variants (plain, report.Info wrapper, code before the cast, blank lines between cast and use, cast inside module-level if/else) -- **all 5 detected**.
- (d) P1-1 matrix, real index, typo class (`ILexDb.EntriesOC`) inside if/try/for/flat -> **4/4 `has_typos=True`**.
- (e) #97 Bug2 verbatim 4-branch MSA repro -> both detectors `False`/`0 issues`. 0/2 false positives (real-index run; used the exact code from the test file).

## Check 5 -- RED/GREEN, done myself (monkeypatch, not the test file)
`preflight_runner.FAKE_API_INDEX.liblcm = {"entities": {}}` -> `run_preflight_chain(issue39 entry)` = **`ok, None`** (RED, matches pre-fix). Restored -> **`preflight_reject, casting_issues_detected`** (GREEN). Coverage is real, not illusory.

## Check 6 -- four quadrants through `handle_run_module` (real gate code, real index; only `certify_script_readonly`/subprocess/logger stubbed)
1. read-only + warning (`return wa.CategoryRA`, no cast) -> **RUNS**, advisory in `warnings`.
2. read-only + error (`entry.HeadWord`, known pattern) -> **REJECTED**, `casting_issues_detected`.
3. write-enabled + warning -> **REJECTED**, `casting_issues_detected`. (My first pass showed this wrongly RUNNING -- traced to a broken sed edit that left a stale cast alias in my own scratch script, satisfying the property before the check ran; rewritten script gives the correct REJECT.)
4. read-only + typo -> **REJECTED**, `casting_issues_detected`.
All 4 match spec; no regression in the two safety cells (3, 4).

## Check 7 -- validate_only vs run_module agreement (typo class)
write_enabled=False: run_module -> reject/`casting_issues_detected`; validate_only -> `status=validation_failed`, casting gate `passed=false`.
write_enabled=True: same on both sides. **Agree at both values, no false reassurance.**

## Check 8 -- #103 hvo gate, 4 quadrants (real gate, real index, `project.Agents.Delete(<hvo>)`)
1. read-only + literal -> not blocked, `[hvo stability]` advisory in `warnings`.
2. write (confirmed) + literal -> **BLOCKED**, `hvo_literal_write_risk`.
3. `.Hvo` read-this-run variable, write -> not flagged (no hvo warning).
4. no literal, write -> silent (no hvo mention).
All 4 match spec.

## Check 9 -- #100/#101
- `_not_cmpossibility_warning`: real function, no index dependency (curated set) -- called directly: all 3 #101 types (interface + concrete forms) flagged; `IMoMorphType`/`MoMorphType` not flagged. Confirmed live.
- access_path: real shipped flexicon index has **no** `access_path` key yet (confirmed: `idx.flexicon["entities"]["MSAOperations"].get("access_path") is None`) -- absent-key fallback exercised against real data. Surfacing behavior tested with a synthetic entity dict (matches unit tests' method, since regenerating the index is off-limits): `paginate_entity` carries `access_path` through in both summary and full mode when present, key omitted (not `None`) when absent; `_build_entity_import` prefers `access_path`, falls back to `from flexicon import X` when absent or no entity passed.

## Check 10 -- import sanity
Loads clean: 118 Flexicon entities, 1878 liblcm entities.

## Check 11 -- the flake, characterized
Ran `TestFileDiscoveryCacheInvalidation` in isolation 20x: **3/20 failed (15%)**, alternating between `test_new_exact_file_visible_after_write` and `test_new_latest_file_visible_after_write`. Ran `test_new_exact_file_visible_after_write` completely alone (no sibling test in the same invocation) 8x: **2/8 failed (25%)**. This directly **contradicts** the "passes in isolation" characterization carried by two prior cycles -- it is a genuine mtime-granularity race intrinsic to the single test, not an interaction between the two tests in the class. Not fixed, per instructions -- flagged as a documentation correction owed to the campaign.

## Not verifiable here
No live-LCM write was performed or attempted, per the explicit prohibition (server PID 19808 predates this campaign's fixes). Nothing in 1e30148 required one -- it is pure AST/static-analysis logic, fully exercisable against the real index without a live project.

## Regression check, prior 9 commits
`cb3f1b8, 0c9a59b, 8f72b9f, b5f41d8, cea0ca6, aba84d8, d1f30da, a1f6897, ffd4bf4`: full suite result above (1120/1121 non-flake pass) covers their tests; #103 (8f72b9f), casting severity (b5f41d8, d1f30da, a1f6897), #100/#101 (cea0ca6) all independently re-verified live above with no discrepancy. **No regression found.**

## `1e30148`: **PASS**
