"""
id: affix-templates-and-slots
intent: Show the affix templates of given parts of speech, their slots (optional marked), the affixes in each slot and their environments
match_terms: ["affix templates", "template slots", "which affixes are in this slot", "inflectional template", "slots of a part of speech", "optional slots", "affix slot contents"]
entities: ["MoInflAffixTemplate", "MoInflAffixSlot", "MoInflAffMsa", "PartOfSpeech", "PhEnvironment"]
operations: ["read", "iterate"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/templates_slots_envs.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
notes: A slot marked "?" is optional. Templates come from project.MorphRules.GetAllAffixTemplatesForPOS; use the AffixTemplate and AffixSlot wrappers (prefix_slots, suffix_slots, slot.name, slot.optional, slot.affixes) and don't cast them to IMoInflAffixTemplate / IMoInflAffixSlot. An AffixSlot wrapper never compares equal to the raw slot that project.MSA.GetInflAffMsaSlots returns, so match affixes through slot.affixes, keyed by the .concrete MSA of each project.MSA.GetAll(entry) wrapper. The environment strings printed at the end are the exact notation AddPhoneEnv expects. POS names are compared after NFC normalization.
"""
# --- PARAMS ---
POS_NAMES = ["Verbo"]  # parts of speech whose templates to show (analysis-language names)
SHOW_AFFIXES = True  # list the affixes (with allomorph environments) filling each slot
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


def slot_label(slot):
    return slot.name + ("?" if slot.optional else "")


# inflectional-affix MSA -> "headword env=[...]", built once.
affix_labels = {}
if SHOW_AFFIXES:
    for entry in project.LexEntry.GetAll():
        msas = [m for m in project.MSA.GetAll(entry) if m.is_infl_aff_msa]
        if not msas:
            continue
        envs = sorted(
            set(
                project.Environments.GetStringRepresentation(x)
                for a in project.Allomorphs.GetAll(entry)
                for x in project.Allomorphs.GetPhoneEnv(a)
            )
        )
        label = project.LexEntry.GetHeadword(entry) + (f" env={envs}" if envs else "")
        for msa in msas:
            affix_labels[msa.concrete] = label

wanted = set(nfc(n) for n in POS_NAMES)
seen = set()
for pos in project.POS.GetAll():
    name = nfc(project.POS.GetName(pos))
    if name not in wanted:
        continue
    seen.add(name)
    for template in project.MorphRules.GetAllAffixTemplatesForPOS(pos):
        prefixes = [slot_label(s) for s in template.prefix_slots]
        suffixes = [slot_label(s) for s in template.suffix_slots]
        report.Info(
            f"{name} template '{template.name}'{' (disabled)' if template.disabled else ''}: {prefixes} STEM {suffixes}"
        )
        if SHOW_AFFIXES:
            for slot in list(template.prefix_slots) + list(template.suffix_slots):
                fillers = sorted(affix_labels.get(a, "?") for a in slot.affixes)
                report.Info(f"   {slot_label(slot)}: {fillers}")
for name in sorted(wanted - seen):
    report.Warning(f"no part of speech named {name}")
envs = [project.Environments.GetStringRepresentation(x) for x in project.Environments.GetAll()]
report.Info(f"environments ({len(envs)}): {envs}")
