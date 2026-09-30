# Implementation Plan: parser-check CP4 -- ParseFiler, the write ladder, and the first mutation

**Branch**: `feat/parser-check-cp4`, in its own worktree (`C:\Github\FlexToolsMCP-cp4`), branched from `origin/main` at `2aedb1d`. Planning began against `97589ea`; source line numbers below were re-checked at `2aedb1d`.

**Date**: 2026-09-23

**Spec**: [`spec.md`](./spec.md), over [`../parser-check/SPEC.md`](../parser-check/SPEC.md) sections 5.2, 12.2-12.7, 14, 15 and 16

**Predecessors**: CP1, CP2, CP2a-bridge, CP2b and CP3 have all landed. The entry gate is satisfied.

**Size**: `oversized` (projected 14 files, 40 tasks), so this is a full-tier plan (constitution: write-path work).

---

## Summary

CP4 lets `flextools_parse_text(apply=true)` file HermitCrab results into a project
through FieldWorks' own `ParseFiler`, the same filer FLEx's *Parse Words in Text* menu
uses. Before it runs, the request has to get through:
- the write ladder `run_module` already walks;
- a preview of what may be deleted, computed from the project;
- a confirmation bound to that exact preview;
- a best-effort backup;
- a gate that refuses to file against a grammar that did not load cleanly.

Nothing is written until every rung has completed and a run identifier exists.

The technical approach, in three parts:

1. **Extract, don't copy, the ladder.** Today it is inline in `handle_run_module`
   (`handlers/execution.py:~4480-4710` at `2aedb1d`). It moves to `server/write_ladder.py`, with no
   change in behaviour, and both handlers call it (R-07).
2. **Put the write spine in its own package, `server/filing/`,** run by a new
   `FILING_ROLE` worker. This is the only place a project is opened for writing. The CP3
   read spine, its worker and its standing no-write tests stay byte-for-byte as they are
   (R-09).
3. **Drive the filer headlessly** with a real, paused `IdleQueue`, pumped by hand, and
   a new filer for every word (R-03). Before each word, check the filer's own
   would-delete set against the confirmed projection. That makes "nothing is deleted
   outside the projection" something the code enforces, not something live testing
   hopes for (R-02).

Research turned up four source facts that change how the spec reads. Each is designed
for below, not glossed over:

- **CP3's deletion projection is not an upper bound** (R-01). FLEx deletes human-made,
  never-evaluated, unused analyses, and CP3's projection does not count them. CP4 reuses
  CP3's *join* and *probe* (FR-015), but not its predicate.
- **The facade reloads a stale grammar silently before every parse** (R-05). The gate
  therefore runs on *every* reload during the job, not only on the first load.
- **Config and a bare boolean can bypass confirmation today** (R-08).
  `require_write_confirmation` can be set false through `flextools_manage_config`, and
  `confirmed` is never checked against a preview. For filing, confirmation is
  unconditional and bound to a `plan_id`.
- **Two processes on one non-shared project is unverified**, and the "read-only" worker
  has been seen rewriting a project file (R-10). This is Phase 1's blocking live
  question, with a safe interim default. That default conflicts with FR-027 on
  non-shared projects. It is surfaced as maintainer decision M-1, not absorbed.

No new language, dependency or storage is introduced. The reference sets named for
pythonnet are already loaded by the worker for the parser facade, apart from `FwUtils`
(the home of `IdleQueue`), which ships in the same FieldWorks directory.

---

## Scope fence

| Not in this slice | Where | Why |
|---|---|---|
| Merging parser morphology into gloss-only analyses | parent 17.6 | Disclosed as a count (FR-016), not built |
| Filing the lowercase form of a capitalised word | follow-up | R-06. It would delete outside the projection; the divergence is disclosed |
| Any bypass: `force`, `skip_confirmation`, unattended or scheduled filing | never | FR-004, SC-008. Pinned by a surface-enumeration test |
| Coordinating with FLEx's own parser | out | Disclosed through the shared-mode advisory (FR-030) |
| Undo of a filing run | out | Restore the backup (non-S/R), or discard and re-download (S/R). Named, never automated |
| Creating a missing HermitCrab agent | out | Refuse (spec Assumptions). The live finding Q2 may justify a follow-up |
| Sandbox spine, telemetry, user docs | CP5, CP6 | -- |
| Documenting `confirmation_required`'s detail model | CP6 | That code is emitted today with no row in `docs/TOOL-CONTRACT.md`. It is a pre-existing gap, noted here and not widened |
| Editing issue #165's text | human | Outward-facing. See M-2 |

---

## Technical Context

| | |
|---|---|
| **Language/Version** | Python 3.11+ for the server and workers; pythonnet for the filing worker |
| **Primary Dependencies** | `pyflexicon >= 4.9.0, < 5`: `project.Parser.ParseWord` returns the raw .NET `ParseResult` (R-04). FieldWorks `ParserCore.dll`, `FwUtils.dll` (`IdleQueue`), `SIL.LCModel*`. `pydantic` v2 detail models |
| **Storage** | CP3 run records under `record.get_record_dir()`, plus a `filing` section in `meta.json` and a new `filing/deletions.jsonl` per run. Backups under `~/.flextoolsmcp/backups`. **Nothing inside a project folder** (FR-042) |
| **Testing** | `pytest`. The offline suite is the default. `requires_flex` live groups run against **disposable copies** only (FR-037). `FLEXLIBS_REQUIRE_LIVE=1` turns a missing live prerequisite into a failure |
| **Target Platform** | Windows with FieldWorks 9 |
| **Constraints** | No project-wide claim (FR-027). The ladder completes before the `run_id` exists (FR-003). The contract stays `tool-responses/1.0`. The read spine is unchanged |
| **Scale/Scope** | One extended tool, one new small tool (`flextools_parse_cancel`), two new codes plus one enum value, one extracted module, one new package of about 9 modules |

---

## Constitution Check

*GATE: must pass before Phase 0 research, and is re-checked after Phase 1 design.*

| Principle | Assessment |
|---|---|
| **I. Safety-First Write Path** (NON-NEGOTIABLE) | **PASS, and strengthened.** Read-only by default (`apply=false`). Session `write_enabled` is required, with no per-call override (R-15). Confirmation is **unconditional** for filing and bound to a `plan_id` (R-08). The preview is the dry run (FR-005). Backup is **best-effort and never raises**, which is the resolution the spec clarification chose, with a no-recovery-point warning. Nothing asks for a decision mid-job (FR-003, FR-024). Unattended live writes stop as `needs_human` (the `lex-verification` hook). The limit is stated honestly: `plan_id` proves the preview was *issued and unchanged*, not that anyone *read* it. This is a safety property, not a security boundary. `if modifyAllowed:` guarding is N/A: filing runs MCP-owned code, not a user script |
| **II. Discovery Over Memory** | **PASS / N/A.** No generated module changes. Every LCM and ParserCore member the filing worker binds is capability-probed, not assumed (R-03) |
| **III. Self-Contained, Regenerable Extraction** | **PASS / N/A.** No extractor or index change. pyflexicon is unchanged, so memory note `release-order-flexicon-first` does not apply |
| **IV. Append-Only Versioned Contracts** | **PASS.** Two codes, one enum value, four detail fields *appended* after the parent's five (a strict prefix), one parse_log section and one tool, all additive. One CHANGELOG entry under "Tool contract" |
| **V. Errors That Teach** | **PASS.** Every refusal names the next call: re-baseline with a read-only parse (FR-021), `flextools_parse_status(run_id)` for an in-progress run, `flextools_start(write_enabled=true)`, the enable-sharing remedy |
| **VI. One Module, One Source of Truth** | **PASS with one justified violation.** The ladder is *extracted* (R-07), not copied. **Violation**: `filing/eligibility.py` ports two private `HCLoader` predicates. See Complexity Tracking; it is pinned by a live parity test |
| **VII. Windows-First** | **PASS.** Windows-only pythonnet in the worker. Live tests are marked and deselectable. Console text is ASCII. Worker stdio is UTF-8 (existing) |

**Quality gates.**
- *Pattern audit*: four sweeps are scheduled; see Test strategy.
- *Live verification*: mandatory, on disposable copies (Phase 8).
- *Merge requirements*: CHANGELOG, golden fixtures for the two codes, integrity
  validator, lint.

**Post-design re-check (after Phase 1).**
- There is no change from the table above.
- The design adds exactly one place that opens a project for writing
  (`filing/worker_filing.py`). It is pinned by an inverse structural test, so a second
  one cannot appear unnoticed.
- The one tension the design created, R-10's interim read refusal on non-shared projects
  during filing, is **not** a constitution violation. It errs toward safety. It is a
  *spec* conflict (FR-027), and it is escalated as M-1.

---

## Project Structure

### Documentation (this feature)

```text
specs/parser-check-cp4/
├── plan.md              # This file
├── spec.md              # Already written (clarified)
├── research.md          # Phase 0 -- R-01..R-16
├── data-model.md        # Phase 1 -- plan, projection, gate, filing record
├── quickstart.md        # Phase 1 -- L-0 and scenarios 1-8
├── contracts/
│   └── tools.md         # arguments, check order, two codes, new tool
├── checklists/
│   └── requirements.md  # Already written
├── evidence/            # Phase 8 live artifacts (FR-036)
└── tasks.md             # /speckit.tasks -- NOT created here
```

### Source Code

```text
src/flextoolsmcp/server/
├── write_ladder.py                 # NEW -- extracted rungs: probe_write_access, backup_intent, take_backup (R-07)
├── filing/                         # NEW package -- the ONLY write spine
│   ├── __init__.py
│   ├── claims.py                   # in-process per-project claim + startup sweep (R-11)
│   ├── plan.py                     # build_plan, canonical JSON, plan_id (R-08)
│   ├── projection.py               # deletion_upper_bound on FR-011's two conjuncts (R-01)
│   ├── gate.py                     # find_baseline, load-error diff, eligibility diff (R-12)
│   ├── eligibility.py              # port of IsValidLexEntryForm / HasValidRuleForm (R-12)
│   ├── paths.py                    # assert_outside_project; Send/Receive detection (R-14)
│   ├── filer.py                    # per-word ParseFiler + paused IdleQueue pump (R-03)
│   ├── classify.py                 # before/after per-word outcome, R-02 guard, captures
│   └── worker_filing.py            # FILING_ROLE entry: writable open, gate on every reload (R-05)
├── parse/
│   ├── stages.py                   # + FILING edges only for filing runs (data-model section 10)
│   ├── record.py                   # + `filing` meta section, deletions.jsonl, eligible_entries in baseline
│   ├── runner.py                   # + filing=True submission, claim release on terminal, read-worker recycle
│   ├── worker_client.py            # + FILING_ROLE
│   └── worker_main.py              # + read-only `filing_preview` message (fresh join, eligibility, stored analyses)
├── signals/projections.py          # docstring line only: "not the filing bound" (R-01)
├── handlers/
│   ├── parse.py                    # + apply/confirmed/plan_id path; + handle_flextools_parse_cancel
│   └── execution.py                # run_module refactored onto write_ladder (no behaviour change)
├── session.py                      # + filing_plans, filing_backed_up_projects
├── models.py                       # + three ParseTextInput fields; + ParseCancelInput
├── response_models.py              # + ParserFilingInProgressDetail, GrammarLoadUncleanDetail
├── tool_definitions.py             # parse_text description line 1; + parse_cancel ToolDef
├── dispatch.py                     # + parse_cancel route
└── (startup)                       # + filing claim sweep, beside the existing lock sweep

docs/TOOL-CONTRACT.md               # +2 code rows; count +2
CHANGELOG.md                        # one "Tool contract" entry
specs/parser-check/SPEC.md          # 12.2 correction (D-2); 12.4 "best-effort"; 14 row extension; 17.10 and 9.5.3 findings
specs/parser-check-cp3/contracts/artifact.md   # additive: eligible_entries; filing section; deletions.jsonl

tests/
├── test_write_ladder_extraction.py         # run_module unchanged; ladder leaves called once each
├── test_filing_projection.py               # R-01 trap; the gloss path; unknown counted in the bound
├── test_filing_plan_binding.py             # plan_id required; recompute mismatch -> re-preview (FR-006)
├── test_filing_bypass_surface.py           # SC-008 enumeration; require_write_confirmation=false still confirms
├── test_filing_gate.py                     # morpher_null, new errors, eligibility drop, absent baseline, FR-023
├── test_filing_eligibility.py              # the port's rules, one fixture per branch
├── test_filing_claims.py                   # FR-026/027/028; sub-second refusal; crash sweep
├── test_filing_ladder_order.py             # check order of contracts section 1; nothing before the claim
├── test_filing_backup.py                   # intent == outcome; the no-recovery warning; S/R wording; FR-042
├── test_filing_filer_pump.py               # paused IdleQueue fake; declined -> filer_declined; per-word filer
├── test_filing_classify.py                 # counts; R-02 outside_projection; captures written before the pump
├── test_filing_record.py                   # meta filing section; forbidden-word scan; D-2 list
├── test_filing_write_confinement.py        # INVERSE: writeEnabled=True appears only in filing/worker_filing.py
├── test_filing_cancel.py                   # word-boundary stop; filed_words; wording
├── test_parse_text_handler.py              # EXISTS -- schema/first-line/filing assertions updated (R-16)
├── test_parse_no_project_writes.py         # EXISTS -- scan set unchanged; FILING narrowed per run (R-16)
├── test_parse_no_edit_blocking.py          # EXISTS -- + filing/claims.py
├── test_issue55_write_safety_ladder.py     # EXISTS -- must pass unmodified (the extraction's proof)
├── test_response_contract.py / test_parser_error_models.py   # EXIST -- count +2, field-order rows
└── test_parse_live_cp4.py                  # requires_flex; disposable copies; FLEXLIBS_REQUIRE_LIVE
tests/live_support/make_disposable.py       # NEW -- copy/teardown helper (FR-037)
```

**Structure Decision.** The write spine is a sibling package, `server/filing/`, and not
an extension of `server/parse/`. The line between them is the same line FR-029 draws:
- `parse/` and `signals/` keep a standing structural proof that they never write;
- `filing/` is the one place a write may happen, pinned by an inverse test.

The ladder moves into `server/write_ladder.py`, because two handlers now share it and
neither owns it.

---

## Implementation phases

These are ordered by dependency and risk. Each phase names its exit condition.

### Phase 1 -- The live questions that can move the design (R-10, R-13)

- **L-0 coexistence**, including the root cause of the read-worker save. This one
  **blocks Phase 5 merging**.
- **Q2** (HermitCrab agent), **Q3** (staleness after a filed word), **Q5** (checksum
  parity).
- The `tests/live_support/make_disposable.py` helper.

Every run is on a disposable copy, with evidence under `evidence/`. Q1 and Q4 are
evidence-only and can run in Phase 8.

*Exit*:
- `evidence/l0-coexistence.json` exists;
- R-10's interim default is either dropped or escalated (M-1);
- Q2, Q3 and Q5 are recorded;
- the Q2 finding is written into parent section 17.10.

### Phase 2 -- Extract the ladder (FR-002, R-07)

`write_ladder.py` gets `probe_write_access`, `backup_intent` and `take_backup`.
`handle_run_module` is rewritten to call them.

*Exit*: `test_issue55_write_safety_ladder.py`, the `test_shared_mode_*` tests,
`test_issue92_write_path_e2e.py` and `test_async_locking.py` all pass **without any
modification**. The golden responses for `confirmation_required` and `project_locked`
are byte-identical.

### Phase 3 -- The contract (FR-035) and the surface (FR-001, FR-004)

- Two detail models, doc rows, golden fixtures and the CHANGELOG entry.
- The `ParseTextInput` fields and the description's first line.
- `flextools_parse_cancel`.
- The R-16 updates to existing tests.
- `test_filing_bypass_surface.py`, written **before** the handler exists, so that it
  fails if a bypass-shaped name ever appears.

*Exit*:
- the contract tests are green at the new count;
- the surface test is green;
- `apply=false` responses are unchanged apart from `filing: "not_requested"`.

### Phase 4 -- The preview: projection, gate and plan (US1, US3; FR-005, FR-010..FR-016, FR-020..FR-023, FR-025, FR-039, FR-040)

`filing/projection.py` comes first, with R-01's trap fixture written **red** before the
function exists. The trap is the natural implementation: call CP3's projection.

Then:
- the `filing_preview` read-only worker message, with a fresh join (R-02);
- `eligibility.py`, `gate.py` (the baseline lookup by `created_at`, R-12) and `plan.py`
  (canonical JSON and `plan_id`);
- the additive `eligible_entries` key written by every batch run.

*Exit*: SC-001 offline (sha256 identical across an unconfirmed request), SC-003 and the
SC-005 preview variants are green.

### Phase 5 -- The ladder walk and the claim (US2, US4; FR-003..FR-009, FR-026..FR-030, FR-042, FR-043)

- The check order of `contracts/tools.md` section 1, enforced by `test_filing_ladder_order.py`
  with boom-stubs on everything after each refusal (the `_boom_lock` pattern). The
  rung order is `run_module`'s, literally: an unconfirmed request against an
  exclusively-held project gets `confirmation_required`, not `project_locked`.
- `claims.py` and the startup sweep.
- The backup rung with its separate session key.
- `paths.py`: the confinement check and Send/Receive detection.

*Exit*: SC-004, SC-006 and SC-008 are green offline, and L-0's outcome is applied.

### Phase 6 -- The filing worker (US2; FR-017..FR-019, FR-024, FR-031, FR-034, FR-041)

- `worker_filing.py`: a writable open, the agent resolved by GUID, and the gate re-run on
  every reload (R-05). At teardown it reuses #147's `RefreshFromDisk`-before-`CloseProject`
  step (`106a2ff`), gated on the same flexicon capability, rather than writing its own.
- `filer.py`: a per-word filer and a paused-queue pump (R-03).
- `classify.py`: the R-02 guard, then the captures (written *before* the pump), then the
  pump, then the before/after classification.
- Cancellation at a word boundary.
- `stages.py`'s per-run FILING edges.

*Exit*: every `test_filing_*` offline test is green, run against a fake CLR surface.

### Phase 7 -- The record and the corrections (US6; FR-032, FR-033, FR-041)

- The `meta.json` filing section, `deletions.jsonl`, and the `deletions` parse_log
  section.
- The forbidden-word scan.
- Parent-spec corrections:
  - 12.2, D-2 ("filing *does* overwrite an in-use human disapproval");
  - 12.4 (backup is best-effort, per the clarification);
  - 14 (the row extension);
  - 9.5.3 (the FR-038 finding).
- CP3's artifact contract, amended additively.

*Exit*: SC-011's offline half is green, and all corrections are committed.

### Phase 8 -- Live verification (US5; FR-036..FR-038, SC-002, SC-009, SC-011)

Quickstart scenarios 2-8 run on disposable copies of `IndonesianHC-Complete`
(correctness) and `Malay Parsing-20230810withHC` (scale). Five evidence artifacts, one
per FR-036 case, plus Q1 and Q4. Run under `FLEXLIBS_REQUIRE_LIVE=1`.

*Exit*: SC-002, SC-009 and SC-011 are observed live. The full suite (SC-010) is green.
**If no human is present, this phase stops as `needs_human` and does not perform the
writes** (constitution I; the `lex-verification` hook).

---

## Test strategy

The `lex-qc` plan gate asks for coverage that is *scheduled*, not merely asserted. Every
FR has a row.

| Requirement | Proof (the wrong implementation fails) | Where |
|---|---|---|
| FR-001 apply absent is unchanged; annotation unchanged | read-only response diffed against the CP3 golden, except `filing`; annotations pinned | `test_parse_text_handler.py` |
| FR-002 same rungs, reused | ladder leaves patched and called exactly once each from both handlers; no copy of the rung code in `handlers/parse.py` (AST check for `probe_project_access` calls outside `write_ladder.py`) | `test_write_ladder_extraction.py` |
| FR-003 rungs before the run id | `start_run` boom-stubbed until the last rung; the run id is absent from every refusal | `test_filing_ladder_order.py` |
| FR-004 / SC-008 no bypass | schema and config enumeration; `require_write_confirmation=false` **still** returns `confirmation_required` | `test_filing_bypass_surface.py` |
| FR-005 / SC-001 preview writes nothing | fixture `.fwdata` sha256 identical; no backup dir created; the filing worker never spawned | `test_filing_ladder_order.py` + live S1 |
| FR-006 plan binding | `confirmed=True` with no or a foreign `plan_id` re-previews; a recompute mismatch re-previews | `test_filing_plan_binding.py` |
| FR-007 / SC-004 backup best-effort, intent stated | disk-full and opt-out fixtures: the run proceeds, intent == outcome, the warning is present in the response and in meta | `test_filing_backup.py` + live S5 |
| FR-008 separate key; before the writable open | a `run_module` backup does not satisfy filing; backup timestamp < filing worker spawn | `test_filing_backup.py` |
| FR-009 location or warning | a path is present, or the verbatim warning is | `test_filing_backup.py` |
| FR-010 plan fields | every data-model section 2 key present | `test_filing_plan_binding.py` |
| FR-011 / FR-012 conjunction, disapproved excluded | **R-01 trap**: a human-made unused analysis is counted; the gloss path is shielded; disapproved is excluded. CP3's predicate fails this fixture | `test_filing_projection.py` (red first) |
| FR-013 concrete per wordform, including 0 | a never-parsed fixture gives `upper_bound == 0` and `by_wordform == {}` | `test_filing_projection.py` |
| FR-014 upper bound | R-02: a word whose live would-delete set exceeds the projection is skipped `outside_projection`, **nothing filed** | `test_filing_classify.py` + live S2 |
| FR-015 reuse of the join and probe | `projection.py` imports `oracle.segment_occurrence` and `project_state.probe_project_state`; there is no second traversal | `test_filing_projection.py` (import assertion) |
| FR-016 duplicate disclosure | CP3 `duplicate_projection` output carried through | `test_filing_plan_binding.py` |
| FR-017 errored words | an error result is filed; `errored_words` and `errored_word_deletions` are counted separately; try-word never files (structural) | `test_filing_classify.py`, `test_parse_no_project_writes.py` |
| FR-018 real filer, real queue | a fake `IdleQueue` asserts `IsPaused=True` and non-null; the agent comes from the HC GUID; the handler is non-null | `test_filing_filer_pump.py` |
| FR-019 liveness, decline | invalid result gives `invalid_object`; `Delegate` returning False gives `filer_declined`, and the **next word does not file it** (per-word filer) | `test_filing_filer_pump.py` |
| FR-020 morpher null | a `None` parse gives `morpher_null`, with no override path | `test_filing_gate.py` |
| FR-021 new errors, escape named | 3 then 5 gives `new_error_count=2`; the message names the read-only re-baseline | `test_filing_gate.py` |
| FR-022 pre-existing / absent | first run: every error pre-existing, `baseline_source="absent"` | `test_filing_gate.py` |
| FR-023 never FLEx's file as prior | a stale `HCLoadErrors.xml` with a foreign mtime plays no part | `test_filing_gate.py` |
| FR-024 three points + every reload | the gate refuses at preview, at confirm, and on a mid-run reload (`refused_midrun`, nothing asked) | `test_filing_gate.py`, live S4d |
| FR-025 agent probe first | a missing agent gives `parser_agent_missing` before the preview; a `KeyNotFoundException` at GUID lookup is mapped | `test_filing_ladder_order.py` |
| FR-026 / SC-006 in progress | the second request is refused with 4 fields in < 1 s, before the engine check (boom-stub) | `test_filing_claims.py` |
| FR-027 / SC-007 no project-wide claim | try-word proceeds while the claim is held (shared, and non-shared if L-0 passes); forbidden names absent | `test_filing_claims.py`, `test_parse_no_edit_blocking.py` |
| FR-028 clears on any terminal state | success, refusal, cancel, worker crash, server-crash sweep | `test_filing_claims.py` |
| FR-029 read tools stay read-only | the existing scan is **unchanged** and green; inverse confinement test | `test_parse_no_project_writes.py`, `test_filing_write_confinement.py` |
| FR-002 rung order / FR-030 shared / exclusive | unconfirmed + `open_exclusive` gives `confirmation_required` (plan `access` names the remedy); **confirmed** + `open_exclusive` gives `project_locked`; `unknown` gives `project_drive_unavailable`; `open_shared` proceeds with the verbatim advisory in plan and result | `test_filing_ladder_order.py` |
| FR-031 pre-deletion capture | the capture line is written **before** the pump (ordering asserted on the fake) | `test_filing_classify.py` |
| FR-032 record counts | every count key present; projected beside actual | `test_filing_record.py` |
| FR-033 wording | the verbatim sentence; forbidden-word scan over responses and meta | `test_filing_record.py` |
| FR-034 persist; cancel | cancel stops at a boundary; `filed_words` matches; not-undoable wording | `test_filing_cancel.py` + live S8 |
| FR-035 contract | count +2, field order equal to the contract row, goldens, CHANGELOG | `test_response_contract.py`, `test_parser_error_models.py` |
| FR-036 / SC-009 five live cases | five evidence files | `test_parse_live_cp4.py` |
| FR-037 disposable copies | the live fixture refuses a project name without the `CP4-Scratch-` prefix | `test_parse_live_cp4.py` |
| FR-038 re-probe | evidence file plus parent 9.5.3 edit | live Q4 |
| FR-039 eligibility drop | an emptied lexeme form gives `eligible_forms_dropped` and names the entry; a load-error-only gate **passes** this fixture and so fails the test | `test_filing_gate.py`, `test_filing_eligibility.py` |
| FR-040 / SC-011 disapproval projection | a separate count, not folded into in-use approvals | `test_filing_projection.py` + live S3 |
| FR-041 overwrite list | the prior evaluation captured; parent 12.2 corrected | `test_filing_record.py` |
| FR-042 nowhere in project folder | `FLEXTOOLSMCP_PARSE_RECORD_DIR` set inside a project folder is refused; the backup path is outside | `test_filing_backup.py` |
| FR-043 S/R route | a `.hg` fixture gives the verbatim route in plan and warning; `unknown` treated as S/R | `test_filing_backup.py` |
| Eligibility port parity | the port's count equals the loaded grammar's entry count | `test_parse_live_cp4.py` |

**Wrong-implementation tripwires.** Five tests are written so that the tempting
implementation fails, not just disagrees:
- **R-01's trap**: reusing CP3's projection.
- **FR-039's silent-drop fixture**: a load-error-only gate.
- **FR-019's declined-then-next-word fixture**: a single long-lived filer.
- **FR-006's foreign `plan_id`**: a bare `confirmed` flag.
- **FR-002's locked-and-unconfirmed request**: refusing on the lock before confirming, which is the order this plan first had and the QC gate caught.
- **SC-008's `require_write_confirmation=false`**: honouring the config for filing.

**Pattern-audit obligations.** Each shaped class gets a sweep, not a point fix:

1. **A proxy predicate that under-counts a C# predicate** (R-01: `is_human_record` as a
   stand-in for "deletable"). Sweep: where else does MCP code approximate an LCM or
   ParserCore decision with a related-but-different field test?
2. **A worker-lifetime cache consulted for a safety decision** (R-02: the cached segment
   join). Sweep: other per-worker or per-session caches read by a gate.
3. **A config key that can lower a safety rung** (R-08: `require_write_confirmation`
   through `manage_config`). Sweep: every `config_get` in `src/` (re-grepped at
   `2aedb1d`):
   - the gate-consuming calls: `execution.py:4537` (`REQUIRE_WRITE_CONFIRMATION_KEY`),
     `execution.py:4547` and `backup.py:95` (`BACKUP_BEFORE_WRITE_KEY`), and
     `backup.py:123` (`BACKUP_RETENTION_KEY`);
   - reviewed, not a safety rung: `execution.py:2820` (`AUTO_FIX_ENABLED_KEY`) the three
     `diagnostic_report.py` report-key reads, and `admin.py`'s generic read inside
     `flextools_manage_config`.

   For each call, record whether lowering the key is intended. The sweep re-greps
   `config_get(` rather than trusting this list, because line numbers drift.
4. **A fail-open probe.** Upstream fixed the instance that prompted this (#118,
   `5612fc2`): an unresolvable projects directory now gives `verdict="unknown"`,
   `probed=False`, not `free`. The rest still applies:
   - filing **refuses** `unknown` with `project_drive_unavailable`. That is a disclosed
     divergence from `run_module`, which proceeds (contracts section 1, row 11);
   - sweep: other probes whose failure mode is the permissive verdict. #118 fixed one; the
     sweep asks whether it had siblings.

**Live verification.** It is mandatory (write path), on disposable copies only, with
pre/post evidence (constitution). Q0/L-0 runs **first**, because its answer can change
Phase 5.

---

## Complexity Tracking

| Violation / complexity | Why needed | Simpler alternative rejected because |
|---|---|---|
| **Principle VI**: `filing/eligibility.py` ports two private `HCLoader` predicates | FR-039 must *name* the entries the loader drops silently (D-1). The predicates are private **instance** methods that depend on mid-load state (R-12) | Reflecting on the loaded `Language` can count entries but cannot name them, and it binds a private field. Doing nothing leaves D-1's silent-shrink path open. **Mitigation**: a live parity test fails the suite if the port and the loader disagree |
| A new `server/filing/` package and worker role | FR-029 is kept as a structural fact that existing tests keep proving | A write mode inside `worker_main.py` breaks the standing no-writes test or needs an allowlist inside the file it protects |
| A new `ParseFiler` per word | A declined update would otherwise be filed silently with the next word (R-03) | A single filer re-pumped later files the word out of order and outside its own liveness check |
| Confirmation for filing ignores `require_write_confirmation=false` (a divergence from `run_module`) | SC-008 and FR-004 cannot hold otherwise, because `manage_config` flips the key freely | Honouring the key would ship a bypass on day one |
| A new tool `flextools_parse_cancel` | FR-034 needs cancellation, and no tool reaches `cancel_run` | A cancel action on `parse_status` changes the meaning of a read-only annotation, which callers can see |

---

## Risks

| Risk | Handling |
|---|---|
| **Two-process coexistence on non-shared projects** (R-10). The read worker's release could silently revert a filing | Phase 1 blocking live question. Interim default: release the read worker, and refuse reads on that project during filing. Escalated as M-1 |
| **The ladder extraction regresses `run_module`**, the one path users already rely on | Its own phase. The exit condition is the existing ladder suite **unmodified** plus byte-identical goldens |
| **The eligibility port drifts from FieldWorks** | Live parity test. Environment-dependent validity is left to the load-error diff, which does see it (R-12) |
| **Per-word re-gating is slow** if the filer's writes mark the grammar stale (Q3) | Safe by default. Fallback: a grammar change stamp in place of `IsUpToDate` (R-05) |
| **Checksum mismatch across processes** (Q5) | This only degrades the "unchanged" count to an idempotent re-file. It is reported, never hidden |
| **"Pre-existing load errors are benign" is a hypothesis** | Stated as one in the plan's `hypothesis_note`, not as a fact |
| **A human disapproval is overwritten by design** (D-2) | Projected (FR-040), listed (FR-041), and corrected in the parent spec |
| **`plan_id` proves issuance, not reading** | Stated in the contract and the plan. It is a safety property, not a security boundary (constitution I) |

---

## Open maintainer decisions

| # | Decision | Default taken so planning is not blocked | When it must be settled |
|---|---|---|---|
| **M-1** | If L-0 shows that read-only coexistence on a **non-shared** project is unsafe, reads on that project must be refused during a filing run. That contradicts FR-027 and SC-007 for non-shared projects | Apply the restriction until L-0 answers. If L-0 passes, the restriction is removed and FR-027 holds everywhere | Before Phase 5 merges. **An L-0 failure is a `needs_human` stop**, not a downgrade. **Resolved 2026-09-24:** L-0 failed (a read-only open takes the lock; a second writable open raises `FP_FileLockedError`). The maintainer amended FR-027 and SC-007: reads wait for filing on projects with sharing off, and are not blocked on projects with sharing on |
| **M-2** | Issue #165's definition of done still says "Mandatory pre-write backup". The clarification reversed that | The parent SPEC 12.4 edit is scheduled (Phase 7). The GitHub issue edit is **outward-facing** and is not done without authorisation | Before CP4 is marked complete |
| **M-3** | `flextools_parse_cancel` is a new tool rather than an action on `parse_status` | New tool (Complexity Tracking) | Before Phase 3. Overturning it later costs a caller-visible change |
