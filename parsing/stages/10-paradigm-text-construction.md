# Stage 10 -- Paradigm Text Construction

[Back to overview](../00-overview.md) | [Prev: Stage 09](09-compounding-and-clitics.md) | [Next: Stage 11](11-parse-and-repair-loop.md)

## Purpose

Build the parser's **targeted test suite**: a constructed text whose wordforms are
exactly the paradigm cells the grammar is supposed to generate. This is what
Stage 11 parses, and it is what makes a parse failure diagnosable -- you know what the
form was supposed to be.

> "Populate the project with a paradigm text of nouns in different inflections. This
> means different permutations of words, e.g. singular nouns, plural nouns, case
> marked nouns, etc." (D-M2-01)

## Entry Criteria

- [Stage 06](06-stem-and-affix-population.md) and
  [Stage 07](07-allomorphy-modeling.md) complete for the paradigm in question.
- A source-of-truth paradigm table exists, with an offline `check()` validator
  (M2 §6).

## Inputs

- The paradigm table: for each stem, every cell's intended surface form.
- The existing text inventory (for collision checking).
- An existing, working paradigm text to copy the format of (M5 op 28).

## Procedure

1. **Decide the sampling strategy.** Two modes appear in the corpus:
   - **Exhaustive** for a core paradigm: one paragraph per stem, every cell
     (10 stems x 14 forms = 140 wordforms; later 100 verbs x 6 forms = 600).
   - **Representative** for combinatorially large spaces:
     > "you don't need to add every permutation, but a representative sample of nouns
     > and affixes from the [core] text along with different postpositions that are
     > ones that attach. **Critical is to cover where there are enclitic allomorphs for
     > different endings on roots and suffixes**" (D-M2-06)
     The sampling criterion is **coverage of every allomorph-triggering environment**
     -- every distinct final-segment class of every host -- not "some examples".
2. **Do not invent unattested cells.** Cells with zero corpus attestation were
   deliberately omitted rather than filled in (L-M5-02). An invented cell that fails to
   parse wastes a debugging cycle on a form that may not exist.
3. **One text per coherent paradigm domain.** The corpus built separate texts per
   domain (noun paradigm; noun + postposition; demonstrative paradigm; verb paradigm;
   pronoun paradigm), which makes per-text parse reporting meaningful.
4. **Copy the format of an existing working paradigm text** rather than inventing a
   layout (M5 op 28) -- case order and row structure should match across texts so the
   reader and the diagnostics can align them.
5. **Build the text programmatically from the same source table** used to build the
   entries, so the two cannot drift.
6. **Check for wordform collisions across texts and categories** before writing --
   identical surface forms in different paradigms make the parse report ambiguous
   (M1 op 13). Note the related entry-lookup hazard: when two categories have
   identically-shaped affixes, an existence check by form alone cannot tell them apart
   (L-M2-10).
7. **Create the text idempotently** (guard on title) and force segmentation if segments
   do not auto-populate; then set free translations (M5 §5 stage 4).
8. **Verify** paragraph, segment and token counts against the intended table size.

## Linguistic Decisions Required

- **Which cells the paradigm has** -- the shape of the paradigm itself is a linguistic
  claim. The corpus's noun/pronoun case inventory and its verb TAM inventory are
  hypotheses; see
  [`reference/malayalam-morphophonology.md`](../reference/malayalam-morphophonology.md).
- **Which cells are attested** (and therefore included) versus merely predicted
  (L-M5-02).
- **What counts as a distinct allomorph-triggering environment**, for the sampling
  criterion (D-M2-06). This determines whether the test suite actually tests anything.
- **Whether a surface homophony across cells is real**, because it will show up as a
  multi-parse later and you need to know in advance whether to accept it (D-M3-04,
  L-M3-06).

## QC / Exit Criteria

- Paragraph / segment / token counts match the intended table exactly.
- Every allomorph-triggering environment identified in Stage 07 appears at least once
  in some text.
- No cell in the text is an invented form.
- Wordform collisions across texts are known and listed (not necessarily eliminated).
- The text was generated from the same source table as the entries.

## Common Failure Modes

- **A sample that does not cover the triggering environments**, so the parse run
  reports success while whole allomorph classes are untested (the thing D-M2-06 exists
  to prevent).
- **Invented cells** producing phantom parse failures (avoided by L-M5-02's rule).
- **Wordform collisions** making the parse report unattributable (M1 op 13).
- **Drift between the paradigm table and the lexicon**, because the text was authored
  separately.
- **Segments not auto-populating**, so the text looks created but has no parseable
  tokens (M5 §5 stage 4).
- **Entry-existence checks by form alone** failing to distinguish same-shaped affixes
  in different categories (L-M2-10).

## Automation Notes

**Automatable now:** text/paragraph creation, idempotency guard, segmentation forcing,
free translations, and all the count verification.

**Human required for:** the paradigm shape, attestation judgements, and the sampling
criterion.

**Missing tooling (requirements):**
- **`environment_coverage_report(text)`** -- for each allomorph and each conditioning
  environment in the grammar, does any wordform in the test texts exercise it? This is
  D-M2-06's criterion, mechanized, and it is the single most valuable missing tool for
  this stage. It is a *test coverage report for a grammar*.
- `generate_paradigm_text(stems, cells)` -- build the text from the same table used to
  build the entries, guaranteeing no drift.
- A **collision report** across all texts and categories (M1 op 13).
- An "unattested cell" marker: let a paradigm table declare a cell as
  attested / predicted / absent, and exclude non-attested cells from the text while
  keeping them visible in the table (L-M5-02).

## Provenance

- M1 ops 6, 13, 15 (2026-09-10 16:18, 19:54, 20:42); D-M1-01; M1 §5 "Stems + paradigm
  text".
- M2 ops 1, 3, 5 (2026-09-10 15:36-20:46); **D-M2-01, D-M2-06**; L-M2-10.
- M4 op 7 (2026-09-12 17:09) -- 100 paragraphs x 6 forms = 600 words; D-M4-02.
- M5 ops 18-20, 28, 32, 47-52 (2026-09-14 05:40 .. 10:55); **L-M5-02**; M5 §5 stage 4.
- M8 op 4 (2026-09-15 14:06) -- build-by-analogy from an existing paradigm/template.
- **Merge seam:** Matthew may prefer real text from the start rather than constructed
  paradigms; if so, Stages 10 and 12 merge for him and the coverage guarantee has to
  come from somewhere else.

## Open Questions

- The corpus never states how to decide exhaustive vs representative sampling beyond
  "the cross-product is too big". Q-21.
- No coverage metric was ever computed; coverage was asserted by construction. Q-22.
</content>
</invoke>
