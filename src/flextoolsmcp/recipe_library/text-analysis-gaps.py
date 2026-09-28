"""
id: text-analysis-gaps
intent: Find words in text with no morpheme analysis and identify morpheme bundles missing sense or MSA
match_terms: ["unanalyzed words", "words with no analysis", "incomplete morpheme analysis", "missing sense or msa", "text analysis gaps", "find unanalyzed text"]
entities: ["IText", "IWfiWordform", "IWfiAnalysis", "IMoMorphBundle"]
operations: ["read", "iterate"]
requires_write: false
origin: From Ron/FLExTrans Published Modules/TextClasses.py (find-unanalyzed-words) and InterlinData.py (detect-incomplete-morpheme-analysis)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 2
notes: Walks the selected text's (or, if TEXT_TITLE is "", every text's) own paragraphs, segments, and word occurrences, reporting (1) word occurrences with no analysis at all and (2) analyzed occurrences whose morpheme bundles are missing a sense or MSA. Skips punctuation tokens, SFM markers, and, by default, capitalized non-sentence-initial words (likely proper nouns; toggle with SKIP_CAPITALIZED_NONINITIAL). Segment occurrence tokens (IWfiWordform/IWfiAnalysis/IWfiGloss/IPunctuationForm) are dispatched by ClassName since the token type is polymorphic; IWfiGloss's owning IWfiAnalysis is read via the raw .Owner property, which needs raw LCM access since there is no public token-to-owning-analysis resolver besides the private one GetMorphemeBundles uses internally (flexicon gap #575).
"""
# --- PARAMS ---
TEXT_TITLE = ""  # exact text title to check; "" means all texts
SKIP_CAPITALIZED_NONINITIAL = True  # skip capitalized non-sentence-initial words (likely proper nouns)
# --- END PARAMS ---

import unicodedata
from SIL.LCModel import ICmObject

def nfc(text):
    return unicodedata.normalize("NFC", text or "")

def resolve_wordform_and_analysis(token):
    """Resolve a segment occurrence token to (wordform, analysis-or-None).
    Returns (None, None) for punctuation tokens."""
    cls = token.ClassName  # raw-lcm: dispatch on occurrence token subtype (documented SegmentOperations.GetAnalyses contract)
    if cls == "PunctuationForm":
        return None, None
    if cls == "WfiWordform":
        return token, None
    if cls == "WfiGloss":
        analysis = ICmObject(token).Owner  # raw-lcm: flexicon gap #575 (WfiGloss -> owning WfiAnalysis)
    else:  # "WfiAnalysis"
        analysis = token
    wf = project.WfiAnalyses.GetOwningWordform(analysis)
    return wf, analysis

# Collect all text titles if filtering
target_texts = {}
if TEXT_TITLE:
    wanted = nfc(TEXT_TITLE)
    for text in project.Texts.GetAll():
        if nfc(project.Texts.GetTitle(text)) == wanted:
            target_texts[text] = wanted
            break
else:
    for text in project.Texts.GetAll():
        target_texts[text] = nfc(project.Texts.GetTitle(text))

if not target_texts:
    if TEXT_TITLE:
        report.Error(f"no text with title {TEXT_TITLE}")
    else:
        report.Info("no texts in project")
else:
    unanalyzed_count = 0
    incomplete_bundle_count = 0

    for text in target_texts.keys():
        text_title = target_texts[text]
        report.Info(f"Checking text: {text_title}")

        for paragraph in project.Paragraphs.GetAll(text):
            for segment in project.Segments.GetAll(paragraph):
                for token in project.Segments.GetAnalyses(segment):
                    wf, analysis = resolve_wordform_and_analysis(token)
                    if wf is None:
                        continue  # punctuation

                    wf_form = nfc(project.Wordforms.GetForm(wf))

                    # Skip empty forms and SFM markers
                    if not wf_form or wf_form.startswith("\\"):
                        continue

                    # Skip capitalized non-sentence-initial words if requested
                    if SKIP_CAPITALIZED_NONINITIAL and wf_form[0].isupper():
                        continue

                    if analysis is None:
                        unanalyzed_count += 1
                        report.Warning(
                            f"No analysis found for word: {wf_form}",
                            project.BuildGotoURL(wf)
                        )
                        continue

                    for bundle in project.WfiAnalyses.GetMorphBundles(analysis):
                        sense = project.WfiMorphBundles.GetSense(bundle)
                        msa = project.WfiMorphBundles.GetMSA(bundle)
                        morph = project.WfiMorphBundles.GetMorph(bundle)

                        if morph and (not sense or not msa):
                            incomplete_bundle_count += 1
                            morph_form = project.Allomorphs.GetForm(morph) if morph else "?"
                            report.Warning(
                                f"Incomplete morpheme bundle in word '{wf_form}': "
                                f"morph='{morph_form}' sense={'MISSING' if not sense else 'OK'} "
                                f"msa={'MISSING' if not msa else 'OK'}",
                                project.BuildGotoURL(wf)
                            )

    # Summary
    report.Info(f"Unanalyzed words found: {unanalyzed_count}")
    report.Info(f"Incomplete morpheme bundles found: {incomplete_bundle_count}")
    report.Info("Analysis complete")
