# T034 report -- morphology rows 1, 6, 7, 10

## Rows implemented (`src/flextoolsmcp/server/scan/grammar_scan_module.py`)

- **Row 1** `zero-surface-morph-repeatable`: predicate `is_zero_surface_form(form)`
  (`is_empty_form(form.Form)`) over `project.ObjectsIn(IMoFormRepository)`, no cast
  (direct property). `measured = "{count} allomorphs have an empty surface form"`
  -- the exact contract-example wording, count-first, **no slot-reachability
  claim** ("reachable from an optional slot" does not appear anywhere in this
  row). `evidence_basis = "425x"` (data-model.md row 1). Zero-surface `IMoForm`s
  are counted unconditionally, project-wide -- no position/slot argument, no
  `AlternateFormsOS` walk.
- **Row 6** `partial-morpheme-incomplete-form`: `IMoForm.IsComplete == False`
  over the same repository walk, no cast. `measured = "{count} morphs are
  incomplete"`, `evidence_basis = "hc-partial-morpheme"`.
- **Row 7a** `stem-allomorph-stem-name-restriction`: `IMoStemAllomorph(obj)
  .StemNameRA is not None` over `IMoStemAllomorphRepository`, cast applied
  unconditionally per the row2/4/9 precedent. `evidence_basis = None` (table
  has no PanGloss figure for this row).
- **Row 7b** `multiple-allomorphs-per-entry`: `entry.AlternateFormsOS.Count >
  1` over `project.LexEntry.GetAll()`, **written per D9's CONFIRMED verdict**
  -- not routed to `checks_skipped`. No per-element cast (`.Count` is a
  collection-level read on `ILcmOwningSequence`, D9).
- **Row 10** `optional-template-slot-branching`: `is_optional_slot(slot)`
  (`.Optional`) plus a scan-level `.Affixes` non-empty check, over
  `IMoInflAffixSlotRepository`. Confirmed no `ICmPossibility` cast anywhere
  in the module (`ICmPossibility(` does not appear in source text --
  `TestOptionalTemplateSlotsRow10::test_source_never_casts_a_slot_to_icmpossibility`
  passes; had to rephrase two docstring mentions that originally spelled the
  literal cast text and tripped the same substring check on themselves).

`"***"` handling: `is_empty_form`/`is_zero_surface_form` treat `"***"` as
empty (row 1's regression guard passes). For rows where the form may be
non-empty (row 6, 7a), the raw `.Form` value is passed straight to
`_found_object`, which already normalizes `None`/`"***"` labels to `""`
(pre-existing helper, unchanged) -- so no row re-implements that normalization.

All four rows wired into `run_grammar_scan` at their marked row-order slots;
no other function's structure changed. T035's rows 3/5/8 markers untouched.

## Before/after

`pytest tests/test_grammar_scan_checks.py tests/test_grammar_health.py -q`:
before **20 failed / 73 passed**, after **11 failed / 82 passed**. All 9
newly-green tests were T034's (6x `TestZeroSurfaceMorphRow1`, 3x
`TestOptionalTemplateSlotsRow10`); `test_grammar_scan_checks.py` is now
fully green (0 failures). The remaining 11 are all in `test_grammar_health.py`:
10 require `server.handlers.grammar_health._assemble_findings` (T020, not
yet written) and 1 (`test_example_measured_matches_the_factual_count_based_template`)
is a pre-existing mismatch between the contract doc's own JSON example
wording and its regex checker, unrelated to any scan-module code path --
present before and after this task's changes, not fixable within T034's
scope (contract doc is off-limits here).

`ruff check` on the module: all checks passed.

Full suite (`pytest tests/ -q`): 18 failed / 1601 passed / 9 skipped -- the
11 above plus 7 pre-existing `test_parser_health_block.py` failures (T013,
in flight, expected RED per task brief). `tests/test_mcp_tools.py`: 30/30
green. `tests/test_parser_agent_probe.py`: 16 passed/1 skipped, also green.

## Files touched

- `D:\Github\_Projects\_LEX\FlexToolsMCP\src\flextoolsmcp\server\scan\grammar_scan_module.py`
  (only file edited; no test/spec/doc files touched, nothing committed).
