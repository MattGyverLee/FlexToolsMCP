# Cycle 4 -- Programmer W1: nested-UnitOfWork pre-flight gate (#92 follow-up)

## (a) UoW-opening call shapes (grounded, not guessed)
Checked liblcm + installed flexicon (`D:\...\flexicon\flexicon\code`):
- `UndoableUnitOfWorkHelper`/`NonUndoableUnitOfWorkHelper` -- constructor (ctor calls `BeginUndoTask`/`BeginNonUndoableTask`, `UndoableUnitOfWorkHelper.cs:31`, `NonUndoableUnitOfWorkHelper.cs:34-44`) and static `.Do()`/`.DoSomehow()`/`.DoUsingNewOrCurrentUOW()` etc.
- Raw `IActionHandler.BeginUndoTask(u,r)` / `.BeginNonUndoableTask()`, any owner expression.
- flexicon's OWN `project.Transaction()`/`project.UndoableOperation()` (`transaction.py`, `undoable_operation.py`) are NOT unsafe -- both ask `ActionHandlerAccessor.CurrentDepth` and **join** an open UoW instead of nesting (liblcm's own `DoUsingNewOrCurrentUOW` idiom). Excluded from detection by design.
- Evidence for the collision itself: `liblcm/.../Impl/UndoStack.cs:187-216` (`BeginUndoTask`) and `:252-264` (`BeginNonUndoableTask`) both call `CheckNotProcessingDataChanges`, which calls `Rollback(0)` **then** throws `InvalidOperationException("Nested tasks are not supported.")` when a task is already open.

## (b) Gate fires only when write_enabled
`flexicon/code/FLExProject.py:262-289`: `MainCacheAccessor.BeginNonUndoableTask()` is called only in the `self.writeEnabled and not self._undoable` branch. Since CP1 hardcodes `undoable=False` unconditionally, that's equivalent to "only when `write_enabled=True`". Read-only runs never enter either branch -- no UoW is opened, nothing to nest into. **Gate condition implemented: `if write_enabled: ...`** at `execution.py:2704`.

## Implementation
- `src/flextoolsmcp/server/validators.py:444-548`: `detect_nested_unit_of_work(code, tree)` -- AST-based (`ast.walk` over `ast.Call`), matches direct ctor calls, static `Helper.Method(...)` calls, and any `.BeginUndoTask(...)`/`.BeginNonUndoableTask(...)`. Comments/strings never produce `ast.Call` nodes, so they never false-positive (no explicit stripping needed). Reconciled with, not duplicating, `_LIBLCM_MUTABLE_PATTERNS:94`'s narrower `_cache.BeginNonUndoableTask(` entry -- that one feeds the *unrelated* unprotected-writes/guard gate; mine is guard-blind by design since a guard doesn't fix nesting.
- `execution.py:73,87` (imports), `:2686-2735` (gate, modeled verbatim on the `partial_module_structure` gate at `:2654-2684`).
- **Second call site (`:1726-1739`, validate_only's 11-gate list): NOT added.** That "11 gates" count is documented across files I don't own (`tool_definitions.py`, `models.py`, 4 `workflow-*.svg`, `docs/workflow-detail.md`, `tests/test_issue49_validate_only.py`); widening it mid-fix would be an inconsistent partial change outside scope. Flagged as a follow-up, not done.
- **Error code `nested_unit_of_work`** -- no collision (grepped repo).
- `response_models.py`: `NestedUnitOfWorkDetail` (`extra="forbid"`, fields `constructs`, `guidance`) before `ProjectLockedDetail` (untouched, per constraint); `AnyDetail` union entry; docstring counts.
- `session.py`: `_ASSISTANCE_HINTS_BY_ERROR_CODE["nested_unit_of_work"]`.
- `tests/make_golden.py`: `GOLDEN_FIXTURES["nested_unit_of_work"]`; regenerated (`tests/golden/responses/nested_unit_of_work.json` new, all 19 others unchanged).
- **16->17 moved in**: `docs/TOOL-CONTRACT.md:69,110`, `tests/test_response_contract.py:9,199(ALL_16_CODES->ALL_17_CODES+entry),220`, `response_models.py` (2 docstrings), `CLAUDE.md:111`, `README.md:145`. Left untouched (historical, correct-at-the-time record): `CHANGELOG.md:620,622` (past release entry), `specs/**/reviews/*.md` (past cycle records), README's unrelated "MCP Tools (16)" tool count.
- New `tests/test_nested_uow_gate.py` (15 tests): each construct detected directly; guard-does-not-suppress; flexicon's own Transaction/UndoableOperation not flagged; comment-only and string-only not flagged; gate refuses write-enabled runs with no lock/subprocess reached (boom-stubs); ordinary guarded write not refused; read-only run with the construct not refused.
- `CHANGELOG.md` `[Unreleased]` new section added before the `#84` entry.

## Test results
`pytest -q`: **1008 passed, 4 skipped** (no failures). One transient failure in `tests/test_flextools_health.py` (CP2's file, a filesystem-mtime timing test) on one run, passed clean on immediate rerun and in isolation -- unrelated to my changes, not touched.

## Drafted issue (not filed)
**Title:** Raw liblcm UnitOfWork constructs (`BeginUndoTask`/`BeginNonUndoableTask`, `UndoableUnitOfWorkHelper`) silently discard writes since CP1's `undoable=False`
**Body:** CP1 (#92) made every write-enabled run hold one non-undoable UnitOfWork open for the session (`FLExProject.py:262-289`). A script calling `UndoStack.cs`'s `BeginUndoTask`/`BeginNonUndoableTask` a second time (`:187-264`) rolls back the already-open task via `Rollback(0)` before throwing -- this worked under the old `undoable=True` default (no session envelope was open to nest into) and is a new regression surface. Fix: the `nested_unit_of_work` pre-flight gate in this cycle. Own issue because it's a distinct regression discovered *after* #92 shipped (not a rider on #92, already merged/closed) and orthogonal to #93's shared-mode-access scope (CP2-CP6).

## Left undone
Second validate_only call site (documented above); diagnostic-report's `NON_REPORTABLE_CODES` doesn't classify the new code (fails open to non-reportable, out of this task's file ownership).
