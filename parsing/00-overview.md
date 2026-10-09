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

Per the "multiple projects, one process" constraint, no stage body contains language-A
facts. Phenomena, classes, and environment strings live in:

- [`reference/example-agglutinative-suffixing.md`](reference/example-agglutinative-suffixing.md)
- [`reference/natural-classes.md`](reference/natural-classes.md)
- [`reference/allomorphy-environments.md`](reference/allomorphy-environments.md)

and the language-neutral modeling logic lives in:

- [`reference/flex-modeling-decisions.md`](reference/flex-modeling-decisions.md)

Stage bodies cite them by link. The second operator's language-specific material is in
[`reference/swahili-morphophonology.md`](reference/swahili-morphophonology.md).

---

## 5. The principles tested against a second operator

The merge notes asked that each principle be tested against Matthew's Swahili practice.
Shards S1-S11 now cover both machines' logs (S1-S5 from one, S6-S11 from the other;
2026-05-21 .. 09-30). P2 and P6 were predicted to be the most idiosyncratic to Ron.
That prediction did not hold: P6 is confirmed and P2 is refined, not refuted.

*Evidence caveats.* S1-S7 logs keep no tool output and S8-S11 logs truncate it; no log
keeps Matthew's mid-turn messages. On 2026-10-09 the S6-S10 claims were re-checked
against the Claude Code transcripts behind them. That moved several verdicts below:
the 09-13 grammar work was parse-checked (by Matthew in FLEx, then in process), the
overnight agents wrote one at a time, and many decisions first credited to the AI were
Matthew's. Some sessions were other clients (local models, Matthew's Hermes setup, the
unidentified non-Claude Code client of S11); they count as failure evidence, not as
Matthew's practice.

| Principle | Matthew's practice | Verdict | Evidence |
|---|---|---|---|
| P1 Bottom-up | Dependency order kept, but features (from the catalog) came before phonemes, rules before the lexicon, templates after it. The S1 glide rule, written before the lexicon, still blocked class-4 *mi-* nouns in September: disabling it in a sandbox fixed 54 of 2,139 words and broke 3; narrowing it did not help | **Partly** -- see [README 4.9](README.md). The rule-first cost argues for keeping P1 for rules | D-S1-01, D-S1-02, C-S1-08, V-S9-07, T-S9-08 |
| P2 Inflection first | Derivation scoped *in*: a derived word enters with its base and a derivational affix (R4). The early build put extensions in inflectional slots instead -- the same error P2 exists to prevent. Fixed 09-13 by converting the six extensions to derivational MSAs | **Refined:** "derivation with its pieces, never in a template" rather than "derivation later" | L-S3-01, C-S1-06, L-S7-05, V-S7-01 |
| P3 Cheap version first | Not a standing instruction, but visible as scope control: he rejected the agent's corpus-wide parse and restated "(don't run the parse yet) ... individually", then "top 10 ... (don't run the full set)"; restricted single-word probes. Broken by the AI in a 12-change op that failed half-way | **Confirmed as scope discipline** | D-S4-09, D-S9-13, D-S9-02, D-S10-02, C-S9-04 |
| P4 Plan first | Strong from S3 on: dry runs, manifests, hold lists; later a read-only diagnosis phase before each write stage. Absent in S1-S2 (a whole-lexicon delete with no plan) | **Confirmed** (late) | D-S4-11, D-S5-05, C-S1-02, D-S7-06, D-S10-03 |
| P5 validate_only first | Absent in S1-S2 and June; standard from August, extended into a ladder (`validate_only` -> dry run -> 5-entry batch -> full -> idempotency rerun). A clean validate_only still let a grammatically wrong slot merge through | **Confirmed and extended; validate_only is mechanical only** | D-S3-04, C-S3-04, D-S10-09, C-S6-02 |
| P6 Proof of recipe | One phoneme before the inventory; 10 approvals before the bulk run; tag classes before restricting allomorphs; a 20-root prototype, reverted, before the 647-verb conversion | **Confirmed** | D-S1-04, L-S2-03, D-S5-04, D-S7-06 |
| P7 Verification | Fresh-session verification after every write; identity assertions; GUID keys; `parse_diff` against a baseline. Before any AI could parse, Matthew ran the FLEx parser himself and sent screenshots (09-13 01:20-01:41); the 09-13 valency rollout was diffed over 1,054 forms (1,020 unchanged, 34 lost, 0 gained). Gaps: blind writes on 09-12, by the overnight subagents and in the 09-13 evening session; an in-op read-back that never persisted; a failed run that still committed (T-S11-10) | **Confirmed, extended:** verify by a live parse and by reopening; after a failed write, read the database back | D-S4-07, D-S7-16, V-S7-11, T-S9-03, D-S10-05, C-S6-05, C-S9-02 |
| P8 Blast radius | Referrer listing before replacing classes; reference checks before deletes (entry-level only in S5); later, counting the stored analyses that depend on a rule output before changing it | **Confirmed**; the S5 gap is closed for rules, still open for owned objects | L-S1-03, C-S5-01, L-S9-06, L-S10-02 |
| P9 Distrust the result | Verified the reviewers' claims; rejected only verified-bad analyses; questioned a parse the template should block; doubted that `DoNotUseForParsing` did anything ("in the UI, only "isAbstract" is surfaced") and had FieldWorks read -- it did nothing; checked run sizes ("did you say you had started parses of 14000 words?"). Stored "unparsed" state turned out mostly stale | **Confirmed, with a new target:** distrust the stored analysis state too | D-S4-10, D-S5-01, D-S8-12, D-S10-14, D-S9-07, D-S9-12, L-S10-01, L-S11-01 |
| P10 Decompose | Demonstratives and connectives decomposed; suppletives kept whole. Verb extensions decomposed on 09-13 to Matthew's subcategory design; "I do want you to build it properly" over whole-word entries. Later lexicon passes re-listed *zalia* / *zaliwa* | **Confirmed in practice from 09-13, with relapses** | D-S2-04, C-S2-03, D-S7-14, V-S7-01, D-S10-15, C-S7-06, C-S10-03 |

**Candidate additions from the second operator** (not yet promoted to principles --
one project's evidence):

- **P11 (candidate). Define "done" per entry before populating.** Write an explicit
  parse-ready standard and measure the whole lexicon against it (D-S3-03).
- **P12 (candidate). Soft before hard.** Disable before delete, and reject before
  delete. Keep a hold list for anything evidence cannot settle (D-S4-08, D-S4-10,
  D-S3-05). Suppress a redundant whole-word entry only once its compositional analysis
  is attested (D-S7-04). Caveat: the flag used for "disable" then,
  `DoNotUseForParsing`, is read by neither parser, so every S4-S8 suppression was a
  no-op (D-S8-12, D-S10-14); it is refused at preflight since FlexToolsMCP 2.13.0. To
  disable now, set `IsAbstract` on the lexeme form and every allomorph, and prove the
  effect with `parse_diff` (README 4.19).
- **P13 (candidate; strongest of the new ones). Reparse before triage.** Stored
  analyses describe the last parse run, not the current grammar. A refile alone cut the
  unparsed count from 14,096 to 9,260; the top words of every "unparsed" queue mostly
  parsed live and were merely unfiled (L-S8-01, T-S9-14, L-S10-01, L-S11-01). Matthew
  moved to it himself: "give me a command to run parsing on all ... words with no
  parser analyses" (D-S11-06). Tool-output evidence, language-neutral; a corollary of
  P9 and P7, and a candidate for promotion.
- **P14 (candidate). The project holds its own design record.** Template
  Descriptions record why a structure exists and what was deliberately not built; the
  AI's clean-up passes reversed undocumented decisions and skipped documented ones
  (D-S6-09, D-S7-02, C-S6-02, C-S7-02).
- **P15 (candidate). Parallel readers, one writer.** Read-only proposal and diagnosis
  agents in parallel; writes serialized per project. Practised from the start: Matthew
  asked for per-POS subagents, the AI kept them read-only and ran the 09-13 write
  agents one at a time. The conflicts that did happen came from FLEx and from a second
  session writing at the same time, so the rule spans sessions and clients, not just
  subagents (D-S6-13, D-S6-12, D-S7-10, D-S10-03, C-S7-01, T-S7-03, C-S10-06). See
  guardrails L1.
- **P16 (candidate). Write, file and approve are separate authorities.** Matthew asks
  for filing as its own step (D-S9-11, C-S10-01); even then the agent owes him the
  preview's delete bound before confirming (C-S10-02), and a filing deferred to a
  later stage must actually run (V-S11-04). Neither write mode nor filing authorizes a
  Human approval (C-S7-04, K1). See guardrails L4, L9.
- **P17 (candidate). Build what was approved.** Approvals come per option, from a
  preview; the built object must match it, and any deviation goes back for a decision
  (D-S6-03, C-S10-09, D-S9-16). See guardrails L14.
