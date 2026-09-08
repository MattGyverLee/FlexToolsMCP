# Live session 2 -- 2026-09-08 (second sitting), issue #93

**Why a separate file:** `live-cp4.md` was being edited concurrently by the
cycle-8 doc task when this evidence was captured. This file is append-only
evidence in the same spirit; fold it into `live-cp4.md` once that edit lands.

**Machine state at the start of this sitting**, verified from the probe rather
than reported:

- `Sena 3` projectSharing = **ON** (`sharing_enabled: true`).
- FieldWorks **OPEN** and holding the project: PID 40664, started 10:38:17,
  `Responding: True` (`Get-Process`), sole FieldWorks process on the machine.
- Probe verdict `open_shared`, lock age 535 s at first sample.
- MCP server PID 15852, version 2.9.1. **This server predates the cycle-8
  `_pid_is_alive` fix (commit `a8cf35b`)**, so every probe result below is
  PRE-FIX behaviour. That is deliberate: it is the baseline the post-fix
  re-test is compared against.
- Resolved library versions per `flextools_health`: flexicon 4.5.2 (index
  4.5.2, exact), liblcm 11.0.0, flexlibs_stable 1.2.8. Note the cycle-7
  handoff warned that `flexicon` on this machine may resolve to the sibling
  source repo rather than a wheel; health reports 4.5.2 exact.

---

## Item A -- PID ground truth while FLEx is genuinely alive (finding (k), true-positive leg)

The probe's reported holder was cross-checked against the OS.

```
=== PID 40664 (probe-reported holder) ===
Id          : 40664
ProcessName : FieldWorks
StartTime   : 9/8/2026 10:38:17 AM
Responding  : True

=== all FieldWorks / Flex processes ===
   Id ProcessName StartTime
   -- ----------- ---------
40664 FieldWorks  9/8/2026 10:38:17 AM
```

**Result: PASS.** While FieldWorks is genuinely running, the probe's
`holder_pid` matches the one real FieldWorks process exactly. Finding (k) is
specifically a *post-close* false positive, not a general inaccuracy -- this
leg establishes that, and rules out the simpler explanation that the probe
merely reports garbage.

The post-close leg of this test was not reached in this sitting; see
"Not completed" below.

---

## Item B -- database BEFORE-capture (read-only)

Writing systems (4). The `fr` writing system removed in the previous sitting
is confirmed absent:

```
  ws: {'name': 'English', 'tag': 'en'}
  ws: {'name': 'Portuguese', 'tag': 'pt'}
  ws: {'name': 'Sena', 'tag': 'seh'}
  ws: {'name': 'Sena (Phonetic)', 'tag': 'seh-fonipa-x-etic'}
```

Reversal indexes (2). The vernacular `seh` index created and deleted in the
previous sitting is confirmed absent:

```
count = 2
  [0]  ws='pt'  name='Portuguese'  guid=<ERR AttributeError>  entries=<ERR AttributeError: 'ReversalIndexOperations' object has no attribute 'GetAllEntries'>
  [1]  ws='en'  name='English'  guid=<ERR AttributeError>  entries=<ERR AttributeError: 'ReversalIndexOperations' object has no attribute 'GetAllEntries'>
```

Custom fields, matching the documented baseline (Plural, Singular on
LexEntry; Parsing Note on LexSense), and the probe name confirmed unused:

```
LexEntry: 2 custom field(s)
    name=<ERR TypeError>  type=<ERR TypeError>  owner=<ERR TypeError>
    name=<ERR TypeError>  type=<ERR TypeError>  owner=<ERR TypeError>
LexSense: 1 custom field(s)
    name=<ERR TypeError>  type=<ERR TypeError>  owner=<ERR TypeError>
LexExampleSentence: 0 custom field(s)
MoForm: 0 custom field(s)
FindField('LexEntry','ClassBProbe93') -> None
```

---

## Item C -- CP4 confirmed live under a real FieldWorks master

`validate_only=True` against the live project, sharing ON, FLEx holding it:

```
project_lock: {
  "locked": true,
  "lock_file": "C:\\ProgramData\\SIL\\FieldWorks\\Projects\\Sena 3\\Sena 3.fwdata.lock",
  "sharing_enabled": true,
  "verdict": "open_shared",
  "blocking": false
}
```

All 11 preflight gates passed. **`blocking: false` is CP4's core promise**: a
peer write is permitted while FieldWorks holds the project, because sharing is
on. This is the `open_shared` path exercised live under a genuine FLEx master.

---

## Item D -- CP5-a is UNRUNNABLE AS SPECIFIED (new, blocks a SPEC test)

SPEC Session 2 test 1 (CP5-a) requires that
`CustomFieldOperations.CreateField` with FLEx open be refused with
`requires_exclusive_access`, and **then succeed with FLEx closed**.

The second leg cannot succeed. `CreateField` refuses unconditionally in the
runner's default transaction mode, independent of FLEx state and independent
of shared mode. Verbatim, from a live write-enabled run:

```
FP_TransactionError: CreateField cannot run inside an open UnitOfWork. Custom
field creation is a schema mutation that LCM forbids inside an active task
(raises InvalidOperationException at UndoStack.CheckNotProcessingDataChanges).
In Phase 1 transaction mode this UoW is opened at OpenProject() and stays open
until CloseProject(), so schema mutations are not possible via the wrapper.
Fix: create custom fields through the FLEx UI (Tools > Configure > Custom
Fields) before running bootstrap scripts that populate values. Do NOT bypass
this guard with raw IFwMetaDataCacheManaged.AddCustomField: the field is
created in memory only, SetValue writes data referencing a ghost field, and the
project corrupts on next FLEx UI open (issue #21). See docs/CUSTOM_FIELDS.md.
```

This was already documented in the `CreateField` docstring's "Transaction
Safety" section; it had simply not been reconciled against the CP5-a test
design. **CP5-a needs redesigning around a different operation**, and the
choice of `CreateField` as the exclusive-access exemplar should be revisited
before CP5 is implemented against it.

Consequence for Class B: the intended empirical confirmation of the Class B
mechanism **did not happen**. Nothing reached the database, so the Class B
premise in SPEC Section 3 -- derived entirely from liblcm source and still
never observed -- remains unobserved.

---

## Item E -- THE RUNG-3 CONFIRMATION GATE WAS BYPASSED (safety, new)

This contradicts the scope bound carried from finding (d), which held that the
confirmation gate "is not bypassable". That is true for `SetGloss`. It does not
generalise.

The run in Item D was submitted with `write_enabled=True` and
**`confirmed=False`** -- the combination finding (d) says is refused. It was
not refused. No `confirmation_required` error was returned. The runner opened
the project in write mode and **executed the mutating code**. The only thing
that prevented a schema write landing on the live database was flexicon's own
internal transaction guard.

Gate output on the same script:

```
validate_only:
  writeability: {"is_mutating_script": false, "mutations_detected": [],
                 "would_require": {"write_enabled": false, "project_lock": false}}

executed run:
  write_certification: {"is_certified_readonly": true, "confidence": "high",
                        "mutating_calls_detected": []}
```

`is_mutating_script` is **false**, not merely under-enumerated, for a method
the API index itself marks `"is_mutating": true`.

**Why it escapes where `SetGloss` does not.** `SetGloss` still trips
`cud_info["is_cud"]` via the CUD regex, which flips `is_mutating_script` true,
which is why the gate fired for it in the previous sitting. `CreateField`
misses every layer:

- `_PATTERN_OPERATIONS_CALL` (`validators.py:74`) requires a literal
  `Operations` token in the receiver; `project.CustomFields` does not match.
- The raw-LCM mutable patterns key on
  `Set|Update|Modify|Change|Edit|Replace` (`validators.py:107`); `Create` is
  not in that alternation.
- So `cud_info["is_cud"]` is false too, and nothing flips the boolean.

The affected class is **creation and schema calls reached through a
`project.<Accessor>` namespace**, for which the confirmation gate effectively
does not exist. This is a safety defect, not a UX defect, and it is a
different severity from the recorded (a)/(d).

No database change resulted, so no restore was required.

---

## Incidental library findings from this sitting

1. `ReversalIndexOperations` has **no `GetAllEntries`**; the method is
   `GetEntries(index_or_hvo)`. Separately, it exposes **no method to create a
   reversal entry** at all (11 methods: Create, Delete, ExportToLIFT, Find,
   FindByWritingSystem, GetAll, GetEntries, GetName, GetWritingSystem,
   SetName, `__init__`). Consequence: Session 2 test 3 ("add a reversal entry,
   then check visibility") **cannot be executed through flexicon** -- the entry
   must be added by hand in the FLEx UI or through raw LCM.
2. `ReversalIndexOperations` has **no `GetGuid`**, so a reversal index cannot
   be given a durable cross-call identifier by the documented GUID round-trip.
   Every other Operations class surveyed in this project exposes one.
3. `CustomFieldOperations.GetFieldName` / `GetFieldType` / `GetOwnerClass` all
   raise **`TypeError`** when passed the elements returned by
   `GetAllFields(owner_class)`. Either `GetAllFields` returns a different
   representation than the accessors accept, or the accessors are mis-typed.
   The count is correct (2 on LexEntry, 1 on LexSense), so only the per-field
   accessors are affected. This makes the custom-field surface unusable for
   enumeration, and it is why the baseline above cannot name the fields it
   found.

---

## Item F -- finding (k) post-close leg: ATTEMPTED, and it does not arise on a clean close

FieldWorks was closed normally and the probe sampled either side of it, on the
pre-fix server (PID 15852).

Sample 1, health call followed a few seconds later by the OS check:

```
probe   : verdict "open_shared", holder {pid 40664, process_name "FieldWorks"},
          lock_age_seconds 1032.26
warning : "...held by FieldWorks (PID 40664), process still running."

[10:55:43] PID 40664 GONE from Get-Process
[10:55:43] FieldWorks-like processes: 0
--- tasklist cross-check ---
INFO: No tasks are running which match the specified criteria.
```

Sample 2, immediately after:

```
verdict          : "free"
holder           : null
lock_age_seconds : null
```

And on disk:

```
NO .fwdata.lock -- FieldWorks removed it on clean close
```

**This is NOT a reproduction of finding (k), and must not be recorded as one.**
Two reasons, both disqualifying:

1. **Ordering.** The health call ran several seconds BEFORE the `Get-Process`
   check. FieldWorks may have been genuinely alive at the instant the probe
   sampled and exited in the gap. The observation is consistent with a correct
   probe and therefore proves nothing.
2. **The scenario does not arise on a graceful close.** FieldWorks deletes its
   own `.fwdata.lock` when it shuts down cleanly, so there is no lock file left
   to misclassify -- hence `verdict: free`, not a false `open_shared`. Finding
   (k) requires a holder that died **without** removing its lock file, i.e. a
   crash or a hard kill, with a handle still open against the terminated
   process object. The original (k) observation followed a FieldWorks *crash*,
   with the Windows crash reporter holding the handle.

Consequence: the post-close window cannot be exercised by asking a user to
close FieldWorks normally. A faithful live re-test needs a **crashed or
force-killed** holder. That was not attempted here: force-killing the user's
FieldWorks was outside the approved scope for this sitting.

What this sitting DOES establish for (k) is the true-positive leg (Item A) and
the clean-close leg (verdict correctly collapses to `free`). The unit tests
committed with the fix in `a8cf35b` cover the freshly-dead branch directly by
patching the kernel32 seam, which is the appropriate level for it.

---

## Item G -- the health `warnings` array is stale and self-contradictory (new)

Across all three `flextools_health(verbose=True)` calls in this sitting, the
`warnings` entry for `Sena 3` was **byte-identical**:

```
"Lock detected: ...\\Sena 3\\Sena 3.fwdata.lock (53 s old), held by FieldWorks
 (PID 40664), process still running. Project sharing is enabled, so writes
 through the shared commit log are expected to succeed without closing
 FieldWorks."
```

That text was wrong in two different ways at two different times:

- On call 1 it said "53 s old" while `verbose.project_access.lock_age_seconds`
  in the SAME response read `535.03`; on call 2, `1032.26`.
- On call 3 it still asserted a live FieldWorks holder while
  `verbose.project_access` in the SAME response read
  `verdict: "free", holder: null, lock_age_seconds: null`, and the lock file
  no longer existed on disk.

So a single health response can contain a warning that directly contradicts
its own probe block. The warnings appear to be computed once and cached for
the life of the server process, while `verbose.project_access` is probed
fresh per call.

This matters beyond cosmetics: the warnings array is the surface a user or
assistant reads first, and it is the one asserting "process still running" --
the same sentence finding (k) is about. An observer could easily attribute a
stale *warning* to the `_pid_is_alive` defect and conclude the fix had failed
when it had not. Worth filing separately from (k), and worth checking whether
the CP2/CP3 warning paths share the cache.

---

## Not completed in this sitting

- **Class B empirical confirmation.** Blocked by Item D; still unobserved.
- **A faithful finding (k) post-close reproduction.** See Item F -- needs a
  crashed or force-killed holder, not a clean close.
- **Post-fix re-test on a restarted server.** The server ran the pre-fix code
  (PID 15852, predating `a8cf35b`) throughout, which is why every result above
  is labelled pre-fix.
- **UI before-readings** (reversal layout list, main Reversal Index view).
  Not captured; these need a human reading the FLEx screen. Per the process
  lesson carried forward from the previous sitting, no UI surface may be cited
  as evidence without a before-reading, so no UI claim is made anywhere in
  this file.
