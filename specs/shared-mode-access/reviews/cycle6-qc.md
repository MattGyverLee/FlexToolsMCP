# QC Report -- cycle 6 (520dba4 + ad1d50c)

**Date:** 2026-09-07 | **Score:** 87/100 | **Status:** [ISSUES]
**Scope:** 520dba4, ad1d50c only. 6677fd8 cleared at 88/100 (cycle5-qc.md).

## Gates
- **Pattern-audit:** sections present in both bodies; listed siblings verified genuine. Spot-check of ad1d50c's *exclusion* claim ("both already reflect the true verdict") **[FAIL]**. Gate **PASS** (miss is pre-existing, not a regression) -- P1-2.
- **Live-LCM:** validate_only never opens a project; sweep_stale_locks is log-only. **N/A (no LCM call).** SPEC.md:233-235 CP3 live observation still outstanding -- checkpoint stays **CONDITIONAL**.
- Regression run: 275 tests over the 11 affected files, all pass.

## Confirmed fixed
**Q1 -- `diag` is now genuinely atomic.** `build_access_remedy()` is evaluated inside the `extra` literal (execution.py:1251-1264); if it raises, `extra` is never bound and `diag` is untouched. `diag.update(extra)` (:1265) is the sole mutation and the last statement in the try; nothing between probe and update touches `diag`. **P1-1 closed.** Also closed: silent swallow (:1266-1269, None-guarded debug log), PID assertions, test rename, docstring line-ref.

## P0
None.

## P1
1. **Enrichment untested; seam half-mocked.** All seven `check_project_locked` monkeypatch sites (test_issue49:412,525; test_issue55:178; test_issue96:73; test_nested_uow_gate:157; test_issue103:183; test_shared_mode_write_gate:147) stub the lock check but not `probe_project_access`, so execution.py:2064 probes the live host. **Q2: nothing breaks** -- :551 asserts only `locked`, and GOLDEN_FIXTURES holds error_response shapes only (no validate_only fixture). But `verdict`/`blocking` are now host-dependent and uncovered. Patch the probe in `_stub_validate_only_env`; add open_shared + open_exclusive cases.
2. **Q4 -- missed sibling:** project_discovery.py:371-375, the unreadable-holder branch of the function ad1d50c just edited. Declares **"Stale lock detected"** from bare existence -- the inversion of probe_project_access:341-350's documented fallback (unknown holder -> `open_exclusive`) -- and still says "Close FieldWorks". Net: the branch that *knows* the holder is dead now says "no action"; the one that knows *nothing* says "stale". Test-locked at test_shared_mode_access.py:442-451.

## P2
3. **Q3 -- `blocking` is correct for all five verdicts** (True for exactly `open_exclusive`/`held_by_other`; unreadable holders map to `open_exclusive`, erring safe). Gap is upstream: `get_projects_directory() -> None` yields `verdict="free"`, so any non-Windows/FW-absent host emits `blocking: false` **without probing**. Emit `verdict:"unknown"` / `blocking: null` there.
4. **Pyright execution.py:2066-2067** (`str`, `bool|None` into inferred `dict[str,bool]`; :2047 pre-existing). Fix: `project_lock: Dict[str, Any]`. `sharing_enabled=None` is **not** a defect -- `blocking` derives from `verdict` alone; JSON `null` correctly means unknown. Keep the tri-state.

## Scores
Code Quality 23/25 | Standards 23/25 | Error Handling 21/25 | Best Practices 20/25

## Final
**87/100 -- FIX ISSUES.** Both P1s are cheap and in-place; neither regresses 6677fd8. CP3 stays conditional on the live observation.

---
**Reviewed By:** QC Agent
