"""
id: wordform-analyses
intent: Show the existing analyses (morph and gloss per morpheme) of given words, with human and parser approval
match_terms: ["wordform analyses", "how is this word analyzed", "existing analyses of a word", "morpheme breakdown of a word", "interlinear analysis of a word", "comparator analyses", "parse a wordform and get morphological decomposition", "morph bundles of a wordform", "verify parses of words"]
entities: ["WfiWordform", "WfiAnalysis", "WfiMorphBundle"]
operations: ["read", "iterate", "search"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/wordform_analyses.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
notes: Words are matched case-insensitively after NFC normalization of both sides. Each analysis line shows allomorph form:gloss per morpheme; "?" means the bundle has no allomorph or sense linked. status is the human approval; parser=True means the parser also produced it.
"""
# --- PARAMS ---
WORDS = ["pikakhala", "ampwaza", "ndiwe"]  # surface wordforms, any case
# --- END PARAMS ---
import unicodedata


def norm(text):
    return unicodedata.normalize("NFC", text or "").casefold()


probe = set(norm(w) for w in WORDS)
found = set()
for wf in project.Wordforms.GetAll():
    form = project.Wordforms.GetForm(wf)
    if norm(form) not in probe:
        continue
    found.add(norm(form))
    analyses = project.Wordforms.GetAnalyses(wf)
    parser = sum(1 for a in analyses if project.WfiAnalyses.IsComputerApproved(a))
    human = sum(1 for a in analyses if project.WfiAnalyses.IsHumanApproved(a))
    report.Info(
        f"== {form} count={project.Wordforms.GetOccurrenceCount(wf)} analyses={len(analyses)} parser={parser} human={human}"
    )
    for analysis in analyses:
        parts = []
        for bundle in project.WfiAnalyses.GetMorphBundles(analysis):
            morph = project.WfiMorphBundles.GetMorph(bundle)
            morph_form = project.Allomorphs.GetForm(morph) if morph else "?"
            gloss = project.WfiMorphBundles.GetGloss(bundle) or "?"
            parts.append(f"{morph_form}:{gloss}")
        status = project.WfiAnalyses.GetApprovalStatus(analysis).name
        report.Info(
            f"   {' + '.join(parts) or '(no morphemes)'}  status={status} parser={project.WfiAnalyses.IsComputerApproved(analysis)}"
        )
for word in sorted(probe - found):
    report.Warning(f"no wordform {word}")
