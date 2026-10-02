"""
id: morpheme-character-check
intent: Check headwords and affix glosses for disallowed characters such as spaces, periods or angle brackets
match_terms: ["invalid morpheme characters", "character validation", "disallowed lemma characters", "check affix glosses for invalid chars", "morpheme character check"]
entities: ["LexEntry", "LexSense", "MoForm"]
operations: ["read", "iterate"]
requires_write: false
origin: FLExTools module InterlinData.py (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Validates headwords and affix glosses against a set of disallowed characters, useful for catching data-entry errors that would break parser morpheme segmentation or interlinear/export gloss alignment. Default DISALLOWED_CHARS is space, period, and angle brackets: space splits what should be one morpheme into two tokens, "." collides with the Leipzig gloss-part separator, and "<"/">" collide with feature-notation brackets used in some export/rule formats. Set DISALLOWED_CHARS to "" to skip validation entirely. Multi-word lexemes (e.g. idioms) will legitimately trip the space check on CHECK_HEADWORDS; narrow DISALLOWED_CHARS (e.g. "<>") or set CHECK_HEADWORDS=False if that noise is unwanted.
"""
# --- PARAMS ---
DISALLOWED_CHARS = " .<>"  # string of characters to forbid in headwords/glosses; empty = no check
CHECK_HEADWORDS = True  # whether to validate headwords
CHECK_GLOSS_AFFIXES = True  # whether to validate affix glosses in senses
# --- END PARAMS ---


def has_disallowed(text, disallowed_set):
    """Check if text contains any disallowed characters."""
    if not disallowed_set:
        return False
    return any(c in disallowed_set for c in text)


if not DISALLOWED_CHARS:
    report.Info("DISALLOWED_CHARS is empty; skipping character validation")
else:
    disallowed_set = set(DISALLOWED_CHARS)
    issues_found = 0

    for entry in project.LexEntry.GetAll():
        headword = project.LexEntry.GetHeadword(entry) or ""

        # Check headword
        if CHECK_HEADWORDS and has_disallowed(headword, disallowed_set):
            bad_chars = "".join(sorted(set(c for c in headword if c in disallowed_set)))
            report.Warning(
                f'Headword "{headword}" contains disallowed characters: {bad_chars}',
                project.BuildGotoURL(entry),
            )
            issues_found += 1

        # Check affix glosses in senses
        if CHECK_GLOSS_AFFIXES:
            for sense in project.LexEntry.GetSenses(entry):
                gloss = project.Senses.GetGloss(sense) or ""
                if gloss and has_disallowed(gloss, disallowed_set):
                    bad_chars = "".join(sorted(set(c for c in gloss if c in disallowed_set)))
                    report.Warning(
                        f'Affix gloss "{gloss}" in sense contains disallowed characters: {bad_chars}',
                        project.BuildGotoURL(entry),
                    )
                    issues_found += 1

    report.Info(f"Found {issues_found} entries/senses with disallowed characters")
