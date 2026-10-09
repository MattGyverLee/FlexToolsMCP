# Open Questions

[Back to README](README.md)

Unresolved items from the corpus, each with who can resolve it. Referenced by id from
the stage files.

| Audience | Meaning |
|---|---|
| **Ron** | a process/modeling decision only the original operator can explain |
| **Matthew** | likely answered by the second process, to be resolved at merge |
| **Native speaker** | a claim about a target language that no one in the corpus could verify |
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
*Status 2026-10-09: partly cheap now. The `flextools_parse_text` report gives an
`analysis_count_distribution` and flags root-entry disagreement, and `parse_diff`'s
`changed` bucket shows loosening on attested words (FlexToolsMCP 2.13.0). Generating
unattested forms is still open (T-22).*

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

## Language A -- for a native speaker

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
*Status 2026-10-09: now cheap to probe -- `flextools_try_word level=explain` on the
expected compound, then `parse_log section=trace` for the rejection summary
(FlexToolsMCP 2.13.0). There is still no compound-specific diagnostic (T-34).*

**Q-19. Why does one noun take enclitics and a structurally similar one not?**
The comparison script ran; the diagnosis was never recorded (M6 §7).
*Audience: Ron, Tooling.* [Stage 09](stages/09-compounding-and-clitics.md).
*Status 2026-10-09: now cheap to probe -- run `try_word level=explain` on both nouns
with the enclitic and compare their `parse_log section=trace` summaries.*

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
Swahili logs, 2026-05-21..09-30; S6-S11 checked against the Claude Code transcripts behind
the logs):

| Q | Status after the merge |
|---|---|
| Q-02 | **Answered in practice: not safe.** Non-master-peer writes while FieldWorks or another client held the project lost commits to `FP_ConflictingSaveError` (C-S8-03; 61 shared-peer writes on 09-13, T-S7-03). On 09-13 the cause was the FLEx UI saving underneath and a second Claude session writing at the same time (01:04-01:31), **not sibling agents**: the overnight write agents ran sequentially by design, because the MCP holds one global session (C-S7-01, D-S7-10, updated by transcript). A fresh session reads the on-disk file, not the shared commit log, so a verifier nearly re-created objects that already existed (C-S7-13). The recovery that worked: close FLEx, re-apply, verify by read-back after reopen (D-S8-04). The 09-13 Description overwrite was one agent's own later run, which restored the text (C-S7-01). *Status 2026-10-09: partial -- a conflicting save now raises `FP_ConflictingSaveError` instead of losing data silently (flexicon 4.6.0), and WS/custom-field schema changes are refused while FLEx holds the project (FlexToolsMCP 2.15.0). Value writes as a peer are still allowed; there is no write lease (T-67).* |
| Q-06 | Not tested -- features were used throughout (see above) |
| Q-12 | Answered for Swahili (see above) |
| Q-16 | Still open -- no rule-ordering policy appears in the Swahili logs either. Rules were narrowed by left context (L-S7-06) and gated by an exception feature (L-S10-02), never reordered |
| Q-18 | Data points, no budget: about 3-6 s/word on 09-25. The 1,783-word Stage 2 baseline (estimated ~95 min) died at word 173 twice and was never completed (D-S10-05). Single `try_word` calls often outran the grace window (T-S10-02) |
| Q-21 | Two data points: one noun-class paradigm text with one unambiguous pair per class (D-S5-08); then on 09-13 **exhaustive** mechanical generation for every template of every inflecting POS (16 texts, ~1,100 paragraphs), proofread (69 corrections), with forms judged ungrammatical moved to "No Parse" texts at Matthew's instruction (537 verb forms; D-S7-07, D-S7-08). Those texts are a hand-judged **ungrammatical** set: no parse was run on them, and most would parse (wrongly) (C-S7-11). From 09-24 regression sets were a frequency head plus words containing the targeted segments, not paradigms (D-S10-05) |
| Q-22 | Partly: a per-grapheme parse rate was computed on 09-25 (gh 7%, th 17% vs a 66% mean) and found an orthography defect (D-S10-06). Environment coverage was still not measured |
| Q-23 | Still open. Matthew used a *static* threshold instead: 0 entries in the "orphaned" bucket, and a parse-ready count per phase (D-S3-03). The first measured rate is 66% of occurring wordforms on 09-25 (D-S10-06); no target was set |
| Q-25 | Partly: on 09-12 an agent measured that the all-optional finite template licensed 376 of 569 verb analyses, 112 of them junk readings of non-verbs (L-S6-07); later, analysis counts were the signal (*kichwa* 6, *mwana* 13, *Misri* 10; L-S6-09, L-S10-05, V-S10-07). The "No Parse" texts are a hand-judged negative set that was never parsed (C-S7-11). No systematic measurement |
| Q-27 | Cleanup was opportunistic in timing too, but each run was a planned, tiered batch (D-S5-05). S6-S11 add a cleanup trigger: after any failed write, sweep for orphans and partial state, because a write run that raises still commits what it wrote before the error (C-S6-01, C-S8-05, C-S11-05, T-S11-10) |

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
unification and unify-not-overwrite semantics (L-S7-01), reasoned rather than
parse-tested. The 09-20 claim that a 1a stem fails a class-1 concord (D-S8-11, V-S8-03)
concerns a concord on a separate word (*wake*), which a one-word HermitCrab parse never
unifies with the noun, so it is probably not a parser effect (S8 transcript, analyst
inference; ask lex-parser before relying on it).
**Restated question:** how should null-prefix over-generation be contained? 9/10 nouns get
one analysis per null prefix (*nyumba* 2; the 09-30 "duplicates" of *hukumu, ishara, enzi*,
L-S11-02), and null prefixes stack (*kichwa* 6, *watu* 5-8, *mwana* 13, *Misri* 10;
L-S6-09, L-S9-05, V-S10-07, L-S11-03). *Audience: Matthew, Tooling.*
*Status 2026-10-09: measuring it is cheap now (`parse_text` report
`analysis_count_distribution`; `parse_diff` after each containment change). The
modelling question stays open, and so do the feature-disjointness lint (T-48) and
the bucket partition (T-04).*
[reference/swahili-morphophonology section 2](reference/swahili-morphophonology.md).

**Q-39. What happened to the class-16 null prefix and the 11 held BantuMany rows?**
**Class 16 answered: it was never suppressed.** On 09-13 the noun write agent set
`zero-5` (cl.16) `DoNotUseForParsing`, not deleted, because it added a spurious cl.16
reading to about 967 prefixless stems (V-S7-02). Neither parser reads that flag (Q-43), so
the null prefix stayed active, which is why `∅ nul.pref.nc16 + watu` was still analysed on
09-24 (V-S9-03, explained). V-S7-02's "suppressed" is refuted by transcript. **Still
open:** keep the cl.16 null prefix, delete it, or hide it with `IsAbstract` (check with
`parse_diff`; *mahali* is stored whole and would lose its cl.16 reading).
**BantuMany:** used by zero MSAs on 09-12 (V-S6-07), 3 senses by 09-20 (V-S8-02, D-S8-09),
but the feature still has 6 values on 09-25 (V-S10-03). A lex-domain consult offered two
readings (non-count grouping; derived-locative stacking); the data favours retiring it.
The 11 held rows are not addressed in any log. *Audience: Matthew, Tooling (inspect the
project).* *Note: `run_module` refuses `DoNotUseForParsing` at preflight even in
read-only runs (FlexToolsMCP 2.13.0), so an inspection script cannot read the flag
directly.*

**Q-40. Are the Swahili verb extensions going to be decomposed?** **Answered: yes, on
09-13**, to Matthew's design: intransitive verbs as a subcategory, inherited parent
morphology, "derivational affixes can make words jump categories" (D-S7-14). Causative and
applicative became `MoDerivAffMsa` Underived -> Transitive; passive, reciprocal, stative
and statal Transitive -> Detransitive; the empty inflectional slots were removed (V-S7-01,
L-S7-05, D-S7-06). Matthew stopped the rollout after the prototype ("Revert W3, keep
W1+W2") and restarted it ("make a plan and resolve it fully"; D-S7-11). **The outcome is
known from the transcript:** 1,054 forms before/after, 1,020 unchanged, 34 lost, 0 gained
(V-S7-11). Passive and stative surface as affixes in 09-25 parses (V-S10-05).
**Remaining:**
- the 508 vt / 139 vi classification was LLM-only (default Transitive, an adversarial
  second pass, no human review; D-S7-12);
- reducer stacking is now blocked (*kuvunjanewa, kuvunjewika* 1 -> 0) and caus/appl order
  is free (*kuvunjishia, kuvunjiisha* both parse); put to Matthew at 12:13, unanswered
  (L-S7-11);
- one root relapsed twice (*zalia, zaliwa*; C-S7-06, C-S10-03 -- see Q-46);
- a 09-30 long-tail sample of extended verbs (*walifanywa, amekikalia, hukomesha*)
  stayed unparsed with no diagnosis (S11).

*Audience: Matthew.*

**Q-41. When should an analysis be approved, and by which agent?** **Partly answered by
practice, still no written policy.** S2 auto-approved by heuristic as Human and
reversed it; S4 rejected with reasons. Then:
- 09-12: every analysis but three was parser-approved (V-S6-06).
- 09-13: a write-mode session again approved heuristic segmentations (C-S7-04, V-S7-06).
- 09-23: 448 human-approved vs 24,796 parser analyses. Matthew asked to "identify and
  remove all incomplete user analyses"; the agent promised to delete "only after you
  confirm", then sent `confirmed: true` 20 s later without showing him the list (only the
  parse-worker lock stopped it). 14 of the 18 lacked only a verb-extension sense, so
  linking them was the better fix (D-S8-14, C-S8-06, updated by transcript).
- 09-24: **Matthew removed all human approvals himself** ("i just removede user-approved
  analyses", D-S9-06, V-S9-01). From then on analyses are parser-filed only, through a
  two-step preview / confirm, and he asked for filing explicitly ("apply the parsese to
  the project", D-S9-11).
- 09-25: Matthew ordered the whole-corpus filing ("remove *mwaka, file the parses.").
  The agent confirmed it without showing him the 24,259 upper bound; the real result was
  322 deletions, 10,299 new and 21,959 re-approved analyses (C-S10-02, L-S10-01, updated
  by transcript). The "Filing NOT authorized" brief that evening was the orchestrating
  agent's prompt to its subagent, not Matthew's words; he had said "I approve if you do.
  You're running the show." (D-S10-04; V-S10-10 refuted).

Open: is the approval layer gone for good, or reset for a fresh baseline (this changes
README 4.14)? Is filing a human gate separate from write mode? *Audience: Matthew, Ron.*
*Status 2026-10-09 (tooling side): filing needs `confirmed=true` plus the preview's
`plan_id`, but an agent can supply both itself, so the tool does not enforce a human
gate (T-73). flexicon's `ApproveAnalysis` / `RejectAnalysis` always record the human
agent and take no reason (T-44).*
[Stage 11](stages/11-parse-and-repair-loop.md).

**Q-42. Are AI-drafted free translations and textbook paradigm forms acceptable test
material?** **Still open, sharpened.** D-S4-01 drafted English free translations by
machine, and D-S5-08 took paradigm forms from general knowledge. Since then:
- the 09-13 paradigm texts carry a "generated mechanically" header and rejected forms
  carry a stated reason, which partly meets H6's labelling condition (V-S7-07);
- an AI-invented "must survive" probe set held likely non-words (*kuvunjewa,
  kuchaguwa*; C-S7-07);
- Matthew drove the 09-13 proofreading and gave rulings, but the corrections were AI
  judgement with no parse or corpus check (V-S7-07);
- the 647-verb valency classification was LLM-only (D-S7-12);
- Matthew explicitly sanctioned the AI's "deep knowledge of Swahili" (D-S9-01, D-S10-03),
  and the resulting entries, glosses and classes are not labelled in the project;
- a weaker client invented the corpus words it was diagnosing (C-S11-01), and the
  unidentified 09-30 client fabricated parser decompositions, then created 9 junk entries
  to match them (C-S11-08, C-S11-05).

No native-speaker or attested-corpus check appears in any shard. *Audience: Matthew,
Native speaker.*

**New questions (from S6-S11):**

**Q-43. What replaces `DoNotUseForParsing` for "listed but not parsed"?** **Largely
answered (09-25).** The project tried to suppress whole-word possessives, a duplicate stem
and the cl.16 null prefix with it (33 entries by 09-20; D-S7-04, D-S8-12, V-S7-02).
Matthew doubted it on 09-20 ("in the UI, only "isAbstract" is surfaced", D-S8-12) and on
09-25 had subagents read the FieldWorks source (D-S10-14):
- **The flag does nothing in either parser.** HermitCrab never reads it and drops a form
  only when it is `IsAbstract` or empty (`HCLoader.cs` :256, :543, :585); XAmple filters
  only on `IsAbstract`; the FLEx UI does not show the flag. So every S4-S8 suppression with
  it was a no-op. This explains V-S9-03 and settles C-S8-07.
- **The replacement is `IsAbstract` on the entry's forms**: the lexeme form and every
  allomorph (an entry drops out only when all its forms are abstract; affix-process forms
  are not filtered this way). Recipe `hide-entry-from-parser`; flexicon
  `Allomorph.Get/SetIsAbstract` (#546).
- **Matthew's decision:** treat the flag as deprecated and blocked until FLEx and the
  parsers implement it; he opened Jira LT-22810, preferring the old field to overloading
  `IsAbstract`. *Status 2026-10-09: done in FlexToolsMCP 2.13.0 (PR #259): `deprecated_member`
  at preflight, a "did you mean" from `entry.IsAbstract` to the forms, and a weekly
  upstream watch (README 4.19).*

**Still open:** migrate the 33 flagged entries (to `IsAbstract`, clear the flag, or leave
them; asked three times on 09-25, unanswered). Each move changes parser output, so prove
it with `parse_diff`. The overlap with the soft-delete convention also remains. *Audience:
Matthew.* [reference/flex-modeling-decisions section 7](reference/flex-modeling-decisions.md).

**Q-44. How should Swahili glide formation be modelled: a global rule, per-prefix
allomorphs, or an exception feature?** It lives in two places: 10 prefixes carry the
glide allomorph lexically, 35 depend on the rule (L-S7-18). On 09-13 Matthew chose to keep
the rule and add a left context rather than list allomorphs (L-S7-06). The rule then
blocked cl.4 `mi-` (*miaka*); narrowing its context did not help, cause unexplained
(V-S9-07). A live disable never persisted (C-S9-02). The evidence since:
- **Disable, tested:** the 09-24 sandbox A/B on 2,139 words: 1,517 -> 1,568 parsed, 54
  fixed, 3 broken (*vyombo, vyanzo*, because `vi-2` lacks a `vy` allomorph). Recommended:
  disable the rule and add `vy` to `vi-2`. Unanswered (T-S9-08, L-S9-09).
- **Exception feature, applied:** the 09-25 fix tags three stems (L-S10-02). It was only
  spot-checked, and the chat that chose it never saw the sandbox result (C-S10-08). It
  does not scale, and it sits on stems because HermitCrab reads an affix MSA's
  `FromProdRestrict` as a *required* feature, so the triggering prefix cannot carry it
  (L-S10-07, source reading, untested).
- **Per-morpheme allomorphs, specified:** the 09-25 linguist spec calls gliding
  morpheme-conditioned ("produces kwona, and it misses mwili and kwake") and recommends
  deleting the rule, adding `mw-/tw-/kw-` per morpheme and listing *kwenda/kwisha*
  (L-S10-09). Matthew's division of labour (D-S6-07) points the same way.

Matthew approved the glide item with all 11 Stage 2 options (D-S10-16); Stage 2 never
executed (D-S10-05). *Audience: Matthew.* See also Q-50.
*Status 2026-10-09 (tooling side): `PhonRules.SetDisabled` is in flexicon 4.12.0 (#572).
Creating an exception feature (`ExceptionFeatureCreate`, #631) and tagging affix MSAs
(`side="from"|"to"`, #630) are fixed on flexicon main, not yet released (after 4.12.0);
given L-S10-07, the affix side would not exempt anything in HermitCrab. Writing a rule's
required/excluded rule features is still open (README 4.18).*
[Stage 08](stages/08-phonological-rules.md).

**Q-45. Separate template, or optional slot, for verb forms with no TAM filler?** At
20:56 on 09-13 a blind evening session made TAM2 optional so habitual *husema* and
negative-present *sisemi* parse, against the same day's design record ("DO NOT change the
Optional flag ... TAM2") and README 4.13; it read no template Description and also
questioned inflection4's documented RelSuf anchor (C-S7-02). The other 09-13 template
changes are settled: the singular-imperative template was built at Matthew's request and
corrected after his parser screenshot (L-S7-03), and the subjunctive without an object
marker got its own `Verb subjunctive` template at 01:42 (L-S7-18). *Audience: Matthew.*
[Stage 05](stages/05-categories-and-templates.md),
[README 4.13](README.md#413-relax-the-slot-vs-separate-templates).

**Q-46. When is a derived stem lexicalized enough to list rather than decompose?**
*zalia* 'give birth to/for' and *zaliwa* 'be born' were stored first as allomorphs of
*zaa*, then as separate Transitive stems, after the extensions had become derivational
(C-S7-06, L-S10-04). The 09-25 split was never put to Matthew; it went through as a
"lexicon-only" fix, and the agents' own linguist spec calls *zalia* `za-li-a` (C-S10-03).
No criterion was stated. *Audience: Matthew, Native speaker.*

**Q-47. Are these AI-asserted Swahili forms right?** Each was written into the project
without a logged check:
- the passive `-ew-` environment after consonant-final roots (it pre-existed 09-12,
  D-S6-06; standard Swahili has plain `-w-` there);
- *Torati* (Torah) and *Yerusalemu* (a place) carry noun class 1a, copied from a personal
  name (L-S9-04);
- *binti* moved from 2/1 to 1a, its old features reused for *israeli* (S9);
- the 1sg `na-` analysis as `n-` + `a-` 'present (general)' rather than a ni+na
  contraction (Matthew approved the change, the analysis is the AI's; D-S10-13).

Settled by transcript: the cl.1 object marker does have `m / _ C`, with `mu` only before
u (D-S6-05); class 13 under both features was Matthew's instruction (D-S8-10).

*Audience: Native speaker, then Matthew.*

**Q-48. Is the dotted gloss scheme (`sbj.nc10`, `conn.conc.nc4`) the project's
convention, or should glosses follow Leipzig?** A local-model session rewrote 808
glosses on 09-14 and called the result Leipzig; it is a project-local scheme (D-S8-02).
It also moved category hints such as "(v)" out of glosses (S8 conflict 4) and broke
scripts that looked affixes up by gloss (C-S7-09). *Audience: Matthew.*
[conventions/flex-data-conventions](conventions/flex-data-conventions.md).

**Q-49. What is the live state the logs stop short of?** Mostly answered by the
transcripts and a read-only check of the project file:
- **junk entries: yes, 9** (`malaka, el, kumu, gizo, is, hara, en, ghadha, bu`),
  committed 09-30 19:54 and still present, not yet sent by Send/Receive; `fu, hu, zi, ma,
  a` pre-existed. Delete the 9 GUIDs listed in the S11 transcript check (C-S11-05;
  [swahili-morphophonology section 7](reference/swahili-morphophonology.md));
- **Stage 2 did not land**: its baselines died at word 173 and the agent stopped at 23:32
  on 09-25; Stages 3-5 and the filing never ran (D-S10-05, V-S11-04);
- **the 09-13 extension conversion**: 1,054 forms, 1,020 unchanged, 34 lost, 0 gained
  (V-S7-11); **the 09-24 glide sandbox**: 54 fixed, 3 broken of 2,139 (T-S9-08).

Still open: is the Quantifier template still inert (fillers owned by Connective, L-S6-11,
L-S7-04)? Are the 4 possessive flags of 09-20 still set (the revert offer was never
answered, D-S8-12)? *Audience: Tooling (inspect the project), Matthew.*

**Q-50. How should CV verb roots be kept from gliding?** Eight CV-shaped roots (*ju, tu,
ku, chu, vu, li, zi, ti*) are still glided by the rule: *ju+a* gives *\*jwa* for *jua*
(also *lia, tua*; L-S7-17, 09-13). A right-context fix was dropped because it would break
29 stems that need the glide (*mweupe, choo, maua*; C-S7-15). On 09-13 the AI said FLEx has
no per-morpheme exception for phonological rules and offered only a lexical fix (invariant
stems), not taken. That claim was **superseded on 09-25**: the `noGlide` exception feature
on stem MSAs does block the rule (L-S10-02). Nobody has applied it to these roots, and
whether they still mis-glide today is unchecked (`try_word` on *jua, kujua, lia*). If the
rule is replaced by per-morpheme allomorphs (Q-44), this goes away. *Audience: Matthew,
Tooling (check with `try_word`).* [reference/swahili-morphophonology section 1](reference/swahili-morphophonology.md).

**Q-51. Which of the 09-13 linguistic rulings still need building?** Raised in the
evening proofreading and never implemented (L-S7-14, L-S7-15):
- Matthew's rulings: irregular plurals as inflectional variants (*meno*); a 9/10 concord
  N- form fixed by a phonological rule (*ndefu, mpya*); *vikijana -> vijana* as an affix
  process. The AI preferred storing roots (`-uso`, `-jana`) so *nyuso, vijana* fall out;
- `-i` (negative non-past) must not attach to Arabic-origin stems (*hasamehe, harudi*);
- hu- is ambiguous between habitual and NEG.2SG;
- an object marker plus imperative needs `-e` (*isemeni*, not *isemani*);
- `-cha-` is mis-tagged as a relative marker (it is the cl.7 connective).

*Audience: Matthew, Native speaker.*

---

## Note on what "unresolved" costs

Several of these are cheap to close by simply inspecting the live project
(Q-08, Q-17, Q-20, Q-14). They are open here only because the **log format persists
source code and message counts, not report output** (M6 §6, M2 §7, M8 §6). That is
itself a tooling finding -- see [MERGE-NOTES](MERGE-NOTES.md).
*Status 2026-10-09: still open (T-43). The operation log keeps a 1000-character `[OUT]`
preview per result, and report.Info only for failed runs. Parse runs are the exception:
they persist in their own records (newest 20 per project).*
