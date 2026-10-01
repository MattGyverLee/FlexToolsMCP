# Research: Exclusive-access gate and shared-mode follow-ups

Date: 2026-09-30. Worktree base: origin/main `db66f11`. LCM source:
`sillsdev/liblcm@master` (downloaded for this research). FieldWorks source:
`sillsdev/FieldWorks@main`. flexicon: local working tree `v4.11.0-4-g562d5f4`.
Line numbers drift; re-check before editing.

## R1. Where the gate goes in `run_module`

**Decision**: Detect exclusive-only calls before the access probe. When
`write_enabled` is true and any are found, force the probe. Put the refusal
right after the probe and read-back block (`execution.py:5257-5278`), **before**
the confirmation gate (`:5285`).

**Rationale**:
- Today `_probe_access = needs_lock or (not write_enabled)` (`:5257`). That skips
  the probe for a write-enabled run that certified read-only (`needs_lock`
  false), so a mis-certified script would get neither the probe nor the gate.
  Detecting first and forcing the probe closes that hole (spec FR-005).
- Refusing before the confirmation gate means the user is never asked to
  confirm a run that will be refused anyway.
- The predecessor ruled that the `project_locked` refusal must win. That still
  holds, because the two use disjoint verdicts. The new gate fires only on
  `open_shared` and `unknown`. `project_locked` fires only on `open_exclusive`
  and `held_by_other`.

**Alternatives considered**:
- After the `project_locked` refusal (`:5423`), as the predecessor's T5.3
  proposed. Rejected: that spot sits inside `if needs_lock`, so it misses the
  mis-certified case, and it comes after the confirmation round-trip.

**The gate does not apply to read-only runs** (`write_enabled=False`). They run
with `modifyAllowed=False`, so guarded mutations never execute. Unguarded
mutations are already refused at validation (constitution I).

## R2. How detection works

**Decision**: Add a new module, `server/exclusive_access.py`. It holds the
`EXCLUSIVE_ONLY_OPERATIONS` table and `detect_exclusive_only_operations(code,
tree, cert)`. Detection has two layers:

1. **Wrapper calls.** Take the `(class, method, line)` rows that
   `certify_script_readonly` already produces in `mutating_calls`,
   `protected_calls`, `unknown_calls` and the Step 2b `unresolved_receiver`
   rows (`validators.py:6327-6737`). Filter them against the table. This
   inherits every resolution rule the certifier has: Steps 1, 1b (facade and
   alias), 1c (accessor) and 2b (fail-closed receivers), so detection is never
   weaker than mutation detection. Guards are deliberately ignored: a guarded
   call still runs on a write-enabled run.
2. **Raw LCM calls.** Walk the AST, modelled on `detect_raw_addcustomfield_risk`
   (`validators.py:5789-5871`), and match the raw names in R3. Names that only
   exist on these interfaces (`AddCustomField`, `DeleteCustomField`,
   `AddToCurrentVernacularWritingSystems`, ...) match by attribute name alone.
   Generic names (`Set`, `Add`, `Remove`, `Save`, `Replace`, `GetOrSet`) match
   only when the receiver is the writing-system manager or one of the four
   writing-system lists, either directly in the attribute chain or through an
   alias assigned from it in the same scope.

**Rationale**: Comments and strings are invisible to the AST, so they don't
trigger. The existing certifier does no dead-code pruning, and this gate
follows it: a call inside `if False:` still counts, which fails closed. The
spec's acceptance scenario 1.6 is narrowed to comments and strings to match.

**Placement**: a separate module, not inside `validators.py` (8473 lines).
`validators.py` stays the source of the certifier rows. The new module only
reads them, so there is no parallel copy of detection logic (constitution VI).

**Index flags** (`flexicon_api_v4.11.0.json`):
- `WritingSystemOperations`: `Create`, `Ensure`, `Delete`, `SetFontName`,
  `SetFontSize`, `SetRightToLeft`, `SetDefaultVernacular` and
  `SetDefaultAnalysis` are `is_mutating: true`. That is exactly the class's
  mutating set.
- `Duplicate` is `is_mutating: false` and raises `NotImplementedError`, so it
  is left out of the table.
- `CustomFieldOperations` value methods (`SetValue`, `AddListValue`,
  `RemoveListValue`, `SetListFieldSingle`, `SetListFieldMultiple`,
  `ClearValue`) are also `is_mutating: true`. The table must name schema
  methods explicitly and must not derive its rows from `is_mutating`.
- Accessors: `project.WritingSystems` maps to `WritingSystemOperations`, and
  `project.CustomFields` to `CustomFieldOperations`. Both come from the index,
  not hardcoded (`validators.py:2577-2595`, `:6450-6456`).

## R3. Raw LCM names (VERIFIED in LCM source)

| Category | Names | Source |
|---|---|---|
| Custom field, metadata cache | `AddCustomField` (3 overloads), `UpdateCustomField`, `DeleteCustomField` | `LcmMetaDataCache.cs:920,1016,1068,1093`; `IFwMetaDataCacheManaged` |
| Custom field, FLEx route | `FieldDescription.UpdateCustomField()`; `MarkForDeletion = True` (assignment) | `FieldDescription.cs:336`; FW `AddCustomFieldDlg.cs:949` |
| WS manager | `Set`, `GetOrSet`, `Replace`, `Save` on `WritingSystemManager` | `WritingSystemManager.cs:271,287,331,346,412` |
| WS container | `AddToCurrentVernacularWritingSystems`, `AddToCurrentAnalysisWritingSystems` | `IWritingSystemContainer` |
| WS lists | `Add`/`Remove`/`Insert`/`Clear` on `VernacularWritingSystems`, `AnalysisWritingSystems`, `CurrentVernacularWritingSystems`, `CurrentAnalysisWritingSystems` | LangProject |
| WS services | `FindOrCreateWritingSystem`, `FindOrCreateSomeWritingSystem`, `UpdateWritingSystemFields`, `DeleteWritingSystem`, `MergeWritingSystems`, `UpdateWritingSystemId` | `WritingSystemServices.cs:1327-1665` |
| WS properties | assignment to `DefaultVernacularWritingSystem`, `DefaultAnalysisWritingSystem`, `DefaultFontName`, `DefaultFont`, `DefaultFontSize`, `RightToLeftScript` | flexicon `WritingSystemOperations.py` setters |

`WritingSystemManager.Create` returns a detached definition and does not
mutate anything, so it is not a row. flexicon's comment that `AddCustomField`
inside a task throws at `CheckNotProcessingDataChanges` is not supported by
LCM source. FLEx itself runs `UpdateCustomField` inside a non-undoable task.
That is noted for the upstream filing (R7), and it does not change the gate.

## R4. Undo of peer writes in FLEx (VERIFIED in LCM source)

**Finding**:
- A master picks up foreign changes only during its own `Commit`
  (`SharedXMLBackendProvider.cs:378-485`). There is no timer.
- `ChangeReconciler.ReconcileForeignChanges` (`ChangeReconciler.cs:200-204`)
  wraps them in a `NonUndoableUnitOfWork` and calls
  `NonUndoableStack.AddForeignBundleToUndoStack` (`UndoStack.cs:859-870`).
- `UnitOfWorkService` starts with fresh, empty stacks (`:169-172`), and
  nothing loads undo history.

So FLEx's Undo cannot reverse a peer write, whether FLEx was open or closed at
the time. The spec's Section 2 is amended to say so. A live Edit > Undo check
is still recorded as evidence (quickstart V6), and is not a blocker.

**Consequence**: There is nothing for the MCP to supply to FLEx. Undo of MCP
writes, if wanted, means programmatic undo inside one `run_module` process.
Under `undoable=True` LCM does keep a per-process undo stack, so that is
possible, but it is out of scope.

## R5. Read-back sync (US5)

**Finding**:
- The MCP opens projects with `undoable = "per-operation-uow" in
  flexicon.CAPABILITIES` (`execution.py:4855`). The current flexicon
  advertises that capability, so the default is `undoable=True`.
- `SyncForeignChanges()` raises `FP_TransactionError` under `undoable=True`.
  The equivalent is `SaveChanges()` at depth 0. Both raise `FP_ReadOnlyError`
  when the project is not write-enabled (`FLExProject.py:1286-1383`, and
  `SaveChanges`).

**Decision**: The generated runner (`execution.py:4872-4892`) gains an
optional "sync at open" step. It runs only when `WRITE_ENABLED` is true and
the probe reported `open_shared`, and it calls `SaveChanges()` or
`SyncForeignChanges()` to match `_undoable`. A failure is logged and reported
as a note and never fails the run. The step ships only if live check V5 shows
it makes a prior peer write visible. Otherwise only the note text changes.

**Alternatives considered**:
- Opening a writable session for read-only read-backs. Rejected by the spec,
  because it would take the write path's lock and backup steps just to read.

## R6. Error-contract placement

**Decision**: Add the new code `requires_exclusive_access` as a purely
additive change under the current contract major. That means:
- A detail model `RequiresExclusiveAccessDetail` (`extra="forbid"`) next to
  `ProjectLockedDetail` (`response_models.py:396`), added to the `AnyDetail`
  union (`:979-1026`).
- A golden fixture (`tests/make_golden.py:105`).
- `ALL_ERROR_CODES` and the per-code maps in `tests/test_response_contract.py`
  (`:169-367`).
- Updating the count from 46 to 47 in `test_response_contract.py:521-522`,
  `docs/TOOL-CONTRACT.md:82` and the `response_models.py` docstring, plus
  fixing the stale "44 codes" text at `TOOL-CONTRACT.md:721`.
- A hint in `_ASSISTANCE_HINTS_BY_ERROR_CODE` (`session.py:33`).

The most recent code to model on is `atomic_property_iteration` (#313). Its
CHANGELOG entry is missing, so use `recipe_not_found` (CHANGELOG:69-72) as
the CHANGELOG model instead.

**validate_only**: add a sibling key `project_lock.exclusive_access` holding
`{required, operations, blocking}`. Appending a key is allowed, and the
existing `blocking` semantics are left untouched.

## R7. Messages that conflict with shared mode (FR-011, FR-013)

- `_diagnose_project_open_error` (`execution.py:1223`, hint at `:1265-1271`)
  keeps the generic "Close FieldWorks and retry" message whenever
  `build_lock_diagnosis` returns None. That covers `free` and `open_shared`
  (`project_access.py:367`). **Decision**: on `open_shared`, give a
  shared-mode message instead: sharing is on, so the lock is not the cause;
  report the underlying error.
- `write_ladder.py:157-158` has similar fallback guidance. It gets reviewed in
  the same task.
- The `open_shared` advisory (`write_ladder.py:172-179`) ends with "Custom-field
  and writing-system changes are NOT safe from a peer...". **Decision**:
  replace it with a pointer to the gate.
- Pattern audit: grep `src/` for other "Close FieldWorks" and "close FLEx"
  guidance strings and list each sibling in the commit body.

## R8. Parse filing

A grep of `handlers/parse*` and `filing/` found no writing-system or
custom-field mutators. The only hit is a read of
`VernacularDefaultWritingSystem` (`filing/eligibility.py:274`). **Decision**:
the gate stays out of the filing path. A unit test pins this by running the
detector over the filing worker source and asserting zero matches.

## R9. Live test for the custom-field hazard (US3)

**Finding**:
- A peer cannot persist a custom-field definition. `CommitLogRecord` carries
  only object adds, updates and deletes (`CommitLogRecord.cs:23-48`), and
  `PerformCommit` writes only the master's own custom-field list
  (`SharedXMLBackendProvider.cs:429,479`).
- flexicon's `CreateField` always refuses (`CustomFieldOperations.py:305-333`),
  and `DeleteField` raises `NotImplementedError`.

**Decision**: replace CP5-a with a harness that runs outside `run_module`,
modelled on the archived `evidence/live_shared_peer.py`. With FLEx open on
Sena 3 in shared mode, a peer:
1. Builds `FieldDescription(cache)` for `zzExclTest`.
2. Calls `UpdateCustomField()` inside a non-undoable task.
3. Commits.

The test records whether the field shows in FLEx, then closes and reopens FLEx
and records whether the definition survived. The expected result is that it is
gone (Class B). It writes **no data** to the field, so a lost definition
cannot leave orphan data behind. If the definition does survive, it is deleted
through FLEx's Custom Fields dialog. Closing and reopening FLEx needs a human,
so this task is `needs-human`.

## R10. Constitution wording (out of scope, flagged)

Constitution I still says "Rollback is reviewed, never automatic. Undo returns
the operation to be undone." That describes the removed undo tool. Changing it
is a governance amendment, so it is flagged for the maintainer and not changed
here.

## R11. Upstream filing (US6)

Before filing, check each of the four hazards against flexicon `v4.11.0-4`:
- `ConflictingSave` modal: `FwLcmUI` is still passed (`FLExLCM.py`). Check
  whether `headless_ui.py` now replaces it.
- `BeginUndoTask` arity.
- `_transaction_depth` leak.
- `RollbackToMark`.

Also add the R3 note about the inaccurate `CheckNotProcessingDataChanges`
comment. Filing needs the maintainer's OK per item (`needs-human`).
