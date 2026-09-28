"""
id: parser-coverage
intent: Parser coverage and the most frequent unparsed wordforms
match_terms: ["parser coverage", "unparsed words", "words that don't parse", "parse rate"]
entities: ["WfiWordform"]
operations: ["read", "iterate"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/candidates.py
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
notes: Frequency is GetOccurrenceCount. A wordform counts as parsed when the parser has at least one analysis (ParserCount > 0). Coverage is over wordforms that occur in texts; wordforms with no occurrences are ignored.
"""
# --- PARAMS ---
COUNT = 10  # how many unparsed words to list, most frequent first
# --- END PARAMS ---
rows = []
occurring = 0
for wf in project.Wordforms.GetAll():
    c = project.Wordforms.GetOccurrenceCount(wf)
    if c == 0:
        continue
    occurring += 1
    if wf.ParserCount == 0:
        rows.append((c, project.Wordforms.GetForm(wf), wf.UserCount))
rows.sort(key=lambda r: (-r[0], r[1]))
parsed = occurring - len(rows)
pct = 100.0 * parsed / occurring if occurring else 0.0
report.Info(f"parser coverage: {parsed}/{occurring} occurring wordforms ({pct:.1f}%)")
report.Info(f"total unparsed with occurrences: {len(rows)}")
for c, f, u in rows[:COUNT]:
    report.Info(f"{f}\tcount={c}\tuser={u}")
