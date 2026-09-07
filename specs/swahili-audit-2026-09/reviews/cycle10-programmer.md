# Cycle 10 -- Programmer: CP-E stale-read fix (versioning.py, authorized)

## Design choice: hybrid token (mtime + entry_count + max_child_mtime)

`_dir_state_token()` now returns `(dir_mtime, entry_count, max_child_mtime)`,
computed from a single `os.scandir()` pass over `index_dir`.

**Rejected: full directory-listing hash.** Would require reading/hashing
every versioned JSON on every lookup, on a hot discovery path hit far more
often than the cache-miss glob it protects against. Too expensive for the
benefit.

**Rejected: write counter.** A process-local counter only sees writes made
by *this* process. The defect's primary scenario is an *out-of-band*
`python -m flextoolsmcp.refresh` in a different process (per the existing
`find_latest_versioned_api_file` docstring) -- a counter is structurally
blind to exactly the case this cache-invalidation mechanism exists to
cover, so it fails the actual use case rather than just being imprecise.

**Rejected: bypass-cache-on-miss.** Only fixes the "was a miss, now should
be a hit" half of the race (`find_versioned_api_file` after a file appears).
`find_latest_versioned_api_file`'s race is a *hit that becomes wrong* (an
existing cached "latest" superseded by a newer version written same-tick)
-- bypass-on-miss does nothing there, since the first lookup was already a
hit.

**Chosen hybrid** covers both: a new filename changes `entry_count`
immediately, independent of mtime resolution (the exact "add v4.2.0"
scenario in both measured races); an in-place overwrite of an existing
filename is caught by `max_child_mtime`. `entry.stat()` inside `scandir()`
reuses the OS's already-cached listing data on Windows (no extra per-file
syscall), so the added cost over bare `stat()` is one directory scan --
cheap relative to the `glob()` x2-pattern x2-dir scan a cache miss already
performs.

**Residual, accepted gap:** overwriting an existing filename with new
content while pinning file+dir mtime identical would not change any of the
three signals. Not in scope -- FLExToolsMCP's versioned-filename convention
means "new API version" is always "new filename," so this cache never needs
to detect same-name content churn.

## Docstring correction

`_dir_state_token()` docstring rewritten to state the measured rates
plainly (58/200, 29% unchanged mtime -- cycle8-qc.md; 40/300, 13.3% stale
reads -- cycle8-verification.md), explain the fix, and record why each
rejected alternative was rejected, landed in the same commit as the fix per
instruction.

## Red/Green evidence

Added `TestSameTickCacheInvalidation` to `tests/test_flextools_health.py`,
restoring the same-tick coverage D-2's `_bump_dir_mtime` removed. Instead of
relying on flaky real-clock timing (the 13-29% rate proves it's not 100%
reproducible), it pins `index_dir`'s mtime to an identical fixed value
across two real writes via `os.utime()`, then calls the real
`find_versioned_api_file()` / `find_latest_versioned_api_file()` directly
(no mocks).

- **RED** (pre-fix, ran on the pristine `_dir_state_token`):
  `test_new_exact_file_visible_same_dir_mtime` FAILED --
  `AssertionError: ... assert None is not None`.
  `test_new_latest_file_visible_same_dir_mtime` FAILED --
  `AssertionError: ... got flexicon_api_v4.0.0.json` (expected 4.5.0).
  Both failed 2/2, deterministically (verified by rerun).
- **GREEN** (post-fix): `pytest tests/test_flextools_health.py` -- 12
  passed, including both new tests and all 3 pre-existing
  `TestFileDiscoveryCacheInvalidation` tests (unmodified, still pass with
  the new token).

## Full suite

`pytest -q`: **1135 passed, 4 skipped, 12 subtests passed** (baseline to
beat: 1133 passed, 4 skipped, 12 subtests -- delta is exactly the 2 new
same-tick tests, no regressions).

## Adjacent nit: `_bump_dir_mtime`

Left unchanged, as permitted. The hybrid token makes the future-dated
`+1s`-per-write bump technically unnecessary for the *existing*
`TestFileDiscoveryCacheInvalidation` tests (new filenames alone now bump
`entry_count`), but it is still correct and harmless (writes land in
`tmp_path`, no persistent side effect), and removing it isn't required by
this fix -- doing so would only add churn/risk to 100+ dependent test runs
for no behavior change. Left as-is.

## Files changed

- `src/flextoolsmcp/server/versioning.py` (fix + docstring correction,
  `import os` added, `_file_discovery_cache` type annotation corrected to
  match the real 3-element key)
- `tests/test_flextools_health.py` (same-tick red/green tests)

## Lockout

Acquired `session_id dfa03cff-d35f-4617-a0f7-46bf5f2da05a` over
`versioning.py` + (mis-specified) `tests/server/test_versioning.py`; actual
edits landed in `tests/test_flextools_health.py` instead (the file that
already owns this cache-invalidation suite) -- no conflicting lock existed
for it. Released after commit.

## Commit

Single commit, code + tests + docstring correction together (report
committed first per COMMIT ORDER). SHA recorded in commit history following
this report's commit.
