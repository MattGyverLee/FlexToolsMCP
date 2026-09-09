# SPEC -- write-authorization audit trail

**Feature:** `write-authorization-audit`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** triage of `user-logs/Kendall/session_{145439,154828}*.log`, 2026-09-09
**Depends on:** nothing (ships standalone; highest priority of the MCP-side
specs)

---

## 1. Context

A live, destructive write executed and **the log cannot say whether a human
authorised it.**

Session 154828 op#3 (15:51:02): `Write enabled: True`, `Preflight: passed
(tier=none)`, `[BACKUP] 'Test' -> ...20260909T205102Z\Test.fwdata`, ran to
completion. No `[REJECT]`, no `confirmation_required`.

That should have been impossible. The gate at `execution.py:4253` is
`needs_lock = write_enabled and is_mutating_script`, and I ran the **verbatim**
logged code (extracted from the DEBUG block, 1484 bytes, matching the logged
`sha256=0ce1eadb7869`) through the real detector with the real index:

```
145439_op3 (2355 bytes)  is_mutating_script: True  [AddComplexFormComponent, Delete]  -> gate fired
154828_op3 (1484 bytes)  is_mutating_script: True  [AddComplexFormComponent, Delete]  -> gate did NOT fire
```

Detection was correct in both. The two escape routes from `execution.py:4257-4260`
are `args.get("confirmed", False)` being True, or
`require_write_confirmation` being false in config (`config.py:78-79`, default
True). **Neither is recorded anywhere**, so post-mortem cannot distinguish
"the user said yes" from "the model asserted confirmation on the user behalf"
from "the setting was off".

The contrast is stark within the same log set. Session 145439 did it right:
op#2 rejected with `Reason code: confirmation_required / mutations=2`, and
op#3 carries `User request: yes` -- the human assent is in the record. In
session 154828 every operation carries the same stale string,
`User request: open project "Test" with the flextools MCP`, which is the
session-opening message, not a request for any of ops 2-7.

`_log_operation_start` (`execution.py:440-453`) takes no `confirmed` parameter.
It logs project, write_enabled, source_kind, user_intent, user_request and code
fingerprint. That is the whole header.

### Three further gaps in the same trail

1. **Report bodies are never captured.** The op that mutated the lexicon left
   `Messages: 5 info, 0 warnings, 0 errors` and nothing else. Worse, the module
   emits two messages per component in *both* branches
   (`"complex form added"` / `"complex form would be added"`), so the counts
   are **identical** for a live write and a dry run. The log cannot tell you
   which one happened.

2. **Restores are invisible.** `[BACKUP]` is logged
   (`execution.py`, backup path). There is no restore record anywhere:

   ```
   grep -rn "\[RESTORE\]|def .*restore" --include=*.py src/   ->  (no matches)
   ```

   Message counts reconstruct what the log should have stated outright: op#2
   (15:49) saw one component; op#3 (15:51) consumed it; op#4 (15:54) saw
   **zero** (3 info = the three unconditional messages only) yet reported
   `[OK] Operation completed successfully` for an intent of *"Verify the
   ILexEntry-cast-free version still works"* -- a false pass against data the
   previous op had destroyed; then op#6 (15:59) saw one component again, so a
   restore happened off-log. State across operations is unreconstructable.

3. **`user_request` goes stale.** It falls back to `user_intent`
   (`execution.py:487-490`) but nothing detects that the same verbatim string
   is being replayed across many ops. When it is the only evidence of human
   assent, a stale value is worse than an absent one.

---

## 2. Settled -- do not revisit

- **This is logging, not policy.** Do not change what the confirmation gate
  allows; record what it decided and why. Tightening the gate is a separate
  decision the user has not made.
- **Record the authorisation inputs even when the gate is skipped.** A skipped
  gate is exactly the case we could not audit.
- **Never fabricate assent.** If the model passes `confirmed=True`, the log says
  the flag arrived on the call. It must not be rendered as "user confirmed".
  The distinction between "the caller asserted it" and "a human typed yes" is
  the whole point.
- **Do not log the report body for read-only runs by default.** Verbose
  transcripts of a 50k-entry read are noise; write runs are the ones that need
  the record. See 3c.

---

## 3. Design

### 3a. Header fields

Add to `_log_operation_start` and the `operations.jsonl` stash
(`_stash_op_start`, `execution.py:497+`):

```
Confirmed:       True (supplied by caller)      # or: False
Confirm policy:  require_write_confirmation=True
Backup policy:   backup_before_write=True (already backed up this session: False)
Gate outcome:    write_confirmation=skipped_confirmed
```

`Gate outcome` is the load-bearing addition. One of:
`not_applicable` (read-only, or no mutations detected),
`fired` (rejected -- pairs with the existing `_log_preflight_reject`),
`skipped_confirmed` (`confirmed=True` on the call),
`skipped_policy_disabled` (`require_write_confirmation=false` in config).

`skipped_policy_disabled` must also be surfaced in the operation *response*,
not just the log. A user whose config silently disables write confirmation
should be told on every write.

### 3b. Mutation record on the executed path

Today `mutations_detected` is built only to populate the rejection payload
(`execution.py:4261`). Build it for the executed path too and log it:

```
Mutations:       2 (guarded)  LexEntryOperations.AddComplexFormComponent:18, VariantOperations.Delete:19
```

Then the log states what the run was permitted to do, independent of what the
module chose to report.

### 3c. Report bodies

- `write_enabled=True`: log every message (type, text, ref) at INFO, under a
  `Report:` block mirroring the existing `Code:` DEBUG block convention.
- `write_enabled=False`: log the body at DEBUG (present when the session log
  level allows, absent from routine INFO logs).
- Cap it the way info-cap already works (the `Info-cap:` line), and record the
  truncation count rather than silently dropping.
- Include the messages in `operations.jsonl` so `op_telemetry` can query them.

This alone would have distinguished the live write from the dry run in session
154828.

### 3d. Restore records

- Add `[RESTORE] '<project>' <- <backup path>` at the same level as `[BACKUP]`,
  emitted by whatever performs a restore.
- There is no restore *tool* today (section 1, gap 2) -- the user does it by
  hand. So also: on every operation, record a cheap project-state stamp
  (`.fwdata` mtime + size) in the header. An out-of-band restore then shows up
  as a discontinuity in the log even though the MCP did not perform it.
- **This stamp is what makes the trail reconstructable across manual restores,
  which is how this user actually works** -- session 145439 op#4 intent reads
  *"Verify project state after restoring pre-write backup"*.

### 3e. Stale `user_request` detection

When the effective `user_request` is byte-identical to the previous operation
in the same session, mark it:

```
User request:    open project "Test" with the flextools MCP  (UNCHANGED from op#2)
```

Do not block on it. The marker is enough to stop a reader mistaking a replayed
string for fresh assent.

### 3f. Do not let a false pass read as success

Related to `shared-mode-access` CP1/T1.5 (do not report success over a failed
write). The narrower rule here: when an operation whose declared intent is
verification processes **zero** target objects, say so. A `[OK]` line on a run
that iterated nothing is how op#4 passed. Emit
`Coverage: 0 objects processed` when the run reports no per-item messages and
completed in a loop-shaped module, and reflect it in the response so the model
does not read the result as confirmation.

Keep this heuristic conservative and advisory -- it is a legibility aid, not a
gate.

---

## 4. Checkpoints

### CP1 -- header and policy fields

- **T1.1** Extend `_log_operation_start` (`execution.py:440`) with `confirmed`,
  `require_write_confirmation`, `backup_before_write`, `was_backed_up`; log per
  3a and add all four to `_stash_op_start`.
- **T1.2** Compute and log `Gate outcome` at the four decision points around
  `execution.py:4253-4325`.
- **T1.3** Surface `skipped_policy_disabled` in the response payload.
- **T1.4** JSONL schema bump; update whatever validates
  `operations.jsonl` records and `op_telemetry.group_records_by_session`.

### CP2 -- mutations and report bodies

- **T2.1** Build `mutations_detected` on the executed path and log per 3b.
- **T2.2** `Report:` block per 3c, with the write/read split, cap and
  truncation count.
- **T2.3** Messages into `operations.jsonl`.

### CP3 -- state continuity

- **T3.1** `[RESTORE]` emission point and the project-state stamp per 3d.
- **T3.2** Stale-`user_request` marker per 3e.
- **T3.3** `Coverage:` line per 3f.

---

## 5. Verification

1. **Unit** -- `tests/test_write_authorization_audit.py`: the `Gate outcome`
   decision table (write_enabled x is_mutating_script x confirmed x policy),
   asserting the logged string for each of the four outcomes.
2. **Replay** -- reconstruct both write runs from the Kendall logs as fixtures
   and assert the new header would have distinguished them. Concretely: with
   `confirmed=True` supplied, session 154828 op#3 must log
   `Gate outcome: write_confirmation=skipped_confirmed`, and the `Report:`
   block must contain `complex form added` rather than
   `complex form would be added`. **This is the acceptance test for the whole
   spec.**
3. **Redaction** -- confirm no header field can carry lexical data that was not
   already in the log; the `Report:` block may (by design) and must respect the
   existing info-cap.
4. **Contract** -- `python tests/make_golden.py --regen`, then
   `pytest tests/test_response_contract.py`.
5. **Live** *(requires FieldWorks + human authorization)* -- one write with
   `confirmed=True`, one refused, one with the policy disabled; read the three
   log blocks and confirm a reader can tell them apart without the transcript.
6. **Regression** -- full `pytest`, `validate_integrity.py all`,
   `verify_python.py`.

---

## 6. Out of scope

- Changing the confirmation policy, adding a second human-assent channel, or
  making `confirmed=True` harder for a model to supply. Worth discussing; not
  this spec.
- Building a restore *tool*. 3d only records restores and detects out-of-band
  ones.
- The false-pass root cause (a verification run against destroyed data) --
  3f makes it legible; `vanilla-flextools-parity` makes verification real.
