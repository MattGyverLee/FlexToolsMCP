# Cycle 7 - Programmer report: CP-D D-2 + D-3 (P2s)

## D-2: versioning-cache flake (tests/test_flextools_health.py)

Root cause confirmed per corrected characterization: `versioning._dir_state_token()`
keys the file-discovery cache on `index_dir.stat().st_mtime`. The three tests write
a file, do a lookup (caching a result), write a second file, then expect the next
lookup to see it -- relying on the filesystem to visibly bump the directory's mtime
between writes microseconds apart. On Windows/NTFS that's not reliable.

**Isolated-run failure counts (40 runs each, `pytest -q <single-test> -p no:randomly`,
one process per run):**

| Test | Before | After |
|---|---|---|
| `test_new_exact_file_visible_after_write` | 5/40 | 0/40 |
| `test_new_latest_file_visible_after_write` | 1/40 | 0/40 |
| `test_health_reflects_post_refresh_reality` | 0/40 | 0/40 |

The third test did not reproduce the flake pre-fix in 40 isolated runs -- reported
honestly, not claimed as evidence either way for that one specifically. It shares the
same dependency (`_write_api_file` -> cache lookup) so the fix was applied to it too
for consistency, and it stayed green.

**Fix** (`tests/test_flextools_health.py`, test-only, `versioning.py` untouched):
added `_bump_dir_mtime()` (os.utime with an explicit, monotonically-increasing
timestamp via an `itertools.count` counter) and call it from `_write_api_file()`
after every fixture write. Diff: +44 lines, module-level helper + docstring, no
production code touched. Commit `71576a6`.

## D-3: 8th import-advertising surface (server/handlers/api.py:689-692)

**STEP 1 triage.** Enumerated all 43 `constants.KNOWN_OPERATIONS` members and
runtime-checked `hasattr(flexicon, name)` against the installed package
(flexicon 4.5.2, `D:\Github\_Projects\_LEX\flexicon\flexicon\__init__.py`, read-only).
Result: **43/43 importable, 0 facade-only.** Additionally ran
`flexicon_analyzer._extract_facade_access_paths` against the real
`FLExProject.py`: 42/43 KNOWN_OPERATIONS members also have a facade `access_path`
(e.g. `LexEntryOperations -> project.LexEntry`) but remain top-level importable too
-- both being true is documented as normal in `flexicon_analyzer.py`'s own comment
(lines 1296-1306). `MSAOperations` is the one genuinely facade-only flexicon class
(confirmed `hasattr(flexicon, "MSAOperations") == False`, facade path
`project.MSA`) but it is **not** a member of `KNOWN_OPERATIONS` -- confirmed by
direct read of `constants.py` lines 18-42 and by the runtime check. So the buggy
branch never fires for the one class that would expose it: **inert for every
current entry.**

**STEP 2:** per instructions, inert-for-every-entry means no speculative rewrite.
Added a documented no-op comment at `api.py:689` (before the `is_operations_class`
check) explaining the finding and pointing at the regression test, plus
`TestKnownOperationsImportInvariant` in `tests/test_issue100_access_path.py`
(2 tests) pinning the invariant. Commit `ce267e0`.

**Red/green evidence** (temporary edits to the test file only, reverted before
final commit -- `constants.py` is outside my lock set):
- `test_every_known_operations_member_is_top_level_importable`: mutated the
  candidate set to `KNOWN_OPERATIONS | {"MSAOperations"}` (one line) ->
  `AssertionError: Lists differ: ['MSAOperations'] != []`. Reverted -> passes.
- `test_msa_operations_deliberately_excluded_from_known_operations`: mutated
  `assertNotIn` -> `assertIn` (one line) -> `AssertionError: 'MSAOperations' not
  found in {...}`. Reverted -> passes.

Both confirmed pytest-collectible and independently green after revert
(`tests/test_issue100_access_path.py`: 21 passed).

## Suite + corpus (post both commits)

- `python -m pytest -q`: **1129 passed, 4 skipped, 12 subtests** (baseline 1127 + 2
  new D-3 tests; matches expectation, no regressions).
- `python -m pytest -q tests/evals/test_corpus.py`: **35 passed, 2 skipped**
  (unchanged).

## Commits

- `71576a6` fix: pin explicit directory mtime bumps in file-discovery cache tests (D-2)
- `ce267e0` docs: confirm the 8th import-advertising surface is a no-op (D-3)

## Deferred / out of scope

Nothing deferred outside the lock set for D-2. For D-3, the STEP-2 access_path-aware
fix itself is not needed today (confirmed no-op), but if `KNOWN_OPERATIONS` ever
gains a facade-only member, the fix would need to touch `api.py:689-692` only
(in-lock-set) unless the correct place to record that fact turns out to be
`constants.py` (out of lock set) -- flagged in the comment/test docstrings for
whoever picks this up next.

Untouched per instructions: `src/flextoolsmcp/server/validators.py`, the
flexicon 4.4.1->4.5.2 index migration, `operations.jsonl`,
`specs/swahili-audit-2026-09/reviews/cycle1-*.md`, `specs/logscan-2026-09-07/`.
