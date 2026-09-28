"""
id: reorder-affix-templates
intent: Sort affix templates by name for a selected part of speech (numerically if all names start with numbers, else alphabetically)
match_terms: ["sort affix templates", "reorder templates", "template ordering", "reorganize templates by name", "numerical template sort", "alphabetical template sort"]
entities: ["PartOfSpeech", "AffixTemplate"]
operations: ["update"]
requires_write: true
origin: FLExTools module Reorder_Affix_Templates.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 1
notes: Reorders affix templates for a single POS by sorting on name: numerically if every template name starts with a number, alphabetically otherwise. POS_NAME must match exactly one POS after NFC normalization, or the recipe reports the mismatch and does nothing. Dry run always shows the intended sort order; write mode applies it by matching each template's Guid and moving it to its sorted position via raw LCM access to AffixTemplatesOS and MoveTo, since neither is wrapped by flexicon (flexicon gap #580).
"""
# --- PARAMS ---
POS_NAME = "Verb"
# --- END PARAMS ---

import re
import unicodedata
from SIL.LCModel import IPartOfSpeech


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


def starts_with_number(s):
    return bool(re.match(r'^\d+', s))


# Validate and find POS
matches = [p for p in project.POS.GetAll() if nfc(project.POS.GetName(p)) == nfc(POS_NAME)]

if len(matches) != 1:
    if matches:
        report.Error(f"POS '{POS_NAME}' matches {len(matches)} entries; must match exactly 1")
    else:
        avail = sorted(project.POS.GetName(p) for p in project.POS.GetAll())
        report.Error(f"POS '{POS_NAME}' not found. Available: {avail[:5]}")
else:
    pos = matches[0]
    pos_name = project.POS.GetName(pos)
    templates = list(project.MorphRules.GetAllAffixTemplatesForPOS(pos))

    if len(templates) <= 1:
        report.Info(f"{pos_name} has {len(templates)} template(s); nothing to sort.")
    else:
        names = [t.name for t in templates]
        all_numeric = all(starts_with_number(n) for n in names)

        if all_numeric:
            report.Info(f"Sorting {pos_name} templates numerically.")
            sorted_templates = sorted(templates, key=lambda t: int(re.match(r'^\d+', t.name).group()))
        else:
            report.Info(f"Sorting {pos_name} templates alphabetically.")
            sorted_templates = sorted(templates, key=lambda t: t.name)

        report.Info(f"Current order:")
        for t in templates:
            report.Info(f"  {t.name}")

        report.Info(f"New order:")
        for t in sorted_templates:
            report.Info(f"  {t.name}")

        if modifyAllowed:
            try:
                coll = IPartOfSpeech(pos).AffixTemplatesOS  # raw-lcm: flexicon gap #580 (direct access to collection)
                for new_idx, target in enumerate(sorted_templates):
                    for cur_idx, t in enumerate(coll):
                        if t.Guid == target.concrete.Guid:
                            if cur_idx != new_idx:
                                coll.MoveTo(cur_idx, cur_idx, coll, new_idx)  # raw-lcm: flexicon gap #580 (MoveTo not wrapped)
                            break
                report.Info(f"Sorted {pos_name} templates.")
            except Exception as e:
                report.Error(f"Error sorting {pos_name} templates: {e}")
        else:
            report.Info("(dry run) Run with modifyAllowed=True to apply sort.")
