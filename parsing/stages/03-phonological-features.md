# Stage 03 -- Phonological Features

[Back to overview](../00-overview.md) | [Prev: Stage 02](02-phoneme-inventory.md) | [Next: Stage 04](04-natural-classes.md)

## Purpose

Give every phoneme a distinctive-feature specification, so that natural classes
(Stage 04) can be defined by feature conjunction rather than by hand-maintained segment
lists, and so that phonological rules (Stage 08) can refer to classes.

This stage is deliberately **after** the inventory is stable (D-M1-01, D-M2-05) --
features assigned to an inventory that is still changing will be re-done.

## Entry Criteria

- [Stage 02](02-phoneme-inventory.md) complete and frozen: inventory size and
  membership will not change under you.
- A candidate feature set (preferably from the standard feature catalog).

## Inputs

- The full phoneme inventory.
- A feature catalog (the SIL/MGA-style catalog shipped with FLEx).
- A source-of-truth assignment table: phoneme x feature -> value. **Keep this outside
  the database**, in a versioned data module or JSON, because you will need it to
  diff and restore (see Failure Modes).

## Procedure

1. **Prefer catalog-sourced binary features over ad hoc ones.** The corpus went
   through three iterations and converged on catalog-linked binary (+/-) features
   (D-M1-05). Create them with the catalog source id so provenance is recorded
   (M1 §6). Do not invent feature names that shadow catalog ones.
2. **Prefer a fully specified matrix over a minimal one.** The corpus first assigned
   only the specs needed to distinguish phonemes, then replaced that with a matrix
   where every phoneme carries every feature (D-M1-05, 475 -> 1088 specs). Rationale:
   once natural classes are defined by feature conjunctions, an unspecified feature is
   an accidental class boundary.
3. **Prove the invariants before writing.** Two checks, run on the source table, and
   the write is refused if either fails (D-M1-04):
   - **Distinctiveness**: all phonemes pairwise distinguishable.
   - **Non-redundancy / minimality**: no single feature-value spec is droppable.
     (This check is what *justifies* the minimal matrix; once you move to a fully
     specified matrix, run distinctiveness on the full matrix and minimality on the
     distinguishing subset, so you still know the feature set is not bloated.)
4. **Dry-run first**, then execute (P5). The corpus used `validate_only` before the
   binary-feature replacement (M1 op 21).
5. **Read back and verify**: catalog linkage present, total spec count matches the
   source table exactly, all phonemes still pairwise distinct, feature value names and
   definitions preserved (M1 ops 22-23).
6. **Retire features that carry no load.** The corpus removed one feature outright once
   it was found unnecessary (D-M1-06, the `back` feature).
7. **Re-verify after any human GUI edit.** See Failure Modes.

## Linguistic Decisions Required

- **Which feature inventory.** Catalog-standard is strongly preferred; the corpus's
  own first attempt at custom multi-valued features was abandoned (D-M1-05).
- **Binary vs multi-valued.** The corpus converged on binary.
- **Where non-segmental marks sit in the feature space.** The corpus put the
  vowel-killer mark on the non-consonantal side of the primary consonant/vowel
  partition (L-M1-06), and defined the nasalization mark by a `[+cons -syl +lab]`
  conjunction (L-M2-06). Both are **modeling hypotheses**, chosen because they made
  the needed classes definable -- not native-speaker facts.
- **Which feature is load-bearing.** The corpus's primary consonant/vowel partition was
  a single feature carrying 68 specs; when it was deleted the whole class system
  collapsed. Know which features are structural.

## QC / Exit Criteria

- Every phoneme carries a spec for every feature (fully specified matrix).
- Total spec count equals inventory size x feature count, and equals the source table.
- All phonemes pairwise distinct.
- Every feature is catalog-linked, with its value names and definitions intact.
- No feature exists that no class or rule references (or its retention is justified).
- A scripted diff of the live matrix against the source table reports zero
  differences.

## Common Failure Modes

- **Manual GUI deletion of a feature silently wipes that spec from every phoneme.**
  This happened: Ron deleted one feature in the FLEx GUI and a diagnostic found all 68
  specs for it gone project-wide (D-M1-06). The recovery pattern is the lesson: run a
  **scripted diff against the canonical source table before resuming automated
  writes**, then restore from the table, then re-verify. Deletions cascade silently
  through the feature-spec collections.
- **Assigning features before the inventory is frozen**, forcing a redo.
- **A minimal matrix producing accidental natural classes** -- an unspecified feature
  makes a phoneme match a class it should not.
- **Hallucinated wrapper class names** for the feature API (C-M1-03, C-M2-04,
  C-M3-01). The feature surface was reached through the project accessor, not an
  `Operations` import.
- **Features that look distinguishable but are not.** M7 op 34 compared matra feature
  bundles and found them indistinguishable by feature structure -- which killed a
  planned natural class (L-M7-03). Test before you rely on a feature distinction.

## Automation Notes

**Automatable now:** catalog feature creation, bulk spec assignment, full read-back
verification, and both invariant proofs -- the corpus implemented all of these as a
pre-write gate.

**Human required for:** choosing the feature inventory and deciding where
non-segmental marks sit.

**Missing tooling (requirements):**
- `assign_feature_matrix(table)` with the distinctiveness + minimality proof built in
  as a **refusal gate**, not a script the caller has to remember to write.
- `diff_feature_matrix(table)` -- the exact thing that diagnosed the GUI-deletion
  incident, promoted to a tool.
- A **referrer report** for features and feature values: "what breaks if this is
  deleted", surfaced *before* the deletion, including from the GUI if possible.
- A distinguishability report: "these N phonemes are not separable by the current
  feature set" and "these features are never used by any class or rule".

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 come from one machine's logs (2026-05-21..09-11) and S6-S11 from the other's (09-12..09-30); both machines' Swahili logs are now ingested. Logs before 09-23 keep no tool output, so their results are partly inferred; later logs keep truncated output. Sessions run by other clients (local models, a non-Claude agent, an unidentified weaker client) count only as failure-mode evidence. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

- **Answers Q-06: Matthew uses features** -- feature-based natural classes, alpha-feature
  rules, and a full matrix (S1). Q-06 is not closed: a language may still manage
  without them, but this second project did not try.
- **ADDS a step-1 variant: import the whole catalog, then add only what it lacks**
  (D-S1-02): `ImportCatalog`, then a custom `archi` (+/-). Simpler than choosing
  catalog ids one at a time, at the cost of a pruning pass later.
- **CONFIRMS step 2 (fully specified) with a compact idiom** (D-S1-05): write each
  phoneme's matrix as its list of "+" features and default every other feature to "-".
- **ADDS: prune the feature set later, against what uses it** (D-S3-09; see
  [Stage 13](13-cleanup-and-consolidation.md)). Mark each feature LOCKED (some natural
  class or rule uses it) or FREE (only the inventory does). Search exhaustively over the
  FREE features for the largest set you can drop while every phoneme's feature bundle
  stays unique. Delete behind gates, then re-verify that classes and rules are unchanged.
  This turns D-M1-04's minimality proof into a whole-feature procedure. It can only run
  *after* Stages 04 and 08, so it belongs in cleanup, not here.
- **ADDS: catalog provenance applies to inflection features too** (D-S3-01) -- see
  [Stage 05](05-categories-and-templates.md).
- **S6-S11 add no phonological-feature work.** The feature evidence in those shards is
  about inflection features ([Stage 05](05-categories-and-templates.md): one sense per
  agreement value, exact-value unification, the dropped `NA` filler) and rule exception
  features (below).
- **ADDS a third feature kind: lexical exception features** (L-S10-02, C-S10-05). A
  "no glide formation" exception feature, excluded on both RHSs of a rule and set on
  three stems, blocked the rule for those stems only (miaka, mianzo then parsed).
  Creating it took raw LCM after four failed attempts; no wrapper exists. Use it when
  the conditioning is lexical or morphological, not phonological -- see
  [Stage 08](08-phonological-rules.md).

## Provenance

- M1 ops 18-26 (2026-09-11 09:39 .. 11:10); D-M1-04, D-M1-05, D-M1-06; L-M1-06;
  M1 §5 "Phonological feature system construction (3 iterations)"; M1 §6.
- M2 op 8 (2026-09-11 14:29); L-M2-06; C-M2-04.
- M3 L-M3-01 (feature-bundle definition of a class), C-M3-01.
- M7 op 34 (2026-09-15 10:33), L-M7-03.
- **Merge seam:** Merged from S1-S11 (both machines) -- see Second-Operator Evidence above (Q-06 answered for this project: features used). S6-S11 contain no further phonological-feature construction.
  *(Original seam: Matthew may skip features entirely and use segment-list classes only. If so, record the trade-off explicitly -- it changes Stage 04 and Stage 08.)*

## Open Questions

- Was the move from minimal to fully specified ever validated against parse behavior,
  or was it an a-priori preference? The shards record the change (D-M1-05) but not a
  measured effect. Q-05.
- Whether a project can skip Stage 03 entirely and build only segment-list natural
  classes. The corpus used both kinds throughout. Q-06.
