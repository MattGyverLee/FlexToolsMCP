"""
id: phoneme-feature-uniqueness
intent: Validate phoneme inventory has no duplicates; report phonemes with no features
match_terms: ["check phoneme uniqueness", "find duplicate phoneme features", "phoneme inventory validation", "phoneme features unique", "phoneme quality check"]
entities: ["IPhPhoneme", "IFsClosedValue", "IFsFeatStruc"]
operations: ["read"]
requires_write: false
origin: FLExTools modules CheckPhonemeUniqueness.py (Matthew Lee, Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 3
notes: Reports duplicate feature bundles (phonemes with identical feature specs) and phonemes with no feature structure. Essential before running parser tests. Raw LCM used to access IFsClosedValue specs from phoneme feature structure (flexicon gap #578: no describe-helper for phonological feature structs).
"""
# --- PARAMS ---
# No tunable parameters; checks all phonemes in the project
# --- END PARAMS ---
from SIL.LCModel import IFsClosedValue

phoneme_to_feats = {}
problem = False

for phoneme in project.Phonemes.GetAll():
    phoneme_name = project.Phonemes.GetName(phoneme)
    feat_struct = project.Phonemes.GetFeatures(phoneme)

    if not feat_struct:
        report.Warning(f"Phoneme '{phoneme_name}' has no features defined", project.BuildGotoURL(phoneme))
        continue

    # Get feature specs from the feature structure
    feature_abbrs = []
    for spec in feat_struct.FeatureSpecsOC:  # raw-lcm: flexicon gap #578
        spec_value = IFsClosedValue(spec)  # raw-lcm: flexicon gap #578
        value_obj = spec_value.ValueRA  # raw-lcm: flexicon gap #578
        if value_obj and value_obj.Abbreviation:
            abbr_str = project.PhonFeatures.GetAbbreviation(value_obj)
            if abbr_str:
                feature_abbrs.append(abbr_str)

    feature_abbrs.sort()
    feat_concat = "".join(feature_abbrs)

    if feat_concat in phoneme_to_feats:
        report.Error(
            f"Phoneme '{phoneme_name}' has identical features as '{phoneme_to_feats[feat_concat]}' (features: {feat_concat})",
            project.BuildGotoURL(phoneme)
        )
        problem = True
    elif feat_concat:
        phoneme_to_feats[feat_concat] = phoneme_name

if not problem:
    report.Info(f"All {len(phoneme_to_feats)} phonemes are unique by feature combination")
