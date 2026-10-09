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
11. **An invariant category must also inherit no template** (L-S9-01, L-S9-03). A
    subcategory inherits its parent's templates, so a template-less subcategory under a
    parent with obligatory slots still fails on its free words. In the Swahili project,
    moving Pronoun out from under Pro-form fixed 3 words and broke none (`parse_diff`).
    The diagnosis started from Matthew's hypothesis that words "found whole" in the
    dictionary don't get parsed (D-S9-07), and he chose the move ("option 1, make it so")
    over making the PossConcord slot optional (C-S9-06). The step 7 rule reads: owns
    zero templates **and inherits none**.

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
- No inflectional affix sense belongs to no slot. An unslotted inflectional MSA is not
  inert: the parser tries it in every position. The agent had called such senses
  "inert"; Matthew corrected it mid-turn: "unconstrained affixes can apply "anywhere"
  and create parser slowdowns" (D-S8-08). Run the audit at the end of every write that
  adds affix senses (14 found in one dry run, all created by that session).
  *Status 2026-10-09: still open as a lint (T-74) -- not in `grammar_health`; the curated
  recipe `audit-repair-infl-aff-msa-slots` shows each MSA's slot list but flags only
  duplicate slots, so check for empty lists yourself.*
- Once texts parse, whole-word stems parse at similar rates across POS. A POS with a
  much lower rate points at its template (own or inherited), not at the lexicon
  (S9 13:43: Noun 274 parsed / 165 not, Numeral 3 / 17; L-S9-01).

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
  (C-M6-02). *Status 2026-10-09: partial -- `POS.Find` recurses; variant `FindType`
  recurses one level only.*
- **Polymorphic casting rejections** when walking templates and slots (C-M8-02,
  C-M8-03: `StemNameRA` does not exist on an affix template; C-M6-04). C-M8-03 was a
  misuse, not a gap: the stem name lives on the stem allomorph. Read and set it with
  `project.Allomorphs.GetStemName/SetStemName`, and list a POS's stem names with
  `project.POS.GetStemNames`. Walk templates through the `AffixTemplate` / `AffixSlot`
  wrappers (`affix-templates-and-slots` recipe) instead of casting.
  *Status 2026-10-09: stem-name wrappers shipped in flexicon 4.12.0 (flexicon#580);
  `GetAllAffixTemplates` items are unwrapped by the resolvers since flexicon 4.10.0
  (#449; use `item.lcm_object` for a direct cast; related #561).*
- **Not noticing a human restructured the tree** (D-M5-02).
- **Treating validate_only as a grammar check.** It proves a write is mechanically
  sound, not that it is grammatically right: a slot merge passed validation, was
  written, and was reverted at the operator's request a minute later (C-S6-02, T-S6-09).
  Matthew's objection was typed while the write was running, so the AI saw it only after
  the write had landed (D-S6-08): a queued objection does not stop an in-flight write. Pair
  template and optionality edits with an over-generation check or explicit sign-off.
  *Status 2026-10-09: by design -- `validate_only` is a static preflight and never runs
  the script. An over-generation probe is still open (T-22); `flextools_parse_diff`'s
  `changed` bucket shows loosening on attested words only.*

## Automation Notes

**Automatable now:** catalog-sourced category creation, template/slot creation with
explicit ordering, build-by-analogy (clone an existing template's shape), and all the
QC assertions.

**Human required for:** slot inventory, order, optionality, and the
inflection/derivation call.

**Missing tooling (requirements):**
- `clone_template(from_pos, to_pos)` -- mechanize D-M8-03's build-by-analogy.
  *Status 2026-10-09: partial (T-29) -- `MorphRules.Duplicate(template, deep=True)`
  copies a template within its own POS; cloning to another POS is still manual. New
  templates and slots have wrappers since flexicon 4.10.0 (`POS.CreateAffixSlot`,
  `MorphRules.CreateAffixTemplate`, `MorphRules.AddSlotToTemplate`; recipe
  `affix-template-setup`).*
- **An inflection/derivation lint**: warn when an affix entry attached to an
  inflectional slot has an MSA whose from-POS and to-POS differ, or when a
  derivational-looking gloss is slotted. This is C-M6-03 as a guardrail.
  *Status 2026-10-09: open.*
- A morphotactics report: per POS, the slot order, optionality, and fillers, in one
  view -- the corpus hand-wrote this repeatedly.
  *Status 2026-10-09: shipped as the `affix-templates-and-slots` recipe (slots,
  optionality, fillers and their environments per POS); no slot-usage counts (T-46,
  open).*
- Shared-slot impact report: "this slot is shared by these N categories".
  *Status 2026-10-09: open.*
- A category-name registry so creation and consumption cannot diverge (C-M5-01).
  *Status 2026-10-09: open (T-40) -- resolve categories by GUID or catalog id, not by
  display name.*

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 come from one machine's logs (2026-05-21..09-11) and S6-S11 from the other's (09-12..09-30), which ran a pre-2.13.0 FlexToolsMCP main checkout. Those logs keep little or no tool output, so S6-S11 were re-checked (2026-10-09) against the Claude Code transcripts behind them, which hold the parse results, real counts and Matthew's verbatim words (mid-turn messages included) that the logs lost; tooling defects carry their current fix status. Sessions run by other clients (local models, a non-Claude agent, an unidentified non-Claude client on 09-30) count only as failure-mode evidence. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

- **POS first, from the catalog, idempotently** (D-S1-01) -- CONFIRMS the catalog rule.
  **ADDS:** check every catalog id exists *before* the loop (`GOLD:Conjunction` did not,
  and killed a half-run).
- **ADDS: noun class as agreement features**
  ([row 25](../reference/flex-modeling-decisions.md); D-S1-06, D-S3-01, D-S4-05).
  - Three closed inflection features hold the class: singular class, plural class, and
    a third for classes without a singular/plural pair.
  - A stem's grammatical info (MSA) carries its singular class and its paired plural
    class. Class prefixes carry matching values and sit in an obligatory ClassPrefix
    slot.
  - Every unused feature is filled with `NA`, so values unify exactly.
  - The features were later moved to catalog-sourced ones (`fBantuSg/Pl/Many`) and
    nested under the `noun agreement` complex feature. Count the specs that point at
    each feature before migrating.
  - Run a recovery pass afterwards: one refactor dropped `NA` fillers (C-S3-02).
- **ADDS: one template per construction that cannot co-occur; clone a slot when its
  optionality must differ** ([row 29](../reference/flex-modeling-decisions.md); L-S5-02).
  - Whether a slot is optional is set on the slot itself, so every template that uses
    the slot shares the setting.
  - To make TAM required only in the template with an object marker, a required copy
    (TAM2) was cloned and swapped in.
  - The subjunctive got its own template with a required FVsubj (-e) slot and no TAM
    slot.
  - This is the right replacement for the earlier practice of making shared slots
    optional so words would parse (C-S2-02; [README 4.13](../README.md)).
  - *Status 2026-10-09: slot cloning is still manual (T-57, open); `POS.Duplicate` does
    not copy slots.*
- **ADDS: one affix in several slots only if those slots never co-occur**
  ([row 30](../reference/flex-modeling-decisions.md); L-S5-01). An `m-` assigned to both
  Subj and Obj licensed a two-subject parse (D-S5-01).
- **ADDS: build a new concord series by cloning an existing one** (D-S4-06).
  PossConcord and NumConcord were built by deep-copying each ConnConcord feature
  structure. Attach each new structure to its owner *before* filling it.
  *Status 2026-10-09: partial (T-58) -- read with `MSA.GetFeatures` and rebuild with
  `MakeFeatStruc` (which can attach to an MSA); there is no one-call deep copy or
  migrate helper.*
- **ADDS a lint: a bound stem whose POS has no slots cannot parse** (L-S4-04).
  *Status 2026-10-09: open (T-52) -- only the `publication-readiness-check` recipe
  exists; no per-POS parse-ready lint.*
- **CONFIRMS G4 by repeating Ron's mistake** (C-S1-06). Verb extensions went into
  inflectional slots, and affixes were assigned to slots by matching keywords in their
  glosses. Both are wrong, for the reasons in [row 16](../reference/flex-modeling-decisions.md).
- **ADDS a failure mode: validate_only passed, then the live run broke partway**
  (C-S4-02). Slot, template and sense creation was left half-done in a non-undoable
  session. Always follow a structural write with a "what did it actually leave behind"
  read.
  *Status 2026-10-09: the non-undoable session is gone -- since flexicon 4.4.0 and
  FlexToolsMCP 2.13.0 each flexicon operation rolls back on failure, and
  `with project.UndoableOperation(...)` makes a whole script atomic. Slot and template
  creation have wrappers (flexicon 4.10.0). The read-back is still good practice.*

*S6-S11 additions:*

- **CONFIRMS row 29 / L-S5-02, now with Matthew's rationale** (D-S6-08, L-S6-04,
  V-S6-02, L-S7-02). *"the duplication is to allow subject with or without object, but
  not a bare object."* The AI had merged Subj2/TAM2 into Subj/TAM in all four verb
  templates after validate_only passed; Matthew had it reverted a minute later
  (C-S6-02). The cleaner form of the idiom is one MSA in two slots, as TAM/TAM2 and
  FV/FVsubj already were; Subj/Subj2 used two MSAs and 14 duplicate senses (L-S6-04).
  It was reused for a second object slot (Obj2). It was changed twice the next day by
  sessions that did not read the design record. At 01:36 Subj2 was made required in
  answer to Matthew's "make it so" and "do we need more templates for non-finite
  verbs?", and checked by his FLEx parse within minutes. At 20:56 a session that ran
  no parse made TAM2 optional for habitual hu- and negative-present forms (C-S7-02,
  V-S7-03). Template edits move coverage: once `Verb inflection` required TAM2,
  subjunctives without an object marker lost their only template, and a `Verb
  subjunctive` template was built at 01:42 (L-S7-18). Whether TAM2-optional should have
  been a separate template is open ([README 4.13](../README.md)).
- **ADDS: the template Description is the design record** (D-S6-09, D-S7-02, C-S7-01,
  C-S7-02).
  - Write the reasons into the project, with fixed headings: ANCHOR, REASONING,
    DELIBERATELY NOT BUILT, KNOWN GAP, VERIFY-WITH.
  - Read it before editing a template. Merge into it; never overwrite it. One agent's
    `SetDescription` replaced text an earlier agent had written; the same agent then
    restored it verbatim and appended its own (C-S7-01; the agents ran one after
    another, not in parallel).
- **ADDS: every template needs an anchor** (D-S6-13, L-S6-07, L-S7-03, L-S7-04). The
  principle is Matthew's: *"we should seek to avoid having a template with all
  optionals."* The all-optional finite template licensed 376 of 569 verb analyses
  (66%), including 112 verb readings of words that also had a non-verb analysis (*moja*,
  *kila*). If all slots are optional, or the only anchor is a null morpheme, the
  template matches every stem, because HermitCrab inserts null morphemes freely. Anchor
  with an obligatory overt slot or with a bound-stem morph type (L-S6-08: bound vs free
  morph type, not the slot flag, decided which concord stems parsed bare). A write
  agent declined the singular imperative for lack of an anchor; at Matthew's question
  another session built it the same night, his parse showed its optional object slot
  produced a wrong reading, and that slot was removed within minutes. Whether it needs
  a different anchor is unresolved.
- **ADDS a lint: a template's filler MSAs must have the template's POS or an ancestor**
  (L-S7-04). A Quantifier template was inert because its fillers' POS was Connective.
- **ADDS: build templates per construction, and make each parse its own examples**
  (D-S6-10, C-S6-03, D-S6-03). *"Usually the templates are derived grammatically. For
  example, an infinitive will likely have no subject or object."* The data behind it:
  `ku-3` 'subject (cl.15)' had 39 uses against 3 for the real infinitive `ku-1`, and 20
  of 52 `ku-` wordforms were unparsed; an infinitive template was built 09-13 00:16.
  A new relative template licensed 0 analyses because it was not built as approved:
  Matthew picked a preview reading `TAM Obj(opt)`, and the AI built it with TAM2 and a
  required Obj. It shipped with the gap written in its description and was fixed the
  next night with an optional Obj2 slot. Build exactly the approved preview, and treat a
  known gap as an open task, not as documentation.
- **ADDS: unblock a category by changing the tree, not by relaxing slots** (L-S9-01,
  L-S9-02, L-S9-03, V-S9-06, D-S9-07). On 09-24 three tree edits unblocked about 3,000
  tokens with no new entries, each parse-verified before filing and each approved by
  Matthew separately: Pronoun moved to the top level (his choice over relaxing the
  slot, step 11); `*amba` moved to a new
  Verb > Relativizer with a RelSuf-only template; 14 invariant Arabic-origin numerals
  moved to a template-less top-level POS. Unparsed wordforms went 14,038 -> 14,006.
  Extends [row 23](../reference/flex-modeling-decisions.md) (see step 11).
- **REVISES C-S1-06 and V-S6-03: verb extensions are now derivational** (V-S7-01,
  L-S7-05, D-S7-05, D-S7-06, D-S7-11, D-S7-12, D-S7-14). On 09-13 the six extensions
  became derivational MSAs between POS subcategories (Verb > Underived > {Transitive,
  Intransitive}; Verb > Detransitive). All 647 verb stems were classified, the empty
  extension slots were removed, and reduplication became derivational. Ordering comes
  from subsumption alone (no strata, no ProdRestrict; L-S7-10). The architecture is
  Matthew's (01:44-01:49): *"intransitive verbs can be a subcategory and have their own
  constraints"*, *"once a subcategory's template is satisfied, it can take morphology
  from the parent"*, *"derivational affixes can make words jump categories"*. The tree
  details, the asymmetric default and the classification were the AI's. The rollout was
  staged, and every step was checked with in-process HermitCrab parses (quoted in the
  transcript, lost from the logs):
  1. experiments on throwaway objects: inheritance holds; From-category is enforced
     during parsing and is subsumption-aware (From=ZZTest/Noun/Verb gave 4/3/4
     analyses); a two-level check passed;
  2. a prototype: *kuwa* lost its spurious passive reading (3 -> 2), but converting one
     extension alone silently cost the passives of all 605 unmarked verbs and inverted
     extension order (all 8 ordering pairs flipped). Matthew chose "Revert W3, keep
     W1+W2" and "Stop here, write up findings" (D-S7-11); the revert matched baseline on
     all 30 checks;
  3. after his "make a plan and resolve it fully": classification outside FLEx,
     defaulting to Transitive and marking Intransitive only on positive evidence
     (wrongly marking a verb intransitive costs more). 43 verbs came from (tr)/(intr)
     gloss tags, 604 from LLM batches, and an adversarial reviewer overturned 19 of 158
     Intransitive calls: 508 vt / 139 vi, with no human review (D-S7-12);
  4. batched repointing against a 24-form parse baseline (29 analyses before and
     after);
  5. an atomic conversion checked with a 30-form probe and a 1,054-form before/after:
     1,020 unchanged, 34 lost readings, 0 gained. 26 of the 34 were *-kuwa* forms
     losing only the spurious reading; *zamani* and *zikakamilika* lost one because
     their roots were classed vi.

  Still open: recip+pass (*kuvunjanewa*) and pass+stat (*kuvunjewika*) no longer parse,
  put to Matthew and unanswered; caus/appl order is unconstrained (L-S7-11). The
  throwaway nonces corrupted two real roots (C-S7-03): `LexEntry.Find` matched *kuoza*
  and *kuuza* fuzzily, and `CreateDerivAff` deleted their old MSAs; they were restored
  from FLEx's own `.bak` with new GUIDs. Never find-or-create a throwaway object by
  form; collect the existing forms first. Relapses at the lexicon level are in
  [Stage 06](06-stem-and-affix-population.md). See Q-40.
- **REVISES the `NA` filler above** (D-S1-06, C-S3-02 -> V-S10-02). By 09-25 the
  agreement features had no `NA` value, and each null class prefix carried a single
  value, so 9/10 nouns get two analyses by construction (09-30 traces confirm: every
  9/10 noun gets a null-nc9 and a null-nc10 reading, L-S11-04). See Q-38.
- **ADDS: one sense per agreement value** (D-S8-07, L-S8-03). FLEx gives a sense one
  feature structure, so a concord homophonous across three classes needs three senses.
  A gloss `conn.conc.nc4/6/9` sat on features for class 4 only, and the other classes
  silently failed to unify. The rule is Matthew's (*"For the y affix you may need to add
  it with multiple senses"*), and a lex-domain consult confirmed it. Lint: a gloss
  naming N values needs N senses. Rename the old sense before adding, or re-runs
  duplicate it. Do not credit the split with fixing *yake*: its zero count was stale,
  and on 09-23 it parsed through a class-4 sense that predates the split (C-S8-07).
- **ADDS: featureless concord series can be a convention, not a gap** (D-S8-15). A
  census showed every connective, pronominal and demonstrative concord carries features
  (16/16, 16/16, 13/13) and no adjectival, numeral, relative or subject concord does
  (0/12, 0/12, 0/21, 0/12). That overruled a "partial rollout" reading, and 40+ inert
  senses were not added.
- **ADDS: exact-value unification and legacy values** (D-S8-11, D-S8-10, D-S8-09,
  V-S8-03). 40 nouns tagged class 1a were judged to fail against a class-1 concord, so
  1a concord senses were added. Caveat: the concord sits on a separate word (*wake*),
  and HermitCrab parses one word at a time, so this failure is probably not a parser
  effect; check with a parse before relying on it. Census each value's users before
  adding an affix keyed to it. To fix a misfiled value, add the correct one alongside
  the old instead of migrating: class 13 went under both plural and singular features
  on Matthew's instruction (*"add 13 as an option for plural without removing it from
  singualr"*). Reasoned in the module, not parse-tested.
- **ADDS (unverified): affix inflection features unify; they do not overwrite**
  (L-S7-01). So a suffix that changes a noun's class (locative -ni) has to be a
  derivational MSA with To-features. Documented, never implemented or parsed.
- **CONFIRMS L-S4-04** (L-S8-04, V-S8-05). 12 of 21 POS had no template on 09-20.
- **ADDS: wastebasket POS review** (D-S6-11, D-S7-04, L-S6-10). On 09-12 *mbali* was
  flagged as a misfiled Particle, and Particle found to be a wastebasket (adverbs,
  interrogatives, copulas, prepositions, frozen forms). Together with the all-optional
  verb template it produced confident nonsense (*kwa* 14 competing analyses; *kila* =
  cl.7-eat). On 09-13 a write agent, under Matthew's "use your knowledge of swahili to
  judge (and fix) with subagents for each part of speech", redistributed it: Particle
  70 -> 33, Adverb 8 -> 20 (*mbali* included), new Interrogative 12, Copula 11,
  Interjection 3.

## Provenance

- M1 ops 5, 10, 15 (2026-09-10 16:16, 19:52, 20:42); D-M1-02, D-M1-03; M1 §5
  "Inflection template + affix entries (per POS)".
- M2 op 5 (2026-09-10 20:30); L-M2-10; M2 §6 (invariant categories own no template).
- M5 ops 9-10, 24-25, 34, 42-46 (2026-09-13 23:06 .. 09-14 10:50); D-M5-01, D-M5-02,
  D-M5-07, D-M5-08; C-M5-01; M5 §5 stages 2 and 6.
- M6 ops 17-18, 25 (2026-09-14 16:26-16:39); **C-M6-03**, L-M6-03, L-M6-06.
- M7 op 8-9 (2026-09-15 08:18) -- augment built as a Number-slot affix; L-M7-01.
- M8 ops 2, 4-6 (2026-09-15 14:04-14:09); D-M8-03, D-M8-04; L-M8-02; C-M8-03.
- S9 09-24 133553 13:43-14:30 (L-S9-01, L-S9-03) -- step 11 and the stem-parse-rate QC item; S8 09-20 161814 #44-45 (D-S8-08) -- unslotted-affix QC item; S6 09-12 215450 #40-44 (C-S6-02) -- validate_only failure mode.
- **Merge seam:** Merged from S1-S11 (both machines) -- see Second-Operator Evidence above. Matthew used no shared parent-category slots; he used POS subcategories for template inheritance (relativizer) and for derivational From/To categories (verb valency). Open: singular imperative; TAM2 optionality vs a separate template.
  *(Original seam: Matthew's category inventory and slot conventions; in particular whether he uses shared parent-category slots at all.)*

## Open Questions

- The corpus never states a rule for *when* to introduce a shared parent category
  (Nominal) versus duplicating slots per child. Q-09. Swahili evidence on the cost side:
  inherited templates blocked free words in a subcategory (L-S9-01).
- Whether a Noun+Verb compound rule was ever actually created, and why the expected
  compound did not fire (M6 §7). Q-10.
