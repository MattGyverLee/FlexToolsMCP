# Live FieldWorks session checklist -- #93 (one sitting)

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

## Session 2 (later, ~10 minutes, only after CP5 code lands)

**CP5-a** -- with FLEx open on the sharing-ON project, call
`CustomFieldOperations.CreateField`.
**PASS:** refused with `requires_exclusive_access` (not a silent no-op, not a
generic lock error). Then close FLEx, re-submit the **identical** call ->
succeeds. Reopen FLEx and confirm the new custom field is present in the UI.
This is the acceptance test for the whole CP5 gate and cannot be run before the
gate exists.
