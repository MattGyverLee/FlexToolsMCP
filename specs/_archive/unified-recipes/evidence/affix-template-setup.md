# Evidence: affix-template-setup

- **Verified by**: `sena3-live`
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=True)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header; dry run read-only plus live write with same-session cleanup
- **op_id**: `op-100340869-014` (live create), `op-100351904-015` (verify + cleanup delete), dry `op-033645896-009` (first attempt op-033604236-008 refused by the casting gate: `s.name` on raw POS slots; fixed to `project.POS.GetSlotName(s)`)
- **Params**: defaults (`POS_NAME = "Nome"`, `TEMPLATE_NAME = "zzRecipeTestTemplate"`, `SLOT_NAMES = []`, `EXEMPLAR_HEADWORD = "cibubu"`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 3

## Report excerpt

```text
POS 'Nome': top-level category
BEFORE:
  POS 'Nome': owns slots ['dblncl', 'extnpx', 'ncl']
  template 'Nome básico': prefix=['ncl'] [16 affix(es) in slots]
  template 'Nome Locativo': prefix=['dblncl', 'ncl'] [25 affix(es) in slots]
created template 'zzRecipeTestTemplate' on POS 'Nome'
  exemplar 'cibubu': 0 repointed, 8 already correct, 12 skipped (no stem MSA)
AFTER:
  template 'zzRecipeTestTemplate': (no slots) [0 affix(es) in slots]
Nome templates BEFORE cleanup: ['Nome básico', 'Nome Locativo', '', '', 'zzRecipeTestTemplate']
deleted zzRecipeTestTemplate
Nome templates AFTER cleanup: ['Nome básico', 'Nome Locativo', '', '']
```

## Notes

Live write on Sena 3 with same-session cleanup (constitution I Sena 3
exception). Live created `zzRecipeTestTemplate` on POS `Nome`
(`op-100340869-014`); exemplar cibubu 8 senses already on Nome so the
repoint leg is a no-op there (0 repointed, 8 already correct, 12 skipped),
then `MorphRules.Delete` removed the template (`op-100351904-015`) and
verified Nome templates back to 4. On Sena 3 the exemplar cibubu senses are
already on Nome, so the repoint leg is a no-op there; the live leg proves
template create/delete. FR-053 lesson carried: `SetStemMsaPos` clears the
inflection class, so save `InflectionClassRA` first and restore right after
(flexicon#573, the recipe's only raw LCM). Never cast AffixTemplate /
AffixSlot wrappers: read `prefix_slots`/`suffix_slots`/`slot.affixes`
through the wrappers and key MSAs by `.concrete` (D1 workaround). Raw POS
slots (from `POS.GetAffixSlots`) expose names only through
`POS.GetSlotName`, not `.name` -- the casting gate refusal
op-033604236-008 proved it.

## .fwdata before / after

`C:\ProgramData\SIL\FieldWorks\Projects\Sena 3\Sena 3.fwdata` (55,939,810 bytes)

| | SHA-256 | mtime |
|---|---|---|
| before | `011E23272DAF57A20674A477D0666F81FC896B77EB96D13070DF7E13637F00A4` | 2026-09-28T15:01:44Z |
| after live + cleanup | `40301770DEED37587E635A872E0009992B3F7EEF2D8B3364C5621CDBDC96A6AC` | 2026-09-28T15:03:55Z |

Size stayed 55,939,810 bytes; the hash moved because the live create plus
delete touched the database, then cleanup removed the test object. A fresh
`zzRecipeTest` scan after cleanup is recorded with the batch join.

## Port

Discovery (R15): `flextools_get_object_api` on MorphRuleOperations
(CreateAffixTemplate, AddSlotToTemplate, GetAllAffixTemplatesForPOS),
POSOperations (GetAll, GetAffixSlots, GetSlotName), MSAOperations
(SetStemMsaPos, GetAll, GetInflAffMsaSlots), AffixTemplate
(prefix_slots/suffix_slots/proclitic_slots/enclitic_slots, slot.affixes).
Origin: developer op op-142307019-033. Ledger rows for T051: B2 extended
with `tpl-setup`; D-workaround row for wrapper equality; B3/#542 and
B6/#543 rewrite confirmations. Dry runs op-033604236-008 (casting refusal,
fixed) and op-033645896-009 (green).
