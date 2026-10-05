"""
id: affix-template-setup
intent: Set up an inflectional affix template on a part of speech from its existing slots, then repoint an exemplar entry's stem MSAs to that POS keeping inflection class
match_terms: ["set up affix template", "create inflectional template", "add existing slots to template", "repoint stem MSA to POS", "restore inflection class", "POS subcategory template setup", "inflectional template for a part of speech"]
entities: ["PartOfSpeech", "AffixTemplate", "AffixSlot", "MoStemMsa"]
operations: ["create", "update"]
requires_write: true
origin: developer op op-142307019-033
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-live"}
raw_lcm_lines: 0
notes: Validate the POS (subcategories included, NFC names) and every SLOT_NAMES entry before any write; refuse when the POS or exemplar headword resolves to 0 or more than 1 match, and when a wanted slot is not owned by the POS (this recipe only adds existing slots, never creates them). Create the template with project.MorphRules.CreateAffixTemplate and place slots with project.MorphRules.AddSlotToTemplate, inferring each slot's side from sibling templates and refusing when the side is unknown or ambiguous. Repointing a stem MSA with project.MSA.SetStemMsaPos(keep_inflection_class=True) keeps a still-valid inflection class itself (flexicon#573, closed in flexicon 4.12.0); no raw LCM remains in this recipe. Never cast the AffixTemplate or AffixSlot wrappers to IMoInflAffixTemplate or IMoInflAffixSlot: read prefix_slots, suffix_slots and slot.affixes through the wrappers, and key MSAs by the .concrete of the project.MSA.GetAll wrappers (wrapper objects never compare equal to the raw slots that project.MSA.GetInflAffMsaSlots returns). Report through report.Info/Warning/Error only.
"""
# --- PARAMS ---
POS_NAME = "Nome"  # POS (or subcategory) name in the analysis writing system, compared NFC
TEMPLATE_NAME = "zzRecipeTestTemplate"  # template name; a live run creates it on the POS when missing
SLOT_NAMES = []  # existing slot names to ensure on the template; each must already be owned by the POS, empty means validate-only
EXEMPLAR_HEADWORD = "cibubu"  # exemplar entry whose stem MSAs are repointed to the POS, restoring inflection class
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


SIDES = ("prefix", "suffix", "proclitic", "enclitic")


def template_slots(template):
    return {
        "prefix": list(template.prefix_slots),
        "suffix": list(template.suffix_slots),
        "proclitic": list(template.proclitic_slots),
        "enclitic": list(template.enclitic_slots),
    }


def describe_template(template):
    bits = []
    filled = 0
    for side in SIDES:
        slots = template_slots(template)[side]
        names = [s.name + ("?" if s.optional else "") for s in slots]
        if names:
            bits.append(f"{side}={names}")
        filled += sum(1 for s in slots for _a in s.affixes)
    body = "; ".join(bits) if bits else "(no slots)"
    return f"template '{template.name}': {body} [{filled} affix(es) in slots]"


def find_template(pos, name):
    for cand in project.MorphRules.GetAllAffixTemplatesForPOS(pos):
        if nfc(cand.name) == nfc(name):
            return cand
    return None


ok = True
pos = None
ex_entry = None

# 1. Resolve the POS (GetAll is recursive, so subcategories match too).
matches = [p for p in project.POS.GetAll() if nfc(project.POS.GetName(p)) == nfc(POS_NAME)]
if len(matches) != 1:
    report.Error(f"POS {POS_NAME!r}: found {len(matches)} matches, need exactly 1")
    ok = False
else:
    pos = matches[0]
    pos_name = project.POS.GetName(pos)
    parent = project.POS.GetParent(pos)
    if parent is None:
        report.Info(f"POS '{pos_name}': top-level category")
    else:
        report.Info(f"POS '{pos_name}': subcategory of '{project.POS.GetName(parent)}'")
    subs = sorted(project.POS.GetName(s) for s in project.POS.GetSubcategories(pos))
    if subs:
        report.Info(f"POS '{pos_name}': subcategories {subs}")

# 2. Resolve the exemplar entry by exact headword (NFC both sides).
if ok:
    cands = [e for e in project.LexEntry.GetAll() if nfc(project.LexEntry.GetHeadword(e)) == nfc(EXEMPLAR_HEADWORD)]
    if len(cands) != 1:
        report.Error(f"exemplar {EXEMPLAR_HEADWORD!r}: found {len(cands)} entries, need exactly 1")
        ok = False
    else:
        ex_entry = cands[0]

# 3. Validate every wanted slot is already owned by the POS (existing slots only).
slot_by_name = {}
if ok:
    for s in project.POS.GetAffixSlots(pos):
        slot_by_name.setdefault(nfc(project.POS.GetSlotName(s)), s)
    for wanted in SLOT_NAMES:
        if nfc(wanted) not in slot_by_name:
            report.Error(f"slot {wanted!r}: not owned by POS '{pos_name}'; this recipe only adds existing slots")
            ok = False

if not ok:
    report.Error("validation failed: fix PARAMS before any write")
else:
    report.Info("BEFORE:")
    report.Info(f"  POS '{pos_name}': owns slots {sorted(slot_by_name)}")
    for t in project.MorphRules.GetAllAffixTemplatesForPOS(pos):
        report.Info(f"  {describe_template(t)}")
    hw = project.LexEntry.GetHeadword(ex_entry)
    senses = project.LexEntry.GetSenses(ex_entry)
    if not senses:
        report.Warning(f"  exemplar '{hw}': entry has no senses; nothing to repoint")
    by_concrete = {m.concrete: m for m in project.MSA.GetAll(ex_entry)}
    stems = []
    for sense in senses:
        gloss = project.Senses.GetGloss(sense)
        raw_msa = project.Senses.GetMSA(sense)
        wrap = by_concrete.get(raw_msa) if raw_msa is not None else None
        if wrap is None or not wrap.is_stem_msa:
            report.Info(f"  exemplar '{hw}' sense '{gloss}': no stem MSA, skipped")
            continue
        cur = project.Senses.GetPartOfSpeechObject(sense)
        cur_name = project.POS.GetName(cur) if cur is not None else None
        report.Info(f"  exemplar '{hw}' sense '{gloss}': stem MSA on POS {cur_name!r}")
        stems.append((sense, gloss, cur, cur_name))

    # 4. Ensure the template exists (create under modifyAllowed only).
    template = find_template(pos, TEMPLATE_NAME)
    if template is None:
        if not modifyAllowed:
            report.Info(f"(dry run) would create template '{TEMPLATE_NAME}' on POS '{pos_name}'")
        if modifyAllowed:
            project.MorphRules.CreateAffixTemplate(pos, TEMPLATE_NAME)
            template = find_template(pos, TEMPLATE_NAME)
            if template is None:
                report.Error(f"created template '{TEMPLATE_NAME}' but cannot find it afterwards")
                ok = False
            else:
                report.Info(f"created template '{template.name}' on POS '{pos_name}'")

    # 5. Ensure each validated slot sits on the template (add under modifyAllowed only).
    if ok and template is not None:
        on_template = {nfc(s.name) for slots in template_slots(template).values() for s in slots}
        side_by_slot = {}
        for t in project.MorphRules.GetAllAffixTemplatesForPOS(pos):
            for side in SIDES:
                for s in template_slots(t)[side]:
                    side_by_slot.setdefault(nfc(s.name), set()).add(side)
        for wanted in SLOT_NAMES:
            slot = slot_by_name[nfc(wanted)]
            slot_label = project.POS.GetSlotName(slot)
            if nfc(wanted) in on_template:
                report.Info(f"slot '{slot_label}': already on template '{template.name}'")
                continue
            sides = side_by_slot.get(nfc(wanted), set())
            if len(sides) != 1:
                report.Error(f"slot '{slot_label}': side unknown or ambiguous {sorted(sides)}; add it by hand")
                continue
            (side,) = sides
            if not modifyAllowed:
                report.Info(f"(dry run) would add slot '{slot_label}' to template '{template.name}' as {side}")
                continue
            if modifyAllowed:
                project.MorphRules.AddSlotToTemplate(template, slot, side)
                on_template.add(nfc(wanted))
                report.Info(f"added slot '{slot_label}' to template '{template.name}' as {side}")

    # 6. Repoint the exemplar stem MSAs, keeping the inflection class
    # (flexicon#573, closed in flexicon 4.12.0: SetStemMsaPos restores a
    # still-valid class itself, and warns instead of attaching an
    # incompatible one -- no save/restore dance needed).
    repointed = 0
    already = 0
    skipped = 0
    if ok:
        for sense, gloss, cur, cur_name in stems:
            if cur is not None and str(cur.Guid) == str(pos.Guid):
                report.Info(f"sense '{gloss}': already on POS '{pos_name}'; inflection class untouched")
                already += 1
                continue
            if not modifyAllowed:
                report.Info(f"(dry run) would repoint sense '{gloss}' from {cur_name!r} to '{pos_name}', keeping its inflection class when still valid for the new POS")
                continue
            if modifyAllowed:
                project.MSA.SetStemMsaPos(sense, pos, keep_inflection_class=True)
                report.Info(f"repointed sense '{gloss}': POS {cur_name!r} -> '{pos_name}' (inflection class kept when still valid for the new POS)")
                repointed += 1
        skipped = len(senses) - len(stems)

    if ok:
        report.Info("AFTER:")
        template = find_template(pos, TEMPLATE_NAME)
        if template is None:
            report.Info(f"  template '{TEMPLATE_NAME}': still missing (dry run creates nothing)")
        else:
            report.Info(f"  {describe_template(template)}")
        report.Info(f"  exemplar '{hw}': {repointed} repointed, {already} already correct, {skipped} skipped (no stem MSA)")
