"""
id: bulk-set-exception-features
intent: Add or clear exception features on marked senses in bulk by morphological type
match_terms: ["set exception features", "bulk exception feature", "exception feature marking", "mark senses for feature", "exception constraint", "production restriction"]
entities: ["LexEntry", "LexSense", "MoStemMsa", "MoDerivAffMsa", "MoInflAffMsa"]
operations: ["update"]
requires_write: true
origin: FLExTools module Bulk_Set_Exception_Features.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 8
notes: Exception features are not bulk-editable in FLEx UI. This recipe marks senses either by custom field ("x" marker, requires marking senses in bulk edit first) or by exact headword list, then applies or clears the chosen exception feature on the matching MSA field (stem, deriv-from, deriv-to, infl-from). With MORPHTYPE "all", every applicable MSA field is updated, but deriv-from is skipped once deriv-to has already matched on the same MSA to avoid contradictory settings. The feature is looked up via the generic "Exception Features" possibility list rather than scanning MSAs for a match. Applying or clearing the feature on a specific MSA's ProdRestrictRC/FromProdRestrictRC/ToProdRestrictRC needs raw LCM access; no flexicon wrapper exists for those per-MSA reference collections (flexicon gap #574).
"""
# --- PARAMS ---
SELECTION_MODE = "custom_field"  # "custom_field" or "headwords"
CUSTOM_FIELD = "FTFlags"  # name of the custom field to check for "x" marker (ignored if SELECTION_MODE == "headwords")
HEADWORDS = []  # exact headwords to match (ignored if SELECTION_MODE == "custom_field"); empty list = all marked senses
ACTION = "add"  # "add" or "clear"
FEATURE_NAME = ""  # name of exception feature to add; use "" to just clear (ignored if ACTION == "clear")
MORPHTYPE = "all"  # "stem", "deriv_from", "deriv_to", "infl_from", "all"
# --- END PARAMS ---
import unicodedata
from flexicon import FP_ParameterError
from SIL.LCModel import IMoStemMsa, IMoDerivAffMsa, IMoInflAffMsa

def nfc(text):
    return unicodedata.normalize("NFC", text or "")

# Find the exception feature if adding, via the "Exception Features"
# possibility list (generic wrapper; no per-MSA scanning needed).
chosen_feature = None
chosen_feature_label = None
if ACTION == "add" and FEATURE_NAME:
    ef_list = project.PossibilityLists.FindList("Exception Features")
    if ef_list is None:
        report.Error("'Exception Features' possibility list not found in this project")
    else:
        chosen_feature = project.PossibilityLists.FindItem(ef_list, FEATURE_NAME)
        if chosen_feature:
            chosen_feature_label = project.PossibilityLists.GetItemName(chosen_feature)

if ACTION == "add" and FEATURE_NAME and not chosen_feature:
    report.Error(f"Exception feature '{FEATURE_NAME}' not found in any exception feature list")
else:
    # Determine which senses to process
    target_senses = []
    if SELECTION_MODE == "custom_field":
        cf_field = project.CustomFields.FindField("LexSense", CUSTOM_FIELD)
        if not cf_field:
            report.Error(f"Custom field '{CUSTOM_FIELD}' not found on LexSense")
        else:
            for entry in project.LexEntry.GetAll():
                for sense in project.LexEntry.GetSenses(entry):
                    try:
                        marker = project.CustomFields.GetValue(sense, CUSTOM_FIELD)
                    except FP_ParameterError:
                        continue
                    if marker and str(marker).strip().lower() == "x":
                        target_senses.append(sense)
    else:  # headwords
        wanted = set(nfc(h) for h in HEADWORDS) if HEADWORDS else None
        for entry in project.LexEntry.GetAll():
            if wanted is None or nfc(project.LexEntry.GetHeadword(entry)) in wanted:
                for sense in project.LexEntry.GetSenses(entry):
                    target_senses.append(sense)

    # Process marked senses
    changed = 0
    would_change = 0
    for sense in target_senses:
        entry = project.Senses.GetOwningEntry(sense)
        gloss = project.Senses.GetGloss(sense)
        headword = project.LexEntry.GetHeadword(entry)
        meaning = gloss if gloss else project.Senses.GetDefinition(sense)

        # Find MSA and target field based on morphtype
        for msa in project.MSA.GetAll(entry):
            ex_field = None
            msa_type = None

            if MORPHTYPE in ["stem", "all"]:
                if msa.is_stem_msa:
                    stem = IMoStemMsa(msa.as_stem_msa())  # raw-lcm: exception features not wrapped
                    ex_field = stem.ProdRestrictRC  # raw-lcm: exception features not wrapped
                    msa_type = "stem"

            if MORPHTYPE in ["deriv_from", "all"] and not ex_field:
                if msa.is_deriv_aff_msa:
                    deriv = IMoDerivAffMsa(msa.as_deriv_aff_msa())  # raw-lcm: exception features not wrapped
                    ex_field = deriv.FromProdRestrictRC  # raw-lcm: exception features not wrapped
                    msa_type = "deriv_from"

            if MORPHTYPE in ["deriv_to", "all"] and not ex_field:
                if msa.is_deriv_aff_msa:
                    deriv = IMoDerivAffMsa(msa.as_deriv_aff_msa())  # raw-lcm: exception features not wrapped
                    ex_field = deriv.ToProdRestrictRC  # raw-lcm: exception features not wrapped
                    msa_type = "deriv_to"

            if MORPHTYPE in ["infl_from", "all"] and not ex_field:
                if msa.is_infl_aff_msa:
                    infl = IMoInflAffMsa(msa.as_infl_aff_msa())  # raw-lcm: exception features not wrapped
                    ex_field = infl.FromProdRestrictRC  # raw-lcm: exception features not wrapped
                    msa_type = "infl_from"

            if ex_field and msa_type:
                if ACTION == "clear":
                    if modifyAllowed:
                        try:
                            ex_field.Clear()
                            report.Info(f"cleared exception features from sense '{meaning}' of entry '{headword}' ({msa_type})", project.BuildGotoURL(sense))
                            changed += 1
                        except Exception as e:
                            report.Error(f"error clearing exception features from sense '{meaning}' of entry '{headword}': {e}", project.BuildGotoURL(sense))
                    else:
                        report.Info(f"(dry run) would clear exception features from sense '{meaning}' of entry '{headword}' ({msa_type})", project.BuildGotoURL(sense))
                        would_change += 1
                else:  # add
                    if chosen_feature and chosen_feature not in ex_field:
                        if modifyAllowed:
                            try:
                                ex_field.Add(chosen_feature)
                                report.Info(f"added exception feature '{chosen_feature_label}' to sense '{meaning}' of entry '{headword}' ({msa_type})", project.BuildGotoURL(sense))
                                changed += 1
                            except Exception as e:
                                report.Error(f"error adding exception feature to sense '{meaning}' of entry '{headword}': {e}", project.BuildGotoURL(sense))
                        else:
                            report.Info(f"(dry run) would add exception feature '{chosen_feature_label}' to sense '{meaning}' of entry '{headword}' ({msa_type})", project.BuildGotoURL(sense))
                            would_change += 1

    if modifyAllowed:
        report.Info(f"total changed: {changed}")
    else:
        report.Info(f"total to change: {would_change}")
