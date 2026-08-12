# Cycle 1 — Adjudication (issue #84)

Two reviewers (QC, domain) independently reported that ~29 further phantom
accessors remain. Both are wrong, and for the same reason. Recording the evidence
here so the claim doesn't get re-litigated next cycle.

## The disputed claim

> `Example`, `WritingSystem`, `Text`, `Note`, `Filter`, ... (29 names) are phantom
> accessors of the same shape as `LexSense`; the fix addresses only 2 of 31.

Both derived this from the FLExProject `properties` block of
`src/flextoolsmcp/index/python/flexicon_api_v4.3.0.json`.

## Why it is wrong

The index enumerates 58 properties. The live `FLExProject` class exposes
considerably more — both singular and plural aliases. Checking all 43 shorthands
against `dir(FLExProject)` on the installed flexicon 4.3.0:

| bucket | count | meaning |
|---|---|---|
| absent from the live class | **2** | `LexSense`, `PhonologicalRule` — the real phantoms |
| present on live class, present in index | 12 | e.g. `POS`, `LexEntry`, `GramCat` |
| present on live class, ABSENT from index | **29** | e.g. `Example`, `WritingSystem`, `Text` |

The 29 disputed names are exactly the third bucket. They are real accessors that
the index under-reports — which is precisely the reason `_project_accessors()`
unions the legacy list in at all. Judging phantom-ness from the index produces 29
false positives.

**Consequence:** QC's recommendation to derive the allowlist from the index alone
would have removed 29 valid accessors and broken working user code. Rejected.

Reproduce with `python scripts/check_project_accessors.py`, written in response to
the confirmed P1 below. It deliberately uses `dir(FLExProject)` rather than the
index, so this specific mistake fails CI rather than being re-argued.

## Findings that were confirmed and fixed

1. **P0 — entry/sense argument mismatch** (author + domain). The sweep produced
   `project.Senses.GetAllSenses(entry)`; that method takes a sense. Both flavours
   duck-type on an `AllSenses` property, so an entry silently "works" instead of
   raising — which is why the issue reporter's live check appeared to pass. Fixed
   to `project.LexEntry.GetAllSenses(entry)` at all 6 sites; pinned by
   `TestGetAllSensesArgumentType`.
2. **P1 — dangling script reference** (QC + domain). `scripts/check_project_accessors.py`
   did not exist. Written.
3. **P0 pre-existing — broken template imports** (domain). `ReversalOperations`
   was not exported by flexicon; removed. `TestTemplateImportsResolve` then caught
   the same class of defect in `3-liblcm-template.py`, repointed to `SIL.LCModel`.

## Open judgment call

QC argues alias-sourced issues should REJECT rather than auto-fix, so the user's
saved source gets corrected rather than only the executed copy. Left as-is
(auto-fix already emits an "[ACTION REQUIRED] update your source file" note);
flagged to the user for a decision.
