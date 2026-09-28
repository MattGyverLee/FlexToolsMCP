"""
id: case-duplicate-entries
intent: Report entries whose headwords differ only by case and share the same part-of-speech
match_terms: ["case-only duplicate entries", "case-sensitive duplicate headwords", "case variants with same pos", "capitalized duplicates", "homographic case variants"]
entities: ["LexEntry", "LexSense"]
operations: ["read", "iterate"]
requires_write: false
origin: FLExTools module ExtractBilingualLexicon.py (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Detects entries whose headwords and POS form case-only duplicates. Maps (lowercase_headword + POS_abbrev) to entry identity; reports when a new entry with the same map key but different entry ID is found.
"""
# --- PARAMS ---
# No tunable parameters; checks all entries and all senses
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


# Map from (lowercase_headword + POS_abbrev) to (entry_id, original_headword, POS_abbrev)
seen_map = {}
duplicates_found = 0

for entry in project.LexEntry.GetAll():
    headword = nfc(project.LexEntry.GetHeadword(entry))
    if not headword:
        continue

    # Check each sense's POS (an entry can have senses with different POSs)
    for sense in project.LexEntry.GetSenses(entry):
        pos = project.Senses.GetPartOfSpeech(sense)
        if not pos:
            continue

        # Get POS abbreviation or name
        pos_str = str(pos)

        # Create composite key: lowercase headword + POS
        key = nfc(headword.lower()) + pos_str

        entry_id = id(entry)

        if key in seen_map:
            prev_id, prev_headword, prev_pos = seen_map[key]
            if prev_id != entry_id:
                report.Warning(
                    f'Case-only duplicate: "{headword}" (POS={pos_str}) duplicates "{prev_headword}" with same POS',
                    project.BuildGotoURL(entry),
                )
                duplicates_found += 1
        else:
            seen_map[key] = (entry_id, headword, pos_str)

report.Info(f"Checked {len(seen_map)} unique (headword, POS) combinations")
report.Info(f"Found {duplicates_found} case-only duplicate entries")
