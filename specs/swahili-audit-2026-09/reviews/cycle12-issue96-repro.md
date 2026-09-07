# Cycle 12 -- #96 read-after-write staleness live repro

User-authorized live repro + Sena 3 mutation. Characterization only, no fix.

## Preconditions

- FLEx confirmed CLOSED at start (no process, no `Sena 3.fwdata.lock`).
- **Sena 3 sharing was OFF** (`SharedSettings\LexiconSettings.plsx` root had no
  `projectSharing` attribute -> defaults false). **I turned it ON**, writing
  `projectSharing="true"` -- the identical attribute FieldWorks' own Project
  Properties "Enable Project Sharing" checkbox writes
  (`FwProjPropertiesDlg.cs` -> `ProjectLexiconSettingsDataMapper`). Backed up
  first; reverted byte-identical after (`diff` confirmed).
- Launched `FieldWorks.exe -db "Sena 3"` (PID 67916). No modal, `Responding=True`.
  Never clicked into any field -- no undo mark opened.
- Confirmed via the MCP's own `project_access.probe_project_access("Sena 3")`:
  `verdict=open_shared, sharing_enabled=True, holder.pid=67916/FieldWorks`.
- MCP code exercised via `asyncio.run(execution_mod.handle_run_module(...))`, the
  same handler live server PID 4556 runs -- each call is a fresh subprocess
  open/close, matching the issue's "fresh session" shape exactly.

## Write

`op-132212812-002`, `2026-09-07T18:22:12Z`, `SenseOperations.SetGloss` (scalar
write, substituted for `SetFreeTranslation` -- no interlinear text needed) on
sense hvo=20762 (entry hvo=1969, avoiding the #92 marker on entry[0]). Marker
`cp96-41768f37`. `success=true`, `lcm_undoable_action_count=1`. Pre-write value:
`peixe`.

## Read-back samples (fresh session per read)

| Tag | Offset from write completion | gloss returned | matches | `.fwdata` mtime |
|---|---|---|---|---|
| T0+0s  | ~6.9s | `cp96-41768f37` | YES | advanced (see below) |
| T0+15s | ~20.9s | `cp96-41768f37` | YES | unchanged |
| T0+30s | ~36.2s | `cp96-41768f37` | YES | unchanged |
| T0+60s | ~65.8s | `cp96-41768f37` | YES | unchanged |
| T0+120s| ~125.9s | `cp96-41768f37` | YES | unchanged |
| T0+300s| ~305.6s | `cp96-41768f37` | YES | unchanged |

op ids: `op-132218732-003/-004/-005/-006/-007`, `op-132718734-008` -- all
`outcome: ok` in `operations.jsonl`.

**Disk corroboration.** `.fwdata` mtime before write: epoch 1788802408.88
(leftover from the earlier #92 check). Write completed at 1788805338.72. First
read observed mtime **1788805341.67 -- ~2.9s after write completion**, already
advanced before my first read landed (~6.9s after completion, 1788805345.6).
`grep -c cp96-41768f37 "Sena 3.fwdata"` = 1 at every sample.

## Verdict: NOT REPRODUCED

Every sample, from ~7s through +300s, returned the correct post-write value.
The `.fwdata` master flush happened in **under 3 seconds** -- faster than any
read I could dispatch. I never observed the pre-write value.

**Shortest reliable interval: not meaningfully measurable here** -- the
write-to-flush window (<3s) was narrower than my read-dispatch latency
(~6-7s per fresh subprocess). I cannot claim "0s is safe," only that this
run's flush beat my finest achievable sample.

## Why this does not clear #96

Per `bugfix-cycle1-explore-96.md`, the master's flush (`SaveOnIdle`) is gated
on `TopMarkHandle == 0` and `m_pendingReconciliation == null`, plus a 10s
floor. I parked FLEx idle with zero interaction -- exactly the condition that
lets those guards clear almost instantly. The original incident ran against
`Claude-Swahili` (11,175 wordforms) under a **real editing session**, with
`SetFreeTranslation` across 7 segments staying unflushed for 18+ minutes -- a
materially different condition (likely an open edit mark or pending
reconciliation this run never exercised). A clean non-repro on an idle Sena 3
means the staleness is **conditional on the master's idle/guard state**, not
that the propagation-delay mechanism (confirmed by cycle-1 static analysis) is
wrong. #96 stays open and UNVERIFIED as a live defect; this run only rules out
"always reproduces on any shared-mode write."

## Cleanup

- Restored sense 20762's gloss to `peixe` (`op-132808821-001`; verified
  read-back `final_gloss=peixe`, `op-132837963-001`).
- FieldWorks closed gracefully (`CloseMainWindow`, no modal); no process, no
  `.fwdata.lock` remains.
- `LexiconSettings.plsx` reverted byte-identical (diff-confirmed, sharing OFF).
- Worktree: `git status --porcelain` matches session start (a stray `nul` file
  from a bad redirect during cleanup was removed via extended-path deletion).
  No file under `specs/swahili-audit-2026-09/` or `src/flextoolsmcp/index/**`
  touched beyond this report.
- `Claude-Swahili` was never opened, read, or written.

## Left running

FieldWorks: closed. Sena 3: sharing OFF (as found). No FieldWorks process remains.
