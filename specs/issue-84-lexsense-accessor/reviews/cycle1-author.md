# Cycle 1 — Original Author review (issue #84)

Score: 4/10 — REQUEST CHANGES (findings since addressed; see cycle1-adjudication.md)

## Q1 — Template coherence
Prose reads clean, but the "equivalent alternatives" note offered three spellings of
one operation with no stated preference. Recommends picking a house idiom.

## Q2 — Sweep introduced a real signature break (CONFIRMED, P0)
`GetAllSenses` exists on BOTH operations classes with DIFFERENT parameters:
- `LexEntryOperations.GetAllSenses(entry_or_hvo)` — senses owned by this entry
- `LexSenseOperations.GetAllSenses(sense_or_hvo)` — this sense + its subsenses

The mechanical `LexSense` -> `Senses` substitution produced
`project.Senses.GetAllSenses(entry)`, passing an `ILexEntry` where a sense is
expected. Shipped in: `templates/2-flexicon-template.py`,
`server/worked_examples.py`, `templates/00-FLAVOR-GUIDE.md`, `CLAUDE.md`,
`docs/CASTING_SYSTEM.md`, and the new test file's own "corrected form".
`curated_recipes.py` escaped it — it already used `project.LexEntry.GetAllSenses(entry)`
for entry->senses and only redirected genuine per-sense calls.

## Q3 — Test adequacy
The accessor gate only checks attribute NAMES via difflib, never argument arity or
type, so it structurally cannot catch Q2. The item-3 "smoke test" is purely static
and never executes `Main()`. No mock/fixture `FLExProject` exists in `tests/`.
Recommends a duck-typed stub asserting call args match indexed parameter names.

## Q4 — Does it close #84?
Fixes 1 and 2 solid and well-tested. Fix 3 was interpreted down to static
validation, and that gap is what let the Q2 defect ship into the same
authoritative artifact the issue named.
