# Data model: parser-check CP4

**Date**: 2026-09-23 · **Spec**: [`spec.md`](./spec.md) · **Research**: [`research.md`](./research.md)

This is a Phase 1 output. It covers the entities CP4 introduces and the CP3 shapes it
extends. Every CP3 extension is **additive**: CP3's frozen artifact contract
(`../parser-check-cp3/contracts/artifact.md`) gains keys and loses none.

---

## 1. FilingRequest (input; extends `ParseTextInput`)

`models.py:876`, `extra="forbid"`. The three new fields are optional:

| Field | Type | Default | Rule |
|---|---|---|---|
| `apply` | `bool` | `False` | `False` keeps today's read-only behaviour **exactly** (FR-001) |
| `confirmed` | `bool` | `False` | Meaningful only with `apply=True`. It is never enough on its own: see `plan_id` |
| `plan_id` | `Optional[str]` | `None` | 64 lowercase hex characters. Required for `confirmed=True` to reach filing. If it is absent, or not one this session issued, the answer is `confirmation_required` (R-08) |

Validation:
- `confirmed=True` or `plan_id` without `apply=True` is refused as `invalid_input`, the
  existing code. A read-only request cannot carry a confirmation.
- `scope_kind="words"` is allowed for filing. It is still a named scope.
- There is **no** `write_enabled`, `backup_before_write`, `force`, `override` or
  `skip_*` field (FR-004, SC-008, R-15).

## 2. MutationPlan (the preview)

This is what `confirmation_required` carries under `plan`. It is canonical JSON, and
`plan_id = sha256(canonical_json(plan_without_display_fields))`.

| Field | Type | Bound into `plan_id`? | Source |
|---|---|---|---|
| `scope` | `{kind, value, limit}` | yes | request |
| `scope_fingerprint_key` | `str` | yes | CP3 `fingerprint_key` |
| `words_in_scope` | `int` | yes | CP3 `resolve_scope` |
| `gate` | `GateStanding` (section 4) | yes | `filing/gate.py` |
| `deletion_projection` | `DeletionProjection` (section 3) | yes (per-wordform GUID sets and counts) | `filing/projection.py` |
| `disapproval_overwrites` | `{count, by_wordform: {wf: [guid]}}` | yes | FR-040. In-use **and** user `disapproves` |
| `in_use_approvals_projected` | `int` | yes | in-use **and** user `noopinion`. Filing will record an approval on these (FR-033). **Never** labelled tacit |
| `duplicate_disclosure` | `{count, basis}` | yes | CP3 `duplicate_projection`, reused as is (FR-016) |
| `errored_word_rule` | `str` (fixed sentence) | no | FR-017 |
| `backup` | `BackupIntent` (section 5) | yes (`outcome`) | `write_ladder.backup_intent` |
| `access` | `{verdict, shared_mode_advisory?}` | yes (`verdict`) | `write_ladder.probe_write_access` |
| `send_receive` | `true \| false \| "unknown"` | yes | R-14 |
| `recovery_route` | `str` | no | FR-043 wording. Section 8 |
| `side_effects` | `[str]` | no | the project-wide removal of problem annotations; the lowercase non-filing divergence (R-06) |
| `confirmation_setting` | `{require_write_confirmation: bool, effective_for_filing: true}` | no | R-08 |
| `estimate_note` | `str` | no | the projection is an **upper bound**, "may delete up to N", not a prediction |

**Large plans in the response.** When `deletion_projection.by_wordform` or
`disapproval_overwrites.by_wordform` names more than 200 GUIDs, or `words_unreadable`
more than 50 words, the *response* shows that list compact. `by_wordform` becomes
`by_wordform_sample` (the first 20 wordforms) plus `by_wordform_summary`
(`{wordforms, analyses, sample_wordforms}`), and `words_unreadable` is cut to 50 with
`words_unreadable_count`. `plan.detail` then gives `full_plan_path`, the full plan
written to `<record dir>/plans/<plan_id>.json` (the newest 20 are kept), or
`full_plan_unavailable` if that write failed. This affects only how the plan is shown.
The session stores the full plan, `plan_id` hashes the full plan, and filing checks
against the full plan.

**Identity.** `plan_id` is stored in session state as
`filing_plans[(project, scope_fingerprint_key)] = {plan_id, issued_at}`. Only the newest
plan per key is kept.

## 3. DeletionProjection

| Field | Type | Rule |
|---|---|---|
| `predicate` | `"user_noopinion AND not_referenced_by_any_segment_directly_or_via_gloss"` | fixed string (FR-011, R-01) |
| `upper_bound` | `int` | concrete, including `0` (FR-013) |
| `by_wordform` | `{wordform: [analysis_guid]}` | per wordform (FR-013) |
| `segment_use_unknown` | `int` | analyses whose join could not be evaluated. **They are counted inside `upper_bound`**: when the answer is unknown, the analysis is treated as deletable for a bound. This is the opposite of CP3's information projection, and it is deliberate |
| `excluded_disapproved` | `int` | FR-012. Shown so the user can see they were considered |
| `words_unreadable` | `[wordform]` | words whose stored analyses (or whose wordform lookup) could not be read. They are **not covered** by `upper_bound`, which cannot count analyses nobody could list. The confirmation message says so. The R-02 invariant below still refuses any deletion for them that `by_wordform` does not name. Added by the CP4 pattern audit (sweep #4) |
| `project_state` | CP3 `ProjectParseState` | FR-015: the one probe. A never-parsed project gives `upper_bound = 0` (SC-003) |

**Invariant (R-02).** At filing time, a word's would-delete set must be a subset of
`by_wordform[wordform]`. If it is not, the word is skipped with `outside_projection`.

## 4. GateStanding and LoadErrorBaseline

`GateStanding`:

| Field | Type |
|---|---|
| `status` | `"clean" \| "pre_existing_errors" \| "refused"` |
| `signal` | `null \| "morpher_null" \| "new_load_errors" \| "eligible_forms_dropped"` |
| `load_error_count` | `int` |
| `pre_existing_error_count` | `int` |
| `new_errors` | `[LoadError]` |
| `resolved_error_count` | `int` |
| `eligible_count` / `baseline_eligible_count` | `int` / `Optional[int]` |
| `dropped_entries` | `[{entry_guid, headword}]` |
| `baseline_source` | `"this_run" \| "prior_run:<run_id>" \| "absent"` |
| `hypothesis_note` | fixed: "pre-existing load errors are treated as benign; that is a working hypothesis, not an established fact" (spec Assumptions) |

The **CP3 `load_error_baseline` object** gains one key, which is additive:

| Added key | Type | Written by |
|---|---|---|
| `eligible_entries` | `[guid]` | every batch run (read-only or filing) once the grammar is loaded, so a read-only run re-baselines both halves of the gate (FR-021, FR-039) |

A baseline with no `eligible_entries` key, written by a CP3 run from before CP4, compares
load errors only. `baseline_eligible_count` is then `null`, and the plan says the
eligibility half has no baseline yet.

**State transitions of the gate.** It is evaluated at three points: preview, confirmed
call, and the job's **every** grammar load (R-05). A refusal at any of them stops the
filing. Refused at preview or confirm: nothing starts. Refused at job time: the run ends
`refused_midrun`, and whatever was already filed is persisted and reported.

## 5. BackupIntent / BackupOutcome

| Field | Intent (preview) | Outcome (after the rung) |
|---|---|---|
| `outcome` | `"will_be_taken" \| "not_expected" \| "disabled_by_configuration"` | `"taken" \| "not_taken"` |
| `reason` | e.g. `insufficient_disk_space`, `project_fwdata_not_found`, `backup_before_write=false` | from `perform_pre_write_backup.skipped_reason` |
| `path` | -- | the backup directory, outside the project (FR-042) |
| `peer_caveat` | when `open_shared` | `_PEER_BACKUP_CAVEAT`, reused |
| `no_recovery_warning` | when the outcome is not `will_be_taken` | when `not_taken`. Section 8 wording |

The session key is `filing_backed_up_projects`. It is separate from `run_module`'s
`backed_up_projects` (FR-008).

## 6. FilingClaim (in-process; not persisted as a lock)

| Field | Type |
|---|---|
| `project` | `str` (key) |
| `run_id` | `str` (32 hex) |
| `started_at` | ISO-8601 UTC |
| `words_completed` | read live from the `RunHandle` |

Lifecycle: `acquire` happens once all rungs have passed, just before `start_run`.
`release` happens in the runner's terminal transition (`finally`). A startup sweep marks
orphaned non-terminal filing runs `crashed` (R-11).

## 7. Filing run: `meta.json` `filing` section (additive to CP3 `RunMeta`)

This is present only on runs created with `apply=True`.

| Key | Type | FR |
|---|---|---|
| `requested` | `true` | -- |
| `confirmed_plan` | `MutationPlan` (as confirmed) | FR-032 |
| `plan_id` | `str` | FR-006 |
| `backup` | `BackupOutcome` | FR-009, FR-032 |
| `no_recovery_warning` | `Optional[str]` | FR-009. The same text as the response |
| `send_receive` | as section 2 | FR-043 |
| `access_verdict` | `str` | FR-030 |
| `state` | `"filing" \| "completed" \| "cancelled" \| "refused_midrun" \| "crashed" \| "failed"` | FR-028, FR-034 |
| `counts` | `FilingCounts` (below) | FR-032 |
| `projected_deletions` / `actual_deletions` | `int` / `int` | FR-032, SC-002 |
| `in_use_approvals_recorded` | `int` | FR-033. The key name is fixed, and no key or value says `tacit`, `unreviewed` or `auto_approved` |
| `disapprovals_overwritten` | `[DisapprovalOverwrite]` | FR-041 |
| `filed_words` | `[wordform]` in filing order | FR-034 (cancel/crash report) |
| `divergences` | `[str]` | R-06 lowercase, R-03 declined-is-not-deferred |

`FilingCounts`:
- `created`, `reapproved`, `duplicated`, `deleted`, `unchanged`;
- `errored_words`, `errored_word_deletions` (FR-017);
- `skipped: {invalid_object, outside_projection, filer_declined}`.

`skipped` has exactly three reasons:
- `invalid_object`: `ParseResult.IsValid` false or the wordform is gone (FR-019);
- `outside_projection`: R-02;
- `filer_declined`: `CanStartUow` false (FR-019).

A word refused mid-run is not a skip. The run's `state` records it.

**Classifying each word** (worker, per word, from the live objects before and after the
pump):
- `created`: an analysis present after the pump and not before.
- `reapproved`: a pre-existing analysis matched by the result.
- `duplicated`: created **and** CP3's duplicate predicate is true for it.
- `deleted`: present before the pump and absent after.
- `unchanged`: the wordform's `Checksum == result.GetHashCode()` **before** `ProcessParse`.
  The filer skips such a word (`ParseFiler.cs:208`).

## 8. Fixed wording (transcribe from here)

The **no-recovery warning** (FR-009), with `[reason]` substituted:

```
NO BACKUP WAS TAKEN ([reason]). Filing cannot be undone, and no recovery point exists for this run.
```

The **Send/Receive route** (FR-043), appended to the no-backup warning and to the plan
when `send_receive` is not `false`:

```
This project takes part in Send/Receive. If filing damages it, do not Send/Receive; delete this local copy and re-download the project from its repository. A local backup, where one exists, is a convenience for this machine, not a way to revert the shared project.
```

The **shared-mode advisory** (FR-030):

```
FLEx has this project open with sharing enabled; filing will run as a non-master peer. Make sure FLEx's own parser is not running on this project. The MCP cannot detect whether it is, and filing by both at once is not prevented.
```

The **errored-word rule** (FR-017):

```
A word whose parse ends in an error is filed as FLEx files it: its parser opinions are cleared and its unshielded, unreviewed analyses are deleted.
```

The **in-use approvals count** (FR-033), with `[N]` substituted:

```
[N] analyses in use in a text were given a user approval by filing. Approval is recorded for anything left in use; this does not mean anyone reviewed them.
```

## 9. PreDeletionCapture and DisapprovalOverwrite

These are appended to `filing/deletions.jsonl` in the run directory, one line per
analysis, with `fsync` per line (CP3's `append_result` discipline). Each line is written
**before** the pump that deletes or overwrites.

| Field | Capture | Overwrite |
|---|---|---|
| `kind` | `"pre_deletion"` | `"disapproval_overwrite"` |
| `wordform` | yes | yes |
| `analysis_guid` | yes | yes |
| `morph_bundles` | `[{morph_guid, msa_guid, infl_type_guid, form}]` | yes |
| `glosses` | `[{guid, form_by_ws}]` | yes |
| `evaluations` | `[{agent_guid, agent_name, human, opinion, date}]` | yes (**the prior** evaluation) |
| `category` | yes | yes |
| `confirmed_after` | set by the post-pump pass: `deleted` / `survived` | `overwritten` / `unchanged` |

`confirmed_after` is written as a second line keyed by `analysis_guid`, not as a rewrite,
because the file is append-only.

## 10. Stage graph (`parse/stages.py`)

CP4 adds FILING edges **only for runs created with `filing=True`**:
- `parsing -> filing` (the first word is filed);
- `filing -> completed | cancelled | failed`.

A read-only run's transition table is unchanged, and `can_transition(parsing, filing)`
is still False for it. `test_filing_is_unreachable_from_every_stage` is narrowed to read
runs and joined by `test_filing_reachable_only_for_filing_runs`.
