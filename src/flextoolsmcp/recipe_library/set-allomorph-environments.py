"""
id: set-allomorph-environments
intent: Change the environments of one existing allomorph by removing and then adding existing phonological environments, with a BEFORE/AFTER report
match_terms: ["change allomorph environments", "set phone environment on an allomorph", "remove environment from an allomorph", "add environment to an allomorph", "allomorph environment before and after", "fix parsing by changing environments"]
entities: ["LexEntry", "MoForm", "PhEnvironment"]
operations: ["update", "iterate", "search"]
requires_write: true
origin: MCPlayground flex-parse-fixup lib/w_set_allomorph_env.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: Only EXISTING environments can be used here: creating a new environment is grammar-wide, so list them first (affix-templates-and-slots prints the exact notation AddPhoneEnv expects). Run form-usage-before-edit on the entry first: every analysis using these forms is in the filing scope of the change. The headword and FORM are compared after NFC normalization. Every run prints a BEFORE and an AFTER environment list; with REMOVE and ADD empty (the shipped defaults) the run changes nothing. Mutations happen only under modifyAllowed.
"""
# --- PARAMS ---
HEADWORD = "ma-2"  # exact headword of the entry owning the allomorph (errors cleanly if 0 or more than 1 entry matches)
FORM = "lf"  # "lf" = the lexeme form, or the exact form of one alternate allomorph
REMOVE = []  # existing environment strings to remove (exact notation, e.g. "/ _ [V]"); nothing is created
ADD = []  # existing environment strings to add (exact notation, e.g. "/ _ e"); nothing is created
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


def env_names(allo):
    return sorted(nfc(project.Environments.GetStringRepresentation(e)) for e in project.Allomorphs.GetPhoneEnv(allo))


# Resolve the entry by exact headword (NFC both sides); refuse on 0 or >1.
matches = [e for e in project.LexEntry.GetAll() if nfc(project.LexEntry.GetHeadword(e)) == nfc(HEADWORD)]
if len(matches) != 1:
    report.Error(f"{HEADWORD}: found {len(matches)} entries, need exactly 1; nothing changed")
else:
    entry = matches[0]
    allos = list(project.Allomorphs.GetAll(entry))  # includes the lexeme form, listed first
    if FORM == "lf":
        target = allos[0] if allos else None
    else:
        target = next((a for a in allos if nfc(project.Allomorphs.GetForm(a)) == nfc(FORM)), None)
    if target is None:
        report.Error(f"{HEADWORD} / allomorph {FORM} not found; nothing changed")
    else:
        envs = {nfc(project.Environments.GetStringRepresentation(e)).strip(): e for e in project.Environments.GetAll()}
        missing = [x for x in REMOVE + ADD if nfc(x).strip() not in envs]
        if missing:
            report.Error(f"environments not found: {missing}; nothing changed")
        else:
            report.Info(f"{HEADWORD} {FORM} BEFORE env={env_names(target)}", project.BuildGotoURL(entry))
            if modifyAllowed:
                for x in REMOVE:
                    project.Allomorphs.RemovePhoneEnv(target, envs[nfc(x).strip()])
                for x in ADD:
                    project.Allomorphs.AddPhoneEnv(target, envs[nfc(x).strip()])
            else:
                report.Info(f"(dry run) would remove {REMOVE} and add {ADD}")
            report.Info(f"{HEADWORD} {FORM} AFTER env={env_names(target)}", project.BuildGotoURL(entry))
