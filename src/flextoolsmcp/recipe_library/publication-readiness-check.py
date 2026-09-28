"""
id: publication-readiness-check
intent: Audit lexicon for publication readiness: report senses lacking both definition and gloss, and senses with POS marked as uncertain
match_terms: ["publication readiness", "pre-publish audit", "missing definitions or glosses", "uncertain part of speech", "missing gloss and definition", "pos not sure"]
entities: ["LexEntry", "LexSense"]
operations: ["read", "iterate"]
requires_write: false
origin: FLExTools module ReadyForPublish.py (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 0
notes: Non-blocking validation. Reports senses that have neither definition nor gloss, and senses whose POS is marked as the placeholder value (e.g., "<Not Sure>"). Includes entry link for easy navigation.
"""
# --- PARAMS ---
POS_PLACEHOLDER = "<Not Sure>"  # POS value indicating uncertain part of speech
# --- END PARAMS ---

missing_def_gloss = 0
uncertain_pos = 0

for entry in project.LexEntry.GetAll():
    for sense in project.LexEntry.GetSenses(entry):
        definition = project.Senses.GetDefinition(sense)
        gloss = project.Senses.GetGloss(sense)

        # Report senses with neither definition nor gloss
        if not definition and not gloss:
            report.Warning(
                f"Sense has neither definition nor gloss",
                project.BuildGotoURL(entry),
            )
            missing_def_gloss += 1

        # Report senses with uncertain POS
        pos = project.Senses.GetPartOfSpeech(sense)
        if pos and str(pos) == POS_PLACEHOLDER:
            report.Warning(
                f"Sense has POS marked as {POS_PLACEHOLDER}",
                project.BuildGotoURL(entry),
            )
            uncertain_pos += 1

report.Info(f"Found {missing_def_gloss} senses with no definition or gloss")
report.Info(f"Found {uncertain_pos} senses with POS marked as {POS_PLACEHOLDER}")
