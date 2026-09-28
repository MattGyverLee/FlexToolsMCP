# Evidence: add-allomorph

- **Verified by**: `sena3-live`
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=True)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header; dry run read-only plus live write with same-session cleanup
- **op_id**: `op-095920614-006` (live add), `op-095930467-007` (verify + cleanup delete), dry `op-033522058-004`
- **Params**: defaults (`HEADWORD = "cibubu"`, `ADD = [("zzRecipeTestAllo", None)]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
cibubu BEFORE: ['cibubu', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed']
added zzRecipeTestAllo env=[]
cibubu AFTER: ['cibubu', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'zzRecipeTestAllo']
BEFORE: ['cibubu', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'zzRecipeTestAllo']
deleted zzRecipeTestAllo
AFTER: ['cibubu', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed']
```

## Notes

Live write on Sena 3 with same-session cleanup (constitution I Sena 3
exception). Pre: cibubu with 7 forms (lexeme + 6 qZ noise). Live added
`zzRecipeTestAllo` env None (`op-095920614-006`), verified it appears as
8th form, then `Allomorphs.Delete` removed it (`op-095930467-007`) and
verified 7 forms again. `cibubu` carries leftover `qZ` test allomorphs in
Sena 3; that is test-project noise, not a recipe issue. HermitCrab
allomorphs are disjunctive in order: list conditioned allomorphs before
unconditioned ones. Zero raw LCM: environments via `Environments.GetAll`
keyed by `GetStringRepresentation`, allomorphs through `Allomorphs.*`.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `936C45EA1B141E5963A7CAF7886257D152F50FF0BE68EBE9633DEEF1A8939AAC` | 2026-09-28T14:58:06Z |
| after live + cleanup | `C62D859E487E9FC2CB864712CAEE1079ECE0C1A20529564F3E36491635EB23D3` | 2026-09-28T14:59:34Z |

Size stayed 55,939,810 bytes; the hash moved because the live add plus
delete touched the database, then cleanup removed the test object. A fresh
`zzRecipeTest` scan after cleanup is recorded with the batch join.

## Port

Discovery (R15): `flextools_search_by_capability` for "add an allomorph to
a lexical entry"; `flextools_get_object_api` on AllomorphOperations
(Create, GetAll, GetForm, GetPhoneEnv, AddPhoneEnv) and
EnvironmentOperations (GetAll, GetStringRepresentation). Read-only dry run
op-033522058-004. Ledger confirmation for T051: every raw access in
`w_add_allomorph.py` maps to a confirmed rewrite row; `raw_lcm_lines: 0`.
