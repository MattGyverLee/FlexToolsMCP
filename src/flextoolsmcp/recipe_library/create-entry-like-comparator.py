"""
id: create-entry-like-comparator
intent: Create one stem entry modelled on a comparator entry
match_terms: ["create entry like another", "copy entry from comparator", "new stem modelled on existing entry", "duplicate entry structure with a new form", "create stem with the same POS and inflection class", "add a word like cibubu"]
entities: ["LexEntry", "LexSense", "MoStemMsa", "PartOfSpeech"]
operations: ["create"]
requires_write: true
origin: MCPlayground flex-parse-fixup lib/w_create_stem_like.py
verified_against: {"flexicon": "4.12.0", "verified_by": "sena3-dryrun"}
notes: FR-053 lesson carried from w_create_stem_like.py: project.MSA.CreateStem makes a fresh stem MSA without an inflection class, so copy the comparator's class with project.MSA.GetInflectionClass / SetInflectionClass afterwards (flexicon#573, fixed in 4.12.0). Validate the comparator and morph type before any write; refuse when the comparator headword resolves to 0 or more than 1 entry. POS comes from the comparator object via Senses.GetPartOfSpeechObject, never POS.Find by name. Compare headwords after NFC on both sides. Report through report.Info/Warning/Error only.
"""
# --- PARAMS ---
COMPARATOR = "cibubu"  # exact headword of an entry whose first-sense stem MSA supplies POS and inflection class
NEW_FORM = "zzRecipeTestLike"  # lexeme form of the entry to create
MORPH_TYPE = "stem"  # morph type name for the new entry
GLOSS = "zzRecipeTest like"  # gloss for the new entry's single sense
CITATION = None  # citation form or None
FEATURES = None  # feature/value NAMES or None (Sena 3 has no Bantu feature names by default)
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


# Resolve the comparator by exact headword (NFC both sides); refuse on 0 or
# more than 1 match. Never look POS up by name here: names can carry odd
# whitespace, so the POS comes from the comparator object.
matches = [e for e in project.LexEntry.GetAll() if nfc(project.LexEntry.GetHeadword(e)) == nfc(COMPARATOR)]
if len(matches) != 1:
    report.Error(f"comparator {COMPARATOR}: found {len(matches)} entries, need exactly 1")
else:
    comp_entry = matches[0]
    comp_senses = project.LexEntry.GetSenses(comp_entry)
    if not comp_senses:
        report.Error(f"comparator {COMPARATOR}: entry has no senses")
    else:
        pos_obj = project.Senses.GetPartOfSpeechObject(comp_senses[0])
        if pos_obj is None:
            report.Error(f"comparator {COMPARATOR}: first sense has no POS")
        elif not any(w.is_stem_msa for w in project.MSA.GetAll(comp_entry)):
            report.Error(f"comparator {COMPARATOR}: entry has no stem MSA")
        else:
            msa_raw = project.Senses.GetMSA(comp_senses[0])
            if msa_raw is None:
                report.Error(f"comparator {COMPARATOR}: first sense has no MSA")
            else:
                icl = project.MSA.GetInflectionClass(msa_raw)
                valid_morphs = set(name for name, _mt, _is_stem in project.LexEntry.GetAvailableMorphTypes())
                if MORPH_TYPE not in valid_morphs:
                    report.Error(f"new form {NEW_FORM}: unknown morph type {MORPH_TYPE!r}")
                else:
                    report.Info(f"comparator {COMPARATOR}: POS='{project.POS.GetName(pos_obj)}' infl={str(icl) if icl else None}")
                    if not modifyAllowed:
                        report.Info(f"(dry run) would create {NEW_FORM} mt={MORPH_TYPE} gloss='{GLOSS}' like {COMPARATOR}")
                    if modifyAllowed:
                        e = project.LexEntry.Create(NEW_FORM, MORPH_TYPE, create_blank_sense=False)
                        if CITATION:
                            project.LexEntry.SetCitationForm(e, CITATION)
                        s = project.LexEntry.AddSense(e, GLOSS)
                        m = project.MSA.CreateStem(s, pos_obj)
                        if icl is not None:
                            project.MSA.SetInflectionClass(m, icl)
                        if FEATURES:
                            project.InflectionFeature.MakeFeatStruc(FEATURES, owner=m)
                        report.Info(
                            f"created {project.LexEntry.GetHeadword(e)} mt={project.LexEntry.GetMorphType(e)} gloss='{project.Senses.GetGloss(s)}'",
                            project.BuildGotoURL(e),
                        )
