"""
id: form-usage-before-edit
intent: List every analysis that uses an entry's forms, with human and parser opinion, before changing, moving or deleting those forms
match_terms: ["form usage", "who uses this allomorph", "analyses that use this entry", "before editing an allomorph", "before deleting a form", "allomorph references", "filing scope"]
entities: ["LexEntry", "MoForm", "WfiAnalysis", "WfiMorphBundle"]
operations: ["read", "iterate", "search"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/allomorph_refs.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
notes: Run this BEFORE moving, deleting or changing an entry's forms. Every word listed is in the filing scope of the change. Any human opinion (status other than UNAPPROVED) means stop and ask the linguist first. Bundles are matched through the allomorph's owning entry GUID, never HVOs. The headword is compared after NFC normalization.
"""
# --- PARAMS ---
HEADWORD = "khala"  # exact headword of the entry whose forms you plan to change
# --- END PARAMS ---
import unicodedata

target = unicodedata.normalize("NFC", HEADWORD)
entry = None
for e in project.LexEntry.GetAll():
    if unicodedata.normalize("NFC", project.LexEntry.GetHeadword(e)) == target:
        entry = e
        break
if entry is None:
    report.Error(f"no entry with headword {HEADWORD}")
else:
    entry_guid = project.LexEntry.GetGuid(entry)
    forms = [project.Allomorphs.GetForm(a) for a in project.Allomorphs.GetAll(entry)]
    report.Info(f"forms in order (lexeme form first): {forms}", project.BuildGotoURL(entry))
    uses = 0
    human_count = 0
    for wf in project.Wordforms.GetAll():
        for analysis in project.Wordforms.GetAnalyses(wf):
            for bundle in project.WfiAnalyses.GetMorphBundles(analysis):
                morph = project.WfiMorphBundles.GetMorph(bundle)
                if morph is None:
                    continue
                owner = project.Allomorphs.GetOwningEntry(morph)
                if owner is None or project.LexEntry.GetGuid(owner) != entry_guid:
                    continue
                uses += 1
                status = project.WfiAnalyses.GetApprovalStatus(analysis).name
                if status != "UNAPPROVED":
                    human_count += 1
                report.Info(
                    f"{project.Wordforms.GetForm(wf)} occ={project.Wordforms.GetOccurrenceCount(wf)} "
                    f"form={project.Allomorphs.GetForm(morph)} human={status} "
                    f"parser={project.WfiAnalyses.IsComputerApproved(analysis)}"
                )
    report.Info(f"morpheme uses: {uses}; analyses with a human opinion: {human_count}")
    if human_count:
        report.Warning("human-approved or rejected analyses use these forms: ask before changing them")
