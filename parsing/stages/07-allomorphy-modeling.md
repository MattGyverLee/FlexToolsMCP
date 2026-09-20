# Stage 07 -- Allomorphy Modeling

[Back to overview](../00-overview.md) | [Prev: Stage 06](06-stem-and-affix-population.md) | [Next: Stage 08](08-phonological-rules.md)

## Purpose

For each alternation in the language, pick the right FLEx construct, apply it, and
apply it **uniformly** within the entry it applies to.

This is the stage where most of the corpus's effort, and nearly all of its rework,
went. **Read [`reference/flex-modeling-decisions.md`](../reference/flex-modeling-decisions.md)
before starting** -- it is the decision table this stage executes.

## Entry Criteria

- [Stage 06](06-stem-and-affix-population.md) complete: entries exist with their
  citation forms.
- [Stage 04](04-natural-classes.md) has the conditioning sets you need (or you will
  re-enter it).
- You have an inventory of the alternations you intend to model, each with: what
  varies, and what conditions it.

## Inputs

- The alternation inventory.
- Existing natural classes, environments, inflection classes, stem names, variant
  types -- **with referrer counts**.

## Procedure

1. **Classify each alternation by its conditioning, before choosing a construct.**
   The first question is always: is the conditioning **phonological** (a property of
   the adjacent segments), **grammatical** (a property of the morphosyntactic features
   being realized), or **lexical** (an arbitrary subclass of stems)? Getting this wrong
   is the root of the corpus's two largest rework cycles. Use the decision table in
   [`reference/flex-modeling-decisions.md`](../reference/flex-modeling-decisions.md).
2. **Prefer the cheapest construct that works**, in this order:
   plain allomorph -> plain allomorph + phonological environment -> inflection-class
   restriction -> stem name + inflection features -> variant entry -> affix-process
   rule -> global phonological rule. Escalate only when the cheaper device provably
   cannot express the conditioning.
3. **Do not mix representations on one entry.** An affix entry carrying both plain
   allomorphs and affix-process alternates will have the plain forms shadow the
   process rules:
   > "Convert every remaining plain affix allomorph into an affix process rule so each
   > entry matches the working LOC shape." (D-M1-10, C-M1-06)
   Treat plain-allomorph and affix-process representations as **mutually exclusive per
   entry**.
4. **If you convert alternates to process rules, check the citation form survives.**
   The lexeme form is not automatically a parseable alternate:
   > "Find affix entries whose lexeme form is dead because they have plain alternates,
   > and restore it as an explicit alternate." (D-M1-11, C-M1-05)
5. **Know that the lexeme form is the elsewhere case.** FLEx orders the lexeme form
   last, under the negation of every environment above it. So: constrain the
   *alternates* with environments and leave the true elsewhere form as the lexeme form.
   The corpus had to swap a lexeme form with its alternate to restore this
   (L-M3-13). This is a **FLEx architecture fact**, not a language fact.
6. **Constrain the elsewhere form too if it overgenerates.** A lexeme form left free
   will attach everywhere; the corpus constrained one to a specific stem-final class
   to stop it overgenerating (D-M3-06, L-M3-14).
7. **For each per-context subrule of an affix-process rule, decide explicitly whether
   the trigger segment is retained or replaced** -- and test that decision against a
   concrete surface form. Do not default to one behavior across all environments; the
   corpus shipped a "keep" where a "replace" was needed and it produced non-parsing
   output (C-M2-05, L-M2-03).
8. **Before restricting a previously-unrestricted allomorph, enumerate every class
   that legitimately needs it.**
   > "Widen the PAST allomorph restriction to ccu and ttu so tta-final past stems work
   > again." (D-M5-15, C-M5-06)
   A single-class restriction breaks sibling classes sharing the same environment.
9. **Inflection class is set on the MSA and is allomorph-global.** This is the key
   structural fact behind the corpus's final architecture:
   > "a non-past stem of a verb could get married with a NMLZ suffix or any past suffix
   > and be seen as valid since the inflection class on the verb applies to all
   > allomorphs. To mitigate this we could create a variant for past stems and add a
   > sense to that stem so that we can put the right inflection class on the msa
   > object." (D-M8-05)
   **If a stem needs different inflection-class behavior per allomorph, that allomorph
   must become its own lexical entry (a variant) with its own sense and MSA.** See
   [README Conflicts 4.1](../README.md#41-past-stem-alternation-stem-name-keyed-to-a-tense-feature-m4-vs-past-variant-entry-m8).
10. **Grammatically-conditioned stem selection still needs a stem name plus matching
    inflection features on the consuming affix.** A stem allomorph carrying a stem name
    is usable only when the affix realizes features matching one of that stem name's
    regions; an allomorph with no stem name is unrestricted (L-M4-04). And the feature
    objects on the affix must be **the same objects** the already-working affix uses,
    not newly created look-alikes (L-M6-04).
11. **Factor a class system along its true independent dimensions before growing it.**
    The corpus's three verb classes conflated past-stem shape with causative shape;
    once the causative was split out as its own affix entry, one dimension disappeared
    and the class count dropped (L-M3-11). Do this *before* the inventory grows.
12. **Prove the recipe on one exemplar, then siblings, then the class.**
    > "build the two GEN -yute rules as a proof of the recipe" (D-M1-09)
    > "Check 'do' and see if other suffixes in the template parse. If that works, apply
    > the same changes to the suffixes NMLZ.M, NMLZ.PL and TEMP.PST." then "change all
    > verbs to have the past variant in the pattern of 'do'" (D-M8-06, D-M8-07)
13. **Plan first, mutate second** for every structural edit, including surgery inside
    an affix-process rule's own input/output lists (D-M7-03, D-M7-04). Remove indices
    in descending order.
14. **Reuse the existing environment/class object** rather than creating a duplicate
    with the same string (D-M7-05).
15. **Check for factory-seeded default children** after creating a process rule --
    factories pre-seed elements, and the corpus found duplicate variable/copy nodes only
    by comparing a new rule side-by-side against a known-good sibling (M7 op 19-20).

## Linguistic Decisions Required

Every one of these is a linguistic claim that a native speaker should eventually
review. Record each with its status.

- **Conditioning type** per alternation (phonological / grammatical / lexical).
- **Whether an alternation is derivable by a global rule** -- if so it belongs in
  [Stage 08](08-phonological-rules.md) and the stored allomorph should be **deleted**
  (the corpus pruned 25 allomorphs made redundant by rules, M1 op 35, and pruned
  rule-derivable enclitic alternates, L-M3-05).
- **Whether two surface forms are one entry with allomorphs, or two entries.** Two
  affix-process rules with the same environment cannot both fire on one entry, so two
  co-existing spellings required two entries (L-M3-04).
- **Whether an irregular form is a suppletive stem or an irregular inflected form.**
  These take different FLEx constructs (D-M5-04, L-M5-03, L-M5-04).
- **Whether a subclass is semantic or phonological.** The corpus restricted a plural
  allomorph to a "Human" inflection class -- a grammatical/semantic subclass, not a
  natural class (D-M1-08, L-M1-05). Whether that class was ever actually needed for
  parsing was investigated and **not resolved** (L-M4-06).
- **Whether an "environment" is real.** 13 allomorphs flagged as environment-bearing
  turned out to carry empty strings (L-M8-04). Check the actual string.

See [`reference/allomorphy-environments.md`](../reference/allomorphy-environments.md)
for the corpus's allomorph sets and environment strings.

## QC / Exit Criteria

- Every alternation in the inventory has a chosen construct and a written reason.
- No entry mixes plain-allomorph and affix-process representations.
- Every affix entry's citation form is reachable as a parseable alternate.
- The elsewhere form of each alternating affix is the lexeme form.
- Every restriction added to a previously-unrestricted allomorph was preceded by an
  enumeration of all classes using it.
- No stored allomorph duplicates something a global rule already derives.
- No allomorph is a verbatim clone of its own entry's lexeme form (a guaranteed
  duplicate parse -- L-M3-05).
- Every affix-process rule is well-formed with no factory-seeded duplicate nodes;
  "malformed rules: 0".
- The change was proven on one exemplar before being scaled.
- A regression check confirms previously-parsing forms still parse (D-M3-01).

## Common Failure Modes

- **Plain allomorphs shadowing process rules on the same entry** (C-M1-06).
- **Citation form left unreachable after conversion** (C-M1-05).
- **Keep-vs-replace defaulted across environments** (C-M2-05).
- **Over-narrow restriction breaking sibling classes** (C-M5-06); **over-broad shared
  class edit** breaking the rest of the grammar (C-M5-05).
- **Inflection class on the stem applying to all allomorphs**, permitting non-past
  stems to take past suffixes (D-M8-05) -- the corpus's deepest bug.
- **A class-based restriction blocking a derived stem** that inherits its root's class
  (D-M4-01, L-M4-01) -- the mirror-image failure.
- **Right-context environments cannot distinguish homophonous suffixes**, and an
  environment pre-empts the lexeme form even when the alternate's string does not match
  the surface (L-M4-03). This is why grammatical conditioning must not be faked with a
  phonological environment.
- **Redundant allomorphs generating duplicate parses** (L-M3-05).
- **Sibling-interface confusion**: the same object exposes inflection-class membership
  on one interface and phonological environments on another (C-M4-01); and some
  properties exist on neither interface you guessed (C-M8-05).
- **Half-finished conversions** leaving a mixed population across the lexicon -- track
  which entries were converted, in a log file (M8 wrote `convert_log.txt`).

## Automation Notes

**Automatable now:** construct creation and bulk application; the uniformity check
(does any entry mix representations); citation-form reachability; clone-of-lexeme-form
detection; empty-environment detection; referrer enumeration before restriction.

**Human required for:** classifying conditioning type, and every linguistic decision
listed above.

**Missing tooling (requirements). This is the richest gap list in the spec:**
- **`explain_allomorph_selection(entry, surface_form)`** -- given a stem and a target
  surface form, report which allomorph the parser would select and why (which
  environment matched, which class permitted, which was pre-empted). Almost every
  debugging operation in the corpus is a hand-rolled approximation of this.
- **An allomorph-representation lint**: flag entries mixing plain and process
  alternates (C-M1-06); flag an unreachable citation form (C-M1-05); flag an allomorph
  identical to its entry's lexeme form (L-M3-05); flag an environment whose string is
  empty (L-M8-04).
- **`referrers_of(class | environment | inflection_class | stem_name)`**, surfaced
  automatically on any write that touches a shared object (C-M5-05, C-M5-06).
- **`restriction_impact(allomorph, proposed_classes)`** -- which entries currently
  using this allomorph would be excluded.
- **A rule-derivability check**: "this stored allomorph is derivable by phonological
  rule R; delete it?" -- mechanizing the corpus's redundancy pruning.
- **Affix-process rule construction as a single call** with the factory-seeded-node
  cleanup handled, plus well-formedness validation (M7 ops 19-20, C-M1-06).
- **A variant-vs-allomorph conversion primitive** (both directions), since the corpus
  did this conversion, reverted it, and later bulk-applied it 101 times.
- **Feature-object identity helper**: attach *the same* feature/value objects an
  existing affix uses, rather than creating equivalents (L-M6-04).

## Provenance

- M1 ops 33-38, 42-46 (2026-09-11 11:42 .. 12:48); D-M1-08, **D-M1-09, D-M1-10,
  D-M1-11**; L-M1-04, L-M1-05; C-M1-05, C-M1-06; M1 §5 "Non-concatenative allomorphy
  via affix-process rules", "Inflection class (Human)".
- M2 ops 10-13 (2026-09-11 14:32-14:36); L-M2-01..L-M2-05, L-M2-08, L-M2-09; C-M2-05;
  M2 §6.
- M3 ops 13-17, 24-32 (2026-09-11 17:14 .. 09-12 10:38); D-M3-06, D-M3-07; L-M3-04,
  L-M3-05, L-M3-09..L-M3-15; C-M3-03.
- M4 ops 1-2, 8 (2026-09-12 13:55, 23:20); **D-M4-01, D-M4-03**; L-M4-01, L-M4-03,
  L-M4-04, L-M4-06; C-M4-01, C-M4-03; M4 §5 "Class-restriction-to-environment bug fix".
- M5 ops 29-39, 59-60, 69-78 (2026-09-14 09:34 .. 14:21); **D-M5-03, D-M5-04, D-M5-14,
  D-M5-15**; L-M5-03..L-M5-06, L-M5-08, L-M5-09, L-M5-10; C-M5-05, C-M5-06; M5 §5
  stage 8.
- M6 ops 20-25 (2026-09-14 16:30-16:39); L-M6-01, L-M6-02, L-M6-04; C-M6-03.
- M7 ops 8-9, 19-20, 38-41 (2026-09-15 08:18 .. 11:40); D-M7-03, D-M7-04, D-M7-05,
  D-M7-07; L-M7-01, L-M7-04.
- M8 ops 7-25 (2026-09-15 16:40-17:08); **D-M8-05, D-M8-06, D-M8-07**; L-M8-01,
  L-M8-04, L-M8-05, L-M8-06; C-M8-05; M8 §5 "Root-cause diagnosis-then-generalize";
  M8 §9.
- **Merge seam:** this is the stage where Matthew's process is most likely to diverge.
  Capture his construct preferences as a second column in
  [`reference/flex-modeling-decisions.md`](../reference/flex-modeling-decisions.md).

## Open Questions

- Whether the "Human" inflection class is needed for parsing at all -- investigated in
  a dedicated read-only session and never answered in the logs (L-M4-06, M4 §7). Q-13.
- Why the -vu oblique stem-allomorph conversion was reverted; only the action is
  recorded (D-M7-07, L-M7-04). Q-04.
- Whether all 192 verb stem entries "that need it" were actually converted (M8 §7).
  Q-14.
- The conditioning of the long imperative allomorph was never specified (L-M5-10).
  Q-15.
</content>
</invoke>
