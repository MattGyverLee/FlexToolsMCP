# Shared mode: working with FLEx open

FieldWorks (FLEx) and this MCP server can have the same project open at the
same time. Whether that works, and what you can do while it does, depends on
one project setting: **project sharing**. This page explains what works with
FLEx open, what does not and why, and how to turn sharing on.

Tracked as issue #93. The design record, with source citations for every
claim below, is `specs/shared-mode-access/spec.md`; the writing-system and
custom-field refusal is `specs/exclusive-access-gate/spec.md`.

## The short version

| FLEx state | Project sharing | Read-only `run_module` | Writing `run_module` |
|---|---|---|---|
| Closed | either | works | works |
| Open | **on** | works | works; the change appears in the FLEx UI |
| Open | off | refused, with the enable-sharing steps below | refused, with the enable-sharing steps below |

Two kinds of change must **not** be made while FLEx has the project open,
even with sharing on: **custom fields** and **writing systems**. The server
refuses them with `requires_exclusive_access`. See
[Close FLEx for these](#close-flex-for-these).

## Why sharing matters

When FLEx opens a project it takes a `.fwdata.lock` file. With sharing
**off**, that lock is exclusive: no other program can open the project, not
even to read it (`LcmCache.cs:219`).

With sharing **on** (`projectSharing="true"` in
`<Project>\SharedSettings\LexiconSettings.plsx`), FLEx becomes the project's
*master* and other programs attach as *peers*. A peer reads and writes
through a shared commit log, so a change made by this server shows up in the
FLEx window without restarting FLEx (`SharedXMLBackendProvider.cs:102-118`).

## Turning sharing on

1. In FieldWorks, go to **File > Project Management > FieldWorks Project
   Properties**, then the **Sharing** tab.
2. Tick **"Share project contents with programs on this computer"** and click
   **OK**.
3. If FLEx offers to reopen the project, accepting is recommended, but this
   server can attach without it.
4. Re-submit the same `run_module` call. The server checks the setting again
   on every call and continues on its own.

This server **never** edits `LexiconSettings.plsx` for you. Changing the
setting is your decision, made in FLEx.

## How the server decides

Before a run, the server reads the lock file (it is JSON naming the holding
process, e.g. `{"PID":68436,"ProcessName":"FieldWorks",...}`), checks
whether that process is still alive, and reads the sharing flag. The result
is one of these verdicts, reported by `flextools_health(verbose=True)` under
`project_access` and on refusals:

| Verdict | Meaning | Write behavior |
|---|---|---|
| `free` | No lock file | proceeds |
| `open_shared` | FLEx has it open, sharing on | proceeds, with a `shared_mode` note on the result; writing-system and custom-field changes are refused as `requires_exclusive_access` |
| `stale_lock` | Lock names a process that is no longer running | proceeds; LCM treats a stale lock as free |
| `open_exclusive` | FLEx has it open, sharing off (or the lock file is unreadable) | refused as `project_locked`, with the enable-sharing steps |
| `held_by_other` | A live process that is not FLEx holds it, usually a leftover FLExTools/MCP subprocess | refused as `project_locked`; enabling sharing does not help. Wait for that process to exit, or end it |

Read-only runs are never refused on these grounds. If LCM itself refuses to
open the project (sharing off, FLEx open), the error carries the same
diagnosis and remedy as a refused write.

The server never deletes lock files. If a lock is unreadable and you are sure
no FieldWorks or python process is running, delete it yourself.

## Close FLEx for these

Some changes a peer cannot make safely. A write-enabled `run_module` whose
script makes one of them is **refused** with `requires_exclusive_access`
while FLEx has the project open with sharing on (verdict `open_shared`), or
when the server cannot confirm FLEx is closed (verdict `unknown`). The
refusal comes before the confirmation step, the backup and the run, so
nothing has happened yet. To recover:

1. Close FLEx (all windows for this project).
2. Re-submit the **same** `run_module` call, unchanged. Do not rewrite the
   script to get around the refusal.
3. Reopen FLEx after the run finishes.

`validate_only` reports the same decision ahead of time as
`project_lock.exclusive_access.blocking`. Read-only runs are never refused
for this. Ordinary edits are never refused for this either: closing FLEx is
needed only for the changes below.

| Change | What goes wrong from a peer | Evidence |
|---|---|---|
| **Custom field** create, delete or rename (`CustomFieldOperations.CreateField` / `DeleteField` / `SetFieldName`; raw `AddCustomField`, `UpdateCustomField`, `DeleteCustomField`, `MarkForDeletion`) | *Silently lost.* Only the master writes custom-field definitions to disk, and the commit log has nowhere to carry them, so the field is gone after the next restart with no error. FLEx blocks its own Custom Fields dialog in the same situation. | `SharedXMLBackendProvider.cs:429,479`; `CommitLogRecord.cs:23-48`; `XWorksViewBase.cs:715` |
| **Writing system** add, delete or modify (`WritingSystemOperations.Create` / `Ensure` / `Delete` / `SetFontName` / `SetFontSize` / `SetRightToLeft` / `SetDefaultVernacular` / `SetDefaultAnalysis`; the raw writing-system manager, lists and services) | *Crashes FLEx.* The change reaches disk, then the running FLEx throws `NullReferenceException` in `WritingSystemListHandler.AddWritingSystemList` (`TextListeners.cs:286`). Seen live on FieldWorks 9.3.10. | `specs/shared-mode-access/evidence/live-cp4.md`, Item 5 |

The full list, with the raw LCM names, is
`EXCLUSIVE_ONLY_OPERATIONS` in `src/flextoolsmcp/server/exclusive_access.py`.
Setting a custom field's **value** (`CustomFieldOperations.SetValue` and the
other value methods) is an ordinary edit and is not refused.

The custom-field row comes from reading the LCM source; it has not been
reproduced live. Today flexicon's `CustomFieldOperations.CreateField` fails
with `FP_TransactionError` whether or not FLEx is open, so that route cannot
lose data yet.

These are known to be fine from a peer:

- **Ordinary lexicon edits** (glosses, forms, senses, entries). Verified
  live: the change appeared in the FLEx UI and survived a restart.
- **Possibility-list items** (semantic domains, parts of speech, morph types),
  added or renamed. Verified live across a full FLEx close and reopen.

Also refused by LCM itself, so nothing is lost: **renaming the project** while
peers are attached.

## Backups with FLEx open

The first write per session still takes the automatic pre-write backup (see
[RECOVERY.md](RECOVERY.md)). With FLEx open, the `.fwdata` on disk can lag
behind FLEx's unsaved in-memory state, so the backup is a floor to fall back
to, not a copy of what the FLEx window shows. The backup note on the result
says so when FLEx is attached.

## Reading back your own write

A read-only run while FLEx is the master opens a fresh peer that sees FLEx's
last flush to disk. It can show the state **before** a write that has already
committed. Results in this situation carry a `shared_mode_read_back` note.
Do not treat such a read as proof that a write was lost, and do not retry the
write because of it. Check the FLEx UI instead.

## Seeing an MCP change in FLEx

FLEx picks up a peer's change when it next refreshes the view you are on.
**Navigate away and back** (for example, click another entry and then return)
to see it. Pressing **F5** alone is not enough (#96).

## Retrying after `ReportedError`

A run whose script called `report.Error()` comes back with `success: false`
and `error_type: "ReportedError"`, even if most of the work succeeded. Before
retrying:

- Compare `summary.error_count` with `summary.total_messages`, and read
  `messages[]`, to tell "3 of 500 failed" from "everything failed".
- **Never** blindly re-run a script that creates or appends
  (`Create*`, `Add*`, anything that makes a new object). The objects that
  succeeded the first time will be created again.
- Only idempotent setters (`SetGloss`, `SetLexemeForm`, and similar) are safe
  to re-run as-is. Otherwise, re-run only the items that failed.

## Save conflicts

If LCM detects a save conflict it calls the UI helper's `ConflictingSave()`.
flexicon used to open projects with FieldWorks' `FwLcmUI`, which tries to
show a modal dialog from the server's hidden subprocess (`FwLcmUI.cs:47`):
nobody could answer it, and the default answer discarded the peer's writes.
A message LCM posts from its commit thread could also deadlock, because the
subprocess has no message loop.

Already fixed in flexicon 4.6.0 (flexicon#285): `HeadlessLcmUI` is now the
default UI. A save conflict raises `FP_ConflictingSaveError`, so the run fails
with an error instead of hanging, and messages are marshalled through
`SingleThreadedSynchronizeInvoke` instead of a message loop. Every supported
install is on a later flexicon. If a run with FLEx open still fails this way,
assume its writes did not land, and check the FLEx UI. Every run also has a
timeout, after which the server kills the subprocess and its children.

## Undo

There is no undo for an MCP write, from either side:

- **No MCP undo.** LCM keeps its undo stack in memory only, and each
  `run_module` call runs in a fresh process, so nothing survives to undo. The
  old `flextools_undo_last_operation` tool never worked and was removed (#92).
- **FLEx starts with an empty undo history.** Each time FLEx opens a project
  its undo stacks are new and empty; no undo history is saved with the
  project (`UnitOfWorkService.cs:169-172`).
- **FLEx records peer writes as non-undoable.** When FLEx picks up a peer's
  change, it wraps it in a non-undoable unit of work
  (`ChangeReconciler.cs:200-204`, `UndoStack.cs:859-870`). So Edit > Undo in
  FLEx does not offer an MCP change, whether FLEx was open or closed when it
  was made.
- **Programmatic undo is not built.** Under `undoable=True` LCM keeps an undo
  stack inside one `run_module` process, so a script could in principle undo
  its own work before it exits. The server offers no such feature.

Your safety nets are the automatic pre-write backup and, for Send/Receive
projects, the repository. See [RECOVERY.md](RECOVERY.md).
