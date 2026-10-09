# Open Questions

[Back to README](README.md)

Unresolved items from the corpus, each with who can resolve it. Referenced by id from
the stage files.

| Audience | Meaning |
|---|---|
| **Ron** | a process/modeling decision only the original operator can explain |
| **Matthew** | likely answered by the second process, to be resolved at merge |
| **Native speaker** | a claim about Malayalam that no one in the corpus could verify |
| **Tooling** | resolved by building something, see [MERGE-NOTES](MERGE-NOTES.md) |

---

## Process and method

**Q-01. Should the project pre-state be a committed artifact per session?**
The corpus never persisted a grammar snapshot and paid for it repeatedly -- most
visibly in the unexplained slot-count/entry-count drift (C-M2-06) that was flagged and
never resolved. *Audience: Ron, Tooling.*
Raised in [Stage 01](stages/01-project-survey-and-inventory.md).

**Q-02. Is a `[SHARED]` non-master-peer write safe?**
The corpus always proceeded when another process held the project open. Whether that
is safe, and what the failure mode would look like, is not established.
*Audience: Ron, Tooling.* [Stage 01](stages/01-project-survey-and-inventory.md).

**Q-07. Is four the right threshold for making a natural class?**
D-M3-05 says "each set of 4" about one specific situation; the spec generalized it.
*Audience: Ron, Matthew.* [Stage 04](stages/04-natural-classes.md),
[reference/natural-classes](reference/natural-classes.md).

**Q-21. How to decide exhaustive vs representative paradigm sampling?**
The corpus used both and never stated a rule beyond "the cross-product is too big".
*Audience: Ron, Matthew.* [Stage 10](stages/10-paradigm-text-construction.md).

**Q-22. No coverage metric was ever computed.** Coverage of allomorph-triggering
environments was asserted by construction, never measured.
*Audience: Tooling.* [Stage 10](stages/10-paradigm-text-construction.md).

**Q-23. What is the acceptance threshold?**
"Iterate to see how good you can get it" (D-M6-01) is the only stated guidance. No
target parse rate for either the paradigm texts or the real corpus.
*Audience: Ron, Matthew.* [Stage 11](stages/11-parse-and-repair-loop.md),
[Stage 12](stages/12-real-corpus-stress-test.md).

**Q-18. What is the acceptable parse-time budget?**
Ron reacted to 9.6s on one word and 4 minutes for 438 words as unacceptable (D-M3-02),
but no target was set. *Audience: Ron.* [Stage 08](stages/08-phonological-rules.md).

**Q-25. Over-generation was never systematically measured**, only reasoned about
(D-M8-05 was found by thinking, not by a report). *Audience: Tooling.*
[Stage 11](stages/11-parse-and-repair-loop.md).

**Q-27. No cadence is stated for when cleanup should run.** It happened opportunistically
at least seven times. *Audience: Ron, Matthew.*
[Stage 13](stages/13-cleanup-and-consolidation.md).

**Q-24. Did the corpus ever reach full parse coverage on any text?**
Not confirmed in the logs; M1, M5 and M8 all end mid-repair (M1 §7, M5 §7, M8 §9).
*Audience: Ron.*

**Q-26. Did deleting the Aesop text (D-M6-01) cost a regression surface that was later
missed?** *Audience: Ron.* [Stage 12](stages/12-real-corpus-stress-test.md).

---

## Modeling

**Q-04. Obliques: allomorph, variant entry, or inflectional augment?**
The largest unresolved modeling question in the corpus. All three were used;
some entries carried two representations simultaneously (L-M6-01); an experiment
converting between them was run and fully reverted with **no stated reason**
(D-M7-07, L-M7-04); and a fourth path -- replacing 92 variant entries with an
inflectional augment affix -- was taken for nouns but explicitly not for pronouns
(L-M7-01, L-M7-05).
*Audience: Ron (why the revert), then Native speaker (is the noun/pronoun split real).*
[README 4.5](README.md#45-oblique-stems-allomorph-vs-variant-entry-unresolved-within-the-corpus),
[Stage 07](stages/07-allomorphy-modeling.md), [Stage 13](stages/13-cleanup-and-consolidation.md).

**Q-05. Was the move from a minimal to a fully specified feature matrix ever validated
against parse behavior**, or was it an a-priori preference? D-M1-05 records the change,
not a measured effect. *Audience: Ron.* [Stage 03](stages/03-phonological-features.md).

**Q-06. Can a project skip phonological features entirely** and use segment-list
natural classes only? *Audience: Matthew.* [Stage 03](stages/03-phonological-features.md).
*Partial answer (S1, S3):* Matthew used features throughout -- catalog import, a full
matrix, feature-based classes, alpha rules. So the second project did not test
skipping them. Still open.

**Q-09. When should a shared parent category (e.g. "Nominal") be introduced** versus
duplicating slots per child category? The corpus's Nominal restructuring was done by
Ron in the GUI with no recorded rationale (D-M5-02).
*Audience: Ron.* [Stage 05](stages/05-categories-and-templates.md).

**Q-12. Should a given POS have a citation form distinct from its bare lexeme form**
(e.g. an infinitive vs a stem)? Raised in the German project and never resolved
(L-G1-03). *Audience: Matthew, Native speaker.*
[Stage 06](stages/06-stem-and-affix-population.md).
*Answered for Swahili (D-S3-03, D-S5-04):* yes. Nouns keep the full singular word as
the citation form over a bound-stem lexeme form. Verbs keep `ku`+stem(+V), and the
difference encodes the inflection class. See
[flex-data-conventions section 13](conventions/flex-data-conventions.md).

**Q-16. No rule-ordering / stratum policy is stated anywhere in the corpus.**
Compound-rule strata were checked once (M6 op 29); phonological rule ordering never
was. *Audience: Ron, Matthew.* [Stage 08](stages/08-phonological-rules.md).

**Q-03. Is there a principled rule for when a decomposable character sequence should be
a single phoneme?** Decided case by case (M1 op 4).
*Audience: Native speaker, Ron.* [Stage 02](stages/02-phoneme-inventory.md).

---

## Malayalam -- for a native speaker

**Q-13. Is the "Human" noun inflection class needed for parsing, and is it real?**
Created in M1 (D-M1-08, L-M1-05), investigated in a dedicated read-only session on
2026-09-14 (D-M4-04), and the answer is **not recoverable from the logs** (L-M4-06,
M4 §7). Also open: if it is needed, does it need to be on other nouns?
*Audience: Native speaker, then Ron.*

**Q-14. Were all the verbs "that need it" converted** to the past-variant architecture?
The bulk pass covered 101 stem-named, environment-free allomorphs out of a 192-entry
inventory; completeness is not confirmed (M8 §7). *Audience: Tooling (auditable), Ron.*

**Q-15. What conditions the long imperative?**
Added as a bare alternate with no environment; unclear whether free variation,
register-conditioned, or environment-conditioned and simply unconstrained (L-M5-10).
*Audience: Native speaker.*

**Q-29. Are the multi-parse ambiguities real?**
Specifically the imperative/past homophony Ron accepted as genuine (L-M3-06) and the
augmented-stem / dative ambiguity (L-M3-07). *Audience: Native speaker.*

**Q-30. Are the five verb conjugation classes the right cut, and are their memberships
right?** The inventory went 3 -> 2 -> 4 -> 5 across the corpus (L-M3-10, L-M3-11,
L-M4-02, L-M8-01). *Audience: Native speaker.*

**Q-31. Which indefinite pronoun forms are transparent compositions and which are
lexicalized?** Ron retired nine and kept five on analytic intuition (L-M5-07). This is
the corpus's richest single piece of morphological reasoning and also its most exposed.
*Audience: Native speaker.*

**Q-32. Are the chillu-vocalization, virama-deletion and enunciative-u statements
phonological, orthographic, or both** -- and does the distinction matter for the
grammar? The corpus does not separate the two levels (L-M1-01, L-M1-02, L-M1-03).
*Audience: Native speaker.*

**Q-33. Do anusvara-final big numerals really inflect as nouns**, or was that a
mechanism-driven convenience (the augment being unreachable from a sibling category)?
(L-M8-02.) *Audience: Native speaker.*

**Q-34. Is the honorific/formal-heavy pronoun inventory a real gap** and what should
fill it? (L-M5-11.) *Audience: Native speaker.*

**Q-35. Are the 13 -ya-final verb roots with vacuous environments** genuinely
unconditioned, or was a conditioning environment lost? Treated as a non-issue and
excluded from conversion (L-M8-04). *Audience: Native speaker, Ron.*

---

## Diagnostics never closed

**Q-08. Was the abandoned "Enclitic onset" natural class deleted or merely orphaned?**
(M7 §7.) *Audience: Tooling (inspect the project).*

**Q-10. Was a Noun+Verb compound rule ever created, and why did the expected compound
not fire?** Investigated via POS checks with no recorded conclusion (M6 §7).
*Audience: Ron, Tooling.* [Stage 05](stages/05-categories-and-templates.md),
[Stage 09](stages/09-compounding-and-clitics.md).

**Q-19. Why does one noun take enclitics and a structurally similar one not?**
The comparison script ran; the diagnosis was never recorded (M6 §7).
*Audience: Ron, Tooling.* [Stage 09](stages/09-compounding-and-clitics.md).

**Q-17. The content of the exhaustive phonological-rule dump is not recoverable**
from the logs (L-M6-10, M6 §7). *Audience: Tooling (re-dump the project).*

**Q-20. The gloss/definition text of the complementizer enclitic** is not visible in
the logs (L-M6-09). *Audience: Tooling (inspect the project).*

**Q-11. The source-of-truth data modules live only in a local scratchpad** and are not
in any log; the *format* is recoverable, the *content* is not (M1 §8, M2 §7).
*Audience: Ron.*

**Q-28. The correct way to extract a writing-system handle from a single-alternative
string** was never resolved; the failing code path was abandoned (C-M3-04, M3 §7).
*Audience: Tooling.*

**Q-36. The exact content of the feature-assignment source files** was never captured
(M1 §7), so the feature matrix is reproducible only from the live project.
*Audience: Ron.*

---

## Second operator (Swahili)

**Status of the questions addressed to Matthew** (shards S1-S11, covering both machines'
Swahili logs, 2026-05-21..09-30):

| Q | Status after the merge |
|---|---|
| Q-02 | **Answered in practice: not safe.** Non-master-peer writes while FieldWorks or another client held the project lost commits to `FP_ConflictingSaveError` (C-S7-01, C-S8-03; 61 shared-peer writes on 09-13, T-S7-03). The recovery that worked: close FLEx, re-apply, verify by read-back after reopen (D-S8-04). Concurrent clients on one project also overwrote each other's template Descriptions (C-S7-01, C-S10-06) |
| Q-06 | Not tested -- features were used throughout (see above) |
| Q-12 | Answered for Swahili (see above) |
| Q-16 | Still open -- no rule-ordering policy appears in the Swahili logs either. Rules were narrowed by left context (L-S7-06) and gated by an exception feature (L-S10-02), never reordered |
| Q-18 | One data point, no budget: about 6 s/word on 09-25, so a 1,783-word regression baseline took hours (D-S10-05). Single `try_word` calls often outran the grace window (T-S10-02) |
| Q-21 | Two data points: one noun-class paradigm text with one unambiguous pair per class (D-S5-08); then on 09-13 **exhaustive** mechanical generation for every template of every inflecting POS, proofread, with structurally invalid forms moved to "No Parse" texts (D-S7-07, D-S7-08). From 09-24 regression sets were a frequency head plus words containing the targeted segments, not paradigms (D-S10-05) |
| Q-22 | Partly: a per-grapheme parse rate was computed on 09-25 (gh 7%, th 17% vs a 66% mean) and found an orthography defect (D-S10-06). Environment coverage was still not measured |
| Q-23 | Still open. Matthew used a *static* threshold instead: 0 entries in the "orphaned" bucket, and a parse-ready count per phase (D-S3-03). The first measured rate is 66% of occurring wordforms on 09-25 (D-S10-06); no target was set |
| Q-25 | Partly: analysis counts were used as the signal (*mwana* 13, *Misri* 10; L-S10-05, V-S10-07), and the "No Parse" texts are a negative test set (D-S7-08). No systematic measurement |
| Q-27 | Cleanup was opportunistic in timing too, but each run was a planned, tiered batch (D-S5-05). S6-S11 add a cleanup trigger: after any failed write, sweep for orphans and partial state (C-S6-01, C-S11-05) |

**Q-37. Does a lexeme form holding the *most-restricted* allomorph, with no elsewhere
form, actually parse?** **Answered -- moot.** Matthew retracted the S1 arrangement on
09-12 ("the default/everywhere form of the affix should be the lexeme", D-S6-04) and 20
entries were swapped to the F1 arrangement, preserving object identity (D-S6-05,
L-S6-02, V-S6-01). On 09-24/09-25 the class prefixes hold the elsewhere form in the
lexeme form and parse (V-S9-04, V-S10-04). The original arrangement was never tested
directly, and no longer exists. [Stage 07](stages/07-allomorphy-modeling.md),
[README 4.11](README.md#411-lexeme-form-as-the-elsewhere-case-f1-vs-most-restricted-form-in-the-lexeme-s1).

**Q-38. Does a class-9 prefix with `BantuPl=NA` unify with a 9/10 stem carrying
`BantuPl=10`?** **Moot -- restated.** By 09-25 the feature system has no `NA` value, and
each null prefix carries one feature (V-S10-02). The logs support exact-value
unification (a 1a stem does not satisfy a class-1 concord, D-S8-11, V-S8-03) and
unify-not-overwrite semantics (L-S7-01), all reasoned rather than parse-tested.
**Restated question:** how should null-prefix over-generation be contained? 9/10 nouns get
one analysis per null prefix (*nyumba* 2), and null prefixes stack (*watu* 5-8, *mwana*
13, *Misri* 10; L-S9-05, V-S10-07, L-S11-03). *Audience: Matthew, Tooling.*
[reference/swahili-morphophonology section 2](reference/swahili-morphophonology.md).

**Q-39. What happened to the class-16 null prefix and the 11 held BantuMany rows?**
**Partly answered.** `zero-5` (cl.16) was set `DoNotUseForParsing` on 09-13, not deleted
(V-S7-02). But on 09-24 stored analyses still used it (`∅ nul.pref.nc16 + watu`,
V-S9-03), so the flag either does not stop HermitCrab or those analyses predate it (see
Q-43). BantuMany had shrunk to 3 senses by 09-20 (V-S8-02), but the feature still has 6
values on 09-25 (V-S10-03). The 11 held rows are not addressed in any log. *Audience:
Matthew, Tooling (inspect the project).*

**Q-40. Are the Swahili verb extensions going to be decomposed?** **Answered: yes, on
09-13.** Causative and applicative became `MoDerivAffMsa` Underived -> Transitive;
passive, reciprocal, stative and statal Transitive -> Detransitive, after all 647 verb
stems were classified; the empty inflectional slots were removed (V-S7-01, L-S7-05,
D-S7-06). Passive and stative surface as affixes in 09-25 parses (V-S10-05).
**Remaining:** the conversion's parse outcome is not logged (S7 kept no tool output);
one root relapsed twice (*zalia, zaliwa*; C-S7-06, C-S10-03 -- see Q-46); and a 09-30
long-tail sample of extended verbs (*walifanywa, amekikalia, hukomesha*) stayed
unparsed with no diagnosis (S11). *Audience: Matthew.*

**Q-41. When should an analysis be approved, and by which agent?** **Partly answered by
practice, still no written policy.** S2 auto-approved by heuristic as Human and
reversed it; S4 rejected with reasons. Then:
- 09-13: a write-mode session again approved heuristic segmentations (C-S7-04, V-S7-06).
- 09-23: 448 human-approved vs 24,796 parser analyses; a delete of 18 incomplete human
  analyses was queued with no recorded go-ahead (D-S8-14, C-S8-06).
- 09-24: **Matthew removed all human approvals** (V-S9-01). From then on analyses are
  parser-filed only, through a two-step preview / confirm (T-S9-04).
- 09-25: an agent self-confirmed a whole-corpus filing ("may delete up to 24,259
  analyses") 21 s after the preview (C-S10-02); that evening Matthew's brief said
  "Filing NOT authorized" (D-S10-04).

Open: is the approval layer gone for good, or reset for a fresh baseline (this changes
README 4.14)? Is filing a human gate separate from write mode? *Audience: Matthew, Ron.*
[Stage 11](stages/11-parse-and-repair-loop.md).

**Q-42. Are AI-drafted free translations and textbook paradigm forms acceptable test
material?** **Still open, sharpened.** D-S4-01 drafted English free translations by
machine, and D-S5-08 took paradigm forms from general knowledge. Since then:
- the 09-13 paradigm texts carry a "generated mechanically" header and rejected forms
  carry a stated reason, which partly meets H6's labelling condition (V-S7-07);
- an AI-invented "must survive" probe set held likely non-words (*kuvunjewa,
  kuchaguwa*; C-S7-07);
- Matthew explicitly sanctioned the AI's "deep knowledge of Swahili" (D-S9-01, D-S10-03),
  and the resulting entries, glosses and classes are not labelled in the project;
- a weaker client invented the corpus words it was diagnosing (C-S11-01).

No native-speaker or attested-corpus check appears in any shard. *Audience: Matthew,
Native speaker.*

**New questions (from S6-S11):**

**Q-43. What replaces `DoNotUseForParsing` for "listed but not parsed"?** The project
suppressed whole-word possessives, a duplicate stem and the cl.16 null prefix with it
(33 entries by 09-20; D-S7-04, D-S8-12, V-S7-02). The flag is deprecated in this repo's
tooling, its effect was never shown (C-S8-07), and analyses using a flagged entry were
still present on 09-24 (V-S9-03). It also overloads the soft-delete convention. Needed:
a supported mechanism, a reparse diff proving it, and a migration of the 33 entries.
*Audience: Matthew, Tooling.* [reference/flex-modeling-decisions section 7](reference/flex-modeling-decisions.md).

**Q-44. How should Swahili glide formation be modelled: a global rule, per-prefix
allomorphs, or an exception feature?** It exists as a rule *and* as stored glide
allomorphs (S6 conflict 4). The rule over-applied to cl.4 `mi-` for four months
(V-S9-07); a disable never persisted (C-S9-02); the 09-25 fix tags three stems with an
exception feature (L-S10-02), which does not scale and puts the restriction on the stem
rather than on the triggering prefix. Matthew's own division of labour (D-S6-07) points
to allomorphs. Stage 2(b) reopened it with no logged outcome. *Audience: Matthew.*
[Stage 08](stages/08-phonological-rules.md).

**Q-45. Separate template, or optional slot, for verb forms with no TAM filler?** On
09-13 TAM2 was made optional so habitual *husema* and negative-present *sisemi* parse,
against the same day's design record ("DO NOT change the Optional flag ... TAM2") and
README 4.13. A singular-imperative template was built after another agent declined it
for lack of an anchor; and the subjunctive without an object marker has no template
(C-S7-02, L-S7-03, S6). *Audience: Matthew.* [Stage 05](stages/05-categories-and-templates.md),
[README 4.13](README.md#413-relax-the-slot-vs-separate-templates).

**Q-46. When is a derived stem lexicalized enough to list rather than decompose?**
*zalia* 'give birth to/for' and *zaliwa* 'be born' were stored first as allomorphs of
*zaa*, then as separate Transitive stems, after the extensions had become derivational
(C-S7-06, L-S10-04, C-S10-03). No criterion was stated. *Audience: Matthew, Native
speaker.*

**Q-47. Are these AI-asserted Swahili forms right?** Each was written into the project
without a logged check:
- the cl.1 object marker's elsewhere form is `mu`, not standard `m` (S6);
- the passive `-ew-` was placed after consonant-final roots (S6; standard Swahili has
  plain `-w-` there);
- *Torati* (Torah) and *Yerusalemu* (a place) carry noun class 1a, copied from a personal
  name (L-S9-04);
- class 13 sits under both BantuSG and BantuPl, chosen per entry (D-S8-10);
- *binti* moved from 2/1 to 1a, its old features reused for *israeli* (S9).

*Audience: Native speaker, then Matthew.*

**Q-48. Is the dotted gloss scheme (`sbj.nc10`, `conn.conc.nc4`) the project's
convention, or should glosses follow Leipzig?** A local-model session rewrote 808
glosses on 09-14 and called the result Leipzig; it is a project-local scheme (D-S8-02).
It also moved category hints such as "(v)" out of glosses (S8 conflict 4) and broke
scripts that looked affixes up by gloss (C-S7-09). *Audience: Matthew.*
[conventions/flex-data-conventions](conventions/flex-data-conventions.md).

**Q-49. What is the live state the logs stop short of?** Cheap to close by inspecting
the project read-only:
- were the bare entries `el, is, en, fu, kumu, gizo, hara, malaka, ghadha, bu` (and
  perhaps `hu, zi, ma, a`) created on 09-30 (C-S11-05)?
- did Stage 2 of 5 (ng' as U+02BC, glide formation, passive, N- assimilation, ch-/vy-)
  land after 09-25 (D-S10-04)?
- is the Quantifier template still inert (fillers owned by Connective, L-S7-04)?
- what did the 09-13 extension conversion and the 09-24 glide sandbox regression
  actually report (T-S7-02, T-S9-08)?

*Audience: Tooling (inspect the project), Matthew.*

---

## Note on what "unresolved" costs

Several of these are cheap to close by simply inspecting the live project
(Q-08, Q-17, Q-20, Q-14). They are open here only because the **log format persists
source code and message counts, not report output** (M6 §6, M2 §7, M8 §6). That is
itself a tooling finding -- see [MERGE-NOTES](MERGE-NOTES.md).
