"""
id: remove-semantic-domains
intent: Remove semantic domain references from senses in bulk
match_terms: ["remove semantic domains", "clear semantic domains", "bulk remove semantic domain links", "delete semantic domain assignments", "remove semantic domain from senses"]
entities: ["LexEntry", "LexSense", "SemanticDomain"]
operations: ["delete"]
requires_write: true
origin: FLExTools module RemoveSemanticDomains.py (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: Removes semantic domain links from senses, matched by abbreviation, name, or raw string repr against DOMAIN. When DOMAIN is "" (all domains), the recipe issues a loud warning and forces modifyAllowed off, since that setting would strip every semantic domain from every matched sense. Optional HEADWORDS filter restricts to specific entries by exact headword match (NFC-normalized). GetAbbreviation/GetName can legitimately return "" when the project's Semantic Domains list is only localized into a writing system other than the analysis WS; resolve_domain_label() falls back to parsing the domain's own "abbr - name" display string in that case, so DOMAIN still matches across writing systems.
"""
# --- PARAMS ---
DOMAIN = ""  # semantic domain to remove (number as string or name); "" = remove ALL domains (WARNING: very destructive!)
HEADWORDS = []  # if non-empty, process only these entries by exact headword (NFC); empty = all entries
# --- END PARAMS ---
import unicodedata

def resolve_domain_label(dom):
    """Return (abbreviation, name) for a domain, falling back to parsing its
    own string repr (e.g. "2.5.4 - Disabled") when both are unset in the
    default analysis WS (the shared Semantic Domains list may only be
    localized into a WS other than the project's analysis WS)."""
    abbr = project.SemanticDomains.GetAbbreviation(dom) or ""
    name = project.SemanticDomains.GetName(dom) or ""
    if not abbr and not name:
        text = str(dom)
        if " - " in text:
            abbr, name = text.split(" - ", 1)
        else:
            abbr = text
    return abbr, name

if not DOMAIN:
    report.Error("WARNING: DOMAIN is empty, which means ALL semantic domains will be removed from ALL senses. This is very destructive. Please set DOMAIN to a specific domain number/name or acknowledge the risk.")
    if modifyAllowed:
        report.Error("Aborting write due to destructive operation on all domains.")
    modifyAllowed = False

total_removed = 0
would_remove = 0

# Resolve HEADWORDS to entries
target_entries = []
if HEADWORDS:
    hw_set = set(unicodedata.normalize("NFC", hw) for hw in HEADWORDS)
    target_entries = [
        e for e in project.LexEntry.GetAll()
        if unicodedata.normalize("NFC", project.LexEntry.GetHeadword(e)) in hw_set
    ]
else:
    target_entries = list(project.LexEntry.GetAll())

for entry in target_entries:
    entry_removed = 0
    senses = project.LexEntry.GetSenses(entry)

    for sense in senses:
        domains = project.Senses.GetSemanticDomains(sense)

        # Collect domains to remove (iterate a safe copy to avoid
        # modification-during-iteration)
        to_remove = []
        for dom in domains:
            dom_abbr, dom_name = resolve_domain_label(dom)
            if DOMAIN == dom_abbr or DOMAIN == dom_name or DOMAIN == str(dom):
                to_remove.append(dom)

        for dom in to_remove:
            if modifyAllowed:
                project.Senses.RemoveSemanticDomain(sense, dom)
                entry_removed += 1
            else:
                report.Info(f"(dry run) would remove semantic domain {dom}")
                would_remove += 1

    if entry_removed > 0:
        total_removed += entry_removed
        report.Info(
            f"Removed {entry_removed} semantic domain(s) from '{project.LexEntry.GetHeadword(entry)}'",
            project.BuildGotoURL(entry)
        )

if modifyAllowed:
    report.Info(f"Total: removed {total_removed} semantic domain reference(s).")
elif would_remove:
    report.Info(f"Total: would remove {would_remove} semantic domain reference(s).")
