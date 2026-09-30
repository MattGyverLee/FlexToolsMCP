# Cycle 2 Archivist: CP2-SPEC.md Section 7 Correction

## Edit performed
File: specs/parser-check/CP2-SPEC.md, section 7 (~lines 366-381).

**Before:**
- `parse_morph_unresolved` | `morph`, `candidates`, `position`, `hint`
- Preamble: "count bumped from 22."

**After:**
- `parse_morph_unresolved` | `morph`, `candidates`, `position`, `hint`, `resolved_to`*
- Footnote added: `* resolved_to is one of: none | ambiguous | no_msa.`
- Preamble: "count bumped from 22 to 25."

## SPEC.md section 14 cross-check
Read SPEC.md line 1987:
`parse_morph_unresolved` | `morph`, `position`, `resolved_to` (`none` | `ambiguous` | `no_msa`), `candidates`, `hint`

**Field set:** matches (same five names: morph, candidates, position, hint, resolved_to).
**Enum values:** match exactly (`none` | `ambiguous` | `no_msa`).

## Discrepancy found (reported, not silently reconciled)
**Field ORDER differs.** SPEC.md orders: morph, position, resolved_to, candidates, hint.
The dispatch instruction mandated: morph, candidates, position, hint, resolved_to.
Per instructions I wrote the mandated order verbatim and am flagging this order
mismatch for lex-lead/synthesis to resolve against SPEC.md if cross-document
field-order consistency is later required.

## Scope
Only specs/parser-check/CP2-SPEC.md touched. No branch, no commit made.
