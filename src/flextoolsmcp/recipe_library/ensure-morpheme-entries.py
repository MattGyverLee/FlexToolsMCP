"""
id: ensure-morpheme-entries
intent: Make sure each listed morpheme (stem or affix, written with affix markers) has a lexical entry, creating only the missing ones
match_terms: ["create missing lexentries for morphemes", "create missing entries for morphemes", "ensure morphemes exist", "add missing affixes and stems", "find or create entry by morpheme", "check which morphemes are missing from the lexicon", "create entries for prefixes and suffixes"]
entities: ["LexEntry", "LexSense", "MoStemMsa", "MoUnclassifiedAffixMsa", "MoMorphType", "PartOfSpeech"]
operations: ["create", "search", "iterate"]
requires_write: true
origin: FlexToolsMCP log triage 2026-09-30 (Claude-Swahili morpheme-creation workflow, #335)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-live"}
notes: Morph type comes from the affix markers in each form: "ku-" prefix, "-a" suffix, "-ku-" infix, "=ni" enclitic, "ni=" proclitic, bare form = stem. Markers are stripped before storing the lexeme form, as FLEx does. A morpheme already exists when some entry has the same NFC lexeme form and the same morph type; a same-form entry with another morph type is reported but does not count. Every morph type and POS name is validated before any write; an unknown name stops the whole run. New stems get a stem MSA and new affixes an unclassified affix MSA, with the POS when one is given. Inflectional affixes still need a template slot before HermitCrab can use them: follow up with the add-inflectional-affix recipe. Without modifyAllowed the run is a dry run that lists what it would create. Check parses afterwards with flextools_try_word, not in this script. Report through report.Info/Warning/Error only.
"""
# --- PARAMS ---
MORPHEMES = [
    # (form with affix markers, gloss, POS name or None)
    ("zzRecipeTestku-", "zzINF", None),
    ("zzRecipeTestsoma", "zzread", None),
]
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


def split_markers(raw):
    """Return (bare form, morph type name) from a marked form."""
    form = nfc(raw).strip()
    if form.startswith("-") and form.endswith("-") and len(form) > 2:
        return form[1:-1], "infix"
    if form.endswith("-"):
        return form[:-1], "prefix"
    if form.startswith("-"):
        return form[1:], "suffix"
    if form.startswith("="):
        return form[1:], "enclitic"
    if form.endswith("="):
        return form[:-1], "proclitic"
    return form, "stem"


# Morph type name, object and stem-ness, keyed by lowercase name and by GUID.
mt_by_name = {}
mt_name_by_guid = {}
for name, mt, is_stem in project.LexEntry.GetAvailableMorphTypes():
    mt_by_name[name.lower()] = (name, is_stem)
    mt_name_by_guid[str(mt.Guid)] = name

rows = []
ok = True
for raw, gloss, pos_name in MORPHEMES:
    form, mt_name = split_markers(raw)
    if not form:
        report.Error(f"{raw!r}: empty form after removing markers")
        ok = False
        continue
    if mt_name not in mt_by_name:
        report.Error(f"{raw!r}: morph type {mt_name!r} not in this project")
        ok = False
        continue
    pos = None
    if pos_name:
        pos = project.POS.Find(pos_name)
        if pos is None:
            report.Error(f"{raw!r}: unknown POS {pos_name!r}")
            ok = False
            continue
    rows.append((raw, form, mt_by_name[mt_name], gloss, pos))

if not ok:
    report.Error("validation failed: fix PARAMS before any write")
else:
    # (lexeme form, morph type name) -> entries, for the existence check.
    by_form = {}
    for entry in project.LexEntry.GetAll():
        mt = project.LexEntry.GetMorphType(entry)
        mt_name = mt_name_by_guid.get(str(mt.Guid), "?") if mt is not None else "?"
        lf = nfc(project.LexEntry.GetLexemeForm(entry))
        by_form.setdefault(lf, []).append((mt_name, entry))

    created = skipped = 0
    for raw, form, (mt_name, is_stem), gloss, pos in rows:
        same_form = by_form.get(form, [])
        same_type = [e for n, e in same_form if n.lower() == mt_name.lower()]
        if same_type:
            glosses = [project.Senses.GetGloss(s) for e in same_type for s in project.LexEntry.GetSenses(e)]
            report.Info(f"exists {raw}: {len(same_type)} entr{'y' if len(same_type) == 1 else 'ies'}, glosses={glosses}")
            skipped += 1
            continue
        others = sorted(set(n for n, _e in same_form))
        if others:
            report.Warning(f"{raw}: form exists only as {others}; creating a {mt_name}")
        if not modifyAllowed:
            report.Info(f"(dry run) would create {raw} as {mt_name} gloss={gloss!r} POS={project.POS.GetName(pos) if pos else None}")
            continue
        if modifyAllowed:
            entry = project.LexEntry.Create(form, mt_name, create_blank_sense=False)
            sense = project.LexEntry.AddSense(entry, gloss)
            if is_stem:
                project.MSA.CreateStem(sense, pos)
            else:
                project.MSA.CreateUnclassifiedAffix(sense, pos)
            by_form.setdefault(form, []).append((mt_name, entry))
            created += 1
            report.Info(f"created {project.LexEntry.GetHeadword(entry)} as {mt_name} gloss={gloss!r} guid={project.LexEntry.GetGuid(entry)}")
    report.Info(f"done: {created} created, {skipped} already present, {len(rows) - created - skipped} not created")
