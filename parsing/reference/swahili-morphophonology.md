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
| `parse-verified` | confirmed by a parse: Matthew's own FLEx parser run (09-13 01:20 onward, V-S7-12), in-process HermitCrab in the transcripts (09-13 01:55 onward, V-S7-11), or `try_word` / `parse_text` / sandbox output (09-23 onward) |
| `parse-unverified` | built but never confirmed by a parse in the logs or transcripts |

Source shards S1-S11 ([evidence index](../evidence/directive-index.md)). These cover
**both machines' Swahili logs**: S1-S5 from the other machine (2026-05-21..09-11, no tool
output) and S6-S11 from this one (09-12..09-30). The S6-S11 runtime logs were then checked
against the **Claude Code transcripts** behind them, which restore the parse output, the
counts and Matthew's verbatim words (including mid-turn messages) that the logs lost. Ids
are given with the transcript verdict where it changed a claim ("V-S7-02, refuted by
transcript"). The logs call the server 2.12.0, but they came from a **pre-2.13.0 main
checkout** (the parse tools shipped in 2.13.0, 09-25). Where a value changed over time, the
**live state at 09-25 / 09-30** is given, with the date. Several S7 (14:09-20:05), S8 (09-14
and 09-20 local-model) and S11 sessions were run by other clients; the 09-30 client is
unidentified and was **not Claude Code** (S11 transcript). Their output is used here only as
failure-mode evidence, never as Matthew's analysis.

---

## 0. Project size and parse state over time

| Date | Measure | Value | Evidence |
|---|---|---|---|
| 09-12 | Lexical entries | 2,139 (before that session) | S6 A#30 |
| 09-12 | Wordforms / with 0 parser analyses / with 1+ | 798 / 168 / 630 (the 09-12 proposal agents counted 854 / 164 about 1.5 h later; never reconciled) | D-S6-01 |
| 09-12 | Noun stems stored unsegmented | 776 of 1,069 (about 60 genuinely prefix + stem) | L-S6-06 |
| 09-13 | Verb stems classified for valency | 647 -> 508 Transitive / 139 Intransitive | D-S7-06, D-S7-12 |
| 09-13 | Forms parsed before/after the valency conversion | 1,054 (858-wordform inventory + baseline types): 1,020 unchanged, 34 lost, 0 gained | D-S7-06, V-S7-11 |
| 09-24 | Sandbox A/B, glide rule removed (2,139 words) | 1,517 -> 1,568 parsed; 54 fixed, 3 broken | T-S9-08 |
| 09-20 | POS without an affix template | 12 of 21 | L-S8-04 |
| 09-23 | Wordforms / with 0 parser analyses | 27,705 / 14,482 | D-S8-13 |
| 09-23 | Analyses: human-approved / parser | 448 / 24,796 | D-S8-14 |
| 09-24 | Wordforms with a human approval | **0** (Matthew removed them) | V-S9-01 |
| 09-24 | Unparsed (with occurrences) | 14,038 -> 14,006 after three POS fixes | L-S9-03 |
| 09-25 | Unparsed after a **whole-corpus refile, no grammar change** | 14,096 -> 9,260 (+4,836 that already parsed) | L-S10-01 |
| 09-25 | Occurring wordforms parsed / unparsed | 17,659 / 9,066 (**66%**) | D-S10-06 |
| 09-25 | Parse speed; representation-variant product | about 6 s/word; 1.8e10 | D-S10-05, T-S10-02 |
| 09-30 | Top 10 "unparsed" by frequency (Danieli, mamlaka, elfu ...) | **all 10 parse** under `try_word`: they are the 09-25 Stage 1 fixes, never filed | L-S11-01, V-S11-04 |

Read every "unparsed" count as "not parsed and filed since the last FLEx parse run", not
"the grammar cannot parse" (L-S8-01, V-S10-01, V-S11-02). In every session after 09-24 A,
most of the frequency queue already parsed and only needed filing (B 5/20, C 9/10, D 4/5;
T-S9-14). Several definitions of "unparsed" were in use (14,482 / 14,371 / 14,283 on 09-23,
D-S8-13; 14,105 vs 9,151 in texts on 09-24/25, T-S10-09).

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
  (*kubwa, tatu, mbili, nne*; L-S9-08). On 09-13 Matthew ruled that the 9/10 concord
  "can get a N form that will be fixed by a phonological rule", that irregular plurals
  should be inflectional variants, and that *vikijana -> vijana* "sounds like an affix
  process rule"; the AI added root storage (`-uso`, `-jana`) and *meno* as truly irregular
  (L-S7-14). None of it was implemented. N- assimilation was on the Stage 2 agenda on 09-25
  and not executed (Stage 2 never finished, D-S10-05).
- **Natural classes:** 18 feature-based classes, including `[-archi]` surface classes
  and `Vnh = [-high, +syl]` (justified by hii, hivyo, mwana, kwenda; D-S2-03).
- **Division of labour, stated by Matthew (D-S6-07):** "phonological rules are for very
  broad phenomena, but allomorphs and affix process rules are for morphophonemics
  specific to an affix." This narrowed his own remark a minute earlier ("they can more
  broadly be phonological rules"), after which the AI had proposed ki->ch and similar as
  rules; it withdrew them (`ki -> ch / _V` would derive *\*chatu* from *kiatu*). The AI
  applied the same split on 09-13 (L-S7-08). The 09-25 linguist spec goes further: gliding,
  ch-/vy- and passive allomorphy "are conditioned by the morpheme, not by phonology"
  (L-S10-09).
- **Rules** (state at 09-25 unless noted):

| Rule | Statement | Status |
|---|---|---|
| Nasal place assimilation | `N̲ -> [alpha place] / _ + C[alpha place]` | `AI-proposed-accepted`, `parse-unverified` |
| Vowel coalescence a+i -> e | given a `[Consonants] __` left context on 09-13 (L-S7-06); **disabled** by 09-25 | existing state read 10:38 / 22:41 (S10) |
| Vowel coalescence a+u -> o | same left context; enabled | as above |
| Glide formation u -> w, i -> y | see below | `asserted-by-Matthew` (keep and constrain, 09-13); i -> y **over-applied** to cl.4 `mi-` (V-S9-07) |

- **Glide formation, history.** This rule caused the project's longest-running parse
  failure.
  1. S1: built unanchored (C-S1-07); S2 anchored on "+" with `/ _ + Vnh` (D-S2-03).
  2. 09-13 ~01:14: the rule fired on roots, so *a-ta-mu-u-a* surfaced as *atamuwa*, and
     **150 verb roots ending in u or i** were mis-glided (*nunwa, chagwa, sikya*). Matthew
     chose, by multiple choice, "Add left context to the rule" over "Disable rules, list
     allomorphs instead" (35 prefix edits). Result: `+ [C] __ + [Vnh]` plus a word-initial
     RHS `# [C] __ + [Vnh]`, so V-only prefixes (a-, u-, i-) do not glide (L-S7-06,
     V-S7-05). **Parse-verified by Matthew** in FLEx at 01:28: "atamuua looks good"
     (V-S7-12). The rule is not redundant with the stored allomorphs: 10 prefixes carry
     the glide lexically, **35 depend on the rule** (L-S7-18; this corrects the 09-12 AI
     claim that every case is also covered by an allomorph).
  3. **Left over on 09-13: CV verb roots still mis-glide** (*ju, tu, ku, chu, vu, li, zi,
     ti*: *ju+a* -> *\*jwa* for *jua*; L-S7-17). The AI killed a right-context fix that
     would have broken 29 stems that need the glide (*mweupe, choo, maua*; C-S7-15). It
     also said "There is no rule-exception route" and that stem names drive allomorph
     selection, not rule blocking. The second half is right; the first was **superseded on
     09-25**, when an exception feature did block the rule (step 5). Nobody applied it to
     these roots. Open, see [open-questions Q-50](../open-questions.md).
  4. 09-24: *miaka* (214 tokens) failed: `#mi+aka` came out as *\*myaka* (L-S9-06). The
     RHS dump showed the word-initial RHS had no POS limit, but that it **was the cause is
     not established** (V-S9-07, weakened by transcript): narrowing the left context to
     exclude `m`, first on RHS1 and then on both RHSs, left *miaka* failing ("cause not
     found"). Only removing the whole rule fixed it. The 2,139-word **sandbox A/B**
     completed: 1,517 -> 1,568 parsed, **54 fixed** (*miaka, miamba, niambie, kiongozi,
     viongozi, kioo, sielewi* ...), **3 broken** (*vyombo* x2, *vyanzo*, which had only
     wrong verb readings before) because subject `vi-2` (sbj.nc8) has no `vy` allomorph,
     unlike `vi-1` (T-S9-08, L-S9-09). So the 7-of-3,312 dependency count missed affix
     homographs. The agent recommended "disable the rule and add a `vy` / `_ V` allomorph
     to `vi-2`" and waited for Matthew; no answer. The live disable had "succeeded" in the
     op but never persisted after four retries (C-S9-02). *Status 2026-10-09:
     `PhonRules.SetDisabled` now exists (flexicon 4.12.0, flexicon#572) in place of the raw
     cast used then; persistence across a reopen is untested.*
  5. 09-25: a fresh chat, asked to "resolve each one", did not consult that result
     (C-S10-08). It blocked the rule with a lexical **exception feature** "no glide
     formation" (`noGlide`), excluded on both RHSs and set on the stems *\*aka, \*ea,
     \*anzo*. Blast radius counted first (ny 572, vy 383, py 11, my 8 parsed words).
     *miaka, mianzo, myema, vyakula* then parse (L-S10-02). `parse-verified` by spot check
     only: "I didn't reparse the whole corpus." **Why on stems, not on `mi-`:** HermitCrab
     adds a stem's `ProdRestrictRC` to the entry's rule features, but turns an affix MSA's
     `FromProdRestrictRC` into a *required* feature (`HCLoader.cs` :699-700, :950-951), so
     tagging the prefix would not exempt anything (L-S10-07; source reading, untested).
     Creating the feature took raw LCM at the time (C-S10-05). *Status 2026-10-09: tagging
     stem MSAs is wrapped (`MSA.AddExceptionFeature`, flexicon 4.12.0, flexicon#574);
     creating the feature (`InflectionFeatures.ExceptionFeatureCreate`, flexicon#631) and
     tagging affix MSAs with `side="from"/"to"` (flexicon#630) are fixed on flexicon main,
     not yet released (after 4.12.0). Setting the RHS's excluded rule features still has
     no wrapper (readers only).*
  - **Still open:** the alternation lives in two places, the rule and the glide allomorphs
    on 10 prefixes. Tagging stems does not scale to every vowel-initial cl.3/4 stem, and
    the true conditioning is the cl.4 `mi-` prefix, which HermitCrab cannot carry the
    exception on (step 5). Two tested or specified alternatives exist: disable the rule
    and add `vy` to `vi-2` (sandbox: 54 fixed, 3 broken, the 3 fixable), or the linguist
    spec's per-morpheme `mw-/tw-/kw-` allomorphs with *kwenda/kwisha* listed (L-S10-09).
    Matthew approved the glide item among all 11 Stage 2 options (D-S10-16); Stage 2 was
    validate-only and never executed. See open-questions Q-44.

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
  - Class 13 (tu-) was under BantuSG; on 09-20 it was added under BantuPl as well, at
    Matthew's instruction ("add 13 as an option for plural without removing it from
    singualr", D-S8-10). No entry used class 13 at the time.
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
  - **Landed:** on 09-12 a proposal agent found BantuMany used by zero MSAs (V-S6-07);
    by 09-20 it was down to 3 senses, none alongside SG/Pl, one mis-tagged (*panga*
    'machete' as loc. 16; D-S8-09, V-S8-02). A lex-domain consult offered two readings
    (non-count grouping; derived-locative stacking); the data favours dead weight. The
    feature itself still exists (V-S10-03). The 11 held rows are not addressed in any log.
- **Class-16 null prefix -- never suppressed.** On 09-12 the noun proposal agent named the
  unrestricted null prefixes as the main noun over-generator (*kichwa* 6 analyses, five
  wrong; *watu, mwana, uzao* 5 each; L-S6-09). `zero-5` (cl.16) had 12 references and
  added a spurious cl.16 reading to about 967 prefixless stems, so on 09-13 the noun write
  agent set it `DoNotUseForParsing`, not deleted, accepting that *mahali* would lose its
  cl.16 reading (V-S7-02). **That flag is a no-op in both parsers** (section 6), so the
  "suppression" did nothing (V-S7-02's "suppressed", refuted by transcript). This is why
  analyses with `∅ nul.pref.nc16 + watu` were still there on 09-24 (V-S9-03, explained).
  Whether to keep the null prefix is still open (Q-39). To take it out of the parser now,
  set `IsAbstract` on its forms and check with `parse_diff`.
- **Q-38 (the `NA` defect) -- moot at 09-25.** The worry was that a class-9 prefix with
  `BantuPl=NA` would clash with a 9/10 stem carrying `BantuPl=10`. The feature system no
  longer has `NA` (V-S10-02). Unification is by **exact value**, and inflectional features
  unify rather than overwrite (L-S7-01). The 09-20 claim that 40 class-1a nouns "fail to
  unify" with the class-1 `w-` concord (D-S8-11, V-S8-03) needs a parser check: HermitCrab
  parses one word, so a possessive concord on a separate word (*wake*) never meets the
  possessor noun's features (analyst inference from the S8 transcript). The live problem is
  the converse: **null prefixes license too much.**
  - 9/10 nouns get two analyses by construction, one per null prefix (*nyumba*,
    V-S10-02); the 09-30 "duplicate" pairs for *hukumu, ishara, enzi* are this, not
    duplicate entries (L-S11-02).
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
  of the affix should be the lexeme", D-S6-04). Of 20 multi-allomorph entries, none had an
  unconditioned lexeme form: 1 (`m-3`) had the default among the alternates, 19 had no
  elsewhere form. With FieldWorks' own swap logic, 15 were swapped and 19 environments
  cleared, with **3,526 morph-bundle references identical before and after** (D-S6-05,
  L-S6-02, D-S6-06):
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
- **cl.1 object marker m-3:** it was the one entry whose unconditioned `mu` shadowed its
  vowel allomorph (`mw` used 0 times, against 17 for `m` and 17 for `mu`; L-S6-01). After
  the 09-12 swap: `mu` elsewhere (in practice before u, *akamuumba*), **`m / _ C`** (17
  uses), `mw / _a _e _i _o` (D-S6-05). So standard *a-na-m-pend-a* is covered by `m`;
  the earlier worry about `mu` as the elsewhere OM is answered. On 09-13, at Matthew's
  request ("merge the 2 mu entries"), a duplicate `mu` was merged into `m-3` with
  `ILexEntry.MergeObject`; FLEx collapsed the two MSAs, which is what removed the
  duplicate parse: ambiguity tracks MSAs, not senses (T-S7-05, L-S7-19).

## 3. Concord and closed classes

| Series | Category | How built | Evidence |
|---|---|---|---|
| Adjective Concord | adj | S1 template work; pre-vocalic allomorphs added 09-13; **no agreement features**, because noun-adjective agreement is syntactic and HermitCrab parses one word. A 09-20 census showed this is a consistent convention: conn/pro/dem concords all carry features (16/16, 16/16, 13/13), adj/num/rel/sbj none (0/12, 0/12, 0/21, 0/12) | S1, L-S7-07, D-S8-15 |
| ConnConcord (connective "of") | conn | concord prefix + `-a` stem, own template | D-S2-04 |
| PossConcord | pro-form | deep copy of ConnConcord feature structures; each affix carried **one** `nagr` value though several serve many classes (w- = cl.1 only, serves 1/2/3/11/14) | D-S4-06, L-S7-07 |
| NumConcord | num | deep copy of Concord feature structures | D-S4-06 |
| Quantifier (`-ote`) | new POS **Quantifier** | reuses the 9 ConnConcord MSAs; on 09-13 found **inert**: those fillers' POS is Connective, not an ancestor of Quantifier. Retire-or-move recommended, not done | D-S5-05 (ruling D13), L-S7-04 |

- **One sense per agreement value (09-20).** A concord homophonous across classes had a
  multi-class gloss (`conn.conc.nc4/6/9`) over a one-class feature structure, so the
  other classes silently failed to unify. Fix: one sense per class, each with its own
  `nagr` value and slots (y- 4/6/9; w- 1/2/3/11/14 + 1a; kw- 15/17). The rule is
  **Matthew's** ("For the y affix you may need to add it with multiple senses"), confirmed
  by a lex-domain consult ("underspecification is NOT a valid alternative here"); writes
  went in three separately approved steps (D-S8-07, D-S8-16, L-S8-03). The 14 new senses
  were first left unslotted; Matthew's mid-turn correction ("unconstrained affixes can
  apply "anywhere" and create parser slowdowns") made slots required and added the audit
  (D-S8-08). `asserted-by-Matthew`, `domain-ruling`. Not shown to have fixed *yake*: its
  09-20 zero was staleness, and on 09-23 it parsed through `y- (pro.conc.nc4)`, a sense
  that predates the split (C-S8-07). Of its 3 analyses one is a spurious verb reading, and
  no `pro.conc.nc9` analysis appears, cause unexamined (L-S8-07).
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
  Matthew's request (L-S9-01, D-S9-03). The diagnosis began from Matthew's hypothesis that
  "words "found whole" in the dictionary don't get parsed" (D-S9-07), refined to "required
  prefix slot"; he then **explicitly chose** the move ("option 1, make it so") over making
  PossConcord optional (C-S9-06). His "could wewe be w- and ewe?" was rejected on paradigm
  evidence (nami, nawe, naye; D-S9-08). `asserted-by-Matthew`, `parse-verified`
  (`parse_diff` fixed 3, broken 0).
- **Invariant numerals:** 14 Arabic-origin numerals (saba, tisa, kumi, ishirini ... mia)
  in a top-level `Invariant Numeral` POS with no template; Bantu numerals keep concord
  (L-S9-03). `AI-proposed-accepted`, `parse-verified`.
- **Possessives:** compositional, concord + -angu/-ako/-ake/-etu/-enu/-ao. The whole-word
  possessive and demonstrative shadows were set `DoNotUseForParsing` once a >=2-morpheme
  analysis was attested (20 on 09-13, the last 4 possessives on 09-20; D-S7-04, D-S8-12).
  **They were never suppressed**: the flag is a no-op (section 6). Matthew doubted it at
  the time ("I'm not sure exclude-from-parsing has an effect" / "in the UI, only
  "isAbstract" is surfaced"); the agent retracted its claim and offered a revert, which
  was never answered (D-S8-12).
- **Suppletive pronouns:** kept whole ("No parsing benefit").
- **Reduplication:** `[...]` affix (D-S2-02); Matthew confirmed `[...]` is the correct
  full-reduplication syntax (V-S6-04). HermitCrab compiles `[...]` on an ordinary
  `MoAffixAllomorph` into an affix-process allomorph at load time (`HCLoader.cs`
  1446-1472, C-S6-04). On 09-13 RDP became a derivational Verb -> Verb MSA, out of every
  template slot (*kutangatanga*; S7). Non-verbal reduplication (*mbalimbali*) has no path.
  Still `parse-unverified`. **Check:** the S2 record says the form is `IsAbstract=True`;
  HermitCrab drops abstract affix forms (`IsValidRuleForm`, S10 transcript section 0), so
  if that flag is really set the affix never reaches the parser.
- **Wastebasket POS (09-13):** new POS Interrogative and Copula; Particle items moved to
  Adverb, Interrogative, Copula, Interjection (census: Particle 70 -> 33, Adverb 8 -> 20,
  Interrogative 0 -> 12, Copula 0 -> 11, Interjection 0 -> 3; *mbali* -> Adverb); *karibu*
  -> Verb (plus an Adverb entry on 09-24), *miongoni* -> Preposition (D-S7-04). Raised by
  Matthew ("mbali is a 'particle', maybe that's not right", D-S6-11); applied by a write
  agent under his "use your knowledge of swahili to judge (and fix)" (D-S7-13).
  `AI-applied` per item.

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
- **VI4 (09-12):** Matthew chose the post-final relative design by multiple choice, but
  the AI built it with `TAM2` and `Obj` both required, not the `TAM` + `Obj(opt)` of the
  preview he approved, which is why VI4 "licensed zero analyses" (D-S6-03, C-S6-03).
- **09-13 changes:** VI4 rewired at 00:16 to `[Neg1, Subj, Neg2, TAM, Obj2]` with RelSuf
  obligatory; `Obj2` cloned from Obj and shared by the 14 OM MSAs (L-S7-02). Plural
  imperative `(Obj2)-root-(FV)-ni`. Infinitive: ku- as a second, verbal MSA on the cl.15
  `ku-1` (`ku-3` 'subject cl.15' had 39 uses against `ku-1`'s 3; D-S6-10), Inf
  obligatory, FV optional for Arabic-loan stems, NegInf `to-` after Inf (*kutosema*,
  order confirmed by Matthew). At 01:36, answering Matthew's "make it so", Subj2 was made
  obligatory and VI1 moved TAM -> TAM2, so that TAM stays optional for tenseless
  relatives (*asomaye*).
- **The same day's template changes (C-S7-02, updated by transcript):**
  - 01:36-01:42, Matthew-driven and **checked in his FLEx parser within minutes**: he
    asked "do we need more templates for non-finite verbs?", and a `Verb imperative
    singular` template was built (the verb subagent had declined it for lack of an anchor,
    L-S7-03). It first had `[Obj2]`, which produced a wrong *ku-w-a* reading in his next
    screenshot; Obj2 was removed ("a singular imperative with an object marker takes the
    subjunctive -e").
  - 20:56, a blind evening session: TAM2 made optional ("husema / sisemi have no TAM
    filler"), against the verb agent's "DO NOT change the Optional flag". The same session
    called inflection4's documented "RelSuf obligatory" anchor "almost certainly not
    intended". It read no template Description. Under README 4.13 this should have been a
    separate template. **Open** (Q-45).
- 09-25: Verb owns 8 templates (VI1-VI4, imperative plural, ...; V-S10-08).
- **Subjunctive without an object marker -- not a gap on 09-12, closed 09-13.** On 09-12
  *twende, aone, waruke, tufanye* parsed, and 52 of 60 FVsubj analyses had no Obj (the -e
  FV sat in VI1's optional FV slot). Once VI1 required TAM2 (01:36) that path closed, and a
  `Verb subjunctive` template was built at 01:42 (L-S7-18).
- **Negation and habitual (09-13):** habitual hu- is a Subj/TAM portmanteau in Subj;
  negative portmanteaus si- (1sg), ha- (3sg cl.1), hu- (2sg) in Subj; Neg2 si- is the
  subjunctive negative; `-i` is the negative non-past FV, negative past keeps `-a`
  (*sikusema*; L-S7-09). Proposed by the AI, **approved by Matthew** ("portmanteau is a
  valid analysis. Go for it", 20:53); Subj/Subj2 went from 14 to 18 members. Flagged and
  left unfixed the same evening (L-S7-15): Arabic-origin stems do not take `-i`
  (*hasamehe, harudi*); hu- is now ambiguous (habitual vs NEG.2SG); OM + imperative needs
  `-e` (*isemeni*); `-cha-` is the cl.7 connective, not a relative marker.
- **1sg `na-` (09-25):** Matthew approved ("Apply it (Recommended)") an `a-` "present
  (general)" TAM prefix plus `ni-1` `n / _ a` (*nawaambia* = n-a-wa-ambi-a; *najua,
  nataka, nasema* parse too). An earlier run had proposed a ni+na contraction instead
  (D-S10-13, L-S10-06). Which analysis is right is open.
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
- **Origin:** Matthew's design, 09-13 01:44-01:49, prompted by a *kuwa* over-parse in his
  screenshot: "intransitive verbs can be a subcategory and have their own constraints",
  "once a subcategory's template is satisfied, it can take morphology from the parent",
  "or derivational affixes can make words jump categories" (D-S7-14). The concrete tree,
  the asymmetric default and the classification were the AI's.
- **The conversion (V-S7-01, L-S7-05, D-S7-06):** a staged programme, **parse-verified
  throughout** with in-process HermitCrab (V-S7-11; the logs kept none of it).
  1. Experiments on throwaway objects (D-S7-05): subcategory template inheritance
     **holds** (output byte-identical); `MoDerivAffMsa.FromPartOfSpeech` **is enforced**
     and subsumption-aware (From = ZZTest / Noun / Verb gave 4 / 3 / 4 analyses); a
     two-level inheritance and subsumption check passed. Subsumption runs child -> parent
     only, so a stem marked plain `Verb` is not subsumed by `Transitive` (L-S7-12).
  2. Passive-only prototype (W3): *kuwa* 3 -> 2 analyses, but the 605 unmarked verbs
     silently lost their passives, and all 8 ordering pairs flipped, because converting
     one extension alone inverts the order. Matthew chose "Revert W3, keep W1+W2" and
     "Stop here, write up findings" (09:25, D-S7-11); the revert matched baseline on all 30
     checks.
  3. On "make a plan and resolve it fully" (11:26): the gloss was the only evidence
     channel (0 examples, 0 definitions). 43 verbs were pre-assigned from (tr)/(intr); 604
     were classified by LLM batches with a **default of Transitive**, Intransitive only on
     positive evidence; an adversarial reviewer upheld 139 and overturned 19 of 158
     Intransitive calls. Final **508 vt / 139 vi**, no human review (D-S7-12). Repointed
     in 5 batches against a 24-form diff (29 analyses before and after).
  4. Atomic conversion at 12:05: POS tree **Verb > Underived > {Transitive,
     Intransitive}** and **Verb > Detransitive**. Causative and applicative are
     `MoDerivAffMsa` Underived -> Transitive; passive, reciprocal, stative and statal
     Transitive -> Detransitive. Order comes from subsumption alone (strata 0, production
     restrictions 0; L-S7-10). **1,054 forms before/after: 1,020 unchanged, 34 lost, 0
     gained** (analyses 1,270 -> 1,232). 26 forms (*alikuwa, amekuwa* ...) each lost only
     the spurious *ku-u-a* reading; partial losses *zamani* 3 -> 2, *zikakamilika* 4 -> 3;
     the negative-past `-i` was unharmed.
  5. The empty Caus/Appl/Recip/Pass/Stat/Statal/Redup slots were removed from all verb
     templates at 14:58.
  - **Left open on 09-13 (L-S7-11):** reducer stacking is now blocked (*kuvunjanewa*
    recip+pass, *kuvunjewika* pass+stat, 1 -> 0); put to Matthew, unanswered. Caus/appl
    order is unconstrained (*kuvunjishia* and *kuvunjiisha* both parse).
- **Grades (09-12, `AI-applied`):** applicative `-i-`/`-e-`, causative `-ish-`/`-esh-`,
  statal `-lik-`/`-lek-` by mid-vowel harmony; stative `-ik-`; passive `-w-`. The
  passive's `ew / C_` environment **pre-existed** the 09-12 normalisation, which only
  swapped the lexeme (D-S6-06). It puts the longer passive `-ew-` after
  **consonant**-final roots; standard
  Swahili has plain `-w-` after C and `-iw-`/`-ew-`/`-liw-`/`-lew-` after vowel-final
  roots. **Check.** The 09-13 probe set of "must survive" passives (*kuvunjewa,
  kukatewa, kuchaguwa*) is likely non-words (C-S7-07).
- **Evidence it works:** passive and stative surface as affixes in 09-24/25 parses
  (*walipewa* = wa+li+p+ew+a; V-S10-05). Evidence of over-generation: *wanawake*
  mis-parsed as wa+nawa+k(stative)+e; 09-13 STEP6 candidates *kuvunjishia,
  kuvunjiisha*.
- **Relapses (P10):** applicative and passive shapes of *zaa* re-added as stem
  allomorphs 3.5 h after the conversion (*zalia, zaliwa*; C-S7-06), then on 09-25 split
  into separate Transitive stems rather than decomposed (L-S10-04). The split was **never
  put to Matthew**: his approval that hour covered only the `a-`/`n` question, and it went
  through as a "lexicon-only" fix. The agents' own linguist spec, written in the same chat,
  says "`zalia` is `za-li-a`, not an allomorph of `-zaa`", and the agent itself noted
  *zaliwa* is probably Intransitive (C-S10-03). Lexicalized or not is undecided (Q-46).
- **Still unparsed at 09-30:** a long-tail sample with passives (*walifanywa,
  amependezwa*), applicatives (*amekikalia*), causative *-esha* (*hukomesha*), reflexive
  ji-, relative -o-, -po-/-ka-po- relatives and subjunctive *mwondoe* (S11, from the
  unidentified 09-30 client). *(Status 2026-10-09: the per-analysis morphs, glosses and
  entry GUIDs of any run have been in `flextools_parse_log section=results` since 09-22,
  and `section=trace` gives a rejection summary; the in-band `try_word` response is still
  counts only, T-01/T-02.)* This is the best real-corpus test set for the extensions,
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

## 6. Suppression with `DoNotUseForParsing` -- a no-op, now blocked

The project used `DoNotUseForParsing=True` to keep entries listed but out of the parser:

- 09-13: `zero-5` (cl.16 null prefix; V-S7-02), the duplicate `*ote2` (L-S7-04), 20
  whole-word possessive/demonstrative shadows and 5 losing homographs, each only after a
  >=2-morpheme analysis was attested (D-S7-04).
- 09-20: four more whole-word possessives; 33 entries carried the flag in all (D-S8-12).

**None of this suppressed anything.** On 09-25 Matthew had subagents check the FieldWorks
source (S10 transcript section 0, D-S10-14):
- HermitCrab loops over every entry without reading the flag, and drops a form only when
  it is `IsAbstract` or empty (`HCLoader.cs` :256, :543, :585; test `AbstractForm()`).
  XAmple's XSLT filters only on `@IsAbstract`. Outside the model the flag appears only in
  LIFT import/export and LinguaLinks import, and **not in the FLEx UI**.
- So every 09-13 and 09-20 "suppression" was a no-op. This explains V-S9-03 (cl.16 null
  prefix analyses on 09-24) and settles C-S8-07's "effect never shown". Matthew had
  suspected it on 09-20 (D-S8-12).

**What replaces it:** `IsAbstract` on the entry's **forms**: the lexeme form and every
allomorph (`LexemeFormOA` + each `AlternateFormsOS`; `ILexEntry` has no `IsAbstract`).
An entry drops out only when all its forms are abstract. Caveat: `IMoAffixProcess` forms
return before the `IsAbstract` test in HermitCrab (`HCLoader.cs` :538-540).

**Matthew's decisions (09-25):** treat the flag as deprecated and redirect to `IsAbstract`
(he did not want the MCP to use the field again), also in the LibLCM index. His position:
`IsAbstract` is being "abused" for hiding, and the old field may be revived upstream; he
opened Jira LT-22810. *Status 2026-10-09: done. FlexToolsMCP 2.13.0 (PR #259) refuses the
member at preflight (`deprecated_member`, even in read-only runs), suggests the forms for
`entry.IsAbstract`, ships the recipe `hide-entry-from-parser`, and runs a weekly upstream
watch on LT-22810. flexicon has `Allomorph.Get/SetIsAbstract` (#546).*

**Still open:** the 33 flagged entries are unmigrated. Moving them to `IsAbstract` changes
what the parser produces, so each needs a `parse_diff`; asked three times on 09-25,
unanswered (Q-43). Hiding forms this way also overlaps the soft-delete convention in
[flex-data-conventions](../conventions/flex-data-conventions.md).

## 7. Lexicon defects to check (end of logs, 09-30)

- **Junk entries (confirmed):** 9 bare entries `malaka, el, kumu, gizo, is, hara, en,
  ghadha, bu`, committed 09-30 19:54:10 local, each a `stem` with one empty sense (no
  gloss, no MSA) (C-S11-05). `fu` (the Stage 1 adjective root -fu), `hu, zi, ma, a`
  pre-existed. They came from the unidentified 09-30 client (not Claude Code), which first
  **fabricated** syllable splits (*el-fu, is-hara*) that no tool had returned, then created
  the "missing morphemes" to match (C-S11-08). The script raised, but the runner's
  `finally` closes (saves) the project, so everything written before the raise committed;
  the error response also dropped the script's messages, so it looked like a no-op
  (T-S11-10). Not yet sent by Send/Receive; pre-junk backup `20260930T200325Z`. Delete the
  9 GUIDs (S11 transcript). *Status 2026-10-09: #347 keeps report messages on a failed
  run; commit-on-error is unchanged. The recipe `ensure-morpheme-entries` (PR #337) was
  modelled on that run and needs review, and local recipe `local-be769c1f63ae` still
  holds the junk script (T-S11-11).*
- *panga* mis-tagged loc. 16 (D-S8-09); the 158 featureless noun stems (L-S10-03).
- *binti* changed 2/1 -> NC 1a and its old features reused for *israeli*, unreviewed
  (S9 conflict 7). *Musa*'s entry was added by Matthew in FLEx, not by the agent
  (L-S9-04).
- *nami* parses only as a whole stem; the na- + short-pronoun series (*nami, nawe, naye,
  nasi, nanyi, nao*) is listed, not modelled (L-S8-08). *wengi* did parse by 09-24 23:06,
  only unfiled (V-S9-09).
- 09-30 real defects (L-S11-04): *mamlaka* has a spurious verb parse (m-a-m-la-k-a);
  *maagizo* has **no** ma- + agizo analysis, all four are spurious m+a splits (so V-S11-01,
  "class-6 ma- confirmed", is refuted). *waovu* parses, but as a verb, for lack of an
  adjective stem `-ovu` (L-S9-12). The noun *jiwe* has an allomorph *we* with a Pronoun
  analysis (L-S9-11).
- **The 09-25 programme stopped after Stage 1.** Stage 1 added 71 entries; 226 of 227
  tested words parse, nothing filed. Its regressions: *vitani* gains a false 'linen'
  reading, *wazazi* no longer parses, invariable adjectives still take concords (*mbora*),
  *Mayahudi* parses through the cl.2 ma- prefix, a stray 'be' sense on wa- gives junk
  readings (L-S10-08). Matthew had approved all 11 Stage 2 options (D-S10-16); the
  "filing NOT authorized" brief was the orchestrator's prompt to its subagent, not his
  words (D-S10-04). The Stage 2 baselines died at word 173 twice and the agent stopped at
  23:32; Stage 2 never finished, and Stages 3-5 and the filing never ran (D-S10-05,
  V-S11-04).

## 8. Merge seam

This file **does not merge** with the Malayalam file; it sits alongside it. Content
that turns out to be language-neutral has been promoted to
[flex-modeling-decisions](flex-modeling-decisions.md) (rows 25-31 from S1-S5, and the
rows added from S6-S11) and to the stage files' "Second-Operator Evidence" sections.
Both machines' Swahili logs are now ingested (S1-S11, to 09-30), and S6-S11 are checked
against their transcripts. The project itself has
moved on since; for anything newer, read the live project, not this file.
