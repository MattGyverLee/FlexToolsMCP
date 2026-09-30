# QC Report -- cycle1 -- flexicon-project-bridge (FromOpenProject / US2)

Date: 2026-09-09 | Reviewer: QC Agent (read-only) | Scope: uncommitted diff, 5 files

> Persisted by the main session: the QC agent runs with Read/Grep/Glob only and
> could not write this file itself. Content is its report verbatim, followed by
> the main session's adjudication of the P0.

## Pattern-Audit Gate
N/A (one-off/feature) -- spec-driven feature work (tasks.md T001-T012), not a
`bug`-labelled fix or `closes #N` commit.

## Live-LCM Evidence Gate
N/A this cycle. `tests/test_from_open_project.py` disclaims
`requires_live_project` because the bridge opens nothing (research.md R6). Live
verification is scoped to US3 (T013-T016), gated on FieldWorks + human
authorization. No `evidence/` dir exists yet, which is correct for this phase.

## P0
- **`undoable_operation.py:86-106`** -- `__enter__` checks
  `self._project.writeEnabled` *before* `_undoable`/`_IsAttachedView`,
  contradicting `contracts/from-open-project.md` section 4's header rule:
  "All branch on `hasattr(self, '_attached_donor')` -- never on `writeEnabled`
  or `_undoable`." Consequence: a **read-only attached view** calling
  `UndoableOperation()` raises generic `FP_ReadOnlyError`, not
  `FP_TransactionError` with `_ATTACHED_VIEW_UNDOABLE_REFUSAL`. Contrast
  `SaveChanges` (`FLExProject.py:1089-1093`), which puts the attached-view check
  first. No test exercises a read-only view here, so the gap is invisible to the
  current suite.

## P1
- **`FLExProject.pyi`** -- module-level `_IsAttachedView`,
  `_ATTACHED_VIEW_SAVE_REFUSAL`, `_ATTACHED_VIEW_UNDOABLE_REFUSAL` are not
  declared, though `_attached_donor` (also private) already is at class scope.
  A `.pyi` shadows the runtime module for Pyright, so the lazy import in
  `undoable_operation.py:94-98` and the module-level import in
  `test_from_open_project.py:32-37` flag unknown-import-symbol even though
  runtime is correct. No CI Pyright/mypy gate exists, so this is IDE-only today.

## P2
- **`FLExProject.py:130-134`** -- the comment justifying the lazy reverse-import
  claims "FLExProject imports undoable_operation at module level." False: the
  only import is lazy, inside `UndoableOperation()` (`FLExProject.py:1426`). The
  lazy pattern is still correct, but the stated reason is wrong.

## Confirmed correct (no action)
- Exact-type exception pinning: `type(exc) is FP_RuntimeError` +
  `not isinstance(exc, (FP_ReadOnlyError, FP_TransactionError))`.
- Assertions against shipped constants, including
  `"CloseProject" not in _ATTACHED_VIEW_SAVE_REFUSAL`.
- Negative-proof spies for the `CloseProject` no-op.
- Guard ordering in `SaveChanges` / `CloseProject`.
- ASCII-only throughout; docstrings match implementation.

## Verdict
**FIX ISSUES** -- one P0, plus P1/P2.

---

# Main-session adjudication (2026-09-09)

**P0: REJECTED as stated; converted to a documented, tested decision.**

QC reads contract section 4's header as an ordering rule. It is not: "never
branch on `writeEnabled` or `_undoable`" is **Invariant A**, about how a guard
*detects* an attached view (`_attached_donor` is the only honest discriminator,
because a read-only owned project and a read-only view agree on `writeEnabled`).
It does not say an attached-view check must precede every unrelated pre-existing
check.

On the merits the current order is correct, and the asymmetry with `SaveChanges`
is principled rather than accidental:

- In `SaveChanges`, even a **write-enabled** view must refuse, and it must refuse
  *because the host owns the save*. Read-onlyness is not the reason, so
  `FP_ReadOnlyError` would misdescribe it. Attached-view check goes first.
- In `UndoableOperation`, a **read-only** view cannot write by any route.
  `FP_ReadOnlyError` ("not write-enabled") is true and actionable: the fix is for
  the host to open the project write-enabled. The attached-view message points at
  `Transaction()` -- which on a read-only project *also* fails. Emitting it would
  hand the user a wrong answer wearing the costume of a helpful one, which is the
  failure class this whole feature exists to end.

QC's real finding stands, though: nothing pinned this behaviour, so it was an
accident rather than a decision. Resolution:

1. Order left unchanged in `undoable_operation.py`.
2. Test added pinning `FP_ReadOnlyError` for a read-only attached view calling
   `UndoableOperation()`, so a future reorder is a deliberate act that breaks a
   named test rather than a silent behaviour change.
3. Comment added at the branch recording why the order is deliberate.

**P1: ACCEPTED** -- the three module-level names declared in the stub.
**P2: ACCEPTED** -- the false comment corrected. Note the same false claim exists
in the pre-existing comments in `undoable_operation.py`; the ones this feature
touched are corrected, and the untouched ones are left for a follow-up rather
than widening this diff.
