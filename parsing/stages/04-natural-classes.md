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
- **A class in an environment broader than the attested conditioning.** `/ _ [V]`
  claims every vowel conditions the allomorph. In the Swahili project such environments
  blocked regular forms until narrowed to the attested vowels: cl.2 `w-` to `/ _ a`,
  `/ _ e`, after which Waisraeli parsed (L-S9-07); ma-2 `m` to `/ _ e` for maovu
  (L-S10-06). Before writing a class into an environment, list the analyses that use
  the allomorph and the segments that actually follow it.

## Automation Notes

**Automatable now:** creation of both class kinds, membership computation from feature
bundles, referrer counting, and duplicate-membership detection.

**Human required for:** the shared-vs-dedicated judgement and the naming.

**Missing tooling (requirements):**
- **`natural_class_referrers(name)`** -- "what uses this, and what breaks if I change
  it". This single tool would have prevented C-M5-05. It should be *automatically*
  surfaced whenever a write touches an existing class.
  *Status 2026-10-09: open (T-10) -- no referrer API in flexicon and no MCP tool.*
- `propose_natural_classes()` -- scan all allomorph environments and phonological rule
  contexts, cluster identical conditioning sets, and report "this set is used by N
  allomorphs; it is/is not feature-definable" -- i.e. mechanize D-M3-05's threshold
  test.
  *Status 2026-10-09: open -- no tool or recipe (the `natural-classes` recipe lists
  classes and members only).*
- `check_class_distinguishability(members)` -- does the current feature system separate
  these from non-members? (L-M7-03.)
  *Status 2026-10-09: open -- the `phoneme-feature-uniqueness` recipe checks whole-bundle
  duplicates only.*
- A writing-system lint on environment `StringRepresentation` (D-M3-05).
  *Status 2026-10-09: open.*
- Duplicate-object detection across classes and environments (D-M7-05).
  *Status 2026-10-09: partial (T-16) -- `case-duplicate-entries` recipe and the
  `grammar_health` `duplicate-feature-bundle` check; no duplicate finder for
  environments or natural classes.*

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 come from one machine's logs (2026-05-21..09-11) and S6-S11 from the other's (09-12..09-30), which ran a pre-2.13.0 FlexToolsMCP main checkout. Those logs keep little or no tool output, so S6-S11 were re-checked (2026-10-09) against the Claude Code transcripts behind them, which hold the parse results, real counts and Matthew's verbatim words (mid-turn messages included) that the logs lost; tooling defects carry their current fix status. Sessions run by other clients (local models, a non-Claude agent, an unidentified non-Claude client on 09-30) count only as failure-mode evidence. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

- **ADDS: surface classes for rule outputs** (D-S1-03). When an archiphoneme exists,
  define `[-archi]` classes so a rule can state its output.
- **CONFIRMS feature-based classes, each justified by test words** (D-S2-03). The glide
  context `[Vnh] = [-high,+syl]` was justified in its docstring by hii, hivyo, mwana and
  kwenda.
- **CONFIRMS P8, with a replace-and-repoint recipe** (L-S1-03). Segment-based
  Vowels/Consonants were replaced by feature-based ones in five steps: list each old
  class's referrers; build the replacement; repoint every rule context; delete the old
  class; rename the new one.
- **ADDS a failure mode** (L-S2-01): removing a class from a context's member list
  without deleting the context leaves an orphan behind (a case for T-20).
- **ADDS: environment breadth is a failure source** (L-S9-07, L-S10-06). Two over-broad
  `[V]` environments were narrowed to attested vowels (cl.2 `w-`, ma-2 `m`), both
  parse-verified. A related case is not breadth but shadowing (L-S6-01): the cl.1
  object marker m-3 had an unconditioned `mu` beside `mw / _a,e,i,o`, and `mw` was
  never selected (0 uses, against 1-8 for `mw` on the other m- entries). Making `mu`
  the elsewhere lexeme form fixed the setup. No transcript re-checks *akamwita*: the AI
  had no parse tool on 09-12 and asked Matthew for Try A Word five times (C-S6-05).
- **REVISES D-S2-03** (glide context; "rules fire only across +") (V-S7-05, L-S7-06,
  V-S9-07, L-S9-06, T-S9-08, L-S10-02, C-S10-08).
  - On 09-13 the glide rule turned the root `u` of a-ta-mu-u-a into *atamuwa*, and
    about 150 verb roots ending in u or i mis-glided. Matthew chose "Add left context to
    the rule" over "Disable rules, list allomorphs instead" (35 prefix edits), so the
    glide and coalescence contexts got a `[Consonants]` left context and a parallel
    word-initial RHS (8 -> 20 contexts; L-S7-06). His FLEx parse confirmed *atamuua*
    within minutes (V-S7-12). A further right-context fix was dropped after counting the
    29 stems it would break (C-S7-15). Eight CV roots (ju, tu, ku, chu, vu, li, zi, ti)
    still mis-glide; FLEx has no per-morpheme exception for a rule short of exception
    features (L-S7-17).
  - On 09-24 the rule still turned mi+aka into *myaka (miaka, 214 tokens, unparsed).
    Which RHS was responsible was not established: narrowing the left context to exclude
    `m`, on one RHS and then both, left miaka unparsed, and only disabling the whole rule
    fixed it (V-S9-07, refined by transcript). A 2,139-word sandbox A/B with the rule
    disabled finished: 1,517 -> 1,568 parsed, 54 fixed, 3 broken (T-S9-08).
  - The real conditioning was morphological (class-4 mi- does not glide, vi- does), so
    no natural-class context could state it. The 09-24 sandbox result argued for
    disabling the rule and adding allomorphs; the 09-25 fix, made in a fresh chat
    without that result, was a lexical exception feature
    ([Stage 03](03-phonological-features.md); C-S10-08). The project's later linguist
    spec agrees: gliding is "conditioned by the morpheme, not by phonology" (L-S10-09).
    When the conditioning set is a list of morphemes, a natural class is the wrong
    device ([Stage 07](07-allomorphy-modeling.md), [Stage 08](08-phonological-rules.md)).
- **CONFIRMS P8 (count dependents before changing a shared context)** (L-S9-06,
  L-S10-02). Before touching glide formation the agent counted the parsed words that
  depend on each output: 7 of 3,312 analyses on 09-24; ny 572, vy 383, py 11, my 8 on
  09-25. The 09-24 count missed affix homographs: it found the class-8 prefix's `vy-`
  allomorph but not that the subject prefix `vi-2` has none, and the sandbox regression
  showed disabling the rule breaks vyombo and vyanzo (L-S9-06, L-S9-09). Count by
  morpheme, not by form.

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
- **Merge seam:** Merged from S1-S11 (both machines) -- see Second-Operator Evidence above. Membership reconciliation across the two projects does not apply (different languages).
  *(Original seam: Matthew's naming convention and threshold may differ; his classes will need reconciling against these by *membership*, not by name.)*

## Open Questions

- Is four the right threshold, or was it incidental to the case Ron was looking at?
  (D-M3-05 says "each set of 4" about a specific situation.) Q-07.
- Whether the "Enclitic onset" class was actually deleted after being abandoned, or
  merely left unused (M7 §7). Q-08.
