# Cycle 8 -- mutations_detected / write-certification defect (#93 findings (a)/(d) + live escalation)

## Root cause (two stacked gaps, both fixed)

1. **Enumeration gap.** `certify_script_readonly()` (validators.py) correctly
   files a *guarded* mutation (`if modifyAllowed: project.Senses.SetGloss(...)`)
   into `protected_liblcm_calls` (raw-LCM path) or silently dropped it
   entirely for a guarded literal `*Operations(project).Method()` call
   (validators.py, old line 3066-3068: `elif is_mutating and is_protected: pass`).
   `build_writeability_payload()` (validators.py:3286-3305, old) only read
   `mutating_calls` + `unprotected_liblcm_calls` -- never the protected_*
   lists -- so a properly-guarded write produced `mutations_detected: []`
   while `is_mutating_script` still fired via `cud_info["is_cud"]`
   (line-blind, guard-unaware). That is finding (a)'s exact self-contradictory
   refusal, reproduced verbatim locally before any fix.

2. **Boolean/safety gap (live escalation, more severe).** `_PATTERN_OPERATIONS_CALL`
   (validators.py:74) only matches a literal `*Operations` receiver; the
   documented `project.<Accessor>.<Method>(...)` facade idiom (`project.Senses`,
   `project.CustomFields`, etc.) never reached Step 1's index lookup at all.
   For `project.CustomFields.CreateField(...)` the old gate formula --
   `(not cert["is_certified_readonly"]) or cud_info["is_cud"]` (execution.py:4177)
   -- evaluated `(not True) or False` == **False** (guarded, so certified
   readonly; `CreateField` not in the CUD regex verb list since the old
   `Create\(` pattern required an exact match with no suffix). `needs_lock`
   was False: a guarded schema mutation ran with `write_enabled=True,
   confirmed=False` and **no lock, no confirmation_required refusal**. I
   reproduced this independently before patching (confirmed empty
   `mutations_detected`, `is_certified_readonly: True`, and -- critically --
   `is_mutating_script: False` with the old formula).

## Fix (bounded to validators.py + execution.py + tests)

- Added Step 1c to `certify_script_readonly()`: resolves `project.<Accessor>`
  to its Operations class via the index's `access_path` metadata (already
  populated by flexicon_analyzer's issue #100 facade scan) and feeds it
  through the SAME index `is_mutating` lookup as literal `*Operations` calls
  -- authoritative regardless of receiver spelling.
- Added `protected_calls` (new list, parallel to `protected_liblcm_calls`)
  so guarded wrapper mutations are tracked instead of silently dropped.
- `build_writeability_payload()` now surfaces both protected lists in
  `mutations_detected`, each tagged `"protected": bool`; de-dupes same-line
  wrapper/raw_lcm duplicates.
- New shared `compute_is_mutating_script(cert, cud_info)` is now the single
  formula both `build_writeability_payload()` and `handle_run_module()`'s
  `needs_lock` call -- true if ANY of mutating_calls/protected_calls/
  unprotected_liblcm_calls/protected_liblcm_calls/cud_info is non-empty, so
  guarded-but-real mutations always need the lock, regardless of verb
  spelling. Also broadened Create/Delete regexes (`Create\w*\(`) as
  defense-in-depth for when no API index is loaded.
- Confirmation message is now self-consistent even in a residual
  no-line-aware-source edge case (never says "0 mutation(s) detected" while
  refusing as mutating).
- Fixed an unrelated Pyright "possibly unbound" on `check_project_locked`/
  `build_access_remedy` by hoisting their import out of the `if needs_lock:`
  guard.

## Tests

Added/updated across `tests/test_script_certification.py` (+7 tests,
incl. SetGloss guarded/unguarded, CreateField guarded/unguarded, and an
index-only verb -- `AgentOperations.Duplicate` -- with zero regex-list
overlap, proving index-authority), `tests/test_issue49_validate_only.py`
(+2 new, 1 clarified/re-scoped, none weakened), `tests/test_issue55_write_safety_ladder.py`
(+1 integration-level regression that fails against the pre-fix formula --
verified by temporarily reverting the formula and confirming
`run_script_async` fires). Full suite: 1159 passed, 4 skipped (was 1148/4).
Pyright clean (0 errors) on both changed files.

Files: `src/flextoolsmcp/server/validators.py`,
`src/flextoolsmcp/server/handlers/execution.py`,
`tests/test_script_certification.py`, `tests/test_issue49_validate_only.py`,
`tests/test_issue55_write_safety_ladder.py`.
