# Evidence: add-inflectional-affix

- **Verified by**: `sena3-live`
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=True)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, dry run read-only plus live write with same-session cleanup
- **op_id**: `op-095753733-003` (live create), `op-095802864-004` (verify + cleanup delete), dry `op-033513592-003`
- **Params**: defaults (`COMPARATOR = "na-"`, `NEW = [("zzRecipeTestAff", "prefix", "zzRecipeTest affix")]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
comparator na-: POS='Verbo' slots=['tam1', 'neg/rel  tam1']
created zzRecipeTestAff- guid=ccc28557-848d-4084-9f4a-01a1e6f3449c gloss='zzRecipeTest affix' longname='zzRecipeTestAff- (zzRecipeTest affix)'
verify zzRecipeTestAff- lf=zzRecipeTestAff senses=1 guid=ccc28557-848d-4084-9f4a-01a1e6f3449c
  sense gloss=zzRecipeTest affix
  infl POS=Verbo slots=['tam1', 'neg/rel  tam1']
deleted zzRecipeTestAff- guid=ccc28557-848d-4084-9f4a-01a1e6f3449c
```

## Notes

Live write on Sena 3 with same-session cleanup (constitution I Sena 3
exception). Pre: 0 `zzRecipeTest` objects (`op-095728905-001`). Live
created `zzRecipeTestAff` guid `ccc28557-848d-4084-9f4a-01a1e6f3449c`
with sense `zzRecipeTest affix` POS `Verbo` slots `tam1, neg/rel tam1`,
longname `zzRecipeTestAff- (zzRecipeTest affix)`; verify re-read the same
headword, lexeme form and gloss/POS, then `LexEntry.Delete` removed it
(`op-095802864-004`). Dry run shows the intended change without
writing. A new PRODUCTIVE affix is a grammar-wide change: only run with
explicit approval. POS plus slots copy the comparator via
`MSA.GetAll` wrappers (`is_infl_aff_msa`/`pos_main`) and
`MSA.GetInflAffMsaSlots` (flexicon#543, ledger B6 closed); the new entry is
reported with `LexEntry.GetLongName`, not `MSA.LongName` (gap flexicon#575,
avoided).

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `4AB201E9AF5F94FBE8293673E7A32E28E87D90843CACB9A763DF6B82D4C67265` | 2026-09-28T08:54:35Z |
| after live + cleanup | `936C45EA1B141E5963A7CAF7886257D152F50FF0BE68EBE9633DEEF1A8939AAC` | 2026-09-28T14:58:06Z |

Size stayed 55,939,810 bytes; the hash moved because the live create plus
delete touched the database, then cleanup removed the test object. A fresh
`zzRecipeTest` scan after cleanup is recorded with the batch join.

## Port

Discovery (R15): `flextools_get_object_api` on MSAOperations (GetAll,
GetInflAffMsaSlots, CreateInflAff), LexEntryOperations (Create, AddSense,
GetLongName, GetAvailableMorphTypes), POSOperations (GetName, GetSlotName).
Read-only dry run op-033513592-003.
