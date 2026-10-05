"""
id: create-entries-idempotent
intent: Create entries with senses idempotently, skipping existing lexeme-form plus gloss plus POS
match_terms: ["create entries", "bulk import entries", "add entries with senses", "idempotent entry creation", "new stem entry with POS", "skip existing entries"]
entities: ["LexEntry", "LexSense", "MoStemMsa", "PartOfSpeech", "LexEntryRef"]
operations: ["create", "iterate", "search"]
requires_write: true
origin: MCPlayground flex-parse-fixup lib/w_create_entries.py
verified_against: {"flexicon": "4.12.0", "verified_by": "sena3-dryrun"}
notes: Validate every comparator, POS, morph type and variant type before any write; refuse when a PARAMS headword resolves to 0 or more than 1 entry. Idempotent: skips a row whose lexeme form plus first gloss plus POS already exists (POS compared by GUID, text by NFC). New stems copy the comparator POS with project.MSA.CreateStem and its inflection class with project.MSA.GetInflectionClass / SetInflectionClass (flexicon#573, fixed in 4.12.0). Otherwise never cast flexicon wrappers to LCM interfaces, never branch on ClassName, never compare Hvo, and read names through GetName rather than multistring internals. A bare reading (interjection, adverb, particle) must be morph type stem; a bound stem never parses without an affix. Report through report.Info/Warning/Error only.
"""
# --- PARAMS ---
COMPARATORS = {"NOME": "cibubu"}  # comparator key -> exact headword of an entry whose first-sense stem MSA supplies POS and inflection class
NEW = [
    # (lexeme form, morph type, citation or None,
    #  [(gloss, comparator key, FEATURES or None), ...],
    #  (main entry headword, variant type name) or None)
    ("zzRecipeTestYahya", "stem", None, [("zzRecipeTest John", "NOME", None)], None),
]
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


# Resolve every comparator and variant target by exact headword (NFC both
# sides); refuse on 0 or more than 1 match. Never look POS up by name here:
# names can carry odd whitespace, so the POS comes from the comparator object.
hw_entries = {}
for entry in project.LexEntry.GetAll():
    hw_entries.setdefault(nfc(project.LexEntry.GetHeadword(entry)), []).append(entry)

comp = {}
ok = True
for key, hw in COMPARATORS.items():
    matches = hw_entries.get(nfc(hw), [])
    if len(matches) != 1:
        report.Error(f"comparator {key}={hw}: found {len(matches)} entries, need exactly 1")
        ok = False
        continue
    comp_entry = matches[0]
    senses = project.LexEntry.GetSenses(comp_entry)
    if not senses:
        report.Error(f"comparator {key}={hw}: entry has no senses")
        ok = False
        continue
    pos_obj = project.Senses.GetPartOfSpeechObject(senses[0])
    if pos_obj is None:
        report.Error(f"comparator {key}={hw}: first sense has no POS")
        ok = False
        continue
    has_stem = any(w.is_stem_msa for w in project.MSA.GetAll(comp_entry))
    if not has_stem:
        report.Error(f"comparator {key}={hw}: entry has no stem MSA")
        ok = False
        continue
    msa_raw = project.Senses.GetMSA(senses[0])
    if msa_raw is None:
        report.Error(f"comparator {key}={hw}: first sense has no MSA")
        ok = False
        continue
    icl = project.MSA.GetInflectionClass(msa_raw)
    comp[key] = (pos_obj, icl)
    report.Info(f"comparator {key}={hw}: POS='{project.POS.GetName(pos_obj)}' infl={project.InflectionFeatures.InflectionClassGetName(icl) if icl else None}")

# Validate morph types and variant types before any write.
valid_morphs = set(name for name, _mt, _is_stem in project.LexEntry.GetAvailableMorphTypes())
for form, mt, _cit, senses, var in NEW:
    if mt not in valid_morphs:
        report.Error(f"row {form}: unknown morph type {mt!r}")
        ok = False
    for _gloss, ck, _feats in senses:
        if ck not in COMPARATORS:
            report.Error(f"row {form}: unknown comparator key {ck!r}")
            ok = False
    if var:
        vt = project.Variant.FindType(var[1])
        if vt is None:
            report.Error(f"row {form}: unknown variant type {var[1]!r}")
            ok = False

if not ok:
    report.Error("validation failed: fix PARAMS before any write")
else:
    # Existing lexeme forms and (lexeme, gloss, POS-guid) pairs for idempotency.
    existing_lf = set()
    existing_pairs = set()
    for entry in project.LexEntry.GetAll():
        lf = nfc(project.LexEntry.GetLexemeForm(entry))
        existing_lf.add(lf)
        for s in project.LexEntry.GetSenses(entry):
            p = project.Senses.GetPartOfSpeechObject(s)
            if p is not None:
                existing_pairs.add((lf, nfc(project.Senses.GetGloss(s)), str(p.Guid)))

    for form, mt, cit, senses, var in NEW:
        pos_guid = None
        if senses and senses[0][1] in comp:
            pos_guid = str(comp[senses[0][1]][0].Guid)
        if senses and (nfc(form), nfc(senses[0][0]), pos_guid) in existing_pairs:
            report.Warning(f"skip {form} '{senses[0][0]}': already exists")
            continue
        if not senses and nfc(form) in existing_lf:
            report.Warning(f"skip sense-less {form}: lexeme form already exists")
            continue
        if any(ck not in comp for _, ck, _ in senses):
            report.Error(f"skip {form}: comparator not resolved")
            continue
        if not modifyAllowed:
            report.Info(f"(dry run) would create {form} mt={mt} senses={[g for g, _ck, _f in senses]} variant={var}")
            continue
        if modifyAllowed:
            e = project.LexEntry.Create(form, mt, create_blank_sense=False)
            if cit:
                project.LexEntry.SetCitationForm(e, cit)
            out = []
            for gloss, ck, feats in senses:
                pos, icl = comp[ck]
                s = project.LexEntry.AddSense(e, gloss)
                m = project.MSA.CreateStem(s, pos)
                if icl is not None:
                    project.MSA.SetInflectionClass(m, icl)
                if feats:
                    project.InflectionFeature.MakeFeatStruc(feats, owner=m)
                out.append(f"'{gloss}' POS='{project.POS.GetName(pos)}' sense={project.Senses.GetGuid(s)}")
            vinfo = None
            if var:
                mains = hw_entries.get(nfc(var[0]), [])
                main = mains[0] if len(mains) == 1 else None
                vt = project.Variant.FindType(var[1])
                if main is None or vt is None:
                    report.Error(f"{form}: variant main {var[0]!r} or type {var[1]!r} not found; no variant link")
                else:
                    ref = project.Variant.Create(e, form, vt)
                    project.Variant.AddComponentLexeme(ref, main)
                    vinfo = f"{var[1]} of {var[0]}"
            hw_entries.setdefault(nfc(project.LexEntry.GetHeadword(e)), []).append(e)
            report.Info(f"created {project.LexEntry.GetHeadword(e)} guid={project.LexEntry.GetGuid(e)} mt={project.LexEntry.GetMorphType(e)} senses={out} variant={vinfo}")
