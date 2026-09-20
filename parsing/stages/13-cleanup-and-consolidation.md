# Stage 13 -- Cleanup and Consolidation

[Back to overview](../00-overview.md) | [Prev: Stage 12](12-real-corpus-stress-test.md)

## Purpose

Remove what the grammar has made redundant, merge what should never have been
separate, and reconcile places where two conventions have been used for the same
thing. A parsing lexicon accumulates redundancy fast, and redundancy is not inert:
it produces duplicate parses and slows parsing down.

This stage runs **periodically**, not once. In the corpus it recurs at least seven
times across six days.

## Entry Criteria

- The grammar is in a known-good state ([Stage 11](11-parse-and-repair-loop.md)
  converged), so the effect of a deletion is measurable.
- A recent backup exists.

## Inputs

- Referrer counts for every shared object (classes, environments, inflection classes,
  stem names, variant types).
- Allomorph usage counts across all parser analyses (M1 op 41).
- The duplicate-parse analysis from Stage 11.
- An inventory of any place where two conventions coexist for the same phenomenon.

## Procedure

1. **Plan first, mutate second. Always.**
   > "# Pass 1: decide, with no mutation, exactly what goes." (D-M7-03)
   Compute the victim/keep partition read-only, print counts, then mutate under the
   guard. Remove indices in descending order (M7 §5).
2. **Partition candidates into safe / needs-review.**
   > "Build the exact list of [candidate] variant entries that the augment would
   > replace, and confirm they carry no senses." (D-M7-02)
   Anything carrying senses, definitions, or analytical work is **not** a safe
   deletion; warn and skip it for manual review.
3. **Intersect shape-based filters with a category check.** The corpus's worst cleanup
   mistake: a bulk-delete predicate matched purely on orthographic shape and swept up
   six pronoun/quantifier obliques alongside 92 noun obliques (C-M7-01). Run the POS
   survey **before** the destructive operation, not after. The converged practice is
   to scope bulk operations by **explicit target lists**, not broad shape predicates
   (M7 §9).
4. **Back up content before deleting entries that took analytical work.**
   > "the gloss/definition work is real and deletion is irreversible" (D-M5-10)
   Dump form, transliteration, senses, glosses and definitions to a recoverable file
   first. The corpus's retirement operation also aborts entirely if any target entry
   is missing or ambiguous.
5. **Delete what the rules now derive.** Stored allomorphs superseded by a global
   phonological rule (M1 op 35, L-M3-05), and allomorphs that are verbatim clones of
   their own entry's lexeme form (L-M3-05) -- both produce duplicate parses.
6. **Delete allomorphs with zero usage across all analyses** (M1 op 41) -- or find out
   why they are unusable, which is often a bug rather than dead weight.
7. **Merge derived entries back into their bases as conditioned allomorphs** once the
   conditioning is understood. The corpus merged three derivational pairs this way,
   attaching environments to the merged allomorphs (L-M3-15).
8. **Collapse a class system along its true dimensions.** When two independent
   dimensions have been conflated into one class inventory, split the independent one
   out as its own affix and retire the redundant classes (L-M3-11).
9. **Consolidate duplicate possibility-list items.** The human and a script can create
   two same-named variant types or inflection classes independently; reconcile rather
   than leaving both (D-M5-05).
10. **Reconcile competing conventions.** Where the same phenomenon is modeled two ways
    across the lexicon -- the corpus's obliques exist both as stem allomorphs and as
    variant entries, with some entries carrying **both** (L-M6-01) -- count the
    populations, decide, and converge. This one was never resolved in the corpus; see
    Open Questions.
11. **Never delete the last remaining child of a required collection** (D-M7-06);
    guard and warn.
12. **Do not delete a shared object that is still referenced** (M3 §6): check the
    referrer count first.
13. **Write a per-item conversion/deletion log to a file** (M8 wrote
    `convert_log.txt`) -- this is what makes a partial bulk operation recoverable.
14. **Verify afterwards with explicit expected counts** ("want 0", "want 6" -- M7 §5),
    and spot-check individual items.
15. **A rollback is a legitimate outcome.** Trying a modeling technique, verifying it
    live, and then fully reverting it with the same plan-then-mutate discipline is
    normal practice, not failure (D-M7-07).

## Linguistic Decisions Required

- **Is this allomorph genuinely redundant, or does it cover a case the rule misses?**
- **Should these two entries be one entry with allomorphs?** (L-M3-15.)
- **Which of two competing conventions is correct** for a given phenomenon
  (L-M6-01) -- and whether the answer differs by category (M7 restored pronoun
  obliques as variant entries while replacing noun obliques with an inflectional
  affix, L-M7-05).
- **Is this whole-word entry a transparent composition** that can be retired
  (L-M5-07)? See [Stage 09](09-compounding-and-clitics.md).
- **Is a class system's dimensionality right** (L-M3-11)?

## QC / Exit Criteria

- No stored allomorph duplicates a rule-derived form.
- No allomorph is a clone of its own lexeme form.
- No zero-usage allomorph remains unexplained.
- No duplicate possibility-list items (variant types, inflection classes, classes,
  environments) with identical semantics.
- No entry carries two competing representations of the same phenomenon.
- No orphaned objects left behind by structural deletions (contexts, environments,
  classes with zero referrers -- either deleted or justified).
- Deletion log written; content backups exist for every entry deleted.
- Post-cleanup parse run: zero-analysis count unchanged or improved, duplicate-parse
  count reduced, parse time not worse.

## Common Failure Modes

- **Shape-based bulk delete without a category check** (C-M7-01) -- the corpus's
  canonical cleanup disaster, recovered by recreating the six deleted entries from a
  surviving sibling's wiring.
- **Deleting a senseful entry** without review (prevented by D-M7-02).
- **Deleting a still-referenced class or environment.**
- **Removing a required collection's only child** (D-M7-06).
- **A mid-operation failure in non-undoable write mode** leaving the lexicon
  half-converted, with no rollback: "the atomicity unit for this whole session is the
  SESSION, not the operation" (M5 §6, M6 §6, M8 §6). This is a standing hazard for
  every bulk operation in this stage.
- **Factory-seeded duplicate child nodes** left behind after building objects, found
  only by comparing against a known-good sibling (M7 ops 19-20).
- **Leaving both conventions in place** because the reconciliation was deferred
  (L-M6-01 -- still open).

## Automation Notes

**Automatable now:** the plan/mutate split, referrer counting, content backup,
duplicate detection, zero-usage detection, deletion logging, and post-hoc count
verification.

**Human required for:** the redundancy judgements and the convention reconciliation.

**Missing tooling (requirements):**
- **A transactional / rollback-capable write mode.** The non-undoable session-scoped
  atomicity is the single biggest risk in this stage and is flagged in three separate
  shards. Everything else here is a mitigation for its absence.
- **`redundancy_report()`** -- rule-derivable allomorphs, lexeme-form clones,
  zero-usage allomorphs, duplicate possibility items, orphaned contexts and
  environments, and classes with zero referrers, in one pass.
- **`convention_audit()`** -- for a named phenomenon, report how many entries use
  representation A, how many use B, and how many use both (mechanizing L-M6-01's
  count into a standing check).
- **A guarded bulk-delete primitive** that requires an explicit target list or a
  predicate *plus* a category filter, refuses senseful items by default, backs up
  content automatically, writes a log, and can be replayed in reverse (C-M7-01,
  D-M5-10, D-M7-02).
- **Referrer-aware deletion**: refuse to delete a referenced object and name the
  referrers.

## Provenance

- M1 op 35 (2026-09-11 12:10) -- 25 rule-derivable allomorphs pruned; op 41
  (allomorph usage audit).
- M2 op 4 (2026-09-10 19:50) -- NFC/NFD duplicate cleanup; C-M2-03.
- M3 ops 13-14, 25, 29, 32 (2026-09-11 17:14 .. 09-12 10:38); D-M3-07 ("fix it all");
  L-M3-05, L-M3-11, L-M3-15; M3 §6 (referrer check before delete).
- M5 ops 38, 61, 74-75 (2026-09-14 09:58, 12:21, 14:13-14:17); **D-M5-05, D-M5-10**;
  L-M5-07; C-M5-05; M5 §5 stage 9 "Destructive cleanup (retirement)".
- M6 ops 4, 33 (2026-09-14 16:02, 22:03); L-M6-01; C-M6-02.
- M7 ops 6, 10-15, 20, 27-29, 40-41 (2026-09-15 08:09 .. 11:40); **D-M7-02, D-M7-03,
  D-M7-04, D-M7-06, D-M7-07**; **C-M7-01**; L-M7-05; M7 §5, M7 §9.
- M8 ops 20-23 (2026-09-15 16:54-16:55) -- 101-entry bulk conversion with log file;
  D-M8-07; M8 §6, M8 §9.
- G1 §5 "Verify (step 5)" -- cross-theme regression check, language-independent per
  G1 §9.
- **Merge seam:** Matthew's cleanup cadence and his tolerance for redundancy.

## Open Questions

- The oblique allomorph-vs-variant-entry duplication was counted and never resolved
  (L-M6-01). Q-04.
- Whether every verb "that needs it" was converted in the final bulk pass (M8 §7).
  Q-14.
- Whether the abandoned "Enclitic onset" class was deleted or merely orphaned
  (M7 §7). Q-08.
- No cadence is stated for when cleanup should run. Q-27.
</content>
</invoke>
