"""
id: wordform-case-variants
intent: Find every case variant of target wordforms, with occurrence, parser and human counts
match_terms: ["case variants", "capitalized wordform", "wordform case variants", "same word different case", "uppercase and lowercase wordforms"]
entities: ["WfiWordform", "WfiAnalysis"]
operations: ["read", "iterate", "search"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/find_variants.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
notes: Sentence-initial capitals create separate wordforms that the parser handles separately. Comparison is casefold after NFC normalization of both sides. parser and human count the analyses the parser produced and the ones a human approved.
"""
# --- PARAMS ---
TARGETS = ["ndiwe", "pikakhala"]  # wordforms to find in every capitalization
# --- END PARAMS ---
import unicodedata


def norm(text):
    return unicodedata.normalize("NFC", text or "").casefold()


targets = set(norm(t) for t in TARGETS)
found = set()
for wf in project.Wordforms.GetAll():
    form = project.Wordforms.GetForm(wf)
    if norm(form) not in targets:
        continue
    found.add(norm(form))
    analyses = project.Wordforms.GetAnalyses(wf)
    parser = sum(1 for a in analyses if project.WfiAnalyses.IsComputerApproved(a))
    human = sum(1 for a in analyses if project.WfiAnalyses.IsHumanApproved(a))
    report.Info(f"{form}\tcount={project.Wordforms.GetOccurrenceCount(wf)}\tparser={parser}\thuman={human}")
for target in sorted(targets - found):
    report.Warning(f"no wordform {target}")
