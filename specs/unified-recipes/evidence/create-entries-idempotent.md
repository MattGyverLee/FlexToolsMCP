# Evidence: create-entries-idempotent

- **Verified by**: `sena3-dryrun` (live write pending: needs a human present)
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-020246820-003`
- **Params**: defaults (`COMPARATORS = {"NOME": "cibubu"}`, `NEW = [("zzRecipeTestYahya", "stem", None, [("zzRecipeTest John", "NOME", None)], None)]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 3

## Report excerpt

```text
comparator NOME=cibubu: POS='Nome' infl=None
(dry run) would create zzRecipeTestYahya mt=stem senses=['zzRecipeTest John'] variant=None
```

## Notes

Dry run only. The recipe creates objects, so FR-043 also requires a live
write on Sena 3 with `zzRecipeTest`-prefixed objects, pre/post values,
same-session cleanup, and pre/post `.fwdata` hash -- that step needs a human
present and is still pending. The dry run shows the intended change without
writing. Validation of every comparator, POS, morph type and variant type
runs before any write; the comparator POS comes from the comparator object
(`Senses.GetPartOfSpeechObject`), never from `POS.Find`. Idempotency compares
NFC lexeme plus NFC gloss plus POS GUID.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

The hash was taken before and after the dry run. It never changed, so this
run left the file untouched.

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
