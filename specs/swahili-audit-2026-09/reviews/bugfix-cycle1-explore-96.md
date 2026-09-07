# Explore -- root cause of #96 (A4), bugfix cycle 1

> Authored by the cycle-1 Explore agent (read-only investigation). The agent had no
> Write tool, so the main session committed this body verbatim to the lock-claimed
> path. Line numbers reflect committed `db52c3a` unless noted.

## 1. Teardown path (CONFIRMED)

`execution.py` generates a per-call subprocess runner. Open: `execution.py:3571` --
`project.OpenProject(PROJECT_NAME, writeEnabled=WRITE_ENABLED, undoable=False)`.
**No `ui=` argument**, so flexicon supplies WinForms `FwLcmUI`
(`flexicon/code/FLExLCM.py:98-100`) -- the SPEC section 4 hazard, live in the write path.

Teardown is only `execution.py:3747-3752`:

    finally:
        if project:
            try: project.CloseProject()
            except: pass

`result["success"] = True` is set at `execution.py:3722` -- **before** `CloseProject()`
runs. Any commit failure in teardown is swallowed by the bare `except: pass`. Success is
inferred from absence of an exception, and the exception is discarded anyway.

flexicon `CloseProject` (`FLExProject.py:318-337`): `EndNonUndoableTask()` :326 ->
`usm = ObjectRepository(IUndoStackManager)` :331 -> `usm.Save()` :332 -> `Dispose()` :334.
`usm.Save()` -> `UnitOfWorkService.SaveInternal`
(`liblcm/src/SIL.LCModel/Infrastructure/Impl/UnitOfWorkService.cs:293-343`) ->
`m_dataStorer.Commit(...)` :341. `Dispose()` -> `SharedXMLBackendProvider.ShutdownInternal`
(`SharedXMLBackendProvider.cs:126-196`): `CompleteAllCommits()` :131 then, **only
`if (metadata.Master == m_peerID)`** :140, flush foreign changes and set
`metadata.FileGeneration = metadata.CurrentGeneration` :157. A non-master peer takes the
`RemovePeer` branch :159 only.

**There is no flush, settle, or wait-for-master step anywhere.** `CompleteAllCommits` :131
waits on *this* process's `CommitThread` (`XMLBackendProvider.cs:472-477`), which for a
non-master peer is `null` -- `PerformCommit` is guarded by `if (metadata.Master == m_peerID)`
(`SharedXMLBackendProvider.cs:478-479`). It waits for nothing. The MCP never calls
`SaveChanges()` or `RefreshFromDisk()` (grep of `src/flextoolsmcp/`: zero hits).

## 2. Read side (CONFIRMED -- this is the root cause)

`SharedXMLBackendProvider.StartupInternal` :72-114: peer registers with
`Generation = metadata.FileGeneration` :100, then `ReadInSurrogates(currentModelVersion)`
:108 -- **not overridden**; it is `XMLBackendProvider.cs:169-172`, which reads
`ProjectId.Path`, i.e. the on-disk `.fwdata`. Startup **never replays** commit-log records
`FileGeneration+1 .. CurrentGeneration`.

`GetUnseenForeignChanges` (:504) has exactly two callers: `Commit()` :375 and the master's
`ShutdownInternal` :145. A read-only run (`writeEnabled=False`) never reaches `Commit`:
flexicon `CloseProject` skips the whole save block (`FLExProject.py:319-332` guard
`if self.writeEnabled`). So a fresh read-only session's view is *exactly* the last master
flush. It legitimately observed pre-write state. **No read path bypasses this.**
`RefreshFromDisk()` / `usm.Refresh()` does not help: `UnitOfWorkService.cs:392-395` is a
no-op unless `m_pendingReconciliation != null`.

## 3. The propagation contract (CONFIRMED -- load-bearing)

Class comment, `SharedXMLBackendProvider.cs:19-25`:

> "It uses memory mapped files to maintain a shared commit log that all applications use to
> update their state to reflect changes made by other applications... **A single peer is
> responsible for updating the XML file.**"

`CommitLogMetadata.cs:26-33`:

> `CurrentGeneration` -- "The current commit generation of the commit log."
> `FileGeneration` -- "The current commit generation of the **XML file**."

`CommitLogMetadata.cs:60-63`: `Master` -- "The GUID of the master peer that is
**reponsible for reading and writing to the XML file**."

Non-master `Commit()` (:361-487): writes a `CommitLogRecord` to shared memory :430-476,
`metadata.CurrentGeneration++` :481 -- and skips `PerformCommit` :478. `FileGeneration`
advances only in `WriteCommitWork` :499 (master) or master shutdown :157.

**Contract: a non-master peer's commit is durable and visible to LIVE peers, but only when
each of them next calls `Commit()`. It is visible to an INDEPENDENT LATER OPEN only after
the master writes the XML file. There is no propagation to a fresh reader at all.** 18 s is
not "inside a window" -- for a fresh read-only open the window is unbounded. Nothing is
dropped; the data was in the commit log the whole time.

The master's own flush is `SaveOnIdle` (`UnitOfWorkService.cs:225-262`, timer 1 s at :175):
floor of 10 s since last save :253-255, plus guards that need a human --
`m_pendingReconciliation != null -> return; // don't auto-save until the user Refreshes`
:245-246, and `TopMarkHandle != 0 -> return` :249-251 (an open FLEx editing slice). That is
why 18 s elapsed with no flush. HYPOTHESIS (not confirmed): one of those two guards was set
in PID 15400.

Secondary CONFIRMED hazard, worth its own issue: `XMLBackendProvider.WriteCommitWork`
:518-527 returns without writing if `m_lastWriteTime != currentWriteTime`
(`ksFileModifiedByOther`, via a modal `ReportProblem`), yet
`SharedXMLBackendProvider.WriteCommitWork` :499 sets `FileGeneration` unconditionally after
that early return -- metadata then claims a flush that never happened.

## 4. The 19:49 observation

Consistent with a delayed master flush, and it is the only explanation the source supports.
A fresh open at 19:49 reads `.fwdata` (:108), so the FTs must have been in the file by then;
`.fwdata` mtime 20:57 / `.bak` 20:52 shows the master wrote repeatedly. It does not point
elsewhere. It is *not* explained by the 19:49 session reconciling from the commit log:
reconciliation happens only inside `Commit()`, i.e. at that session's `CloseProject()` --
after its reads.

## 5. What the shared-mode work already knows

`specs/shared-mode-access/SPEC.md:53-58` already cites `SharedXMLBackendProvider.cs:102-118`
and "reads and writes through the shared commit log", and section 3 (:97-108) already knows the
master/peer split for custom fields (`CommitLogRecord.cs:16-49` is "not a member of
CommitLogRecord"). But **read-back visibility is nowhere in the SPEC**: section 8 Deferred
(:370-383) lists only the `_contract` envelope gap; section 7 verification (:330-368) asks only
"the change appears in the FLEx UI" (the master's own cache -- which *does* see it, via
`Commit` / `ReconcileForeignChanges` :381-384).

#93 CP4's live evidence (`specs/shared-mode-access/evidence/live-cp4.md`) proves peer writes
land -- but section 2 read the value back in a **third process opened after both others closed**,
i.e. after the master's shutdown flush (:140-157). It therefore cannot and does not bear on
read-back while the master is still alive. Section 6 ("Still owed") already states the
`open_shared` path was never exercised live. #96 is exactly that untested case.

## 6. Remedies, ranked by what the source supports

1. **Cache-bypassing verification read -- SUPPORTED, and the real fix.** `SaveInternal` calls
   `m_dataStorer.Commit(...)` (`UnitOfWorkService.cs:341`) even with empty
   newbies/dirtballs/goners; `SharedXMLBackendProvider.Commit` then runs
   `GetUnseenForeignChanges` :373 and `reconciler.ReconcileForeignChanges()` :381. A
   **write-enabled** verification session that calls `project.SaveChanges()`
   (`FLExProject.py:563-588`) *before* reading will ingest the prior session's records -- they
   are foreign to it, since `ReadUnseenCommitRecords` skips only `rec.Source == m_peerID`
   (:614) and the new subprocess has a new `m_peerID` (:45). And they are guaranteed present:
   purge requires `WriteGeneration <= FileGeneration` (:616), so a record is either still in
   the log or already in the XML. Constraints: needs `write_enabled=True` (flexicon raises
   `FP_ReadOnlyError` at :583) and `ReadyForBeginTask` (`UnitOfWorkService.cs:304`), so it must
   run at session start, before the `undoable=False` envelope -- i.e. it needs a flexicon entry
   point, not just an MCP change. Risk to handle: `OkToReconcileChanges()` false ->
   `ConflictingChanges` :362 -> `m_ui.ConflictingSave()` :372 -> with the current `FwLcmUI` that
   is a modal dialog. **Pass `ui=HeadlessLcmUI()` at `execution.py:3571` first.**
2. **Flush/settle on close -- PARTIALLY supported, insufficient alone.** A non-master peer has
   no API to make the master write; `SaveOnIdle`'s guards (:245-251) are human-gated. Best
   available: don't swallow `CloseProject()` (`execution.py:3749-3752`) and move `success`
   (:3722) to after it. Fixes the silent-failure half of #96, not the staleness half.
3. **Docs-only -- inadequate, and the reporter is right.** There is no reliable interval to
   document (the window is unbounded, per section 3). But docs are still owed: the truthful rule is
   "a fresh read-only session under a live FLEx master shows the last master save, not your
   write."

## 7. Minimal live repro (authorized by the user for `Target`, 2026-09-06)

Target: `Sena 3` or `Target`. Never `Claude-Swahili`.

Setup: open the disposable project in FieldWorks, sharing on (`projectSharing="true"` in
`SharedSettings\LexiconSettings.plsx`), leave FLEx focused on a *non-editing* view (so
`TopMarkHandle == 0`, `UnitOfWorkService.cs:249`). Confirm `probe_project_access` ->
`open_shared` with FLEx's PID.

1. **T0 -- write.** One `run_module`, `write_enabled=True`, setting **one** scalar on **one**
   object (`SenseOperations.SetGloss` on a `TEST_`-prefixed entry created in the same run).
   Record `lcm_undoable_action_count` and the wall clock.
2. **Read-back samples.** Fresh `run_module`, `write_enabled=False`, reading that same gloss,
   at **T0+2 s, +15 s, +30 s, +60 s, +180 s**. Record value + wall clock each time. Do not
   touch FLEx between samples.
3. **Instrument the master.** After each sample, `stat` the `.fwdata` mtime. The mtime crossing
   T0 marks the master flush.
4. **Discriminator.** One fresh `run_module`, `write_enabled=True`, that calls
   `project.SaveChanges()` **first** and then reads the gloss, taken while step 2 is still
   returning the stale value.

Predictions if the hypothesis holds: every read-only sample returns the **pre-write** value
until `.fwdata` mtime advances past T0, then all subsequent samples return the new value; and
step 4 returns the **new** value even while step 2 is still stale.

**Falsifiers.** (a) Any read-only sample returns the new value while `.fwdata` mtime is still
< T0 -> startup is *not* reading only the XML file; hypothesis dead. (b) Step 4 returns the
stale value -> `Commit`-driven reconciliation is not the mechanism; remedy 1 is dead and the
diagnosis needs reopening. (c) The value never appears even after `.fwdata` mtime advances ->
this is a genuine dropped write, not a visibility bug -- escalate to the `WriteCommitWork`
`FileGeneration` bug in section 3.

Cleanup: delete the `TEST_` entry in a final run; leave the project as found.

## Concurrency notes

- `execution.py` was **not** modified in `git status` at read time (only `validators.py` was),
  so line numbers reflect committed `db52c3a`. If the #103 agent lands changes, re-verify
  :3571 / :3722 / :3747-3752 offsets -- none of these conclusions depend on that agent's edits.
- `flexicon/code/FLExProject.py` was stable across all reads; no shifting observed.
  `WfiMorphBundleOperations.py` was not read.
