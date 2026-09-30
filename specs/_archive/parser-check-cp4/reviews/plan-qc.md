# Plan-Gate QC Review -- specs/parser-check-cp4/plan.md

**Verdict: APPROVE WITH NON-BLOCKING** (pass 3, 2026-09-24, worktree `feat/parser-check-cp4` at `2aedb1d`)

## Gate history

| Pass | Verdict | Cause |
|---|---|---|
| 1 | BLOCKED | `spec.md` and `checklists/requirements.md` were absent. A concurrent session had run `git stash -u` in the shared checkout mid-plan. Both files were restored from `stash@{0}^3` and the work was moved to its own worktree |
| 2 | BLOCKED | **B-1**: the filing check order refused on the access gate before confirmation and falsely claimed `run_module` does the same. **B-2**: two of sweep #3's `config_get` citations pointed at non-`config_get` lines. The pass-1 spot-check had wrongly passed them |
| 3 | APPROVE WITH NON-BLOCKING | B-1 and B-2 resolved and spot-checked against source. Upstream drift (#118, #147) edits verified |

## B-1 -- filing check order: RESOLVED

`contracts/tools.md` section 1 now runs in this order:
- row 8, the access **probe** (data only);
- row 10, **confirmation**;
- row 11, the **access-gate** refusal, on the confirmed call;
- row 13, backup.

Spot-checks:
- `execution.py:4489-4491` holds the quoted sentence ("an unconfirmed run against an
  exclusively-held project still gets confirmation_required first") byte-for-byte.
- The lock refusal at `execution.py:4629` comes strictly after the confirmation block.
- The Phase 5 text, the FR-002/FR-030 test row and the tripwire list all match.
- `spec.md` FR-002's rung list is consistent with this order.

## B-2 -- sweep #3 citations: RESOLVED

All four lines hold the `config_get` calls claimed:
- `execution.py:4537` (`REQUIRE_WRITE_CONFIRMATION_KEY`)
- `execution.py:4547` (`BACKUP_BEFORE_WRITE_KEY`)
- `backup.py:95` (`BACKUP_BEFORE_WRITE_KEY`)
- `backup.py:123` (`BACKUP_RETENTION_KEY`)

The non-gate sites are listed as reviewed.

## Upstream drift -- accurate, no new inconsistency

- **#118 (`5612fc2`)**: `project_access.py:398-411` now returns `verdict="unknown"` and
  `probed=False`. `run_module`'s refusal set (`execution.py:4629`) excludes `unknown`, so
  `run_module` proceeds on it, exactly as contracts row 11 and sweep #4 claim. Filing's
  refusal of `unknown` with `project_drive_unavailable` (an existing code) is disclosed
  as a divergence.
- **#147 (`106a2ff`)**: R-10 and Phase 6 agree that the filing worker reuses
  `RefreshFromDisk`-before-`CloseProject`. L-0's reader-side question is still correctly
  open.
- These citations match source: `docs/TOOL-CONTRACT.md:69` (32 codes), `runner.py:810`
  (`cancel_run`) and `runner.py:657` (the word-boundary cancel).

## Non-blocking

1. `research.md:202` cited `project_access.py:373` / `:289`; the actual lines are `374` /
   `290`. **Fixed after the review.**
2. `quickstart.md` has no walkthrough for the `verdict="unknown"` edge. It is covered by
   the FR-002/FR-030 test row and `test_filing_ladder_order.py`. No action needed.
3. These points are carried from passes 1 and 2:
   - the Principle VI eligibility port is justified and pinned by a live parity test;
   - M-2 and M-3 are maintainer defaults;
   - the six wrong-implementation tripwires must survive implementation review;
   - evidence-file naming follows the CP2/CP3 precedent.

## Carried forward (passes 1-2, not re-derived)

- Every FR-001..FR-043 has a named test or live scenario, and every SC-001..SC-011 is
  cited. No coverage is asserted but unscheduled.
- There are four pattern-audit sweeps.
- The live-LCM obligation is structurally satisfied:
  - Phase 8 runs on disposable copies only;
  - `FLEXLIBS_REQUIRE_LIVE=1` is set;
  - there is one evidence artifact per FR-036 case;
  - there is a `needs_human` stop when unattended.
- R-10/M-1 is correctly escalated.
