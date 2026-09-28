"""
id: lowercase-capitalized-wordforms
intent: Rename capitalized wordforms to lowercase, removing user parses when the parser failed
match_terms: ["lowercase wordforms", "rename capitalized forms", "remove failed parses", "capitalize variant entry", "wordform naming"]
entities: ["WfiWordform", "WfiAnalysis"]
operations: ["update"]
requires_write: true
origin: FLExTools module RenameWordformsToLower.py (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: Only touches wordforms whose first character is uppercase. A capitalized wordform with no analyses is lowercased immediately. One with analyses is only lowercased if the parser itself disapproved at least one analysis ("failed by parser"); in that case, any human evaluation on that wordform's analyses is also cleared via SetApprovalStatus(..., UNAPPROVED), which removes the human evaluation record without deleting the analysis. Wordforms whose analyses were not parser-rejected are left untouched. Reading an evaluation's .Approves flag needs raw access on the ICmAgentEvaluation object returned by GetAgentEvaluation/GetHumanEvaluation, since it is a plain property with no flexicon wrapper (flexicon gap #582).
"""
# --- PARAMS ---
# --- END PARAMS ---
import unicodedata
from flexicon import ApprovalStatusTypes

def norm(text):
    return unicodedata.normalize("NFC", text or "")

count = 0
to_clear = []

for wf in project.Wordforms.GetAll():
    form = project.Wordforms.GetForm(wf)
    if not form or not form[0].isupper():
        continue

    analyses = project.Wordforms.GetAnalyses(wf)

    if len(analyses) == 0:
        # No analyses: safe to lowercase immediately
        if modifyAllowed:
            project.Wordforms.SetForm(wf, form.lower())
            count += 1
            report.Info(f"no analyses, lowercased {form} to {form.lower()}")
        else:
            report.Info(f"(dry run) would lowercase {form} (no analyses)")
    else:
        # Check if any analysis has parser failure (parser disapproved)
        parser_failed = False
        for analysis in analyses:
            agent_eval = project.WfiAnalyses.GetAgentEvaluation(analysis)
            if agent_eval is not None and not agent_eval.Approves:  # flexicon gap: #582 (Approves has no wrapper getter)
                parser_failed = True
                break

        if parser_failed:
            # Collect human evaluations to clear from this wordform's analyses
            for analysis in analyses:
                if project.WfiAnalyses.GetHumanEvaluation(analysis) is not None:
                    to_clear.append((wf, form, analysis))

            # Lowercase the wordform
            if modifyAllowed:
                project.Wordforms.SetForm(wf, form.lower())
                count += 1
                report.Info(f"failed user analysis, lowercased {form} to {form.lower()}")
            else:
                report.Info(f"(dry run) would lowercase {form} (failed parser analysis)")

# Clear collected human evaluations (second pass to avoid iterator issues).
# SetApprovalStatus(..., UNAPPROVED) removes the evaluation entirely.
cleared_count = 0
for wf, form, analysis in to_clear:
    if modifyAllowed:
        try:
            project.WfiAnalyses.SetApprovalStatus(analysis, ApprovalStatusTypes.UNAPPROVED)
            cleared_count += 1
            report.Info(f"cleared human evaluation for {form}")
        except Exception as e:
            report.Error(f"failed to clear evaluation: {e}")
    else:
        report.Info(f"(dry run) would clear human evaluation for {form}")

if not modifyAllowed:
    report.Warning("Run with write_enabled=True to actually make changes")

report.Info(f"{count} capitalized wordforms changed to lowercase")
if to_clear:
    report.Info(f"{cleared_count if modifyAllowed else len(to_clear)} human evaluations {'cleared' if modifyAllowed else 'would be cleared'}")
