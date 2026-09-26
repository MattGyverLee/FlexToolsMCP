# Shared mode: working with FLEx open

FieldWorks (FLEx) and this MCP server can have the same project open at the
same time. Whether that works, and what you can do while it does, depends on
one project setting: **project sharing**. This page explains what works with
FLEx open, what does not and why, and how to turn sharing on.

Tracked as issue #93. The design record, with source citations for every
claim below, is `specs/shared-mode-access/SPEC.md`.

## The short version

| FLEx state | Project sharing | Read-only `run_module` | Writing `run_module` |
|---|---|---|---|
| Closed | either | works | works |
| Open | **on** | works | works; the change appears in the FLEx UI |
| Open | off | refused, with the enable-sharing steps below | refused, with the enable-sharing steps below |

Two kinds of change must **not** be made while FLEx has the project open,
even with sharing on: **custom fields** and **writing systems**. See
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
| `open_shared` | FLEx has it open, sharing on | proceeds, with a `shared_mode` note on the result |
| `stale_lock` | Lock names a process that is no longer running | proceeds; LCM treats a stale lock as free |
| `open_exclusive` | FLEx has it open, sharing off (or the lock file is unreadable) | refused as `project_locked`, with the enable-sharing steps |
| `held_by_other` | A live process that is not FLEx holds it, usually a leftover FLExTools/MCP subprocess | refused as `project_locked`; enabling sharing does not help. Wait for that process to exit, or end it |

Read-only runs are never refused on these grounds. If LCM itself refuses to
open the project (sharing off, FLEx open), the error carries the same
diagnosis and remedy as a refused write.

The server never deletes lock files. If a lock is unreadable and you are sure
no FieldWorks or python process is running, delete it yourself.

## Close FLEx for these

Some changes a peer cannot make safely. Until the planned refusal gate
(`requires_exclusive_access`, CP5) ships, **nothing in the server refuses
these** while FLEx is open. Close FLEx first, make the change, then reopen
FLEx.

| Change | What goes wrong from a peer | Evidence |
|---|---|---|
| **Custom field** create, delete or rename | *Silently lost.* Only the master writes custom-field definitions to disk, and the commit log has nowhere to carry them, so the field is gone after the next restart with no error. FLEx blocks its own Custom Fields dialog in the same situation. | `SharedXMLBackendProvider.cs:408,478`; `CommitLogRecord.cs:17-49`; `XWorksViewBase.cs:715` |
| **Writing system** add or modify | *Crashes FLEx.* The change reaches disk, then the running FLEx throws `NullReferenceException` in `WritingSystemListHandler.AddWritingSystemList` (`TextListeners.cs:286`). Seen live on FieldWorks 9.3.10. | `specs/shared-mode-access/evidence/live-cp4.md`, Item 5 |

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

## Known hazard: save conflicts

flexicon opens projects with a UI helper (`FwLcmUI`, `FLExLCM.py:88`). If LCM
detects a save conflict it calls `ConflictingSave()`, which tries to show a
modal dialog with no close box from the server's hidden subprocess
(`FwLcmUI.cs:47`). Nobody can answer it; the default answer discards the
peer's writes (`RevertToSavedState()`). Separately, a message LCM posts from
its commit thread can deadlock because the subprocess has no message loop.

What protects you today: every run has a timeout, after which the server
kills the subprocess and its children. If a run with FLEx open hangs until
the timeout, assume its writes did not land, and check the FLEx UI. The fix
belongs in flexicon (upstream issue not yet filed).

## Undo

There is no undo tool. LCM keeps its undo stack in memory only, and each
`run_module` call runs in a fresh process, so nothing survives to undo. The
old `flextools_undo_last_operation` tool never worked and was removed (#92).
Your safety nets are the automatic backup and, for Send/Receive projects,
the repository.
