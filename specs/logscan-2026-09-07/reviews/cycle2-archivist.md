# cycle2-archivist.md -- Consolidated ledger write (August + September merge)

**Archivist:** /lex-archivist, cycle 2. **Scope:** single consolidated write to
`docs/logscan-state.json`, plus the two cross-link comments authorized in task
item K. No source code touched. No `.gitignore` edit. No issue reopened,
closed, or relabeled. No file deleted.

Sources read: `cycle2-logscan-flexicon.md`, `cycle2-logscan-mcp.md`,
`cycle2-logscan-regressions.md`, `cycle1-logscan-august.md`,
`cycle1-logscan-september.md`, `cycle1-explore-stray-jsonl.md` (all under
`specs/logscan-2026-09-07/reviews/`). The task prompt named two cycle1 files
(`cycle1-domain.md`, `cycle1-explore-nullmorph.md`) that do not exist in this
directory -- confirmed via `ls`; the actual cycle1 files present are the three
listed above plus the two `cycle2-logscan-*` files already covered. Treated as
a naming discrepancy in the task brief, not a missing artifact (see
Discrepancies below).

## Ledger keys modified (before -> after)

### A. State corrections (stale `state: open` -> verified closed)

| Fingerprint | Field | Before | After |
|---|---|---|---|
| `39a2f8c1d004` (#39) | state | `open` | `regression-commented` |
| | close_date | (none) | `2026-07-21T07:38:02Z` |
| | occurrences | `13` | `23` (+10 recurrences) |
| | last_seen | `2026-07-20T00:00:00Z` | `2026-08-28T16:44:57Z` |
| `48c9b7e2a115` (#48) | state | `open` | `closed-not-a-tracker` |
| | close_date | (none) | `2026-07-12T05:51:45Z` |
| | occurrences | `61` | `95` (61 + 31 August + >=3 September, floor -- see Discrepancies) |
| | last_seen | `2026-07-20T00:00:00Z` | `2026-09-07T02:42:10` |
| `53d4e6f0b229` | issue | `53` | `80` (retarget, key unchanged) |
| | state | `open` | `regression-commented` |
| | close_date | (none) | `2026-07-21T06:30:06Z` |
| | occurrences | `31` | `31` (unchanged -- carried forward as-is per task B) |
| | last_seen | `2026-07-20T00:00:00Z` | `2026-08-15T20:49:55Z` |
| `b68be869d2c2` (#69) | state | `open` | `regression-commented` |
| | close_date | (none) | `2026-07-20T09:09:30Z` |
| | occurrences | `2` | `3` |
| | last_seen | `2026-07-10T23:36:42Z` | `2026-08-21T08:43:40Z` |
| `d905780c9f6f` (#75) | state | `open` | `regression-commented` |
| | close_date | (none) | `2026-07-20T23:31:51Z` |
| | occurrences | `3` | `4` |
| | last_seen | `2026-07-20T00:00:00Z` | `2026-08-11T06:15:37Z` |
| `f3827601b213` (#74) | state | `open` | `residual-not-strict-regression` |
| | close_date | (none) | `2026-07-20T23:31:52Z` |
| | tracking_issue | (none) | `109` |

All six carry an added note explaining the stale-state root cause (2026-07-20
write) and that each verified-closed within ~36 hours of that write.

### B. Retarget: `53d4e6f0b229` (#53 -> #80)

Fingerprint key unchanged. `issue: 53 -> 80`, `url` updated to
`.../issues/80`. Added a `correction` object: `prior_attribution: 53`,
`corrected: "2026-09-07"`, reason (#53 never mentions
`api_discovery_required`; #80's body names it at `execution.py:2240-2292`),
and an explicit `occurrences_note` recording that `31` was tallied under the
wrong issue and is carried forward as-is, not silently rewritten. Marked
`state: regression-commented` (a regression, not a plain dedup) since it
recurred 2026-08-11 and 2026-08-15 after #80's real close
(`2026-07-21T06:30:06Z`).

### C. Aggregate ownership: `48c9b7e2a115` (#48)

`state: open -> closed-not-a-tracker`. `occurrences: 61 -> 95`. Added a causal
note: the September scanner mis-deduped fresh `casting_issues_detected` volume
against this bucket *because* of the stale open state corrected in A; #48 is
a closed spec/enhancement, never a defect tracker. Volume flagged as a
SYMPTOM of the open #40/#97 casting-gate work -- nothing filed for it.

### D. Backdates

| Fingerprint | Field | Before | After |
|---|---|---|---|
| `0d7917c944e2` (#100) | first_seen | `2026-09-06T20:17:09Z` | `2026-08-18T21:41:14Z` |
| | occurrences | `1` | `2` |
| `da50b2947f5d` (flexicon#257) | first_seen | `2026-09-06T20:17:09Z` | `2026-08-18T21:41:14Z` |
| | occurrences | `1` | `2` |
| `3969b046e421` (#101) | occurrences | `2` | `3` |
| | last_seen | `2026-09-06T19:21:03Z` | `2026-09-07T02:49:45Z` |

Both backdated entries carry a note that the 08-18 evidence is the
`ReversalIndexOperations` variant while the stored signature text is the
`MSAOperations` string -- same defect family, different class name, NOT the
identical string.

New entry created: `7c7b4c05e2b1` (MCP#98) -- no `filed` entry existed
previously. `repo: MattGyverLee/FlexToolsMCP`, `issue: 98`, `state: open`,
`first_seen: 2026-08-13T00:02:12Z`, `occurrences: 2` (1 August-window + 1
September-window instance; the exact September intra-window timestamp was not
available from the reports read, so `last_seen` is approximated to
`2026-09-06T20:19:27Z`, matching the sibling F1-F6 batch timestamp from the
same scan -- flagged as an approximation in the entry's own notes).

### E. New filings (N1-N7)

| Fingerprint | Proposal | Issue | State |
|---|---|---|---|
| `70b131eb301c` | N1 | flexicon#260 | open |
| `39c206b4c315` | N2 | flexicon#261 | open |
| `5dc1029cc399` | N3 | flexicon#262 | open |
| `abb91b059956` | N4 | flexicon#263 | open |
| `a9895b83b6a4` | N5 | MCP#108 | open |
| `bb05277778ee` | N6 | MCP#109 | open |
| `f4f1db54e896` | N7 | MCP#110 | open |

All seven are brand-new ledger keys (none existed before). N5/MCP#108's note
records the fold decision verbatim: facet (c) (unresolvable rewrite promise
for a plain attribute-name typo with no matching property anywhere in the
liblcm schema) was **kept** in #108 rather than folded into #97, because #97's
scope is *which interface* to suggest among plausibly-correct candidates,
while facet (c) has no candidate at all -- a `did_you_mean`-shaped gap, not a
ranking gap.

### F. Regression entries (`state: regression-commented`)

Covers #84 (new entry, fingerprint `15e120d04d11`), #39 (`39a2f8c1d004`,
above), #75 (`d905780c9f6f`, above), #80 (`53d4e6f0b229`, above), #69
(`b68be869d2c2`, above), and flexicon#34 (new entry, fingerprint
`3393ffcc9d96`). Each carries `close_date`, `recurrence_dates`, and
`comment_url`. #84 additionally carries `close_to_recurrence_minutes: 58`
(the most severe signal in this scan -- `gh issue view 84` shows the merged
fix was documentation-only, which does not plausibly explain the identical
error recurring under an hour later).

Every regression-commented entry records: **no issue was reopened**, and the
ranked reopen recommendation is pending user confirmation:
**#84 > #39 > #80 > #69 > #75** -- differing from the lead's original
ordering (#80 moved up, on the grounds that the hard `preflight_reject`
recurrence regresses the very behavior change #80's own fix introduced).
flexicon#34 is NOT part of this MCP-only ranking (different repo).

### G. #74 classification

`state: open -> residual-not-strict-regression`. `close_date:
2026-07-20T23:31:52Z`. `tracking_issue: 109`. Note records: production
`operations.jsonl` was NOT polluted this time, and the stray row ids were
`op-*` (not #74's original `test-op-*` signature) -- #74's fix partially
held; the leak went to a cwd-relative file instead. Comment posted, not
reopened.

### H. Deferred entries

| Fingerprint | Field | Before | After |
|---|---|---|---|
| `e9be15c60f2e` | occurrences | `2` | `5` |
| | last_seen | `2026-07-20T00:00:00Z` | `2026-08-26T14:48:33Z` |

Added graduation-threshold note (file as an issue if cumulative occurrences
exceed 8 in a future scan). Two brand-new deferred entries created:
`d447c0f2dd76` (`IMoAffixProcessFactory.GetMethods`, 2026-08-19T04:24:43Z,
occurrences 1) and `08d1786ff5ea` (`IMultiUnicode` wrong import path,
2026-08-19T08:50:46Z, occurrences 1). Neither has a `repo`/`issue` field
(no clear fix target, consistent with the existing deferred-entry style in
this ledger).

### I. `scanned_through` (fully re-stat'd, not copied from stale reports)

| Field | Before | After |
|---|---|---|
| operations_log_bytes | `2994063` | `5084909` (fresh `wc -c` against `~/.flextoolsmcp/logs/operations.log`, not the August report's already-stale `4567946`) |
| operations_log_rotated_predecessor | (none) | `{file: operations.log.1, bytes: 5242870, max_date: 2026-08-10}` |
| operations_jsonl_lines | `236` | `648` (fresh `wc -l`) |
| max_log_date | `2026-09-06` | `2026-09-07` |
| coverage_notes | (none) | 3 facts: no unscanned gap 08-29..09-05 (verified via directory listing); real 10-day hole in `operations.log` 08-11..08-20, covered by jsonl (157 records) and per-session logs -- filed as MCP#110; `jsonl.ts` is UTC vs. local-time `.log`/session files |
| session_logs_scanned | (single-session note from the prior scan) | both windows' file lists, August (514 total / 29 real / 485 fixture reruns) and September (3 real sessions / 33 harness-rerun pairs excluded), counts not enumerated individually |

Top-level `last_scan`/`last_scan_by` also updated: `2026-09-06T21:35:00Z` /
`lex-logscan` -> `2026-09-07T00:00:00Z` / `lex-logscan (2 windows) + lex-lead
synthesis`.

### J. History entry appended

`{scan: 2026-09-07T00:00:00Z, new: 7, deduped: 5, regressions: 6, residual: 1,
excluded_as_noise: {fixture_and_harness_reruns: 518, itemised_one_offs: 9},
deferred_low_volume: 3, scan_by: "lex-logscan (2 windows) + lex-lead
synthesis"}` plus a prose `notes` field cross-referencing every fingerprint
touched.

`excluded_as_noise: 518` matches the task's given number exactly (485 August
fixture reruns + 33 September harness-rerun pairs). `regressions: 6` matches
the task's given number exactly (#84, #39, #75, #80, #69, flexicon#34).
`deduped: 5` = #48 aggregate merge + MCP#100 backdate + flexicon#257 backdate
+ new MCP#98 entry + #101 occurrence bump.

## Cross-link comments posted (task item K)

1. MCP#108 -> links flexicon#261 (`DataNotebookOperations.__GetRecordObject`
   raw `LcmCache.GetObject` call) as the concrete case where the polymorphic
   hint fired on a library-internal bug no user-side cast could fix:
   https://github.com/MattGyverLee/FlexToolsMCP/issues/108#issuecomment-5568255374
2. flexicon#261 -> links MCP#108 as the reason the failure was misreported to
   users as a resubmit-fixable casting problem:
   https://github.com/MattGyverLee/flexicon/issues/261#issuecomment-5568256133

Both issues were confirmed live via `gh issue view` (title/URL) before
commenting.

## Discrepancies found

1. **Task-cited cycle1 files do not exist.** The task's "READ FIRST" list
   named `cycle1-domain.md` and `cycle1-explore-nullmorph.md`; `ls` of
   `specs/logscan-2026-09-07/reviews/` shows only `cycle1-explore-stray-
   jsonl.md`, `cycle1-logscan-august.md`, `cycle1-logscan-september.md` (plus
   the three `cycle2-*` files). Read all three actual cycle1 files instead;
   they supply all the evidence the six-key A/B/C/D corrections needed. No
   content appears to be missing as a result, but flagging the filename
   mismatch since it looks like a copy-paste from a different spec directory
   (`swahili-audit-2026-09` has files named `cycle1-domain.md` per this
   session's own git-status listing).
2. **`48c9b7e2a115` September-window occurrence count is a floor, not an
   exact count.** Task C says "merge occurrences: prior 61 + 31 (August
   window) + the September window's instances (see the September cycle1
   report's dedup table)." The September report's dedup table lists three
   representative op#1 instances (one per real session) followed by "etc.",
   with no exhaustive tally. Recorded `occurrences: 95` (61 + 31 + 3) and
   flagged in the entry's own note that the September component is a floor.
3. **`53d4e6f0b229`'s A-instruction close date vs. B's retarget close date
   differ.** Task A literally gives `CLOSED 2026-07-21T07:38:03Z` for this
   fingerprint (which is actually #53's own close date, from the wrong prior
   attribution), while task B's narrative cites `#80's 2026-07-21T06:30:06Z
   close`. Used #80's real close date (`06:30:06Z`) as the operative
   `close_date` post-retarget, since B's retarget supersedes A's pre-retarget
   value; recorded #53's `07:38:03Z` only inside the `correction.reason`
   text for full audit-trail transparency, not as the active `close_date`.
4. **MCP#98's exact September-window timestamp is not in any report read.**
   Approximated `last_seen` to the sibling F1-F6 batch timestamp
   (`2026-09-06T20:19:27Z`) from the same 2026-09-06 scan; flagged as an
   approximation in the entry's notes rather than presented as exact.

## Validation

`python -c "import json; json.load(open(...))"` run before AND after the
write -- both parsed successfully (before: 291 lines / 22 filed keys /
5-entry-minus-1 history; after: 34 filed keys, 5 history entries). No
`.gitignore` edit. No file deleted. No issue reopened/closed/relabeled. No
source code touched.
