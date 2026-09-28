# Evidence: lexicon-form-lookup

- **Verified by**: `sena3-read`
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3` and `Sena_InterlinearTraining`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module(source="existing")`, whole recipe file unchanged, read-only
- **op_id**: `op-012501907-007`
- **Params**: defaults (`KEYS = ["lekerer", "rekerer", "cibubu"]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
cibubu | lf=cibubu | mt=root | allos=['cibubu', 'qZ_cast_dup_seed', ...] | senses=['gaguez [N 7/8]', ...]
lekerera | lf=lekerer | mt=root | allos=['lekerer', 'rekerer'] | senses=['perdoar [V]']
```

## Notes

`rekerer` is found through the allomorph list (it is neither lexeme form nor headword). `cibubu` carries leftover `qZ` test allomorphs in Sena 3; that is test-project noise, not a recipe issue. US3 acceptance 2 (NFD data found by an NFC query) is covered offline by `tests/test_recipes.py::test_lexicon_lookup_finds_nfd_form`, because Sena 3 has no decomposed vernacular forms.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

The hash was taken before the first read run of the batch, between runs, and
after the last run. It never changed, so this run left the file untouched.

## Port

Discovery (R15): `flextools_get_object_api` on AllomorphOperations, LexEntryOperations, LexSenseOperations, MSAOperations, MorphosyntaxAnalysis, WordformOperations, WfiAnalysisOperations, WfiMorphBundleOperations, EnvironmentOperations, POSOperations, MorphRuleOperations (Template filter), AffixTemplate, AffixSlot, PhonologicalRuleOperations, PhonologicalRule, InflectionFeatureOperations (Describe filter); `flextools_search_by_capability` "get the name of a morph type object"; read-only probes op-011417193-001, op-011509856-002, op-011655505-004, op-012807552-015, op-012841743-016.
