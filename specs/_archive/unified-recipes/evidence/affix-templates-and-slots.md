# Evidence: affix-templates-and-slots

- **Verified by**: `sena3-read`
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3` and `Sena_InterlinearTraining`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module(source="existing")`, whole recipe file unchanged, read-only
- **op_id**: `op-012947744-017`
- **Params**: defaults (`POS_NAMES = ["Verbo"]`, `SHOW_AFFIXES = True`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
Verbo template '': ['sbj', 'tam1', 'tam2?', 'obj?'] STEM ['vf', 'pos?']
   sbj: ['a-1', 'a-3', ..., "pi-1 env=['/ _ [C]']", ...]
   tam1: ['a-4', 'da-1', 'kha-', "na- env=['/ _ e']", 'nga-', 'sa-']
   vf: ['-a1']
   pos?: ["-ni env=['/ _ #']", '-tu']
...
environments (38): ['/[V+mid] ([preNas]) [C-nas] ([Mod]) _', '/ [C] _', ...]
```

## Notes

The first version (op-012735416-013) ran without error but listed every slot as `[]`: the `AffixSlot` wrappers in `template.prefix_slots` never compare equal to the raw `IMoInflAffixSlot` objects that `MSA.GetInflAffMsaSlots` returns (probe op-012807552-015: same GUID, `==` False). The recipe now reads `slot.affixes` and labels each MSA through the `.concrete` object of the `MSA.GetAll(entry)` wrappers (probe op-012841743-016). The first draft also exposed a raw-LCM gate false positive: `project.POS` and `GetAllAffixTemplatesForPOS` matched the `*OS` suffix rule. That is fixed in `validators.py`, `recipe_files.py` and `tools/scan_raw_lcm.py`, with regression test `tests/test_raw_lcm_gate.py::TestAcronymNamesAreNotRaw`.

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
