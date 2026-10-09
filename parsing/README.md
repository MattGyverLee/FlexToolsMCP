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
  analytic grounds or proposed by the AI and accepted by Ron. It may not be native-speaker verified.
- The `reference/` files therefore document **"the analysis this project arrived at,
  and how it was arrived at"** -- carrying each item's `status`
  (`asserted-by-Ron` / `AI-proposed-accepted` / `unresolved`) -- and must **not** be
  read as authoritative Malayalam grammar.

### Second operator: Matthew, Swahili

A second, independent corpus has been merged: Matthew's work on the FLEx project
**Claude-Swahili**, taken from the FlexToolsMCP runtime logs on two machines (S1-S5 from
one, S6-S11 from the other). The practitioner and the language are different, and so is
the language type: Bantu noun class agreement and verb templates instead of Dravidian
agglutination.

| Shard | Dates | Content |
|---|---|---|
| S1 | 2026-05-21 | greenfield build: POS, feature catalog, phonemes incl. an archiphoneme, natural classes, rules, noun-class features, CAWL wordlist import, templates |
| S2 | 2026-05-21 .. 05-22 | zero morphs, boundary anchoring, closed-class decomposition, real-text (Genesis) unanalyzed-wordform loop, analysis approval |
| S3 | 2026-06-17 .. 08-13, 09-20 | catalog-sourced noun-class features, frequency queue, per-entry parse-ready standard, Phase 0 baseline, licence policy, feature-matrix pruning |
| S4 | 2026-09-06 .. 09-07 | real interlinear text as test fixture, analysis rejection, over-generation diagnosis, concord cloning, disable-then-delete |
| S5 | 2026-09-07 .. 09-11 | template blocking, final-vowel verb classes, staleness scan, tiered manifest cleanup, interlinear gloss repair, domain rulings |
| S6 | 2026-09-12 | single-word triage (*akamwita*), lexeme form fixed as the elsewhere form, twin-slot idiom defended, template descriptions as design records |
| S7 | 2026-09-13 | parallel per-POS agents, verb extensions made derivational, Verb subcategories, HermitCrab driven by hand inside `run_module`, paradigm and "No Parse" texts |
| S8 | 2026-09-14 .. 09-23 | 808-sense gloss cleanup, concord senses per class, a local-model run that never parsed, the stale "unparsed" queue |
| S9 | 2026-09-24 | in-MCP parse loop: POS templates blocking free words, `amba-` relativizer, glide over-application, `parse_diff`, lock failures |
| S10 | 2026-09-25 | refile before triage, grapheme parse rates, exception-feature rule blocking, regression baseline, staged multi-agent fix-up |
| S11 | 2026-09-30 | a four-hour `run_module` loop on wrong queues; the top "unparsed" words already parse; probable junk entries |

**Read this first:**

- **Two kinds of log.** S1-S7 keep submitted code, requests and errors but **not**
  report output, so their results are read from code, docstrings and the next
  operation's framing. From 2026-09-23 on (late S8, S9-S11) the logs keep tool output,
  truncated at roughly 1-2 KB, so results there are measured. S6-S11 re-check many S1-S5
  claims that were only inferred (the `V-` rows in the
  [evidence index](evidence/directive-index.md)).
- **S6-S11 were re-checked against the Claude Code transcripts** behind those sessions
  (2026-10-09, with Matthew's permission). The transcripts supply the missing output,
  Matthew's verbatim words (the logs' `User request:` field was often agent-filled) and
  decisions the logs never saw. Each index row carries a **Transcript check** verdict,
  and transcript-only ids are marked "(from transcript)". No transcript exists for
  09-13 14:09-20:05, 09-14, the local-model sessions, the 09-25 second client and late
  Stage 1/2 sessions, or 09-30.
- **Version label.** The logs say FlexToolsMCP 2.12.0, but they came from a pre-2.13.0
  main checkout: the parse tools shipped in 2.13.0 (2026-09-25). Many tool defects the
  logs show are fixed since; the stage files and
  [MERGE-NOTES section 4](MERGE-NOTES.md#4-mcp-parsing-tooling-requirements) carry a
  fix status (commit or issue) for each.
- **Not every session is Matthew's practice.** Some local sessions were driven by other
  clients: OpenCode with local models (09-13, 09-14, 09-20), a "hermes_tools" agent
  (09-12) and an unidentified weaker client (09-25). Their evidence is used only as
  failure modes. On the S6-S11 machine the `User request:` field is often agent-filled;
  `(request*)` marks probable but unverified Matthew wording.
- **Where it lands.** Each stage file has a **"Second-Operator Evidence (Swahili)"**
  section, kept separate from Ron's text.
  Language-specific content is in
  [`reference/swahili-morphophonology.md`](reference/swahili-morphophonology.md).
- **No native-speaker verification is recorded** in these logs for the Swahili claims.
  Each carries its own status value.

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
- **`evidence/directive-index.md`** -- every D-/L-/C- id from all shards (plus the T-/V- rows
  of S6-S11), one row each, with where it landed. Use it to audit a claim.
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
| Provenance | **Complete** -- 179 ids (Ron) + 407 (Matthew) indexed, see [`evidence/directive-index.md`](evidence/directive-index.md) |
| Malayalam linguistic content | **Unverified by a native speaker.** Hypotheses only |
| Parse-and-repair stage (11) | Written as it **should** work with in-MCP tooling, before that tooling existed; Ron's corpus (09-10..15) parsed out of band. The tools now exist: they landed 09-18..09-24 and first shipped in FlexToolsMCP 2.13.0 (2026-09-25). Remaining gaps, each with a status, are in [`MERGE-NOTES.md`](MERGE-NOTES.md) section 4 |
| Matthew's process | **Merged** (shards S1-S11, 407 ids, both machines' logs, S6-S11 checked against Claude Code transcripts). Per-stage "Second-Operator Evidence" sections; conflicts in section 4.9-4.20; remaining gaps in [`MERGE-NOTES.md`](MERGE-NOTES.md) |
| Parse-and-repair with in-MCP tools | **Observed** from 2026-09-23 (S8-S11; tools on main from 2026-09-20): `try_word`, `parse_text` with filing, `parse_diff`, `parse_sandbox`. See [Stage 11](stages/11-parse-and-repair-loop.md) and [`MERGE-NOTES.md`](MERGE-NOTES.md) section 4 |
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

### 4.9 Stage order: features first (S1) vs phonemes first (P1)

- **Ron (P1, D-M1-01):** phonemes first; features deferred; categories and templates
  before affix entries.
- **Matthew (S1):** a different order on a greenfield project:
  1. POS from the catalog;
  2. the whole phonological-feature catalog;
  3. phonemes, each created with its features;
  4. natural classes;
  5. rules -- before any stem existed;
  6. lexicon;
  7. a text;
  8. templates, attached to the already-populated lexicon.
- **Assessment.**
  - P1's *dependency* order still holds: nothing referenced an object that did not
    exist yet.
  - The two differ on *when* features arrive. Importing the catalog first makes
    features cheap, so deferring them buys little.
  - The cost of Matthew's order showed up elsewhere. Rules written before the lexicon
    sat unwired for seven hours and one output change was never tested (C-S1-08).
    Templates attached after population led to slot assignment by gloss keyword
    (C-S1-06).
  - **Keep P1 for rules and templates; allow catalog-first features.**

### 4.10 Grammatical conditioning: inflection classes (Malayalam) vs agreement features (Swahili)

Not a conflict but a **language-type difference**, recorded so neither is read as the
"right" default.

- **Ron** carried lexical conditioning on inflection classes, stem names and variant
  entries (rows 6-9).
- **Matthew** carried noun class as agreement features (BantuSG/BantuPl/BantuMany with
  `NA` fill), unified between stem, class prefix and concord (row 25). He used no
  inflection classes, environments or stem names for it (D-S1-06).
- Matthew did use inflection classes, for verb final-vowel behaviour (row 31).
- **Update (S10, V-S10-02):** by 09-25 the feature system held no `NA` values, so the
  S1 fill-every-feature convention is superseded. Noun class 13 was added under
  BantuPl and class-1a concord got its own senses (S8). Homophonous agreement values
  are modelled as **one sense per class** on the concord entry, not as allomorphs or
  separate entries (D-S8-07).

### 4.11 Lexeme form as the elsewhere case (F1) vs most-restricted form in the lexeme (S1)

- **Ron (F1, L-M3-13):** FLEx orders the lexeme form last, so it must be the elsewhere
  form.
- **Matthew (L-S1-02, B#152 docstring):** after merging separate prefix entries, he
  stored the most restricted form in the lexeme form, with an environment, and the
  default form as an alternate, also with an environment. No elsewhere form remains.
- No parse in the S1 logs tests this.
- **Resolved toward F1 by Matthew himself (2026-09-12, D-S6-04, V-S6-01):** *"the
  'default/everywhere' form of the affix should be the lexeme. Many of these are swapped."*
  Twenty entries were corrected with a port of FieldWorks' own `SwapAllomorphWithLexeme`,
  with reference counts checked before and after. The 09-24 and 09-25 prefix entries follow
  F1 and parse (V-S9-04, V-S10-04). The S1 arrangement is a superseded error, not a
  convention. **Follow F1. Q-37 closed.**

### 4.12 Paradigm texts (Stage 10) vs real text from the start

- **Ron:** built constructed paradigm texts as the targeted test suite.
- **Matthew:** tested mostly against real text -- Genesis, and the narrative "Sungura
  na Fisi" -- merging Stages 10 and 12, exactly as the merge seam predicted. He built
  one paradigm text, for noun classes (D-S5-08), late.
- **Both are kept.** Paradigm texts cover environments deliberately. Real text exposes
  approval and gloss defects and closed-class gaps that paradigms never reach.
- **Update (S7, S10).**
  - On 09-13 paradigm texts were generated for every template of every inflecting POS
    (16 texts, about 1,100 paragraphs), plus a **"No Parse"** genre that Matthew asked
    for (V-S7-04). "No Parse" holds forms the AI *judged ungrammatical*, not forms the
    parser fails on; Matthew asked and the AI confirmed it. The generated forms were
    AI-made and AI-proofread, and the evening proofreading consulted no parser (Q-42).
  - For grammar-wide changes from 09-25 on, the regression suite is a **corpus
    baseline** instead: the top-frequency parsed words plus every word containing the
    segment being changed, 1,783 words (D-S10-05).
  - Use a paradigm text to cover cells deliberately. Use a corpus baseline as the guard
    before a change that can break words already parsing.

### 4.13 Relax the slot vs separate templates

- **S2 (C-S2-02):** TAM, FV, Subj and concord slots were made optional so that forms
  would parse.
- **S5 (L-S5-02):** obligatoriness moved into separate templates per construction, with
  a cloned required slot (TAM2).
- **Matthew's late practice agrees with Ron's row 24.** Follow the late form (row 29).
- **Explained and defended (S6, S7).**
  - On 09-12 the AI merged the twin Subj/Subj2 and TAM/TAM2 slots. It passed
    `validate_only` and was written. Matthew reverted it a minute later (C-S6-02).
  - The reason is a FLEx fact: `Optional` lives on the **slot object**, not on its use
    in a template. A slot that is optional in one template and required in another must
    be two slot objects (L-S6-04, L-S7-02).
  - The same MSA in two slots is therefore an idiom when the slots never co-occur in one
    template (Obj/Obj2), and a bug when they do (L-S5-01; V-S7-09).
- **Reopened twice on 09-13 (C-S7-02, transcript-checked).**
  - 01:36, at Matthew's direction ("make it so"): Subj2 made required, and `Verb
    inflection` moved from TAM to TAM2 because "TAM must not be made obligatory
    globally" (tenseless relatives such as *asomaye*). A singular-imperative template
    built in the same pass produced a wrong parse in Matthew's next FLEx screenshot, and
    the AI withdrew it.
  - 20:56, in an evening session that ran no parser: TAM2 was made optional so that
    habitual and negative-present forms (husema, sisemi) with no TAM filler would parse
    (V-S7-03). That session also questioned the documented "ANCHOR: RelSuf is
    obligatory" without reading the template Description.
  - Under this section the 20:56 change should have been a separate template. **Open:**
    record which constructions lack a TAM filler and give them their own template (Q-45).

### 4.14 What "correct" means: parses only (Ron) vs approved analyses and glosses (Matthew)

- **Ron's acceptance test:** the parser produces the attested forms.
- **Matthew's test also covers the analysis layer.** Stored analyses are approved or
  rejected with reasons, word glosses are repaired, and text tokens are pointed at
  their analyses (D-S4-02, D-S5-06).
- **His first approval pass is a lesson in what not to do.** It auto-approved one
  analysis per word as a *Human* by fewest morphemes, and was reversed (C-S2-01).
- **This spec adds the approval layer to Stage 11, with a policy:**
  - no heuristic decision is recorded as a human one;
  - genuine ambiguity is never disapproved.
- **Later practice (S7-S10) complicates this.**
  - The heuristic auto-approval came back on 09-13: a curated-prefix segmenter approved
    analyses and left 424 duplicate allomorphs to clean up (C-S7-04).
  - By 09-24 the project held **zero** human-approved analyses (V-S9-01). Analyses
    were filed by the parser only, through `parse_text` with filing. Whether that was a
    deliberate reset for a fresh baseline is not recorded (Q-41).
  - Filing replaces stored parser analyses in bulk. On 09-25 Matthew asked for it
    ("file the parses"). The AI confirmed the project-wide plan 21 seconds after its
    preview without showing him its upper bound (24,259 deletable analyses). The real
    result was 25,127 words filed, 322 analyses deleted and 271 parse errors
    (C-S10-02, corrected by transcript). "Filing NOT authorized" that evening was the
    orchestrating session's prompt to a subagent, not Matthew's words (V-S10-10
    refuted).
  - **Policy, extended:** a whole-corpus filing is a write that needs the operator's
    decision, made on the preview's numbers, not the AI's. File only the wordforms a fix touches (including their
    capitalised variants) unless the operator asks for more.
    *Status 2026-10-09: partial -- filing still needs only `confirmed=true` plus the
    preview's `plan_id`, which an agent can supply itself; the tool does not enforce a
    human gate, so this policy stays a convention (T-73).*

### 4.15 Growing a class inventory (Ron) vs deriving it from an existing field (Matthew)

- **Ron's verb classes grew 3 -> 2 -> 4 -> 5 as the corpus forced them** (section 4.7).
- **Matthew read one binary dimension off the citation form** (`ku`+stem vs
  `ku`+stem+V) and classified 824 verbs in one pass, with anomalies sent to a human
  (D-S5-04).
- **Assessment.**
  - Where the lexicon already encodes the class, derive it.
  - Where it does not, Ron's L-M3-11 lesson still applies: factor the dimensions before
    growing the inventory.

### 4.16 What "unparsed" means: a stored count (S2-S3) vs a live parse

**The most consequential finding of S8-S11.**

- **S1-S5:** Matthew's real-text loop and frequency queue (D-S2-06, D-S3-02) ranked
  wordforms with **zero stored parser analyses**. S2 already suspected those counts were
  stale (C-S2-05), but the logs had no output to confirm it.
- **S8-S11 confirm it from tool output.**
  - 09-23: the top three "unparsed" words (yake, kama, nami) all parse under
    `try_word` (L-S8-01).
  - 09-25: 9 of the top 10 parsed. One whole-corpus refile with **no grammar change**
    cut unparsed from 14,096 to 9,260, so 4,836 wordforms parsed but had no filed
    analyses (L-S10-01).
  - 09-24: of each queue the agent built, many words already parsed and were only
    unfiled -- 5 of 20, then 9 of 10, then 4 of 5 (T-S9-14).
  - 09-30: about four hours of `run_module` work went into a queue whose top ten all
    parse. `try_word` showed that in two minutes (V-S11-02). They were exactly the 09-25
    Stage 1 fixes, never filed because the later stages never ran (V-S11-04).
- **Rule.** A stored zero-analysis count means "not parsed since the parser last
  ran", not "the grammar fails". **Refile, or `try_word` the candidates, before
  triage**, and build the frequency queue from a fresh parse run. This is Ron's
  acceptance test (live parser output) applied to Matthew's real-text queue: evidence
  for both, a conflict with neither. See [Stage 11](stages/11-parse-and-repair-loop.md)
  and [Stage 12](stages/12-real-corpus-stress-test.md).
  *Status 2026-10-09: partial -- for a live count, run `flextools_parse_text` over all
  texts and read `NumZeroParses`; its scope is occurrence-ordered. The shipped
  `parser-coverage` recipe still reads stored `ParserCount`, so it inherits the
  staleness. No token-weighted figure exists (T-24).*

### 4.17 Verb extensions: inflectional slots (S1) -> derivation (S7) -> lexicalized stems (S7, S10)

- **S1 (C-S1-06):** the extensions sat in inflectional template slots. **S2-S5:** some
  extended forms were stored as stems (Q-40).
- **S7 (V-S7-01), 09-13 12:05:**
  - the design was Matthew's (01:44-01:49): intransitive as a subcategory,
    subcategories inherit the parent's morphology, derivational affixes move words
    between categories (S6 transcript);
  - all six extensions became `MoDerivAffMsa` with From/To POS;
  - Verb gained Transitive/Intransitive/Detransitive subcategories, and 647 verb MSAs
    were reclassified in five batches against a baseline. The 508/139 transitive/
    intransitive split came from AI agents reading glosses, with no human review;
  - every step was checked with in-process HermitCrab: the 1,054-form check gave 1,020
    unchanged, 34 lost, 0 gained (S7 transcript);
  - the empty extension slots were removed from every verb template;
  - RDP became derivational.

  This is P10 (derivation is not inflection), matching Ron's 4.6.
- **Relapses.**
  - *zalia* and *zaliwa* were stored as stem allomorphs of *zaa* 3.5 hours later
    (C-S7-06).
  - On 09-25 they became separate stems (C-S10-03), although passive `-ew-` and stative
    `-k-` already parsed as affixes (V-S10-05).
  - The verbs that still fail on 09-30 (walifanywa, amekikalia, wanaojiwekea ...) all
    carry extensions (S11).
- **Rule.** Follow S7. Lexicalizing a derived stem to make one word parse is a fix
  against P10. It needs a recorded reason (genuinely idiosyncratic meaning), not "it
  parses now". Q-40 is answered *yes* for the model and stays open for the extension
  allomorphy that drives the relapses; lexicalized derived stems are Q-46.

### 4.18 Blocking a rule: lexical exception feature vs morphological conditioning

- **S9 (L-S9-06, V-S9-07):** the S1 glide rule `i -> y` glided class-4 `mi-`, so
  *miaka* (214 tokens) failed. Its second right-hand side has a word-boundary left
  context and no POS limit, but the transcript shows that narrowing either RHS did not
  fix *miaka*; only removing the whole rule did, and why was never found. Disabling the
  rule never persisted (C-S9-02).
- **S9 sandbox regression (session D, transcript):** with the rule disabled, 2,139
  glide-relevant words went from 1,517 to 1,568 parsed -- 54 fixed, 3 broken (vyombo,
  vyanzo: subject `vi-2` has no `vy` allomorph, unlike `vi-1`). The dependency count
  made earlier that day had missed that affix homograph.
- **S10 (L-S10-02):**
  - Fix: an excluded exception feature "no glide formation" on both RHSs, set on three
    stems (*aka, *ea, *anzo).
  - Before the change the blast radius was measured (ny 572, vy 383, py 11 and my 8
    parsed words depend on the rule).
  - After it, miaka parses and the counted dependents still do -- but only a spot check
    was run ("I only spot-checked; I didn't reparse the whole corpus"), although the
    previous night's regression-tested alternative was on record (C-S10-08).
  - The feature sits on stems because HermitCrab treats an exception feature on an
    affix's from-side as a requirement (L-S10-07, from reading the source, not
    tested).
- **Assessment.** The measurement is exemplary (Stage 08). The mechanism is debatable.
  The conditioning is morphological (the cl.4 prefix), so the restriction arguably
  belongs on the prefix or in the rule's required/excluded morpheme set, not on each
  stem, which has to be remembered for every new cl.3/4 vowel-initial stem. **Open: Q-44**; eight CV verb roots (*jua* -> *jwa*) still mis-glide (Q-50);
  see [Stage 08](stages/08-phonological-rules.md).
- **Tooling status (2026-10-09).** The S9/S10 work had no wrappers; most now exist.
  - Disabling a rule: `project.PhonRules.SetDisabled(rule, True)`, fixed in flexicon
    4.12.0 (flexicon#572). The S9 non-persistence (C-S9-02) was never diagnosed, so
    still verify a disable by reopening.
  - Tagging stems with an exception feature: `project.MSA.AddExceptionFeature(msa,
    feat)`, fixed in flexicon 4.12.0 (flexicon#574).
  - Creating the exception feature (`InflectionFeatures.ExceptionFeatureCreate`,
    flexicon#631) and putting it on an affix MSA (`side="from"|"to"`, flexicon#630):
    fixed on flexicon main, not yet released (after 4.12.0). In 4.12.0 the affix-MSA
    calls silently do nothing. The prefix-side option this section argues for needs
    that release.
  - Writing rule features (required/excluded on an RHS, or creating one): still open.
    flexicon 4.12.0 can only read them (`PhonRules.GetRequiredRuleFeatures` /
    `GetExcludedRuleFeatures`), so that step is still raw LCM.

### 4.19 Suppressing objects from the parser: `DoNotUseForParsing` (S4-S8) vs current guidance

- **S4 (D-S4-08)** used the flag as the soft-delete step of disable-then-delete. **S7**
  used it to suppress the class-16 null prefix (V-S7-02), a duplicate quantifier stem
  and about 20 shadow possessives. **S8 (D-S8-12)** used it to keep 12 whole-word
  possessives *listed but not parsed*; its own module marks the effect "UNVERIFIED".
- **Two jobs on one flag** (soft delete; listed-but-not-parsed), and **it changes
  nothing.** On 09-20 Matthew doubted it ("I'm not sure exclude-from-parsing has an
  effect ... in the UI, only isAbstract is surfaced") and the agent retracted its claim
  (D-S8-12). On 09-25 a source investigation settled it: HermitCrab's loader and
  XAmple's transforms filter only on `IsAbstract`, per form (S10 transcript). Matthew
  ruled "treat it as deprecated" and filed LT-22810 (D-S10-14). So the class-16
  "suppression" (V-S7-02) and every S4-S8 suppression were no-ops. The 4 flags set on
  09-20 were never reverted.
- **`DoNotUseForParsing` is deprecated and refused.** Since FlexToolsMCP 2.13.0,
  `run_module` rejects it at preflight (`deprecated_member`) in read and write runs.
  Do not
  use it, either as a soft-delete step (D-S4-08) or to keep an entry listed but not
  parsed (D-S8-12).
- **Use `IsAbstract` instead:** set it on the lexeme form and on every allomorph. Migrate
  the flagged entries (33 by 09-20) and prove each change with a `parse_diff`. This
  answers Q-43 for the mechanism; the migration is still to do.

### 4.20 Blanket mandates ("use your deep knowledge") vs P3/P6 one-variable proof

- **Ron (P3, P6):** cheapest change first, one variable at a time, prove a recipe on one
  item before scaling.
- **Matthew's S4/S5 practice agreed** (manifests, dry runs, tiers, a one-variable
  reparse experiment, D-S4-09).
- **S8-S11 show what happens without it:**
  - seven 808-row gloss writes with no `validate_only` and FLEx open; the last failed with
    a conflicting-save error (C-S8-02); *Status 2026-10-09: partial -- the conflict
    now fails loudly (`FP_ConflictingSaveError`, flexicon 4.6.0), and schema changes
    are refused while FLEx holds the project (FlexToolsMCP 2.15.0). Value writes are not
    gated, so close FLEx for bulk writes.*
  - a 12-change operation under "resolve ... using your deep knowledge of Swahili" that
    failed half-way and could not be attributed per change (C-S9-04);
  - entries guessed as monomorphemic, and syllables entered as morphemes (C-S11-04,
    C-S11-05). On 09-30 an unidentified client (not Claude Code) invented morpheme
    splits that the parse tools never returned. Its write run crashed, but **9 bare
    entries were committed anyway** (malaka, el, kumu, gizo, is, hara, en, ghadha, bu),
    because the runner saves the project in `finally` (C-S11-08, T-S11-10; still open).
    A recipe modelled on that run (`ensure-morpheme-entries`, PR #337) needs review.
- **Also in tension with H6 / Q-42:** entries and glosses the AI writes on such a
  mandate are not marked as AI-sourced in the project.
- **Rule.** A broad mandate authorizes the *goal*, not batching. Keep one change per
  operation, each re-tested with `try_word` before the next. Mark AI-sourced lexical
  content; the forms awaiting a speaker are Q-47. See [guardrails](conventions/ai-collaboration-guardrails.md).

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
  - [swahili-morphophonology.md](reference/swahili-morphophonology.md) (second operator)
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
