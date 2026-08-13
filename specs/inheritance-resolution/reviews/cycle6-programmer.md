# Cycle 6 -- Programmer report: `total_methods_including_inherited` test coverage

## Scope

Test-only change closing the deferred #86 P2: the properties twin
(`total_properties_including_inherited`) had four assertions covering it;
`total_methods_including_inherited` had zero. Added two tests to
`tests/test_issue86_inheritance_resolution.py`, class `TestPaginateEntityMerge`.

## Tests added

File: `tests/test_issue86_inheritance_resolution.py`

- `test_total_methods_byte_identical_own_only` -- line 178
  Unfiltered branch (api.py:634-635). `IFsClosedValue`, `method_filter=""`.
  Asserts `total_methods == 0` and `total_methods_including_inherited == 14`
  (IFsClosedValue declares no own methods; all 14 are inherited).

- `test_total_methods_including_inherited_counts_filtered_inherited` -- line 192
  Filtered branch (api.py:630-631), the discriminating case. `IReversalIndex`,
  `method_filter="find"`. Asserts `total_methods == 1` (own match
  `FindOrCreateReversalEntry`), `total_methods_including_inherited == 2` (adds
  inherited `FindHeaderFooterSetByName`), and
  `[m["name"] for m in result["methods"]] == ["FindOrCreateReversalEntry", "FindHeaderFooterSetByName"]`,
  pinning the own-then-inherited ordering line 630's index comparison relies on.

Both mirror the existing `test_total_properties_byte_identical_own_only`
style: same `from server.handlers.api import paginate_entity` local import,
same `liblcm_entities` fixture, same keyword-argument call shape.

Expected values were pre-verified directly against the shipped index before
writing assertions (`IFsClosedValue` has 0 own / 14 combined methods;
`IReversalIndex` filtered on "find" has 1 own / 2 combined, with methods
ordered `["FindOrCreateReversalEntry", "FindHeaderFooterSetByName"]`) -- all
matched the values specified in the task with no discrepancy, so no
adjustment was needed.

## Full-suite results

- Before mutation check (tests already added): `979 passed, 2 skipped`
  (68.93s)
- After mutation revert, re-run: `979 passed, 2 skipped` (46.39s) -- identical
  counts, confirming no regression and no flake.

## Mutation check (api.py:630)

Temporarily changed `src/flextoolsmcp/server/handlers/api.py:630` from:

```python
total_methods = sum(1 for i, _m in filtered_methods if i < own_method_count)
```

to:

```python
total_methods = sum(1 for i, _m in filtered_methods if i <= own_method_count)
```

Re-ran only `tests/test_issue86_inheritance_resolution.py`. Result:
`1 failed, 25 passed`. The failure was exactly the predicted test:

```
FAILED tests/test_issue86_inheritance_resolution.py::TestPaginateEntityMerge::test_total_methods_including_inherited_counts_filtered_inherited
assert result["total_methods"] == 1  # own match: FindOrCreateReversalEntry
AssertionError: assert 2 == 1
```

This confirms the test genuinely exercises the api.py:630-631 branch: with
the off-by-one (`<=` instead of `<`), the first inherited match
(`FindHeaderFooterSetByName`, at index `own_method_count == 2` within the
filtered/enumerated `methods` list) is miscounted as "own," so
`total_methods` comes back `2` instead of the correct `1`.
`test_total_methods_byte_identical_own_only` (the `IFsClosedValue` case) did
NOT fail under this mutation, as expected -- with 0 own methods it can never
detect this off-by-one under a filter, which is precisely why the
`IReversalIndex` case was required as the discriminating test.

api.py was then reverted to its exact prior state (`i < own_method_count`).

## Final state verification

- `git diff --stat src/` -- empty output; no changes to any file under `src/`.
- `git status --porcelain` -- only `tests/test_issue86_inheritance_resolution.py`
  is modified by this work. (Two unrelated paths --
  `specs/inheritance-resolution/PROPOSED-ISSUE-cp3.md` (modified) and
  `specs/inheritance-resolution/reviews/cycle6-doc.md` (untracked) -- appear
  in `git status` but were not touched by this task; they belong to a
  concurrent doc-agent cycle and are left as-is.)
- Final full-suite re-run after revert: `979 passed, 2 skipped`, matching the
  pre-mutation baseline exactly (both counts already include the 2 new
  tests, since they were added before the baseline run per the task's
  ordering).

## Conclusion

Both new tests pass in the unmutated codebase, and the mutation check
confirms `test_total_methods_including_inherited_counts_filtered_inherited`
fails deterministically when the api.py:630 off-by-one is introduced, with
the exact assertion error `assert 2 == 1`. No P0 finding. `src/` is clean in
the final state; only `tests/test_issue86_inheritance_resolution.py` was
modified.
