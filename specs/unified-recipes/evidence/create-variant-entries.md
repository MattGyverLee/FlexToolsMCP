# Evidence: create-variant-entries

- **Verified by**: `sena3-dryrun` (live write pending: variant entry create + cleanup still to run)
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-033552080-007` (first attempt op-033538115-006 failed cleanly: default `VARIANT_TYPE = "Spelling Variant"` does not exist on Sena 3; fixed to `"Variação de Soletração"`)
- **Params**: `MAIN_HEADWORD = "cibubu"`, `VARIANT_TYPE = "Variação de Soletração"`, `NEW_FORMS = ["zzRecipeTestVar"]`
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
(dry run) would create variant zzRecipeTestVar type=Variação de Soletração of cibubu
```

Failed first attempt (correct behavior -- validation before any write):

```text
unknown variant type 'Spelling Variant'; available=['Variação Dialectal', 'Variação Semântica', 'Variação da Pronuncia', 'Variação Lexical', 'Variação livre', 'Variação Inflectional', 'Variação de Soletração', '', '', '', '']
validation failed: fix PARAMS before any write
```

## Notes

Dry run only. The recipe creates a variant entry plus link, so FR-043 also
requires a live write on Sena 3 with the `zzRecipeTestVar` object,
pre/post values, same-session cleanup, and pre/post `.fwdata` hash --
still pending. Sena 3 variant types are Portuguese; the shipped default now
uses `Variação de Soletração` (spelling variation), validated with
`Variants.FindType` before any write. Correct flexicon accessor is the
plural `project.Variants` (confirmed via `get_object_api(VariantOperations)`
access_path; the singular suggestion in the task brief was wrong).

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

Unchanged, so these runs left the file untouched.

## Port

Discovery (R15): `flextools_search_by_capability` for variant create/link;
`flextools_get_object_api` on VariantOperations (Create, FindType,
AddComponentLexeme, GetAllTypes, GetTypeName) and LexEntryOperations
(Create, GetHeadword, GetLexemeForm). Origin: developer ops log (Ron); no
new ledger rows. Dry runs op-033538115-006 (failed validation, by design)
and op-033552080-007 (green).
