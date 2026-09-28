"""
id: complex-form-components-missing
intent: Identify missing individual words in multi-word lexeme forms; report component words that have no single-word entry
match_terms: ["missing words in phrases", "multi-word lexemes missing components", "find component words not in lexicon", "phrase component check", "complex form missing words"]
entities: ["LexEntry"]
operations: ["read", "iterate"]
requires_write: false
origin: FLExTools module Complex_Lexemes.py (Matthew Lee)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Splits multi-word lexeme forms on whitespace and reports each component word that has no corresponding single-word entry. Uses simple whitespace split; may need adjustment for languages with non-space delimiters or punctuation-attached morphemes.
"""
# --- PARAMS ---
SEPARATOR = " "  # delimiter to split multi-word forms (usually space)
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


# Collect all single-word headwords (normalized)
single_words = set()
multi_word_entries = []

for entry in project.LexEntry.GetAll():
    headword = nfc(project.LexEntry.GetHeadword(entry))
    if not headword:
        continue
    words = headword.split(SEPARATOR)
    if len(words) == 1:
        single_words.add(words[0])
    elif len(words) > 1:
        multi_word_entries.append((headword, entry))

report.Info(f"Found {len(single_words)} single-word lexemes and {len(multi_word_entries)} multi-word lexemes")

# Check each multi-word entry for missing component words
missing_found = 0
for headword, entry in multi_word_entries:
    words = headword.split(SEPARATOR)
    for word in words:
        if word not in single_words:
            report.Warning(
                f'Component word "{word}" in multi-word entry "{headword}" not found in lexicon',
                project.BuildGotoURL(entry),
            )
            missing_found += 1

report.Info(f"Reported {missing_found} missing component words")
