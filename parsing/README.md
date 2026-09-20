# Building a Parsing Lexicon in FLEx -- A Workflow Spec

This directory is a **reusable process spec** for building clean, well-researched
*parsing* lexicons in FieldWorks Language Explorer (FLEx): lexicons whose acceptance
test is "the FLEx / HermitCrab parser produces the attested surface forms", not
"the dictionary looks nice".

It is derived from a real corpus of work, not invented. Everything here is
traceable to a directive, linguistic finding, or correction recorded in the
extraction shards (see [`evidence/directive-index.md`](evidence/directive-index.md)).

---

## 1. Where this came from

| Shard | Dates | Project | Content |
|---|---|---|---|
| M1 | 2026-09-10 .. 09-11 | Malayalam AI (parsing) | phoneme inventory, templates, stems/affixes, features, first phonological rules, first affix-process rules |
| M2 | 2026-09-10 .. 09-11 | Malayalam AI | postposition/enclitic text, demonstrative paradigm, first parse-failure diagnosis loop |
| M3 | 2026-09-11 .. 09-12 | Malayalam AI | parse-speed regression, duplicate-parse triage, natural-class convention, verb inflection classes |
| M4 | 2026-09-12, 09-14 | Malayalam AI | new conjugation classes, 100-verb bulk build, stem-name/inflection-feature refactor |
| M5 | 2026-09-13 .. 09-14 | Malayalam AI | largest session (78 ops): POS catalog bootstrap, variant/inflection-variant modeling, HermitCrab parse loop, clitic decomposition, Aesop corpus |
| M6 | 2026-09-14 .. 09-15 | Malayalam AI | Matthew 2 import, compound rules, derivation-vs-inflection correction |
| M7 | 2026-09-15 | Malayalam AI | oblique augment, bulk delete + restore, anusvara phonological rule. **Its section 9 is the converged-process view.** |
| M8 | 2026-09-15 | Malayalam AI | final sessions: Numeral POS by analogy, past-variant-entry architecture. **Its section 9 is the end state.** |
| G1 | 2026-09-04 .. 09-05 | German VOCABULARY deck | a *different kind of project*; contributes process hygiene only |

**The operator throughout was Ron.** The AI assistant was FlexToolsMCP-driven.

### Critical framing: Ron does not know Malayalam

Ron is an expert computational linguist with strong analytical intuition. He does
**not** speak Malayalam. Therefore:

- **His transferable contribution is METHOD** -- how to model, how to decompose a
  problem, how to debug a parse failure, how to verify a fix, and when to distrust
  a result.
- **Every Malayalam claim in this spec is a hypothesis**, either asserted by Ron on
  analytic grounds or proposed by the AI and accepted by Ron. None of it is
  native-speaker verified.
- The `reference/` files therefore document **"the analysis this project arrived at,
  and how it was arrived at"** -- carrying each item's `status`
  (`asserted-by-Ron` / `AI-proposed-accepted` / `unresolved`) -- and must **not** be
  read as authoritative Malayalam grammar.

### The German shard is a different animal

G1 is a **vocabulary/deck** project. It builds no phoneme inventory, no features,
no natural classes, no phonological rules, no affix templates, no inflection
classes, and runs no parser. Per its own section 9, only its **language-independent
process discipline** is imported here -- into
[`conventions/flex-data-conventions.md`](conventions/flex-data-conventions.md),
[Stage 01](stages/01-project-survey-and-inventory.md) and
[Stage 06](stages/06-stem-and-affix-population.md). Nothing from G1 shapes the
grammar-construction or parse-verification stages.

---

## 2. How to read this

Start at **[`00-overview.md`](00-overview.md)** -- the philosophy and the stage map.

Then:

- **`stages/NN-*.md`** -- the process itself, numbered in **execution order**. Every
  stage has the same eight-plus headings so stages can be compared, skipped, or
  re-entered. Stages are *iterative*, not a waterfall: Stage 11 (parse and repair)
  routinely sends you back to 04, 07, or 08.
- **`reference/`** -- the linguistic and modeling content the project arrived at.
  - [`flex-modeling-decisions.md`](reference/flex-modeling-decisions.md) is the
    **highest-value generalizable file in this directory**: which FLEx construct to
    reach for in which linguistic situation, as a decision table. Read it before
    Stage 07.
  - [`malayalam-morphophonology.md`](reference/malayalam-morphophonology.md),
    [`natural-classes.md`](reference/natural-classes.md), and
    [`allomorphy-environments.md`](reference/allomorphy-environments.md) are
    **language-specific worked examples** -- illustrative, unverified.
- **`conventions/`** -- the non-negotiables:
  [data conventions](conventions/flex-data-conventions.md) and
  [AI collaboration guardrails](conventions/ai-collaboration-guardrails.md).
- **`evidence/directive-index.md`** -- every D-/L-/C- id from all nine shards, one
  row each, with where it landed. Use it to audit a claim.
- **[`open-questions.md`](open-questions.md)** -- what is still unresolved and who
  can resolve it.
- **[`MERGE-NOTES.md`](MERGE-NOTES.md)** -- explicit seams for merging Matthew's
  process later, plus the MCP parsing-tooling requirements this spec implies.

### Notation used throughout

- `(D-M5-03)` etc. cite a directive / finding / correction in the evidence index.
- `(inferred)` marks anything the shards do not state but this spec concludes.
- Ron's verbatim wording is kept in quotes wherever it is load-bearing.
- No emojis anywhere (Windows console constraint).

---

## 3. Status

| Aspect | Status |
|---|---|
| Stage decomposition | **Derived** from shard section 5 across all nine shards; conflicts resolved toward the late-corpus (M7 §9 / M8 §9) form |
| Provenance | **Complete** -- 179 ids indexed, see [`evidence/directive-index.md`](evidence/directive-index.md) |
| Malayalam linguistic content | **Unverified by a native speaker.** Hypotheses only |
| Parse-and-repair stage (11) | Written as it **should** work with in-MCP tooling; the corpus did this partly out-of-band. Tooling gaps listed in [`MERGE-NOTES.md`](MERGE-NOTES.md) |
| Matthew's process | **Not yet merged.** Seams marked in [`MERGE-NOTES.md`](MERGE-NOTES.md) and in each stage's Provenance section |
| Generality | Stage bodies are language-neutral; all language-specific material is confined to `reference/` |

---

## 4. Conflicts and Divergences

Where the corpus disagrees with itself. These are real, and important: they are the
places where somebody learned something. **Where early and late practice conflict,
this spec follows the late (converged) practice** and records the early form here.

### 4.1 Past-stem alternation: stem name keyed to a tense feature (M4) vs. Past variant entry (M8)

**This is the single biggest divergence in the corpus.** The same problem gets two
incompatible architectures three days apart.

- **M4 reading (2026-09-12 23:20, D-M4-03, L-M4-03/04).** A stem allomorph that
  alternates on a *grammatical* (not phonological) condition should be selected by a
  FLEx **stem name** tied to an `MsFeatureSystem` region, with the consuming affixes
  (PAST/NEG.PAST/COND/CONC) carrying matching `InflFeats`. Motivation: a right-context
  environment cannot tell PAST `-u` from IMP `-u`, and the environment pre-empts the
  lexeme form even when the alternate's string does not match the surface -- that is
  what made 14 class-C imperatives unparseable. M6 (L-M6-04) then extends this,
  discovering that the tense feature objects must be the *same* `IFsFeatureSpecification`
  objects the working PAST suffix uses, not newly created look-alikes.
- **M8 reading (2026-09-15 16:40, D-M8-05).** Ron diagnoses the residual defect himself:
  *"the downside of this, I think is that a non-past stem of a verb could get married
  with a NMLZ suffix or any past suffix and be seen as valid since the inflection class
  on the verb applies to all allomorphs. To mitigate this we could create a variant for
  past stems and add a sense to that stem so that we can put the right inflection class
  on the msa object."* The fix: split each past stem into **its own `LexEntry`, a
  "Past" variant** with its own sense and MSA carrying the past inflection class;
  strip the class from the non-past stem; delete the now-redundant stem-named
  allomorph. Proven on one verb ("do"), generalized to three suffixes, then bulk-applied
  to 101 verbs.
- **Root of the divergence.** `InflectionClassRA` on a stem's MSA is
  **allomorph-global**. A stem name restricts which *affix* can see an allomorph, but it
  does not give per-allomorph inflection-class behavior. So M4's mechanism solved the
  *selection* problem and left an *over-generation* problem that only surfaced later,
  under the derivational suffixes added in M6.
- **This spec follows M8.** See
  [`reference/flex-modeling-decisions.md`](reference/flex-modeling-decisions.md) row
  "grammatically-conditioned stem alternation" and
  [Stage 07](stages/07-allomorphy-modeling.md). The M4 stem-name mechanism is retained
  as a *secondary* device (it is still what makes the affix select the right stem),
  not as the primary carrier of class behavior.

### 4.2 Affix-process rules everywhere (M1) vs. environments + inflection classes (M3 onward)

- **M1 reading (2026-09-11 12:42-12:48, D-M1-10, C-M1-06).** Only the LOC case suffix
  parsed. Diagnosis: plain `MoAffixAllomorph` alternates were shadowing the
  `MoAffixProcess` rules on the same entry. Remedy: *"Convert every remaining plain
  affix allomorph into an affix process rule so each entry matches the working LOC
  shape."* Corollary (C-M1-05/D-M1-11): after conversion the entry's citation
  `LexemeForm` became unreachable and had to be restored as an explicit alternate.
- **M3 onward reading (from 2026-09-11 19:28, D-M3-05).** Ron shifts to plain
  allomorphs **constrained by phonological environments**, with shared environments
  factored into **named natural classes**, and grammatical conditioning carried by
  **inflection classes**: *"would it work to make a natural class of each set of 4 that
  would be easier to maintain."* By M3 L-M3-13 the FLEx architecture fact is explicit --
  "the lexeme form is the elsewhere case, ordered last under negation of every
  environment above it" -- which is exactly what an affix-process-only entry throws away.
- **Assessment.** Both readings are internally correct. The M1 uniformity rule
  ("do not mix plain and process alternates on one entry") remains true and is kept.
  What changed is *reach for the cheaper device first*: affix-process rules are now
  reserved for genuinely **non-concatenative** allomorphy (segment replacement,
  truncation, the oblique augment of M7 L-M7-01), and everything concatenative is a
  plain allomorph plus an environment or inflection class. This spec follows the late
  form; see [`reference/flex-modeling-decisions.md`](reference/flex-modeling-decisions.md).

### 4.3 Widen phonological rule environments (M2) vs. anchor them tightly (M3)

- **M2 (2026-09-11 14:31, L-M2-07).** Chillu-vocalization and virama-deletion rules were
  widened to fire across clitic boundaries as well as word-internal ones, adding an
  *unanchored* bare-natural-class right context.
- **M3 (2026-09-11 14:59 / 16:06, D-M3-02, L-M3-02).** Ron: *"the parsing speed slowed
  down considerably after that last set of fixes... 9.6 seconds to parse... Total parse
  time for all 438 words was 4 minutes even."* Root cause: *"an unanchored environment
  is one whose right context is a bare natural class with no boundary marker -- that is
  what makes rule un-application explode."* The unanchored right-hand sides were deleted;
  boundary-anchored ones kept.
- **Resolution.** Both the coverage need and the cost are real. The rule is: widen by
  adding **another boundary-anchored** right-hand side, never by dropping the anchor.
  **Parse time is a first-class quality metric.** See
  [Stage 08](stages/08-phonological-rules.md).

### 4.4 Natural class vs. literal environment: factor out (M3) vs. keep dedicated (M5/M7)

- **M3 D-M3-05.** Factor a conditioning set shared by 4+ allomorphs into a named
  natural class with an English name; maintainability is an explicit design goal.
- **M5 D-M5-14 / C-M5-05.** The opposite failure: adding a phoneme to the *shared* PsF
  natural class to fix one verb subclass had project-wide blast radius. Ron reverses
  himself within four minutes: *"Revert the shared PsF change and add a dedicated nnu
  past class with its own allomorph and environment."*
- **M7 L-M7-03.** A purpose-built "Enclitic onset" natural class was created and then
  **abandoned** in favor of four exact per-segment environments, because the matra
  feature bundles turned out not to be distinguishable by feature structure alone.
- **Resolution.** Not a contradiction, a two-sided test, written up as a decision
  procedure in [`reference/natural-classes.md`](reference/natural-classes.md):
  create a class when the set is **shared and stable**; use a literal environment when
  the conditioning is **local to one lexical subclass** or when the members are not
  cleanly feature-definable. Never extend a shared class without checking referrers.

### 4.5 Oblique stems: allomorph vs. variant entry (unresolved within the corpus)

- **M6 L-M6-01** documents both conventions co-existing: obliques as `IMoStemAllomorph`
  conditioned by `/ _ [PACs]`, *and* obliques as separate `LexEntry`s linked by
  `ILexEntryRef` with variant type "Oblique". It counts entries carrying both and does
  not resolve the duplication.
- **M7 L-M7-04 / D-M7-07** runs the experiment explicitly: two `-vu` noun obliques are
  converted from variant entries to PACs-conditioned stem allomorphs at 11:17, then
  **fully reverted** at 11:39-11:40. The reason for the revert is never stated in-log.
- **M7 L-M7-01** meanwhile replaces 92 oblique variant entries with a single
  **inflectional affix** (the oblique augment in the Number slot) -- a third option.
- **Status: open.** Carried to [`open-questions.md`](open-questions.md) Q-04.

### 4.6 Nominalizers as inflection (M6 early) vs. derivation (M6 late)

Within a single session: nominalizers were added to a new `Nmlz` **inflectional** slot
on the verb template (op 16:28), then reversed at 16:39 -- *"the Nmlz slot was a
mistake: derivation does not belong in a template"* (C-M6-03, L-M6-06). Slot deleted,
MSAs converted to `IMoDerivAffMsa`. **Late form is the rule.**

### 4.7 Verb inflection-class granularity: 3 classes (M3) -> 2 (M3) -> 4 (M4) -> 5 (M8)

M3 L-M3-10 creates V1/V2/V3 keyed jointly to past shape *and* causative shape; L-M3-11
recognizes the two dimensions are orthogonal, splits the causative into its own affix
entry, and collapses to two classes. M4 L-M4-02 adds "Past -ccu" and "Past -ttu". M8
L-M8-01 records five: "Past -i", "Past -ttu", "Past -nnu", "Past -ccu", "Past -nnyu".
Not a contradiction -- an inventory growing with corpus coverage -- but a good
illustration of L-M3-11's methodological lesson: **factor a class system along its true
independent dimensions before growing it.**

### 4.8 Where the German shard would have distorted things

G1's QC loop is "spec vs database reconciliation". A parsing project's QC loop is "does
the parser produce the attested surface forms" (D-M2-04, D-M5-06). If G1's data-loading
shape were allowed into the grammar stages, Stage 11 would disappear and Stage 12 would
become a verification step rather than a discovery step. It is not. G1 contributes only
to Stages 01 and 06 and to the conventions files.

---

## 5. Contents

- [`00-overview.md`](00-overview.md)
- `stages/`
  - [01 -- Project Survey and Inventory](stages/01-project-survey-and-inventory.md)
  - [02 -- Phoneme Inventory](stages/02-phoneme-inventory.md)
  - [03 -- Phonological Features](stages/03-phonological-features.md)
  - [04 -- Natural Classes](stages/04-natural-classes.md)
  - [05 -- Categories and Inflection Templates](stages/05-categories-and-templates.md)
  - [06 -- Stem and Affix Population](stages/06-stem-and-affix-population.md)
  - [07 -- Allomorphy Modeling](stages/07-allomorphy-modeling.md)
  - [08 -- Phonological Rules](stages/08-phonological-rules.md)
  - [09 -- Compounding and Clitics](stages/09-compounding-and-clitics.md)
  - [10 -- Paradigm Text Construction](stages/10-paradigm-text-construction.md)
  - [11 -- Parse and Repair Loop](stages/11-parse-and-repair-loop.md)
  - [12 -- Real-Corpus Stress Test](stages/12-real-corpus-stress-test.md)
  - [13 -- Cleanup and Consolidation](stages/13-cleanup-and-consolidation.md)
- `reference/`
  - [malayalam-morphophonology.md](reference/malayalam-morphophonology.md)
  - [natural-classes.md](reference/natural-classes.md)
  - [allomorphy-environments.md](reference/allomorphy-environments.md)
  - [flex-modeling-decisions.md](reference/flex-modeling-decisions.md)
- `conventions/`
  - [flex-data-conventions.md](conventions/flex-data-conventions.md)
  - [ai-collaboration-guardrails.md](conventions/ai-collaboration-guardrails.md)
- `evidence/`
  - [directive-index.md](evidence/directive-index.md)
- [open-questions.md](open-questions.md)
- [MERGE-NOTES.md](MERGE-NOTES.md)
</content>
</invoke>
