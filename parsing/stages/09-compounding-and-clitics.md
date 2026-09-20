# Stage 09 -- Compounding and Clitics

[Back to overview](../00-overview.md) | [Prev: Stage 08](08-phonological-rules.md) | [Next: Stage 10](10-paradigm-text-construction.md)

## Purpose

Model the word-formation that happens **outside** the inflectional template:
compounding, and clitics that attach beyond the last inflectional slot. These are a
separate stage because they use different FLEx machinery from Stages 05-07 and because
they interact with the phonological rules of Stage 08 at a different boundary.

## Entry Criteria

- [Stage 05](05-categories-and-templates.md): the template slot order is known, so you
  can establish that the clitic really does attach outside it.
- [Stage 06](06-stem-and-affix-population.md): the host stems and the clitic/compound
  members exist as entries with correct POS.
- [Stage 08](08-phonological-rules.md): the clitic-boundary behavior of the
  phonological rules is settled.

## Inputs

- The clitic inventory with each clitic's host category and attachment behavior.
- The compound types the language uses, with headedness.
- Boundary markers (the clitic boundary is distinct from the word-internal one).

## Procedure

### Clitics

1. **Check slot order first.**
   > "Check the Nominal inflection template slot order to see whether a clitic can
   > attach after Case." (D-M5-07)
   A clitic attaching after inflectional morphology is a **separate enclitic lexeme
   attaching outside the template**, not a slot filler. Do not squeeze it into a slot.
2. **Give the clitic the attached citation form, not the free-standing one.** The
   corpus found this necessary so that the project's boundary-sensitive phonological
   rules fire correctly on attachment (L-M5-05).
3. **Declare attachment explicitly.** An enclitic attaching to a category needs both a
   stem MSA carrying the host POS on its sense **and** the "attaches to" collection
   populated (M2 §6).
4. **Model hiatus-breaking / epenthesis at the clitic boundary.** The corpus used two
   different devices for the same class of phenomenon, at different times:
   - **Stored glide allomorphs** conditioned by vowel-final / syllabic-final host
     environments (L-M5-05, L-M6-08) -- seven enclitics given a glide allomorph.
   - **Affix-process rules** inserting the epenthetic segment (L-M3-03).
   - And in a third pass, **deleting** the stored alternates once a global phonological
     rule independently derived them (L-M3-05).
   Choose one per clitic and record why; do not leave both.
5. **Two process rules with the same environment cannot both fire on one entry** --
   two co-existing spellings need two entries (L-M3-04).
6. **Decompose a clitic-bearing closed class only where the composition is
   transparent.**
   > "Retire the whole-word indefinite pronoun entries that are now derived
   > compositionally." (D-M5-10)
   And only the transparent ones: the corpus retired nine and explicitly kept five that
   were not base+clitic (L-M5-07). Create the bases and their oblique stems first,
   verify the derivation parses, *then* retire -- with a content backup (see
   [Stage 13](13-cleanup-and-consolidation.md)).
7. **Cover every distinct host-final environment when sampling** (see
   [Stage 10](10-paradigm-text-construction.md)):
   > "Critical is to cover where there are enclitic allomorphs for different endings on
   > roots and suffixes" (D-M2-06)

### Compounding

8. **Create binary compound rules restricted by the member categories**, with
   headedness set explicitly. The corpus's compounds were right-headed
   (head-last = true) and category-restricted: Noun+Noun -> Noun, and
   Modifier+Noun -> Noun (L-M6-07).
9. **Handle loan-stratum truncation as a per-lexeme compound-form allomorph**, not as
   a general phonological rule, when it applies to a lexically defined set: the corpus
   added a dedicated compound stem for one loanword whose final segment truncates in
   compounds (L-M6-07).
10. **Check strata** after creating compound rules (M6 op 29).
11. **If a compound does not fire, check the POS of both members first** (M6 op 30) --
    a compound rule restricted to Noun+Noun will silently not apply if one member is
    filed under the wrong category.

## Linguistic Decisions Required

- **Clitic vs affix.** Does it attach outside the inflectional template? (D-M5-07.)
- **Which citation form a clitic gets** (attached vs free-standing) -- L-M5-05.
- **Which device handles boundary epenthesis**: stored allomorph, process rule, or
  global phonological rule. All three appear in the corpus for the same class of
  phenomenon.
- **Which whole-word forms are transparent compositions** and which are not (L-M5-07)
  -- a genuinely hard judgement Ron made by hand and the richest piece of morphological
  reasoning in the corpus.
- **Compound headedness and category restrictions** (L-M6-07).
- **Whether a compound-triggered alternation is general or lexical** (L-M6-07).

## QC / Exit Criteria

- Every clitic attaches outside the template, with attachment declared, and with one
  and only one device handling its boundary alternation.
- Retired whole-word entries were backed up, their bases exist, and the composed forms
  parse.
- Kept whole-word entries have a recorded reason for not being decomposed.
- Compound rules read back with correct left/right category and headedness.
- Compound rules actually fire on their intended examples -- tested, not assumed.
- Regression: forms that parsed before the clitic/compound work still parse.

## Common Failure Modes

- **A clitic modeled as an inflectional slot filler** when it attaches outside the
  template (D-M5-07).
- **Free-standing citation form** on an enclitic, stopping the boundary rules firing
  (L-M5-05).
- **Both a stored alternate and a rule deriving the same surface form**, producing
  duplicate parses (L-M3-05).
- **Two process rules with the same environment on one entry** -- neither works
  (L-M3-04).
- **Retiring a whole-word entry whose composition is not actually transparent**
  (avoided in the corpus only by Ron's explicit five-entry exclusion list, L-M5-07).
- **Compound rule not firing due to member POS** (M6 op 30), never resolved in-shard.
- **Casting rejections** on compound-rule member MSAs (C-M6-04).

## Automation Notes

**Automatable now:** clitic and compound rule creation; attachment declaration;
glide-allomorph bulk addition with environments; backup-then-retire.

**Human required for:** the transparency judgement (L-M5-07), headedness, and the
device choice for boundary epenthesis.

**Missing tooling (requirements):**
- **`why_didnt_this_compound(form)`** -- given a compound that should parse, report
  which rule was closest and which restriction blocked it (member POS, stratum,
  headedness). M6 op 30 is exactly this question, asked by hand and left unanswered.
- **A clitic-boundary consistency report**: per clitic, is its alternation carried by
  an allomorph, a process rule, or a global rule -- and flag any carried by more than
  one.
- **A decomposability report**: for a closed class, which surface forms segment as
  base+clitic given the existing bases and clitics, and which do not -- the mechanical
  half of L-M5-07, leaving the human only the semantic judgement.
- Attachment declaration as a wrapper call (the corpus had to drop to raw LCM, M2 §6).

## Provenance

- M2 ops 2-4, 12 (2026-09-10 19:45-19:52; 09-11 14:34); **D-M2-06**; L-M2-09; M2 §6.
- M3 ops 5-8, 13-14 (2026-09-11 15:10-17:14); L-M3-03, L-M3-04, L-M3-05.
- M5 ops 22, 42, 54-61 (2026-09-14 05:44 .. 12:21); **D-M5-07, D-M5-09, D-M5-10**;
  L-M5-01, L-M5-05, L-M5-06, **L-M5-07**, L-M5-08.
- M6 ops 27-30 (2026-09-14 16:47-17:25); **L-M6-07, L-M6-08**, L-M6-09; C-M6-04;
  M6 §5 stage 6.
- **Merge seam:** Matthew's clitic conventions, and whether his projects use compound
  rules at all.

## Open Questions

- Whether a Noun+Verb compound rule was ever created, and why the expected compound
  did not fire (M6 §7). Q-10.
- Why one noun takes enclitics and a structurally similar one does not -- the
  comparison ran, the diagnosis was never recorded (M6 §7). Q-19.
- The gloss/definition content of the complementizer enclitic is not recoverable from
  the logs (L-M6-09). Q-20.
</content>
</invoke>
