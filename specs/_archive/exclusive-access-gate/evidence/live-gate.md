# Live verification: exclusive-access gate (T036, T025, T030)

Project: **Sena 3** (the designated test project). FieldWorks 9.3.x, PID
27984, sharing on. Date 2026-10-01. Worktree `feat/exclusive-access-gate` at
`c3d5df0` plus the evidence scripts in this folder.

**How it was run.** This session's MCP server runs the main checkout, which
has no gate. Every call below went through
`evidence/live_gate_driver.py`, which imports the worktree's `src/` and
drives `handle_start` + `handle_run_module` exactly as the MCP tool does, with
the real API index loaded and `FLEXLIBS_REQUIRE_LIVE=1`.

**run_mode.** All runs are live: a real subprocess against the real Sena 3,
with FieldWorks attached. `tests/live_status.json` does not exist in this
repo, so there was nothing to cross-check. The probe line printed by every
run (`verdict=open_shared sharing=True holder=PID 27984 FieldWorks`) is the
live-state proof.

Command shape (PowerShell, from the worktree):

```
$env:FLEXLIBS_REQUIRE_LIVE='1'
C:\Github\FlexToolsMCP\.venv\Scripts\python.exe specs\exclusive-access-gate\evidence\live_gate_driver.py <mode> [args]
```

## Pre-state

`ws-list` (read-only, op-082355392 and later):

- vernacular: `seh`, `seh-fonipa-x-etic`
- analysis: `en`, `pt`
- `WritingSystemStore` holds 6 `.ldml` files: `en`, `grc`, `hbo`, `pt`,
  `seh-fonipa-x-etic`, `seh`. Their mtimes are recorded by the driver before
  and after each WS step.

## V1: refused while FLEx is open -- PASS

`live_gate_driver.py v1 en`. The script is
`if modifyAllowed: project.WritingSystems.Ensure('en')`, write-enabled,
`confirmed=True`. Op `op-082526186-001`.

- `error_code: requires_exclusive_access`, `verdict: open_shared`,
  `holder_pid: 27984`, `holder_process: FieldWorks`.
- `operations`: `[{key: ws.wrapper, call: WritingSystemOperations.Ensure,
  line: 2, failure_class: crashes_holder, source: wrapper}]`.
- Message, guidance and remedy as in contracts/requires_exclusive_access.md.
- `.ldml` mtimes unchanged (6 files).
- No backup taken: the newest Sena 3 backup was still `20260930T201558Z`.
- FieldWorks PID 27984 still `Responding: True`.

## V2: validate_only -- PASS

`live_gate_driver.py v2 en` (same script, `validate_only=True`):

- `project_lock.exclusive_access = {required: true, operations: [ws.wrapper
  Ensure line 2], blocking: true}`.
- `project_lock.blocking: false`: the ordinary write gate would not refuse.
- `lock_note` carries the exclusive-access sentence.
- `.ldml` unchanged.

## V4: ordinary write while FLEx is open -- PASS

`evidence/v4_create.py`:

- Dry run first (read-only, `op-082630097`): `pre: zzExclTest exists =
  False`.
- Write run (write-enabled, confirmed, `op-082645405`): `created zzExclTest,
  gloss = zzgloss-v4`.
- **Not refused by the gate.** `shared_mode.note` now ends "Writing-system
  and custom-field changes are refused while FieldWorks has the project open
  (requires_exclusive_access)."
- Backup taken: `20261001T132645Z` (with the peer caveat).
- FieldWorks still responding.

Side finding, pre-existing and not this feature: the write gate does not
treat `if modifyAllowed and existing is None:` as a guard
(`unprotected_writes`). A nested `if` passes.

## V5: does a write-enabled session see a peer's write? -- decided NO-SHIP

Call A = V4 (gloss `zzgloss-v4` committed by a peer). Call B reads it back from
a fresh process:

| Call B | op | Read value |
|---|---|---|
| read-only, `v_read.py` | `op-082708234` | `['zzgloss-v4']` |
| write-enabled, confirmed, as-is, `v_read.py` | `op-082717294` | `['zzgloss-v4']` |
| write-enabled, `project.SaveChanges()` first, `v5_read_synced.py` (`SaveChanges ok`) | `op-082747578` | `['zzgloss-v4']` |

All three saw the peer write. Sync-at-open made no difference, so T026 and
T027 are **not shipped**.

Corrected reading (2026-10-02): a fresh session reads the `.fwdata`, which
only the master writes, on idle. The `.fwdata` mtime, 08:26:49, came seconds
after the V4 commit, because FLEx was sitting idle. These read-backs succeeded
because the master had already flushed; that is the favourable case, not a
guarantee. The runtime primer's rule ("a fresh read-only session under a live
FLEx master shows the last master save, not your write") still holds in
general, and the notes now say that this run was the favourable case. (The unguarded
first try of the sync variant was refused as `unprotected_writes`, which is
correct, because `SaveChanges()` is a write.)

## V7: harness dry run

`live_cf_peer.py dry`: opened read-only with `HeadlessLcmUI`;
`FieldDescription.FieldDescriptors` works; `zzExclTest already defined =
False`. (The backend-name helper could not import `IDataStorer`; this is
cosmetic.)

## Peer schema guard, flexicon side -- PASS

`C:\Github\flexicon-peer-guard\evidence\peer_schema_guard_live.py`
(flexicon branch `feat/peer-schema-guard`, `076a239`). FLEx PID 27984 holds
Sena 3. With `SetPeerSchemaGuard(True)`:

- `Ensure('en', analysis)` returned `created=False`;
- `Ensure('qaa-x-zzexcl')` raised `FP_ExclusiveAccessRequiredError`;
- the WS lists were identical in-session and after a fresh open.

## V8: conditional Ensure() end to end (FR-002b) -- PASS

Final design: the active lists are read from the `.fwdata`
(`read_active_writing_systems`; 156 ms on Sena 3's 53 MB file, result
`{analysis: [pt, en], vernacular: [seh, seh-fonipa-x-etic]}`), and the guard
is probed in the server process. For V8a-c, `PYTHONPATH=C:\Github\flexicon-peer-guard`
made both the driver's probe and the run's subprocess use the guard build.
V8d had no `PYTHONPATH`, so it used the released flexicon.

| Step | Script | Result | op |
|---|---|---|---|
| V8a | `v8a_ensure_active.py`: `Ensure('en', 'English', is_vernacular=False)` | ran; `Ensure ... created = False`; `exclusive_access.decision = allowed_conditional`, satisfied `ws.ensure`; `peer_schema_guard: true` | `op-092335154` |
| V8b | `v8b_ensure_new_literal.py`: `Ensure('qaa-x-zzexcl', ...)` | refused up front, `stage: preflight`: "Ensure('qaa-x-zzexcl') on line 3 would add a vernacular writing system: 'qaa-x-zzexcl' is not active as vernacular in the project." | `op-092345041` |
| V8c | `v8c_ensure_new_variable.py`: same tag via a variable | allowed by the gate (`deferred_to_runtime`), then refused **at run time**: `requires_exclusive_access`, `stage: runtime`, "Nothing was written by that call" | `op-092351020` |
| V8d | V8a with the **released** flexicon (no `peer-schema-guard`) | refused up front: "The installed flexicon has no peer schema guard ('peer-schema-guard'), so a no-op Ensure() cannot be told apart safely from one that writes." | `op-092400071` |

The same four steps first ran against an earlier design that used an LCM
subprocess snapshot (ops `op-0856*`), with the same outcomes. That design
was replaced by the file read at the maintainer's suggestion (about 0.5 s
against about 4 s, and no second project open).

Post-state (`ws-list`): vernacular `seh`, `seh-fonipa-x-etic`; analysis
`en`, `pt`; all six `.ldml` mtimes identical to the pre-state. FieldWorks
PID 27984 responding throughout.

Side finding (ledger flexicon-5, already STILL NEW): V8c's
`report.Info("before Ensure ...")` line is missing from the result, because
run_module drops `report` messages when the script raises.

## Merged flexicon (#601) re-run, and an unintended write (2026-10-01 11:37)

After flexicon#601 merged, `C:\Github\flexicon` was pulled to `04786b0`. The
venv's flexicon now has `peer-schema-guard`.

- flexicon offline suite on `main`: the 23 guard / capability / stub tests
  pass. 47 failures, in `test_575_msa_longname_type.py`,
  `test_577_inflectable_features.py`, `test_issue581_offline.py` and
  `test_docstring_example_ratchet.py`, are **pre-existing**: the identical 47
  fail at `ad4a1c2` (main just before the #601 merge). They are unrelated to
  the guard.

**Incident.** The maintainer had closed FieldWorks before this re-run, and
the session did not re-check the probe first. With `verdict: free` the gate
correctly does not apply, so the V8 scripts ran as ordinary writes:

- V8a (`op-113709844`): `Ensure('en', analysis)`, `created=False`. This is
  also the corrected **V3** call (FLEx closed, an already-active tag), and it
  passed the gate and wrote nothing.
- V8b (`op-113719668`): **created** `qaa-x-zzexcl` as a vernacular WS.
- V8c (`op-113729827`): `created=False` (already present by then).

Cleanup (`cleanup_zzexcl_ws.py`, read-only dry run, then write
`op-113850747`): `WritingSystems.Delete('qaa-x-zzexcl')`. A fresh read
confirms vernacular `seh, seh-fonipa-x-etic` and analysis `en, pt`.

**Residue (ledger flexicon-6):** `WritingSystemStore/qaa-x-zzexcl.ldml` and
an `<Add Producer="???">` entry for it in `idchangelog.xml` remain.
Removing them needs a hand edit, pending the maintainer. The pre-write backup
taken just before V8b is `~/.flextoolsmcp/backups/Sena 3/20261001T163719Z`.

Lesson for the driver: probe and print the verdict, and refuse to run a V8
step unless it is `open_shared`.

## V3: FLEx closed -- PASS (closed 2026-10-02)

- Run: `Ensure('en', analysis)` with FieldWorks closed (`verdict: free`,
  `op-113709844`). The gate did not apply, and the call wrote nothing
  (`created=False`).
- The maintainer then reopened FLEx on Sena 3: it opened cleanly, and
  `qaa-x-zzexcl` (created and then deleted during the incident above) is not
  listed among the writing systems.

## V6: FLEx side -- PASS, with one caveat (2026-10-02, maintainer)

- After reopening FLEx, the `zzExclTest` entry shows its gloss `zzgloss-v4`,
  the MCP peer write from V4. It persisted across a FLEx close and reopen.
- Edit > Undo is empty on open. This confirms the "FLEx starts with an empty
  undo history" fact in SHARED-MODE.md.
- **Caveat.** Because FLEx had been reopened, this round did not re-test,
  within one running FLEx session, either that the change appears after
  navigating away and back (and not on F5 alone, #96), or that Undo omits
  the peer write. The docs cite #96 for the first, and LCM source (research
  R4) for the second.
- The maintainer confirmed that navigating away is only needed when FLEx was
  open during the write; a fresh start always shows the current data.
  SHARED-MODE.md now says so.

## V7: custom-field definition from a peer (Class B) -- observed: LOST (2026-10-02)

Harness `evidence/live_cf_peer.py`. Sena 3 was held by FieldWorks PID 6468
(`open_shared`, sharing on). A second FLEx had Claude-Swahili open; it was not
touched, and the harness asserts Sena 3.

1. `dry` (read-only): `zzExclTest` defined = False.
2. `add` (writable peer): `FieldDescription(cache)` for LexEntry, MultiUnicode,
   analysis WS, via `UpdateCustomField()` inside
   `NonUndoableUnitOfWorkHelper.Do`, then commit. No data was written to the
   field. In-process: defined = True. FieldWorks kept responding. (A first
   attempt failed before opening the project, because .NET was imported
   before `FLExInitialize`; it wrote nothing, and the harness was fixed.)
3. `check` from a **fresh peer** while FLEx was still open: defined = **False**.
   The `.fwdata` was unchanged (mtime 2026-10-01 11:38:53); its only
   `zzExclTest` text is the V4 entry's lexeme form.
4. Maintainer, in the **master** FLEx: Tools > Configure > Custom Fields
   showed **no zzExclTest field**.
5. The maintainer closed Sena 3 (verdict then `free`). `check`: defined =
   **False**. The `.fwdata` mtime was still unchanged.

**Outcome:** the definition never reached the master, any other peer, or
disk, so it is silently lost. This is stronger than research R9 expected (R9
expected it to be visible and then gone after a restart). It confirms the
`silently_lost` failure class live: the gate's custom-field rows protect real
users. Nothing to clean up for the field itself.

## Cleanup (2026-10-02, Sena 3 closed)

- `qaa-x-zzexcl` residue (maintainer-approved):
  - deleted `WritingSystemStore/qaa-x-zzexcl.ldml`;
  - removed its single `<Add Producer="???">` block from `idchangelog.xml`,
    leaving the 15 original entries (2016-2017). XML still parses; encoding
    (UTF-8, no BOM) and CRLF preserved.
  - Copies of both files before the edit are in the session scratchpad, not
    the project folder.
- `zzExclTest` entry (from V4): `cleanup_zzexcltest_entry.py` with
  `--expect free`; dry run, then write (`op-092650017`). A fresh read
  (`v_read.py`) shows "zzExclTest: absent".

## Final state -- confirmed by the maintainer (2026-10-02)

After reopening Sena 3 in FLEx:

- Tools > Configure > Custom Fields lists no `zzExclTest`;
- the `zzExclTest` entry is gone;
- the writing systems are `seh`, `seh-fonipa-x-etic` / `en`, `pt`, with no
  `qaa-x-zzexcl`.

Every live step (V1-V8) is complete, and every test object has been cleaned
up.
