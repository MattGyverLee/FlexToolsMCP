# Verification -- bugfix cycle 5 (a1f6897 / ffd4bf4 + regression set)

No live LCM write was performed or attempted, per the explicit prohibition in
the task (server PID 19808 predates these fixes; live writes would exercise
stale execution.py and risk a modal-dialog hang). All checks below are
static-analysis/handler-level (pytest + direct calls into the real validator
and `handle_run_module` functions with only project I/O and the subprocess
launch stubbed) -- no `SIL.LCModel`/FieldWorks project was opened.

**1. Full suite:** `python -m pytest -q` -> 1 failed, 1114 passed, 4 skipped,
12 subtests. The 1 failure was `test_new_latest_file_visible_after_write`
(the documented mtime-race flake). Reran it + its sibling
`test_new_exact_file_visible_after_write` individually -> both passed.
Net: matches the claimed **1115 passed, 4 skipped, 12 subtests**.

**2. Eval corpus:** `python -m pytest -q tests/evals/test_corpus.py` ->
**34 passed, 2 skipped**. Matches claim exactly.

**3. P1-1 regression matrix (real index, 118 entities):** `d = ILexDb(project); d.EntriesOC`
in all 4 shapes -- all DETECTED (has_typos=True, typo_attr=EntriesOC,
did_you_mean=[Entries]): if-after: DETECTED; try/except: DETECTED;
for-after: DETECTED; flat control: DETECTED. Agrees with main session's 4/4.

**4. #97 Bug 2 non-regression:** verbatim 4-branch MSA repro -> **0 false
positives** (typo detector has_typos=False; detect_casting_needs
casting_issues == []), independently reran
`test_PROMINENT_bug2_msa_repro_still_zero_false_positives_after_p1_fix`. Agrees
with main session.

**5. Four casting quadrants, live through `handle_run_module` (real detectors,
only project I/O stubbed):**
- (a) read-only + warning-tier only -> **RUNS**, success=True, warning text
  `[casting] 1 polymorphic property access issue(s)... did NOT block this
  READ-ONLY run`.
- (b) read-only + error-tier (known pattern `entry.HeadWord`) -> **REJECTED**,
  error_code=casting_issues_detected.
- (c) write-enabled + warning-tier only -> **REJECTED**, error_code=casting_issues_detected.
- (d) read-only + typo -> **REJECTED**, error_code=casting_issues_detected.
All 4 match spec; (c) and (d) hold.

**6. validate_only / run_module agreement (typo class):** write_enabled=False:
validate_only.status=validation_failed, run_module.error_code=
casting_issues_detected (both reject). write_enabled=True: same -- both
reject. Agreement holds at both flags.

**7. #100/#101 non-regression:** `tests/test_issue100_access_path.py` +
`tests/test_issue101_not_cmpossibility.py` -> 31/31 passed. `IMoMorphType`
still not flagged; the 3 #101 types (IMoInflAffixSlot, IMoInflAffixTemplate,
IMoInflClass) still flagged. REAL-INDEX checks: `TestRealIndexPremise`
(liblcm_api_v11.0.0.json, shipped) and `TestRealIndexPreRefreshState`
(flexicon_api_v4.5.2.json, shipped, confirms access_path still absent + the
fallback path is live). All other access_path-surfacing/absent-key-fallback
assertions use synthetic fixtures (no index refresh performed, as instructed).

**8. #103 hvo gate:** `tests/test_issue103_hvo_stability.py` -> 18/18 passed,
including all 4 quadrants: keyword literal write -> hvo_literal_write_risk;
`Object(int)` literal write -> hvo_literal_write_risk; read-only literal ->
not blocked, warned; `.Hvo`-variable write -> not flagged; comment-only
mention -> not flagged. Unaffected by this cycle's casting-block edits.

**9. Import sanity:** PASS -- 118 Flexicon entities loaded.

**10. Flake class:** fired once (test_new_latest_file_visible_after_write);
reran and it passed, consistent with the documented ~1-in-5 mtime race. No
other failures observed.

## Verdict per commit
- **a1f6897** (P1 pair): PASS.
- **ffd4bf4** (primer scoping, docs-only string change, no LCM call): PASS
  (regression test `tests/test_issue96_teardown_visibility.py`, 9/9 passed).
- **b5f41d8, cea0ca6, aba84d8, d1f30da**: PASS, no regression detected.

Not verifiable here: any live-LCM/shared-mode behavior (explicitly
prohibited this cycle) and anything requiring an index refresh (also
prohibited) -- both are out of scope for this campaign's verification pass
and were not silently narrowed.
