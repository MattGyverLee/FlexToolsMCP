# Evidence: set-allomorph-environments

- **Verified by**: `sena3-dryrun` (dry-run-only recipe per tasks.md T045: existing environments only, shipped defaults change nothing)
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-033503938-002`
- **Params**: defaults (`HEADWORD = "ma-2"`, `FORM = "lf"`, `REMOVE = []`, `ADD = []`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
ma-2 lf BEFORE env=[]
(dry run) would remove [] and add []
ma-2 lf AFTER env=[]
```

## Notes

`ma-2` resolves to exactly 1 entry on Sena 3 and its lexeme-form allomorph
currently carries no environments. Shipped defaults are empty, so the run
changes nothing by construction; a real change supplies exact existing
environment strings (creating one is grammar-wide). BEFORE/AFTER lists print
on every run. No live write is required beyond the dry run for T045, but a
follow-up dry run with real REMOVE/ADD values against Sena 3 environments
would strengthen the evidence.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

Unchanged, so this run left the file untouched.

## Port

Discovery (R15): `flextools_search_by_capability` for "list all
phonological environments and read their string representation" and "read
and change an allomorph's phone environments";
`flextools_get_object_api` on AllomorphOperations (GetAll, GetForm,
GetPhoneEnv, AddPhoneEnv, RemovePhoneEnv) and EnvironmentOperations (GetAll,
GetStringRepresentation). Read-only dry run op-033503938-002. Ledger
confirmation for T051: `project.project`/`EnvironmentsOS`/
`StringRepresentation`/`LexemeFormOA`/`AlternateFormsOS`/`PhoneEnvRC`/
`ClassName` all rewrite through the wrappers (write side: AddPhoneEnv /
RemovePhoneEnv).
