# Overview -- Philosophy and Stage Map

[Back to README](README.md)

---

## 1. What this process is for

Building a FLEx lexicon whose **acceptance test is machine parsing**. The goal, in
Ron's words at the outset of the corpus:

> "The goal is to be able to use the FLEx Parser to parse the paradigm words." (D-M2-04)

Everything downstream of that sentence -- which fields are mandatory, which FLEx
construct models which alternation, when to stop -- follows from parseability being
the acceptance criterion rather than dictionary presentability.

This is materially different from a vocabulary/deck project, whose QC loop is
"spec versus database reconciliation" (G1 §9). A parsing project's QC loop is
"does the grammar generate exactly the attested surface forms, and nothing else."

---

## 2. Ten principles the corpus actually exhibits

**P1. Bottom-up, in dependency order.** Phonemes before features; features before
natural classes; classes before rules; categories and templates before affix entries;
stems and affixes before paradigm texts; paradigm texts before parsing.
(D-M1-01, D-M2-02, D-M2-05.) Ron's opening directive explicitly defers features:
*"Also populate/edit the phoneme inventory as needed for the language. Don't yet add
phonological features."*

**P2. Scope inflection first, derivation later.** *"Don't list nouns with derivational
affixes right now."* (D-M2-01.) Derivation is a different FLEx mechanism
(`IMoDerivAffMsa`, never an inflectional template slot -- C-M6-03) and mixing it in
early is how the Nmlz-slot mistake happened.

**P3. Cheap version first.** *"do the cheap version first"* -- the standing instruction
on every one of 41 operations in M7 (D-M7-01). Write the minimal, least-casted probe;
escalate only when it fails or preflight rejects it. Corrections land within the same
minute (M7 §9).

**P4. Plan first, mutate second.** *"# Pass 1: decide, with no mutation, exactly what
goes."* (D-M7-03.) Compute the victim/keep partition read-only, print counts, flag
anything needing human judgement (has senses; is the rule's only RHS -- D-M7-06), then
mutate under `if modifyAllowed:`. By the end of the corpus this is reflexive for *all*
structural edits, including surgery on internal LCM object graphs (D-M7-04), not just
lexical entries (M7 §9).

**P5. Every live write is preceded by an identical `validate_only` run.** With the
same code fingerprint. In M7 this pairing appears with no exceptions (M7 §9), and
across M5/M8 it precedes every bulk or risky write.

**P6. Proof-of-recipe before scale-up.** *"build the two GEN -yute rules as a proof of
the recipe"* (D-M1-09); *"Check 'do' ... If that works, apply the same changes to the
suffixes NMLZ.M, NMLZ.PL and TEMP.PST"* then *"change all verbs to ..."* (D-M8-06,
D-M8-07). One exemplar, fully verified; then siblings; then the whole class.

**P7. Verification is part of the task, not an extra.** Every feature is followed by a
dedicated read-only "assert the invariants" snippet with explicit expected counts
("want 0", "want 6") (M7 §9, D-G1-06). And fixing a bug includes a **regression check**
on what already worked: *"Fix it, but verify the others that are working will still
parse."* (D-M3-01.)

**P8. Blast radius before edit.** Before extending a shared natural class, environment,
or feature, check what else references it (C-M5-05, D-M5-14). Before narrowing a
previously-unrestricted allomorph, enumerate *all* classes that legitimately need it
(C-M5-06, D-M5-15). Before a shape-based bulk delete, intersect with a POS check
(C-M7-01).

**P9. Distrust the result.** Ron's most characteristic move is not building -- it is
doubting. Not every multi-parse is a bug (*"That's ok if those are true ambiguities in
the language"* -- D-M3-04). Not every skipped bulk-import row is fine (D-M5-13). Not
every flagged environment is real (L-M8-04: 13 "env-bearing" allomorphs turned out to
carry empty strings). Not every zero-hit paradigm cell should be invented
(L-M5-02: four instrumentals with zero corpus hits deliberately omitted).

**P10. Decompose, do not list.** Prefer an analysis (base + productive clitic with its
own allomorphy) over an inventory of surface forms -- **but only where the composition
is transparent** and only after the derivation is verified to parse (D-M5-09, L-M5-07).
Likewise merge derived entries back into their bases as conditioned allomorphs once
the conditioning is understood (L-M3-15).

---

## 3. The stage map

Stages are numbered in **execution order** for a greenfield project. They are not a
waterfall: Stage 11 is a loop that routinely re-enters Stages 04, 06, 07, 08 and 09,
and Stage 12 re-enters Stage 06 in bulk.

| # | Stage | One-line purpose |
|---|---|---|
| 01 | [Project Survey and Inventory](stages/01-project-survey-and-inventory.md) | Know the real current state before touching anything |
| 02 | [Phoneme Inventory](stages/02-phoneme-inventory.md) | Every grapheme the corpus tiles against exists as a phoneme with a `PhCode` |
| 03 | [Phonological Features](stages/03-phonological-features.md) | A catalog-linked, fully specified binary feature matrix over the inventory |
| 04 | [Natural Classes](stages/04-natural-classes.md) | Named, maintainable conditioning sets -- and the discipline of when *not* to make one |
| 05 | [Categories and Inflection Templates](stages/05-categories-and-templates.md) | POS inventory from the FLEx catalog; affix templates and ordered slots per POS |
| 06 | [Stem and Affix Population](stages/06-stem-and-affix-population.md) | Idempotent bulk creation of stems and affix entries with complete field sets |
| 07 | [Allomorphy Modeling](stages/07-allomorphy-modeling.md) | Choose the right FLEx construct per alternation and apply it uniformly |
| 08 | [Phonological Rules](stages/08-phonological-rules.md) | Global rules, boundary-anchored, with parse time as a metric |
| 09 | [Compounding and Clitics](stages/09-compounding-and-clitics.md) | Compound rules and enclitics -- the things that live outside the template |
| 10 | [Paradigm Text Construction](stages/10-paradigm-text-construction.md) | Constructed texts that are the parser's targeted test suite |
| 11 | [Parse and Repair Loop](stages/11-parse-and-repair-loop.md) | The core loop: parse, triage failures and over-generation, fix, regression-check |
| 12 | [Real-Corpus Stress Test](stages/12-real-corpus-stress-test.md) | Real text finds the gaps constructed paradigms cannot |
| 13 | [Cleanup and Consolidation](stages/13-cleanup-and-consolidation.md) | Retire redundancy, merge entries, reconcile duplicate conventions |

### Dependency sketch

```
01 Survey
 |
 +-> 02 Phonemes -> 03 Features -> 04 Natural classes ------+
 |                                                          |
 +-> 05 Categories + templates -> 06 Stems + affixes -------+
                                        |                   |
                                        v                   v
                                   07 Allomorphy  <----> 08 Phon. rules
                                        |                   |
                                        +--> 09 Compounds / clitics
                                                    |
                                                    v
                                            10 Paradigm texts
                                                    |
                                                    v
                            +----------->  11 Parse + repair  <-----------+
                            |                       |                     |
                            |                       v                     |
                            +---------------  12 Real corpus  -------------+
                                                    |
                                                    v
                                            13 Cleanup / consolidation
```

Stages 02-04 and 05-06 can proceed in parallel; they meet at Stage 07.

### If the project is not greenfield

Run Stage 01 in full, then enter at the first stage whose Exit Criteria the project
fails. A project restore, a GUI edit by the human, or a concurrent session all
invalidate your assumptions and send you back to Stage 01 (D-M3-03, D-M5-02, D-M6-01,
C-M2-06).

---

## 4. What is deliberately *not* in the stage bodies

Per the "multiple projects, one process" constraint, no stage body contains Malayalam
facts. Phenomena, classes, and environment strings live in:

- [`reference/malayalam-morphophonology.md`](reference/malayalam-morphophonology.md)
- [`reference/natural-classes.md`](reference/natural-classes.md)
- [`reference/allomorphy-environments.md`](reference/allomorphy-environments.md)

and the language-neutral modeling logic lives in:

- [`reference/flex-modeling-decisions.md`](reference/flex-modeling-decisions.md)

Stage bodies cite them by link.
</content>
</invoke>
