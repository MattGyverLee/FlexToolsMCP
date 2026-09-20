# Allomorph Sets and Environment Strings

[Back to README](../README.md) | Used by [Stage 07](../stages/07-allomorphy-modeling.md)

The allomorph inventories this project arrived at, and the environment strings used to
condition them, as written in FLEx.

**Unverified.** These are the analyses the project converged on because they produced
the intended parses. Ron does not speak Malayalam; see the framing in
[`malayalam-morphophonology.md`](malayalam-morphophonology.md). Status values are as
defined there.

Many surface strings are not recoverable from the logs (the log format persists source
code and message counts but not `report.Info` text -- M6 §6, M2 §7). Where a shard
recorded only a schematic, the schematic is what appears here.

---

## 1. Environment string syntax as used

| Form | Meaning | Example from the corpus |
|---|---|---|
| `/ [CLASS] _` | after a member of CLASS | `/ [NyF] _`, `/ [PlF] _`, `/ [Vs] _`, `/ [Syl] _` |
| `/ [C1][C2] _` | after a two-segment sequence | `/ [Vir][PsF] _` (the "geminate environment") |
| `/ _ [CLASS]` | before a member of CLASS | `/ _ [PACs]` |
| `/ _ <literal>` | before a literal string | `/ _ u#`, `/ _ il` |
| `#` | word / clitic boundary | `/ _ u#` (before word-final -u) |
| `+` | word-internal morpheme boundary | used in phonological rule contexts |

Conventions:

- **Writing system.** If the environment contains a vernacular character and is a
  one-off (not worth a natural class), the **entire** string must be authored in the
  vernacular writing system, or FLEx renders boxes (D-M3-05).
- **Set the string representation directly**, not just the name (M3 §6); the corpus hit
  a runtime error trying to set it as a multi-alternative string when it is a single
  string (C-M5-04).
- **Reuse the existing environment object** with the same string rather than creating a
  duplicate (D-M7-05).
- **Check the string is not empty** before believing an allomorph is conditioned: 13
  allomorphs flagged as environment-bearing carried empty strings (L-M8-04).
- **The lexeme form is the elsewhere case**, ordered last under the negation of every
  environment above it (L-M3-13). Constrain the alternates; leave the elsewhere form as
  the lexeme form -- unless it over-generates, in which case constrain it too
  (L-M3-14).

---

## 2. Nominal case suffixes -- affix-process subrule sets

Each case suffix is an ordered list of affix-process subrules. A subrule is
`(trigger natural class, keep the trigger segment?, inserted string)`. **Whether the
trigger is kept or replaced must be decided per subrule and tested against a concrete
surface form** -- the genitive got this wrong once (C-M2-05).

Recorded at 2026-09-11 14:33 (M2 op 11) and corrected at 14:36 (M2 op 13).

| Gloss | Trigger class | Keep? | Inserted | Status |
|---|---|---|---|---|
| **PL** | Chillu n | replace | -r | `AI-proposed-accepted` (L-M2-01) |
| | Anusvara | replace | -ngngal | |
| | Virama | replace | -ukal | |
| **ACC** | Vowel sign | keep | -ye | `AI-proposed-accepted` (L-M2-02) |
| | Syllabic | keep | -ye | |
| **GEN** | Chillu n | replace | -nte | `AI-proposed-accepted`, `revised` (L-M2-03) |
| | Virama | **replace** (was wrongly "keep") | conjunct directly | |
| | Vowel sign | keep | -yute | |
| | Syllabic | keep | -yute | |
| **DAT** | Chillu n | replace | -n | `AI-proposed-accepted` (L-M2-04) |
| | Chillu (coronal) | keep | -kk | |
| | Vowel sign | keep | -kk | |
| | Syllabic | keep | -ykk | |
| **INS** | Vowel sign | keep | -yaal | `AI-proposed-accepted` (L-M2-05) |
| | Syllabic | keep | -yaal | |
| **SOC** | Vowel sign | keep | -yoot | `AI-proposed-accepted` (L-M2-05) |
| | Syllabic | keep | -yoot | |
| **LOC** | Vowel sign | keep | -yil | `AI-proposed-accepted` (L-M2-05) |
| | Syllabic | keep | -yil | |

Notes:

- The demonstrative case affixes have the **same forms** as the noun ones, so an
  existence check by form alone cannot tell them apart (L-M2-10).
- LOC was the only case suffix that never needed an affix-process rule, and was
  consequently the only one parsing at one point -- which is how the
  plain-alternates-shadow-process-rules problem was found (C-M1-06).
- The genitive **elsewhere** form was later constrained with `/ [PlF] _` to stop it
  over-generating onto non-plural stems (L-M3-14).

---

## 3. Noun oblique / augment allomorphs

| Pattern | Environment | Status | Evidence |
|---|---|---|---|
| virama-final -am stems -> -att oblique, plus a further -attin oblique | (unconditioned alternates at the time) | `AI-proposed-accepted` | L-M2-08 |
| other consonant-final stems -> -in oblique | | `AI-proposed-accepted` | L-M2-08 |
| stem allomorph used before the post-augment case onsets | `/ _ [PACs]` | `AI-proposed-accepted` | L-M3-07, L-M6-01 |
| stem allomorph used before vowel-initial case suffixes | `/ _ [CsOn]` | `AI-proposed-accepted` | L-M3-08 |
| anusvara-final nouns: oblique augment, three shapes (bare, dative-conditioned, chillu-final) | implemented as **affix-process allomorphs of an inflectional augment affix** in the Number slot, stripping the anusvara -- replacing 92 variant entries | `asserted-by-Ron` | L-M7-01 |

Attested example forms recorded in the shards: maram -> maratt, marattin;
pustakam -> pustakatt, pustakattin; puuv -> puuvin; maav -> maavin;
raajaav -> raajaavin; at -> atin; it -> itin (L-M2-08, L-M3-07).

**The oblique representation question is unresolved** -- see
[README 4.5](../README.md#45-oblique-stems-allomorph-vs-variant-entry-unresolved-within-the-corpus)
and [open-questions.md](../open-questions.md) Q-04.

---

## 4. Verb suffix allomorphs

| Suffix family | Restriction / environment | Status | Evidence |
|---|---|---|---|
| PAST -u (ccu class) | `/ [Vir][PsF] _`, restricted to inflection class `ccu`, then **widened to `ccu` + `ttu`** | `asserted-by-Ron`, arrived at in 3 iterations | L-M5-09, D-M5-15 |
| PAST -u (nnu class) | a **dedicated literal environment** (virama + na immediately before the suffix), created rather than broadening shared PsF | `asserted-by-Ron` | L-M5-09, D-M5-14 |
| PAST -u (further stem-final subtype) | yet another dedicated environment; two verbs moved into `nnu` | `asserted-by-Ron` | L-M5-09 |
| nya-initial PAST / COND / CONC / NEG.PAST | `/ [NyF] _` ("after a nya-past stem, never after a derived stem"), **plus** the existing inflection-class restriction | `AI-proposed-accepted` | L-M3-09 |
| NEG.PAST -illa | `/ [Vir][PsF] _` (the geminate environment), set on the alternate, not the lexeme form; simultaneously the PAST entry's lexeme form and its -i alternate were **swapped** so the elsewhere case is the lexeme form again | `AI-proposed-accepted` | L-M3-13 |
| NEG.PAST split by class | nya-initial restricted to the nya class; -i-initial restricted to the others | `AI-proposed-accepted` | L-M3-12 |
| COND / CONC | class restriction **replaced** by `/ [CondF] _`, because the class restriction blocked derived stems that inherit the root's class | `asserted-by-Ron` | D-M4-01, L-M4-01 |
| derived past allomorphs of causative / long causative / passive | `/ _ u#` (before word-final -u, the plain past suffix) and `/ _ il` (before the negative past) | `AI-proposed-accepted` | L-M3-15 |
| CVB (converb) | five past inflection classes attached at the **allomorph** level, not the MSA | `asserted-by-Ron` | L-M8-06 |
| NMLZ.M / NMLZ.PL / TEMP.PST | five senses, one per past inflection class, on the derivational MSA; the tense feature structure cleared | `asserted-by-Ron` | L-M8-05 |
| long imperative | **no environment recorded** | `unresolved` | L-M5-10 |
| -ya-final roots -> shortened alternate | environments present but their strings are **empty** | `unresolved` (treated as a non-issue) | L-M8-04 |

**Important:** a right-context environment on a *stem* allomorph pre-empts the lexeme
form even when the alternate's string does not match the surface, and cannot
distinguish homophonous suffixes -- which is why the past-stem alternation moved to a
stem name and then to variant entries (L-M4-03, L-M4-04, D-M8-05). See
[`flex-modeling-decisions.md`](flex-modeling-decisions.md) rows 8 and 9.

---

## 5. Clitic and enclitic allomorphs

| Set | Environment | Status | Evidence |
|---|---|---|---|
| u-initial alternates for 8 enclitic postpositions ("for the sake of", "together with", "before", "after", "below", "on top of", "outside", "inside") after a virama-final host | initially stored alternates; later **replaced** by affix-process insert-phones rules; later still, alternates derivable by the global rule were **deleted** | `AI-proposed-accepted`, twice `revised` | L-M2-09, L-M3-03, L-M3-05 |
| "to, into" after a chillu-l-final host | Chillu l | `AI-proposed-accepted` | L-M3-03 |
| y-glide allomorphs for 7 vowel-initial enclitics (copula, two aspectual/linking forms, negative, emphatic, relative, complementizer) | `/ [Vs] _` and `/ [Syl] _` | `AI-proposed-accepted` | L-M6-08 |
| =um "and", =oo "or", =engkilum "even if" | glide allomorph on `/ [Vs] _`, `/ [Syl] _`; **lexeme form is the attached (matra) spelling**, not the free-standing one | `AI-proposed-accepted` | L-M5-05, L-M5-06 |

Two co-existing spellings of one postposition required **two entries**: two
affix-process rules with the same environment cannot both fire on one entry (L-M3-04).

---

## 6. Inflection-class restrictions (non-phonological conditioning)

Not environments, but they sit alongside them in the same decision and are often the
right answer when an environment is not.

| Restriction | Applied to | Status | Evidence |
|---|---|---|---|
| "Human" noun inflection class | the -r plural allomorph | `asserted-by-Ron`; **necessity unresolved** | D-M1-08, L-M1-05, L-M4-06 |
| Verb classes "Past -i" / "Past -nnyu" (after the causative dimension was split out) | PAST, COND, CONC, NEG.PAST, causative allomorphs | `asserted-by-Ron` | L-M3-10, L-M3-11, L-M3-12 |
| Five past classes ("Past -i", "-ttu", "-nnu", "-ccu", "-nnyu") | past-variant entries' MSAs; the CVB allomorph; five senses each on the NMLZ family | `asserted-by-Ron` | L-M8-01, L-M8-05, L-M8-06 |
| "Plain anusvara" class + a rule feature | scoping one right-hand side of the anusvara phonological rule | `asserted-by-Ron` | L-M7-03 |

---

## 7. Environments recorded and later retired

Worth keeping visible, because retiring an environment is as much a decision as
creating one:

- Two environments retired when the geminate environment replaced them (L-M3-13).
- Phoneme-proxy environments and their classes (NyF, PvF, LcF as proxies) retired when
  verb inflection classes took over that conditioning (M3 op 27).
- The "Enclitic onset" class's environment replaced by four exact per-segment
  environments (L-M7-03).
- Unanchored right-hand sides on three phonological rules deleted for parse-time
  reasons (L-M3-02).
- 25 allomorphs deleted once the global phonological rules derived them (M1 op 35);
  lexeme-form clones and rule-derivable enclitic alternates deleted later (L-M3-05).

Always check the referrer count before deleting an environment or class (M3 §6).

---

## 8. Merge seam

This file is language-specific and does **not** merge. What should be promoted out of
it when Matthew's material arrives:

- The **environment string syntax** table (section 1) is language-neutral; move it to
  [`flex-modeling-decisions.md`](flex-modeling-decisions.md) or a conventions file if
  a second project confirms it.
- The **keep-vs-replace-per-subrule** discipline and the **elsewhere-form** fact are
  already in the decision table; this file only illustrates them.
- Matthew's environments become `reference/<language>-allomorphy-environments.md`.
</content>
</invoke>
