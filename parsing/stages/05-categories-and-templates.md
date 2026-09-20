# Stage 05 -- Categories and Inflection Templates

[Back to overview](../00-overview.md) | [Prev: Stage 04](04-natural-classes.md) | [Next: Stage 06](06-stem-and-affix-population.md)

## Purpose

Build the morphosyntactic skeleton: the part-of-speech inventory, and per-POS
inflectional affix templates with ordered, correctly-optional slots. This is what
Stage 06's affix entries plug into and what constrains what the parser will even
attempt.

## Entry Criteria

- [Stage 01](01-project-survey-and-inventory.md) complete: the existing POS tree,
  templates and slots are known, including which slots are shared via a parent
  category.
- A first-pass morphological analysis exists: which categories inflect, for what, in
  what order.

## Inputs

- FLEx's built-in grammatical-category catalog.
- The target category inventory.
- The morphotactic order of affix positions per inflecting category.

## Procedure

1. **Take categories from the catalog, do not invent them.**
   > "Use the grammatical category catalog if the project doesn't currently have a
   > needed category." (D-M5-01)
   Record provenance via the catalog source id. Nest sub-categories under the right
   parent -- the parent is what carries shared inflection slots.
2. **Build a new category by analogy with a working one.**
   > "Inspect the Demonstrative template so a Numeral category can be built the same
   > way." (D-M8-03)
   Do not build a template from scratch when a structurally analogous, *parsing*
   category already exists. Bundle the POS item, its template (referencing an existing
   shared slot where appropriate), and its initial lexical population into one
   validated pass (D-M8-04).
3. **Split a category when only some members inflect.**
   > "Create an Interrogative pronoun category under Nominal>Pronoun and move the three
   > declinable interrogatives into it." (D-M5-08)
   Category membership tracks **morphosyntactic behavior (template inheritance)**, not
   semantic or functional grouping.
4. **Create the affix template and its slots in explicit order.** Slot order is a
   linguistic claim; set it explicitly by index rather than relying on creation order
   (M1 §5).
5. **Set each slot's optionality from a language fact.**
   - Optional when the bare stem is itself a word (the corpus's noun Number and Case
     slots were optional so the bare stem parses).
   - **Non-optional** when it is not:
     > "Create the Verb affix template with a required TAM slot" -- *"Not optional: a
     > bare verb stem is not a word, every form carries exactly one tense/aspect/mood
     > suffix."* (D-M1-02)
6. **Insert new slots at the right position relative to existing ones.** The corpus
   inserted Causative and Voice as optional slots *before* the required TAM slot,
   giving root-Causative-Voice-TAM (D-M1-03). Order is a morphotactic claim; state it.
7. **Give invariant categories no template at all.** A category whose members never
   inflect should own **zero** templates and slots, not an empty template -- that is
   what prevents the parser from ever attaching case to them (M2 §6, L-M2-10).
8. **Never put derivation in an inflectional template.** A category-changing affix
   belongs on a derivational MSA, not in a slot:
   > "the Nmlz slot was a mistake: derivation does not belong in a template"
   > (C-M6-03, L-M6-06)
   Test before adding an affix to a slot: *does this affix change the word's part of
   speech?* If yes, it is derivation.
9. **Check slot order before assuming a clitic fits in one.** Clitics attaching outside
   inflectional morphology are separate enclitic lexemes, not slot fillers
   (D-M5-07). See [Stage 09](09-compounding-and-clitics.md).
10. **Re-inspect the tree periodically.** The human may restructure categories in the
    FLEx GUI mid-session -- in the corpus, the Pronoun category was moved under Nominal
    by hand so it would share the Case slot (D-M5-02).

## Linguistic Decisions Required

- **Which categories inflect, and for what.**
- **Slot inventory and order** per category -- a morphotactic claim.
- **Optionality per slot** -- equivalently, "can the bare stem surface as a word?"
- **Shared vs per-category slots.** A slot owned by a parent category and shared by
  children is a strong claim that the children inflect identically. The corpus's
  Nominal Case slot is shared by Noun, Demonstrative, Pronoun and later Numeral.
- **Inflection vs derivation** per affix (the C-M6-03 test above).
- **Declinable vs indeclinable sub-categories** (D-M5-08).
- Note that a category boundary can also have a *reachability* consequence: the corpus
  filed anusvara-final big numerals under Noun rather than Numeral precisely because
  the augment they need "lives in the Noun template's Number slot and is not reachable
  from a sibling category" (L-M8-02). Category assignment is partly a mechanism
  decision, not purely a taxonomic one.

## QC / Exit Criteria

- Every category needed by the target lexicon exists, catalog-sourced where possible,
  correctly nested.
- Every inflecting category has a template with ordered slots; slot order recorded.
- Slot optionality is set and each setting is justified by a stated language fact.
- Invariant categories own zero templates/slots.
- No category-changing affix is attached to an inflectional slot.
- Slot filler counts match the number of affix entries you intend to create in
  Stage 06.
- POS names used by downstream scripts are **derived from the created objects**, not
  re-typed (see Failure Modes).

## Common Failure Modes

- **POS name mismatch between the creation script and the consumer script.** In the
  corpus this failed all 69 rows of a bulk import with "POS not found" (C-M5-01).
  Derive names from the created objects or a shared constants module.
- **Derivation placed in an inflectional slot** (C-M6-03) -- caught only after the
  parser selected the wrong stem.
- **An empty template instead of no template** on an invariant category.
- **Assuming a slot's optionality** instead of deciding it. An optional TAM slot lets
  bare verb stems parse as words; a required Number slot stops bare nouns parsing.
- **Shallow possibility-list search** when resolving categories or variant types
  (C-M6-02).
- **Polymorphic casting rejections** when walking templates and slots (C-M8-02,
  C-M8-03: `StemNameRA` does not exist on an affix template; C-M6-04).
- **Not noticing a human restructured the tree** (D-M5-02).

## Automation Notes

**Automatable now:** catalog-sourced category creation, template/slot creation with
explicit ordering, build-by-analogy (clone an existing template's shape), and all the
QC assertions.

**Human required for:** slot inventory, order, optionality, and the
inflection/derivation call.

**Missing tooling (requirements):**
- `clone_template(from_pos, to_pos)` -- mechanize D-M8-03's build-by-analogy.
- **An inflection/derivation lint**: warn when an affix entry attached to an
  inflectional slot has an MSA whose from-POS and to-POS differ, or when a
  derivational-looking gloss is slotted. This is C-M6-03 as a guardrail.
- A morphotactics report: per POS, the slot order, optionality, and fillers, in one
  view -- the corpus hand-wrote this repeatedly.
- Shared-slot impact report: "this slot is shared by these N categories".
- A category-name registry so creation and consumption cannot diverge (C-M5-01).

## Provenance

- M1 ops 5, 10, 15 (2026-09-10 16:16, 19:52, 20:42); D-M1-02, D-M1-03; M1 §5
  "Inflection template + affix entries (per POS)".
- M2 op 5 (2026-09-10 20:30); L-M2-10; M2 §6 (invariant categories own no template).
- M5 ops 9-10, 24-25, 34, 42-46 (2026-09-13 23:06 .. 09-14 10:50); D-M5-01, D-M5-02,
  D-M5-07, D-M5-08; C-M5-01; M5 §5 stages 2 and 6.
- M6 ops 17-18, 25 (2026-09-14 16:26-16:39); **C-M6-03**, L-M6-03, L-M6-06.
- M7 op 8-9 (2026-09-15 08:18) -- augment built as a Number-slot affix; L-M7-01.
- M8 ops 2, 4-6 (2026-09-15 14:04-14:09); D-M8-03, D-M8-04; L-M8-02; C-M8-03.
- **Merge seam:** Matthew's category inventory and slot conventions; in particular
  whether he uses shared parent-category slots at all.

## Open Questions

- The corpus never states a rule for *when* to introduce a shared parent category
  (Nominal) versus duplicating slots per child. Q-09.
- Whether a Noun+Verb compound rule was ever actually created, and why the expected
  compound did not fire (M6 §7). Q-10.
</content>
</invoke>
