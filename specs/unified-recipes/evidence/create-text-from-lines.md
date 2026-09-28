# Evidence: create-text-from-lines

- **Verified by**: `sena3-dryrun` (live write pending: text create + delete still to run)
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-033529928-005`
- **Params**: defaults (`TITLE = "zzRecipeTest Lines"`, `LINES = ["zzRecipeTest line one", "zzRecipeTest line two"]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
(dry run) would create text 'zzRecipeTest Lines' with 2 paragraph(s)
```

## Notes

Dry run only. The recipe creates a text, so FR-043 also requires a live
write on Sena 3 (create `zzRecipeTest Lines` with 2 paragraphs, verify
contents, delete it, verify it is gone) with pre/post `.fwdata` hash --
still pending. Title-exists check compares NFC on both `GetName` and
`GetTitle` and warns instead of delete-and-recreate. No `StText` wrapper
exists in flexicon 4.11.0 (confirmed via `get_object_api` miss); the recipe
reaches paragraphs through `project.Texts.*` / `project.Paragraphs.*` only.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

Unchanged, so this run left the file untouched.

## Port

Discovery (R15): `flextools_search_by_capability` for "create a new text
with paragraphs" and "list all texts find text by title create text";
`flextools_get_object_api` on TextOperations (GetAll, Create, GetName,
GetTitle, Exists) and ParagraphOperations (Create); StTextOperations miss
confirmed. Origin: developer ops log (Ron); no new ledger rows
(`raw_lcm_lines: 0`). Read-only dry run op-033529928-005.
