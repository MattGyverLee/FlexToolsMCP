"""
id: entry-parser-detail
intent: Show how entries are modelled for the parser: allomorphs in order, environments, abstract forms, MSA, POS, inflection class, features and slots
match_terms: ["entry detail", "how is this entry modelled", "allomorph order", "entry parser detail", "inflection class of an entry", "msa of an entry", "why doesn't this entry parse"]
entities: ["LexEntry", "MoForm", "MoStemMsa", "MoInflAffMsa", "PhEnvironment"]
operations: ["read", "iterate"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/entry_detail.py
verified_against: {"flexicon": "4.12.0", "verified_by": "sena3-read"}
notes: Allomorphs are listed in parser order; the first is the lexeme form, and HermitCrab tries the alternates in order as disjunctive choices. An abstract form is skipped by the parser. The MSA kind comes from the wrappers that project.MSA.GetAll(entry) yields (is_stem_msa / is_infl_aff_msa), not from ClassName. Inflection class and exception features come from project.MSA.GetInflectionClass and project.MSA.GetExceptionFeatures on the stem MSA that as_stem_msa() hands back (flexicon#573, #574, fixed in 4.12.0). Don't cast flexicon wrappers to LCM interfaces.
"""
# --- PARAMS ---
HEADWORDS = ["lekerera", "pi-1"]  # exact headwords, homograph number included (e.g. "pi-1")
# --- END PARAMS ---
import unicodedata


wanted = set(unicodedata.normalize("NFC", h) for h in HEADWORDS)
seen = set()
for entry in project.LexEntry.GetAll():
    headword = unicodedata.normalize("NFC", project.LexEntry.GetHeadword(entry))
    if headword not in wanted:
        continue
    seen.add(headword)
    mt = project.LexEntry.GetMorphType(entry)
    report.Info(
        f"== {headword} mt={str(mt) if mt else None} cit={project.LexEntry.GetCitationForm(entry)}",
        project.BuildGotoURL(entry),
    )
    for i, allo in enumerate(project.Allomorphs.GetAll(entry)):
        envs = [project.Environments.GetStringRepresentation(x) for x in project.Allomorphs.GetPhoneEnv(allo)]
        amt = project.Allomorphs.GetMorphType(allo)
        report.Info(
            f"   {'lf ' if i == 0 else 'alt'} form={project.Allomorphs.GetForm(allo)} "
            f"abstract={project.Allomorphs.GetIsAbstract(allo)} env={envs} mt={str(amt) if amt else None}"
        )
    for sense in project.LexEntry.GetSenses(entry):
        report.Info(f"   sense '{project.Senses.GetGloss(sense)}': POS={project.Senses.GetPartOfSpeech(sense) or None}")
    for msa in project.MSA.GetAll(entry):
        pos = project.POS.GetName(msa.pos_main) if msa.pos_main else None
        feats = project.InflectionFeatures.DescribeFeatStruc(msa)
        if msa.is_stem_msa:
            stem = msa.as_stem_msa()
            icl = project.MSA.GetInflectionClass(stem)
            restrict = [project.PossibilityLists.GetItemName(p) for p in project.MSA.GetExceptionFeatures(stem)]
            report.Info(f"   stem MSA: POS={pos} infl class={project.InflectionFeatures.InflectionClassGetName(icl) if icl else None} feats={feats or None} exception feats={restrict}")
        elif msa.is_infl_aff_msa:
            slots = [project.POS.GetSlotName(x) for x in project.MSA.GetInflAffMsaSlots(msa)]
            report.Info(f"   infl-affix MSA: POS={pos} slots={slots} feats={feats or None}")
        elif msa.is_deriv_aff_msa:
            frm = project.POS.GetName(msa.pos_from) if msa.pos_from else None
            to = project.POS.GetName(msa.pos_to) if msa.pos_to else None
            report.Info(f"   deriv-affix MSA: {frm} -> {to}")
        else:
            report.Info(f"   unclassified-affix MSA: POS={pos}")
for headword in sorted(wanted - seen):
    report.Warning(f"no entry with headword {headword}")
