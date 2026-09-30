# Evidence: wordform-analyses

- **Verified by**: `sena3-read`
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3` and `Sena_InterlinearTraining`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module(source="existing")`, whole recipe file unchanged, read-only
- **op_id**: `op-012654623-010`
- **Params**: defaults (`WORDS = ["pikakhala", "ampwaza", "ndiwe"]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
== pikakhala count=0 analyses=1 parser=0 human=1
   pi:8 + ka:12 + khal:ser + a:IND  status=APPROVED parser=False
== ndiwe count=14 analyses=2 parser=1 human=1
   nd:Cop + iwe:Ppron  status=UNAPPROVED parser=True
   ?:?  status=APPROVED parser=False
== Ndiwe count=4 analyses=0 parser=0 human=0
```

## Notes

Parser and human counts come from `IsComputerApproved` / `IsHumanApproved` over `Wordforms.GetAnalyses`, not the raw `ParserCount` / `UserCount` (ledger row; flexicon#576 is optional).

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
