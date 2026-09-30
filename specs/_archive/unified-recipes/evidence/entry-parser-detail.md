# Evidence: entry-parser-detail

- **Verified by**: `sena3-read`
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3` and `Sena_InterlinearTraining`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module(source="existing")`, whole recipe file unchanged, read-only
- **op_id**: `op-012629118-009`
- **Params**: defaults (`HEADWORDS = ["lekerera", "pi-1"]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 3

## Report excerpt

```text
== lekerera mt=root cit=lekerera
   lf  form=lekerer abstract=False env=[] mt=root
   alt form=rekerer abstract=False env=['/ [V-front] _'] mt=root
   stem MSA: POS=Verbo infl class=None feats=None exception feats=[]
== pi-1 mt=prefix- cit=None
   lf  form=pi abstract=False env=['/ _ [C]'] mt=prefix-
   infl-affix MSA: POS=Verbo slots=['obj', 'sbj'] feats=None
   infl-affix MSA: POS=Nome slots=['ncl'] feats=[NounAgr: [genro: 7/8]]
```

## Notes

The first run (op-012528908-008) passed, but the run-time casting gate warned on `InflectionClassRA`: it cannot see that `as_stem_msa()` returns an `IMoStemMsa`, and a write-enabled session would reject the line. An explicit `IMoStemMsa(...)` cast on the gap line removed the warning (this run). `raw_lcm_lines: 3` = the cast + `InflectionClassRA` (flexicon#573) + `ProdRestrictRC` (flexicon#574).

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
