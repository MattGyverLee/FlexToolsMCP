"""
id: create-variant-entries
intent: Create variant entries linked to a main entry with a validated variant type
match_terms: ["create variant entries", "add variant entry", "link variant to main entry", "spelling variant of entry", "variant type link", "new variant form"]
entities: ["LexEntry", "LexEntryRef", "VariantType"]
operations: ["create"]
requires_write: true
origin: developer ops log (Ron)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-live"}
raw_lcm_lines: 0
notes: The variant main entry must resolve to exactly 1 entry by NFC headword; the variant type is validated with Variants.FindType before any write. New forms use the zz prefix for test objects and are skipped when the lexeme form already exists. This recipe never deletes anything.
"""
# --- PARAMS ---
MAIN_HEADWORD = "cibubu"  # exact headword of the main entry; must resolve to exactly 1 entry (NFC both sides)
VARIANT_TYPE = "Variação de Soletração"  # variant type name; validated with project.Variants.FindType before any write
NEW_FORMS = ["zzRecipeTestVar"]  # new variant forms to create; each is skipped when its lexeme form already exists
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


# Resolve every headword by exact match with NFC on both sides.
hw_entries = {}
for entry in project.LexEntry.GetAll():
    hw_entries.setdefault(nfc(project.LexEntry.GetHeadword(entry)), []).append(entry)

ok = True
mains = hw_entries.get(nfc(MAIN_HEADWORD), [])
if len(mains) != 1:
    report.Error(f"main {MAIN_HEADWORD}: found {len(mains)} entries, need exactly 1")
    ok = False
    main = None
else:
    main = mains[0]

vt = project.Variants.FindType(VARIANT_TYPE)
if vt is None:
    names = [project.Variants.GetTypeName(t) for t in project.Variants.GetAllTypes()]
    report.Error(f"unknown variant type {VARIANT_TYPE!r}; available={names}")
    ok = False

if not ok:
    report.Error("validation failed: fix PARAMS before any write")
else:
    existing_lf = set()
    for entry in project.LexEntry.GetAll():
        existing_lf.add(nfc(project.LexEntry.GetLexemeForm(entry)))
    for form in NEW_FORMS:
        if nfc(form) in existing_lf:
            report.Warning(f"skip {form}: lexeme form already exists")
            continue
        if not modifyAllowed:
            report.Info(f"(dry run) would create variant {form} type={VARIANT_TYPE} of {MAIN_HEADWORD}")
            continue
        if modifyAllowed:
            e = project.LexEntry.Create(form, "stem", create_blank_sense=False)
            ref = project.Variants.Create(e, form, vt)
            project.Variants.AddComponentLexeme(ref, main)
            existing_lf.add(nfc(form))
            hw_entries.setdefault(nfc(project.LexEntry.GetHeadword(e)), []).append(e)
            report.Info(
                f"created variant {form} type={VARIANT_TYPE} of {MAIN_HEADWORD}",
                project.BuildGotoURL(e),
            )
