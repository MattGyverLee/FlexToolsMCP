"""
id: bulk-set-stem-name
intent: Add or clear stem names on marked allomorphs in bulk with POS validation
match_terms: ["set stem name", "bulk stem name", "mark allomorphs for stem name", "stem name by POS", "stem name assignment"]
entities: ["LexEntry", "MoAllomorph", "MoStemName", "PartOfSpeech"]
operations: ["update"]
requires_write: true
origin: FLExTools module Bulk_Set_Stem_Name.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 7
notes: Stem names are not bulk-editable in FLEx UI. This recipe marks allomorphs either by custom field ("x" marker, requires marking allomorphs in bulk edit first) or by exact headword list, then applies or clears stem names on each. Writes validate that the allomorph's entry POS matches, or descends from, the stem name's owning POS by walking project.POS.GetParent() to the root; a mismatch is skipped with a warning rather than written. Writing StemNameRA must go through the raw LCM object (allo.lcm_object), not the Allomorph wrapper -- the wrapper has no attribute-write override, so assigning to it would silently set a Python attribute instead of the database field (flexicon gap #573: stem names have no wrapper).
"""
# --- PARAMS ---
SELECTION_MODE = "custom_field"  # "custom_field" or "headwords"
CUSTOM_FIELD = "FTFlags"  # name of the custom field to check for "x" marker (ignored if SELECTION_MODE == "headwords")
HEADWORDS = []  # exact headwords to match (ignored if SELECTION_MODE == "custom_field"); empty list = all marked allomorphs
ACTION = "add"  # "add" or "clear"
STEM_NAME = ""  # name of stem name to add; use "" to just clear (ignored if ACTION == "clear")
LIMIT = 2000  # max allomorphs to process
# --- END PARAMS ---
import unicodedata
from SIL.LCModel import IMoStemAllomorph, IMoStemName

def nfc(text):
    return unicodedata.normalize("NFC", text or "")

def pos_matches_or_is_descendant(candidate_pos, target_pos):
    """Walk up the POS hierarchy from candidate_pos looking for target_pos."""
    p = candidate_pos
    while p is not None:
        if p == target_pos:
            return True
        p = project.POS.GetParent(p)
    return False

# Find the stem name if adding
chosen_stem_name = None
chosen_pos = None
chosen_stem_label = None
if ACTION == "add" and STEM_NAME:
    for pos in project.POS.GetAll():
        pos_name = project.POS.GetName(pos)
        try:
            for raw_stem_name in pos.StemNamesOC:  # raw-lcm: stem names not wrapped (flexicon gap #573)
                stem_name = IMoStemName(raw_stem_name)  # raw-lcm: stem names not wrapped
                sn_name = str(stem_name.Name.AnalysisDefaultWritingSystem.Text) if stem_name.Name else ""  # raw-lcm: stem names not wrapped
                if nfc(sn_name) == nfc(STEM_NAME):
                    chosen_stem_name = stem_name
                    chosen_pos = pos
                    chosen_stem_label = f"{pos_name} - {sn_name}"
                    break
        except Exception:
            pass
        if chosen_stem_name:
            break

if ACTION == "add" and STEM_NAME and not chosen_stem_name:
    report.Error(f"stem name '{STEM_NAME}' not found in any POS")
else:
    # Determine which allomorphs to process
    target_allos = []
    if SELECTION_MODE == "custom_field":
        cf_field = project.CustomFields.FindField("MoForm", CUSTOM_FIELD)
        if not cf_field:
            report.Error(f"custom field '{CUSTOM_FIELD}' not found on allomorphs (MoForm)")
        else:
            for entry in project.LexEntry.GetAll():
                for allo in project.Allomorphs.GetAll(entry):
                    try:
                        marker = project.CustomFields.GetValue(allo, CUSTOM_FIELD)
                        if marker and str(marker).strip().lower() == "x":
                            target_allos.append((entry, allo))
                    except Exception:
                        pass
    else:  # headwords
        wanted = set(nfc(h) for h in HEADWORDS) if HEADWORDS else None
        for entry in project.LexEntry.GetAll():
            if wanted is None or nfc(project.LexEntry.GetHeadword(entry)) in wanted:
                for allo in project.Allomorphs.GetAll(entry):
                    target_allos.append((entry, allo))

    # Process marked allomorphs
    changed = 0
    would_change = 0
    for idx, (entry, allo) in enumerate(target_allos):
        if changed + would_change >= LIMIT:
            report.Warning(f"limit of {LIMIT} reached; process again to continue")
            break

        headword = project.LexEntry.GetHeadword(entry)
        form = project.Allomorphs.GetForm(allo)

        if not allo.is_stem_allomorph:
            report.Warning(f"allomorph '{form}' of entry '{headword}' is not a stem allomorph; skipping", project.BuildGotoURL(allo))
            continue

        # Stem names are a raw LCM field (flexicon gap #573); write via the
        # raw LCM object, not the wrapper (wrapper has no __setattr__, a
        # write to the wrapper attribute would silently be a no-op).
        concrete_allo = IMoStemAllomorph(allo.lcm_object)  # raw-lcm: stem names not wrapped

        if ACTION == "clear":
            try:
                if concrete_allo.StemNameRA:  # raw-lcm: stem names not wrapped
                    if modifyAllowed:
                        concrete_allo.StemNameRA = None  # raw-lcm: stem names not wrapped
                        report.Info(f"cleared stem name from allomorph '{form}' of entry '{headword}'", project.BuildGotoURL(allo))
                        changed += 1
                    else:
                        report.Info(f"(dry run) would clear stem name from allomorph '{form}' of entry '{headword}'", project.BuildGotoURL(allo))
                        would_change += 1
            except Exception as e:
                report.Error(f"error clearing stem name from allomorph '{form}' of entry '{headword}': {e}", project.BuildGotoURL(entry))
        else:  # add
            if chosen_stem_name:
                try:
                    if concrete_allo.StemNameRA is None:  # raw-lcm: stem names not wrapped
                        # Validate POS match: entry's stem-MSA POS must be, or
                        # descend from, the stem name's owning POS.
                        pos_match = False
                        for msa in project.MSA.GetAll(entry):
                            if msa.is_stem_msa and msa.pos_main:
                                if pos_matches_or_is_descendant(msa.pos_main, chosen_pos):
                                    pos_match = True
                                    break

                        if not pos_match:
                            report.Warning(f"POS mismatch for allomorph '{form}' of entry '{headword}'; skipping", project.BuildGotoURL(entry))
                        else:
                            if modifyAllowed:
                                concrete_allo.StemNameRA = chosen_stem_name  # raw-lcm: stem names not wrapped
                                report.Info(f"added stem name '{chosen_stem_label}' to allomorph '{form}' of entry '{headword}'", project.BuildGotoURL(allo))
                                changed += 1
                            else:
                                report.Info(f"(dry run) would add stem name '{chosen_stem_label}' to allomorph '{form}' of entry '{headword}'", project.BuildGotoURL(allo))
                                would_change += 1
                    else:
                        report.Warning(f"stem name already set on allomorph '{form}' of entry '{headword}'; skipping", project.BuildGotoURL(allo))
                except Exception as e:
                    report.Error(f"error processing allomorph '{form}' of entry '{headword}': {e}", project.BuildGotoURL(entry))

    if modifyAllowed:
        report.Info(f"total changed: {changed}")
    else:
        report.Info(f"total to change: {would_change}")
