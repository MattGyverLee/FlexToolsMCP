# Quickstart: validating parser-check CP4

**Date**: 2026-09-23 · **Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md)

These are runnable validation scenarios. Each one names the success criteria it
discharges. Shapes are in [`data-model.md`](./data-model.md); strings are in
[`contracts/tools.md`](./contracts/tools.md).

---

## Prerequisites

| | |
|---|---|
| OS | Windows with FieldWorks installed (live). Any platform for the offline suite |
| Library floor | `pyflexicon >= 4.9.0, < 5` (the parser facade `ParseWord` returns the raw `ParseResult`, R-04) |
| Source project | `IndonesianHC-Complete` (correctness), `Malay Parsing-20230810withHC` (scale) |
| **Never** | a working project in place (FR-037). `Sena 3` is excluded, because it uses the XAmple engine |
| Live gate | `FLEXLIBS_REQUIRE_LIVE=1` makes a missing live prerequisite **fail**, not skip |

### Disposable copy (every live scenario)

```bash
python tests/live_support/make_disposable.py --from "IndonesianHC-Complete" --as "CP4-Scratch-IndonesianHC"
# copies <projects>/IndonesianHC-Complete/ to <projects>/CP4-Scratch-IndonesianHC/,
# renaming the .fwdata. It refuses if the target exists, and it deletes .hg in the copy
# so that the copy is never Send/Receive-capable.
```

The helper and its teardown (`--delete`) are Phase 1 deliverables. Every evidence
artifact goes to `specs/parser-check-cp4/evidence/`, **never** into a project folder
(FR-042).

---

## Offline suite

```bash
pytest tests/ -q                                         # full suite (SC-010)
pytest tests/test_issue55_write_safety_ladder.py -q      # run_module ladder unchanged by the extraction
pytest tests/ -k "filing" -q
pytest tests/test_parse_no_project_writes.py tests/test_parse_no_edit_blocking.py tests/test_cp1_boundary.py -q
```

---

## L-0 -- Can two processes hold one non-shared project? (R-10, blocks FR-027 on non-shared)

1. Take a disposable copy. Record the sha256 and mtime of its `.fwdata`.
2. Open it with the read worker (`try_word`). Then open it writable in a second process
   through the filing worker's open. Record:
   - whether a `.fwdata.lock` appears, and with which PID;
   - whether either open fails.
3. File one word. Close the filing worker. Then **release the read worker**.
4. Is the filed analysis still in the `.fwdata`? Did the read worker's release rewrite
   the file? Compare hash and mtime.
5. Repeat step 3 on the XAmple-refusal path to root-cause the memory-noted save.

**Record**: `evidence/l0-coexistence.json`. **Outcome decides**: drop the interim
restriction on reads (R-10), or stop as `needs_human` for a maintainer amendment of
FR-027.

## Scenario 1 -- The preview writes nothing (US1; SC-001, SC-003)

1. Write-disabled session: `flextools_parse_text(scope_kind="text", scope_value=<t>,
   apply=true)` returns `server_state_error` / `write_disabled`, and no parse is started.
2. `flextools_start(write_enabled=true)`, then the same call. It returns
   `confirmation_required`, and `plan.deletion_projection.upper_bound == 0` on a copy
   never parsed live.
3. The `.fwdata` sha256 is identical before and after both calls.

## Scenario 2 -- The projection is the conjunction, and it is an upper bound (US1, US5; SC-002)

1. On the copy, seed 12 parser-evaluated, user-`noopinion` analyses. Put 4 of them in a
   text segment: 2 directly, 2 **through a gloss**. Seed 1 human-made, unevaluated,
   unused analysis. This is R-01's trap.
2. Preview. The expected upper bound is 8 + 1 = 9. None of the 4 in-text analyses are in
   it.
3. Confirm with the `plan_id`. After the run:
   - `actual_deletions` is a subset of the projection;
   - every deleted analysis has a `pre_deletion` line in `deletions.jsonl`;
   - the 4 in-text analyses survive, now with a user approval (FR-036 auto-approval
     survival).

**Record**: `evidence/s2-projection-vs-actual.json`, `evidence/s2-auto-approval-survival.json`.

## Scenario 3 -- A human disapproval gets overwritten (D-2; SC-011)

1. Mark one in-text analysis `disapproves` by the user.
2. Preview. `disapproval_overwrites.count == 1`, and it is not folded into
   `in_use_approvals_projected`.
3. File. `disapprovals_overwritten` lists it, with the prior evaluation captured.

## Scenario 4 -- The gate refuses (US3; SC-005)

1. Run a read-only `parse_text` of the scope. This records the baseline.
2. (a) Give one allomorph an invalid shape that the loader rejects and logs. The preview
   returns `grammar_load_unclean` / `new_load_errors` with
   `baseline_source=prior_run:<id>`.
3. Revert. Re-baseline. (b) Empty one entry's only lexeme form. The preview returns
   `eligible_forms_dropped`, and `dropped_entries` names it. This is D-1's silent path.
4. (c) Preview clean, then break the grammar, then confirm. The confirmed call refuses.
5. (d) Confirm clean, then break the grammar while the job runs. The run ends
   `refused_midrun`, the words filed so far are reported, and nothing asks for input.

**Record**: `evidence/s4-refuse-to-file.json` (FR-036).

## Scenario 5 -- Backup outcomes (US2; SC-004)

1. Default config: the plan says `will_be_taken`, and the result names a path under
   `~/.flextoolsmcp/backups/`. That path is **not** under the project folder.
2. `flextools_manage_config set backup_before_write false`: the plan says
   `disabled_by_configuration`. The result and `meta.json` carry the no-recovery warning.
3. `flextools_manage_config set require_write_confirmation false`: filing **still**
   returns `confirmation_required`. The plan discloses the setting (SC-008).

## Scenario 6 -- Concurrency (US4; SC-006, SC-007)

1. Start a filing run on the Malay copy. Immediately submit a second `apply=true` call.
   It returns `parser_filing_in_progress` in under 1 s, with all four fields.
2. While the run is going, call `try_word` on the same project. It answers before the run
   ends on a project with sharing on. On a project with sharing off it is refused at once
   (FR-027 as amended after L-0); see
   L-0.
3. Kill the server process mid-run and restart. The startup sweep marks the run
   `crashed`, and a new filing request is not refused as in progress.

## Scenario 7 -- Live questions (US5; FR-036, FR-038)

- **Q1 `MoveConcAnnotationsToWordform`**: delete an in-segment analysis through the
  generic `Delete()` path on the copy, then record what the segment's `AnalysesRS` holds
  afterwards. Record to `evidence/q1-moveconc.json`.
- **Q2 HermitCrab agent**: on a copy whose `ActiveParser` is set to `HC` and has never
  been parsed, inspect `ICmAgentRepository` read-only. Record to
  `evidence/q2-hc-agent.json`, and write the finding into parent SPEC section 17.10.
- **Q3 staleness**: after filing one word, does `IsUpToDate()` still return true? Record
  to `evidence/q3-staleness.json`.
- **Q4 FR-038**: re-probe the installed ParserCore/HermitCrab assemblies for public
  grammar-health checkers. Record the version and finding in
  `evidence/q4-checker-reprobe.json` and in parent section 9.5.3.
- **Q5 checksum**: file a scope twice with the grammar unchanged. The second run reports
  every word `unchanged` (US2 AS-6).

## Scenario 8 -- Cancel (US2 AS-7)

Start a run and cancel it with `flextools_parse_cancel(run_id)`. The
report lists `filed_words` and says the changes cannot be undone except by restoring the
backup, or, for an S/R project, by discarding the copy and re-downloading it.
