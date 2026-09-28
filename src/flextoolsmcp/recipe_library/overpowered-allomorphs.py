"""
id: overpowered-allomorphs
intent: Identify allomorphs with no constraints (no environments, features, stem names, or classes) in free variation, and optionally remove homophonous duplicates
match_terms: ["overpowered allomorph", "free variation allomorph", "allomorph with no constraint", "allomorph with no environment", "homophonous duplicate", "abstract lexeme form"]
entities: ["LexEntry", "MoAllomorph", "MoStemAllomorph", "PhEnvironment"]
operations: ["read", "delete"]
requires_write: true
origin: FLExTools module Overpowered_Allomorphs.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 6
notes: Reports allomorphs causing free variation (no environments, features, stem names, or inflection classes), and abstract lexeme forms paired with non-abstract allomorphs (the lexeme may then never surface). Checks are scoped to alternate allomorphs only, never the lexeme form itself, since comparing the lexeme form to itself would trivially count as a homophonous duplicate. Optionally removes homophonous allomorphs (same form as the lexeme, no environment) via project.Allomorphs.Delete(); deletion only happens under REMOVE_HOMOPHONOUS_DUPLICATES and modifyAllowed together, and the dry-run message only appears when that toggle is actually on. Stem-name and inflection-class checks need raw LCM access via separate IMoStemAllomorph/IMoAffixAllomorph casts (flexicon gap #580); the required-features check is also raw (flexicon gap #581).
"""
# --- PARAMS ---
REPORT_ABSTRACT_MISMATCH = True  # report abstract lexeme with non-abstract allomorphs
REPORT_EMPTY = True  # report empty allomorphs and lexeme forms
REPORT_FREE_VARIATION = True  # report unconstrained allomorphs in free variation
REMOVE_HOMOPHONOUS_DUPLICATES = False  # remove homophonous duplicates with no environments (requires write_enabled)
# --- END PARAMS ---
import unicodedata
from SIL.LCModel import IMoStemAllomorph, IMoAffixAllomorph

to_delete = []

for entry in project.LexEntry.GetAll():
    entry_allos = list(project.Allomorphs.GetAll(entry))
    lf_obj = entry_allos[0] if entry_allos else None
    lf = project.Allomorphs.GetForm(lf_obj) if lf_obj else ""
    lf_norm = unicodedata.normalize("NFC", lf or "")

    # Check for empty lexeme form
    if REPORT_EMPTY and (not lf_obj or not lf):
        report.Warning(f'Entry has an empty lexeme form', project.BuildGotoURL(entry))
        continue

    # Check for abstract lexeme form with non-abstract allomorphs
    lf_abstract = project.Allomorphs.GetIsAbstract(lf_obj)
    if REPORT_ABSTRACT_MISMATCH and lf_abstract:
        for allo in entry_allos[1:]:
            if not project.Allomorphs.GetIsAbstract(allo):
                alt_form = project.Allomorphs.GetForm(allo)
                report.Warning(
                    f'"{lf}" has abstract lexeme form with non-abstract allomorph "{alt_form}". Lexeme form may never surface.',
                    project.BuildGotoURL(entry),
                )

    # Check each alternate allomorph (NOT the lexeme form itself -- comparing
    # the lexeme form against itself would trivially count as a "homophonous
    # duplicate with no environment" on every single-allomorph entry; the
    # original FLExTools source iterates entry.AlternateFormsOS, never the
    # lexeme form, for exactly this reason)
    for allo in entry_allos[1:]:
        alt_form = unicodedata.normalize("NFC", project.Allomorphs.GetForm(allo) or "")

        # Check for empty allomorph
        if REPORT_EMPTY and (not alt_form or alt_form == ""):
            report.Warning(f'"{lf}" has an empty allomorph', project.BuildGotoURL(entry))
            continue

        has_environment = len(project.Allomorphs.GetPhoneEnv(allo)) > 0
        has_inflection_class = False
        has_features = False
        has_stem_name = False

        # Check for stem name on stem allomorphs (flexicon gap #580)
        try:
            stem_allo = IMoStemAllomorph(allo.lcm_object)  # raw-lcm: stem name not wrapped (flexicon gap #580)
            if stem_allo.StemNameRA is not None:
                has_stem_name = True
        except Exception:
            pass

        # Check for inflection classes and required morphosyntactic features
        # on affix allomorphs -- InflectionClassesRC/MsEnvFeaturesOA live on
        # IMoAffixAllomorph, not on stem allomorphs (flexicon gap #580/#581)
        try:
            affix_allo = IMoAffixAllomorph(allo.lcm_object)  # raw-lcm: inflection classes not wrapped (flexicon gap #580)
            if affix_allo.InflectionClassesRC:  # raw-lcm: flexicon gap #580
                has_inflection_class = len(affix_allo.InflectionClassesRC) > 0
            if affix_allo.MsEnvFeaturesOA:  # raw-lcm: required features not wrapped (flexicon gap #581)
                has_features = True
        except Exception:
            pass

        # For allomorphs that differ from lexeme form
        if alt_form != lf_norm:
            if REPORT_FREE_VARIATION and not has_environment and not has_inflection_class and not has_features and not has_stem_name:
                report.Info(
                    f'"{lf}" has unconstrained allomorph "{alt_form}" (no environments, features, stem names, or classes). Free variation.',
                    project.BuildGotoURL(entry),
                )

        # For homophonous allomorphs (same form as lexeme)
        elif alt_form == lf_norm:
            if not has_environment:
                report.Warning(
                    f'"{lf}" has homophonous allomorph with no environments',
                    project.BuildGotoURL(entry),
                )
                if REMOVE_HOMOPHONOUS_DUPLICATES and modifyAllowed:
                    to_delete.append((allo, entry, alt_form))
                elif not modifyAllowed and REMOVE_HOMOPHONOUS_DUPLICATES:
                    report.Info(f'(dry run) would delete homophonous allomorph: "{alt_form}"')
            else:
                report.Info(
                    f'"{lf}" has homophonous allomorph "{alt_form}" with environment constraints. Manual review suggested.',
                    project.BuildGotoURL(entry),
                )

# Delete collected allomorphs
for allo, entry, form in to_delete:
    if modifyAllowed:
        try:
            project.Allomorphs.Delete(allo)
            report.Info(f'Deleted homophonous allomorph: "{form}"')
        except Exception as e:
            report.Error(f'Failed to delete homophonous allomorph "{form}": {e}', project.BuildGotoURL(entry))

if to_delete:
    report.Info(f'Removed {len(to_delete)} homophonous duplicate allomorphs')
