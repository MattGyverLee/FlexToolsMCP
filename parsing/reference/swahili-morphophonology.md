# Swahili -- the Analysis the Claude-Swahili Project Arrived At

[Back to README](../README.md) | Companion to
[malayalam-morphophonology.md](malayalam-morphophonology.md)

**Status of everything here.** This is **what Matthew's FLEx project modelled, and how it
got there.** It is not an authoritative grammar of Swahili. The logs record no
native-speaker verification. The status values used:

| Status | Meaning |
|---|---|
| `asserted-by-Matthew` | stated or chosen by Matthew in a request |
| `AI-proposed-accepted` | proposed by the assistant, applied with Matthew's go-ahead |
| `AI-applied` | proposed and written by an agent (often a subagent or an agent working under a blanket mandate) with no logged per-change go-ahead |
| `domain-ruling` | decided by a `/lex-domain` review pass (numbered rulings D13, D18, ...) |
| `source-attested` | supported by an outside lexical source (kaikki, wold) under the licence policy |
| `corpus-attested` | supported by agreement evidence in the project's own texts (D-S10-08) |
| `parse-verified` | confirmed by `try_word` / `parse_text` **tool output** in the log (S8 09-23 onward) |
| `parse-unverified` | built but never confirmed by a parse in the logs |

Source shards S1-S11 ([evidence index](../evidence/directive-index.md)). These cover
**both machines' Swahili logs**: S1-S5 from the other machine (2026-05-21..09-11, no tool
output) and S6-S11 from this one (09-12..09-30). S6-S7 still have no tool output; S8 from
09-23, and S9-S11, have truncated `[OUT]` blocks. Where a value changed over time, the
**live state at 09-25 / 09-30** is given, with the date. Several S7, S8, S10 and S11
sessions were run by other clients (local models, an unidentified weaker client); their
output is used here only as failure-mode evidence, never as Matthew's analysis.

---

## 0. Project size and parse state over time

| Date | Measure | Value | Evidence |
|---|---|---|---|
| 09-12 | Lexical entries | 2,139 (before that session) | S6 A#30 |
| 09-13 | Verb stems classified for valency | 647 | D-S7-06 |
| 09-13 | Corpus wordforms used in the before/after parse | 858 | D-S7-06 |
| 09-20 | POS without an affix template | 12 of 21 | L-S8-04 |
| 09-23 | Wordforms / with 0 parser analyses | 27,705 / 14,482 | D-S8-13 |
| 09-23 | Analyses: human-approved / parser | 448 / 24,796 | D-S8-14 |
| 09-24 | Wordforms with a human approval | **0** (Matthew removed them) | V-S9-01 |
| 09-24 | Unparsed (with occurrences) | 14,038 -> 14,006 after three POS fixes | L-S9-03 |
| 09-25 | Unparsed after a **whole-corpus refile, no grammar change** | 14,096 -> 9,260 (+4,836 that already parsed) | L-S10-01 |
| 09-25 | Occurring wordforms parsed / unparsed | 17,659 / 9,066 (**66%**) | D-S10-06 |
| 09-25 | Parse speed; representation-variant product | about 6 s/word; 1.8e10 | D-S10-05, T-S10-02 |
| 09-30 | Top 10 "unparsed" by frequency (Danieli, mamlaka, elfu ...) | **all 10 parse** under `try_word` | L-S11-01 |

Read every "unparsed" count before 09-25 as "not parsed since the last FLEx parse run",
not "the grammar cannot parse" (L-S8-01, V-S10-01, V-S11-02). Three different definitions
of "unparsed" were in use on 09-25 alone (T-S10-09).

## 1. Phonology

- **Inventory:** 31 phonemes, each with lower- and upper-case graphemes, IPA and a
  description, built from one data table (D-S1-04). Default /x/ and a duplicate /ŋ/
  were deleted. Upper-case graphemes handle sentence-initial capitals (D-S5-02);
  confirmed on 09-25 (ch/Ch/CH, gh/Gh/GH, ng'/Ng'/NG'; *Roho* and *roho* parse alike,
  V-S10-09). `asserted-by-Matthew`.
- **Orthography defect (open at 09-25):** the `ng'` phoneme is coded with U+0027, but the
  texts use U+02BC MODIFIER LETTER APOSTROPHE (*ngʼombe*, L-S8-05). A grapheme parse-rate
  audit found the digraph words far below the 66% mean: gh 7.0%, th 17.0%, dh 35.6%,
  sh 45.6%, ny 68.0%, ch 80.3% (D-S10-06). The U+02BC change was validated, not written
  (Stage 2a, S10). gh/th/dh are unexplained.
- **Features:** the whole FLEx phonological-feature catalog was imported, plus a custom
  `archi` (+/-) (D-S1-02). In 2026-09 the set was pruned: features that are "-" for every
  phoneme were removed, then `dr` and `labio-dental` after an exhaustive search
  confirmed every phoneme stays distinct (D-S3-09). `AI-proposed-accepted`.
- **Archiphoneme `N̲`** (N + U+0332): a nasal with no place of its own, `[+archi]`
  (D-S1-03). Still `parse-unverified` -- the rule's output class was changed late and
  not tested (C-S1-08). On 09-13 the AI held that *mbili* / *nne* (n- + -wili / -nne)
  belong to this rule and that the whole-word `-mbili` masks the gap (L-S7-08); on 09-24
  the concord `ny-` instead got a **∅ allomorph** before voiceless obstruents and nasals
  (*kubwa, tatu, mbili, nne*; L-S9-08). N- assimilation was on the Stage 2 agenda on 09-25
  and not executed in the logs.
- **Natural classes:** 18 feature-based classes, including `[-archi]` surface classes
  and `Vnh = [-high, +syl]` (justified by hii, hivyo, mwana, kwenda; D-S2-03).
- **Division of labour, stated by Matthew (D-S6-07):** "phonological rules are for very
  broad phenomena, but allomorphs and affix process rules are for morphophonemics
  specific to an affix." The AI applied the same split on 09-13 (L-S7-08).
- **Rules** (state at 09-25 unless noted):

| Rule | Statement | Status |
|---|---|---|
| Nasal place assimilation | `N̲ -> [alpha place] / _ + C[alpha place]` | `AI-proposed-accepted`, `parse-unverified` |
| Vowel coalescence a+i -> e | given a `[Consonants] __` left context on 09-13 (L-S7-06); **disabled** by 09-25 | existing state read 10:38 / 22:41 (S10) |
| Vowel coalescence a+u -> o | same left context; enabled | as above |
| Glide formation u -> w, i -> y | see below | `AI-proposed-accepted`; i -> y **over-applied** (V-S9-07) |

- **Glide formation, history.** This rule caused the project's longest-running parse
  failure.
  1. S1: built unanchored (C-S1-07); S2 anchored on "+" with `/ _ + Vnh` (D-S2-03).
  2. 09-13: a `[Consonants]` left context plus a parallel word-initial RHS
     `# [C] __ + [Non-high V]`, so that V-only prefixes (a-, u-, i-) do not glide
     (L-S7-06, V-S7-05).
  3. 09-24: that word-initial RHS1 had **no POS limit**, so it turned `#mi+aka` into
     *\*myaka*; *miaka* (214 tokens) failed (L-S9-06, V-S9-07). Only 7 of 3,312 stored
     analyses depended on i -> y, all already covered by stored `vy` / `ch` allomorphs. A
     disable "succeeded" in the op but never persisted after four retries (C-S9-02).
  4. 09-25: blocked by a lexical **exception feature** "no glide formation", excluded on
     both RHSs and set on the stems *\*aka, \*ea, \*anzo*. Blast radius counted first
     (ny 572, vy 383, py 11, my 8 parsed words). *miaka, mianzo, myema, vyakula* then
     parse (L-S10-02). `parse-verified`.
  - **Still open:** the alternation is modelled twice, as a global rule and as stored
    glide allomorphs on each prefix (S6 conflict 4). Tagging stems does not scale to
    every vowel-initial cl.3/4 stem, and the true conditioning is the cl.4 `mi-` prefix,
    not the stem. Stage 2(b) reopened it on 09-25. See open-questions (glide formation).

## 2. Noun classes

- **Model:** agreement features, not inflection classes
  ([row 25](flex-modeling-decisions.md)); confirmed on 09-20 as the nested complex feature
  `nagr:[BantuSG:n | BantuPl:n]` on `MoInflAffMsa.InflFeatsOA` (V-S8-04). Three closed
  features hold the class: singular class, plural class, and BantuMany, originally for
  non-count classes. They are catalog-sourced since 2026-06 (`fBantuSg/Pl/Many`) and
  nested under `noun agreement` (D-S3-01).
- **Feature values at 09-25** (V-S10-02, V-S10-03): BantuSG 13 values, BantuPl 6,
  BantuMany 6 (NC 16, 15, 17, 18, 6a, 14). **There is no `NA` value any more.**
  - Locatives 15-18 sit under BantuSG (p- 16, mw- 18, kw- 15/17; D-S8-09).
  - Class 13 (tu-) was under BantuSG; on 09-20 it was added under BantuPl as well,
    rather than migrated (D-S8-10). Which one an entry uses is still per-entry.
  - Class 1a has its own concord senses (40 nouns carry BantuSG:1a; D-S8-11). Proper
    nouns carry NC 1a so the null prefix can fill ClassPrefix (L-S9-04).
- **What each entry carries:**
  - A noun stem's MSA carries its singular class + paired plural class (e.g. 9/10)
    (D-S1-06). The S1 `NA` fill of unused features is gone by 09-25 (V-S10-02).
  - Class prefixes carry matching values in an obligatory **ClassPrefix** slot. By 09-25
    a null prefix carries **one** feature (`∅-1 nul.pref.nc10.pl [BantuPl:10]`).
  - Null prefixes exist for cl. 5, 9, 10, 1a and 16 (D-S2-01).
  - Noun and Proper Noun template: `[ClassPrefix] STEM [Locative?]` (V-S10-08).
- **BantuMany relocation (2026-09-06):**
  - Null prefixes sat on BantuMany while the stems sat on SG/Pl. The features never
    overlapped, so the null prefixes over-generated (L-S4-01).
  - 77 BantuMany values were moved onto BantuSG/BantuPl, with 10 class corrections. 11
    rows were held with reasons (D-S4-05, D-S4-10). `domain-ruling`.
  - **Landed:** by 09-20 BantuMany was down to 3 senses, none alongside SG/Pl, one
    mis-tagged (*panga* 'machete' as loc. 16; D-S8-09, V-S8-02). The feature itself
    still exists (V-S10-03). The 11 held rows are not addressed in any log.
- **Class-16 null prefix:** questioned as having no legitimate stem (L-S4-01).
  `zero-5` (cl.16) was set `DoNotUseForParsing` on 09-13, not deleted (V-S7-02). On
  09-24 stored analyses still showed `∅ nul.pref.nc16 + watu` (V-S9-03), so either the
  flag does not stop HermitCrab or those analyses predate it. Not resolved (Q-39).
  `DoNotUseForParsing` is **deprecated in this repo's tooling** -- see section 6.
- **Q-38 (the `NA` defect) -- moot at 09-25.** The worry was that a class-9 prefix with
  `BantuPl=NA` would clash with a 9/10 stem carrying `BantuPl=10`. The feature system no
  longer has `NA` (V-S10-02). Unification is by **exact value**: a 1a stem does not
  satisfy a class-1 concord (D-S8-11, V-S8-03), and inflectional features unify rather
  than overwrite (L-S7-01). The live problem is the converse: **null prefixes license too
  much.**
  - 9/10 nouns get two analyses by construction, one per null prefix (*nyumba*,
    V-S10-02).
  - Stacking: *watu* 5 null-prefix analyses (L-S9-05) or 8 (L-S10-05), *mwana* 13,
    *wana* 10, *Misri* 10 (V-S10-07); a 1a name with `∅ nc10.pl` (V-S9-02). Null
    prefixes are tried on every name (`∅-3`, L-S11-03).
- **Noun-class assignment, rules of evidence** (D-S3-05, `asserted-by-Matthew`):
  1. the prefix test (what the parser enforces);
  2. kaikki / wold;
  3. concord evidence;
  4. *added 09-25:* **agreement of the following word in the corpus** (*mamlaka* NEXT
     ya 15, yake 5 -> 9/10; *hukumu* -> 9/10; D-S10-08). `corpus-attested`.

  Worked example: `afisa` -> 5/6 from the attested plural `maafisa`. Undecidable cases
  go in with a `class-negotiable` flag. Never default to 9/10: C-S1-04 shows the cost,
  and it was **still being paid on 09-25**: *roho* and *fimbo* 1/2 -> 9/10, *nguo* 7/8
  -> 9/10, *zazi* 5/8 -> 7/8, *kabila* 9/10 -> 5/6, and 158 noun stems with no class
  features at all (plurals entered as stems: *\*maaskari, \*makuhani*; L-S10-03,
  V-S10-06).
- **Lexical convention:** the lexeme form is the **bound stem** with the prefix
  stripped; the citation form is the full singular word (D-S3-03, L-S3-02). The
  August standard bucketed 832 of 1,024 nouns as parse-ready. Applied again on 09-25:
  *mwanadamu* -> lexeme `anadamu`, citation `mwanadamu` (L-S10-06).
- **Elsewhere form of the prefixes (S1 -> S6).** S1 put the most-restricted form in the
  lexeme (L-S1-02). On 09-12 Matthew called this an error ("the default/everywhere form
  of the affix should be the lexeme", D-S6-04) and 20 entries were swapped with
  FieldWorks' own swap logic, keeping object identity (D-S6-05, L-S6-02, D-S6-06):
  - noun-class and concord prefixes: the pre-consonantal full form is basic, the
    pre-vocalic glide form (mw-, ch-, vy-, w-, kw-, ny-) is the conditioned variant;
  - verbal extensions: the -i- grade is basic, the -e- grade is the harmony variant.

  At 09-24/09-25 the class prefixes follow F1 and parse (vi-1 `vi` + `vy / _ [V]`, m-1,
  n-, wa-4, ni-1, zi-1; V-S9-04, V-S10-04). `asserted-by-Matthew` (principle);
  per-entry choices `AI-applied`.
- **Narrowed allomorph environments** (each fixed one blocked word, `parse-verified`):
  cl.2 `w-` `/ _ [V]` -> `/ _ a`, `/ _ e` (*Waisraeli*; L-S9-07); ma-2 `m` -> `/ _ e`
  (*maovu*); zi-1 `z / _ a` (*zadumu*); ni-1 `n / _ a` (*nawaambia*; L-S10-06).
  Suppletive plural stems as stem allomorphs: *jambo* `mbo / # ma _`, *mungu*
  `ungu / # mi _`, checked against `maa-` words first (L-S9-08). `AI-applied`.
- **cl.1 object marker m-3:** lexeme now `mu`, with `mw` narrowed from `[V]` to
  `/_a /_e /_i /_o` (S6). Two duplicate `mu` entries were merged with
  `ILexEntry.MergeObject` on 09-13 (T-S7-05). Choosing `mu` rather than `m` as the
  elsewhere OM is unusual for standard Swahili (a-na-m-pend-a). **Unresolved.**

## 3. Concord and closed classes

| Series | Category | How built | Evidence |
|---|---|---|---|
| Adjective Concord | adj | S1 template work; pre-vocalic allomorphs added 09-13; **no agreement features**, because noun-adjective agreement is syntactic and HermitCrab parses one word | S1, L-S7-07 |
| ConnConcord (connective "of") | conn | concord prefix + `-a` stem, own template | D-S2-04 |
| PossConcord | pro-form | deep copy of ConnConcord feature structures; each affix carried **one** `nagr` value though several serve many classes (w- = cl.1 only, serves 1/2/3/11/14) | D-S4-06, L-S7-07 |
| NumConcord | num | deep copy of Concord feature structures | D-S4-06 |
| Quantifier (`-ote`) | new POS **Quantifier** | reuses the 9 ConnConcord MSAs; on 09-13 found **inert**: those fillers' POS is Connective, not an ancestor of Quantifier. Retire-or-move recommended, not done | D-S5-05 (ruling D13), L-S7-04 |

- **One sense per agreement value (09-20).** A concord homophonous across classes had a
  multi-class gloss (`conn.conc.nc4/6/9`) over a one-class feature structure, so the
  other classes silently failed to unify. Fix: one sense per class, each with its own
  `nagr` value and slots (y- 4/6/9; w- 1/2/3/11/14 + 1a; kw- 15/17). 14 new senses were
  found unslotted by the module's own audit and fixed (D-S8-07, D-S8-08, L-S8-03).
  `AI-applied`; indirectly `parse-verified` (*yake* 3 analyses, 09-23).
- **Demonstratives:** h- + concord + deictic suffix, own template; 22 whole-word entries
  retired (D-S2-04). Split on 09-13 into proximal/referential (h- anchor + optional -o)
  and distal (-le anchor); zero allomorph for ha-o / hu-o and cl.18 m-le **open**.
- **Relative `amba-` (09-24):** `*amba` sat in `Verb > Transitive`, whose template
  requires Subj2, so all 13 amba- forms (999 tokens) failed. New `Verb > Relativizer`
  POS with template `amba- relative` = [RelSuf, required]. RelSuf: -ye nc1,
  -o nc2/3/11/14, -yo nc9, -lo nc5, -cho nc7, -vyo nc8, -zo nc10, -po nc16, -ko nc17,
  -mo nc18 (L-S9-02). `AI-proposed-accepted`, `parse-verified`, filed.
- **Independent pronouns:** top-level `Pronoun` POS with no template (it had been a
  subcategory of `Pro-form`, which owns one); *yeye* retyped bound stem -> stem at
  Matthew's request (L-S9-01, D-S9-03). `parse-verified` (`parse_diff` fixed 3, broken 0).
- **Invariant numerals:** 14 Arabic-origin numerals (saba, tisa, kumi, ishirini ... mia)
  in a top-level `Invariant Numeral` POS with no template; Bantu numerals keep concord
  (L-S9-03). `AI-proposed-accepted`, `parse-verified`.
- **Possessives:** compositional, concord + -angu/-ako/-ake/-etu/-enu/-ao. The 12
  whole-word possessive stems were set `DoNotUseForParsing` (about 20 shadow entries on
  09-13, the last 4 on 09-20; D-S7-04, D-S8-12). Effect on the parser **unverified**;
  see section 6.
- **Suppletive pronouns:** kept whole ("No parsing benefit").
- **Reduplication:** abstract `[...]` affix (D-S2-02); Matthew confirmed `[...]` is the
  correct full-reduplication syntax (V-S6-04). On 09-13 RDP became a derivational
  Verb -> Verb MSA, out of every template slot (*kutangatanga*; S7). Parse result not
  logged: still `parse-unverified`.
- **Wastebasket POS (09-13):** new POS Interrogative and Copula; Particle items moved to
  Adverb, Interrogative, Copula, Interjection; *karibu* -> Verb (plus an Adverb entry
  on 09-24), *miongoni* -> Preposition (S7). Raised by Matthew ("mbali is a 'particle',
  maybe that's not right", D-S6-11). `AI-applied`.

## 4. Verbs

**Templates.** The slot order is now in the logs. On 09-12 (D-S6-08, restored after
the AI tried to merge the clones, C-S6-02):

| Template | Prefix slots | Construction |
|---|---|---|
| Verb inflection (VI1) | Neg1 Subj2 Neg2 TAM Rel | finite, no object marker |
| Verb inflection2 (VI2) | Neg1 Subj Neg2 TAM2 Rel Obj | finite, with object marker |
| Verb inflection3 (VI3) | Neg1 Subj Neg2 Rel Obj | subjunctive, no TAM, required FVsubj `-e` |
| Verb inflection4 (VI4, 09-12) | Neg1 Subj Neg2 TAM2 Obj | post-final relative, `... FV RelSuf` |

- **Why the clones exist** (Matthew, D-S6-08): "the duplication is to allow subject
  with or without object, but not a bare object." Optionality lives on the slot
  object, so a different Optional value needs a duplicate slot (L-S6-04, L-S5-02). The
  reasons are written into each template's Description (D-S6-09, D-S7-02).
- **09-13 changes:** VI4 rewired to `[Neg1, Subj, Neg2, TAM, Obj2]` with RelSuf
  obligatory, because it "licensed zero analyses" (C-S6-03); `Obj2` cloned from Obj
  and shared by the 14 OM MSAs (L-S7-02). Plural imperative `(Obj2)-root-(FV)-ni`.
  Infinitive: ku- as a second, verbal MSA on the cl.15 `ku-1`, Inf obligatory, FV
  optional for Arabic-loan stems, NegInf `to-` after Inf (*kutosema*, order confirmed
  by Matthew). Subj2 made obligatory and VI1 moved TAM -> TAM2 (main session 01:36).
- **Contradictions the same day (C-S7-02):** a `Verb imperative singular` template
  was built by the main session after the verb subagent had declined it for lack of an
  anchor (L-S7-03); and TAM2 was made optional at 20:56 ("husema / sisemi have no TAM
  filler"), against the verb agent's "DO NOT change the Optional flag". Under README
  4.13 the second should have been a separate template. **Open.**
- 09-25: Verb owns 8 templates (VI1-VI4, imperative plural, ...; V-S10-08).
- Subjunctive **without** an object marker: VI3 requires Obj; the gap was found on
  09-12 and no template is logged for it. **Open.**
- **Negation and habitual (09-13, `AI-applied`):** habitual hu- is a Subj/TAM
  portmanteau in Subj; negative portmanteaus si- (1sg), ha- (3sg cl.1), hu- (2sg) in
  Subj; Neg2 si- is the subjunctive negative; `-i` is the negative non-past FV, negative
  past keeps `-a` (*sikusema*; L-S7-09). 09-25 added an `a-` "present (general)" TAM
  prefix (*nawaambia*; L-S10-06).
- **Inflection classes** (D-S5-04), from the citation form:
  - **FVt** (takes the final vowel): 563 stems, where citation = `ku` + stem + vowel.
  - **Inv** (invariant, e.g. loans): 76 stems, where citation = `ku` + stem.
  - Named 'Final-vowel taking' and 'Invariant (loan)' at 09-25 (V-S10-08).
  - Anomalies go to a human. Whether the FV allomorphs were restricted to these classes
    is not logged.
- **Stems:** roots without the final vowel. Root+FV duplicates were disabled, then
  deleted (L-S4-02). A duplicate `*mwaka2` was deleted with a GUID + headword guard
  (C-S10-01).
- **`ku-`:** two homographs by function -- infinitive/augment in TAM/TAM2, and negative
  past (L-S5-03, `domain-ruling`). From 09-13 the infinitive is the cl.15 noun prefix
  with a verbal MSA. `ku-3` ('subject cl.15', 36-38 of its 39 uses really infinitives)
  was left with its stale analyses (V-S7-08).
- **Relative suffixes:** -ye, -yo, -cho, -lo created 09-12 with no class features (S6);
  -o -vyo -zo -po -ko -mo added 09-13; full inventory in section 3. An over-generation
  risk (any subject class with any relative suffix) is not tested.

### 4.1 Verb extensions (Q-40) -- decomposed on 09-13

- **Before:** in inflectional slots Caus / Appl / Recip / Pass / Stat / Statal in every
  verb template (C-S1-06, still so on 09-12: V-S6-03), and at one point listed inside
  stems (*ambie, chukuliwa, mpelekee*; C-S2-03).
- **The conversion (V-S7-01, L-S7-05, D-S7-06):** a staged programme.
  1. Experiments on throwaway objects: subcategory template inheritance; whether
     HermitCrab enforces `MoDerivAffMsa.FromPartOfSpeech`, subsumption-aware (D-S7-05).
     Verdicts not logged; the next steps rely on both.
  2. Passive-only prototype on 20 hand-marked roots, then reverted (reason not logged).
  3. All 647 verb senses exported, classified outside FLEx as Transitive/Intransitive,
     and repointed in 5 batches against a 24-form parse baseline and diff.
  4. Atomic conversion at 12:05: POS tree **Verb > Underived > {Transitive,
     Intransitive}** and **Verb > Detransitive**. Causative and applicative are
     `MoDerivAffMsa` Underived -> Transitive; passive, reciprocal, stative and statal
     Transitive -> Detransitive. A 30-form probe list and 858 corpus wordforms were
     parsed before and after (counts not logged, T-S7-02).
  5. The empty Caus/Appl/Recip/Pass/Stat/Statal/Redup slots were removed from all verb
     templates at 14:58.
- **Grades (09-12, `AI-applied`):** applicative `-i-`/`-e-`, causative `-ish-`/`-esh-`,
  statal `-lik-`/`-lek-` by mid-vowel harmony; stative `-ik-`; passive `-w-`. The code
  comment put the longer passive `-ew-` after **consonant**-final roots; standard
  Swahili has plain `-w-` after C and `-iw-`/`-ew-`/`-liw-`/`-lew-` after vowel-final
  roots. **Check.** The 09-13 probe set of "must survive" passives (*kuvunjewa,
  kukatewa, kuchaguwa*) is likely non-words (C-S7-07).
- **Evidence it works:** passive and stative surface as affixes in 09-24/25 parses
  (*walipewa* = wa+li+p+ew+a; V-S10-05). Evidence of over-generation: *wanawake*
  mis-parsed as wa+nawa+k(stative)+e; 09-13 STEP6 candidates *kuvunjishia,
  kuvunjiisha*.
- **Relapses (P10):** applicative and passive shapes of *zaa* re-added as stem
  allomorphs 3.5 h after the conversion (*zalia, zaliwa*; C-S7-06), then on 09-25 split
  into separate Transitive stems rather than decomposed (L-S10-04, C-S10-03).
  Lexicalized or not is undecided.
- **Still unparsed at 09-30:** a long-tail sample with passives (*walifanywa,
  amependezwa*), applicatives (*amekikalia*), causative *-esha* (*hukomesha*), reflexive
  ji-, relative -o-, -po-/-ka-po- relatives and subjunctive *mwondoe* (S11). The tool
  used could not show why. This is the best real-corpus test set for the extensions,
  and nobody followed it up.
- **Not implemented:** locative `-ni` as a derivational Noun -> Noun MSA with
  ToInflFeats (an inflectional cl.17 stamp would fail to unify with the stem's class;
  L-S7-01); not on human cl.1/2, blocked after cl.16-18.

## 5. Lexical-source and licence policy

From the phase plans (D-S3-05):

| Source | Licence | Allowed use |
|---|---|---|
| kaikki.org (Wiktextract) | CC BY-SA | facts (class, plural) only; glosses re-authored |
| lexibank/wold | CC-BY | importable with attribution; cross-check |
| TUKI dictionaries | restricted | validation only |
| SALAMA | restricted | treated as unreachable in the plan |

**In practice, 09-24 onward**, Matthew asked the AI to use its "deep knowledge of
Swahili" (D-S9-01) and later "/lex-linguist's deep linguistic knowledge" (D-S10-03).
The entries, glosses, class assignments and allomorphs made under those mandates are
not labelled as AI-sourced in the project (Q-42). Proper-noun classes for *Torati*
(Torah) and *Yerusalemu* (a place) as 1a were copied from *Havila*, not checked
against text agreement (L-S9-04).

**Glosses (09-14):** 808 senses were given short glosses, with the full original moved
to the Definition (D-S8-01). Grammatical morphemes got a dotted, lowercase scheme
(`sbj.nc10`, `conn.conc.nc4`, `nul.pref.nc1a`, `neg.3sg.nc1`; D-S8-02). The agent
called it Leipzig; it is a **project-local convention**, not Leipzig. It was run by a
local-model client, so it is failure-mode evidence as much as practice (C-S8-02).
Scripts that looked affixes up by gloss broke (C-S7-09).

## 6. Suppression with `DoNotUseForParsing` -- recorded, but deprecated

The project used `DoNotUseForParsing=True` to keep entries listed but out of the parser:

- 09-13: `zero-5` (cl.16 null prefix; V-S7-02), the duplicate `*ote2` (L-S7-04), about
  20 whole-word possessive shadow entries and the losing homographs, each only after
  the compositional analysis was confirmed in the corpus (D-S7-04).
- 09-20: four more whole-word possessives; 33 entries carried the flag in all (D-S8-12).

**Caveats:**
- **The flag is deprecated in this repo's tooling.** It is not to be used in recipes or
  fix-ups, or as a model for new Flexicon API. These uses are a record of what the
  project did, not a pattern to copy. They need migrating to the current mechanism.
- **Its effect is unverified.** The 09-20 module marked it "UNVERIFIED", and its
  "decisive test" from stored ParserCount could not work without a reparse (C-S8-07).
  On 09-24 stored analyses still used the flagged cl.16 null prefix (V-S9-03).
- It overloads the soft-delete convention in
  [flex-data-conventions](../conventions/flex-data-conventions.md). A separate "listed but
  not parsed" convention is an open question.

## 7. Lexicon defects to check (end of logs, 09-30)

- **Probable junk entries:** bare entries `malaka, el, fu, kumu, gizo, is, hara, en,
  ghadha, bu` (and possibly `hu, zi, ma, a`) created around 2026-09-30 19:54 from
  syllable splits, with no sense, POS or morph type (C-S11-05, inferred). Stage 13
  candidate; check read-only first.
- *panga* mis-tagged loc. 16 (D-S8-09); the 158 featureless noun stems (L-S10-03).
- *binti* changed 2/1 -> NC 1a and its old features reused for *israeli*, unreviewed
  (S9 conflict 7).
- *nami* parses only as a whole stem; na- + -mi is not modelled (S8). *wengi* still
  unparsed on 09-24 (S9).
- Stage 2 of 5 (ng', glide formation, passive, N- assimilation, ch-/vy-) was briefed on
  09-25 with filing withheld; no Stage 2 write is in the logs (D-S10-04).

## 8. Merge seam

This file **does not merge** with the Malayalam file; it sits alongside it. Content
that turns out to be language-neutral has been promoted to
[flex-modeling-decisions](flex-modeling-decisions.md) (rows 25-31 from S1-S5, and the
rows added from S6-S11) and to the stage files' "Second-Operator Evidence" sections.
Both machines' Swahili logs are now ingested (S1-S11, to 09-30). The project itself has
moved on since; for anything newer, read the live project, not this file.
