"""
id: text-interlinear-walk
intent: Walk one interlinear text paragraph by paragraph and segment by segment, giving each word's morpheme breakdown, and flag incomplete analyses
match_terms: ["walk interlinear text", "interlinear data extraction", "morpheme bundle breakdown", "analyze text structure", "incomplete morpheme analysis", "text segmentation with analysis"]
entities: ["Text", "StText", "Paragraph", "Segment", "WfiAnalysis", "WfiMorphBundle", "WfiWordform", "LexEntry"]
operations: ["read", "iterate"]
requires_write: false
origin: InterlinData.py (Ron Lockwood) walk-interlinear-text-structure lines 524-687
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Walks a named text's paragraphs and segments, reporting each morpheme's form, entry headword, sense number, gloss, and POS, and flags bundles missing a sense or MSA. Baseline text and free translation are shown per segment when present. GetAnalyses yields polymorphic tokens (WfiWordform, WfiGloss, WfiAnalysis, PunctuationForm), so bundles are read via project.WfiAnalyses.GetMorphemeBundles, which resolves the owning analysis for any token type and returns [] for punctuation or unanalyzed words; calling the wordform/gloss objects' own morph-bundle accessor directly would raise on non-WfiAnalysis tokens.
"""
# --- PARAMS ---
TEXT_TITLE = "Sample Interlinear Text"  # exact title of the text to walk; case-sensitive
SENTENCE_PUNCTUATION = ".!?"  # punctuation marks that end sentences/segments
POS_SKIP_LIST = []  # POS abbreviations to skip when reporting (leave empty to report all)
MAX_SEGMENTS = 0  # max segments to process (0 = all); useful for sampling large texts
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


# Find text by title
target_text = None
for text in project.Texts.GetAll():
    if nfc(project.Texts.GetTitle(text)) == nfc(TEXT_TITLE):
        target_text = text
        break

if target_text is None:
    report.Error(f"text {TEXT_TITLE!r} not found")
else:
    report.Info(f"Walking text {TEXT_TITLE!r}")

    par_count = 0
    seg_count = 0
    bundle_count = 0
    incomplete_bundles = 0

    for paragraph in project.Paragraphs.GetAll(target_text):
        par_count += 1
        report.Info(f"Paragraph {par_count}")

        for segment in project.Segments.GetAll(paragraph):
            seg_count += 1
            if MAX_SEGMENTS > 0 and seg_count > MAX_SEGMENTS:
                break

            baseline = project.Segments.GetBaselineText(segment)
            free_trans = project.Segments.GetFreeTranslation(segment)

            seg_label = f"  Segment {seg_count}: '{baseline}'"
            if free_trans:
                seg_label += f" => '{free_trans}'"
            report.Info(seg_label)

            analyses = project.Segments.GetAnalyses(segment)
            for analysis in analyses:
                # GetAnalyses yields polymorphic tokens (WfiWordform, WfiGloss,
                # WfiAnalysis, PunctuationForm); GetMorphBundles requires a
                # genuine WfiAnalysis and raises AttributeError on the others
                # (WfiGloss, the fully-glossed and most common case, is not
                # one). GetMorphemeBundles resolves the owning analysis for
                # any token type and returns [] for punctuation/unanalyzed.
                bundles = project.WfiAnalyses.GetMorphemeBundles(analysis)

                for bundle in bundles:
                    bundle_count += 1
                    morph = project.WfiMorphBundles.GetMorph(bundle)
                    morph_form = project.Allomorphs.GetForm(morph) if morph else "(no morph)"
                    gloss = project.WfiMorphBundles.GetGloss(bundle) or ""
                    sense = project.WfiMorphBundles.GetSense(bundle)
                    msa = project.WfiMorphBundles.GetMSA(bundle)

                    # Get entry and sense info from sense object
                    headword = None
                    sense_num = -1
                    if sense:
                        entry_obj = project.Senses.GetOwningEntry(sense)
                        if entry_obj:
                            headword = project.LexEntry.GetHeadword(entry_obj)
                            senses = project.LexEntry.GetSenses(entry_obj)
                            for idx, s in enumerate(senses):
                                if project.Senses.GetGuid(s) == project.Senses.GetGuid(sense):
                                    sense_num = idx
                                    break

                    # Get POS from MSA via the entry's wrapped MSAs (matched
                    # by Hvo-equality to the bundle's raw MSA, same technique
                    # as affix-catalog.py) -- no ClassName check or cast needed
                    pos_abbrev = None
                    if msa:
                        try:
                            owning_entry = project.Allomorphs.GetOwningEntry(morph) if morph else None
                            if owning_entry:
                                wrapped_msa = next(
                                    (m for m in project.MSA.GetAll(owning_entry) if m == msa), None
                                )
                                if wrapped_msa and wrapped_msa.pos_main:
                                    pos_abbrev = project.POS.GetAbbreviation(wrapped_msa.pos_main)
                        except Exception:
                            pass

                    # Flag incomplete bundles
                    incomplete = False
                    incomp_reason = []
                    if not sense:
                        incomp_reason.append("no sense")
                        incomplete = True
                    if not msa:
                        incomp_reason.append("no MSA")
                        incomplete = True
                    if POS_SKIP_LIST and pos_abbrev and pos_abbrev in POS_SKIP_LIST:
                        incomp_reason.append(f"POS skipped ({pos_abbrev})")
                        incomplete = True

                    if incomplete:
                        incomplete_bundles += 1

                    # Build report line
                    parts = [f"morph={morph_form}"]
                    if headword:
                        parts.append(f"entry={headword}")
                        if sense_num >= 0:
                            parts.append(f"sense={sense_num+1}")
                    if gloss:
                        parts.append(f"gloss={gloss}")
                    if pos_abbrev:
                        parts.append(f"POS={pos_abbrev}")

                    if incomp_reason:
                        parts.append(f"INCOMPLETE[{', '.join(incomp_reason)}]")
                        report.Warning(f"      {' '.join(parts)}")
                    else:
                        report.Info(f"      {' '.join(parts)}")

    report.Info(f"Summary: {par_count} paragraph(s), {seg_count} segment(s), {bundle_count} bundle(s), {incomplete_bundles} incomplete")
