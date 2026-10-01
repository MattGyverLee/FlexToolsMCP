# Feature Specification: Exclusive-access gate and shared-mode follow-ups

**Feature Branch**: `feat/exclusive-access-gate` (worktree `C:\Github\FlexToolsMCP-exclusive-access`)

**Created**: 2026-09-30

**Status**: Draft

**Input**: User description: "Close [#93] and the spec, and make a new spec to build whatever we still need to build." The user also noted: "when FLEx is opened, it starts with a 'fresh' undo history and we can't undo items in the UI that were done with the UI closed. Even if the UI is open, I don't know if we are (or should) populate the metadata needed for Undo. We probably could programmatically undo via the LCM if we wanted to, but this hasn't been successfully built yet."

**Tier**: Full - per `.specify/memory/constitution.md` v1.1.0. The feature adds an
error code to the published tool-response contract and changes when
`run_module` refuses a write. `plan.md` and `tasks.md` follow this spec.

**Touches a write path?**: Yes. The gate decides whether a mutating script runs
against a project FLEx has open. The live-LCM verification obligation applies:
refusal and resume cycles MUST be checked live on the **Sena 3** test project
with FieldWorks open in shared mode. Never use Claude-Swahili.

**Predecessor**: `specs/shared-mode-access/` (#93), retired. Its AS-BUILT record
lives in `specs/_archive/shared-mode-access/`. That feature shipped CP1-CP4 and
most of CP6. This spec carries forward what it left unbuilt: CP5 and the rest
of CP6.

**Related issues**: #93 (closed, predecessor), #96 (read-after-write
staleness, closed), #315 (`project_locked` held by a python PID, open and being
fixed separately on `fix/315-project-locked-holder`; out of scope here),
flexicon#292 (`SyncForeignChanges()`, shipped).

**Amended 2026-09-30 during planning**: Section 2 (FLEx Undo of peer writes
is answered by LCM source), US5/FR-030 (sync call depends on undo mode),
FR-002 (raw LCM names). See `research.md`.

---

## 1. Context: where things stand

The server can already work on a project while FLEx has it open, if the project
has sharing turned on. A probe reads the lock file and sharing flag and gives
one of five verdicts (`free`, `open_shared`, `open_exclusive`, `stale_lock`,
`held_by_other`). Writes go ahead on `open_shared`, and that has been verified
live.

Two kinds of change are not safe for a second program (a "peer") to make while
FLEx holds the project:

| Change | What goes wrong from a peer | Status of evidence |
|---|---|---|
| Writing system add or modify | The running FLEx crashes (`NullReferenceException`, FieldWorks 9.3.10) | Seen live |
| Custom field create, delete or rename | The field definition is never saved, and the field disappears on the next FLEx open with no error | From LCM source; not reproduced live, because flexicon's `CreateField` currently fails with `FP_TransactionError` in every case |

On 2026-09-08 the user set an interim policy: treat both kinds as requiring
FLEx to be closed. That policy is written down but nothing enforces it. The
only guard is a note in the shared-mode advisory, and the user sees it *after*
the write has run. This spec turns the policy into a real refusal.

## 2. Undo: what is true, and what this spec does about it

Undo is not part of the gate, but every document this feature touches has to
describe it correctly, and two still describe it wrongly.

What is true:

- **The MCP has no undo.** LCM keeps its undo stack in memory only, and each
  `run_module` call runs in a fresh process. The old
  `flextools_undo_last_operation` tool never worked and was removed (#92).
- **FLEx's own Undo cannot reach MCP writes made while FLEx was closed.** FLEx
  starts with an empty undo history every time it opens.
- **FLEx's own Undo cannot reach MCP writes made while FLEx is open either.**
  LCM source (checked 2026-09-30, see `research.md` R4): FLEx picks up a
  peer's change during its own next commit, and `ChangeReconciler` records it
  as a non-undoable unit of work (`AddForeignBundleToUndoStack` on the
  non-undoable stack). The MCP has no metadata it could supply to change that.
  A live check (Edit > Undo in FLEx after an MCP write) is still worth
  recording as evidence.
- **Undoing through LCM from the MCP may be possible but has never been built.**

What this spec does: it corrects the documentation (FR-020 to FR-022) and
records the source finding about FLEx Undo while FLEx is open. It does **not**
build programmatic undo. That would be a separate feature with its own spec
(see Out of scope).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Refuse a writing-system or custom-field change while FLEx is open (Priority: P1)

A linguist has their project open in FLEx with sharing on. They ask the
assistant to add a writing system, or to create a custom field. The server
refuses before anything runs. It names the operation and why it is unsafe, and
tells the user to close FLEx briefly, re-run the same request, and reopen FLEx.
Once FLEx is closed, the same request goes through the normal write path.

**Why this priority**: A peer writing-system change crashes FLEx, and a peer
custom-field change can lose the field silently. Today nothing stops either.
This is the only part of the predecessor feature that protects data.

**Independent Test**: With Sena 3 open in FLEx (sharing on), submit a script
that adds a writing system. It must be refused with `requires_exclusive_access`
before execution, and FLEx must keep running. Close FLEx and submit the same
script. It must get past the gate.

**Acceptance Scenarios**:

1. **Given** FLEx holds the project in shared mode, **When** a script calls a
   writing-system-mutating operation, **Then** the call is refused with
   `requires_exclusive_access` before any project code runs, and the response
   names the operation, the reason and the close-FLEx-and-resubmit steps.
2. **Given** FLEx holds the project in shared mode, **When** a script calls a
   custom-field create, delete or rename (flexicon wrapper or raw LCM name),
   **Then** it is refused the same way.
3. **Given** FLEx is not running (`free`, or `stale_lock`), **When** the same
   script is submitted, **Then** this gate does not refuse it. The script's
   outcome is decided by the rest of the write path.
4. **Given** FLEx holds the project exclusively (sharing off), **When** any
   such script is submitted, **Then** the existing `project_locked` refusal
   with the enable-sharing steps wins. This gate does not override it.
5. **Given** a script that would certify as read-only but contains an
   exclusive-only call, **When** it is submitted with FLEx open, **Then** it
   is still refused. Mis-certification must not bypass the gate.
6. **Given** a script where the exclusive-only call appears only in a comment
   or a string, **When** it is submitted, **Then** the call does not trigger
   the gate. (A call in a dead branch such as `if False:` still triggers it,
   matching the existing mutation detection, which fails closed.)
7. **Given** a request made with `validate_only`, **When** the script contains
   an exclusive-only call and FLEx holds the project in shared mode, **Then**
   the preflight result reports that the run would be refused, and why.
8. **Given** a read-only run (writes not enabled), **When** the script
   contains a guarded exclusive-only call, **Then** this gate does not fire:
   guarded code does not execute on a read-only run.
---

### User Story 2 - The assistant recovers from the refusal without looping (Priority: P1)

After a `requires_exclusive_access` refusal, the assistant asks the user to
close FLEx, waits for confirmation, re-submits the identical request, and tells
the user they can reopen FLEx. It does not retry blindly, rewrite the script to
dodge the gate, or tell the user to close FLEx for ordinary edits.

**Why this priority**: A refusal that the assistant mishandles costs as much
trust as no refusal. The project's error responses are meant to teach the
assistant what to do next.

**Independent Test**: Trigger the refusal, then check that the response carries
a specific recovery hint for this code, not the generic fallback.

**Acceptance Scenarios**:

1. **Given** a `requires_exclusive_access` response, **When** the assistant
   reads it, **Then** the hint says to close FLEx, re-submit unchanged, and
   reopen FLEx afterwards.
2. **Given** an ordinary write that fails for another reason on an
   `open_shared` project, **When** the error is diagnosed, **Then** the hint
   does not tell the user to close FieldWorks. Today a generic fallback does,
   and it contradicts both shared mode and this gate.

---

### User Story 3 - Prove the custom-field hazard with a valid live test (Priority: P2)

The predecessor's acceptance test for custom fields (CP5-a) was withdrawn as
invalid: `CreateField` fails with `FP_TransactionError` regardless of FLEx, so
the test would "pass" its refusal half for the wrong reason and could never
pass its success half. The maintainer needs a test that actually shows the
gate protects custom fields.

**Why this priority**: The gate can ship on the source analysis. But the
silent-loss failure (Class B) has never been observed, and the gate's
custom-field row should eventually rest on a live result like the
writing-system row does.

**Independent Test**: A documented live procedure on Sena 3 that writes a
custom-field definition from a peer by a route that does not hit the
transaction refusal, then reopens FLEx and records whether the definition
survived.

**Acceptance Scenarios**:

1. **Given** the redesigned procedure, **When** it runs with FLEx open, **Then**
   the evidence file records whether the definition was lost, and the
   custom-field row's evidence column is updated to "seen live" or to what was
   actually observed.
2. **Given** the procedure cannot be built without a flexicon change, **When**
   that is established, **Then** the gap is filed upstream and the row keeps
   its "from source" label.

---

### User Story 4 - Documentation tells the truth about undo and shared mode (Priority: P2)

A user or assistant reading the docs learns: there is no MCP undo; FLEx's Undo
cannot reverse MCP writes made while FLEx was closed; whether it can reverse
writes made while FLEx is open is unknown; to see an MCP write in an open FLEx
window you navigate away and back (F5 is not enough); and which changes need
FLEx closed, now enforced.

**Why this priority**: Two docs still teach a tool that does not exist, and
assistants follow the docs.

**Independent Test**: Search the shipped docs and tool descriptions for
`undo_last_operation` and for any claim that a write can be undone. None may
remain except the explicit "there is no undo" statements.

**Acceptance Scenarios**:

1. **Given** the shipped docs, **When** searched, **Then** no document
   describes `flextools_undo_last_operation` or an MCP undo stage.
2. **Given** `docs/SHARED-MODE.md`, **When** read, **Then** its "Close FLEx for
   these" section says the server refuses these changes, and its Undo section
   carries the four undo facts from Section 2 (extending the existing section).
3. **Given** `docs/SHARED-MODE.md`, **When** read, **Then** it says that FLEx
   shows a peer write after navigating away and back, not after F5.

---

### User Story 5 - A write-enabled session can see a peer's earlier writes (Priority: P3)

An assistant writes with FLEx open, then in a later call reads the data back.
Today that read may show the state *before* the write, because a fresh session
sees only FLEx's last save to disk. flexicon now provides
`SyncForeignChanges()`, which pulls in other peers' committed changes.

From the flexicon source, pulling in a peer's changes means committing, so it
needs a write-enabled session: `SyncForeignChanges()` (for `undoable=False`
sessions) and `SaveChanges()` (for `undoable=True` sessions, the MCP's default
when flexicon advertises `per-operation-uow`) both raise `FP_ReadOnlyError`
in a read-only session. So syncing can help write-enabled
runs (for example a script that writes and then verifies), but not read-only
read-backs. Opening a writable session just to read is out of scope: it would
take the write path's lock and backup steps for a read.

**Why this priority**: The current `shared_mode_read_back` note already stops
the assistant from acting on a stale read. Being able to verify the write is
better, but it is not a safety issue.

**Independent Test**: On Sena 3 with FLEx open, write a gloss in one call. In a
second write-enabled call, read it back with and without the sync step and
record what each shows.

**Acceptance Scenarios**:

1. **Given** sync makes the prior write visible, **When** a write-enabled
   session opens on an `open_shared` project, **Then** it syncs before running
   the script, and its results no longer carry the stale-read note.
2. **Given** a read-only session on an `open_shared` project, **When** it
   returns results, **Then** the stale-read note stays, and says that
   read-only sessions cannot pull in a peer's recent writes, instead of
   calling the path "untested".

---

### User Story 6 - Close out the predecessor's unfiled findings (Priority: P3)

The predecessor left work that is filing, not code: four upstream flexicon
issues and a set of drafted issues that were never filed.

**Why this priority**: Housekeeping. It needs the maintainer's authorization
for each filing.

**Independent Test**: Each item ends as a filed issue number, or as an explicit
"not filing" with a reason, recorded in this spec.

**Acceptance Scenarios**:

1. **Given** the four upstream hazards (the `ConflictingSave` modal dialog, the
   `BeginUndoTask` arity bug, the `_transaction_depth` leak, the nonexistent
   `RollbackToMark` call), **When** each is checked against current flexicon,
   **Then** each is filed, or recorded as already fixed, and
   `docs/SHARED-MODE.md` no longer says "upstream issue not yet filed".
2. **Given** the drafts in `specs/_archive/shared-mode-access/issues/DRAFT-issues.md`,
   **When** each is checked against existing issues, **Then** new ones are
   filed with the maintainer's OK and the rest are marked as duplicates or
   fixed.

---

### Edge Cases

- **The exclusive-only call is buried**, for example reached through an alias
  (`ws = project.WritingSystems; ws.Add(...)`), or through a helper defined in
  the same script. Detection must follow the same resolution rules the existing
  mutation detection uses. It must not be weaker than them.
- **The probe cannot tell** (`unknown` verdict). The gate must fail closed for
  exclusive-only calls: refuse, and say the server could not confirm that FLEx
  is closed. Ordinary writes keep today's behavior on `unknown`.
- **FLEx is closed between the refusal and the re-submit**, but a leftover
  process still holds the lock. The existing `held_by_other` refusal applies.
- **The writing-system operation is read-only** (listing or reading writing
  systems). It must not trigger the gate. Only add, modify and delete count.
- **Project delete, restore or rename.** LCM already refuses a rename with
  peers attached. FLEx's own in-use guard cannot see a pythonnet peer when it
  backs up, restores or deletes. The server exposes none of these today. If one
  is added later, it gets a row in the same table.
- **Parse tools** that write (filing parses) take their own write path. They do
  not touch writing systems or custom fields, so the gate does not apply to
  them. This assumption must be checked during planning.

## Requirements *(mandatory)*

### Functional Requirements

**The gate (US1, US2)**

- **FR-001**: The server MUST keep one table of exclusive-only operations.
  Each entry MUST carry the operation names (flexicon wrapper names and raw LCM
  names), a plain-language reason, the failure class (`crashes_holder` or
  `silently_lost`) and the evidence.
- **FR-002**: The table MUST cover:
  - **Writing systems**, flexicon `WritingSystemOperations`: `Create`,
    `Ensure` (it adds the writing system when absent), `Delete`, and the
    modifiers `SetFontName`, `SetFontSize`, `SetRightToLeft`,
    `SetDefaultVernacular`, `SetDefaultAnalysis`. Planning MUST check whether
    `Duplicate` can reach a writing system.
  - **Custom fields**, flexicon `CustomFieldOperations` schema changes:
    `CreateField`, `DeleteField`, `SetFieldName` (the "rename").
  - **Raw LCM names** (verified in LCM source, `research.md` R3): metadata
    cache `AddCustomField`, `UpdateCustomField`, `DeleteCustomField`;
    `FieldDescription.UpdateCustomField` and `MarkForDeletion`; writing-system
    manager `Set`, `GetOrSet`, `Replace`, `Save`;
    `AddToCurrentVernacularWritingSystems`,
    `AddToCurrentAnalysisWritingSystems`; `Add`/`Remove` on the four
    writing-system lists; the `WritingSystemServices` mutators. Manager and list
    calls are matched on their receiver, never on a bare `.Set(` or `.Add(`. Raw names are reachable only from user-submitted code, so
    detection MUST match them in the script itself.
- **FR-002a**: Reads and value edits MUST NOT trigger the gate. That includes
  every writing-system `Get*`, `Exists*` and display method, and the
  custom-field value methods `SetValue`, `AddListValue`, `RemoveListValue`,
  `SetListFieldSingle` and `SetListFieldMultiple`. Matching on a `Set*` or
  `Add*` prefix is not acceptable (SC-002).
- **FR-003**: The server MUST detect exclusive-only calls in a submitted script
  before it runs. Detection MUST use the same parse, alias resolution and
  ignored-region rules as the existing mutation detection.
- **FR-004**: When the access probe reports a live FLEx peer (`open_shared`)
  and the script contains an exclusive-only call, `run_module` MUST refuse with
  the new error code `requires_exclusive_access` before running any project
  code, and before the pre-write backup.
- **FR-005**: If an exclusive-only call is detected in a write-enabled run,
  the access probe MUST run even when the script certified as read-only. The
  gate applies only to write-enabled runs.
- **FR-006**: On an `unknown` probe verdict, exclusive-only calls MUST be
  refused, with a message saying FLEx could not be confirmed closed.
- **FR-007**: `open_exclusive` and `held_by_other` MUST keep their existing
  `project_locked` refusal. This gate MUST NOT replace or reword it.
- **FR-008**: The refusal MUST name each matched operation, its reason and
  failure class, and the recovery steps: close FLEx, re-submit unchanged,
  reopen FLEx afterwards.
- **FR-009**: `validate_only` MUST report the refusal the real run would give.
- **FR-010**: The new code MUST have a specific recovery hint, so a retry loop
  does not get the generic fallback.
- **FR-011**: The generic "close FieldWorks and retry" fallback MUST NOT appear
  for failures on an `open_shared` project, unless the failure is this gate's.
- **FR-012**: The new code MUST go through the full contract process: a detail
  model, a golden fixture, a row in `docs/TOOL-CONTRACT.md`, and the error-code
  count updated everywhere it is stated. The change is additive under the
  current contract version.
- **FR-013**: The after-the-fact custom-field and writing-system warning in the
  `open_shared` advisory MUST be removed or reworded, since the gate now
  refuses those runs up front.

**Live evidence (US3)**

- **FR-014**: The CP5-a test MUST be replaced by a procedure that writes a
  custom-field definition from a peer by a route that does not hit flexicon's
  transaction refusal, or this feature MUST record why no such route exists
  and file the gap upstream.
- **FR-015**: The writing-system refusal and the close-FLEx-and-resubmit cycle
  MUST be verified live on Sena 3, with the evidence recorded in this feature's
  `evidence/` folder.

**Documentation (US4)**

- **FR-020**: `docs/workflow-summary.md` MUST lose its "Inspect & Undo" stage
  and every reference to `flextools_undo_last_operation`. Inspection tools that
  do exist (operation logs, session history) stay, described without undo.
- **FR-021**: `docs/FLEXTOOLS-STYLE-GUIDE.md` MUST NOT say that a tool can
  reverse a write.
- **FR-022**: The Undo section of `docs/SHARED-MODE.md` MUST state the four
  facts in Section 2: no MCP undo; FLEx Undo starts empty on open, so it cannot
  reach writes made while FLEx was closed; FLEx records peer writes made while
  it is open as non-undoable, so its Undo cannot reach them either;
  programmatic undo through LCM is not built.
- **FR-023**: `docs/SHARED-MODE.md` MUST say how to see a peer write in an open
  FLEx window (navigate away and back; F5 is not enough).
- **FR-024**: The "Close FLEx for these" section MUST describe the refusal as
  shipped, and give the error code.
- **FR-025**: `CHANGELOG.md` `[Unreleased]` MUST carry the new error code and
  the documentation corrections.
- **FR-026**: Tool descriptions that mention undo (`tool_definitions.py`) MUST
  be reviewed. Any wording that suggests the MCP can undo a write MUST be
  corrected.

**Read-back (US5)**

- **FR-030**: The feature MUST establish live whether a commit at the start of
  a write-enabled session (`SaveChanges()` under `undoable=True`,
  `SyncForeignChanges()` under `undoable=False`) makes it see a prior peer's
  committed write.
  Read-only sessions cannot call it (source-established).
- **FR-031**: If it works, write-enabled runs on an `open_shared` project MUST
  sync before running the script. The `shared_mode_read_back` note on
  read-only results MUST state the read-only limit accurately.

**Filing (US6)**

- **FR-040**: Each of the four upstream hazards MUST end as a filed flexicon
  issue or as "already fixed" with the commit, and `docs/SHARED-MODE.md` MUST
  link the result.
- **FR-041**: Each draft in the archived `DRAFT-issues.md` MUST end as filed,
  duplicate (with the issue number) or fixed. Nothing is filed without the
  maintainer's OK.

### Key Entities

- **Exclusive-only operation entry**: operation names (wrapper and raw), reason,
  failure class, evidence reference. The single source the gate, the docs table
  and the refusal message all draw from.
- **`requires_exclusive_access` refusal**: matched operations (each with
  reason and failure class), the probe verdict and holder, and recovery steps.
- **Access verdict**: the existing five-state probe result plus `unknown`. This
  feature consumes it; it does not change it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With FLEx open in shared mode, 100% of submitted scripts that add
  or modify a writing system, or create, delete or rename a custom field, are
  refused before any project code runs. FLEx never crashes from an MCP
  writing-system change during live verification.
- **SC-002**: Zero ordinary lexicon edits (glosses, forms, senses, entries,
  possibility-list items) are refused by the new gate in the existing test
  corpus and in live verification.
- **SC-003**: After a refusal, a user can close FLEx, have the identical
  request succeed past the gate, and reopen FLEx, all in one conversation
  without the assistant rewriting the script.
- **SC-004**: A search of shipped docs and tool descriptions finds zero
  references to `flextools_undo_last_operation` and zero claims that the MCP
  can undo a write.
- **SC-005**: Every item the predecessor left unfiled has a recorded outcome:
  an issue number, a duplicate reference, or a fix reference.

## Assumptions

- The interim policy of 2026-09-08 stands: writing-system and custom-field
  changes both need FLEx closed. The gate ships on that policy, without waiting
  for the custom-field live result (US3).
- Sharing detection, the access probe and its verdicts are correct as shipped
  in #93 and are reused unchanged.
- flexicon's `CustomFieldOperations.CreateField` still fails with
  `FP_TransactionError` in the current release (checked 2026-09-30 in the
  flexicon working tree). The custom-field row still matters, because raw LCM
  calls and any future flexicon fix can reach the hazard.
- Wrapper names in FR-002 come from the flexicon working tree on 2026-09-30
  and MUST be re-checked against the shipped flexicon index during planning.
- The LCM-level claims were checked against `sillsdev/liblcm@master` during
  planning (`research.md`).
- Programmatic undo through LCM is out of scope (see below).

## Out of scope

- **Building undo.** That covers undoing MCP writes through LCM, and supplying
  undo metadata so FLEx's Undo can reverse peer writes. If the maintainer wants
  either, it gets its own spec, starting from a live test of whether a peer
  write made while FLEx is open shows up in FLEx's Edit > Undo.
- **#315** (lock held by a python process the model cannot end). Fixed
  separately.
- **Writing `LexiconSettings.plsx`** to turn sharing on. The #93 decision
  stands: the server never writes it, and the user turns sharing on in FLEx.
- **Send/Receive, data migration and project rename.** FLEx or LCM already
  refuse these with peers attached.
