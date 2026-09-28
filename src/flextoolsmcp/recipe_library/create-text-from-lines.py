"""
id: create-text-from-lines
intent: Create a text with one paragraph per input line, warning when the title already exists
match_terms: ["create text", "import text lines", "paragraphs per line", "new text from lines", "add text with paragraphs", "one paragraph per line"]
entities: ["Text", "StText", "Paragraph"]
operations: ["create", "iterate", "search"]
requires_write: true
origin: developer ops log (Ron)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-live"}
raw_lcm_lines: 0
notes: One paragraph is created per LINES entry in the default vernacular writing system. The title is compared after NFC normalization on both sides; when a text with the same title already exists the recipe reports a Warning and stops, never deleting or recreating the existing text. TITLE defaults to the zzRecipeTest title. Report through report.Info/Warning/Error only.
"""
# --- PARAMS ---
TITLE = "zzRecipeTest Lines"  # title for the new text; must not match an existing text
LINES = ["zzRecipeTest line one", "zzRecipeTest line two"]  # one paragraph per entry
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


want = nfc(TITLE)
existing = None
for text in project.Texts.GetAll():
    if nfc(project.Texts.GetName(text)) == want or nfc(project.Texts.GetTitle(text)) == want:
        existing = text
        break

if existing is not None:
    report.Warning(
        f"text {TITLE!r} already exists; not deleting or recreating it",
        project.BuildGotoURL(existing),
    )
else:
    blank = [line for line in LINES if not nfc(line).strip()]
    if not LINES or blank:
        report.Error("LINES must hold one non-empty paragraph per entry; nothing created")
    elif not modifyAllowed:
        report.Info(f"(dry run) would create text {TITLE!r} with {len(LINES)} paragraph(s)")
    if modifyAllowed:
        if existing is None and LINES and not blank:
            new_text = project.Texts.Create(TITLE)
            for line in LINES:
                project.Paragraphs.Create(new_text, line)
            report.Info(
                f"created text {TITLE!r} with {len(LINES)} paragraph(s)",
                project.BuildGotoURL(new_text),
            )
