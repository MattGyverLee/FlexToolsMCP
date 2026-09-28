"""
id: delete-texts
intent: Delete texts whose title matches a regex pattern, with optional scripture cleanup
match_terms: ["delete texts", "remove texts", "remove scripture texts", "clean up texts", "bulk delete texts"]
entities: ["Text"]
operations: ["delete"]
requires_write: true
origin: FLExTools module Remove_All_Texts.py (Matthew Lee) and RemoveScripture.py (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: Selects texts for deletion by regex match against the title in both vernacular and analysis writing systems; dry run lists titles and counts without deleting. Default pattern is deliberately narrow ("^zzRecipeTest") -- widening TITLE_PATTERN to something like ".*" would delete every text in the project, so change it with care. Scripture cleanup is optional (INCLUDE_SCRIPTURE=True) and only runs if Scripture books exist; it uses its own try/except so a failure there does not affect the text deletion above it. Uses a collect-then-delete two-pass approach so deletion never mutates the collection being iterated.
"""
# --- PARAMS ---
TITLE_PATTERN = r"^zzRecipeTest"  # Regex pattern to match text titles; default is safe, matches texts starting with "zzRecipeTest"; use ".*" with caution as it deletes ALL texts
INCLUDE_SCRIPTURE = False  # If True, also delete Scripture book data if any exists
# --- END PARAMS ---
import re
import unicodedata

vern_ws = project.GetDefaultVernacularWSHandle()

texts_to_delete = []

# Collect all texts matching the pattern
for text in project.Texts.GetAll():
    # Get titles in both writing systems
    vern_title = project.Texts.GetTitle(text, wsHandle=vern_ws) or ""
    analysis_title = project.Texts.GetTitle(text) or ""  # defaults to analysis WS

    # Normalize for consistent matching
    vern_normalized = unicodedata.normalize("NFC", vern_title)
    analysis_normalized = unicodedata.normalize("NFC", analysis_title)

    # Check if title matches pattern
    matches = (re.search(TITLE_PATTERN, vern_normalized) or
               re.search(TITLE_PATTERN, analysis_normalized))

    if matches:
        texts_to_delete.append({
            "text": text,
            "vern": vern_normalized,
            "analysis": analysis_normalized
        })

# Report what was found
if not texts_to_delete:
    report.Info(f"No texts matched pattern '{TITLE_PATTERN}'")
else:
    report.Info(f"Found {len(texts_to_delete)} text(s) matching pattern '{TITLE_PATTERN}':")

    # List the titles that will be deleted
    for item in texts_to_delete:
        title_display = f"{item['vern']}" if item['vern'] else f"(unnamed)"
        if item['analysis'] and item['analysis'] != item['vern']:
            title_display += f"|{item['analysis']}"
        report.Info(f"  {title_display}")

    # Perform deletion if allowed
    if modifyAllowed:
        deleted_count = 0
        error_count = 0
        for item in texts_to_delete:
            try:
                project.Texts.Delete(item["text"])
                deleted_count += 1
                title = item['vern'] or "(unnamed)"
                report.Info(f"Deleted text '{title}'")
            except Exception as e:
                error_count += 1
                title = item['vern'] or "(unnamed)"
                report.Error(
                    f"Failed to delete text '{title}': {e}",
                    project.BuildGotoURL(item["text"])
                )

        report.Info(f"SUMMARY: {deleted_count} deleted, {error_count} error(s)")
    else:
        report.Info(f"(dry run) would delete {len(texts_to_delete)} text(s)")
        report.Warning("This operation is destructive. Verify the pattern matches expected texts before running with write enabled.")

# Handle optional scripture cleanup
if INCLUDE_SCRIPTURE:
    try:
        books = list(project.ScrBooks.GetAll())
        if books:
            if modifyAllowed:
                deleted_books = 0
                for book in books:
                    try:
                        project.ScrBooks.Delete(book)
                        deleted_books += 1
                    except Exception as e:
                        report.Error(f"Failed to delete Scripture book: {e}")
                report.Info(f"Deleted {deleted_books} Scripture book(s)")
            else:
                report.Info(f"(dry run) would delete {len(books)} Scripture book(s)")
        else:
            report.Info("No Scripture data found to delete")
    except Exception as e:
        report.Warning(f"Could not access Scripture data: {e}")
