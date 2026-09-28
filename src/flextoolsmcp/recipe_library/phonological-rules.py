"""
id: phonological-rules
intent: List every phonological rule with its direction and stratum, and for rules matching a name filter show their input and output
match_terms: ["phonological rules", "list phonological rules", "phon rules", "rule input and output", "what rules does the parser apply"]
entities: ["PhSegmentRule", "PhRegularRule"]
operations: ["read", "iterate"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/phon_rules.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
notes: Uses the PhonologicalRule wrappers from project.PhonRules.GetAll() (name, direction, stratum, input_contexts, output_specs). Left/right contexts, exception features and input-POS restrictions have no flexicon reader yet (flexicon#572), so this recipe does not show them. Name filters are case-insensitive substrings; an empty list shows the detail for every rule.
"""
# --- PARAMS ---
NAME_CONTAINS = []  # substrings of rule names to show in detail; [] = all rules
# --- END PARAMS ---
filters = [k.casefold() for k in NAME_CONTAINS]
rules = project.PhonRules.GetAll()
report.Info(f"phonological rules: {len(rules)}")
for i, rule in enumerate(rules):
    name = rule.name or ""
    report.Info(f"#{i} {name} dir={rule.direction} stratum={rule.stratum}")
    if filters and not any(k in name.casefold() for k in filters):
        continue
    report.Info(f"   input: {[str(c) for c in rule.input_contexts]}")
    if rule.has_output_specs:
        report.Info(f"   output: {[str(c) for c in rule.output_specs]}")
