# Evidence: add-inflectional-affix

- **Verified by**: `sena3-dryrun` (live write pending: prefix entry create + cleanup still to run)
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-033513592-003`
- **Params**: defaults (`COMPARATOR = "na-"`, `NEW = [("zzRecipeTestAff", "prefix", "zzRecipeTest affix")]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
comparator na-: POS='Verbo' slots=['tam1', 'neg/rel  tam1']
(dry run) would create zzRecipeTestAff mt=prefix gloss='zzRecipeTest affix' POS='Verbo' slots=['tam1', 'neg/rel  tam1']
```

## Notes

Dry run only. The recipe creates an inflectional affix entry, so FR-043
also requires a live write on Sena 3 with the `zzRecipeTestAff` object,
pre/post values, same-session cleanup, and pre/post `.fwdata` hash -- still
pending. A new PRODUCTIVE affix is a grammar-wide change: only run with
explicit approval. POS plus slots copy the comparator via
`MSA.GetAll` wrappers (`is_infl_aff_msa`/`pos_main`) and
`MSA.GetInflAffMsaSlots` (flexicon#543, ledger B6 closed); the new entry is
reported with `LexEntry.GetLongName`, not `MSA.LongName` (gap flexicon#575,
avoided).

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

Unchanged, so this run left the file untouched.

## Port

Discovery (R15): `flextools_get_object_api` on MSAOperations (GetAll,
GetInflAffMsaSlots, CreateInflAff), LexEntryOperations (Create, AddSense,
GetLongName, GetAvailableMorphTypes), POSOperations (GetName, GetSlotName).
Read-only dry run op-033513592-003.
