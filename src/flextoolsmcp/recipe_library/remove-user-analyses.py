"""
id: remove-user-analyses
intent: Remove human-evaluated wordform analyses in bulk by approval status or parser failure
match_terms: ["remove user analyses", "delete human wordform evaluations", "clear approved analyses", "parser testing", "remove manual parses", "bulk remove analyses"]
entities: ["WfiWordform", "WfiAnalysis"]
operations: ["update"]
requires_write: true
origin: FLExTools modules Remove_All_User_Analyses.py, Remove_Approved_User_Analyses.py, Remove_Failed_User_Analyses.py (Matthew Lee, Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: MODE controls which human evaluations are removed from analyses: "approved" (default) removes human-approved evaluations, "disapproved" removes human-disapproved ones, "all" removes every human evaluation, and "parser-failed" removes human evaluations on analyses the parser also rejected. This recipe preserves the analyses themselves -- it only clears human evaluation records via SetApprovalStatus(analysis, ApprovalStatusTypes.UNAPPROVED), which removes the human evaluation entirely per its own docs; parser-only evaluations are never touched. Always dry-run first (modifyAllowed=False) to see the count before removing evaluations for real.
"""
# --- PARAMS ---
MODE = "approved"  # "approved" | "disapproved" | "all" | "parser-failed"
WORDFORMS = []  # empty list = all wordforms; provide specific wordforms to limit
# --- END PARAMS ---
import unicodedata
from flexicon import ApprovalStatusTypes

# Validate MODE
valid_modes = {"approved", "disapproved", "all", "parser-failed"}
if MODE not in valid_modes:
    report.Error(f"MODE must be one of {valid_modes}, got {MODE!r}")
else:
    def norm(text):
        return unicodedata.normalize("NFC", text or "").casefold()

    # Build set of wordforms to process (empty = all)
    target_wordforms = set(norm(w) for w in WORDFORMS) if WORDFORMS else None

    # First pass: collect analyses whose human evaluation should be cleared
    to_remove = []
    for wf in project.Wordforms.GetAll():
        form = project.Wordforms.GetForm(wf)
        if target_wordforms is not None and norm(form) not in target_wordforms:
            continue

        for analysis in project.Wordforms.GetAnalyses(wf):
            human_eval = project.WfiAnalyses.GetHumanEvaluation(analysis)
            if human_eval is None:
                continue  # No human evaluation on this analysis

            approves = bool(human_eval.Approves)
            is_computer_approved = project.WfiAnalyses.IsComputerApproved(analysis)

            should_remove = False
            remove_reason = ""

            if MODE == "approved":
                if approves:
                    should_remove = True
                    remove_reason = "human-approved"
            elif MODE == "disapproved":
                if not approves:
                    should_remove = True
                    remove_reason = "human-disapproved"
            elif MODE == "all":
                should_remove = True
                remove_reason = "human-evaluated"
            elif MODE == "parser-failed":
                if not is_computer_approved:
                    should_remove = True
                    remove_reason = "human evaluation on parser-failed analysis"

            if should_remove:
                to_remove.append((wf, form, analysis, remove_reason))

    # Second pass: clear collected human evaluations
    removed_count = 0
    for wf, form, analysis, reason in to_remove:
        if modifyAllowed:
            try:
                project.WfiAnalyses.SetApprovalStatus(analysis, ApprovalStatusTypes.UNAPPROVED)
                removed_count += 1
                report.Info(
                    f"removed {reason} for {form}",
                    project.BuildGotoURL(wf)
                )
            except Exception as e:
                report.Error(f"failed to remove evaluation for {form}: {e}")
        else:
            report.Info(f"(dry run) would remove {reason} for {form}")

    if not modifyAllowed:
        report.Warning("Run with write_enabled=True to actually remove evaluations")

    report.Info(f"Total evaluations processed: {len(to_remove)}")
    if modifyAllowed and removed_count > 0:
        report.Warning(f"Removed {removed_count} evaluations. Make sure to leave the Word Analyses area!")
