# QC doc gate — CP5 re-plan docs (research cycle 2)

Reviewer: lex-qc (read-only; saved by the main session). Scope: spec.md, plan.md,
research.md, tasks.md, data-model.md, quickstart.md, contracts/{hcparse,tools,sandbox-worker}.md
against the sandbox-in-worker design of record (R-17, D1-D8, FR-046..FR-050).

## P0

1. tasks.md:192-200 (T029) and :237-240 (T033) still assert the `dotnet tool install -g
   SIL.Machine.Morphology.HermitCrab.Tool` hint / `parser_tool_missing` with the `hc` hint (FR-007)
   with no Superseded marker, contradicting reworded FR-007 and D7. Add "Superseded ... see T105";
   audit T036-T094 for the same gap.
2. tasks.md:261-277 (T034) and :278+ (T035) describe FR-013 quoting, `-o`/`-c` hc flags, ASCII
   console output for Parse mode, and `hc-stdout.txt` timeout handling as live acceptance tests
   with no Superseded annotation.
3. (false alarm) T025's skew line is covered by a note at :172-173.

## P1

4. FR-050 shaping rules a-d have no explicit task: T096 (tasks.md:839-849) omits FormID-0 skip,
   circumfix handling, drop-on-unresolved-id and the user_added exception; T099 covers only the
   sidecar. Add an explicit task/sub-bullet with unit tests against contracts/sandbox-worker.md.
5. plan.md:171 lists contracts/hcparse.md as covering "dispatch.json" without qualifier (retired
   in hcparse.md section 4).

## P2

6. tasks.md:96 (T011) still says load `dispatch.json` tolerantly; prune to `run.json`.

## Verified OK

D1-D8 map to FR-046/047/048/050; SC-003(d) limits differences to gloss source and user_added;
CP1 amendment is a pinned allowlist; Phase 10 dependency order sane; no `worker_diagnostics`;
log section names unchanged per FR-038.
