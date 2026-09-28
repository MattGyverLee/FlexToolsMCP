"""
id: natural-classes
intent: List each natural class with its member phonemes and their grapheme representations
match_terms: ["natural classes", "list natural classes", "phoneme classes", "phonology", "natural class members", "segment inventory in class"]
entities: ["IPhNaturalClass", "IPhPhoneme", "IPhCode"]
operations: ["read"]
requires_write: false
origin: FLExTools module DoStampSynthesis.py (Ron Lockwood, output_nat_class_info function ~723-753)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 4
notes: Lists every natural class in the project: segment-based classes (IPhNCSegments) with their member phonemes and grapheme codes, feature-based classes (IPhNCFeatures) with their feature abbreviations. project.NaturalClasses.GetType() returns "segments" or "features" (or a ClassName fallback), and that value -- not a string like "PhNCFeatures" -- is what selects which listing path a class takes. There is no describe-helper for phonological feature structs (unlike the morphosyntactic DescribeFeatStruc), so feature-based specs and grapheme representations are read via raw LCM access (flexicon gap #578).
"""
# --- PARAMS ---
# No tunable parameters; lists all natural classes in the project
# --- END PARAMS ---
from SIL.LCModel import IFsClosedValue, IPhCode
from SIL.LCModel.Core.KernelInterfaces import ITsString

def describe_feature_based(nc):
    """Describe a feature-based natural class's feature specs (flexicon gap #578)."""
    fs = project.NaturalClasses.GetFeatures(nc)
    if not fs:
        return []
    labels = []
    for spec in fs.FeatureSpecsOC:  # raw-lcm: no describe-helper for phonological feature structs (flexicon gap #578)
        try:
            spec_value = IFsClosedValue(spec)  # raw-lcm: flexicon gap #578
            value_obj = spec_value.ValueRA  # raw-lcm: flexicon gap #578
            if value_obj:
                abbr = project.PhonFeatures.GetAbbreviation(value_obj)
                if abbr:
                    labels.append(abbr)
        except Exception:
            pass
    return labels

for nat_class in project.NaturalClasses.GetAll():
    class_name = project.NaturalClasses.GetName(nat_class)
    if not class_name:
        continue

    class_type = project.NaturalClasses.GetType(nat_class)

    if class_type == "features":
        feature_labels = describe_feature_based(nat_class)
        if feature_labels:
            report.Info(f"Natural class '{class_name}' (feature-based): [{', '.join(feature_labels)}]")
        else:
            report.Warning(f"Natural class '{class_name}' (feature-based) has no feature specs")
        continue

    # Segment-based (or unrecognized fallback): list member phonemes
    phonemes = project.NaturalClasses.GetPhonemes(nat_class)

    if phonemes:
        grapheme_list = []
        ws_handle = project.GetDefaultVernacularWSHandle()
        for phoneme in phonemes:
            codes = project.Phonemes.GetCodes(phoneme)
            for code in codes:
                if ws_handle:
                    repr_str = ITsString(IPhCode(code).Representation.get_String(ws_handle)).Text  # flexicon gap: #578 (PhCode.Representation)
                    if repr_str:
                        grapheme_list.append(repr_str)

        if grapheme_list:
            report.Info(f"Natural class '{class_name}': {' '.join(grapheme_list)}")
        else:
            report.Warning(f"Natural class '{class_name}' has no grapheme codes")
    else:
        report.Warning(f"Natural class '{class_name}' has no phonemes")
