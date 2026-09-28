"""
id: add-inflectional-affix
intent: Create inflectional affix entries whose POS and slots copy a comparator affix
match_terms: ["add inflectional affix", "new affix modelled on", "copy affix POS and slots", "create prefix like", "new TAM prefix", "add affix with slots"]
entities: ["LexEntry", "LexSense", "MoInflAffMsa", "PartOfSpeech", "AffixSlot"]
operations: ["create"]
requires_write: true
origin: MCPlayground flex-parse-fixup lib/w_add_affix.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-live"}
raw_lcm_lines: 0
notes: A new PRODUCTIVE affix is a grammar-wide change: only run with explicit approval. The comparator supplies POS plus slots, never looked up by name. POS and slot names are read through GetName wrappers, never multistring internals. Report the new entry with LexEntry.GetLongName, not MSA.LongName (flexicon gap #575).
"""
# --- PARAMS ---
COMPARATOR = "na-"  # exact headword of an existing inflectional affix whose first inflectional-affix MSA supplies POS and slots; must resolve to exactly 1 entry
NEW = [
    # (bare form, morph type, gloss)
    ("zzRecipeTestAff", "prefix", "zzRecipeTest affix"),
]
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


# Resolve the comparator by exact headword (NFC both sides); refuse on 0 or
# more than 1 match. The POS comes from the comparator object, never by name.
hw_entries = {}
for entry in project.LexEntry.GetAll():
    hw_entries.setdefault(nfc(project.LexEntry.GetHeadword(entry)), []).append(entry)

matches = hw_entries.get(nfc(COMPARATOR), [])
if len(matches) != 1:
    report.Error(f"comparator {COMPARATOR}: found {len(matches)} entries, need exactly 1")
else:
    comp_entry = matches[0]
    senses = project.LexEntry.GetSenses(comp_entry)
    infl = None
    for m in project.MSA.GetAll(comp_entry):
        if m.is_infl_aff_msa:
            infl = m
            break
    if not senses:
        report.Error(f"comparator {COMPARATOR}: entry has no senses")
    elif infl is None:
        report.Error(f"comparator {COMPARATOR}: entry has no inflectional-affix MSA")
    else:
        pos = infl.pos_main
        if pos is None:
            report.Error(f"comparator {COMPARATOR}: inflectional-affix MSA has no POS")
        else:
            slots = project.MSA.GetInflAffMsaSlots(infl)
            slot_names = [project.POS.GetSlotName(s) for s in slots]
            report.Info(f"comparator {COMPARATOR}: POS='{project.POS.GetName(pos)}' slots={slot_names}")
            valid_morphs = set(name for name, _mt, _is_stem in project.LexEntry.GetAvailableMorphTypes())
            ok = True
            for form, mt, gloss in NEW:
                if mt not in valid_morphs:
                    report.Error(f"row {form}: unknown morph type {mt!r}")
                    ok = False
            if not ok:
                report.Error("validation failed: fix PARAMS before any write")
            else:
                for form, mt, gloss in NEW:
                    if not modifyAllowed:
                        report.Info(f"(dry run) would create {form} mt={mt} gloss='{gloss}' POS='{project.POS.GetName(pos)}' slots={slot_names}")
                        continue
                    if modifyAllowed:
                        e = project.LexEntry.Create(form, mt, create_blank_sense=False)
                        s = project.LexEntry.AddSense(e, gloss)
                        project.MSA.CreateInflAff(s, pos, slots=slots)
                        report.Info(f"created {project.LexEntry.GetHeadword(e)} guid={project.LexEntry.GetGuid(e)} gloss='{gloss}' longname='{project.LexEntry.GetLongName(e)}'", project.BuildGotoURL(e))
