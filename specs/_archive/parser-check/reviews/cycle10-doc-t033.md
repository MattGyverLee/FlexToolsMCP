# Cycle 10 -- Doc Agent -- T033

**Section added:** `## \`flextools_grammar_health\` scan implementation table (SPEC 9.5.4)`
in `specs/parser-check/data-model.md`, inserted after the existing `FoundObject`
block and before `## Validation rules`. Contains a scope note, a check_id-slug
note (only row 1's slug was fixed elsewhere; I assigned the other nine), the
five cross-cutting notes (numbered 1-5) plus two more required by the prompt
(`IMoInflAffixSlot` is not `ICmPossibility`; `Disabled` gates every rule-based
check before counting), an overview table (check_id / owning task / gated? /
cast_example), and a predicate+wording table (LCM predicate / `measured`
phrasing / `evidence_basis`).

**Fully specified (ungated):** rows 1, 2, 3a (epenthesis), 4, 6, 7a
(`StemNameRA`), 8 (corrected), 9, 10 -- nine of eleven sub-checks.

**Gated on T016 (running concurrently, verdict not asserted):** row 3b
(metathesis), row 5, row 7b (`AlternateFormsOS`). Each is written as a
branch: confirmed -> normal `checks_run`/`findings` entry; not confirmed ->
`checks_skipped` entry with reason exactly `lcm_name_unverified`.

**Cross-cutting notes confirmed present:** (1) cast guidance with the 32/37
and 31/36 statistics plus a base-vs-subtype rule for when a cast is actually
needed, verified against `casting_index_liblcm-v11.0.0.json`'s
`requires_cast_from` entries for `StemNameRA`, `OrderNumber`,
`InitialStratumRA`, `FinalStratumRA`, `StrucDescOS`; (2) the `form in (None,
"", "***")` predicate with an explicit CLAUDE.md cross-reference stating the
Flexicon Operations-layer normalization does not apply on this direct-LCM
path; (3) `OrderNumber` stratum-pair-only comparability; (4) gated sub-checks
and the `checks_skipped` fallback; (5) the index-inheritance trap, verified
directly against `liblcm_api_v11.0.0.json`'s `IMoStemAllomorph` entity record
(its own `properties` array lists only `PhoneEnvRC`/`StemNameRA`).

**Predicate found underspecified in SPEC 9.5.4 for an implementer:** row 1's
`measured` wording. The existing contract example
(`flextools_grammar_health.md`) reads "reachable from an optional slot", but
T034 states CP1 counts every zero-surface `IMoForm` unconditionally (no
slot-reachability walk -- that needs a CP2 flexicon gap per research D5). SPEC
9.5.4 does not itself flag this wording mismatch. I resolved it in the table
by giving CP1 its own wording basis and calling out the contract's phrasing as
CP2-only; flagging here in case `/lex-lead` wants the contract doc's example
corrected too (out of my file scope -- `flextools_grammar_health.md` is a
contract, not this table).

**Not touched:** `SPEC.md`, `research.md`, `tasks.md`, anything under `src/`
or `tests/`. No checkboxes ticked, no commit made.

---
**Doc Agent:** /lex-doc
