# Malayalam Morphophonology -- The Analysis This Project Arrived At

[Back to README](../README.md)

## Read this first

**This is not a description of Malayalam. It is a record of the analysis one project
arrived at, and how it got there.**

- **Ron does not speak Malayalam.** He is an expert computational linguist working from
  analytic intuition, reference materials, and what made the parser behave.
- Every claim below is either a hypothesis Ron asserted and steered, or one the AI
  proposed and Ron accepted because it produced correct parses.
- **None of it has been verified by a native speaker.**
- A claim "worked" here means "the grammar parsed the intended forms with it". That is
  evidence, but it is weak evidence about the language: several distinct analyses can
  produce the same surface forms.

Each item carries a **status**:

| Status | Meaning |
|---|---|
| `asserted-by-Ron` | Ron stated it as the analysis to implement |
| `AI-proposed-accepted` | the AI proposed it; Ron accepted it implicitly or explicitly by proceeding |
| `unresolved` | raised, never settled in the corpus |
| `revised` | superseded by a later analysis in the corpus |

Forms are given as the shards give them: transliterated, schematic, or by abbreviation.
The logs did not persist most surface strings (M6 §6, M2 §7), so specific forms are
sparse by necessity, not by choice.

---

## 1. Inventory and script-level assumptions

| Id | Claim | Status |
|---|---|---|
| L-M1-06 | The primary partition of the 68-grapheme inventory is a consonantal feature: 44 graphemes consonantal-positive (consonants, chillus, anusvara, visarga), 24 negative (vowels, vowel signs/matras, **and the virama itself**). The virama patterns with the non-consonantal segments. | `asserted-by-Ron` -- the feature was restored specifically because Ron considered it load-bearing |
| L-M2-06 | The virama and the anusvara are definable as **feature-based** natural classes rather than segment lists: virama as `[-cons -son]`, anusvara as `[+cons -syl +lab]`. | `AI-proposed-accepted` |
| L-M4-05 | **Every suffix in this project is stored in its post-consonantal shape**, so a suffix always opens with a dependent vowel *sign* (matra), never an independent vowel letter. Using the independent letter produced a visibly wrong surface form. | `asserted-by-Ron` |
| M4 §6 | Verb stems are stored "with their inherent -a and no final virama", so plain concatenation with a post-consonantal suffix reproduces the correct surface form. | `AI-proposed-accepted` (a storage convention, not a claim about the language) |

Three decomposable matra phonemes were deleted from the inventory as redundant with
their components (M1 op 4). Whether that decomposition is the right analysis is not
argued anywhere.

---

## 2. Phonological rules (general alternations)

These are the alternations the project chose to state as **global rules** rather than
stored allomorphs.

### 2.1 Chillu vocalization

- **Claim.** A chillu (a bare, virama-less final consonant letter) surfaces with its
  inherent vowel when a morpheme boundary is immediately followed by a syllabic
  segment. Stated for two chillu subclasses (coronal, velar).
- **Environment.** input = chillu class; output = syllabic; right context = a boundary
  followed by a vowel. Later widened to fire across the clitic boundary as well as the
  word-internal one (L-M2-07).
- **Evidence.** *"A coronal chillu takes its inherent vowel before a following
  morpheme: MAKAN + E -> makana + e."* (L-M1-01, 2026-09-11 11:37)
- **Status.** `AI-proposed-accepted`.

### 2.2 Virama deletion before a vowel

- **Claim.** A virama cannot stand immediately before a vowel sign; it deletes.
- **Environment.** input = virama; no output (deletion); right context = boundary +
  vowel class. Also widened to the clitic boundary (L-M2-07).
- **Evidence.** *"A virama cannot stand before a vowel sign; the vowel sign itself
  cancels the inherent vowel."* (L-M1-02)
- **Status.** `AI-proposed-accepted`. Note this is at least partly an **orthographic**
  statement, not a phonological one -- the corpus does not distinguish the two levels.

### 2.3 Enunciative /u/

- **Claim.** A word-final virama surfaces as an epenthetic "enunciative" vowel /u/
  when another morpheme follows across a boundary.
- **Environment.** input = virama; output = u-matra; right context = boundary.
- **Evidence.** L-M1-03, rule named "Enunciative u".
- **Status.** `AI-proposed-accepted`.

### 2.4 Anusvara before a vowel

- **Claim.** An anusvara alternates with a labial-nasal + inherent-vowel sequence
  before a boundary followed by a vowel.
- **Environment.** input = anusvara; output = the labial-nasal syllable; right context
  = word-internal boundary + vowel class.
- **Refinement.** For two anusvara-final proper nouns, the change is scoped more
  narrowly -- gated by a dedicated "Plain anusvara" inflection class and a rule
  feature, with the unrestricted subrule using **four exact per-segment environments**
  rather than a natural class, because the four matras proved indistinguishable by
  feature structure (L-M7-03).
- **Status.** `AI-proposed-accepted`; the proper-noun scoping is `asserted-by-Ron`.

### 2.5 Architectural notes about the rules

- All rule right-hand sides must be **boundary-anchored**. An unanchored bare-natural-
  class right context caused parse-time explosion (L-M3-02). This is a **parser fact,
  not a language fact**.
- Whether phonological rules apply across clitics is a **FLEx application setting**
  outside the data (D-M3-03).

---

## 3. Nominal morphology

### 3.1 Case inventory

Seven case forms per nominal, in a fixed order used consistently across the noun,
demonstrative and pronoun paradigm texts: NOM, ACC, DAT, SOC, INS, GEN, LOC (L-M5-02).
`AI-proposed-accepted`.

The Case slot is owned by a parent "Nominal" category and **shared** by Noun,
Demonstrative, Pronoun, Interrogative pronoun and (later) Numeral -- a claim that these
categories decline identically (M5 op 34, M8 §9). The category restructuring that made
this so was done by Ron himself in the FLEx GUI (D-M5-02).

### 3.2 Case-suffix allomorphy

Conditioned by the stem-final segment class. Recorded as ordered affix-process
subrules, each stating its trigger class, whether the trigger segment is **kept or
replaced**, and the inserted string (L-M2-01..L-M2-05). See
[`allomorphy-environments.md`](allomorphy-environments.md) for the table.

Two points of method rather than of Malayalam:
- Whether the trigger segment is kept or replaced must be decided **per subrule and
  tested against a concrete surface form** -- the genitive's virama subrule was
  initially "keep" and had to be corrected to "replace" (C-M2-05, L-M2-03).
- A suffix's elsewhere form can over-generate and may itself need an environment
  (L-M3-14).

Status of the whole case-allomorphy analysis: `AI-proposed-accepted`, with the genitive
correction `revised`.

### 3.3 Oblique stems

Nouns form an oblique stem before case suffixes. The corpus modeled this **three
different ways** over six days and never fully reconciled them:

1. **Oblique allomorphs** on the head entry, conditioned by a post-augment case-onset
   environment (L-M6-01).
2. **Oblique variant entries** linked to the head via a variant type nested under
   "Irregularly Inflected Form" (L-M6-01, D-M5-03).
3. **An oblique augment as an inflectional affix** in the Number slot, with
   affix-process allomorphs that strip the anusvara -- this replaced 92 variant
   entries (L-M7-01).

Some entries carried both (1) and (2) simultaneously; the duplication was counted and
not resolved (L-M6-01). An experiment converting two `-vu` nouns from (2) to (1) was
run and then fully reverted with no stated reason (L-M7-04, D-M7-07).

**Status: `unresolved`.** See [open-questions.md](../open-questions.md) Q-04.

Specific oblique patterns recorded:

| Claim | Status |
|---|---|
| Virama-final stems ending in the -am shape take an oblique in -att, plus a further oblique in -attin; other consonant-final stems take an -in oblique (L-M2-08) | `AI-proposed-accepted` |
| Nouns add an **-in- augment** before certain case markers, and the augmented stem is itself ambiguous with a full dative reading (L-M3-07) | `AI-proposed-accepted` |
| Anusvara-final nouns take an oblique augment (three augment shapes: bare, dative-conditioned, chillu-final) (L-M7-01) | `asserted-by-Ron` |
| Pronoun and demonstrative obliques take the same augment but as pronouns, outside the Noun template's scope, so they keep variant-entry modeling (L-M7-05) | `asserted-by-Ron` |
| `-vu`-final nouns split: two of four reject naive concatenative case forms (L-M7-04) | `unresolved` |

### 3.4 Number

- A plural allomorph is restricted to a **"Human" inflection class** of human-denoting
  nouns rather than competing freely (L-M1-05, `asserted-by-Ron`). Whether this class
  is actually needed for parsing was investigated in a dedicated read-only session and
  **never answered** (L-M4-06, `unresolved`).
- The plural suffix is implemented as an affix-process rule, not a simple allomorph
  (L-M4-06).
- Plural allomorphy is conditioned by the stem-final class: chillu-n, anusvara, and
  virama each select a different shape, all replacing the trigger (L-M2-01).

### 3.5 Pronouns

| Claim | Status |
|---|---|
| Many pronouns have **suppletive** oblique stems not derivable from the nominative (L-M5-03) | `AI-proposed-accepted` |
| Two forms are **whole-word irregular inflected forms** (a genitive and a dative) filling the Case slot, distinct from suppletive stems (L-M5-04) | `AI-proposed-accepted` |
| Five pronouns have **no attested instrumental**; the cells were deliberately omitted rather than invented (L-M5-02) | `asserted-by-Ron` -- a methodological rule, not a Malayalam claim |
| The original eleven-pronoun set is honorific/formal-register-heavy and under-covers colloquial third-person forms (L-M5-11) | `unresolved` coverage gap |
| Only **three interrogatives decline**; they were split into their own subcategory (D-M5-08) | `asserted-by-Ron` |
| Most indefinite pronouns decompose as base + clitic; **five do not** and were kept as whole-word entries (L-M5-07) | `asserted-by-Ron` -- "the single richest piece of morphological reasoning in the log" |
| Demonstratives decline exactly like nouns (same six case forms, same triggers) but are a separate category (L-M2-10) | `AI-proposed-accepted` |
| Determiners are invariant and own **no** template (L-M2-10) | `AI-proposed-accepted` |

### 3.6 Numerals

| Claim | Status |
|---|---|
| Numerals decline and get a Case template modeled on the demonstrative's (D-M8-04) | `asserted-by-Ron` |
| **Anusvara-final big numerals (thousand, lakh, crore) inflect as nouns, not numerals**, because the augment they need lives in the Noun template's Number slot and is not reachable from a sibling category (L-M8-02) | `AI-proposed-accepted` -- note this is partly a *mechanism* decision, not purely a claim about the language |
| Two cardinals show an n/m alternation before a following consonant, stored as two allomorphs on one entry (L-M8-03) | `AI-proposed-accepted` |

---

## 4. Verbal morphology

### 4.1 Template

- **A bare verb stem is not a word**: every verb form carries exactly one TAM suffix,
  so the TAM slot is **non-optional** (D-M1-02). `asserted-by-Ron`.
- Slot order: root - Causative - Voice - TAM, with Causative and Voice optional and
  inboard of the obligatory TAM slot (D-M1-03). `asserted-by-Ron`.
- Later the TAM position was split into non-past and past suffix slots hosting
  different suffix sets (L-M6-03). `AI-proposed-accepted`, then partly `revised` when
  the nominalizers moved out of the template entirely.

### 4.2 Conjugation classes

Named by their past-stem shape. The inventory grew with corpus coverage:

| Stage | Classes | Evidence |
|---|---|---|
| First | V1/V2/V3, keyed jointly to past shape **and** causative shape | L-M3-10 |
| Collapsed | Two classes ("Past -i", "Past -nnyu") after the causative was split out as its own affix entry, because the two dimensions are **orthogonal** | **L-M3-11** |
| Extended | Plus "Past -ccu" and "Past -ttu" | L-M4-02 |
| Final | Five: "Past -i", "Past -ttu", "Past -nnu", "Past -ccu", "Past -nnyu" | L-M8-01 |

`asserted-by-Ron` throughout. L-M3-11 is the important one and it is a **method**
lesson, not a Malayalam one: factor a class system along its true independent
dimensions before growing it.

Illustrative class members (transliterated as the shard gives them): "Past -ccu"
pathikka -> pathiccu (past stem -icc-); "Past -ttu" etukka -> etuttu (past stem -tt-);
"Past -nnyu" karaya -> kara with ya-deletion; "Past -i" thudanga with no irregular past
stem (L-M4-02, L-M6-02). `asserted-by-Ron`.

### 4.3 Past-stem formation and the over-generation problem

- Past-stem shapes are **not uniformly predictable** from the present stem; they
  cluster into the named classes (L-M6-02). `AI-proposed-accepted`.
- Past-tense suffix (-i / -u) allomorph selection depends **jointly** on the
  phonological environment of the stem-final segment **and** the lexically-assigned
  inflection class (L-M5-09). `asserted-by-Ron` -- resolved only after three
  iterations (shared-class overreach -> dedicated class + literal environment ->
  over-narrow restriction -> widened restriction).
- **Class D's past stem ends in a geminate that is also a legitimate non-past stem
  final**, so a right-context environment cannot distinguish past -u from imperative -u
  (L-M4-03). `asserted-by-Ron`. This is the observation that forced the stem-name
  mechanism.
- Two verbs take a nya-initial past/conditional/concessive/negative-past series rather
  than the -i-initial pattern; formalized as a stem-final class restriction, "never
  after a derived stem" (L-M3-09). `AI-proposed-accepted`.
- **A derived stem inherits its root's inflection class** -- which is why a
  class-based restriction on a suffix blocked derived stems of one class (L-M4-01).
  `asserted-by-Ron`.
- **The final architecture** splits past stems into their own "Past" variant entries
  with their own senses and MSAs carrying the class, because inflection class on the
  stem's MSA applies to all its allomorphs and therefore let non-past stems take past
  suffixes (D-M8-05, L-M8-01). `asserted-by-Ron`.

### 4.4 Other verbal morphology

| Claim | Status |
|---|---|
| Some verb forms legitimately parse as either imperative or past -- genuine surface homophony, not a bug (L-M3-06) | `asserted-by-Ron` |
| The causative dimension is **independent** of the past-stem dimension; the long causative is its own suffix entry in the Causative slot, and one form previously glossed as a second causative is really the first causative's past stem (L-M3-11) | `asserted-by-Ron` |
| Three derivational pairs (causative, long causative, passive) had their past forms merged back into the base entries as environment-conditioned allomorphs (L-M3-15) | `AI-proposed-accepted` |
| Negative-past allomorphy splits by verb class; the geminate overlap with plain past stems was resolved by a geminate environment (L-M3-12, L-M3-13) | `AI-proposed-accepted` |
| A "long imperative" allomorph exists alongside the short one; **no conditioning environment was ever recorded** (L-M5-10) | `unresolved` |
| A closed set of -ya-final roots takes a shortened alternate stem; the environments recorded for these turned out to be **empty strings**, i.e. no real conditioning (L-M8-04) | `unresolved` -- treated as a non-issue and excluded from conversion |

### 4.5 Derivation

- Verbal nominalizers and temporal converbs are **category-changing** (verb -> noun,
  verb -> adverb) and therefore derivational, not inflectional (L-M6-06). The corpus
  first put them in an inflectional slot and reversed it: *"the Nmlz slot was a
  mistake: derivation does not belong in a template"* (C-M6-03). `asserted-by-Ron` in
  its corrected form.
- These suffixes **select for the past-participle stem**. Two mechanisms were used:
  first an inflection feature on the derivational MSA (L-M6-04), later five senses
  each carrying one of the five past inflection classes (L-M8-05). The converbal
  suffix needed a **third** mechanism -- allomorph-level inflection-class restriction
  (L-M8-06). `asserted-by-Ron`.
- Two nominalizers additionally got a tense-free sense for a non-past reading
  (L-M6-04). `AI-proposed-accepted`.
- **Derivation was explicitly out of scope at the start** -- *"Don't list nouns with
  derivational affixes right now"* (D-M2-01) -- and entered only when real text forced
  it.

---

## 5. Clitics, postpositions and compounding

| Claim | Status |
|---|---|
| Enclitic postpositions (bound) versus standalone postpositions (free) both belong under one Postposition category, with enclitics additionally recording their attachment host (L-M5-01) | `asserted-by-Ron` |
| A set of enclitic postpositions take a u-initial shape after a virama-final host; one takes a different shape after a chillu-l-final host (L-M2-09, L-M3-03) | `AI-proposed-accepted` |
| A closed set of vowel-initial enclitics develop a y-glide allomorph after a vowel-final or syllabic host, breaking hiatus -- seven enclitics (L-M6-08, L-M5-05) | `AI-proposed-accepted` |
| The citation form of an enclitic must be its **attached (matra) spelling**, not its free-standing spelling, so the boundary rules fire (L-M5-05) | `AI-proposed-accepted` |
| One concessive clitic is itself compositionally "if" + "and", modeled as a single clitic with the same glide allomorphy (L-M5-06) | `AI-proposed-accepted` |
| Two co-existing spellings of one postposition need **two entries**, because two affix-process rules with the same environment cannot both fire on one entry (L-M3-04) | `AI-proposed-accepted` -- a FLEx fact driving a lexicographic decision |
| Compounds are **right-headed**; two binary endocentric rules: noun+noun -> noun and modifier+noun -> noun (L-M6-07) | `AI-proposed-accepted` |
| One Sanskrit-derived -am loanword needs a compound-form allomorph dropping its final anusvara -- treated as a per-lexeme irregularity, not a general rule (L-M6-07) | `AI-proposed-accepted` |
| An expected noun+verb compound did not fire; POS assignments were checked and no conclusion recorded (M6 §7) | `unresolved` |

---

## 6. What a native speaker should be asked

Consolidated in [open-questions.md](../open-questions.md), but the highest-value
questions are:

1. Are the multi-parse ambiguities the grammar produces (imperative/past homophony,
   augmented-stem/dative ambiguity) **real** in the language?
2. Is the "Human" noun subclass real, and is it needed to get the plural right?
3. Are the five verb conjugation classes the right cut, and are their memberships
   right?
4. Which of the indefinite pronoun forms are transparent compositions and which are
   lexicalized? (Ron's five-entry exclusion list is an intuition.)
5. When is the long imperative used?
6. Are the chillu-vocalization, virama-deletion and enunciative-u statements
   phonological, orthographic, or both -- and does that distinction matter for the
   grammar?
7. Do the anusvara-final big numerals really behave as nouns, or was that a
   mechanism-driven convenience?

---

## 7. Merge seam

Matthew's project will be a different language. This file does **not** merge; it
becomes one of several `reference/<language>-morphophonology.md` files, and the
language-neutral content that has leaked in here (parse-time facts, FLEx architecture
facts, the "omit unattested cells" principle) should be promoted to
[`flex-modeling-decisions.md`](flex-modeling-decisions.md) or the stage bodies rather
than duplicated per language.
</content>
</invoke>
