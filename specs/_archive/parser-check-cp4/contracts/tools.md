# Contract: CP4 tool surface

**Date**: 2026-09-23 · **Spec**: [`../spec.md`](../spec.md) · **Plan**: [`../plan.md`](../plan.md)

This is a Phase 1 output and **the transcription source** for implementation.
Identifiers marked *verbatim* come from the spec's Verbatim Constraints section. Do not
rename, recase or pluralise them. CP2's field-order divergence happened during
transcription, which is why this file exists.

---

## 1. `flextools_parse_text` (extended, not new)

| Aspect | Value |
|---|---|
| Name | `flextools_parse_text` *(verbatim)* |
| Annotations | **unchanged**: `readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False` (CP3 FR-025 / D-1; `tool_definitions.py:636-642`) |
| Description, first line | `[PARSE] In-process batch spine -- parse a corpus scope; with apply=true, file the results into the project behind preview, confirmation and backup.` It no longer says that filing is unreachable (FR-001) |
| Contract version | `tool-responses/1.0` *(verbatim)* |

### Arguments

The existing arguments are unchanged: `scope_kind`, `scope_value`, `limit`,
`vernacular_ws` and `project_name`. Three optional arguments are added:

| Argument | Type | Default | Notes |
|---|---|---|---|
| `apply` | boolean | `false` | *(verbatim; issue text `apply=true`)* Absent or false gives today's read-only batch, exactly |
| `confirmed` | boolean | `false` | *(verbatim: `confirmed=True`)* Resubmission flag |
| `plan_id` | string, 64 lowercase hex | none | Returned by the preview. Required for `confirmed` to take effect |

**No other argument is added.** `test_filing_bypass_surface.py` enumerates the input
schema and the config keys and fails if any name matches
`write|backup|force|override|skip|bypass|unattended|auto_confirm`, other than
`apply`, `confirmed` and `plan_id` (SC-008).

### Call sequence

```
1. apply=true                                  -> confirmation_required  {plan, plan_id}
2. apply=true, confirmed=true, plan_id=<id>    -> (plan re-computed)
      same plan_id  -> rungs 3-4 -> run started {run_id, backup | no_recovery_warning}
      different     -> confirmation_required   {plan, plan_id}   (FR-006)
```

The handler applies these checks, **in this order**, before anything else runs. Each row
is a refusal that stops the call:

| # | Check | Refusal | FR |
|---|---|---|---|
| 0 | input validation (`confirmed`/`plan_id` without `apply`) | the dispatcher's existing input-validation refusal | -- |
| 1 | project resolved | `project_name_required` (existing) | -- |
| 2 | **filing claim held for this project** | `parser_filing_in_progress` | FR-026. Before the engine, scope, preview, backup or parse |
| 3 | session `write_enabled` *(verbatim)* | `server_state_error` (existing), with `server_state: "write_disabled"`, `component: "session"`, and a `state_description` that names `flextools_start(write_enabled=true)` | FR-002, US1 AS-5. Nothing is parsed. `run_module` has no refusal here, because a disabled session simply runs read-only. Filing cannot degrade to read-only without lying about what `apply=true` did, so it refuses with an existing code rather than adding a third new one |
| 4 | engine gate | `parser_engine_mismatch` (existing) | CP3 FR-024 |
| 5 | HermitCrab agent probe | `parser_agent_missing` (existing, unchanged) | FR-025 |
| 6 | filing surface capability probe (R-03) | `parser_core_missing` / `incompatible_surface` (existing) | -- |
| 7 | scope resolution | `parse_scope_empty` / `parse_scope_ambiguous` (existing) | -- |
| 8 | access **probe** (`probe_project_access`), data only | none -- the verdict goes into the plan (`access`), with the remedy when it is `open_exclusive` / `held_by_other` | FR-030. Mirrors `execution.py:4482-4511`: `run_module` probes early, but only to gather data |
| 9 | refuse-to-file gate (preview load) | `grammar_load_unclean` | FR-020..FR-024, FR-039 |
| 10 | **confirmation** (unconditional for filing, R-08) | `confirmation_required` *(verbatim)* with `plan` + `plan_id` | FR-002 rung 2, FR-005, FR-006 |
| 11 | **access gate** (confirmed call): `open_exclusive` / `held_by_other` | `project_locked` (existing, reused) | FR-002 rung 3, FR-030. `verdict="unknown"` (the projects directory cannot be resolved, #118) is **refused** for filing with `project_drive_unavailable` (existing). This is a disclosed divergence: `run_module` proceeds on `unknown` |
| 12 | gate again (confirmed call) | `grammar_load_unclean` | FR-024 |
| 13 | backup rung (`perform_pre_write_backup` *(verbatim)*), best-effort | never refuses | FR-002 rung 4, FR-007, FR-008 |
| 14 | claim acquired, run started, `run_id` issued | -- | FR-003 |

`needs_lock` *(verbatim)* is always true for `apply=true`.

**The rung order is `run_module`'s, literally (FR-002).** The order is session
`write_enabled` (row 3), then confirmation (row 10), then the access gate (row 11), then
backup (row 13). `execution.py:4489-4491` says so in its own words: "an unconfirmed run
against an exclusively-held project still gets `confirmation_required` first". The lock
refusal itself is at `execution.py:4629`, after the confirmation block. So filing does
the same: an unconfirmed request against a project FLEx holds exclusively gets the
preview, and the preview's `access` field already says the confirmed call will be
refused and what the remedy is. The preview needs only the read-only open CP3 already
performs. Rows 4-9 are filing-specific preflights (engine, agent, surface, scope, gate).
They refuse before a preview exists because a preview cannot be built without them, and
none of them is a `run_module` rung. (Line numbers are at `2aedb1d`.)

### Response: confirmation_required (filing)

These keys are spread at the top level beside `error_code`, following `run_module`'s
`writeability`/`backup` precedent. `confirmation_required` has no detail model today, so
these keys are additive:

| Key | Type |
|---|---|
| `plan` | `MutationPlan` ([data-model section 2](../data-model.md)) |
| `plan_id` | string |
| `backup` | `{intent, note}`, same shape as `run_module`'s, with `intent` from `BackupIntent.outcome` |
| `next_step` | resubmit with `confirmed=true, plan_id=<plan_id>` |

The message names the deletion upper bound as a number, for example "may delete up to 8
analyses across 3 words", even when it is 0 (FR-013, SC-003).

### Response: filing run started

| Key | Present when |
|---|---|
| `run_id`, `stage`, `record_dir`, `scope_fingerprint` | always (CP3 shape) |
| `filing` | `"started"`; read-only runs carry `"not_requested"` |
| `backup` | `{path, created: true, note?}`, **naming the location** (FR-009) |
| `no_recovery_warning` | when no backup was taken. Data-model section 8 wording, with the Send/Receive route appended when applicable |
| `shared_mode_advisory` | `open_shared` (FR-030) |
| `stale_lock_advisory` | `stale_lock` (reused text) |
| `plan_id` | always |

A read-only run (`apply` absent or false) returns exactly CP3's shape, except that
`filing` is now `"not_requested"` instead of the old not-reachable sentence.

### Reading a filing run back

`flextools_parse_status`, `flextools_parse_log` and `flextools_parse_diff` are
unchanged, and **they never refuse on the filing claim**, because they read disk
(FR-027). `parse_log`'s `summary` section gains a `filing` block, which is the `meta.json`
filing section ([data-model section 7](../data-model.md)). Its `results` section is
unchanged. The pre-deletion captures are served by a new `parse_log` section `deletions`.
The section list is additive:

```
summary | config_generation | hc_stdout | hc_output | trace | words | results | deletions
```

For a read-only run, `deletions` returns the typed not-applicable response, naming
"filing runs only". It is never empty (CP3 FR-028's rule).

### `flextools_parse_cancel` (new, small)

Cancelling a filing run uses the runner's existing `ParseRunner.cancel_run`
(`runner.py:810`). **No MCP tool calls `cancel_run` today**, and FR-034 requires
cancellation.
- `flextools_parse_status` is annotated read-only (the default annotation,
  `tool_definitions.py:87`). Giving it a cancel action would change what that
  annotation means, which callers can see. So cancellation is a **new tool**, and the
  addition is additive.
- **Annotations**: `readOnlyHint=False, destructiveHint=False, idempotentHint=True,
  openWorldHint=False`. Stopping a job writes nothing to the project.
- **Argument**: `run_id` (required).
- **Results**:
  - an unknown run gives `parse_run_not_found` (existing);
  - an already-terminal run gives `parse_job_cancelled` (existing, `RunAlreadyTerminal`);
  - otherwise the result is `{run_id, cancel_requested: true}`.
- It **works on read-only batch runs too**. That is not a new capability: the runner
  already supports it, and the tool only exposes it.
- The run stops at a word boundary (`runner.py:657`). The filing section then reports
  `state: "cancelled"`, `filed_words`, and the not-undoable wording (FR-034).

## 2. Refusal codes

Two new codes, added **additively**. The contract stays `tool-responses/1.0`, and the
documented code count in `docs/TOOL-CONTRACT.md` rises by exactly two. Take the count
from the live file at implementation time; it was 32 when this was written. There is one
`CHANGELOG.md` entry under **"Tool contract"** (FR-035).

Each detail model uses `ConfigDict(extra="forbid", populate_by_name=True)` and a `Literal`
`error_code`. It is appended to `AnyDetail` and given a doc row plus a golden fixture in
`tests/golden/responses/<code>.json`.

**Detail fields, in this exact order:**

| Code | Fields, in order |
|---|---|
| `parser_filing_in_progress` *(verbatim)* | `run_id` (required str), `started_at` (required str, ISO-8601 UTC), `words_completed` (required int), `hint` (required str) |
| `grammar_load_unclean` *(verbatim)* | `signal` (required: `morpher_null` \| `new_load_errors` \| `eligible_forms_dropped`), `new_error_count` (required int), `baseline_error_count` (required int), `baseline_source` (required: `this_run` \| `prior_run:<run_id>` \| `absent`), `log_path` (str or null), **then, appended after the parent's five**: `new_errors` (list), `dropped_entries` (list of `{entry_guid, headword}`), `baseline_eligible_count` (int or null), `eligible_count` (int or null) |
| `parser_agent_missing` | **existing, unchanged** |

Notes:
- `eligible_forms_dropped` is the new signal value FR-039 requires the plan to name. It is
  an additive enum extension.
- The four appended fields keep parent section 14's five-field order as a strict
  **prefix**. The parent spec's row gets the same additive extension (Phase 7).
- `baseline_source` is a pattern, not a closed enum: `^(this_run|absent|prior_run:[0-9a-f]{32})$`.
- `grammar_load_unclean`'s `hint`-equivalent is in `message`. For `new_load_errors` and
  `eligible_forms_dropped` it MUST name the only escape: "run a read-only
  flextools_parse_text of the same scope, which re-baselines" (FR-021). There is no
  override argument.
- `parser_filing_in_progress.hint` points to `flextools_parse_status(run_id=...)`.

## 3. Wording

This is transcribed in [data-model section 8](../data-model.md) and not repeated here.
Tests assert those strings byte-for-byte.

**Forbidden in any filing output** (FR-033, CP3 FR-042), asserted by a scan of every
emitted response and every `meta.json`:

```
tacit   unreviewed   auto_approved   auto-approved
```

## 4. Fixed values

| Thing | Value |
|---|---|
| Live gate env var | `FLEXLIBS_REQUIRE_LIVE=1` *(verbatim)*. When set, a live-marked filing test that cannot find FieldWorks or its disposable project **fails** instead of skipping |
| Named live edge case | `MoveConcAnnotationsToWordform` *(verbatim)* |
| Filing worker role | `FILING_ROLE` (new, beside `SHARED_ROLE`/`MEASUREMENT_ROLE`) |
| Plan id | sha256, 64 lowercase hex |
| Artifact roots | `~/.flextoolsmcp/backups/...` and `get_record_dir()`. **Never inside a project folder** (FR-042) |
| Send/Receive marker | `<projects>/<P>/.hg` is a directory |
