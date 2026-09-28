"""
id: find-overpowered-affixes
intent: Identify problematic affixes and stems in grammar: duplicate affixes in templates, null affixes in optional slots, senses without grammatical category
match_terms: ["grammar debugging", "overpowered affixes", "find problematic affixes", "null affix", "duplicate affix in template", "parser ambiguity", "stem with no category"]
entities: ["PartOfSpeech", "AffixTemplate", "AffixSlot", "MoInflAffMsa", "MoDerivAffMsa", "MoStemMsa", "LexEntry", "LexSense", "MoForm"]
operations: ["read"]
requires_write: false
origin: FLExTools module Overpowered_Affixes.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Read-only grammar audit for three issues: the same affix entry reused across two or more prefix slots of the same template, null-form allomorphs ('∅' or '[^0]') sitting in an optional slot, and stem senses with no grammatical category (POS). Duplicate-affix detection considers all of a template's prefix slots together, so legitimate multi-slot designs (e.g. parallel agreement-prefix tracks) are still reported -- treat a warning as "worth reviewing," not automatically a data error. Finding an affix's owning LexEntry from its MSA needs raw LCM access (affix_msa.OwnerOfClass(5002)); slot.affixes hands back unwrapped LCM objects with no flexicon wrapper (flexicon gap #581). Advanced constraint checks (inflection classes, features) are out of scope and would need further raw LCM access.
"""
# --- PARAMS ---
# (No parameters - checks all grammar)
# --- END PARAMS ---

def is_null_form(form):
    """Check if form is a null affix."""
    return form in ("[^0]", "∅")


# Check for duplicate affixes in templates
report.Info("Checking for duplicate affixes in templates...")
found_duplicates = False

for pos in project.POS.GetAll():
    pos_name = project.POS.GetName(pos)
    for template in project.MorphRules.GetAllAffixTemplatesForPOS(pos):
        template_name = template.name
        seen_affixes = {}

        # Check all slots
        for slot in template.prefix_slots:
            for affix_msa in slot.affixes:
                try:
                    entry = affix_msa.OwnerOfClass(5002)  # flexicon gap: #581 (MSA -> owning entry has no wrapper)
                except Exception:
                    continue
                if entry is None:
                    continue
                entry_hvo = entry.Hvo
                if entry_hvo in seen_affixes:
                    affix_name = seen_affixes[entry_hvo]
                    report.Warning(f"Duplicate affix '{affix_name}' in template '{template_name}' in {pos_name}")
                    found_duplicates = True
                else:
                    seen_affixes[entry_hvo] = project.LexEntry.GetHeadword(entry)


# Check for null affixes in optional slots
report.Info("Checking for null affixes in optional slots...")
found_nulls = False

for pos in project.POS.GetAll():
    pos_name = project.POS.GetName(pos)
    for template in project.MorphRules.GetAllAffixTemplatesForPOS(pos):
        template_name = template.name

        for slot in template.prefix_slots + template.suffix_slots:
            if slot.optional:
                for affix_msa in slot.affixes:
                    try:
                        entry = affix_msa.OwnerOfClass(5002)  # flexicon gap: #581 (MSA -> owning entry has no wrapper)
                    except Exception:
                        continue
                    if entry is None:
                        continue
                    for allo in project.Allomorphs.GetAll(entry):
                        form = project.Allomorphs.GetForm(allo)
                        if is_null_form(form):
                            report.Warning(
                                f"Null allomorph '{form}' in optional slot '{slot.name}' in template '{template_name}'",
                                project.BuildGotoURL(entry)
                            )
                            found_nulls = True


# Check senses without grammatical category
report.Info("Checking for senses without grammatical category...")
found_uncategorized = False

for entry in project.LexEntry.GetAll():
    mt = project.LexEntry.GetMorphType(entry)
    if mt and "stem" in str(mt).lower():
        entry_form = project.LexEntry.GetLexemeForm(entry)
        for sense in project.LexEntry.GetSenses(entry):
            gloss = project.Senses.GetGloss(sense)
            pos = project.Senses.GetPartOfSpeech(sense)
            if pos is None:
                report.Warning(
                    f"Stem sense '{gloss}' in '{entry_form}' has no grammatical category",
                    project.BuildGotoURL(sense)
                )
                found_uncategorized = True


if not found_duplicates:
    report.Info("No duplicate affixes found in templates.")
if not found_nulls:
    report.Info("No null affixes in optional slots found.")
if not found_uncategorized:
    report.Info("All stem senses have grammatical categories.")

report.Info("Complete!")
