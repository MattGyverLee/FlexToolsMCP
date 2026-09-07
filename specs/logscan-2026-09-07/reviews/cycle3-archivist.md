# cycle3-archivist.md -- Follow-up ledger write: user-authorized reopens, MCP#111, cleanup

**Archivist:** /lex-archivist, cycle 3. **Scope:** reconcile `docs/logscan-state.json`
and `STATUS.md` with what actually happened after the user authorized lex-lead's
cycle-2 recommendations (four reopens, two deliberate non-reopens, one new filing,
and the stray-`operations.jsonl` cleanup). No issue state was changed by this
agent -- all four reopens, both non-reopen decisions, the MCP#111 filing, the
file removal, and the `.gitignore` edit had already been executed before this
cycle began; this pass only brings the durable records into line with GitHub's
actual state (verified live via `gh issue view` for every touched issue before
editing).

Baseline confirmed before editing: `docs/logscan-state.json` and
`specs/logscan-2026-09-07/.crew-handoff.json` on disk exactly matched commit
`69e0260` (the cycle-2 write) -- `git diff --stat` against each was empty prior
to this cycle's edits, so no drift had occurred between cycle 2 and now.

## Live GitHub verification performed before writing

| Issue | State (confirmed via `gh issue view`) | Reopen comment / decision comment URL |
|---|---|---|
| MCP#84 | OPEN (reopened) | `.../issues/84#issuecomment-5572007779` |
| MCP#39 | OPEN (reopened) | `.../issues/39#issuecomment-5572009878` |
| MCP#80 | OPEN (reopened) | `.../issues/80#issuecomment-5572012012` |
| MCP#69 | OPEN (reopened) | `.../issues/69#issuecomment-5572013895` |
| MCP#75 | CLOSED (not reopened) | `.../issues/75#issuecomment-5572032974` |
| flexicon#34 | CLOSED (not reopened) | `.../issues/34#issuecomment-5572080207` |
| MCP#111 | OPEN (new) | `.../issues/111` |

The stray-`operations.jsonl` evidence file at
`specs/logscan-2026-09-07/evidence/stray-root-operations-2026-09-07.jsonl` was
read and its 5 rows confirmed: single shared `code_sha256`
(`6121ed003c437fd8b9e13917ba5c66df0c508eb168529c271236c5853f5b1102`), project
`TestProj`, `code_bytes` 91, `code_lines` 4, empty `session_id`/`user_intent`/
`user_request`, `duration_s` 0.0, timestamps `06:42:27Z` and `06:42:40Z` (13s
apart across two invocations) -- matches the MCP#109 comment's inlined copy
verbatim. `.gitignore` was confirmed already carrying `operations.jsonl*` /
`operations.log*` (lines 54-55, with a comment citing #109).

## Ledger keys modified (before -> after)

### Task A: six regression entries

**`15e120d04d11` (MCP#84):**
- `state`: `regression-commented` -> `regression-reopened`
- added `reopened_date: "2026-09-07"`
- added `reopen_comment_url`
- `close_to_recurrence_minutes: 58` PRESERVED unchanged
- `notes`: appended a REOPENED block recording rank 1 of 5 and the rationale
  (documentation-only fix cannot alter runtime behavior; recurrence 58 minutes
  after close was structurally guaranteed, not merely likely); replaced the
  "pending user confirmation" language with the actioned outcome.

**`39a2f8c1d004` (MCP#39):**
- `state`: `regression-commented` -> `regression-reopened`
- added `reopened_date: "2026-09-07"`, `reopen_comment_url`
- `notes`: appended REOPENED block, rank 2 of 5 -- 10 recurrences matching the
  window's entire PolymorphicAttributeError tally; at least two were NOT user
  casting mistakes (`LcmCache`.GetObject = library-internal bug, now
  flexicon#261; `LcmCache`.Cache = discoverability trap, now MCP#108 facet a),
  so the "resubmit" hint was actively misleading for those two; scope boundary
  against MCP#108 preserved (gating vs. hint content/coverage).

**`53d4e6f0b229` (MCP#80, retargeted fingerprint):**
- `state`: `regression-commented` -> `regression-reopened`
- added `reopened_date: "2026-09-07"`, `reopen_comment_url`
- `notes`: appended REOPENED block, rank 3 of 5 -- recurred twice as a HARD
  `preflight_reject`, reproducing precisely the behavior Part 1 of #80's own
  fix was meant to replace with a soft advisory.

**`b68be869d2c2` (MCP#69):**
- `state`: `regression-commented` -> `regression-reopened`
- added `reopened_date: "2026-09-07"`, `reopen_comment_url`
- `notes`: appended REOPENED block, rank 4 of 5 -- recurred 2026-08-21T08:43:40Z;
  the same session's next attempt was a second wrong guess at the same target,
  so the user was never steered to `project.lp` in either attempt.

**`d905780c9f6f` (MCP#75):**
- `state`: `regression-commented` -> `regression-closed-superseded`
- added `not_reopened_comment_url`, `tracking_issue: 111` (Task C)
- `notes`: appended a DELIBERATELY NOT REOPENED block -- recurrence is at a
  THIRD call site (`ISilDataAccess.BeginUndoTask`), not either of the two
  originally reported (`GetFields`, `Create`); original fix holds for its known
  sites while the gap generalizes; tracked instead by new MCP#111.
  `reopen_rank: 5` preserved unchanged (now documented as "the one candidate
  recommended against reopening").

**`3393ffcc9d96` (flexicon#34):**
- `state`: `regression-commented` -> `regression-closed-deliverable-was-correct`
- added `not_reopened_comment_url`
- `notes`: appended a DELIBERATELY NOT REOPENED block -- cookbook issue, docs
  were the correct deliverable and were delivered; the verbatim 3-month
  recurrence indicates a surfacing gap (`find_examples`/`search_by_capability`),
  not a bad fix. Recorded the un-filed FlexToolsMCP-side surfacing-gap follow-up
  candidate inline (no issue number assigned yet). Explicit contrast with MCP#84
  noted per the task brief (#84 reopened on the opposite reasoning -- docs-only
  change merged against a runtime-symptom defect).

### Task B: new filed entry, MCP#111

New key `51a3e9827ef5` (sha1 of the canonical signature string
`No method matches given arguments for ISilDataAccess.BeginUndoTask`, truncated
to 12 hex chars, consistent with this ledger's existing fingerprint style).
`repo: MattGyverLee/FlexToolsMCP`, `issue: 111`, `state: open`,
`first_seen`/`last_seen: "2026-08-11T06:15:37 (local)"` -- explicitly labeled
`(local)` rather than given a trailing `Z`, per the UTC/local skew documented in
MCP#110 (fingerprint `f4f1db54e896`). `occurrences: 1`. Note cites the evidence
path, cross-references closed #75 and MCP#108, and records that it supersedes
the #75 recurrence.

### Task C: #75 entry points at #111

Covered in the `d905780c9f6f` edit above: `tracking_issue: 111` added; the
entry stays historically attributed to closed #75 (`repo`/`issue` fields
unchanged) while the notes make clear #111 is now the active tracker for the
generalization gap.

### Task D: scanned_through.coverage_notes

Added a fourth coverage note recording that the repo-root `operations.jsonl`
existed, was not part of the scan cursor (which tracks `~/.flextoolsmcp/logs/`),
was preserved at the evidence path and inlined into a MCP#109 comment, then
removed with user authorization, and that `.gitignore` now prevents recurrence
of the accidental-commit exposure (not the underlying `log_dir_fn` defect).
Other `scanned_through` fields left unchanged -- the cleanup did not touch the
scan cursor.

### Task E: history entry amended (2026-09-07 scan)

| Field | Before | After |
|---|---|---|
| `new` | `7` | `8` |
| `reopened` | (absent) | `4` |
| `closed_deliberately` | (absent) | `2` |
| `cleanup` | (absent) | object with stray_jsonl_removed/evidence_preserved/gitignore_updated |
| `notes` | described 6 comment-only regressions "pending user confirmation" | rewritten to describe the 4 reopens with ranks, 2 deliberate non-reopens, the MCP#111 filing, and the completed cleanup |

`deduped: 5`, `regressions: 6`, `residual: 1`, `excluded_as_noise`,
`deferred_low_volume: 3` all left unchanged -- none of MCP#111's evidence
overlaps those buckets (the #75 recurrence was already counted once, under
`regressions`, in the cycle-2 write).

### STATUS.md

Appended a new subsection, "Follow-up: user-authorized reopens + cleanup
(2026-09-07, same day)", directly after the cycle-2 log-triage section's
"Awaiting user confirmation" list. Covers all four reopens with rank plus a
one-line rationale each, both deliberate non-reopens with reasons, the
MCP#111 filing, the completed cleanup, a pointer to this report, and the
single remaining un-filed follow-up (the flexicon#34-implied FlexToolsMCP
recipe-surfacing gap). No other STATUS.md section touched.

### .crew-handoff.json

- `status`: `needs_human` -> `feature_complete`
- `blocker`: (rationale string) -> `null`
- `spurt_complete` / `last_cycle`: updated to cycle 3
- `tasks_done`: 9 new entries appended for the reopens, MCP#111 filing,
  cleanup, .gitignore verification, ledger reconciliation, STATUS.md update,
  and this commit
- `next_checkpoint` / `next_entry`: rewritten -- no checkpoint remains; the
  only optional follow-up is the un-filed flexicon#34 surfacing-gap issue
- `filed.MattGyverLee/FlexToolsMCP`: `[108, 109, 110]` -> `[108, 109, 110, 111]`
- `commented`: restructured -- the old `closed_regression` split into
  `reopened_regression` (4 issues) and `closed_regression_not_reopened` (2
  issues, with one-line reasons)
- `ledger`: added `filed_keys_after_cycle3: 35` alongside the existing
  `filed_keys_before`/`filed_keys_after_cycle2` (renamed from
  `filed_keys_after`)
- new `reopens_actioned` (issue -> rank) and `deliberately_not_reopened`
  (issue -> reason) objects added
- new `cleanup` object added (removal date, evidence paths, gitignore flag)
- `deliberately_not_closed` (MCP#40) left unchanged -- out of this cycle's scope

## Discrepancies found this cycle

None. Every fact in the task brief (issue states, comment URLs, evidence
contents, the code_sha256/counts in the preserved JSONL, the .gitignore
lines, the MCP#111 body) was independently re-verified live against GitHub and
the filesystem before being written into the ledger, and all matched the task
brief exactly. The only judgment call made independently (not dictated
verbatim by the task) was the MCP#111 fingerprint value itself, since no
fingerprint algorithm is documented anywhere in this ledger; a sha1 of the
canonical signature string, truncated to 12 hex characters, was used for
consistency with the existing key style (e.g. `15e120d04d11`, `39a2f8c1d004`).

## Validation

`python -c "import json; json.load(open(...))"` run on both
`docs/logscan-state.json` and `specs/logscan-2026-09-07/.crew-handoff.json`
before AND after this cycle's edits -- both parsed successfully both times.
Before: 34 filed keys / 5 history entries (matching commit `69e0260`); after:
35 filed keys / 5 history entries (the history entry was amended in place, not
appended -- the scan itself did not recur, only its resolution changed). No
issue was reopened/closed/relabeled by this agent (all were already actioned
before this cycle began). No source code touched. No index JSON touched.

## Commit

Staged exactly: `.gitignore`, `docs/logscan-state.json`, `STATUS.md`,
`specs/logscan-2026-09-07/.crew-handoff.json`,
`specs/logscan-2026-09-07/evidence/`, `specs/logscan-2026-09-07/reviews/`
(this file). Verified via `git diff --cached --name-status` before committing
that no unrelated files (the flexicon 4.4.1->4.5.2 index migration, the
swahili-audit-2026-09 cycle1 files) were swept in.

Commit sha: see the immediate follow-up commit touching only this file, in the
style of this repo's precedent at `eb2a1f2` ("record the cycle-6 fix commit
sha in its own report").
