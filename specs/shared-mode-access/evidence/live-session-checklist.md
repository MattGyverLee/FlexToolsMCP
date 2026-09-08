# Live FieldWorks session checklist -- #93 (one sitting)

> **STATUS: session 1 COMPLETE, run 2026-09-08 against `Sena 3`.**
> All of items 0-8 are done. Results, verbatim, in
> [`live-cp4.md`](live-cp4.md) under `# Session 2026-09-08`.
> **CP3 and CP4 both PASS.** Q1 -> Class A (peer WS change **crashes**
> FieldWorks), Q2 -> Class A safe, Q3 -> drops out of the CP5 table.
> Follow-up work is queued in
> [`live-session-followups.md`](live-session-followups.md).
> Only "Session 2" below is still outstanding.
>
> Note the checklist was deliberately **reordered** on the day: `Sena 3` was
> found sharing-OFF and already open, i.e. sitting in the item 4 trigger state,
> so item 4 part 1 was banked first and the one project was then run through
> both roles. Rationale recorded in `live-cp4.md` section 0.

**Authorized by:** the user only. The crew does not run any of this.
**Produced:** 2026-09-07, lex-lead cycle 7 close.
**Covers:** every live-gated item outstanding for CP3 and CP4, plus the three
OPEN questions that decide CP5's Section 3 rows. **CP5-a is NOT in this
session** -- the CP5 gate code does not exist yet; it needs a second, much
shorter sitting after CP5 lands (see "Session 2" at the bottom).

Record every result inline in `specs/shared-mode-access/evidence/live-cp4.md`
(append a `## Session 2026-XX-XX` section). Raw output pasted verbatim beats a
summary -- the whole reason this gate exists is that prose claims about live
behaviour have been wrong before.

---

## 0. Pre-flight -- BEFORE starting FieldWorks

| # | Do | Pass criterion |
|---|---|---|
| 0a | Pick the sharing-**ON** project. `Claude-Swahili` and `Target` both have `projectSharing="true"`. Items 1-3 and 5-7 run against **one** of them; prefer `Target` (the CLAUDE.md scratch project) because items 5-7 are schema-level. | Project name written down. |
| 0b | **Take a restorable backup of that project.** FLEx: *File > Back up this Project*. Items 5-7 mutate schema/lists and may not be undoable. | A `.fwbackup` exists with today's date. |
| 0c | Pick the sharing-**OFF** project for item 4. If you have none, make one: copy a small project, open it, *File > Project Properties > Sharing* -> **off**, close FLEx. | A second project name written down, sharing confirmed off. |
| 0d | Confirm the MCP server is running the current tree (six local commits through `7a4fa5c`). Restart the MCP server if it was started before those commits. | `flextools_health()` returns without error. |

---

## 1-3. Sharing-ON project, **FieldWorks OPEN** (start FLEx now, open the project from 0a, leave it open for items 1-7)

### 1. CP4-a -- the probe sees the live FLEx holder

```
flextools_health(verbose=True)
```

**PASS:** the project access / lock block reports `verdict: "open_shared"`,
`sharing_enabled: true`, and `holder_pid` equal to the **real FieldWorks PID**
(cross-check in Task Manager, or `tasklist | findstr -i fieldworks`), with a
`holder_process` naming FieldWorks -- not `python`, not `unknown`.
**FAIL shapes to capture:** `open_exclusive` (sharing flag not being read),
`held_by_other` (FieldWorks process-name matcher is wrong), or a `python` PID
(the probe read a stale MCP lock instead of FLEx's).

### 2. CP4-b -- read-only run with FLEx open

```
flextools_run_module(project="<project from 0a>", code=<<<
for entry in project.LexEntry.GetAll()[:5]:
    report.Info(project.LexEntry.GetLexemeForm(entry))
>>>)
```

**PASS:** the run completes and lists entries. No `project_locked` refusal, no
"Close FieldWorks" advice anywhere in the response.

### 3. CP4-c -- **the single most load-bearing observation in this feature**

A write, with FLEx actually running and holding the project, that lands *and is
visible in the FLEx UI*. Everything CP4 and CP5 assume rests on this.

```
flextools_run_module(project="<project from 0a>", write_enabled=True, code=<<<
entries = project.LexEntry.GetAll()
entry = entries[0]
senses = project.LexEntry.GetAllSenses(entry)
report.Info("before: " + repr(project.Senses.GetGloss(senses[0])))
if modifyAllowed:
    project.Senses.SetGloss(senses[0], "CP4LIVE-<today's date>")
report.Info("after: " + repr(project.Senses.GetGloss(senses[0])))
>>>)
```

**PASS -- all three legs, in order:**
1. The run is **not refused**; the response carries the `open_shared` advisory
   (a note that the write proceeds because sharing is on), not a refusal.
2. `report` shows the gloss changed from its old value to `CP4LIVE-...`.
3. **In the FieldWorks window**, refresh (F5, or click away to another entry and
   back) and confirm the new gloss is visible **without restarting FLEx**.
   *If leg 3 fails but legs 1-2 pass*, that is a MAJOR finding, not a wash:
   it means the peer write landed only in the shared commit log and the master
   never picked it up -- exactly the #96 staleness shape. Capture it verbatim
   and stop before item 5; the crew must re-rule on CP4's message wording
   ("writes are expected to succeed") before CP5 is built on top of it.

---

## 4. CP3 -- sharing-OFF project, FieldWorks OPEN

Close the 0a project in FLEx and **open the sharing-OFF project from 0c** (or
run a second FLEx instance if you prefer; one at a time is cleaner).

```
flextools_run_module(project="<project from 0c>", code=<<<
report.Info(str(len(project.LexEntry.GetAll())))
>>>)
```

**PASS (part 1):** the response contains the **enable-sharing recipe** -- text
telling you to turn on *Project Properties > Sharing* -- and **NOT** the
generic "Close FieldWorks and retry" hint. That distinction is the entire CP3
checkpoint (SPEC.md:233-235, Verification step 5 final bullet).

**Then (part 2):** in FLEx, enable sharing on that project, close and reopen
FLEx, and re-run the identical call.

**PASS (part 2):** it now proceeds with no further prompting -- no recipe, no
lock hint, no refusal.

---

## 5-7. OPEN questions (schema-level; the backup from 0b is your undo)

Re-open the 0a sharing-ON project in FLEx and leave it open. These three decide
whether the corresponding rows in SPEC.md Section 3c ("Unclassified -- pending
live test") become Class A (`refused`, safe by construction), Class B
(`silently_lost`, must be gated by CP5), or drop out of the table.

For each: run the write with FLEx open, then **check the FLEx UI**, then
**close and reopen FLEx** and check again. The difference between those two
checks is the whole finding -- a change visible before the restart but gone
after it is `silently_lost`, the dangerous class.

### 5. Q1 -- writing system add/change

Add or modify a writing system through the MCP while FLEx is open (or, if no
MCP path exists, attempt it and record the error).
**Record:** refused outright / applied and survives restart / applied then lost
/ FLEx UI corrupted. **Decides:** whether writing systems belong in T5.1 at all.

### 6. Q2 -- possibility-list item mutation

Add or rename a semantic-domain (or other possibility-list) item with FLEx open.
**Record:** same four outcomes. **Decides:** Class A vs Class B for lists.

### 7. Q3 -- reversal index create/regenerate

Create or regenerate a reversal index with FLEx open.
**Record:** same four outcomes, plus whether FLEx's own reversal view is
consistent afterwards. **Decides:** a Section 3 row that SPEC currently does
not cover at all.

---

## 8. Wrap-up

| # | Do |
|---|---|
| 8a | Close FieldWorks. |
| 8b | Append everything to `specs/shared-mode-access/evidence/live-cp4.md` -- verbatim output for items 1-4, four-outcome verdicts for 5-7. |
| 8c | If item 3 leg 3 FAILED, say so loudly at the top of that section. It changes CP4's ruling. |
| 8d | If anything in items 5-7 damaged the project, restore the 0b backup. |
| 8e | Tell the crew to resume: CP3 and CP4 sign off, and CP5's Section 3 rows get classified from items 5-7. |

---

## Session 2 (later, ~20 minutes; item 1 only after CP5 code lands)

### 1. CP5-a -- WITHDRAWN as written; needs redesign before it can be scheduled

> **Updated 2026-09-08 (second sitting).** This test is invalid as specified,
> and the reason is not that the CP5 gate is missing. **Its second leg cannot
> pass no matter what CP5 does.** Do not schedule it, and do not treat a
> first-leg pass as evidence for CP5.

The test as originally written:

> With FLEx open on the sharing-ON project, call
> `CustomFieldOperations.CreateField`.
> **PASS:** refused with `requires_exclusive_access` (not a silent no-op, not a
> generic lock error). Then close FLEx, re-submit the **identical** call ->
> succeeds. Reopen FLEx and confirm the new custom field is present in the UI.

**Why it cannot work.** `CreateField` refuses unconditionally with
`FP_TransactionError`, independent of FLEx state and of shared mode, because
Phase 1 transaction mode opens a non-undoable UnitOfWork at `OpenProject()`
that stays open until `CloseProject()`, and LCM forbids schema mutation inside
an active task. So:

- the "close FLEx, re-submit -> **succeeds**" leg fails with FLEx closed too;
- and a first-leg refusal would be the *transactional* refusal, not an
  access-based one -- the right outcome for the wrong reason, which is worse
  than a clean failure because it looks like CP5 working.

Verbatim evidence: `evidence/live-session2.md`, Item D.

**What a redesigned CP5-a needs.** An exclusive-only operation that genuinely
*can* succeed when FLEx is closed, so the refuse/resume cycle is observable
end to end. `CreateField` is not that operation. Candidates should be checked
against the same transaction constraint before being adopted -- the constraint
is a property of Phase 1 mode, not of custom fields specifically, so any other
schema mutation is likely to hit it too. Redesigning this is a prerequisite
for CP5, not a follow-up to it.

**Interim policy (user decision, 2026-09-08):** CP5 stays open, and in the
meantime both writing-system and custom-field operations are *assumed* to
require exclusive access. See the CP5 status block in `SPEC.md`. That is a
documentation and review policy; nothing enforces it in code today.

*Note from session 1, still valid for any future custom-field test:* `Sena 3`
already carries custom fields (`Plural` and `Singular` on LexEntry,
`Parsing Note` on LexSense), so pick an unused name. Confirmed again in the
second sitting: LexEntry 2, LexSense 1, `ClassBProbe93` unused.

### 2. Derived-field confirmation -- no CP5 code needed

Session 1 established that a reversal index's `Name`, written via the **default**
writing system, is reverted by FLEx on project open, while an explicit-WS write
survives. The leading explanation is that FLEx maintains that field as
**derived** from the writing system (the user's point: naming the English index
"English" is circular). Item 6 supported this -- an ordinary semantic-domain
default-WS write survived the same restart -- but the decisive test has not run.

**Test:** with FLEx **fully closed**, run the default-WS
`ReversalIndexes.SetName`, then open FLEx and re-read.
**Interpretation:** still reverted with no peer involved at any point ->
derived-field explanation proven, shared mode conclusively irrelevant to Q3.
Survives -> the revert really is peer-specific and Q3 returns to the CP5 table.

### 3. Empty-index visibility -- no CP5 code needed

The peer-created reversal index on vernacular `seh` never appeared anywhere in
the FLEx UI. All three indexes held **0 entries** throughout, so emptiness is
ruled out as the *sole* cause (`en` and `pt` were equally empty and both
displayed) -- but a conjunctive rule like "display if analysis WS **or** has
entries" is untested.

**Test:** recreate a reversal index on a vernacular WS, add a reversal
**entry** to it, and check the main Reversal Index view.
**Then delete it again** -- and note finding (l): `WritingSystems.Delete` left
residue on disk, so verify the reversal delete is complete too.

### 4. Layout-list baseline -- no CP5 code needed, do it before touching anything

Session 1 had to retract a finding because the reversal **layout** list
(`English, English, Portuguese`) was cited as evidence about a specific index
without a before-reading. It still showed three entries after the `seh` index
was deleted, which suggests it is pre-existing `Sena 3` configuration.

**Test:** record what that layout list contains on a clean `Sena 3`, before any
write. If it was already 3 entries -> unrelated, close it out. If it went
2 -> 3 during session 1 -> the delete left an orphaned layout behind, which is a
new finding worth chasing.

---

## Preconditions (added 2026-09-08, post-session-1)

State as of right now, verified live (not reported): `Sena 3` has
`projectSharing="true"` (sharing ON) and FieldWorks is OPEN holding it. This
is the current as-found state -- do not write "Sena 3 is sharing OFF"
anywhere; that was true earlier on 2026-09-08 and is now stale.

Per-test preconditions, since the four tests below do not all need the same
machine state:

1. **Test 1 (CP5-a) -- BLOCKED, and not by scheduling.** The precondition
   that matters first is that **the CP5 gate code must exist**.
   `specs/shared-mode-access/.crew-handoff.json` -> `checkpoints_remaining.CP5`
   reads "SCOPED + SPEC AMENDED, NOT IMPLEMENTED". `CustomFieldOperations.CreateField`
   cannot be refused with `requires_exclusive_access` by code that has not
   been written -- leg 1 of this test would assert against a gate that does
   not exist and cannot pass. A human at a live FLEx install is also
   required, but that is secondary: do not schedule this test as though the
   only thing missing is a person at the keyboard.
   - Once CP5 lands: `Sena 3` already has custom fields (`Plural`, `Singular`
     on `LexEntry`; `Parsing Note` on `LexSense`), so pick an unused field
     name.
   - Sharing state needed: ON, FieldWorks open (matches current as-found
     state -- no flip needed for this test).
   - **Proposed companion/replacement test, not yet approved:** SPEC.md
     Section 3's Class B mechanism (custom fields being silently swallowed)
     is derived entirely from liblcm source
     (`SharedXMLBackendProvider.cs:478/:408`, `BackendProvider.cs:506-515`,
     `CommitLogRecord.cs:17-49`) and has never been empirically observed --
     yet CP5 is being built on it. An empirical confirmation of that
     mechanism (peer creates a custom field with FLEx open, FLEx is fully
     closed and reopened, field is absent with no error at any point) would
     be more load-bearing than CP5-a and does not require CP5 code to exist.
     This is a proposal for the crew/user to rule on, not a run instruction
     -- it is user-gated like every other live test in this file and has not
     been authorized.
2. **Test 2 (derived-field confirmation) -- needs FLEx FULLY CLOSED.**
   Sharing state is irrelevant while FLEx is closed (no peer is involved at
   any point, which is the entire point of this test), but FLEx must
   actually be closed, not just minimized -- the test's interpretive value
   depends on no live holder existing during the write.
3. **Test 3 (empty-index visibility) -- needs FLEx OPEN.** Sharing state:
   ON (matches current as-found state). Needs a *clean* reversal-index
   baseline: confirm `Sena 3` currently holds exactly the two indexes
   (`English`/`en`, `Portuguese`/`pt`) recorded at the end of session 1
   before adding the vernacular-WS test index.
4. **Test 4 (layout-list baseline) -- needs FLEx OPEN, and needs to run
   FIRST among 3-4**, before any reversal-index write, since it is reading a
   baseline that a test-3 write would otherwise disturb.
5. **A sharing-OFF re-test of the CP3 item-4-part-1 criterion** (if anyone
   wants to re-verify CP3 rather than rely on the 2026-09-08 sign-off) is
   NOT one of the four Session 2 tests above, but if run: `Sena 3` must be
   flipped **OFF** first (it is currently ON, the opposite of session 1's
   starting state) and then restored back to **ON** afterwards, since ON is
   what the user left it at and where it currently sits.

**A human must be physically at a live FLEx install** for tests 1 (once
CP5 exists) and 3; test 2 needs a human only to close/reopen FLEx, not to
observe a UI (it is read back through the MCP).

**Process lesson carried forward from session 1:** capture a BEFORE-state
for every UI surface you intend to cite, not just for the database. One
session-1 finding had to be retracted (`196a9c7`) precisely because a UI
list was cited as evidence without first establishing what it enumerates
or capturing a before-reading of it -- see `live-cp4.md` "RETRACTION"
(`:1012`) and its process note. Test 4 above exists specifically to apply
this lesson to the reversal-layout list before it is touched again.
