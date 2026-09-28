# Evidence: add-allomorph

- **Verified by**: `sena3-dryrun` (live write pending: allomorph add to cibubu + removal still to run)
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-033522058-004`
- **Params**: defaults (`HEADWORD = "cibubu"`, `ADD = [("zzRecipeTestAllo", None)]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
cibubu BEFORE: ['cibubu', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed', 'qZ_cast_dup_seed']
(dry run) would add zzRecipeTestAllo env=None
cibubu AFTER: ['cibubu', 'qZ_cast_dup_seed', ...]
```

## Notes

Dry run only. The recipe adds an allomorph, so FR-043 also requires a live
write on Sena 3 (add `zzRecipeTestAllo` with env None to cibubu, verify it
appears, remove it, verify it is gone) with pre/post `.fwdata` hash --
still pending. `cibubu` carries leftover `qZ` test allomorphs in Sena 3;
that is test-project noise, not a recipe issue. HermitCrab allomorphs are
disjunctive in order: list conditioned allomorphs before unconditioned ones.
Zero raw LCM: environments via `Environments.GetAll` keyed by
`GetStringRepresentation`, allomorphs through `Allomorphs.*`.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

Unchanged, so this run left the file untouched.

## Port

Discovery (R15): `flextools_search_by_capability` for "add an allomorph to
a lexical entry"; `flextools_get_object_api` on AllomorphOperations
(Create, GetAll, GetForm, GetPhoneEnv, AddPhoneEnv) and
EnvironmentOperations (GetAll, GetStringRepresentation). Read-only dry run
op-033522058-004. Ledger confirmation for T051: every raw access in
`w_add_allomorph.py` maps to a confirmed rewrite row; `raw_lcm_lines: 0`.
