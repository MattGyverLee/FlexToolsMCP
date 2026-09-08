# SPEC -- Shared-mode access: let the user keep FLEx open

**Feature:** `shared-mode-access`
**Status:** CP1 implementation underway (cycle 1)
**Branch:** `feat/shared-mode-access`
**Filed issues:** #92 (bug, prerequisite -- broken write path / undo removal), #93 (enhancement, this feature's CP2-CP6 scope)
**Source plan:** `C:\Users\thoua\.claude\plans\early-versions-of-this-compressed-scott.md`

---

## 1. Context

Early versions of this MCP happily opened projects that FLEx had open. Two
incidents narrowed that: custom-field creation needed FLEx closed, and `undo`
appeared to need an exclusive connection. The response was to broaden the lock
gate until, in practice, the MCP became unusable while FLEx was open. That was
an over-correction -- the single most valuable thing about editing a FieldWorks
lexicon is *watching the change land in the UI*.

Research established four facts that change the shape of the fix:

1. **Writes are broken right now, in the default configuration.** Issue #55
   Rung 1 made `undoable=True` the default whenever `write_enabled=True`. In
   undoable mode flexicon's `OpenProject` deliberately skips
   `BeginNonUndoableTask()` and opens no UnitOfWork (`FLExProject.py:229-247`),
   so multi-mutation methods hit a one-argument `_begin_undo_fn` against LCM's
   two-argument `BeginUndoTask(bstrUndo, bstrRedo)` (`DomainDataByFlid.cs:805`)
   -> `TypeError`; simple setters (`SetGloss`, `SetLexemeForm`, `Delete`) hit
   `UnitOfWorkService.RegisterCommon` with `CurrentProcessingState ==
   ReadyForBeginTask` -> `InvalidOperationException: "Not in the right state to
   register a change."` (`UnitOfWorkService.cs:562-568`); `transaction.py:69`
   increments `_transaction_depth` before `__enter__`, so after the first
   failure the depth is stuck at 1 for the process lifetime. Confirmed live:
   `~/.flextoolsmcp/logs/operations.log:26095` against `Ejagham Full GT-Test`
   (`No method matches given arguments for ISilDataAccess.BeginUndoTask:
   (<class 'str'>)`), and line 26096 then logged `[OK] Operation completed
   successfully` -- the tool reports success on a write that never happened.
   Zero end-to-end coverage: `operations.jsonl` has 27 `write_enabled: true`
   records and 0 with `undoable: true`. **Tracked as #92.**
2. **`flextools_undo_last_operation` has never worked and cannot work.** LCM's
   undo stack is `Stack<UnitOfWork>` in RAM holding live `ICmObject`
   references, with no serializer (`UndoStack.cs:88`); nothing writes undo
   records to `.fwdata`. The MCP opens and closes the project in a fresh
   subprocess per call, so every undo attempt starts from
   `UndoableActionCount == 0`, and `UndoStack.Undo()` on an empty stack
   throws. Independently, flexicon's `FLExProject.Undo()` reads
   `self.project.UndoStack`, not a member of `LcmCache` -- `AttributeError`
   -> `FP_TransactionError`, unconditionally, in every process. "Close FLEx to
   unlock undo" trades away nothing.
3. **Shared access hinges on one flag we can read for free.** LCM takes the
   exclusive `.fwdata.lock` on *any* open unless `projectSharing="true"` in
   `<Project>\SharedSettings\LexiconSettings.plsx` (`LcmCache.cs:219`), read
   once at cache-open. When it is on and FLEx opened first, our process
   attaches as a non-master peer, skips `LockProject()`, and reads and writes
   through the shared commit log (`SharedXMLBackendProvider.cs:102-118`).
4. **The `.fwdata.lock` file is not opaque.** It is JSON --
   `{"PID":68436,"ProcessName":"FieldWorks","Timestamp":...}` (verified live).
   That resolves the stale-lock ambiguity `sweep_stale_locks()` currently
   documents as unknowable, and distinguishes "FLEx has it" from "a dead
   process left a lock" from "another MCP holds it".

**Intended outcome:** writes work again; read-only exploration always works
with FLEx open; writes work in shared mode without ceremony; the user is asked
to close FLEx only for operations a non-master peer genuinely cannot perform,
and can reopen immediately after.

---

## 2. Settled -- do not revisit

These decisions were made with the user and are not open for re-litigation by
the crew. (Verbatim from the approved plan.)

> - **No shared-mode consent gate.** With no undo to trade away, there is
>   nothing to consent to. Do everything safely doable in shared mode,
>   silently.
> - **Never write `LexiconSettings.plsx`.** When sharing is off, instruct the
>   user to enable it in FLEx, then *verify on the next call* and proceed.
> - **Delete `flextools_undo_last_operation`** and the false claims around it.

Execution constraints (also settled):

> Run through **`/lex-lead`** (dispatch-plan protocol) on a feature branch off
> `main`. Merge to `main` only after CP1 and CP5's live checks pass against a
> real project. Repo is at `2.9.1`; conventional commits with `closes #N`, and
> every PR owes a `CHANGELOG.md` `[Unreleased]` entry per `CONTRIBUTING.md:66-92`.
>
> File issues first: the broken write path (CP1) is a distinct bug from the
> shared-mode feature and deserves its own issue and its own commit.

(Executed this cycle: #92 filed for CP1, #93 filed for CP2-CP6.)

---

## 3. The exclusive-only operation tables

The user asked for the full list, not just custom fields. Each entry is
backed by source, and each is a reason to ask the user to close FLEx
briefly -- but "exclusive-only" is not one failure mode. It was scoped as
two; live evidence from the 2026-09-08 session (see `evidence/live-cp4.md`
"# Session 2026-09-08") forced a third, added below:

- **Class A -- LCM refuses outright.** Data migration and project rename
  are safe *by construction*: the caller gets an exception, nothing is
  written, nothing is lost.
- **Class B -- LCM permits the write and silently swallows it.** Custom
  fields get **no exception, no retry, and no second chance** -- the
  schema change is simply absent after the next restart. **Class B is the
  only class that requires a gate.** Class A needs no alarm; LCM already
  tells the user. Nothing else will ever catch a Class B loss, which is
  why CP5 exists at all.
- **Class C -- LCM permits the write and it crashes the FLEx holder.**
  Added 2026-09-08 (3c below). Neither `refused` nor `silently_lost`: the
  write reaches disk on both legs and then brings the live FLEx master
  down. Needs a gate at least as strongly as Class B, for a different
  reason.

**Scoping note, added 2026-09-08.** "Safe by construction" in the Class A
bullet above describes the `refused` mechanism ONLY -- LCM raises before
anything is written. It does not extend to an operation that writes
successfully and is safe for some other, empirically-verified reason (3a-ii
below, possibility lists) or unsafe in a way that is neither refusal nor
silent loss (3c below, writing systems). "Class A" is not a synonym for "no
CP5 gate needed" -- check the mechanism, not just the outcome.

**The Class B mechanism (custom fields), re-derived from liblcm source, not
taken on trust:** `PerformCommit` is the only path that writes
`<AdditionalFields>` to the XML file, and it is gated
`if (metadata.Master == m_peerID)` (`SharedXMLBackendProvider.cs:478`, also
`:408`). A non-master peer's `HaveAnyModifiedCustomProperties`
(`BackendProvider.cs:506-515`) clears and rebuilds `m_extantCustomFields`
from the live MDC on every commit, so the peer's own bookkeeping believes
the field was recorded -- then the declaration is discarded. The next
commit sees no diff and never retries. `CommitLogRecord`
(`CommitLogRecord.cs:17-49`) has no field for custom-field schema at all,
so it cannot even ride along to the master. Net effect: no exception, no
error, no second chance. The field simply does not exist after restart.

**Precedent: FieldWorks gates this identically in its own UI.**
`XWorksViewBase.cs:715` refuses to open the Custom Fields dialog when
`SharedBackendServices.AreMultipleApplicationsConnected(cache)` is true.
CP5 is not inventing a restriction -- it is matching one FLEx already
enforces on itself. (FLEx's `ProjectsInUseLocally` guard, `FieldWorks.cs
:813,1988`, enumerates only .NET-Remoting clients and is structurally
blind to a pythonnet peer, so we cannot rely on FLEx to stop us instead.)

### 3a. Class A -- LCM refuses outright (`failure_class: refused`)

| Operation | Why a non-master peer cannot do it | Evidence | failure_class |
|---|---|---|---|
| **Project rename** | LCM refuses outright when peers are attached. | `SharedXMLBackendProvider.cs:637-641` (`OtherApplicationsConnectedCount > 0`) | `refused` |

### 3a-ii. Also safe, no CP5 gate -- succeeds and persists (`failure_class: safe`)

Different mechanism from 3a: nothing refuses the write. Verified safe by
live restart evidence, not by inference. Added 2026-09-08, resolving
`live_session_checklist` OPEN Q2.

| Operation | Why it needs no gate | Evidence | failure_class |
|---|---|---|---|
| **Possibility-list item add/rename** (semantic domains, POS, morph types) | A peer write (add or rename) is applied, visible in the FLEx UI immediately, and durable across a full FLEx close/reopen -- the restart discriminator that separates this from Class B. | `evidence/live-cp4.md` Item 6: write `:1149-1165`, human observation `:1172-1189`, restart discriminator `:1191-1209` | `safe` |

The naive `Create`/`SetName` call writes the name into the analysis-default
writing system only, so a domain created or renamed with the obvious call
can look unnamed/unchanged to an English-reading user. Real defect, but a
flexicon one, not a shared-mode one (finding (g), flexicon tracker).

### 3b. Class B -- LCM permits it and silently swallows it (`failure_class: silently_lost`)

| Operation | Why a non-master peer cannot do it | Evidence | failure_class |
|---|---|---|---|
| **Custom field create/delete/update** | See the Class B mechanism above: `<AdditionalFields>` is written only by the master, `HaveAnyModifiedCustomProperties` self-updates the peer's own bookkeeping so there is no second chance, and `CommitLogRecord` has no custom-field schema field to ride along on. | `SharedXMLBackendProvider.cs:478,408`; `BackendProvider.cs:506-515`; `CommitLogRecord.cs:17-49`; precedent `XWorksViewBase.cs:715` | `silently_lost` |

Writing systems were provisionally listed in this class before live
evidence existed. **Moved to 3c below** -- live-tested 2026-09-08; the
actual outcome is worse than `silently_lost`, and is a different class,
not a relabeling within this one. The Class B mechanism itself (the
liblcm-source derivation above, for custom fields) remains untested live;
CP5 is being built on inference for that row too -- see the note under
Session 2 preconditions in `evidence/live-session-checklist.md`.

### 3c. Class C -- LCM permits it and it crashes the FLEx holder (`failure_class: crashes_holder`, NEW 2026-09-08)

Neither prior class fits this outcome: the write is not `refused` (both
legs reached disk, verified independently of the LCM read-back) and it is
not `silently_lost` (nothing was lost -- it landed and stayed landed). The
failure is that a live, non-master write to this data corrupts the FLEx
**master's running state**, not the data. Refusing the operation is not a
defensive nicety here; it is the only response that keeps FLEx usable.

| Operation | Why a non-master peer cannot do it | Evidence | failure_class |
|---|---|---|---|
| **Writing system add/modify** | A peer `WritingSystemOperations.Create`/`SetFontSize` write reaches disk on both legs (`.ldml` + `SharedSettings/LexiconSettings.plsx`) with no refusal, then crashes the live FLEx holder on its next idle/activate cycle: `NullReferenceException` in `WritingSystemListHandler.AddWritingSystemList`, `Src/xWorks/TextListeners.cs:286`, reached from the toolbar's WS-combo population. Confirmed live (resolves `live_session_checklist` OPEN Q1). The current advisory-note response (a `shared_mode.note` string in a JSON field the user never reads) is inadequate; this row **MUST BE REFUSED** with `requires_exclusive_access`. | `evidence/live-cp4.md` Item 5: write `:1310-1323`, both-legs-on-disk check `:1325-1345`, crash stack + FLEx log timeline `:1347-1382` | `crashes_holder` |

`WritingSystemOperations.Delete` is also an incomplete mitigation: finding
(l) (`evidence/live-cp4.md:1463-1499`) shows it clears the LCM model but
leaves the `.ldml` file and the `.plsx` entry on disk, risking FLEx
re-ingesting (and re-crashing on) the same writing system on its next
open. Flagged for the flexicon tracker; not fixed by the CP5 gate.

### 3d. Retired questions (formerly "3c. Unclassified -- pending live test")

Empty as of 2026-09-08. All three OPEN questions this subsection existed to
hold are resolved: Q1 -> 3c above (`crashes_holder`), Q2 -> 3a-ii above
(`safe`), Q3 -> **removed from this table entirely**. Q3 (reversal index
create/regenerate) is not a shared-mode failure: it splits into two
ordinary flexicon bugs -- `ReversalIndexes.Create` accepting a
non-analysis writing system (finding (h)) and `SetName` targeting a
FLEx-derived field that regenerates itself on open regardless of who wrote
it (see `evidence/live-cp4.md` "REFRAMING" `:1080-1137`, and the
"RETRACTION" at `:1012-1079` for the withdrawn manage-layouts reading).
Neither belongs in a shared-mode exclusive-access table. Kept empty rather
than deleted, so a future maintainer does not read the disappearance as an
oversight.

### 3e. Unreachable from this MCP (not gated)

These are Class-A-shaped (LCM or FLEx itself refuses or blocks them) but
have **no callable surface from this MCP at all** -- there is nothing for
T5.1/T5.2 to detect, so they are documented here for completeness and
explicitly **not** added to `EXCLUSIVE_ONLY_OPERATIONS`.

- **Data migration** -- flexlibs sets `DisableDataMigration = True`
  unconditionally (`FLExLCM.py:92`); non-master peers additionally throw
  `LcmDataMigrationForbiddenException` (`SharedXMLBackendProvider.cs
  :108-111`).
- **Send/Receive** -- FLEx blocks S/R while other applications are
  connected (`FLExBridgeListener.cs:314`); this MCP has no S/R tool.
- **Project backup / restore / delete** -- this MCP's own pre-write backup
  is a plain file copy, not a call into FLEx's restore/delete machinery;
  there is no tool surface that invokes FLEx's backup/restore/delete APIs.

---

## 4. Known hazard (accepted, documented, filed upstream)

flexicon passes `FwLcmUI` to LCM (`FLExLCM.py:88`). On a save conflict LCM
calls `ConflictingSave()`, which opens a **modal WinForms dialog with no close
box** from our headless subprocess (`FwLcmUI.cs:47`,
`ConflictingSaveDlg.Designer.cs:86`) -- and its polarity
(`result != DialogResult.OK`) makes the fail-safe default `true` ->
`RevertToSavedState()`, silently discarding our writes. Separately,
`DisplayMessage` from LCM's commit thread does `Control.Invoke` against a
window with no message pump, which deadlocks. This is flexicon's bug to fix,
not ours:

- Rely on the existing subprocess timeout + process-tree kill
  (`subprocess_helpers.py:108-117`).
- When a run times out **and** the probe reported a live FLEx peer, say so in
  the timeout message.
- Document in `docs/SHARED-MODE.md`; file upstream flexicon issues for this,
  the `BeginUndoTask` arity bug, the `_transaction_depth` leak, and
  `Transaction()`'s call to a nonexistent `RollbackToMark`.

## 5. Out of scope

- Repairing flexicon's `Undo()` / `Transaction()` / `BeginUndoTask` arity bugs
  or its `RollbackToMark` call to a method that exists nowhere in liblcm.
  Filed upstream; CP1 routes around them using the working `undoable=False`
  path.
- Reading `<ProjectName>_CommitLogMetadata` shared memory to enumerate peer
  PIDs. It works (verified), but the `.fwdata.lock` JSON plus a liveness
  check covers every case we gate on, without .NET interop in the server
  process.
- Any automated restore. `docs/RECOVERY.md:88-98` argues against it, and
  nothing here changes that.

---

## 6. Checkpoints

### CP1 -- Fix the write path; delete undo *(ships first, standalone; tracked as #92)*

This is a production bug fix and it unblocks everything after it: shared-mode
writes cannot be verified while writes fail outright.

- **T1.1** Hardcode `undoable=False` at the generated `OpenProject` call
  (`execution.py:3505`), so flexicon takes the `BeginNonUndoableTask()` path
  that actually works. Remove the `undoable` session flag and its plumbing
  (`session.py`, `admin.py:423-444`, `execution.py:2480`).
- **T1.2** Remove `flextools_undo_last_operation`: `tool_definitions.py:416-439`,
  the `dispatch.py:258` entry, `UndoLastOperationInput` (`models.py:120-129`),
  `handle_undo_last_operation` (`handlers/admin.py:683-784`), and
  `undo_subprocess.py` entirely.
- **T1.3** Delete the false warning at `admin.py:534-541` ("can reverse them
  across MCP sessions") and the `undo_available` / `redo_available` fields in
  `get_session_history` (`admin.py:647-680`).
- **T1.4** Delete the dead Feature-3 undo machinery: `record_operation`,
  `undo_stack`, `redo_stack`, `pop_undo`, `pop_redo`, `can_redo`
  (`session.py:430-518`) -- `record_operation` is never called from production
  code, so `get_session_history` has always reported `total_operations: 0`.
  Also `undo_checkpoints` and its rollover logging (`execution.py:4123-4143`).
- **T1.5** Stop reporting success over a failed write: if the run emitted any
  `report.Error`, the operation must not be logged or returned as a clean
  success.
- **T1.6** Delete `tests/test_undo_wiring.py`. Add the end-to-end write test
  that was never written: open a scratch project, `SetGloss`, `CloseProject`,
  reopen, assert the value persisted. Mark `requires_flex`.

**Checkpoint:** CP1 lands as its own commit closing #92, verified by
Verification step 1 (live, FLEx closed) before any CP2+ work is merged.

### CP2 -- Access probe (new detection, no behavior change)

- **T2.1** New `src/flextoolsmcp/server/project_access.py` -- pure filesystem +
  stdlib, matching `project_discovery.py`'s documented I/O constraint
  (registry read, `listdir`, `stat`; never opens the project).
- **T2.2** `read_lock_holder(project_name) -> Optional[LockHolder]` -- parse
  the `.fwdata.lock` JSON for `PID` / `ProcessName` / `Timestamp`; tolerate an
  unparseable or empty lock file by returning a holder with unknown fields.
- **T2.3** `_pid_is_alive(pid)` -- stdlib only:
  `ctypes.windll.kernel32.OpenProcess` with
  `PROCESS_QUERY_LIMITED_INFORMATION` on Windows, `os.kill(pid, 0)` on POSIX.
  Do not add psutil -- `subprocess_helpers.py:29` records the deliberate
  decision to keep it out of runtime deps.
- **T2.4** `is_project_sharing_enabled(project_name) -> Optional[bool]` --
  parse the root `projectSharing` attribute of
  `<Project>\SharedSettings\LexiconSettings.plsx` with `xml.etree`. Missing
  file -> `False`. Unreadable -> `None` (fail open).
- **T2.5** `probe_project_access(project_name) -> ProjectAccess` -- composes
  into a verdict: `free` | `open_shared` | `open_exclusive` | `stale_lock` |
  `held_by_other`, plus `sharing_enabled`, `holder`, `lock_age_seconds`. Reuse
  `get_projects_directory()` and `_FWDATA_EXT` from `project_discovery.py`
  rather than re-deriving paths.
- **T2.6** Rewrite `sweep_stale_locks()` on top of `read_lock_holder` +
  `_pid_is_alive`, so its warning can finally name the holding process and
  whether it is alive. Keep detection-only, no deletion.
- **T2.7** Wire into `flextools_health(verbose=True)`: replace
  `_build_project_lock_block()` (`handlers/diagnostic_health.py:276`) with a
  `project_access` block -- pure composition, no side effects, never opens a
  project.

**Checkpoint:** CP2 lands with `tests/test_shared_mode_access.py` passing
(see Verification step 2) and no change to any existing gate's behavior.

### CP3 -- Read-only always works

The gate at `execution.py:3792` already fires on write intent only, so reads
are *permitted* by the MCP today; they still fail inside LCM when sharing is
off. Close that gap.

- **T3.1** Extend `_diagnose_project_open_error` (`execution.py:1179-1206`).
  On the `FP_FileLockedError` / `LcmFileLockedException` markers, call
  `probe_project_access` and emit a specific diagnosis instead of the generic
  hint.
- **T3.2** Sharing **off** + live FieldWorks holder -> the enable-sharing
  recipe (close FLEx -> Project Properties -> Sharing tab -> "Share project
  contents with programs on this computer" -> OK -> reopen FLEx), stating that
  the next call verifies and continues automatically.
- **T3.3** Holder PID **dead** -> say the lock is stale and name the dead PID.
- **T3.4** Holder is another python/MCP process -> say so; a real collision.
- **T3.5** Enrich the `project_locked` detail model (`response_models.py:262`)
  with `sharing_enabled`, `holder_pid`, `holder_process`, `remedy`. It is
  `extra="forbid"`, so the model must be extended before the handler can send
  these.

**Checkpoint:** CP3 lands with a read-only `run_module` against a
sharing-off, FLEx-open project returning the enable-sharing remedy instead of
the generic lock error (verified in CP3's slice of Verification step 5).

**SIGNED OFF 2026-09-08.** Code was already CODE ACCEPTED unconditionally
(`.crew-handoff.json`); the live sign-off gap is now closed too, both parts
PASS: `evidence/live-cp4.md` "## Item 4 part 1" (`:214`, sharing-off project
with a real FieldWorks holder returns the enable-sharing recipe, not the
generic lock hint) and "## Item 4 part 2" (`:263`, the identical call
proceeds with no prompting once sharing is enabled).

### CP4 -- Writes allowed in shared mode

Replace the blanket block at `execution.py:3787-3814` with probe-driven
logic. The current code refuses on the mere *existence* of a lock file; that
is the regression this plan exists to undo.

- **T4.1** Implement the verdict table:

  | Probe verdict | New behavior |
  |---|---|
  | `free` | proceed (unchanged) |
  | `open_shared` (sharing on, live FLEx) | **proceed**; attach a `shared_mode` advisory to the response |
  | `open_exclusive` (sharing off, live FLEx) | refuse `project_locked` with the CP3 remedy |
  | `stale_lock` (holder dead) | **proceed**; note the stale lock -- `SimpleFileLock` treats stale locks as acquirable, so LCM takes it cleanly |
  | `held_by_other` (live non-FLEx holder) | refuse -- a genuine collision |

- **T4.2** Keep the pre-write backup, but relabel it honestly: with a FLEx
  peer attached, the `.fwdata` on disk lags FLEx's unsaved in-memory state, so
  the copy is a floor, not a snapshot. Say that in the backup note rather than
  implying a clean restore point.
- **T4.3** Confirm backup running only under `needs_lock`
  (`execution.py:3820`) stays correct and is not accidentally widened or
  narrowed by the probe-driven refactor.

**Checkpoint:** CP4 lands with a write `run_module` against an `open_shared`
project succeeding and visibly appearing in the FLEx UI (Verification step
5).

**SIGNED OFF 2026-09-08.** All three checklist items PASS, live, under a
real FLEx master: `evidence/live-cp4.md` Item 1 (`:300`, probe sees the
genuine FieldWorks holder), Item 2 (`:332`, read-only run with FLEx open),
Item 3 (`:352`, the load-bearing write -- all three legs, including the
human UI observation at `:399`, "confirmed CP4LIVE-2026-09-08"). This
closes both gaps that file's section 5/6 listed as owed: the `open_shared`
path exercised under a real FLEx master, and the probe tested against a
genuine FieldWorks holder rather than a leftover python process.

### CP5 -- The "close FLEx briefly" gate

> **STATUS: OPEN, and deliberately so. Interim policy adopted 2026-09-08 by
> the user.**
>
> CP5 is **not implemented** and is not being implemented yet. Until it
> ships, the project operates on a **conservative assumption**, adopted
> without waiting for proof:
>
> **Both writing-system operations and custom-field operations are assumed to
> require exclusive access.** Treat them as unsafe for a peer to perform while
> FieldWorks holds the project, in code, docs, recipes and review.
>
> This is an *assumption*, chosen because the failure modes are severe and the
> cost of being wrong in the safe direction is a user closing FLEx briefly.
> Three independent lines of live evidence support it, and none contradicts it:
>
> 1. **Writing systems -- proven harmful.** A peer WS change crashes
>    FieldWorks 9.3.10 (`NullReferenceException` in
>    `WritingSystemListHandler.AddWritingSystemList`, `TextListeners.cs:286`).
>    Both legs of the write reached disk; nothing refused it. See 3c
>    (`crashes_holder`).
> 2. **Custom fields -- already impossible via the wrapper anyway.**
>    `CustomFieldOperations.CreateField` refuses unconditionally with
>    `FP_TransactionError` in Phase 1 transaction mode, independent of FLEx
>    state and of shared mode, because `OpenProject()` holds a non-undoable
>    UnitOfWork open until `CloseProject()`. Assuming exclusivity costs
>    nothing here: the operation cannot succeed as a peer regardless.
> 3. **The write gate cannot currently be relied on to catch either.** A live
>    schema mutation executed with `confirmed=False` because
>    `is_mutating_script` came back `false` for a method the API index marks
>    `is_mutating: true`. Until that is fixed, a policy that depends on the
>    gate recognising these calls would be resting on a detector that
>    demonstrably misses them.
>
> **This settles the open scope call in T5.1's scoping note.** That note left
> "whether writing systems join the custom-fields-only core now or ship as a
> fast-follow row" undecided. Under this policy both are in scope from the
> start; CP5, when it is built, gates writing systems and custom fields
> together. The custom-fields-only framing below predates this decision.
>
> **CP5-a's acceptance test is invalid as written and must be redesigned
> before CP5 is built against it.** It asks that `CreateField` be refused with
> `requires_exclusive_access` while FLEx is open and then **succeed with FLEx
> closed**. The second leg cannot pass -- see point 2 above; the refusal is
> transactional, not access-related, so the test would pass its first leg for
> entirely the wrong reason and fail its second no matter what CP5 does.
> Evidence: `evidence/live-session2.md`, Item D.
>
> **Consequence while CP5 is open:** the assumption is documentation and
> review policy, not an enforced gate. Nothing in the code refuses these
> operations on access grounds today. Do not describe the protection as
> shipped.

**New error code `requires_exclusive_access`** -- the one place we ask the
user to close FLEx, and only when they actually requested a blocked
operation.

- **T5.1** Add `EXCLUSIVE_ONLY_OPERATIONS` to `validators.py` -- a table keyed
  by call signature, each entry carrying `reason` + `evidence` +
  `failure_class` from the Section 3b table. Cover the wrapper calls
  (`CustomFieldOperations.CreateField` / `DeleteField` / `SetFieldName` --
  **not** `UpdateField`, which does not exist in flexicon 4.5.2;
  `SetFieldName` is the schema-mutating analogue) and the raw LCM names
  (`AddCustomField`, `UpdateCustomField`, `RenameDatabase`,
  `FieldDescription`). The raw names have **zero occurrences in `src/`** --
  they are reachable only via user-submitted code -- so T5.2 must detect
  them by AST walk on the literal name, not by matching against any
  existing wrapper table.
  **Scoping note:** CP5 ships a **custom-fields-only core**. `T5.1`'s table
  in this checkpoint carries only the Class B custom-field row (wrapper +
  raw names above). **Updated 2026-09-08:** the three open live experiments
  this note originally deferred are now resolved (Section 3, updated in the
  same pass) -- possibility lists are `safe`/3a-ii (no row needed) and
  reversal indexes were removed from the table entirely (not a shared-mode
  issue). Writing systems are **not** resolved the same way: they are now
  Class C / `crashes_holder` (3c), and MUST be refused, which is a stronger
  claim than the "add later by row, whenever convenient" framing this note
  originally implied. Whether writing systems join this custom-fields-only
  core now or ship as an immediate fast-follow row is a scope call for
  lex-lead, not decided by this edit.
- **T5.2** `detect_exclusive_only_operations(code, tree)` -- follow the
  existing shape of `detect_cud_operations` / `certify_script_readonly`;
  reuse the same AST walk and `find_protected_ranges` conventions.
- **T5.3** Gate in `handle_run_module` beside the lock probe. Fires **only**
  when the probe reports a live peer **and** the script contains an
  exclusive-only op. Payload names the operation, the reason, and the resume
  recipe: close FLEx, re-submit this exact call, reopen FLEx after.
  Three rulings from lex-lead govern the implementation (verified against
  the tree at commit `520dba4`/`ad1d50c`; re-verify line numbers again
  before landing code, they drift):
  - **Insertion seam:** after the CP4 `project_locked` refusal ends
    (`execution.py:4269-4303`) and before the `open_shared` advisory begins
    (`:4305`), i.e. immediately before the pre-write backup block (`:4346`).
  - **Precedence:** CP5 keys on `_access.verdict == "open_shared"` / a live
    FLEx peer (the existing `_live_fw_peer` at `execution.py:4186`) --
    **never** on `_access is not None`. CP3's enable-sharing remedy must
    win over CP5 for an exclusively-held project (`open_exclusive` /
    `held_by_other` are already refused earlier by the CP4 block; CP5 does
    not re-adjudicate them).
  - **Detect first, probe second:** if `detect_exclusive_only_operations()`
    matches an exclusive-only op, the gate must force the access probe
    regardless of `needs_lock` -- a script that certifies read-only while
    calling `CreateField` is mis-certified, and that must not be a way to
    bypass the gate.
- **T5.4** Add an `_ASSISTANCE_HINTS_BY_ERROR_CODE` entry (`session.py:35`) so
  a retry loop on this code gets a real hint, not the generic fallback.
- **T5.5** Contract chores per `CONTRIBUTING.md:66-92`: detail model with
  `extra="forbid"` + `AnyDetail` union entry (`response_models.py`, next to
  `ProjectLockedDetail` at `:278-302`), `GOLDEN_FIXTURES` entry +
  `python tests/make_golden.py --regen`, `docs/TOOL-CONTRACT.md` row.
  **Re-grepped and verified against the current tree** (do not copy the
  original "16 codes" wording, and do not trust `response_models.py:361` --
  that line does not carry the count): the code count is **18** today, in
  `docs/TOOL-CONTRACT.md:69` ("one of the 18 codes below"),
  `tests/test_response_contract.py:9` (module docstring) and `:234` (class
  docstring "Each of the 18 codes"), with `ALL_ERROR_CODES` enumerated at
  `tests/test_response_contract.py:200-230`, and echoed in
  `response_models.py:10` ("18 per-code detail models"). Bump all four to
  **19**.
- **T5.6** Align the generic post-hoc fallback hint at `execution.py
  :1207-1216` ("Close FieldWorks and retry...") so it does not collide with
  CP5's message on an `open_shared` project: `build_lock_diagnosis()`
  (`project_access.py:276-320`) returns `None` for `open_shared` (and for
  `free`), so a post-hoc LCM failure surfacing on an otherwise-`open_shared`
  project currently falls through to this generic hint, which tells the
  user to close FieldWorks even though the whole point of shared mode is
  that they don't have to. Make the two messages agree.

**Checkpoint:** CP5 lands with `tests/test_issue<N>_exclusive_access_gate.py`
passing (Verification step 3) and the live custom-field refusal/resume cycle
confirmed (Verification step 5).

### CP6 -- Docs

- **T6.1** New `docs/SHARED-MODE.md` -- what works with FLEx open, what does
  not and why, the enable-sharing recipe, and the exclusive-only table with
  citations.
- **T6.2** `docs/workflow-detail.md` fixes: the 12-gate table (`:442-457`)
  omits the lock gate entirely, and `:420-427` describes undo behavior that
  never matched the shipped code. Fix both, update the four
  `workflow-*.svg` diagrams, add the new gate.
- **T6.3** `docs/RECOVERY.md` -- backups are now the *only* safety net; say
  so, and add the shared-mode caveat about FLEx's unsaved in-memory state.
- **T6.4** `CLAUDE.md` "Safety-first" bullet and `USAGE.md:228` -- remove the
  undo claim.
- **T6.5** `CHANGELOG.md` `[Unreleased]`, per repo convention.
- **T6.6** Document the known hazard (Section 4) in `docs/SHARED-MODE.md`; file
  upstream flexicon issues for the `ConflictingSave` modal-dialog deadlock,
  the `BeginUndoTask` arity bug, the `_transaction_depth` leak, and
  `Transaction()`'s nonexistent `RollbackToMark` call.
- **T6.7** Document the `error_type="ReportedError"` retry contract (source:
  `specs/shared-mode-access/reviews/cycle2-domain.md`). On a response with
  `error_type="ReportedError"`, callers must inspect
  `summary.error_count` vs `summary.total_messages` before deciding to
  retry, and must **never** blind-retry a batch containing
  Create*/append-style mutations -- only idempotent setters (`SetGloss`,
  `SetLexemeForm`) are safe to re-run. Add this to `docs/SHARED-MODE.md`
  (or `docs/TOOL-CONTRACT.md` if it fits the response-contract docs better)
  alongside the other CP6 documentation work.

**Checkpoint:** CP6 lands with `docs/SHARED-MODE.md` present, the stale
12-gate table and undo description in `docs/workflow-detail.md` corrected,
and `CHANGELOG.md` carrying the `[Unreleased]` entry for this feature.

---

## 7. Verification

1. **CP1 live check, before anything else** *(requires a live FLEx target and
   human authorization to run against it)* -- with FLEx closed, `run_module` a
   `SetGloss` and an `ApplySyncableProperties` against a scratch project;
   reopen and confirm both persisted. This is the test that would have
   caught the current breakage.
2. **Unit** -- new `tests/test_shared_mode_access.py`, following
   `tests/test_startup_lock_sweep.py`: fake the projects tree under
   `FW_PROJECTS_DIR`, write real-shaped `.fwdata.lock` JSON and `.plsx`
   files, assert every `probe_project_access` verdict including malformed
   inputs. Monkeypatch `_pid_is_alive` for the alive/dead split.
3. **Gate** -- new `tests/test_issue<N>_exclusive_access_gate.py` using the
   boom-stub pattern from `tests/test_issue55_write_safety_ladder.py:210-261`
   (`_boom_lock` / `_boom_subprocess`) to prove a refused
   `requires_exclusive_access` run takes no lock and spawns no subprocess --
   and the converse, that an `open_shared` verdict with an ordinary write
   *does* reach the subprocess.
4. **Contract** -- `python tests/make_golden.py --regen`, then
   `pytest tests/test_response_contract.py`.
5. **Live, with FLEx open** *(requires a live FLEx target and human
   authorization to run against it)* -- the real acceptance test, on
   `Claude-Swahili` (already `projectSharing="true"`):
   - `flextools_health(verbose=True)` reports `verdict: open_shared` with
     FLEx's real PID.
   - read-only `run_module` listing entries: succeeds.
   - write `run_module` setting a gloss: succeeds, and the change appears in
     the FLEx UI -- the whole point of this work.
   - `CustomFieldOperations.CreateField`: refused with
     `requires_exclusive_access`; close FLEx, re-submit unchanged, succeeds;
     reopen FLEx.
   - a project with sharing **off**, FLEx open -> read-only run refused with
     the enable-sharing recipe; enable in FLEx, reopen, re-run: proceeds with
     no further prompting.
6. **Regression** -- full `pytest`, plus
   `python scripts/validate_integrity.py all` and
   `python scripts/verify_python.py` (both required by `CONTRIBUTING.md`).

---

## 8. Deferred follow-ups

The two entries that needed the user's authorization to file were FILED on
2026-09-08 as **#118** (fail-open probe) and **#119** (TOOL-CONTRACT envelope
gap). The remaining entries are draft notes with no GitHub issue, by ruling.

- **P2, pre-existing, out of this feature's scope -- FILED as #119:**
  `docs/TOOL-CONTRACT.md:13-26` claims all success responses carry
  `_contract`/`status`/`op_id`, but `run_module`'s raw success dict is
  returned verbatim at `execution.py:4723` and never carries any of those
  fields -- only `success`/`error`/`error_type`. It never passes through
  `build_response_with_context()` (`response_utils.py:128`), which is the
  sole `_contract` stamper (`:142`); `grep -n '_contract'
  src/flextoolsmcp/server/handlers/execution.py` returns zero hits. Note
  that the same handler *does* stamp its discovery-redirect (`:1056`) and
  `validate_only` (`:2107`) exits correctly, and that
  `build_response_with_context` stamps only `_contract` -- never `status`
  or `op_id` -- so the doc's three "guaranteed keys" are broader than any
  code path delivers. This gap predates CP1 (confirmed by cycle-2 QC
  review). Fix in either direction: add the envelope to `run_module`'s
  return path, or carve out an explicit exception in
  `docs/TOOL-CONTRACT.md`. Sibling exits to check: `:4166`, `:4403`,
  `:4731`, `:4746`.
- **P2-4, cycle-6 QC, declined to action:** the "an unreadable PID" branch
  in `build_lock_diagnosis()` (`project_access.py:308`) is untested -- none
  of `probe_project_access()`'s `ProjectAccess(...)` construction sites
  (`project_access.py:357,370,395`) pass a `holder` whose `pid` is `None`
  while `verdict == "stale_lock"`, so the branch is dead in practice today
  and unverified if it ever becomes live. Left for a future cycle.
- **P2-8, cycle-6 QC, declined to action:** CP3's post-hoc diagnosis
  (`execution.py:1251-1262`) spreads the four probe facts (`verdict`,
  `sharing_enabled`, `holder_pid`, `holder_process`) flat into the
  response, while CP4's write-gate advisory namespaces the same four facts
  under `shared_mode` (`execution.py:4306-4310,4326-4330`). This is a
  drift hazard for a future maintainer reconciling the two payload shapes,
  but lex-lead ruled against changing either shape mid-feature. Left for a
  future cycle.
- **P1-class, pre-existing -- FILED as #118:** the fail-open probe. `probe_project_access()` returns `verdict="free"`
  when `get_projects_directory()` returns `None` -- i.e. it reports "not
  blocking" *without ever inspecting a lock file*. Cycle 7 landed a
  strictly-bounded interim patch (`ProjectAccess.probed: bool = True`, set
  `False` only in that branch; the `validate_only` reporting site now emits
  `blocking: None` and omits `verdict` when `probed` is false), so nothing
  currently ships a confident false negative. The **full** fix is still
  deferred because it widens an enum consumed by `build_access_remedy`,
  `build_lock_diagnosis`, the CP4 gate, `diagnostic_health`,
  `ProjectLockedDetail` and 30+ tests. Recommended shape when filed:
  (1) keep `probed` as the additive flag; (2) add a real `verdict="unknown"`
  with `blocking: null` only if a consumer actually needs to branch on it;
  (3) make every reporting site emit `blocking` *unconditionally* alongside
  `locked`, plus a `note` explaining that `locked` is bare lock-file
  existence. Rationale and the decision trail are in
  `.crew-handoff.json` -> `fail_open_ruling`; do not relitigate from scratch.
- **P2 residual, cycle 7, accepted:** `execution.py`'s `validate_only`
  enrichment omits `blocking` entirely when `project_name` is falsy or the
  probe raises, leaving the bare `locked` boolean unqualified. Safe-direction
  (a consumer over-blocks rather than under-blocks) and enumerated as a
  "note" row -- not a DEFECT row -- in `reviews/lock-site-inventory.md`.
  Folds into #118 (the fail-open issue above), item (3).
- **P3, cycle 7, deferred with the contract documented in place:**
  `project_discovery.py:262` `check_project_locked()`'s *name* asserts a
  conclusion its return value cannot support (a lock file may be stale or
  shared). It is the proximate cause of two of the three historical
  bare-lock misses. Cycle 7 stated the correct contract in its docstring but
  deferred the rename to `find_lock_file()` -- **16 occurrences** across
  `src/` and `tests/`, zero behaviour change. Verified breakdown
  (`grep -rn check_project_locked src/ tests/ --include=*.py`, 2026-09-08):
  7 in `src/` (the definition at `project_discovery.py:262`, four
  dual-path imports and two calls in `handlers/execution.py`) and 9 in
  `tests/` (7 `monkeypatch.setattr` string references across five test
  files, plus 2 prose mentions in comments/docstrings). The earlier
  "~9 call sites" estimate undercounted. Do it as a standalone mechanical
  commit in the CP6 cleanup pass; no GitHub issue (it is inside #93's
  scope and carries a durable row in `reviews/lock-site-inventory.md`).
- **P3, cycle 7, new:** `sweep_stale_locks()` runs at server startup
  (`server.py:1048`) with **no** `try/except` around its per-lock loop and
  none at the call site, so an unexpected exception there fails server
  startup outright. Pre-existing shape (`read_lock_holder` / `_pid_is_alive`
  were already unguarded), but cycle 7 added two more calls inside that loop
  (`is_project_sharing_enabled`, `build_access_remedy`; both internally
  exception-tolerant, so the added risk is small). One-line fix: wrap the
  loop body in `except Exception: continue`, or guard the call site.
