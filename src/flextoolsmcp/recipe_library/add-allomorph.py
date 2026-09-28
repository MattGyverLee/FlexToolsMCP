"""
id: add-allomorph
intent: Add allomorphs to one entry, each with an existing phonological environment or none
match_terms: ["add allomorph", "add alternate form to entry", "allomorph with environment", "new allomorph form", "conditioned allomorph", "extra stem form"]
entities: ["LexEntry", "MoForm", "PhEnvironment"]
operations: ["create"]
requires_write: true
origin: MCPlayground flex-parse-fixup lib/w_add_allomorph.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-live"}
raw_lcm_lines: 0
notes: Port of w_add_allomorph.py with zero raw LCM: environments come from project.Environments.GetAll keyed by project.Environments.GetStringRepresentation, allomorphs through project.Allomorphs.GetAll/GetForm/Create/GetPhoneEnv/AddPhoneEnv, never project.project or StringRepresentation.Text. HermitCrab allomorphs are disjunctive in order, so an unconditioned allomorph blocks later ones; list conditioned allomorphs first. Every ADD environment must already exist (creating one is grammar-wide); on any missing string the recipe reports an error and changes nothing. The headword resolves to exactly 1 entry after NFC normalization on both sides, else nothing is written. Prints BEFORE and AFTER allomorph lists; a dry run only reports what would be added.
"""
# --- PARAMS ---
HEADWORD = "cibubu"  # exact headword of the entry to extend (known Sena 3 entry)
ADD = [
    # (form, environment string or None; None = unconditioned, always safe)
    ("zzRecipeTestAllo", None),
]
# --- END PARAMS ---
import unicodedata


def nfc(text):
    return unicodedata.normalize("NFC", text or "")


matches = []
for entry in project.LexEntry.GetAll():
    if nfc(project.LexEntry.GetHeadword(entry)) == nfc(HEADWORD):
        matches.append(entry)
if len(matches) != 1:
    report.Error(f"{HEADWORD}: found {len(matches)} entries, need exactly 1; change nothing")
else:
    entry = matches[0]
    before = [project.Allomorphs.GetForm(a) for a in project.Allomorphs.GetAll(entry)]
    report.Info(f"{HEADWORD} BEFORE: {before}", project.BuildGotoURL(entry))
    envs = {}
    for existing in project.Environments.GetAll():
        envs.setdefault(nfc(project.Environments.GetStringRepresentation(existing)), existing)
    wanted = set(env for _form, env in ADD if env is not None)
    missing = sorted(env for env in wanted if nfc(env) not in envs)
    if missing:
        report.Error(f"environment not found: {missing}; change nothing")
    else:
        for form, env in ADD:
            if not modifyAllowed:
                report.Info(f"(dry run) would add {form} env={env}")
                continue
            if modifyAllowed:
                allo = project.Allomorphs.Create(entry, form)
                if env is not None:
                    project.Allomorphs.AddPhoneEnv(allo, envs[nfc(env)])
                allo_envs = [
                    project.Environments.GetStringRepresentation(x)
                    for x in project.Allomorphs.GetPhoneEnv(allo)
                ]
                report.Info(f"added {form} env={allo_envs}")
        after = [project.Allomorphs.GetForm(a) for a in project.Allomorphs.GetAll(entry)]
        report.Info(f"{HEADWORD} AFTER: {after}", project.BuildGotoURL(entry))
