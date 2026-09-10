# T008 -- lifecycle tests for attached-view refusals (RED)

**File touched:** `D:/Github/_Projects/_LEX/flexicon/tests/test_from_open_project.py` (only file changed, per constraint)

## Baseline (before this task)

`python -m pytest tests/test_from_open_project.py -q` -> **23 passed, 0 failed**
(US1, T001-T007; the file already imported `_ATTACHED_VIEW_SAVE_REFUSAL`,
`_ATTACHED_VIEW_UNDOABLE_REFUSAL`, `FP_TransactionError` but had no lifecycle
test bodies).

## After this task

`python -m pytest tests/test_from_open_project.py -q` -> **30 passed, 8 failed**
(38 collected; 15 new tests added: 8 RED lifecycle tests + 7 GREEN
non-lifecycle/regression tests).

## New tests added

### `TestAttachedViewCloseProject` (T2.2a) -- all 4 RED
- `test_returns_none_without_raising`
- `test_does_not_end_the_hosts_non_undoable_task`
- `test_does_not_save_or_dispose_the_hosts_cache`
- `test_leaves_the_view_pointed_at_the_donors_cache`

RED signature (identical root cause for all four -- `CloseProject()` is
unguarded, runs the owned-project path, calls `EndNonUndoableTask()` on the
donor's cache, then crashes trying to save):

```
flexicon\code\FLExProject.py:643: in CloseProject
    usm = self.ObjectRepository(IUndoStackManager)
flexicon\code\FLExProject.py:3822: in ObjectRepository
    return self.project.ServiceLocator.GetService(repository)
AttributeError: '_FakeCache' object has no attribute 'ServiceLocator'
```
(propagates out of `view.CloseProject()` in each test before any of the
test's own assertions run -- confirming `EndNonUndoableTask()` and
`Dispose()` both fire on the donor's cache today, exactly what T009 must stop.)

### `TestAttachedViewSaveChanges` (T2.2b) -- 3 of 5 RED
- `test_write_enabled_donor_at_depth_zero` -- RED (falls through the
  depth-0 guard, crashes in the same `ObjectRepository`/`ServiceLocator`
  `AttributeError` as above -- ahead of any `FP_RuntimeError`).
- `test_write_enabled_donor_at_depth_one_does_not_tell_a_depth_story` -- RED:
  ```
  assert type(exc) is FP_RuntimeError
  E   assert <class 'flexicon.code.exceptions.FP_TransactionError'> is FP_RuntimeError
  ```
  (today's depth guard fires first and raises `FP_TransactionError` naming
  `CurrentDepth is 1` -- the exact "transaction-depth story" T011 must
  pre-empt with the attached-view guard.)
- `test_read_only_donor_still_gets_the_attached_view_refusal` -- RED:
  ```
  assert type(exc) is FP_RuntimeError
  E   AssertionError: assert <class 'flexicon.code.exceptions.FP_ReadOnlyError'> is FP_RuntimeError
  ```
  (this is the trap called out in the brief: a bare
  `pytest.raises(FP_RuntimeError)` would have silently passed here since
  `FP_ReadOnlyError` is a subclass -- the exact-type assertion is what
  makes it RED.)
- `test_the_refusal_constant_does_not_repeat_closeproject_advice` -- GREEN
  (asserts against the `_ATTACHED_VIEW_SAVE_REFUSAL` constant itself, which
  already ships the correct wording; not implementation-dependent).
- `test_the_refusal_constant_is_ascii` -- GREEN (same reasoning).

### `TestAttachedViewUndoableOperation` (T2.2c) -- 1 of 3 RED
- `test_raises_transaction_error_with_the_attached_view_wording` -- RED:
  ```
  assert _ATTACHED_VIEW_UNDOABLE_REFUSAL in str(excinfo.value)
  E   AssertionError: assert 'UndoableOperation() is not available on a project attached with FromOpenProject()...' in 'Project must be opened with undoable=True to use UndoableOperation. Current project was opened with undoable=False.'
  ```
  (`_FLExUndoableOperation.__enter__` still raises the owned-project
  wording unconditionally on `not self._project._undoable` -- T010 must add
  the `_IsAttachedView` branch ahead of it.)
- `test_the_refusal_constant_does_not_blame_an_argument_never_passed` -- GREEN
  (constant-only check).
- `test_the_refusal_constant_is_ascii` -- GREEN (constant-only check).

### `TestOwnedProjectRegressionLocks` -- all 3 GREEN now, must stay GREEN after T009-T012
- `test_is_attached_view_is_false_for_an_owned_project` -- GREEN
  (`_IsAttachedView(_OwnedProjectDouble())` is `False`; the double is a
  plain class, not `unittest.mock.Mock`, specifically so `hasattr(...,
  "_attached_donor")` can't auto-vivify a false positive).
- `test_is_attached_view_is_true_for_an_attached_view` -- GREEN
  (`_IsAttachedView(view)` is `True`, view built via `FromOpenProject`).
- `test_owned_project_keeps_the_original_undoable_false_wording` -- GREEN
  (`with _FLExUndoableOperation(owned, "label"):` raises `FP_TransactionError`
  containing `"opened with undoable=False"` -- confirmed unchanged today,
  and must remain unchanged once the attached-view guard is added in front
  of it).

## Full counts

| | Before | After |
|---|---|---|
| Passed | 23 | 30 |
| Failed | 0 | 8 |
| Total | 23 | 38 |

All 8 failures are exactly the 8 lifecycle-refusal assertions T009-T012 are
meant to turn green; every other new test (7) and every pre-existing test
(23) is green, confirming the regression locks hold today and the new RED
signatures are isolated to the unimplemented guards.

## Constraints honored
- Only `tests/test_from_open_project.py` was modified; no `flexicon/code/*.py`
  file was touched.
- No `requires_live_project` marker used anywhere in this file.
- `sys.modules["SIL"]` was never stubbed; the file imports `flexicon` normally.
- All added text is ASCII; both `_ATTACHED_VIEW_SAVE_REFUSAL` and
  `_ATTACHED_VIEW_UNDOABLE_REFUSAL` are additionally asserted against
  `.encode("ascii")` not raising.
