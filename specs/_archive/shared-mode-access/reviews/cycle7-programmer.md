# Programmer Report -- Cycle 7 (closes P1s + inventory sweep)

**Commit:** `7a4fa5c26e16f1d59628c0787bad5ea5502a5ee1` (main, local, unpushed)
**Files:** execution.py, project_access.py, project_discovery.py,
test_issue49_validate_only.py, test_shared_mode_access.py. specs/ untouched
per instruction (matches ad1d50c/520dba4 precedent).

| # | Item | Landed |
|---|---|---|
| 1 | P1-B project_discovery.py unknown-holder wording | Yes -- inventory's exact recommended text used verbatim |
| 2 | P1-B companion test docstring/assertion | Yes -- renamed to `test_unreadable_lock_is_reported_as_exclusively_held`, asserts "could not be identified" / "exclusively held" / NOT "Stale lock detected" |
| 3 | P1-A validate_only enrichment test coverage | Yes -- `probe_project_access` stubbed in `_stub_validate_only_env` + `_stub_agreement_env` (sibling gap, same file); new `TestValidateOnlyProjectLockEnrichment` (free/open_shared/open_exclusive/unprobed, 4 tests) |
| 4 | Fail-open interim patch | Yes -- additive `probed: bool = True` on `ProjectAccess`, `False` only in the dir-unresolvable branch; validate_only site emits `blocking=None` + omits `verdict` when unprobed. Verdict enum and CP4 gate untouched |
| 5 | `project_lock: Dict[str, Any]` annotation | Yes -- pyright now clean on those lines; `sharing_enabled` tri-state left as-is |
| 6 | Additional inventory DEFECT sites | project_discovery.py:344-354 (P2 live-holder "Close FieldWorks" wrongness for held_by_other/open_shared) fixed by branching on `_is_fieldworks_process_name` + delegating to `build_access_remedy`. P3 rename of `check_project_locked` **skipped** (touches ~9 call sites; docstring corrected instead, contract stated) |

**Tests:** baseline 1144 passed / 4 skipped -> now 1148 passed / 4 skipped.
Delta is exactly the 4 new `TestValidateOnlyProjectLockEnrichment` cases; no
regressions, no other new/removed test functions (the P1-companion test was
renamed, not added). `python scripts/validate_integrity.py all` exits 0.
pyright re-run on the three touched src files: the two pre-existing
`execution.py:4284-4285` unbound-var errors remain (unrelated, pre-existing);
no new errors, and the old dict-type complaint at the enrichment lines is
gone.

**Deviations / refusals:**
- Skipped the P3 `check_project_locked` rename (explicitly optional); left a
  docstring correcting its contract instead.
- Left `diagnostic_health.py:296` unchanged: it publishes `verdict` but never
  a `blocking` field, so it doesn't share the enrichment's exact field set
  the strictly-bounded fail-open patch targeted; changing it would have been
  scope creep beyond item 4's letter.
- Did not touch the other 5 files in the "seven check_project_locked
  monkeypatch sites" list (test_issue55/96/103/nested_uow/write_gate) --
  verified none of them ever call `handle_run_module(validate_only=True)`,
  so `_handle_validate_only`'s enrichment is unreachable from them; their
  `check_project_locked` stubs are inert w.r.t. this bug and patching them
  would have had no effect on coverage.
