# Doc Agent Change Log -- tasks.md, cycle 6

Applied all 15 reconciled edits from cycle-5 review (domain/programmer/qc/author) to
`specs/parser-check/tasks.md`. New tasks T029-T035 added at dependency position, not
appended; T001-T028 IDs unchanged.

- **E1** (T015, T034): row-1/6 emptiness predicate corrected to `form in (None, "", "***")`;
  added regression-guard assertion to T015 that a `"***"` stub counts as zero-surface.
- **E2** (T016, T034, T035): T016's closing clause now requires recording, per gated
  sub-check, the written-or-`checks_skipped` verdict; T034/T035 spell out both branches
  for row 3-metathesis, row 5, and row 7's `AlternateFormsOS` half.
- **E3** (T029 new, T030 new, T019/T034/T035): T029 records the import-vs-splice decision
  and corrects research D1; T030 builds the chosen seam; scan tasks now state they return
  findings via `report.Result(...)`.
- **E4** (T003, T006): T003 now extends `AnyDetail` and bumps both docstring counts to 22;
  T006 asserts through `validate_detail()`, not the bare model.
- **E5** (T009): names `ParserCore.dll` explicitly and notes the two non-shared precedents.
- **E6** (T014, T017): denylist backstop expanded (proxy + synonym words); added allowlist/
  `extra="forbid"`, order-invariance, and positive-template assertions; T017 now defines
  `GrammarHealthFinding` with the closed six-key set.
- **E7** (T031 new): reflection-only `GrammarHealthChecker` probe, placed in the Phase 4 W2
  research chain.
- **E8** (T028): enumerated the CP1-scoped SPEC 16 groups/bullets by name.
- **E9** (T008): added the named Windows+FieldWorks integration test, skip-guarded.
- **E10** (T027, moved to Phase 4 W2 `[P]`): expanded to four fixes (row 8, stale
  verified-rows note, `OrderNumber` caveat, SPEC 15 "refusal logic" reword).
- **E11** (T015, T034, Phase 4 independent-test paragraph): removed "reachable from an
  optional slot" claim in all three places; added the deferred-walk note to T034.
- **E12** (T026): restated as static-scan + dynamic-spy checks, one file.
- **E13** (T032 new): D-note for `active_engine: null`, referenced from T012.
- **E14** (T013): literal CP1 replacement action string for the read-only-Try-A-Word row;
  added the contract file to T013's path list.
- **E15** (T033 new; T019 split into T019/T034/T035): data-model.md now holds the per-row
  predicate/cast/inheritance detail; the scan module split into phonology (T019, ungated) /
  morphology (T034) / rule-ordering (T035), strictly ordered on the same file.

Dependencies & Execution Order section rewritten end to end (phase order, story
independence, per-phase wave table, ordering constraints, file-sharing invariant) to match
the target Phase 4 shape (W1 T014/T015 -> W2 research chain + T027/T033 `[P]` -> W3
T017/T018/T030/T019 -> W4 T034 -> W5 T035 -> W6 T020 -> W7 T021).

**Not applied:** none of the 15 edits were skipped. One judgment call: E14's literal
replacement string ("filing unavailable; the read spine above already confirms whether
the grammar loads") is new prose I authored to satisfy the constraint -- it is not quoted
from any existing doc, since none proposed exact wording; flag for author-voice review if
a different phrasing is preferred.
