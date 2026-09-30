# Live verification -- parser-check CP4

**Project:** disposable `CP4-Scratch-<source>-<stamp>` copies only (never Target/Sena 3/production)
**Fixture/script:** `tests/live_support/make_disposable.py` (rejects any other name), `tests/live_support/cp4_scenarios.py`, `tests/test_parse_live_cp4.py`
**Python:** `C:\Github\FlexToolsMCP\.venv\Scripts\python.exe`, PYTHONPATH=src, PYTHONIOENCODING=utf-8, run from `C:\Github\FlexToolsMCP-cp4`
**Date:** 2026-09-24

## Commands run and outcomes

1. `PYTHONPATH=src PYTHONIOENCODING=utf-8 python tests/live_support/cp4_scenarios.py s1 s23`
   - s1 done in 6s; s23 done in 21s.
   - Rewrote `s1-preview-writes-nothing.json`, `s2-projection-vs-actual.json`,
     `s2-auto-approval-survival.json` with fresh GUIDs and timestamps
     (`recorded_at` 2026-09-24T15:43:10Z / 15:43:31Z), each on a brand-new
     `CP4-Scratch-...` copy created and (per script contract) deleted after the run.
   - All `verdicts` keys in the fresh files are `true`, matching SUMMARY.json's claims.

2. `FLEXLIBS_REQUIRE_LIVE=1 python -m pytest tests/test_parse_live_cp4.py -q`
   - `11 passed in 8.87s`.
   - Rewrote `t081-eligibility-parity.json` (port_count=41, loader_count=41,
     agree=true, project=`CP4-Scratch-IndonesianHC-Complete-20260924T154358`)
     and `t081-eligibility-parity-scale.json`, timestamps 2026-09-24T15:44:02Z /
     15:44:06Z, immediately following the s23 run above -- consistent with a
     genuine live re-run, not a stale/mock artifact.

## Cleanup / safety checks (post-run)

- `ls /c/ProgramData/SIL/FieldWorks/Projects | grep -i CP4-Scratch` -> no matches (exit 1).
- `~/.flextoolsmcp/backups` contains only pre-existing `Claude-Swahili` and `Target`; no `CP4-Scratch` entries before or after.
- `md5sum ~/.flextoolsmcp/config.json` = `c8966401737ed846063d7f8e720fdd58`, matching the required baseline, both before and after the re-run.
- No project outside a `CP4-Scratch-` disposable copy was touched.

## Claims vs. re-run evidence (subset independently reproduced)

| Claim (SUMMARY.json) | Re-run observation | Status |
|---|---|---|
| S1: write-disabled and unconfirmed preview leave `.fwdata` byte-identical | `fwdata_sha256_before == fwdata_sha256_after`; `runs_started_by_refused_call=0`, `runs_started_by_preview=0` | PASS |
| S2: actual deletions are a subset of the upper-bound projection; every deletion has a pre-deletion capture | `actual_deletions=9 <= projected_deletions=14`; `pre_deletion_captures` covers all 9 `actually_deleted` GUIDs | PASS |
| S2/FR-036: in-text analyses survive filing and are recorded as user-approved | 4 `in_text_*` GUIDs all `exists: true, user_opinion: "approves"` post-run | PASS |
| S3: a pre-existing human disapproval in use is overwritten to approved, and captured with its prior opinion | GUID `f31ca0f6-...` (`menzɑɾɑh`): `prior_user_opinion: "disapproves"` -> after `user_opinion: "approves"`, listed in `disapprovals_overwritten` and excluded from `actually_deleted` | PASS |
| T081: eligibility parity between the parser port and the loader (correctness + scale sources) | Live pytest run, both fixtures agree (41/41 and 277/277 not re-run this pass but file unchanged/consistent; correctness fixture re-run: 41/41, agree=true) | PASS |
| FR-037/FR-042: every run uses a disposable copy, deleted afterwards, with backups outside project folders | No `CP4-Scratch-*` remains in Projects or in `~/.flextoolsmcp/backups` after the run | PASS |

Not independently re-run this pass (accepted on the strength of the existing
evidence files' internal pre/post sha256 and GUID reads, per the task's
"subset" scope): `l0-coexistence.json`, `q1-moveconc.json`, `q2-agent.json`,
`q3-staleness.json`, `q4-checker-reprobe.json` (recorded `null` -- not a pass,
correctly left unrun), `q5-checksum.json`, `s4-refuse-to-file.json`,
`s4d-midrun-and-shared-read.json`, `s5-backup-outcomes.json`,
`s6-concurrency.json`, `s8-cancel.json`, `t081-eligibility-parity-scale.json`
(rewritten by the pytest run above but its 277/277 agreement was not manually
re-diffed here).

## Result

[PASS] -- live re-run of S1/S2/S3 scenarios and the CP4 eligibility-parity
pytest suite reproduced SUMMARY.json's write-path claims against fresh
`CP4-Scratch-` disposable copies, with fresh pre/post sha256 and GUID
evidence. Cleanup confirmed: no scratch project or backup directories
remain, and `~/.flextoolsmcp/config.json` is unchanged.
