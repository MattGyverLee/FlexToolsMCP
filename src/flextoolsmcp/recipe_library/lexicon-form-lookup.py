"""
id: lexicon-form-lookup
intent: Check whether forms exist in the lexicon as a lexeme form, headword or allomorph
match_terms: ["lexicon lookup", "does this form exist", "find entry by form", "is this word in the lexicon", "look up allomorph", "which entry has this form"]
entities: ["LexEntry", "MoForm", "LexSense"]
operations: ["read", "iterate", "search"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/lexicon_lookup.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
notes: Vernacular text is compared after NFC normalization on both sides, so a form stored decomposed (NFD) still matches a composed query. Morpheme-break marks (- * =) are stripped before comparing. project.Allomorphs.GetAll(entry) already includes the lexeme form, listed first. Read the morph type with str(project.LexEntry.GetMorphType(entry)); don't .lower() the object.
"""
# --- PARAMS ---
KEYS = ["lekerer", "rekerer", "cibubu"]  # bare vernacular forms to look for (no - * = marks needed)
# --- END PARAMS ---
import unicodedata


def norm(text):
    # NFC both sides, then drop affix/clitic marks and ignore case.
    return unicodedata.normalize("NFC", text or "").strip("-*=").lower()


keys = set(norm(k) for k in KEYS)
found = set()
for entry in project.LexEntry.GetAll():
    lexeme = project.LexEntry.GetLexemeForm(entry)
    headword = project.LexEntry.GetHeadword(entry)
    allos = [project.Allomorphs.GetForm(a) for a in project.Allomorphs.GetAll(entry)]
    hits = keys.intersection(norm(x) for x in [lexeme, headword] + allos)
    if not hits:
        continue
    found.update(hits)
    senses = [
        f"{project.Senses.GetGloss(s)} [{project.Senses.GetPartOfSpeech(s) or 'no POS'}]"
        for s in project.LexEntry.GetSenses(entry)
    ]
    mt = project.LexEntry.GetMorphType(entry)
    report.Info(
        f"{headword} | lf={lexeme} | mt={str(mt) if mt else None} | allos={allos} | senses={senses}",
        project.BuildGotoURL(entry),
    )
for key in sorted(keys - found):
    report.Warning(f"not in the lexicon: {key}")
