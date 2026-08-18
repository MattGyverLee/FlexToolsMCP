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
