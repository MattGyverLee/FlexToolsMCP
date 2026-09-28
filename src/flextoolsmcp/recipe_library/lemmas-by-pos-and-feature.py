"""
id: lemmas-by-pos-and-feature
intent: Find stems and affixes of a part of speech that carry a given inflectional feature value
match_terms: ["feature value inventory", "stems with feature", "affixes with feature", "which entries have this feature", "feature coverage", "stems and affixes by feature"]
entities: ["LexEntry", "MoStemMsa", "MoInflAffMsa", "PartOfSpeech", "InflectionalFeature"]
operations: ["read", "iterate"]
requires_write: false
origin: FLExTools module Utils.py (~1108-1163, ~1165-1222) (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Collects stems (headword plus sense number) and affix glosses that match both a grammar category (POS name, exact match) and a feature value abbreviation. The feature check uses project.InflectionFeatures.DescribeFeatStruc's display string and looks for the abbreviation as a substring, which is simpler than parsing the feature structure recursively but can over-match if the abbreviation also appears as a substring of an unrelated value. Abstract lexeme forms are skipped. project.Senses.GetMSA returns an unwrapped MSA object; its wrapper (needed for .is_stem_msa/.is_infl_aff_msa/.pos_main) is found by Hvo-equality against project.MSA.GetAll(entry), the same technique used in affix-catalog.py.
"""
# --- PARAMS ---
POS_NAME = "Noun"  # exact part of speech name (analysis language)
FEATURE_VALUE = "Sg"  # feature value abbreviation to match (e.g., "Sg", "Fut", "3SG")
# --- END PARAMS ---
import unicodedata


def nfc(text):
    """Normalize text to NFC form for comparison."""
    return unicodedata.normalize("NFC", text or "")


# Find the target POS
target_pos = None
for pos in project.POS.GetAll():
    if nfc(project.POS.GetName(pos)) == nfc(POS_NAME):
        target_pos = pos
        break

if not target_pos:
    report.Error(f"Part of speech '{POS_NAME}' not found")
else:
    stems = []
    affixes = []

    # Collect matching stems and affixes from all entries
    for entry in project.LexEntry.GetAll():
        # Skip entries without a lexeme form (first item from GetAll is the
        # lexeme form; AllomorphOperations has no dedicated GetLexemeForm)
        allo = next(iter(project.Allomorphs.GetAll(entry)), None)
        if not allo:
            continue

        # Skip abstract forms
        if project.Allomorphs.GetIsAbstract(allo):
            continue

        # Iterate through senses
        entry_msas = project.MSA.GetAll(entry)
        for sense_idx, sense in enumerate(project.LexEntry.GetSenses(entry)):
            # Get MSA for this sense (GetMSA returns the raw, unwrapped LCM
            # object; find its wrapper counterpart by Hvo-based equality)
            raw_msa = project.Senses.GetMSA(sense)
            if not raw_msa:
                continue
            msa = next((m for m in entry_msas if m == raw_msa), None)
            if not msa:
                continue

            # Check POS match
            pos_name = None
            if msa.is_stem_msa:
                pos_name = project.POS.GetName(msa.pos_main) if msa.pos_main else None
            elif msa.is_infl_aff_msa:
                pos_name = project.POS.GetName(msa.pos_main) if msa.pos_main else None

            if not pos_name or nfc(pos_name) != nfc(POS_NAME):
                continue

            # Get feature structure description (display string)
            feat_desc = project.InflectionFeatures.DescribeFeatStruc(msa)
            if not feat_desc:
                continue

            # Check if feature value abbreviation is in the description
            if FEATURE_VALUE not in feat_desc:
                continue

            # Match found - collect stem or affix
            if msa.is_stem_msa:
                headword = project.LexEntry.GetHeadword(entry)
                stems.append(f"{headword}.{sense_idx + 1}")
            elif msa.is_infl_aff_msa:
                gloss = project.Senses.GetGloss(sense)
                if gloss:
                    affixes.append(gloss)

    # Report results
    report.Info(f"POS: {POS_NAME}, Feature value: {FEATURE_VALUE}")
    report.Info("")

    report.Info(f"STEMS ({len(stems)} found):")
    if stems:
        for headword in sorted(stems):
            report.Info(f"  {headword}")
    else:
        report.Info("  (none)")

    report.Info("")
    report.Info(f"AFFIXES ({len(affixes)} found):")
    if affixes:
        for gloss in sorted(affixes):
            report.Info(f"  {gloss}")
    else:
        report.Info("  (none)")
