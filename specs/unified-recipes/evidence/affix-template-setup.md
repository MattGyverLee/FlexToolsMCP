# Evidence: affix-template-setup

- **Verified by**: `sena3-dryrun` (live write pending: template create + exemplar repoint + restore still to run)
- **Project**: Sena 3 (asserted with `flextools_list_projects`; session `flextools_start(project_name="Sena 3", write_enabled=False)`)
- **flexicon**: 4.11.0 (installed = index, exact match)
- **Run**: `flextools_run_module`, recipe PARAMS-plus-code as shipped except the file docstring header, read-only (modifyAllowed=False)
- **op_id**: `op-033645896-009` (first attempt op-033604236-008 refused by the casting gate: `s.name` on raw POS slots; fixed to `project.POS.GetSlotName(s)`)
- **Params**: defaults (`POS_NAME = "Nome"`, `TEMPLATE_NAME = "zzRecipeTestTemplate"`, `SLOT_NAMES = []`, `EXEMPLAR_HEADWORD = "cibubu"`)
- **Date**: 2026-09-28
- **raw_lcm_lines**: 3

## Report excerpt

```text
POS 'Nome': validated
BEFORE:
  POS 'Nome': owns slots ['dblncl', 'extnpx', 'ncl']
  template 'Nome básico': prefix=1 suffix=0
  template 'Nome Locativo': prefix=2 suffix=0
sense 'gaguez': already on POS 'Nome'; untouched
(dry run) would create template 'zzRecipeTestTemplate' on POS 'Nome'
```

## Notes

Dry run only. The recipe creates a template (and would repoint exemplar
stem MSAs), so FR-043 also requires a live write on Sena 3 with the
`zzRecipeTestTemplate` object, pre/post values, same-session cleanup
(delete the template, confirm exemplar untouched), and pre/post `.fwdata`
hash -- still pending. On Sena 3 the exemplar cibubu senses are already on
Nome, so the repoint leg is a no-op there; the live leg proves template
create/delete. FR-053 lesson carried: `SetStemMsaPos` clears the inflection
class, so save `InflectionClassRA` first and restore right after
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
| before | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |
| after | `076f0c165257ec118ed19799f57e65f00faae0fa28d0c69bb812abe826c9b131` | 2026-09-27T18:10:56 |

Unchanged, so these runs left the file untouched.

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
