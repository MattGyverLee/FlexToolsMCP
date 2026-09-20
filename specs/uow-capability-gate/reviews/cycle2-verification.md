# Live verification -- issue #144: DateModified stamping under undoable=False vs True

**Project:** Sena 3 scratch copies (`Sena 3-ZZTEST-144`, `Sena 3-ZZTEST-144B`), deleted after run
**Original Sena 3:** never opened write-enabled (read-only only, for baseline confirmation)
**Command:** `uv run python scratchpad/probe144.py A` and `... B` (standalone script, driving flexicon directly; not a pytest run, no repo files touched)
**Date:** 2026-09-18

## Claim under test
Does `entry.DateModified` get stamped by an MCP-style write (`LexSenseOperations.SetDefinition`), and does it differ between `undoable=False` (today's hardcoded mode) and `undoable=True` (the 4.4.0+ default the fix would select)? Also: is the reported LexReference-delete asymmetry real, and does rollback work under `undoable=True`?

## Results table

| Reading | Mode A `undoable=False` | Mode B `undoable=True` |
|---|---|---|
| DateModified before mutation (in-session) | 2026-09-18 16:03:29 Local | 2026-09-18 16:03:29 Local |
| DateModified after `SetDefinition` (in-session) | 2026-09-18 16:03:29 Local (**unchanged**, delta=0.0s) | 2026-09-18 16:37:12 Local (**moved**, delta≈2023s, matches wall-clock) |
| DateModified after CloseProject + reopen read-only (3rd reading) | 16:03:29 Local -- **still unchanged** | 16:37:12 Local -- **stamp persisted** |
| On-disk `.fwdata` DateModified element for target entry | `2026-09-18 21:03:29.287` (UTC; matches pre-mutation, confirming no stamp) | `2026-09-18 21:37:12.159` (UTC; matches post-mutation) |
| LexReference.Delete asymmetry (2 affected entries) | **Moved** in both modes: before=2006 dates, after=delete-moment (in-session, on reopen, and on disk) | **Moved** identically |
| Rollback of mid-op exception | Warned explicitly: "no mark available, rollback not performed... NOT reversed" -- marker string **persisted to disk** (verified, present in-session and after reopen) | Logged "UnitOfWork rolled back"; marker **absent** from disk (`grep -c` = 0) and value reverted in-session |
| DateTimeKind observed | `Local` on every read, both modes, both sessions | `Local` on every read, both modes, both sessions |

`DateTimeKind` was `Local` consistently (never `Utc`/`Unspecified`), so the in-session vs. reopened Local readings above are directly comparable; no spurious offset was observed between in-session and reopened values for the same underlying edit. The on-disk value is UTC text (`21:03:29` vs. Local `16:03:29`, a 5-hour offset consistent with the host's local timezone), which is expected and not evidence of a bug.

## Findings

1. **Not stamped under `undoable=False`** (today's hardcoded behavior). Confirmed identical before/after/reopened/on-disk timestamps for a `SetDefinition` write. The gap the reporter describes is real and reproduces cleanly.
2. **Stamped under `undoable=True`** (the 4.4.0+ default). The delta matches wall-clock elapsed time exactly, and the stamp survives `CloseProject()`/reopen and is visible on disk. Selecting `undoable=True` in the fix would restore `DateModified` stamping for this write path.
3. **The asymmetry is real and confirmed on disk, in both modes.** `LexReferenceOperations.Delete` moves `DateModified` on affected entries regardless of `undoable` setting -- consistent with the claim that liblcm's domain layer stamps this inline in the delete side-effect, independent of the UOW pass. This means today's codebase already has *inconsistent* dates (some ops stamp, some don't) even before any fix; the fix converges everything toward "stamped," which is the safer direction.
4. **Rollback works under `undoable=True` and does not under `undoable=False`.** Verified by injecting a mid-transaction exception: under B the partial write was absent from disk; under A it persisted, exactly matching the tool's own runtime warning text.

No ambiguous readings; all four items resolved cleanly.

## Cleanup
Both scratch project directories were deleted after the run; confirmed absent via directory listing. Original `Sena 3` project untouched throughout (read-only baseline query only; grep quoted directly above was against the scratch copies, now deleted).

## Result
**[PASS]** -- Selecting `undoable=True` (the flexicon 4.4.0+ default) restores `DateModified` stamping for standard writes and also grants working transaction rollback, which the hardcoded `undoable=False` path in today's codebase lacks entirely.
