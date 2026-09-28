"""
id: affix-catalog
intent: Catalog all affixes and clitics by morph type, with gloss, grammatical info, slots, and allomorph environments
match_terms: ["affix inventory", "affix catalog", "list all affixes", "affix by morpheme type", "affix slots", "affix allomorphs", "circumfix", "clitic catalog"]
entities: ["LexEntry", "MoAllomorph", "MoStemMsa", "MoInflAffMsa", "MoDerivAffMsa", "PhEnvironment", "PartOfSpeech"]
operations: ["read", "iterate"]
requires_write: false
origin: FLExTools modules CatalogTargetAffixes.py (Ron Lockwood), DoStampSynthesis.py (~755-924, ~296-370), SetUpTransferRuleGramCat.py (~380-424)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Groups affixes and non-root morphemes (clitics, etc.) by morph type. For each entry, lists gloss, MSA kind (stem/infl-aff/deriv-aff), POS or from-POS/to-POS, and inflectional slots; for each allomorph, shows form and phonological environments. Root/stem exclusion is name-based (morph type name contains "stem" or "root"), matching how FLEx's standard morph-type list names its root-like types (Stem, Root, Bound stem, Bound root) -- the same convention senses-by-gloss.py uses. MSA subtype is read via project.MSA.GetAll(entry) wrappers matched to the sense's MSA by Hvo equality, so no ClassName check or raw cast is needed.
"""
# --- PARAMS ---
MORPH_TYPE_FILTER = ""  # filter by morph type name (e.g. "prefix"; "" = all)
POS_FILTER = ""  # filter by POS abbreviation (e.g. "V"; "" = all)
EXCLUDE_ROOT_TYPES = True  # exclude root/stem morpheme types from output
# --- END PARAMS ---
import unicodedata

morphtype_to_entries = {}

for entry in project.LexEntry.GetAll():
    # Get main form morpheme type
    lf_mt = project.LexEntry.GetMorphType(entry)
    if not lf_mt:
        continue
    mt_name = str(lf_mt)

    # Root/stem morpheme types are excluded by name (Stem, Root, Bound stem,
    # Bound root); everything else (prefix, suffix, infix, circumfix, clitic,
    # etc.) is treated as an affix/non-root morpheme.
    is_root_type = "stem" in mt_name.lower() or "root" in mt_name.lower()
    if EXCLUDE_ROOT_TYPES and is_root_type:
        continue

    # Filter by morph type if specified
    if MORPH_TYPE_FILTER and MORPH_TYPE_FILTER.lower() not in mt_name.lower():
        continue

    morphtype_to_entries.setdefault(mt_name, []).append(entry)

# Report grouped by morpheme type
for morph_type in sorted(morphtype_to_entries.keys()):
    report.Info(f"\n=== {morph_type} ===")

    for entry in morphtype_to_entries[morph_type]:
        hw = project.LexEntry.GetHeadword(entry)
        report.Info(f"\n  Entry: {hw}", project.BuildGotoURL(entry))

        # List senses with glosses and MSA info
        for sense in project.LexEntry.GetSenses(entry):
            gloss = unicodedata.normalize("NFC", project.Senses.GetGloss(sense) or "")
            pos = project.Senses.GetPartOfSpeech(sense)

            # Filter by POS if specified
            if POS_FILTER and (not pos or POS_FILTER not in str(pos)):
                continue

            report.Info(f"    Sense gloss: {gloss}")

            # Find the sense's MSA among the entry's wrapped MSAs (equality
            # is by Hvo, per LCMObjectWrapper) so no ClassName check/cast
            # is needed to tell stem/infl-aff/deriv-aff apart.
            raw_msa = project.Senses.GetMSA(sense)
            msa = None
            if raw_msa is not None:
                msa = next((m for m in project.MSA.GetAll(entry) if m == raw_msa), None)
            if msa is None:
                report.Info(f"      MSA: (none)")
            elif msa.is_stem_msa:
                report.Info(f"      MSA: Stem, POS={pos}")
            elif msa.is_infl_aff_msa:
                slots = project.MSA.GetInflAffMsaSlots(sense)
                slot_names = [project.POS.GetSlotName(s) for s in slots] if slots else []
                report.Info(f"      MSA: Inflectional Affix, POS={pos}, Slots={slot_names}")
            elif msa.is_deriv_aff_msa:
                pos_from = project.POS.GetName(msa.pos_from) if msa.pos_from else None
                pos_to = project.POS.GetName(msa.pos_to) if msa.pos_to else None
                report.Info(f"      MSA: Derivational Affix, {pos_from} -> {pos_to}")
            else:
                report.Info(f"      MSA: Unclassified affix, POS={pos}")

        # List allomorphs with environments
        report.Info(f"    Allomorphs:")
        for i, allo in enumerate(project.Allomorphs.GetAll(entry)):
            form = project.Allomorphs.GetForm(allo)
            is_abstract = project.Allomorphs.GetIsAbstract(allo)
            envs = project.Allomorphs.GetPhoneEnv(allo)

            abstract_note = " (abstract)" if is_abstract else ""
            env_str = "; ".join([project.Environments.GetStringRepresentation(e) for e in envs]) if envs else "(no environments)"
            report.Info(f"      [{i}] form={form}{abstract_note}")
            report.Info(f"          environments: {env_str}")
