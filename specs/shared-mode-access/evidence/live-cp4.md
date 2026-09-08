# Live evidence -- #93 CP4 (writes allowed in shared mode)

**Date:** 2026-08-19
**Machine:** the user's Windows 11 box, FieldWorks projects at
`C:\ProgramData\SIL\FieldWorks\Projects` (resolved from the registry)
**Runtime under test:** `D:/Apps/anaconda3/python.exe` -- the same interpreter
the MCP server is configured to run -- with `pyflexicon 4.3.1` installed
**Scripts:** `run_live_peer.py` / `live_shared_peer.py` / `live_control.py`
(scratchpad; reproduced below)

---

## 1. What was verified live, and what was not

CP4's own checkpoint is *"a write `run_module` against an `open_shared`
project succeeding and visibly appearing in the FLEx UI."* **That was not
run: FieldWorks was not running on this machine at the time** (`tasklist`
showed no FieldWorks process), and starting it and enabling sharing on a
project is a human decision, not something to do unattended.

What *was* verified live is the LCM premise the whole checkpoint rests on:
**can a second process attach and write while a first process holds the
project open, and does the `projectSharing` flag decide it?** If that were
false, "proceed on `open_shared`" would merely move the failure from the
pre-flight gate into LCM, and CP4 would be wrong.

Both halves were run against real projects, in separate OS processes, with
the value read back from a **fresh** process rather than asserted on the
value passed in.

## 2. Experiment A -- sharing ON: the peer write lands (PASS)

Project **`Target`** (`projectSharing="true"`, the CLAUDE.md scratch project
for write-path work). Process 1 opened it read-only and held it; process 2
then opened it write-enabled and created a `TEST_`-prefixed entry.

```
holder is up, PID 48280; project is now locked by a live python process
probe verdict while held: held_by_other sharing=True
    holder=LockHolder(pid=48280, process_name='python', timestamp_ticks=639226984916918706)

===== write =====                     <- process 2, while process 1 still holds it
[INFO] opened Target writeEnabled=True ui=HeadlessLcmUI
[PRE ] entry count = 0                <- pre-state, read from the LCM
[WRITE] created 'TEST_cp4_peer' -> True
[POST] closed; pre-state count was 0

===== read =====                      <- process 3, after both closed
[INFO] opened Target writeEnabled=False ui=HeadlessLcmUI
[READ] total entries = 1              <- post-state, re-queried from the LCM
[READ] 'TEST_cp4_peer' present after reopen = True
PASS

===== cleanup =====
[CLEAN] removed 1 entr(ies) named 'TEST_cp4_peer'
```

- **pre-state:** `Target` held 0 lexical entries.
- **post-state (re-queried in a fresh process):** 1 entry, `TEST_cp4_peer`.
- **Target was left as found** -- the entry was deleted in the cleanup pass.

A plain `XMLBackendProvider` would have thrown on the second open. It did
not; the write went through and persisted. That is
`SharedXMLBackendProvider` behaving exactly as `LcmCache.cs:211-226`
describes.

## 3. Experiment B -- control, sharing OFF: LCM refuses (PASS)

The same two-process open against **`Sena 3`** (`projectSharing="false"`).
Both opens read-only, so nothing in Sena 3 was touched.

```
holder up on 'Sena 3' (sharing=false), PID 65216
probe verdict while held: held_by_other sharing=False
    holder=LockHolder(pid=65216, process_name='python', timestamp_ticks=639226985614725804)
SECOND OPEN REFUSED BY LCM: FP_FileLockedError: This project is in use by
    another program. To allow shared access to this project, turn on the
    sharing option in the Sharing tab of the Fieldworks Project Properties
    dialog.

CONTROL: PASS (second open refused, as expected)
```

The flag is the discriminator, and nothing else. This is the exact failure
the CP4 gate now refuses *ahead of* LCM, with an actionable remedy instead
of that message.

## 4. Probe accuracy against all 87 real projects (PASS)

`probe_project_access()` was run over every project in the real projects
directory:

```
Counter({'free': 86, 'held_by_other': 1})

Hdi: verdict=held_by_other sharing=False
     holder=LockHolder(pid=47648, process_name='python', ...)
```

`Hdi` carries a `.fwdata.lock` naming a **live** python PID -- a leftover
FLExTools/MCP subprocess. The probe identified the holder and its liveness
correctly; the old gate could only have said "a lock file exists."

## 5. Honest limitation found by this run

In both experiments the holder was a **python** process, so the probe
returned `held_by_other` -- which CP4 **refuses** (per the SPEC's T4.1
table) -- while LCM itself **allowed** the write in Experiment A. The gate
is therefore stricter than LCM strictly requires for a python holder on a
sharing-enabled project.

That is the SPEC's settled choice ("a live non-FieldWorks holder is a real
collision", usually a leftover subprocess of our own), and it fails safe.
It is recorded here rather than quietly ignored: if it turns out to bite in
practice, the fix is to route `held_by_other` + `sharing_enabled is True`
to the same proceed path as `open_shared`, and the evidence that this is
safe is Experiment A above.

## 5b. Re-run after deployment (PASS)

After the editable install of this branch into
`D:/Apps/anaconda3/python.exe` and the pyflexicon upgrade **4.3.1 ->
4.4.1**, Experiment A was re-run end to end and passed identically
(holder PID 63088, pre-state 0 entries, post-state 1 entry re-queried in a
fresh process, `Target` restored). `scripts/validate_integrity.py` reports
`flexicon version: 4.4.1`, `43/43 Operations`, contract check passed, and
the MCP suite is 990 passed / 2 skipped on the same interpreter.

## 6. Still owed before CP4 can be called complete

- The **`open_shared` path itself** has not been exercised live -- it needs
  FieldWorks running, holding a sharing-enabled project. Unit coverage
  (`tests/test_shared_mode_write_gate.py::TestGateWiring`) exercises the
  handler's branch, but not LCM's behaviour under a real FLEx master.
- The **"visibly appears in the FLEx UI"** half of the checkpoint is by
  definition a human observation.

Per CLAUDE.md this is a `needs_human` item, not a pass to be assumed.

## Reproducing

```
# A: sharing ON -- peer write must land
D:/Apps/anaconda3/python.exe run_live_peer.py

# B: control, sharing OFF -- second open must be refused
D:/Apps/anaconda3/python.exe live_control.py
```

---

# Session 2026-09-08 -- live FieldWorks sitting (checklist run)

**Authorized and driven by:** the user, at the keyboard, with FieldWorks running.
**Checklist:** `specs/shared-mode-access/evidence/live-session-checklist.md`
**Target project:** `Sena 3` (the user's choice) -- used for BOTH roles, see below.

## 0. Pre-flight (items 0a-0d)

Machine state as found, before anything was run:

| Project | `projectSharing` in `SharedSettings/LexiconSettings.plsx` | Lock holder |
|---|---|---|
| `Sena 3` | **attribute absent -> OFF** | FieldWorks PID **35236** (started 09:23:51) |
| `Claude-Swahili` | `"true"` -> ON | FieldWorks PID 41464 (started 09:23:31) |
| `Target` | `"true"` -> ON | not open |

Two FieldWorks instances were live. `Sena 3.fwdata.lock` verbatim:

```
{"__type":"FileLockContent:#Palaso.IO.FileLock","PID":35236,"ProcessName":"FieldWorks","Timestamp":639244562327878323}
```

- **0a/0c -- deviation from the checklist, deliberate.** The checklist assumed a
  sharing-ON project for items 1-3/5-7 and a *separate* sharing-OFF project for
  item 4. `Sena 3` was found sharing-**OFF** and already open, i.e. sitting in
  exactly the item-4 trigger state. So the checklist was **reordered** to run
  `Sena 3` through both roles in sequence: item 4 part 1 FIRST (while sharing is
  still off), then enable sharing on `Sena 3` for item 4 part 2, then items 1-3
  and 5-7 against the now-sharing-ON `Sena 3`.
  Rationale: once sharing is on, the CP3 observation is unrecoverable without
  turning it back off, so it had to be banked first. This is strictly more
  evidence than the original plan, not less -- the same project is observed on
  both sides of the flag flip, with the FLEx holder PID unchanged in kind.
- **0d -- PASS.** MCP server PID 49416 started 2026-09-08 09:22:41; the newest
  commit in the tree is `5e3d23b` at 09:07:17, and `7a4fa5c` (the cycle-7 fix)
  at 2026-09-07 20:48:05. The running server therefore post-dates both.
  `flextools_health()` returned without error: server 2.9.1, FieldWorks 9
  detected, liblcm 11.0.0, flexicon 4.5.2 / liblcm 11.0.0 / flexlibs_stable
  1.2.8 all `match: "exact"`.

## Item 4 part 1 -- CP3, sharing-OFF project with FieldWorks OPEN: **PASS**

Session: `api_mode=flexicon`, `project_name="Sena 3"`, `write_enabled=False`.
`LexEntryOperations` was discovered first (`flextools_get_object_api`) so that
the only gate left to fire would be the lock gate.

Call:

```
flextools_run_module(project_name="Sena 3", write_enabled=False,
                     code='report.Info(str(len(project.LexEntry.GetAll())))')
```

Response, verbatim (op `op-092802240-001`):

```json
{
  "success": false,
  "error": "Project 'Sena 3' is currently locked by another process.",
  "error_code": "project_locked",
  "verdict": "open_exclusive",
  "sharing_enabled": false,
  "holder_pid": 35236,
  "holder_process": "FieldWorks",
  "raw_error": "Failed to open project 'Sena 3': This project is in use by another program. To allow shared access to this project, turn on the sharing option in the Sharing tab of the Fieldworks Project Properties dialog.",
  "remedy": "FieldWorks has this project open and project sharing is OFF, so LCM took the .fwdata lock exclusively and no other process can write to it. To let this server write while you keep FLEx open: in FieldWorks go to File > Project Management > FieldWorks Project Properties > Sharing tab, tick \"Share project contents with programs on this computer\", and click OK. FLEx will ask to reopen the project -- let it, because the flag is read once when the cache opens (LcmCache.cs:219). Then re-submit this same call: it re-checks the setting and continues automatically. This server never writes LexiconSettings.plsx on your behalf.",
  "write_certification": {"is_certified_readonly": true, "confidence": "high", "mutating_calls_detected": []}
}
```

`help`, `hint` and `remedy` all carried that same enable-sharing text.

**Why this is a PASS on the CP3 criterion specifically** (SPEC.md:233-235,
Verification step 5 final bullet): the response contains the **enable-sharing
recipe** and **not** the generic "Close FieldWorks and retry" hint. The remedy
goes further than the checklist required -- it explicitly frames the fix as
"while you keep FLEx open", which is the opposite of the close-FLEx advice the
checkpoint was written to rule out.

Secondary confirmations from the same response:
- `verdict: "open_exclusive"` -- the sharing flag was read, and read correctly
  as off (absent attribute -> False, per `project_access.py:211-236`).
- `holder_pid: 35236` matches the real FieldWorks PID from `tasklist` and from
  the `.fwdata.lock` contents above -- **not** a python PID, so the probe read
  FLEx's own lock and not a stale MCP one.
- `holder_process: "FieldWorks"` -- the process-name matcher works against a
  genuine FieldWorks process, which no prior run had exercised (all earlier
  live evidence used python holders; see section 5 "Honest limitation").

## Item 4 part 2 -- sharing turned ON, same call re-submitted: **PASS**

The user enabled sharing in FLEx (File > Project Management > FieldWorks Project
Properties > Sharing tab). `SharedSettings/LexiconSettings.plsx` changed to
`<ProjectLexiconSettings projectSharing="true">`.

The **identical** call was re-submitted and proceeded with no recipe, no lock
hint and no refusal (op `op-093037766-002`):

```json
{"success": true, "project": "Sena 3", "write_enabled": false,
 "messages": [{"type": "INFO", "message": "1462", "ref": null}],
 "error": null, "exit_code": 0}
```

1462 entries. CP3 part 2 criterion met.

### Secondary observation -- the holder never reopened, and the peer open still worked

Worth recording because the CP3 remedy text asserts a reopen is what makes the
flag take effect ("FLEx will ask to reopen the project -- let it, because the
flag is read once when the cache opens (LcmCache.cs:219)"). Observed:

- FieldWorks PID **35236 did not restart** -- `Get-Process` start time was
  `9/8/2026 9:23:51 AM` both before and after the flag flip.
- `Sena 3.fwdata.lock` was **byte-identical** before and after: same PID and the
  same `Timestamp` ticks `639244562327878323`.
- Yet the peer open succeeded immediately after only the `.plsx` edit.

The prediction made from the remedy text ("LCM will still refuse until the
holder reopens") was therefore **wrong**. Whether FLEx reopened the project
internally without rewriting the Palaso lock file, or a reopen is genuinely
unnecessary because the *peer* reads the flag at its own cache-open, is NOT
resolved by this observation -- it needs a crew ruling. If a reopen is in fact
unnecessary, `ENABLE_SHARING_REMEDY` overstates a requirement and should be
softened.

## Item 1 -- CP4-a, the probe sees the live FLEx holder: **PASS**

`flextools_health(verbose=True)`, `project_access` block verbatim:

```json
{
  "project": "Sena 3",
  "verdict": "open_shared",
  "sharing_enabled": true,
  "holder": {"pid": 35236, "process_name": "FieldWorks",
             "timestamp_ticks": 639244562327878323},
  "lock_age_seconds": 550.063518
}
```

All three PASS criteria met: `verdict: "open_shared"`, `sharing_enabled: true`,
and `holder_pid` = **35236**, the real FieldWorks PID (cross-checked against
`tasklist` and against the `.fwdata.lock` contents), with
`holder_process: "FieldWorks"` -- not `python`, not `unknown`.

**None of the three documented FAIL shapes occurred:** not `open_exclusive`
(the sharing flag was read), not `held_by_other` (the FieldWorks process-name
matcher works), and not a python PID (the probe read FLEx's lock, not a stale
MCP one).

This is the **first time the probe has been exercised against a genuine
FieldWorks holder.** All prior live evidence in this file (sections 2-4) used
python holder processes, which is exactly the gap section 5 flagged as an
honest limitation. That gap is now closed on the `open_shared` side.

Also from the same call: `flexinit_importable: true`, `pythonnet_available: true`.

## Item 2 -- CP4-b, read-only run with FLEx open: **PASS**

Code:

    for entry in project.LexEntry.GetAll()[:5]:
        report.Info(project.LexEntry.GetLexemeForm(entry))

op `op-093355753-003`, `"success": true`, five INFO messages:

```
bubu bubu
sengere
makuantanthatu
tatu
cibese
```

No `project_locked` refusal and no "Close FieldWorks" advice anywhere in the
response. Criterion met.

## Item 3 -- CP4-c, the load-bearing write: **PASS, all three legs**

A `validate_only=True` dry run was taken first (op `op-093440633-004`): **all 11
gates passed**, and the read-only lock probe reported
`{"locked": true, "sharing_enabled": true, "verdict": "open_shared", "blocking": false}`.

Then the real write (op `op-093503117-005`), `write_enabled=True`,
`confirmed=True`. Code and output verbatim:

```python
entries = project.LexEntry.GetAll()
entry = entries[0]
form = project.LexEntry.GetLexemeForm(entry)
guid = project.LexEntry.GetGuid(entry)
senses = project.LexEntry.GetAllSenses(entry)
sense = senses[0]
report.Info("entry: " + repr(form) + "  guid=" + str(guid))
report.Info("before: " + repr(project.Senses.GetGloss(sense)))
if modifyAllowed:
    project.Senses.SetGloss(sense, "CP4LIVE-2026-09-08")
report.Info("after: " + repr(project.Senses.GetGloss(sense)))
report.Info("goto this entry in FLEx", project.BuildGotoURL(sense))
```

```
entry: 'bubu bubu'  guid=0006f482-a078-4cef-9c5a-8bd35b53cf72
before: 'gaguez'
after: 'CP4LIVE-2026-09-08'
goto this entry in FLEx
    -> silfw://localhost/link?database%3dSena+3%26tool%3dlexiconEdit%26guid%3d07086e7d-dfcc-4f4e-b0d6-0be7a7943f97%26tag%3d
```

**Leg 1 -- PASS.** Not refused, and the response carries the `open_shared`
advisory rather than a refusal:

```json
"shared_mode": {
  "verdict": "open_shared", "sharing_enabled": true,
  "holder_pid": 35236, "holder_process": "FieldWorks",
  "note": "FieldWorks has this project open with sharing enabled, so this run attached as a non-master LCM peer and wrote through the shared commit log. The change should be visible in the FLEx UI. Custom-field and writing-system changes are NOT safe from a peer and are not covered by this path."
}
```

**Leg 2 -- PASS.** Gloss went from `'gaguez'` to `'CP4LIVE-2026-09-08'`, and
`lcm_undoable_action_count: 1` confirms LCM registered one mutation.

**Leg 3 -- PASS.** The user, at the FieldWorks UI, reported verbatim:
"confirmed CP4LIVE-2026-09-08". The new gloss was visible on entry `bubu bubu`,
first sense, in the running FLEx instance (PID 35236) **without restarting
FLEx**.

The refresh gesture matters and is recorded deliberately. The user noted, before
the check: *"note that in shared projects, I have to leave and return to that
area in FLEx to see changes."* That is the gesture that was used -- navigate out
of the area and back, **not** F5 alone. It matches the `shared_mode_read_back`
primer's mechanism exactly: the master picks up a peer write through its own
live cache (`Commit` / `ReconcileForeignChanges`), not by re-reading `.fwdata`.

**Consequence for future test design:** an F5-only check is capable of producing
a false negative here, which would have been misread as the #96 staleness shape
and wrongly escalated as a MAJOR finding. Any future restatement of this
checklist item should specify leave-and-return rather than offering F5 as an
equivalent option (the current checklist line 77 offers them as alternatives:
"refresh (F5, or click away to another entry and back)").

**This closes the two items that section 6 of this file listed as still owed:**
the `open_shared` path has now been exercised live under a real FLEx master, and
the "visibly appears in the FLEx UI" human observation has been made. CP4's
premise -- that a peer write in shared mode both lands and becomes visible to
the master -- is confirmed, not assumed.

### Item 3 side-findings (NOT part of the CP4 criteria)

**(a) `write_certification` misreports a mutating run as read-only.** On the
real write above:

```json
"write_certification": {"is_certified_readonly": true, "confidence": "medium",
                        "mutating_calls_detected": []}
```

The run demonstrably mutated the database (gloss changed;
`lcm_undoable_action_count: 1`), yet it is certified **read-only** and
`mutating_calls_detected` is **empty**. The `validate_only` pass agreed:
`writeability: {"is_mutating_script": true, "mutations_detected": []}` -- so
something flags the script as mutating, but the per-call list is empty in both
places. `project.Senses.SetGloss` is not being recognised as a mutating call.

Two consequences, the second more serious than the first:

1. The confirmation gate's user-facing "mutation plan" would render blank.
2. Per the documented Rung-3 condition (refuse when the script is *certified
   mutating* AND `write_enabled=True`), a script whose certification says
   `is_certified_readonly: true` plausibly **never triggers
   `confirmation_required` at all** -- i.e. this write could have executed with
   no confirmation. The `confirmed=True` passed here may have been redundant.
   Stated as a hypothesis, to be tested by re-running a mutating script with
   `confirmed=False` (the owed gloss restore is being used as that probe).

**(b) No rollback was in effect.** `stderr` verbatim:

```
OpenProject: writeEnabled=True with an explicit undoable=False. This opts OUT of
per-operation units of work, which is the default since 4.4.0. In this legacy
mode Transaction() is a labelling/nesting construct only -- liblcm exposes no
reachable rollback-to-mark API in this mode (issue #236). The atomicity unit for
this whole session is the SESSION, not the operation: if code raises
mid-operation, every mutation applied before the failure remains in the
in-memory cache and will be written to disk by CloseProject()/SaveChanges().
Drop the argument to get rollback back.
```

The MCP runner is opening projects in the no-rollback legacy mode. Directly
relevant to items 5-7, where a partial failure mid-schema-change cannot be
rolled back.

**(c) The server pre-empted the safety question about custom fields and writing
systems.** The `shared_mode.note` already asserts "Custom-field and
writing-system changes are NOT safe from a peer and are not covered by this
path." Items 5 (Q1, writing systems) and Session 2 (CP5-a, custom fields) are
tests of that assertion, not open questions about which nobody has an opinion.

### Backup situation (item 0b), recorded honestly

No `.fwbackup` for `Sena 3` exists in either standard FieldWorks backup
location. The user supplied one out of a source tree:

```
D:\Github\_Projects\_LEX\flexicon\tests\fixtures\Sena 3 2018-09-11 1145.fwbackup
    15,363,735 bytes
```

**Caveat, accepted by the user:** that is the pristine 2018 Sena 3 sample
fixture, 15MB against the live 56MB `.fwdata` (last modified 2026-09-07 23:05).
Restoring it is a hard reset to the 2018 sample state, not a snapshot of the
project as it stands today -- it would discard all subsequent content. For a
sample project that is an acceptable floor, and it is the undo of record for
items 5-7.

The server additionally took its own automatic pre-write copy:

```
C:\Users\thoua\.flextoolsmcp\backups\Sena 3\20260908T143503Z\Sena 3.fwdata
```

with the honest note that "FieldWorks currently has this project open, so the
.fwdata on disk lags FLEx's unsaved in-memory state. This copy is a floor to
fall back to, not a snapshot of what the FLEx UI is showing."

## Post-item-3: gloss restored, plus three incidental findings

### Restore (Sena 3 left as found)

op `op-093846487-008`, `write_enabled=True`, `confirmed=True`:

```
entry: 'bubu bubu'  guid=0006f482-a078-4cef-9c5a-8bd35b53cf72
before restore: 'CP4LIVE-2026-09-08'
after restore: 'gaguez'
```

The user confirmed in the FLEx UI: "yes, confirmed gaguez". So the **restore
write also propagated to the master's live cache** -- a second, independent
observation of the same CP4-c leg-3 behaviour, in the opposite direction. The
`bubu bubu` first-sense gloss is back to its original value; Sena 3's lexical
data was left as found.

The restore was written defensively, re-resolving the entry by position and
asserting its GUID before mutating, so a renumbered/reordered collection could
not cause a write to the wrong entry:

```python
entries = project.LexEntry.GetAll()
entry = entries[0]
guid = str(project.LexEntry.GetGuid(entry))
report.Info("entry: " + repr(project.LexEntry.GetLexemeForm(entry)) + "  guid=" + guid)
if guid != "0006f482-a078-4cef-9c5a-8bd35b53cf72":
    report.Error("GUID mismatch - this is not the entry we wrote to. Aborting restore.")
else:
    ...
```

### Finding (d) -- CORRECTION to finding (a): the confirmation gate is NOT bypassable

Finding (a) above hypothesised that `is_certified_readonly: true` might mean
`confirmation_required` never fires. **That hypothesis was tested and is
false.** The restore was first submitted deliberately with `confirmed=False`
(op `op-093805998-006`) and **was refused**:

```json
{
  "status": "error",
  "error_code": "confirmation_required",
  "message": "This run would mutate the database (0 mutation(s) detected) but confirmed=False. Review `mutations_detected`, then resubmit the SAME call with confirmed=True to execute.",
  "writeability": {"is_mutating_script": true, "mutations_detected": [],
                   "would_require": {"write_enabled": true, "project_lock": true}}
}
```

The gate keys off `writeability.is_mutating_script`, not off
`write_certification.is_certified_readonly`. **There is no safety hole here**,
and finding (a) consequence 2 is withdrawn.

Finding (a) consequence 1, however, is **confirmed and is worse than predicted**
-- the refusal message is self-contradictory and actively unhelpful:

- it says the run "would mutate the database (**0 mutation(s) detected**)",
  asserting a mutation and denying it in the same sentence;
- it instructs the user to "Review `mutations_detected`", which is an **empty
  array**.

So a user hitting this gate legitimately -- the intended safety interaction --
is told to review a blank plan. Severity: not a safety defect, but a real
correctness/UX defect in the Rung-3 gate's user-facing output, reproduced on
three separate ops (`-004` validate_only, `-005` write, `-006` refusal) and on
two different mutating scripts. Root cause is the same in all cases:
`project.Senses.SetGloss` is not enumerated by whatever populates
`mutations_detected` / `mutating_calls_detected`.

Note also that `write_certification` reported `is_certified_readonly: true`
on **every** write run in this session, including the two that mutated. Any
other consumer that trusts that field to mean "this run did not write" would be
misled.

### Finding (e) -- `project.Object(guid)` returns an uncast `ICmObject`

The first restore attempt (op `op-093821186-007`) failed:

```
AttributeError: 'ICmObject' object has no attribute 'AllSenses'
  ... during handling of which:
AttributeError: 'ICmObject' object has no attribute 'SensesOS'
  File "flexicon/code/Lexicon/LexEntryOperations.py", line 2673, in GetAllSenses
```

with `polymorphic_error_detected: true`, `object_type: "ICmObject"`,
`property_name: "SensesOS"`.

The code was the pattern the server's **own** `hvo_stability` runtime primer
prescribes for crossing a call boundary:

> "project.Object(...) is the INVERSE -- it accepts an int (hvo, same-run only),
> a str GUID, or a System.Guid, and resolves to the live CmObject. Prefer the
> str-GUID form when crossing a call boundary: project.Object(guid_str)."
> ... "Call 2: entry = project.Object(guid_str)"

That primer text does not mention that the returned object is an uncast
`ICmObject` and must be cast (e.g. to `ILexEntry`) before any Operations method
that reaches for `SensesOS` / `AllSenses` will accept it. The preflight casting
gate did **not** catch it either -- `validate_only` was not run on this attempt,
but the real run's `casting` gate had passed on the earlier equivalent script,
and the failure surfaced only at runtime, where the handler correctly
identified it and emitted the `resolve_property` fallback advice.

**Recommendation for the crew:** the `hvo_stability` primer is the single most
prominently-surfaced piece of guidance in `flextools_start`'s response, and its
worked example is not runnable as written for the common `ILexEntry` case. It
should show the cast. Filed here because it was hit while executing an official
checklist, not while improvising.

## Items 5-7 -- API surface discovered (no mutations yet)

`flextools_search_by_capability` did **not** surface the writing-system write
path (its top hits for "add or modify a writing system" were
`ApplySyncableProperties`, `ParagraphOperations.Create` and OCM catalog
imports -- all irrelevant). `flextools_get_object_api` found it immediately.
Recorded as a search-quality observation: keyword search missed the single most
on-point entity for a direct, literal query.

All three OPEN questions **do** have MCP write paths:

| Item | Class / access path | Create | Undo available |
|---|---|---|---|
| 5 (Q1) writing systems | `WritingSystemOperations` / `project.WritingSystems` | `Create(language_tag, name, is_vernacular=True)` | `Delete(ws_handle_or_tag)` |
| 6 (Q2) possibility list | `SemanticDomainOperations` / `project.SemanticDomains` | `Create(name, number, parent=None, wsHandle=None)`; also `SetName` for the rename variant | `Delete(domain_or_hvo)` |
| 7 (Q3) reversal index | `ReversalIndexOperations` / `project.ReversalIndexes` | `Create(name, writing_system, guid=None)` | `Delete(index_or_hvo)` |

Item 5's checklist escape hatch ("if no MCP path exists, attempt it and record
the error") is therefore **not** needed -- `WritingSystems.Create` exists and
will be exercised directly.

Also relevant: `WritingSystemOperations` additionally exposes `SetFontName`,
`SetFontSize`, `SetRightToLeft`, `SetDefaultAnalysis`, `SetDefaultVernacular`
and `Delete`, so the "modify" half of Q1 has several distinct surfaces, not
just create.
