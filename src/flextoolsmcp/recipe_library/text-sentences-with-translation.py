"""
id: text-sentences-with-translation
intent: Extract paragraph and sentence hierarchy from a text with baseline text and free/literal translations numbered as p.s (paragraph.sentence)
match_terms: ["text with translations", "sentence translations", "paragraph sentence structure", "text baseline and gloss", "extract text segments with translations"]
entities: ["Text", "StText", "Paragraph", "Segment"]
operations: ["read", "iterate"]
requires_write: false
origin: InterlinData.py (Ron Lockwood) checkForNewSentOrPar lines 259-287 + setFlagsAndSpaces lines 384-406
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Extracts the paragraph/sentence hierarchy from a named text, one segment per sentence, numbered p.s (1.1 for paragraph 1, sentence 1). Baseline text is always reported; free and literal translations are reported only when present.
"""
# --- PARAMS ---
TEXT_TITLE = "Sample Translation Text"  # exact title of the text to extract; case-sensitive
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
    report.Info(f"Text: {TEXT_TITLE}")

    par_num = 0
    for paragraph in project.Paragraphs.GetAll(target_text):
        par_num += 1

        seg_num = 0
        for segment in project.Segments.GetAll(paragraph):
            seg_num += 1

            baseline = project.Segments.GetBaselineText(segment)
            free_trans = project.Segments.GetFreeTranslation(segment)
            literal_trans = project.Segments.GetLiteralTranslation(segment)

            # Build the output line
            label = f"{par_num}.{seg_num} {baseline}"
            if free_trans:
                label += f" => {free_trans}"
            if literal_trans:
                label += f" (lit: {literal_trans})"

            report.Info(label)
