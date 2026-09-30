# Evidence: create-variant-entries

- **Verified by**: `sena3-live`
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=True)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header; dry run read-only plus live write with same-session cleanup
- **op_id**: `op-100128509-011` (live create), `op-100140923-013` (verify + cleanup delete), dry `op-033552080-007` (first attempt op-033538115-006 failed cleanly: default `VARIANT_TYPE = "Spelling Variant"` does not exist on Sena 3; fixed to `"Variação de Soletração"`)
- **Params**: `MAIN_HEADWORD = "cibubu"`, `VARIANT_TYPE = "Variação de Soletração"`, `NEW_FORMS = ["zzRecipeTestVar"]`
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
created variant zzRecipeTestVar type=Variação de Soletração of cibubu guid=251da293-29eb-4728-9185-c603d714c0bd
verify zzRecipeTestVar lf=zzRecipeTestVar guid=251da293-29eb-4728-9185-c603d714c0bd
variant refs=1
  ref form=zzRecipeTestVar type=Variação de Soletração
  components=['cibubu']
deleted zzRecipeTestVar guid=251da293-29eb-4728-9185-c603d714c0bd
```

Failed dry-run attempt (correct behavior -- validation before any write):

```text
unknown variant type 'Spelling Variant'; available=['Variação Dialectal', 'Variação Semântica', 'Variação da Pronuncia', 'Variação Lexical', 'Variação livre', 'Variação Inflectional', 'Variação de Soletração', '', '', '', '']
validation failed: fix PARAMS before any write
```

## Notes

Live write on Sena 3 with same-session cleanup (constitution I Sena 3
exception). Live created `zzRecipeTestVar` guid
`251da293-29eb-4728-9185-c603d714c0bd` type `Variação de Soletração` of
cibubu (`op-100128509-011`), verified 1 ref with component cibubu, then
`LexEntry.Delete` removed it (`op-100140923-013`). Sena 3 variant types are
Portuguese; the shipped default now uses `Variação de Soletração` (spelling
variation), validated with `Variants.FindType` before any write. Correct
flexicon accessor is the plural `project.Variants` (confirmed via
`get_object_api(VariantOperations)` access_path; the singular suggestion in
the task brief was wrong).

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `011E23272DAF57A20674A477D0666F81FC896B77EB96D13070DF7E13637F00A4` | 2026-09-28T15:00:34Z |
| after live + cleanup | `011E23272DAF57A20674A477D0666F81FC896B77EB96D13070DF7E13637F00A4` | 2026-09-28T15:01:44Z |

Hash unchanged and size stayed 55,939,810 bytes; the live create plus delete
netted clean, then cleanup removed the test object. mtime moved because the
database was touched. A fresh `zzRecipeTest` scan after cleanup is recorded
with the batch join.

## Port

Discovery (R15): `flextools_search_by_capability` for variant create/link;
`flextools_get_object_api` on VariantOperations (Create, FindType,
AddComponentLexeme, GetAllTypes, GetTypeName) and LexEntryOperations
(Create, GetHeadword, GetLexemeForm). Origin: developer ops log (Ron); no
new ledger rows. Dry runs op-033538115-006 (failed validation, by design)
and op-033552080-007 (green).
