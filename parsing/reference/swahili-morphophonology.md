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
| `domain-ruling` | decided by a `/lex-domain` review pass (numbered rulings D13, D18, ...) |
| `source-attested` | supported by an outside lexical source (kaikki, wold) under the licence policy |
| `parse-unverified` | built but never confirmed by a parse in the logs |

Source shards S1-S5 ([evidence index](../evidence/directive-index.md)). **Partial:**
more Swahili work is in logs on another machine. Counts are as of the op cited; the
live project has moved on since.

---

## 1. Phonology

- **Inventory:** 31 phonemes, each with lower- and upper-case graphemes, IPA and a
  description, built from one data table (D-S1-04). Default /x/ and a duplicate /ŋ/
  were deleted. Upper-case graphemes handle sentence-initial capitals (D-S5-02).
  `asserted-by-Matthew`.
- **Features:** the whole FLEx phonological-feature catalog was imported, plus a custom
  `archi` (+/-) (D-S1-02). In 2026-09 the set was pruned: features that are "-" for every
  phoneme were removed, then `dr` and `labio-dental` after an exhaustive search
  confirmed every phoneme stays distinct (D-S3-09). `AI-proposed-accepted`.
- **Archiphoneme `N̲`** (N + U+0332): a nasal with no place of its own, `[+archi]`
  (D-S1-03). `parse-unverified` -- the rule's output class was changed late and not
  tested (C-S1-08).
- **Natural classes:** 18 feature-based classes, including `[-archi]` surface classes
  and `Vnh = [-high, +syl]` (justified by hii, hivyo, mwana, kwenda; D-S2-03).
- **Rules** (all anchored on the morpheme boundary "+" after the S2 rewrite):

| Rule | Statement | Status |
|---|---|---|
| Nasal place assimilation | `N̲ -> [alpha place] / _ + C[alpha place]` | `AI-proposed-accepted`, `parse-unverified` |
| Vowel coalescence | `a + i -> e`, `a + u -> o` | `AI-proposed-accepted` |
| Glide formation | `i -> y`, `u -> w` / `_ + Vnh` | `AI-proposed-accepted` |

## 2. Noun classes

- **Model:** agreement features, not inflection classes
  ([row 25](flex-modeling-decisions.md)). Three closed features hold the class:
  singular class, plural class, and a third, BantuMany, originally for non-count
  classes. They are catalog-sourced since 2026-06 (`fBantuSg/Pl/Many`) and nested under
  `noun agreement` (D-S3-01).
- **What each entry carries:**
  - A noun stem's MSA carries its singular class + paired plural class (e.g. 9/10),
    with `NA` in every unused feature (D-S1-06).
  - Class prefixes carry matching values in an obligatory **ClassPrefix** slot.
  - Null prefixes exist for cl. 5, 9, 10, 1a and 16 (D-S2-01).
- **BantuMany relocation (2026-09-06):**
  - Null prefixes sat on BantuMany while the stems sat on SG/Pl. The features never
    overlapped, so the null prefixes over-generated (L-S4-01).
  - 77 BantuMany values were moved onto BantuSG/BantuPl, with 10 class corrections. 11
    rows were held with reasons (D-S4-05, D-S4-10). Example: "'umilele' not a word".
  - `domain-ruling` (three independent passes).
- **Class 16 null prefix:** questioned as having no legitimate stem (L-S4-01). Its fate
  is not recorded (Q-39).
- **Possible defect, never checked:** a class-9 prefix with BantuPl=NA may clash with a
  9/10 stem carrying BantuPl=10 (S1, inferred). See Q-38.
- **Noun-class assignment, rules of evidence** (D-S3-05, `asserted-by-Matthew`):
  1. the prefix test (what the parser enforces);
  2. kaikki / wold;
  3. concord evidence.
  Worked example: `afisa` -> 5/6 from the attested plural `maafisa`. Undecidable cases
  go in with a `class-negotiable` flag. Never default to 9/10: C-S1-04 shows the cost.
- **Lexical convention:** the lexeme form is the **bound stem** with the prefix
  stripped; the citation form is the full singular word (D-S3-03, L-S3-02). The
  August standard bucketed 832 of 1,024 nouns as parse-ready.

## 3. Concord and closed classes

| Series | Category | How built | Evidence |
|---|---|---|---|
| Adjective Concord | adj | S1 template work | S1 |
| ConnConcord (connective "of") | conn | concord prefix + `-a` stem, own template | D-S2-04 |
| PossConcord | pro-form | deep copy of ConnConcord feature structures | D-S4-06 |
| NumConcord | num | deep copy of Concord feature structures | D-S4-06 |
| Quantifier (`-ote`) | new POS **Quantifier** | reuses the 9 ConnConcord MSAs | D-S5-05 (ruling D13) |

- **Demonstratives:** h- + concord + deictic suffix, with their own template; 22
  whole-word entries retired (D-S2-04).
- **Suppletive pronouns:** kept whole ("No parsing benefit").
- **Reduplication:** abstract `[...]` suffix in a Redup slot (D-S2-02).
  `parse-unverified`.

## 4. Verbs

- **Template (main):** slots include Subj, TAM, Rel, Obj and FV around the stem. The
  logs do not record the slot order, so take it from the live template. Two
  refinements (L-S5-02):
  - **TAM2**: a required clone of TAM, swapped into the template with an object marker
    ("Verb inflection2").
  - **Subjunctive template** ("Verb inflection3"): no TAM slot, plus a required
    **FVsubj** slot holding `-e`.
- **Inflection classes** (D-S5-04), from the citation form:
  - **FVt** (takes the final vowel): 563 stems, where citation = `ku` + stem + vowel.
  - **Inv** (invariant, e.g. loans): 76 stems, where citation = `ku` + stem.
  - Anomalies go to a human. As of 09-07, the final-vowel allomorphs were not yet
    restricted to these classes.
- **Stems:** roots without the final vowel. Root+FV duplicates were disabled, then
  deleted; root+extension forms were held as separate entries (L-S4-02).
- **`ku-`:** two homographs by function -- infinitive/augment in TAM/TAM2, and negative
  past (L-S5-03, `domain-ruling`).
- **Open, and the largest gap against P10** (C-S2-03, Q-40):
  - The extensions (applicative, causative, passive, stative, reciprocal) and the
    subjunctive were at one point *listed as stems* (ambie, chukuliwa, mpelekee...).
  - Before that, they had been put in inflectional slots (C-S1-06).
  - The August plan's R4 (derivation enters with derivational MSAs) points the right
    way, but no log shows it applied to verb extensions.

## 5. Lexical-source and licence policy

From the phase plans (D-S3-05):

| Source | Licence | Allowed use |
|---|---|---|
| kaikki.org (Wiktextract) | CC BY-SA | facts (class, plural) only; glosses re-authored |
| lexibank/wold | CC-BY | importable with attribution; cross-check |
| TUKI dictionaries | restricted | validation only |
| SALAMA | restricted | treated as unreachable in the plan |

## 6. Merge seam

This file **does not merge** with the Malayalam file; it sits alongside it. Content
that turns out to be language-neutral has already been promoted to
[flex-modeling-decisions](flex-modeling-decisions.md) rows 25-31 and to the stage files'
"Second-Operator Evidence" sections. When the remaining Swahili logs are ingested,
update the counts and statuses here first.
