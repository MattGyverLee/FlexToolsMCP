# Evidence: create-entry-like-comparator

- **Verified by**: `sena3-dryrun` (live write pending: single stem entry create + cleanup still to run)
- **Project**: Sena 3 (asserted with `flextools_list_projects`, which returned `Sena 3` and `Sena_InterlinearTraining`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-033433536-001`
- **Params**: defaults (`COMPARATOR = "cibubu"`, `NEW_FORM = "zzRecipeTestLike"`, `MORPH_TYPE = "stem"`, `GLOSS = "zzRecipeTest like"`, `CITATION = None`, `FEATURES = None`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 3

## Report excerpt

```text
comparator cibubu: POS='Nome' infl=None
(dry run) would create zzRecipeTestLike mt=stem gloss='zzRecipeTest like' like cibubu
```

## Notes

Dry run only. The recipe creates one stem entry, so FR-043 also requires a
live write on Sena 3 with the `zzRecipeTestLike` object, pre/post values,
same-session cleanup, and pre/post `.fwdata` hash -- that step is still
pending. The dry run shows the intended change without writing. The
comparator POS comes from the comparator object
(`Senses.GetPartOfSpeechObject`), never from `POS.Find`. The FR-053 lesson
is carried: `MSA.CreateStem` resets the stem MSA, so `InflectionClassRA` is
restored afterwards (raw-LCM gap flexicon#573, ledger B2). Idempotency is by
construction (single NEW_FORM; re-run skips when the lexeme form exists only
via the T043-style pair check -- here the live leg must confirm absence
first).

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

The hash was taken before the first read run of the batch and after the
last dry run of this round. It never changed, so these runs left the file
untouched.

## Port

Discovery (R15): `flextools_get_object_api` on LexEntryOperations (Create,
AddSense, SetCitationForm, GetAvailableMorphTypes), MSAOperations
(CreateStem, GetAll), LexSenseOperations (GetPartOfSpeechObject, GetMSA,
GetGloss), POSOperations (GetName), InflectionFeatureOperations
(MakeFeatStruc); `flextools_search_by_capability` for "create a new lexicon
entry with morph type stem", "restore inflection class on stem MSA"
(confirmed gap B2, no flexicon method). Read-only dry run op-033433536-001
(cibubu/Nome candidate, infl None).
