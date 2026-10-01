# QC Report -- Cycle 7: Lock-Site Inventory

**Date:** 2026-09-07 | **Status:** [ISSUES] | **Method:** mechanical enumeration
**Full table:** `specs/shared-mode-access/reviews/lock-site-inventory.md` (38 sites)
**Greps re-run:** 26 / 21 / 152 hits -- baseline matched exactly.
Both known defects surfaced independently. Defect rows only, prioritized.

---

## P1 -- `project_discovery.py:372-377` (`else:` at 372)

Declares `Stale lock detected` **and** `Close FieldWorks` from bare
`lock_path.exists()` when the holder is unknown. Inverts
`probe_project_access`'s documented fallback (unknown -> `open_exclusive`) and
is self-contradictory. Relayed to users by `server.py:1048` and
`diagnostic_health.py:245`.

**Recommended replacement text:**

> `Lock detected: {lock_path} ({age_str} old), but the lock file is empty or
> unreadable so the holder could not be identified. Treating it as exclusively
> held. If no FieldWorks or python process is actually running, the lock is
> stale -- delete it manually and retry. This server never deletes lock files.`

Mirrors `build_access_remedy()`'s unknown-holder branch
(`project_access.py:250-262`); drops "Stale" and the FieldWorks attribution.

## P1-companion -- `tests/test_shared_mode_access.py:440-453`

Pins the P1 wording with a docstring claiming `test_startup_lock_sweep.py`
requires `"Stale lock detected"`. **Verified false:** that file has **zero**
occurrences; its only wording assertions (lines 47-62) check project name and
`".fwdata.lock"`. Sole assertion-by-comment repo-wide.

**Fix:** rewrite the docstring to state the real contract, rename to
`test_unreadable_lock_is_reported_as_exclusively_held`, and assert
`"could not be identified"` and `"exclusively held"` in `warnings[0]`, plus
`"Stale lock detected" not in warnings[0]`.

## P2 -- `execution.py:2035-2047`

`project_lock["locked"]` is bare existence; `true` for `stale_lock` and
`open_shared`, where writes succeed.

**Fix:** always emit `blocking` alongside `locked`. On probe failure set
`"verdict": "unknown", "blocking": null` plus
`"note": "Access probe unavailable; `locked` means only that a lock file exists
on disk, not that a write would be refused."`

## P2 -- `project_discovery.py:344-354`

Live-holder branch says "Close FieldWorks" without reading `ProcessName` or the
sharing flag -- wrong for `held_by_other` and `open_shared`.

**Fix:** delegate per project to `probe_project_access()` +
`build_lock_diagnosis()` rather than re-deriving; minimally, branch on
`_is_fieldworks_process_name(holder.process_name)` and use
`build_access_remedy`'s `held_by_other` text otherwise.

## P3 -- `project_discovery.py:262-274`

`check_project_locked`'s name asserts a conclusion its return value cannot
support; proximate cause of two historical misses.

**Fix:** rename to `find_lock_file()`; docstring line 1:
`Existence check ONLY -- a lock file may be stale or shared. Use
probe_project_access() for any accessibility decision.`

---

**Recommendation:** FIX ISSUES. No source or test files were modified.
