"""
id: prune-citation-forms-matching-lexeme
intent: Remove citation forms that are identical to the lexeme form (redundant duplicates)
match_terms: ["remove duplicate citation forms", "prune citation form matching lexeme", "clear citation form if it matches lexeme", "clean up citation forms", "remove redundant citation form"]
entities: ["LexEntry"]
operations: ["update"]
requires_write: true
origin: FLExTools module Prune_Citation_Forms That_Match_Lexeme.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: Removes citation forms that are identical (NFC-normalized) to the lexeme form, which is useful when a citation form was accidentally populated with the same value as the lexeme. GetLexemeForm/GetCitationForm can return None for entries with no such form set, so both are coerced to "" before normalizing. All writing is guarded under modifyAllowed; dry run reports what would be cleared.
"""
# --- PARAMS ---
# --- END PARAMS ---
import unicodedata

count = 0
for entry in project.LexEntry.GetAll():
    lexeme_form = unicodedata.normalize("NFC", project.LexEntry.GetLexemeForm(entry) or "")
    citation_form = unicodedata.normalize("NFC", project.LexEntry.GetCitationForm(entry) or "")

    if lexeme_form and citation_form == lexeme_form:
        report.Warning(
            f"Citation form matches lexeme '{lexeme_form}' (removing duplicate)",
            project.BuildGotoURL(entry)
        )
        if modifyAllowed:
            project.LexEntry.SetCitationForm(entry, "")
            count += 1
        elif not modifyAllowed:
            report.Info(f"(dry run) would remove citation form from '{lexeme_form}'")

if modifyAllowed:
    report.Info(f"Removed {count} duplicate citation forms.")
