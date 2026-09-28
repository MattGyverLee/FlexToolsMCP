# Evidence: create-entry-like-comparator

- **Verified by**: `sena3-live`
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3`; session `flextools_start(project_name="Sena 3", write_enabled=False)` for dry run, write-enabled for live)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header; dry run read-only (modifyAllowed=False) plus live write with same-session cleanup
- **op_id**: `op-035324411-001` (dry run), `op-035355278-002` (pre: 0 zzRecipeTest), `op-035413531-004` (live create), `op-035431735-006` (verify + cleanup delete)
- **Params**: defaults (`COMPARATOR = "cibubu"`, `NEW_FORM = "zzRecipeTestLike"`, `MORPH_TYPE = "stem"`, `GLOSS = "zzRecipeTest like"`, `CITATION = None`, `FEATURES = None`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 3

## Report excerpt

```text
comparator cibubu: POS='Nome' infl=None
(dry run) would create zzRecipeTestLike mt=stem gloss='zzRecipeTest like' like cibubu
```

Live:

```text
comparator cibubu: POS='Nome' infl=None
created zzRecipeTestLike mt=stem gloss='zzRecipeTest like'
```

Verify + cleanup:

```text
verify found=1
entry guid=16f1344e-d958-4731-9da1-430e5a504afc hw=zzRecipeTestLike lf=zzRecipeTestLike mt=stem glosses=['zzRecipeTest like'] pos=['Nome']
deleted 16f1344e-d958-4731-9da1-430e5a504afc
after cleanup count=0
remaining zzRecipeTest=[]
```

## Notes

Live write on Sena 3 with same-session cleanup (constitution I Sena 3
exception). Pre: 0 `zzRecipeTest` objects (`op-035355278-002`). Live
created `zzRecipeTestLike` guid `16f1344e-d958-4731-9da1-430e5a504afc`
with sense `zzRecipeTest like` POS `Nome`; verify re-read the same headword,
lexeme form, morph type, gloss and POS, then `LexEntry.Delete` removed it
(`op-035431735-006`). Dry run shows the intended change without
writing. The comparator POS comes from the comparator object
(`Senses.GetPartOfSpeechObject`), never from `POS.Find`. The FR-053 lesson
is carried: `MSA.CreateStem` resets the stem MSA, so `InflectionClassRA` is
restored afterwards (raw-LCM gap flexicon#573, ledger B2; Sena 3 cibubu has
infl None, so the restore leg is a no-op there). Idempotency is by
construction (single NEW_FORM; live leg confirmed absence first).

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `680fb4eaa8e32392d23897f8f846fc96dc92a5fea409a16bee112bbd83786b64` | 2026-09-28T08:45:50Z |
| after live + cleanup | `4ab201e9af5f94fbe8293673e7a32e28e87d90843cacb9a763df6b82d4c67265` | 2026-09-28T08:54:35Z |

Size stayed 55,939,810 bytes; the hash moved because the live create plus
delete touched the database, then cleanup removed the test object. A fresh
`zzRecipeTest` scan after cleanup found 0 objects.

## Port

Discovery (R15): `flextools_get_object_api` on LexEntryOperations (Create,
AddSense, SetCitationForm, GetAvailableMorphTypes), MSAOperations
(CreateStem, GetAll), LexSenseOperations (GetPartOfSpeechObject, GetMSA,
GetGloss), POSOperations (GetName), InflectionFeatureOperations
(MakeFeatStruc); `flextools_search_by_capability` for "create a new lexicon
entry with morph type stem", "restore inflection class on stem MSA"
(confirmed gap B2, no flexicon method). Dry run op-035324411-001
(cibubu/Nome candidate, infl None); live op-035413531-004 with backup
`C:\Users\thoua\.flextoolsmcp\backups\Sena 3\20260928T085413Z\Sena 3.fwdata`.
