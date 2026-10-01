# Filing ledger (US6, FR-040/FR-041)

Checked 2026-09-30 against flexicon `v4.11.0-4-g562d5f4` (C:\Github\flexicon)
and open + closed issues on MattGyverLee/flexicon and MattGyverLee/FlexToolsMCP
(`gh issue list --state all --search`). **Nothing has been filed.** Each
"STILL NEW" row waits for the maintainer's OK (T035); fill in "Authorized by"
and the issue number when it is filed.

## Upstream hazards (T033)

| Item | Target repo | Check result | Outcome | Authorized by |
|---|---|---|---|---|
| ConflictingSave modal (`FwLcmUI` default) | flexicon | `FLExLCM.py:111-112`: `if ui is None: ui = HeadlessLcmUI()`; a conflict raises `FP_ConflictingSaveError` | already fixed in `cb1d355` (flexicon#285, v4.6.0) | n/a |
| `BeginUndoTask` arity | flexicon | no direct calls left; `UndoableUnitOfWorkHelper(handler, label, label)` at `transaction.py:124`, `undoable_operation.py:146` | already fixed in `287bb20` (flexicon#233) | n/a |
| `_transaction_depth` leak | flexicon | counter removed; depth read from `ActionHandlerAccessor.CurrentDepth` (`FLExProject.py:413-419`) | already fixed in `287bb20` (flexicon#234) | n/a |
| `RollbackToMark` in `Transaction()` | flexicon | no `RollbackToMark` left; only `Rollback(0)` (`FLExProject.py:1551`) | already fixed in `b3a5bb9` (flexicon#236) | n/a |
| `CreateField` comment: AddCustomField in a task throws at `CheckNotProcessingDataChanges` (research R3) | flexicon | still at `System/CustomFieldOperations.py:292-294` and in the raised message `:308-311`; LCM source does not support it (FLEx runs `UpdateCustomField` inside a non-undoable task) | STILL NEW (doc/message accuracy; low) | |

## Archived drafts (T034, `specs/shared-mode-access/issues/DRAFT-issues.md`)

| Item | Target repo | Check result | Outcome | Authorized by |
|---|---|---|---|---|
| flexicon-1 `SemanticDomainOperations.GetAll(recursive=False)` returns an interleaved list | flexicon | unchanged (`SemanticDomainOperations.py:134`, `FLExProject.py:3806-3809`); `GetSubdomains(recursive=False)` :650 is the model fix | STILL NEW | |
| flexicon-2 default-WS resolution breaks semantic-domain name read/write | flexicon | `GetName` :318-320, `FindByName` :237, `SetName`/`Create` :399-401 still use `DefaultAnalWs`; closed flexicon#183 fixed only `GetNumber`/`Find` | STILL NEW (follow-up to closed #183) | |
| flexicon-3 `ReversalIndexes.Create` accepts a vernacular WS | flexicon | no analysis-WS guard (`ReversalIndexOperations.py:173-180`) despite docstring :113/:150 | STILL NEW | |
| flexicon-4 `ReversalIndexes.SetName` targets a FLEx-derived field | flexicon | no caveat; still writes analysis default (:366-400) | STILL NEW | |
| flexicon-5 `report.Info` output lost when an exception escapes | **FlexToolsMCP** (misfiled in the draft) | `execution.py` run_module exception handler sets only `result["error"]`, never `messages`; sibling `run_scan` does | STILL NEW (retarget to FlexToolsMCP) | |
| flexicon-6 `WritingSystemOperations.Delete` leaves LDML / `.plsx` residue | flexicon | `WritingSystemOperations.py:429-500` removes only from the lists; related closed #179, #250 cover Create/Exists | STILL NEW | |
| flexicon-7 peer-written `idchangelog.xml` entries carry `Producer="???"` | flexicon | no Producer handling in flexicon | STILL NEW (low) | |
| flexicon-8 `project.Object(guid)` returns an uncast `ICmObject` | flexicon + FlexToolsMCP primer | crash fixed: `cast_to_concrete` in `66e61c6` (flexicon#269, #333 closed); `project.Object` deliberately uncast; primer (`handlers/admin.py:265-275`) has no cast note | flexicon half: already fixed (#269); primer-wording half: STILL NEW, optional, low | |
| flexicon finding (b) `undoable=False` / no rollback-to-mark (comment on #236) | flexicon / FlexToolsMCP | flexicon#236 closed (RollbackToMark fixed); MCP runner uses `undoable = "per-operation-uow" in CAPS` since `0d3a791` | duplicate of closed FlexToolsMCP#144; do not comment on #236 | n/a |
| flextoolsmcp-1 `_pid_is_alive` reports a dead PID alive | FlexToolsMCP | `project_access.py:169-183` checks `GetExitCodeProcess == STILL_ACTIVE` | already fixed in `a8cf35b` (#93) | n/a |
| flextoolsmcp-2 empty `mutations_detected` / self-contradictory refusal | FlexToolsMCP | `execution.py` branches on an empty list | duplicate of closed #105 / #131 (fixed `ee53b11`) | n/a |
| flextoolsmcp-3 `ENABLE_SHARING_REMEDY` overstates the reopen requirement | FlexToolsMCP | `project_access.py:280-283` says reopening is recommended, not required | already fixed in `a8cf35b` | n/a |
| flextoolsmcp-4 server restart voids write-discovery state | FlexToolsMCP | not documented; closed #42, #29 cover other cases | STILL NEW (doc only, optional) | |

## Found during this feature (T039 sweep, `reviews/sweep-detector.md`)

| Item | Target repo | Check result | Outcome | Authorized by |
|---|---|---|---|---|
| `_collect_local_container_names` treats a loop target over a list of LCM collections as a local container, so `coll.Add(s)` is dropped from the unprotected-writes gate (`validators.py:5982-5989`, `6009-6010`, `6056-6060`) | FlexToolsMCP | from static reading; not reproduced | STILL NEW (candidate; reproduce before filing) | |
| Write-gate regexes without a left word boundary (`validators.py:100`, `160-165`, `65/73/86`, `137-144`) over-match `myproject.X.Delete(` and `position.Note =` | FlexToolsMCP | over-match only (fail-closed) | STILL NEW (low; candidate) | |
| V7 could not run (if it does not) | liblcm / FieldWorks | per FR-014: file the Class B gap upstream | pending T030 | |
