# Cycle 1 — Domain review (issue #84)

Score: 55/100. Q1/Q2 PASS, Q3 FAIL (rejected on evidence), Q4 MIXED (confirmed P0).

## Q1 — `LexSense` -> `Senses`: PASS
`Senses` is a real FLExProject property returning `LexSenseOperations`
(`index/python/flexicon_api_v4.3.0.json`). The class docstring says "Access via
`FLExProject.Senses` property (recommended)". Note: a singular `project.Sense`
DOES exist on the live class though it is absent from the index; `Senses` remains
the right target.

## Q2 — `PhonologicalRule` -> `PhonRules`: PASS
`PhonRules` is the real property returning `PhonologicalRuleOperations`. The entity
named `PhonologicalRule` is an unrelated per-object wrapper class, not a competing
accessor. No ambiguity.

## Q3 — Completeness: claimed FAIL
Claims ~27 further phantoms by the same singular/plural argument as the QC review.
**REJECTED** on the same evidence — those names exist on `dir(FLExProject)` and are
simply not enumerated in the index property list. See cycle1-adjudication.md.

## Q4 — Template alternatives: MIXED (CONFIRMED P0)
Both cited idioms are individually valid and accept an entry:
- `LexEntryOperations.GetAllSenses(entry_or_hvo)`
- `LexSenseOperations(project).GetAll(entry_or_hvo=None, recursive=True)`

But the template code called `project.Senses.GetAllSenses(entry)`, which is
`LexSenseOperations.GetAllSenses(sense_or_hvo)` — it takes a SENSE. Independently
confirmed against flexicon source; fixed to `project.LexEntry.GetAllSenses(entry)`.

## Bonus finding (CONFIRMED, pre-existing)
`templates/2-flexicon-template.py` imported `ReversalOperations`, which flexicon
4.3.0 does not export — an ImportError that kills the module before `Main()` runs.
Removed. A follow-on import test then caught the same defect class in
`templates/3-liblcm-template.py`, which pulled LCM interfaces from
`flexicon.code.lcm_casting`; that module imports them internally from `SIL.LCModel`
but never re-exports them.
