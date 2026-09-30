# T010 -- attached-view branch in `_FLExUndoableOperation.__enter__`

**File edited (only one):** `D:/Github/_Projects/_LEX/flexicon/flexicon/code/undoable_operation.py`
**Not touched:** `flexicon/code/FLExProject.py` (concurrent agent's file). No `git add`/commit performed.

## Diff

```diff
diff --git a/flexicon/code/undoable_operation.py b/flexicon/code/undoable_operation.py
index 7002db0..3b72dc3 100644
--- a/flexicon/code/undoable_operation.py
+++ b/flexicon/code/undoable_operation.py
@@ -91,7 +91,14 @@ class _FLExUndoableOperation:

         if not self._project._undoable:
             # Lazy import to prevent circular dependency: FLExProject imports undoable_operation at module level
-            from .FLExProject import FP_TransactionError
+            from .FLExProject import (
+                FP_TransactionError,
+                _ATTACHED_VIEW_UNDOABLE_REFUSAL,
+                _IsAttachedView,
+            )
+
+            if _IsAttachedView(self._project):
+                raise FP_TransactionError(_ATTACHED_VIEW_UNDOABLE_REFUSAL)

             raise FP_TransactionError(
                 "Project must be opened with undoable=True to use UndoableOperation. "
```

`_IsAttachedView` and `_ATTACHED_VIEW_UNDOABLE_REFUSAL` are pulled from
`.FLExProject` via the same lazy import already used for
`FP_TransactionError` in this block (mandatory, not stylistic -- FLExProject
imports `undoable_operation` at module level). Both names already existed on
this branch at `FLExProject.py:137` (`_IsAttachedView`) and `:174`
(`_ATTACHED_VIEW_UNDOABLE_REFUSAL`) before this edit; neither was added or
modified here.

Exception type in both branches: `FP_TransactionError` (unchanged).
ASCII only -- no non-ASCII characters were introduced.

## Owned-project message: byte-identical confirmation

The diff above shows the owned-project raise as three unchanged context
lines (no `-`/`+` markers on them):

```
            raise FP_TransactionError(
                "Project must be opened with undoable=True to use UndoableOperation. "
                f"Current project was opened with undoable=False."
            )
```

Character-for-character, this is the exact same string literal that existed
before the edit: `"Project must be opened with undoable=True to use
UndoableOperation. "` concatenated with `f"Current project was opened with
undoable=False."`. Nothing in the edit changed, reformatted, or re-wrapped
this string; the only change is the new `if _IsAttachedView(...): raise ...`
branch inserted immediately above it, which returns/raises before this code
is reached on an attached view and leaves it untouched on an owned project.

## Test results

1. `python -m pytest tests/test_from_open_project.py -q`
   -> **35 passed, 3 failed** (in this in-progress branch state).
   The 3 failures are all in `TestAttachedViewSaveChanges`
   (`test_write_enabled_donor_at_depth_zero`,
   `test_write_enabled_donor_at_depth_one_does_not_tell_a_depth_story`,
   `test_read_only_donor_still_gets_the_attached_view_refusal`) -- these
   exercise `SaveChanges()`, which is T011's guard in `FLExProject.py:798`,
   owned by the concurrent agent and mid-edit; they are unrelated to this
   task's `UndoableOperation()` change and are out of scope here.

2. `python -m pytest -q tests/ -k undoable`
   -> **65 passed, 2431 deselected**. All UndoableOperation-related tests
   (including T2.2c and the depth/join tests in
   `tests/test_from_open_project.py`) pass.

   Full offline gate `python -m pytest -q -m "not requires_live_project"`
   -> **1 failed, 1785 passed, 710 deselected** (deselected count matches
   the stated baseline exactly: 710). The single failure,
   `tests/test_transaction_honesty.py::TestRefreshFromDisk::test_uses_same_accessor_pattern_as_save_changes`,
   is a source-slice-window assertion over `SaveChanges()`'s body length in
   `FLExProject.py` -- it fails because the concurrent agent's in-progress
   `SaveChanges()` guard (T011) has pushed the method body past the test's
   fixed character window. This is entirely inside `FLExProject.py`, not
   touched by this task, and not a regression caused by this edit.

   Note: a bare `python -m pytest -q` (no marker filter) also picks up
   several `requires_live_project` integration tests that need a live FLEx
   session; those showed pre-existing/unrelated failures (duplicate
   operations, natural classes, text operations, issue243 SaveChanges-depth
   probe) with no relationship to `undoable_operation.py`. The
   marker-filtered run above is the correct comparison against the stated
   baseline (1748 passed / 710 deselected mentioned in the task; current
   1785 passed reflects the additional CP2 tests -- T004/T008 -- added on
   this branch since that baseline was recorded).

3. `git diff flexicon/code/undoable_operation.py` -- shown above; confirms
   the owned-project message string is unchanged character-for-character.

## Summary

Only `flexicon/code/undoable_operation.py` was edited. The attached-view
branch is inserted first inside the existing `if not
self._project._undoable:` block, using the lazy import already present in
that block to also reach `_IsAttachedView` and
`_ATTACHED_VIEW_UNDOABLE_REFUSAL` from `.FLExProject`. All `-k undoable`
tests and all `test_from_open_project.py` tests specific to
`UndoableOperation()` pass; the 3 failing tests in that file and the 1
failing test in the full offline gate are scoped to `SaveChanges()`
(T011/`FLExProject.py`), which is the concurrent agent's in-progress work,
not this task.
