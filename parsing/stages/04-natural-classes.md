# Stage 04 -- Natural Classes

[Back to overview](../00-overview.md) | [Prev: Stage 03](03-phonological-features.md) | [Next: Stage 05](05-categories-and-templates.md)

## Purpose

Create the named, maintainable conditioning sets that allomorph environments
(Stage 07) and phonological rules (Stage 08) refer to -- and, just as importantly,
establish the discipline of **when not to create one**.

Ron's standing directive, restated as the operative rule across roughly eight
subsequent operations:

> "would it work to make a natural class of each set of 4 that would be easier to
> maintain. If it works, give it an English name, remember this, if there is just one
> environment (thus not helpful to make a natural class) and it uses a vernacular
> letter, the whole environment should be in the vernacular WS, otherwise I get boxes."
> (D-M3-05)

## Entry Criteria

- [Stage 03](03-phonological-features.md) complete if you intend feature-based classes.
- [Stage 02](02-phoneme-inventory.md) complete if you intend segment-list classes.
- You know which conditioning sets you actually need -- which usually means you have
  already been through Stage 07 or Stage 11 once. **This stage is re-entered
  constantly.**

## Inputs

- The feature matrix and/or the phoneme inventory.
- The set of conditioning environments currently in use, with how many allomorphs or
  rules reference each.

## Procedure

1. **Count the users before creating.** A class earns its existence when the same
   conditioning set is shared by **four or more** allomorphs (D-M3-05). Below that
   threshold, use a literal environment.
2. **Give it a descriptive English name and a short abbreviation.** Names in the
   analysis WS. The corpus's names are readable by a human maintainer
   ("Post-augment case onset", "Plural final chillu", "Nya-past stem final") -- this is
   the maintainability payoff being claimed.
3. **Choose segment-list vs feature-based deliberately.**
   - **Feature-based** when the set is a genuine phonological class expressible as a
     feature conjunction, and you want it to track future inventory additions
     automatically.
   - **Segment-list** when the set is a list of specific graphemes that happens to
     recur, with no coherent feature definition.
   - **Verify the feature conjunction actually picks out the intended members** by
     computing membership from the feature bundles and printing it (M2 op 8). And
     verify the members are *distinguishable at all*: M7 op 34 found four matras
     indistinguishable by feature structure, which is why the planned class was
     dropped for four exact per-segment environments (L-M7-03).
4. **Before extending an existing class, check its referrers.** This is a hard rule,
   bought at the cost of an explicit mid-session reversal:
   > "Revert the shared PsF change and add a dedicated nnu past class with its own
   > allomorph and environment." (D-M5-14, C-M5-05)
   Adding one phoneme to a shared class changed behavior project-wide. If the fix
   applies to one lexical subclass, use a **dedicated inflection class plus a literal,
   non-shared environment** instead.
5. **Reuse existing objects rather than duplicating.** Look up and reuse the existing
   environment/class object with the same semantics rather than creating a second one
   with the same string (D-M7-05).
6. **Writing-system discipline for environment strings.** If an environment is a
   one-off (not worth a class) and contains a vernacular character, author the
   **entire** environment string in the vernacular writing system -- mixing writing
   systems inside one environment string renders as boxes in FLEx (D-M3-05). This is a
   real, user-visible data-quality rule.
7. **Retire classes that became unused.** Check the referrer count first; do not delete
   a class or environment that is still referenced (M3 §6).
8. **Re-verify membership after any inventory change** (Stage 02 re-entry).

## Linguistic Decisions Required

- **Is this set a natural class or a list?** The honest answer is sometimes "a list",
  and the corpus has both: feature-definable classes (consonant, vowel, syllabic) and
  frankly stipulative ones named after their function rather than their phonology
  ("Case suffix onset", "Post-augment case onset", "Plural final chillu"). Functional
  naming is legitimate and was Ron's practice; do not pretend a stipulative set is a
  phonological class.
- **Shared vs dedicated scope.** The central judgement of this stage. See
  [`reference/natural-classes.md`](../reference/natural-classes.md) for the decision
  procedure and the corpus's classes.
- **Whether a class is the right device at all**, versus an inflection class
  (grammatical conditioning) or a stem name. See
  [`reference/flex-modeling-decisions.md`](../reference/flex-modeling-decisions.md).

## QC / Exit Criteria

- Every class has an English descriptive name and an abbreviation.
- Feature-based class membership has been **computed and printed**, and matches intent.
- No class exists with fewer than the threshold number of referrers without a stated
  reason.
- No two classes have identical membership (duplicate-semantics check).
- Every one-off vernacular environment string is wholly in the vernacular WS -- verify
  visually in FLEx, not just programmatically: the failure mode is a rendering
  artifact.
- Referrer counts recorded for every class, so Stage 13 can retire dead ones.

## Common Failure Modes

- **Extending a shared class to fix a local problem** (C-M5-05). The single most
  expensive class-related mistake in the corpus.
- **Creating a class whose members are not actually distinguishable** by the feature
  system you have (L-M7-03).
- **Duplicate classes/environments** with the same semantics created by different
  sessions or by the human in the GUI (D-M5-05, D-M7-05).
- **Mixed-writing-system environment strings** rendering as boxes (D-M3-05).
- **Feature-based vs segment-based confusion at the API level** -- adding phonemes to a
  feature-based class throws (C-M1-01); a hallucinated operations-class import
  (C-M2-04).
- **Deleting a class still referenced** by an allomorph or rule.

## Automation Notes

**Automatable now:** creation of both class kinds, membership computation from feature
bundles, referrer counting, and duplicate-membership detection.

**Human required for:** the shared-vs-dedicated judgement and the naming.

**Missing tooling (requirements):**
- **`natural_class_referrers(name)`** -- "what uses this, and what breaks if I change
  it". This single tool would have prevented C-M5-05. It should be *automatically*
  surfaced whenever a write touches an existing class.
- `propose_natural_classes()` -- scan all allomorph environments and phonological rule
  contexts, cluster identical conditioning sets, and report "this set is used by N
  allomorphs; it is/is not feature-definable" -- i.e. mechanize D-M3-05's threshold
  test.
- `check_class_distinguishability(members)` -- does the current feature system separate
  these from non-members? (L-M7-03.)
- A writing-system lint on environment `StringRepresentation` (D-M3-05).
- Duplicate-object detection across classes and environments (D-M7-05).

## Provenance

- M1 op 28 (2026-09-11 11:37) -- feature-based classes created, segment-based retired;
  L-M1-01/02/04/06; C-M1-01.
- M2 op 8 (2026-09-11 14:29); L-M2-06; C-M2-04; M2 §6.
- M3 ops 3, 20-24, 27, 31-32 (2026-09-11 15:08 .. 09-12 10:38); **D-M3-05** (the
  governing directive); L-M3-01, L-M3-07, L-M3-08, L-M3-09, L-M3-14; M3 §6.
- M4 op 3 (2026-09-12 17:02) -- classes extended plus new ones created; L-M4-01.
- M5 ops 57, 73-75, 77-78 (2026-09-14 12:17 .. 14:21); **D-M5-14**, D-M5-15;
  C-M5-05, C-M5-06; L-M5-09.
- M6 op 32 (2026-09-14 22:02) -- class membership dump during diagnosis; L-M6-01.
- M7 ops 31-35 (2026-09-15 10:24-10:35); D-M7-05; L-M7-03.
- **Merge seam:** Matthew's naming convention and threshold may differ; his classes
  will need reconciling against these by *membership*, not by name.

## Open Questions

- Is four the right threshold, or was it incidental to the case Ron was looking at?
  (D-M3-05 says "each set of 4" about a specific situation.) Q-07.
- Whether the "Enclitic onset" class was actually deleted after being abandoned, or
  merely left unused (M7 §7). Q-08.
</content>
</invoke>
