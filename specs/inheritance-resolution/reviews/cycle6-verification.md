# Cycle 6 -- Verification Report: `total_methods_including_inherited` test coverage

## Scope

Independent certification (per verification-agent protocol) of the two tests
added in cycle 6 to `tests/test_issue86_inheritance_resolution.py`, class
`TestPaginateEntityMerge`:
- `test_total_methods_byte_identical_own_only`
- `test_total_methods_including_inherited_counts_filtered_inherited`

This report does NOT trust `specs/inheritance-resolution/reviews/cycle6-programmer.md`'s
self-reported mutation check; every item below was re-run independently by
the verification agent, including two separate mutations (one on each
branch of the `if method_filter:` split at api.py:625-635), both reverted
and confirmed clean afterward.

## Item 1: Full suite green

Ran the full suite twice: once before any mutation, once after both
mutations were applied-and-reverted.

- Baseline run: `979 passed, 2 skipped in 51.47s`
- Post-mutation/revert run: `979 passed, 2 skipped in 48.90s`

Zero failures, zero errors, in both runs.

**Status: PASS**

## Item 2: Diff scope -- tests-only, src/ untouched

`git status --porcelain` (captured before any mutation work, and again
identically after all reverts):

```
 M specs/inheritance-resolution/PROPOSED-ISSUE-cp3.md
 M tests/test_issue86_inheritance_resolution.py
?? specs/inheritance-resolution/reviews/cycle6-doc.md
?? specs/inheritance-resolution/reviews/cycle6-programmer.md
```

`git diff --stat`:

```
 specs/inheritance-resolution/PROPOSED-ISSUE-cp3.md | 36 +++++++++++++--------
 tests/test_issue86_inheritance_resolution.py       | 37 ++++++++++++++++++++++
 2 files changed, 60 insertions(+), 13 deletions(-)
```

`git diff --stat src/` returned empty output at the start of this
verification (before any mutation was applied) -- confirming the cycle-6
mutation check WAS reverted correctly by the programmer agent and there
was no dirty `src/` at handoff.

`tests/test_issue86_inheritance_resolution.py` is the only modified `.py`
path. The other modified/untracked paths are `.md` files belonging to a
concurrent doc-agent cycle (as the programmer's report also notes), not
`.py` and not under `src/`.

**Status: PASS** (no P0 -- src/ was clean at handoff, before this
verification agent touched anything)

## Item 3: Independent data verification (not reverse-engineered)

Ran a standalone script against the shipped index
(`src/flextoolsmcp/index/liblcm/liblcm_api_v11.0.0.json`) calling
`collect_inherited_members` directly, independent of the test file and
independent of the programmer's report:

```
IFsClosedValue own methods: 0
inherited methods count: 14
combined methods: 14

IReversalIndex own methods: 2
own methods matching "find": ['FindOrCreateReversalEntry']
inherited methods matching "find": ['FindHeaderFooterSetByName']
```

This confirms, from first principles against the real shipped index:
- `IFsClosedValue` has 0 own methods and 14 inherited methods (0/14) --
  matches `test_total_methods_byte_identical_own_only`'s expectation.
- `IReversalIndex` has exactly 1 own method matching filter "find"
  (`FindOrCreateReversalEntry`) and exactly 1 additional inherited method
  matching "find" (`FindHeaderFooterSetByName`), i.e. 1 own / 2 combined --
  matches `test_total_methods_including_inherited_counts_filtered_inherited`'s
  expectation.

**Status: PASS** -- the 0/14 and 1/2 expectations are real, independently
re-derived data, not numbers copied from current test output.

## Item 4: Mutation check on api.py:630 (filtered branch)

Mutated `src/flextoolsmcp/server/handlers/api.py` line 630 from:

```python
total_methods = sum(1 for i, _m in filtered_methods if i < own_method_count)
```

to:

```python
total_methods = sum(1 for i, _m in filtered_methods if i <= own_method_count)
```

Ran ONLY `tests/test_issue86_inheritance_resolution.py`. Result: `1 failed,
25 passed`. The failing test was exactly the predicted one:

```
FAILED tests/test_issue86_inheritance_resolution.py::TestPaginateEntityMerge::test_total_methods_including_inherited_counts_filtered_inherited

    assert result["total_methods"] == 1  # own match: FindOrCreateReversalEntry
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   assert 2 == 1
```

Reverted api.py to its exact prior state (`i < own_method_count`).
Confirmed via `git diff src/` -- empty output, src/ clean again.

**Status: PASS** -- the filtered test fails deterministically under this
mutation with the exact predicted assertion error. This is NOT a P0: the
assertion genuinely exercises api.py:630-631.

## Item 5: Mutation check on api.py:635 (unfiltered branch)

Mutated `src/flextoolsmcp/server/handlers/api.py` line 635 from:

```python
total_methods_including_inherited = len(methods)
```

to:

```python
total_methods_including_inherited = len(methods) - 1
```

Ran ONLY `tests/test_issue86_inheritance_resolution.py`. Result: `1 failed,
25 passed`. The failing test was the unfiltered test, exactly as expected:

```
FAILED tests/test_issue86_inheritance_resolution.py::TestPaginateEntityMerge::test_total_methods_byte_identical_own_only

    assert result["total_methods"] == 0
>   assert result["total_methods_including_inherited"] == 14
E   assert 13 == 14
```

Reverted api.py to its exact prior state (`len(methods)`, no `- 1`).
Confirmed via `git diff src/` -- empty output, src/ clean again.

**Status: PASS** -- `test_total_methods_byte_identical_own_only` is
load-bearing, not merely co-passing: it fails deterministically when the
unfiltered-branch total is perturbed.

## Final state confirmation

After both mutations were applied and reverted, and the full suite was
re-run:

- `git diff --stat src/` -- empty output (src/ byte-identical to what was
  found at the start of this verification).
- `git status --porcelain` -- unchanged from the pre-verification snapshot
  in Item 2 (only `tests/test_issue86_inheritance_resolution.py` and the
  unrelated concurrent-cycle `.md` files show as modified/untracked; no
  `.py` file under `src/` is dirty).
- Full suite re-run: `979 passed, 2 skipped` -- identical to the Item 1
  baseline.

**src/ is confirmed clean. No files were committed, stashed, or left in a
mutated state.**

## Overall Verdict

| # | Item | Status |
|---|------|--------|
| 1 | Full suite green (979 passed, 2 skipped, 0 failed, 0 errors) | PASS |
| 2 | Diff scope -- tests-only .py change, src/ untouched at handoff | PASS |
| 3 | Independent data verification (0/14, 1/2) against shipped index | PASS |
| 4 | Mutation check api.py:630 -- filtered test fails as predicted | PASS |
| 5 | Mutation check api.py:635 -- unfiltered test fails as predicted | PASS |

**No P0 findings. Both new tests are independently certified as
load-bearing (each fails deterministically under its respective targeted
mutation, and both pass in the unmutated codebase alongside the full
979-test suite). src/ is confirmed byte-identical to its pre-verification
state.**

**OVERALL VERDICT: PASS**

---
**Verified By:** Verification Agent
**Date:** 2026-08-13
