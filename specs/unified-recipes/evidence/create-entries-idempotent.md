# Evidence: create-entries-idempotent

- **Verified by**: `sena3-live`
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3`; session `flextools_start(project_name="Sena 3", write_enabled=True)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header; dry run read-only (modifyAllowed=False) plus live write with same-session cleanup
- **op_id**: `op-034537057-003` (live create), `op-034546624-004` (verify + cleanup delete), dry `op-020246820-003`
- **Params**: defaults (`COMPARATORS = {"NOME": "cibubu"}`, `NEW = [("zzRecipeTestYahya", "stem", None, [("zzRecipeTest John", "NOME", None)], None)]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 3

## Report excerpt

```text
comparator NOME=cibubu: POS='Nome' infl=None
(dry run) would create zzRecipeTestYahya mt=stem senses=['zzRecipeTest John'] variant=None
```

## Notes

Live write on Sena 3 with same-session cleanup (constitution I Sena 3
exception). Pre: 0 `zzRecipeTest` objects (`op-034458958-001`). Live
created `zzRecipeTestYahya` guid `601df8ac-8569-4004-930a-3b53b1500b6a`
with sense `zzRecipeTest John` POS `Nome` guid
`9a381a13-0e64-4e8c-8fef-5e4a00d0ae2c`; verify re-read the same headword,
lexeme form and gloss/POS, then `LexEntry.Delete` removed it
(`op-034546624-004`). Dry run shows the intended change without
writing. Validation of every comparator, POS, morph type and variant type
runs before any write; the comparator POS comes from the comparator object
(`Senses.GetPartOfSpeechObject`), never from `POS.Find`. Idempotency compares
NFC lexeme plus NFC gloss plus POS GUID.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after live + cleanup | `680fb4eaa8e32392d23897f8f846fc96dc92a5fea409a16bee112bbd83786b64` | 2026-09-28T08:45:50Z |

Size stayed 55,939,810 bytes; the hash moved because the live create plus
delete touched the database, then cleanup removed the test object. A fresh
`zzRecipeTest` scan after cleanup is recorded with the batch join.

## Port

Discovery (R15): `flextools_get_object_api` on LexEntryOperations (Create,
AddSense, SetCitationForm, GetAvailableMorphTypes), MSAOperations (CreateStem,
GetAll), LexSenseOperations (GetPartOfSpeechObject, GetMSA, GetGuid),
POSOperations (Find, GetName), InflectionFeatureOperations (MakeFeatStruc),
VariantOperations (FindType, Create, AddComponentLexeme);
`flextools_search_by_capability` for "create a new lexicon entry with morph
type stem", "add a sense to an entry and create stem MSA with part of
speech", "find part of speech by name and validate before write", "set
citation form on entry inflection class restore after SetStemMsaPos", "get
guid of part of speech compare POS identity", "undoable operation context
manager for writes"; read-only probes op-020036767-001 (Musa/naam absent on
Sena 3; cibubu/Nome candidate), op-020050530-002 (variant types, morph types,
cibubu stem MSA with infl None, feature names absent so defaults use
feats=None and variant=None).
