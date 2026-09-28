# Evidence: create-text-from-lines

- **Verified by**: `sena3-live`
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=True)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header; dry run read-only plus live write with same-session cleanup
- **op_id**: `op-100018193-008` (live create), `op-100030948-010` (verify + cleanup delete), dry `op-033529928-005`
- **Params**: defaults (`TITLE = "zzRecipeTest Lines"`, `LINES = ["zzRecipeTest line one", "zzRecipeTest line two"]`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 0

## Report excerpt

```text
created text 'zzRecipeTest Lines' with 2 paragraph(s)
verify paras=2
  para: zzRecipeTest line one
  para: zzRecipeTest line two
deleted zzRecipeTest Lines
```

## Notes

Live write on Sena 3 with same-session cleanup (constitution I Sena 3
exception). Live created `zzRecipeTest Lines` guid
`d9fb9a30-1261-4ebb-820e-efc0bb613cc5` with 2 paragraphs
(`op-100018193-008`), verified contents, then `Texts.Delete` removed it
(`op-100030948-010`). Title-exists check compares NFC on both `GetName` and
`GetTitle` and warns instead of delete-and-recreate. No `StText` wrapper
exists in flexicon 4.11.0 (confirmed via `get_object_api` miss); the recipe
reaches paragraphs through `project.Texts.*` / `project.Paragraphs.*` only.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `C62D859E487E9FC2CB864712CAEE1079ECE0C1A20529564F3E36491635EB23D3` | 2026-09-28T14:59:34Z |
| after live + cleanup | `011E23272DAF57A20674A477D0666F81FC896B77EB96D13070DF7E13637F00A4` | 2026-09-28T15:00:34Z |

Size stayed 55,939,810 bytes; the hash moved because the live create plus
delete touched the database, then cleanup removed the test object. A fresh
`zzRecipeTest` scan after cleanup is recorded with the batch join.

## Port

Discovery (R15): `flextools_search_by_capability` for "create a new text
with paragraphs" and "list all texts find text by title create text";
`flextools_get_object_api` on TextOperations (GetAll, Create, GetName,
GetTitle, Exists) and ParagraphOperations (Create); StTextOperations miss
confirmed. Origin: developer ops log (Ron); no new ledger rows
(`raw_lcm_lines: 0`). Read-only dry run op-033529928-005.
