"""
id: feature-system-inventory
intent: List closed features with their values, and per POS list which inflectable features it takes
match_terms: ["feature inventory", "grammar features", "inflectable features by POS", "feature values", "feature system", "which features inflect this POS"]
entities: ["IFsClosedFeature", "IFsComplexFeature", "IPartOfSpeech", "IFsSymFeatVal"]
operations: ["read"]
requires_write: false
origin: FLExTools modules RuleAssistant.py (getFeatureData) and Utils.py (getAllInflectableFeatures), ExtractBilingualLexicon.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 4
notes: Lists all closed features with their possible values (name plus abbreviation), then, per POS (filtered by POS_FILTER prefix match), which features are inflectable for that category. project.InflectionFeatures.FeatureGetAll/FeatureGetValues are real wrappers, but there is no generic Name/Abbreviation getter for a feature or value, no closed-vs-complex feature discriminator, and no wrapper for a POS's inflectable-features collection -- all three go through raw LCM access (ClassName check, InflectableFeatsRC, and a direct ITsString read), covering flexicon gap #577.
"""
# --- PARAMS ---
POS_FILTER = ""  # POS name filter; "" = all. Use a specific POS name to limit output (e.g., "Verb")
# --- END PARAMS ---
import unicodedata
from SIL.LCModel.Core.KernelInterfaces import ITsString

def nfc(text):
    return unicodedata.normalize("NFC", text or "")

ws_handle = project.GetDefaultAnalysisWSHandle()

def get_name(obj):
    try:
        return nfc(ITsString(obj.Name.get_String(ws_handle)).Text) or None  # raw-lcm: no generic Name getter (flexicon gap #577)
    except Exception:
        return None

def get_abbreviation(obj):
    try:
        return nfc(ITsString(obj.Abbreviation.get_String(ws_handle)).Text) or None  # raw-lcm: no generic Abbreviation getter (flexicon gap #577)
    except Exception:
        return None

# First, collect all closed features with their values
report.Info("=== Closed Features ===")
feature_list = []
for feature in project.InflectionFeatures.FeatureGetAll():
    if feature.ClassName != "FsClosedFeature":  # raw-lcm: closed vs complex feature discrimination (flexicon gap #577)
        continue
    feat_name = get_name(feature) or str(feature)
    feature_list.append(feat_name)

    value_strs = []
    for val in project.InflectionFeatures.FeatureGetValues(feature):
        val_abbr = get_abbreviation(val)
        if val_abbr:
            value_strs.append(val_abbr)

    if value_strs:
        report.Info(f"  {feat_name}: {', '.join(value_strs)}")
    else:
        report.Warning(f"  {feat_name}: (no values)")

# Second, list inflectable features per POS
report.Info("\n=== Inflectable Features by POS ===")
for pos in project.POS.GetAll():
    pos_name = project.POS.GetName(pos)

    if POS_FILTER and not nfc(pos_name).startswith(nfc(POS_FILTER)):
        continue

    # Get inflectable features for this POS (no flexicon wrapper: flexicon gap #577)
    infl_feature_names = []
    for infl_feat in pos.InflectableFeatsRC:  # raw-lcm: InflectableFeatsRC not wrapped (flexicon gap #577)
        feat_name = get_name(infl_feat) or str(infl_feat)
        infl_feature_names.append(feat_name)

    if infl_feature_names:
        report.Info(f"  {pos_name}: {', '.join(infl_feature_names)}")
    else:
        report.Info(f"  {pos_name}: (no inflectable features)")

report.Info(f"\nTotal closed features: {len(feature_list)}")
