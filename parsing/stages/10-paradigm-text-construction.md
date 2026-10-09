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
  [`reference/example-agglutinative-suffixing.md`](../reference/example-agglutinative-suffixing.md).
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
- **Cells generated by string concatenation over the template x lexicon**, which yields
  non-words wherever phonology, suppletion or agreement applies, and leaks homograph
  digits into forms (second operator, C-S7-05). Step 5's source table must hold real
  cells, not a slot cross-product.

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
  *Status 2026-10-09: still open (T-18).*
- `generate_paradigm_text(stems, cells)` -- build the text from the same table used to
  build the entries, guaranteeing no drift.
  *Status 2026-10-09: unverified -- not tracked in the status ledgers; the nearest
  piece is recipe `create-text-from-lines` (FlexToolsMCP #138).*
- A **collision report** across all texts and categories (M1 op 13).
  *Status 2026-10-09: unverified -- not tracked in the status ledgers.*
- An "unattested cell" marker: let a paradigm table declare a cell as
  attested / predicted / absent, and exclude non-attested cells from the text while
  keeping them visible in the table (L-M5-02).
  *Status 2026-10-09: unverified -- not tracked in the status ledgers.*
- A **negative test text** convention: forms that must get zero analyses, run as an
  over-generation check alongside the positive text (D-S7-08; T-22).
  *Status 2026-10-09: still open (T-22) -- `flextools_parse_text` over a "No Parse"
  text reports any analyses, but there is no over-generation tool; `parse_diff`'s
  `changed` bucket shows loosening on attested words only.*

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 and S6-S11 cover the logs of both machines. S6-S7 logs keep no tool output; S8 from 09-23 and S9-S11 do (truncated). The Claude Code transcripts behind S6-S11 supply the missing output, numbers and Matthew's own words where they exist (checked 2026-10-09). Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

- **CONFIRMS the predicted divergence: real text first** (D-S2-06, D-S4-02;
  [README 4.12](../README.md)). Most of Matthew's testing used real texts (Genesis, the
  narrative "Sungura na Fisi"), not constructed paradigms. Stages 10 and 12 merged.
- **ADDS: free translations on the test text** (D-S4-01). Each segment gets a free
  translation through the proper Free Translation function, which makes the analyses
  reviewable by someone who does not read the language.
- **When a paradigm text was built** (D-S5-08):
  - The design was one unambiguous singular/plural pair per noun class, with an English
    class label in an **English-tagged run in the same paragraph** so it is not parsed
    as vernacular. Mixed-writing-system rows are a new technique.
  - It broke two of this stage's rules: the forms came from general knowledge rather
    than attestation (step 2), and the text was not generated from the source table
    (step 5).
  - Its post-write check crashed after the commit (C-S5-03). Verify with a separate
    read-only operation.
    *Status 2026-10-09: the `get_WritingSystem` crash class is fixed in flexicon
    4.10.0 (flexicon#351). Still open: no wrapper creates a mixed-WS paragraph or
    reads a per-run WS (`Paragraphs` reads run 0 only), so that step is raw LCM.*

*S6-S11:*

- **REVISES D-S5-08 ("one paradigm text, late")** (D-S7-07, V-S7-04;
  [README 4.12](../README.md)). On 09-13 paradigm texts were generated for every
  template of every inflecting POS: 8 verb templates (three stems) plus noun,
  pro-form, adjective, quantifier, numeral, connective and demonstrative -- 16 texts,
  about 1,100 paragraphs. Each header says the forms were "generated mechanically from
  the template slots". (The generating session ran in another client; no transcript.)
- **CONTRADICTS steps 2 and 5** (C-S7-05). The generator concatenated strings over
  the slot cross-product, so it produced non-words (assimilation, suppletion,
  agreement) and leaked homograph digits. Matthew asked for a proofread ("Correct any
  grammatically incorrect forms"); the AI made 69 corrections (*maema* -> *mema*,
  *nyrefu* -> *ndefu*, *vimbili* -> *viwili*, *majino* -> *meno*, *vikijana* ->
  *vijana* ...). CONFIRMS Ron's L-M5-02 by counterexample; generating through the
  grammar is the T-22 direction.
- **ADDS: a negative partner text -- Matthew's design** (D-S7-08, C-S7-11). Matthew:
  "move invalid forms to different text with a genre of "No Parse"", then the same for
  verbs. Forms judged *structurally* invalid (number agreement, a relative marker that
  does not agree with the subject, object coreferent with subject) went into separate
  texts with the reason in each header: 537 verb forms in one text, 33 noun and 42
  numeral forms (9 and 30 kept). The label means "ungrammatical, hand-judged", not
  "fails to parse": the AI expected most moved forms to parse (wrongly), and the parser
  was never run on them. That makes the set a ready over-generation test: anything
  that parses there is over-generation. Name it for what it is (T-22).
- **ADDS: the text is the source; analyses are derived** (D-S7-09, C-S7-08; log only,
  no transcript). When a paradigm surface was wrong (morpheme order in the negative
  infinitive), Matthew stopped eight attempts to reorder morph bundles: "no, nothing
  about bundles, these are paragraphs". Fix the paragraph and let the parser regenerate
  the analyses.
- **ADDS: dry-run every text edit and re-read before writing** (C-S7-12). The evening
  proofread first read stale paragraphs (`tosema` where another session had just
  written `kutosema`); its dry run proposed *kukutosema* and caught the double prefix.
  Two sessions were editing the same texts.
- **ADDS: labelling partly meets the AI-data concern** (V-S7-07, C-S7-07; Q-42). The
  generated headers label the forms, and rejected forms carry a stated reason. Matthew
  directed the proofread and ruled on the irregular plurals, but the corrections were
  AI judgement, and the evening session never ran the parser (its words: "I never
  consulted FLEx's parser"). The AI-invented "must parse" probe passives (*kuvunjewa*,
  *kuchaguwa* ...) parse only because the grammar has the `ew` allomorph. No
  native-speaker or attested-corpus check appears.
- **ADDS: a corpus regression baseline instead of a paradigm text** (D-S10-05, T-S9-08,
  T-S10-07; tool output). From 09-24 on, no paradigm text was used. Before a
  grammar-wide change the baseline was the top frequent words plus every word containing
  the targeted segments. On 09-24 a 2,139-word set of this kind (top 2,000 plus glide
  words) finished in the sandbox and decided a rule question (see
  [Stage 08](08-phonological-rules.md)). On 09-25 the 1,783- and 1,610-word baselines
  (about 3.2 s/word, 95 minutes each) both died at word 173 when the MCP server
  restarted, and were never rerun; the agent had written its own baseline and diff
  scripts instead of using `parse_diff`. Size the set to parse time and run it in
  chunks. This extends README 4.12 ("both kept"): for grammar-wide regression, a
  frequency-plus-segment corpus set did this stage's job.
- **Gloss style affects reviewability** (D-S8-02). An 808-sense gloss cleanup adopted
  dotted lowercase grammatical glosses (`sbj.nc10`) labelled "Leipzig" though they are
  not Leipzig. Record the scheme as project-local if paradigm texts are reviewed by
  their interlinear glosses.

## Provenance

- M1 ops 6, 13, 15 (2026-09-10 16:18, 19:54, 20:42); D-M1-01; M1 §5 "Stems + paradigm
  text".
- M2 ops 1, 3, 5 (2026-09-10 15:36-20:46); **D-M2-01, D-M2-06**; L-M2-10.
- M4 op 7 (2026-09-12 17:09) -- 100 paragraphs x 6 forms = 600 words; D-M4-02.
- M5 ops 18-20, 28, 32, 47-52 (2026-09-14 05:40 .. 10:55); **L-M5-02**; M5 §5 stage 4.
- M8 op 4 (2026-09-15 14:06) -- build-by-analogy from an existing paradigm/template.
- S6-S11: D-S7-07..D-S7-09, C-S7-05, C-S7-07, C-S7-08, C-S7-11, C-S7-12, V-S7-04,
  V-S7-07; D-S8-02; T-S9-08, V-S9-08; D-S10-05, T-S10-07. Counts and attributions
  checked against the Claude Code transcripts (09-13 evening, 09-24, 09-25).
- **Merge seam:** Merged from S1-S11 (both machines). Matthew built exhaustive generated paradigm texts once (09-13), with a "No Parse" negative partner of his own design (never parsed), then relied on real text and corpus regression baselines. Q-21: the generated texts used a few stems per template; the S5 text one pair per class. Q-42 stays open: no attested or native-speaker check of the generated forms.
  *(Original seam: Matthew may prefer real text from the start rather than constructed paradigms; if so, Stages 10 and 12 merge for him and the coverage guarantee has to come from somewhere else.)*

## Open Questions

- The corpus never states how to decide exhaustive vs representative sampling beyond
  "the cross-product is too big". Q-21.
- No coverage metric was ever computed; coverage was asserted by construction. Q-22.
