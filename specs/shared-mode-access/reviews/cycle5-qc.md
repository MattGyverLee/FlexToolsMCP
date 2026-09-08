# QC Report -- CP3 diff (6677fd8)

**Date:** 2026-09-07 | **Score:** 88/100 | **Status:** [PASS]
**Scope:** commit 6677fd8 only.

## Gates
- **Pattern-audit:** section present. Spot-check found it under-scoped -> P1-2. PASS (not BLOCK; section exists, missed sibling is pre-existing + informational).
- **Live-LCM:** read-only diagnosis path; no Operations class/factory/setter/transaction. **N/A (no LCM write call).** But SPEC.md:233-235's CP3 checkpoint (live read-only run vs sharing-off + FLEx-open) has NOT happened, and all 6 tests mock the probe -- nothing exercises the real registry+filesystem probe from this call site. Diff approved; **checkpoint stays CONDITIONAL.**

## P0
None.

## P1
1. **Partial mutation under the swallow** -- execution.py:1251-1262. The six `diag[...]` writes are not atomic. If `build_access_remedy()` (line 1261, last statement) raises, `diag` escapes with hint/verdict/sharing_enabled/holder_pid/holder_process set but **no `remedy` key** -- spread flat onto `execution_result` by the `.items()` loop at 4429-4438. That is a third payload shape neither path intends, and it violates the invariant test_probe_raising... asserts (`assertNotIn("verdict", diag)`). Fix: accumulate into a local `extra: Dict[str, Any]`, then `diag.update(extra)` as the single last statement in the try.
2. **Sweep under-scoped** ("No sibling sites found"). Live sibling: execution.py:2030 -> project_discovery.py:262-274 `check_project_locked()` sets `project_lock["locked"]=True` on bare `.fwdata.lock` existence -- the same false positive CP3 just removed. Also project_discovery.py:351-357 says "Close FieldWorks ... to allow write operations" in the branch that just determined the holder is "no longer running (stale)" -- the CP3/CP4 wording drift `build_lock_diagnosis` exists to prevent. Follow-up issue, not a blocker.

## P2
3. **Q1 -- the swallow (execution.py:1262).** Breadth is defensible; **silence is not.** A TypeError from a future `probe_project_access` signature change degrades to the generic hint forever with zero trace. Do NOT narrow to a type tuple (enumerating registry/FS failures is what the comment calls unknowable, and a narrow tuple reintroduces crash risk). Instead: `except Exception as exc:` + `logger.debug("CP3 lock diagnosis unavailable: %r", exc)`. `logger` is module-level and used throughout (480-492, 765).
4. **Untested new branch** -- project_access.py:308 `"an unreadable PID"` (pid/holder None) has zero coverage. Telling: the helper's `holder=` param (tests:34/39) is never passed False -- the seam was built and unused.
5. **Q2 -- tests.** Not tautological: the mock supplies only the `ProjectAccess`; assertions land on real `build_lock_diagnosis`/`build_access_remedy` text ("Sharing tab", "does not resolve it"). PID assertion (tests:75-77) *does* catch a wrong-PID regression (4242 vs helper default 68436; no other digits in the text), but `assertIn("4242", ...)` is bare-substring -- passes on "PID 42424". Tighten to `assertIn("PID 4242")` + `assertNotIn("68436")`; same at :83.
6. **Q3 -- new file: not fragmentation.** The surface is already partitioned by concern (probe / CP4 gate / payload contracts); a fourth on that axis is consistent. Nit: named by checkpoint (`cp3`) while siblings are named by concern -- `test_shared_mode_lock_diagnosis.py` ages better.
7. **Q4 -- dispatch: no defect.** Total over five verdicts; every `build_access_remedy` branch (251-273) returns a string for the two delegated verdicts, so delegation can't yield None, and the `is not None` guard (1245) correctly keeps free/open_shared/unknown generic. Caveat: probe runs *after* the failed open, so the verdict is probe-time, not failure-time -- harmless (the stale_lock retry advice is right for exactly that race) but the hint asserts present-tense cause for a past event.
8. **Shape inconsistency:** CP3 spreads the four probe facts flat; CP4 namespaces them under `shared_mode` (4264-4270, 4284-4290). Two nestings, one fact set. Drift hazard only -- all five names exist on ProjectLockedDetail (response_models.py:294-301).

## Scores
Code Quality 22/25 (docstrings record the rejected alternative -- above average) | Standards 24/25 | Error Handling 20/25 | Best Practices 22/25

## Final
**88/100 -- APPROVE**, conditional on the SPEC.md:233-235 live observation before CP3 is marked verified. Address P1-1 (atomic update) and P2-3 (debug log) in-place; file P1-2 as a follow-up.

---
**Reviewed By:** QC Agent
