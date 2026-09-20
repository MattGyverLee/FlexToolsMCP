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

**Q-09. When should a shared parent category (e.g. "Nominal") be introduced** versus
duplicating slots per child category? The corpus's Nominal restructuring was done by
Ron in the GUI with no recorded rationale (D-M5-02).
*Audience: Ron.* [Stage 05](stages/05-categories-and-templates.md).

**Q-12. Should a given POS have a citation form distinct from its bare lexeme form**
(e.g. an infinitive vs a stem)? Raised in the German project and never resolved
(L-G1-03). *Audience: Matthew, Native speaker.*
[Stage 06](stages/06-stem-and-affix-population.md).

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

## Note on what "unresolved" costs

Several of these are cheap to close by simply inspecting the live project
(Q-08, Q-17, Q-20, Q-14). They are open here only because the **log format persists
source code and message counts, not report output** (M6 §6, M2 §7, M8 §6). That is
itself a tooling finding -- see [MERGE-NOTES](MERGE-NOTES.md).
</content>
</invoke>
