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

## 3. The exclusive-only operation table

The user asked for the full list, not just custom fields. Each entry is
backed by source, and each is a reason to ask the user to close FLEx briefly.

| Operation | Why a non-master peer cannot do it | Evidence |
|---|---|---|
| **Custom field create/delete/update** | `<AdditionalFields>` schema is written only by the master (`SharedXMLBackendProvider.cs:479`) and is **not** a member of `CommitLogRecord`. A peer publishes `<Custom name=...>` data referencing a declaration that never persists -> corrupt on next FLEx open. Worse, `HaveAnyModifiedCustomProperties` clears `m_extantCustomFields`, so the *next* commit reports "no change" and the declaration is lost for good. | `CommitLogRecord.cs:16-49`, `BackendProvider.cs:506`, `XMLBackendProvider.cs:551`; FLEx itself refuses at `XWorksViewBase.cs:715` |
| **Writing system add/modify** | `.ldml` under `WritingSystemStore\` and `.plsx`/`.ulsx` bypass the commit log entirely -- no mutex, no reconciliation. Pure last-writer-wins clobber between peers. | `LcmServiceLocatorFactory.cs:223`, `XMLBackendProvider.cs:165` |
| **Project rename** | LCM refuses outright when peers are attached. | `SharedXMLBackendProvider.cs:637` |
| **Data migration** | Non-master peers throw `LcmDataMigrationForbiddenException`; flexlibs also sets `DisableDataMigration = True` unconditionally. | `SharedXMLBackendProvider.cs:108-111`, `FLExLCM.py:92` |
| **Send/Receive** | FLEx blocks S/R while other apps are connected. | `FLExBridgeListener.cs:314` |
| **Project backup / restore / delete** | FLEx's own guard (`ProjectsInUseLocally`) enumerates .NET-Remoting clients only and is **blind to a pythonnet peer** -- nobody protects this, so we must. | `FieldWorks.cs:813, 1988` |

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

### CP5 -- The "close FLEx briefly" gate

**New error code `requires_exclusive_access`** -- the one place we ask the
user to close FLEx, and only when they actually requested a blocked
operation.

- **T5.1** Add `EXCLUSIVE_ONLY_OPERATIONS` to `validators.py` -- a table keyed
  by call signature, each entry carrying `reason` + `evidence` from the
  Section 3 table. Cover wrapper calls (`CustomFieldOperations.CreateField` /
  `DeleteField` / `UpdateField`; writing-system mutators) and raw LCM
  (`AddCustomField`, `UpdateCustomField`, `RenameDatabase`,
  `FieldDescription`).
- **T5.2** `detect_exclusive_only_operations(code, tree)` -- follow the
  existing shape of `detect_cud_operations` / `certify_script_readonly`;
  reuse the same AST walk and `find_protected_ranges` conventions.
- **T5.3** Gate in `handle_run_module` beside the lock probe. Fires **only**
  when the probe reports a live peer **and** the script contains an
  exclusive-only op. Payload names the operation, the reason, and the resume
  recipe: close FLEx, re-submit this exact call, reopen FLEx after.
- **T5.4** Add an `_ASSISTANCE_HINTS_BY_ERROR_CODE` entry (`session.py:35`) so
  a retry loop on this code gets a real hint, not the generic fallback.
- **T5.5** Contract chores per `CONTRIBUTING.md:66-92`: detail model with
  `extra="forbid"` + `AnyDetail` union entry (`response_models.py:311`),
  `GOLDEN_FIXTURES` entry + `python tests/make_golden.py --regen`,
  `docs/TOOL-CONTRACT.md` row, and bump the "16 codes" wording there and in
  `tests/test_response_contract.py`.

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

Draft notes only -- no GitHub issue filed yet; the user authorizes issue
filing separately.

- **P2, pre-existing, out of this feature's scope:**
  `docs/TOOL-CONTRACT.md:13-26` claims all success responses carry
  `_contract`/`status`/`op_id`, but `run_module`'s raw success dict
  (`execution.py:3482-3490,3699`) is returned verbatim and never carries
  any of those fields -- only `success`/`error`/`error_type`. This gap
  predates CP1 (confirmed by cycle-2 QC review) and is worth its own issue
  later, either to add the missing envelope fields to `run_module`'s
  return path or to carve out an explicit exception in
  `docs/TOOL-CONTRACT.md` for that one response shape.
