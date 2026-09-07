# Verification -- bugfix cycle 4 (feat/shared-mode-access)

No live LCM write performed (per instruction: running server PID 19808
predates the fixes). All checks below are mock/unit/eval-corpus level --
a code-correctness verification, not a live-LCM verification.

## 1. Full suite
`python -m pytest -q` -> exact line:
**`1107 passed, 4 skipped, 12 subtests passed in 40.88s`** -- matches claimed
baseline exactly. One earlier run hit the confirmed flake
`TestFileDiscoveryCacheInvalidation::test_new_exact_file_visible_after_write`
(and once its sibling `test_new_latest_file_visible_after_write`); both pass
in isolation and on rerun -- consistent with the documented mtime-race flake.

## 2. Eval corpus
`python -m pytest -q tests/evals/test_corpus.py` -> **34 passed, 2 skipped, 1.35s**.

## 3. Four-quadrant matrix (via `handle_run_module`, real call)
`test_issue40_casting_severity.py::TestSeverityDecision`, 4/4 PASS:
- (a) read-only+warning-only -> proceeds, `success=True`, no `error_code`, `[casting]` warning present.
- (b) read-only+error-tier -> rejected (`casting_issues_detected`).
- (c) write-enabled+warning-only -> still REJECTED (safety quadrant intact).
- (d) read-only+attribute typo -> still REJECTED (safety quadrant intact).

## 4. #97 Bug 2 verbatim repro
`test_issue97_bug2_if_elif_branches_no_false_positive` -- **PASS**, 0/4 false positives (was 4/4 pre-fix).

## 5. `validate_only` vs `run_module` agreement
`test_validate_only_agrees_with_run_module_on_readonly_warning_tier_casting` -- **PASS**.
`_has_error_severity_casting_issue` (execution.py:1690) confirmed as the single
predicate called at both :1794 (real gate) and :2906 (validate-only Gate 5).

## 6. #100/#101 runtime behavior
`test_issue100_access_path.py` + `test_issue101_not_cmpossibility.py` -- **31/31 PASS**.
- `IMoMorphType` NOT flagged, and confirmed it genuinely HAS `ICmPossibility` in
  the real shipped liblcm index.
- All 3 #101 types flagged in both full and summary `get_object_api` modes (synthetic fixtures + real-index interface check).
- `access_path` in summary/full `paginate_entity` output: confirmed via synthetic fixture only -- shipped `liblcm_api_v11.0.0.json` has zero `access_path` keys (grep-confirmed; refresh forbidden).
- Absent-key import fallback: confirmed against the **real, already-present** `flexicon_api_v4.5.2.json` (untracked, not written by me) -- verdict `"from flexicon import MSAOperations"`, PASS.

## 7. Import sanity
`from src.server import ...` -> **fails**, `ModuleNotFoundError: No module named 'src.server'` (confirms known doc bug; no `src/__init__.py`). `from flextoolsmcp.server import APIIndex, get_index_dir` loads correctly. **118 flexicon entities**.

## 8. Known flake
Fired once (and once as its exact-named sibling); passes in isolation and on clean rerun. Not a new failure.

## Not verified this run
No live-LCM write/read against Target or Sena 3 (correctly withheld -- stale
running server, per instruction). No index refresh run. `access_path` end-to-end
against a freshly-regenerated real liblcm/flexicon index remains unverified;
only pre-refresh fallback + synthetic-fixture paths were exercised.

## Verdict per commit
- `b5f41d8` (casting gate, #40+#97 Bug 2): **PASS**
- `cea0ca6` (#100/#101): **PASS** (real-index access_path caveat above)
- `aba84d8` (primer + teardown test): **PASS** (in full 1107-green suite)
- `d1f30da` (validate_only alignment B-5 + `_parents` hardening B-6): **PASS**

Overall: **PASS at unit/eval level; no live-LCM verification performed**
(correctly withheld -- running MCP server predates these fixes).
