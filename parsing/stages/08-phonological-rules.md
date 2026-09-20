# Stage 08 -- Phonological Rules

[Back to overview](../00-overview.md) | [Prev: Stage 07](07-allomorphy-modeling.md) | [Next: Stage 09](09-compounding-and-clitics.md)

## Purpose

Express general, cross-lexical sound alternations once as global phonological rules,
so that individual entries do not have to store every derivable surface allomorph --
and do it without destroying parse performance.

## Entry Criteria

- [Stage 04](04-natural-classes.md) complete for the classes the rules need.
- [Stage 07](07-allomorphy-modeling.md) has identified which alternations are general
  enough to be rules rather than stored allomorphs.
- Boundary markers available (word-internal and clitic).

## Inputs

- The alternation inventory, filtered to the general ones.
- Natural classes, phonemes, and boundary markers.
- A baseline parse time for the corpus (see Procedure step 7).

## Procedure

1. **Write one rule per phenomenon**, named in plain English, with its input, output,
   and left/right contexts stated.
2. **Build multi-element contexts fully before wiring them.** A sequence context whose
   members are not fully constructed first produces a null reference inside the wiring
   call (M1 op 28). Factory-created objects are orphans: own them into an owning
   collection *before* setting properties on them (M2 §6).
3. **Anchor every context to a boundary.** This is the hard rule of this stage:
   > "an unanchored environment is one whose right context is a bare natural class
   > with no boundary marker -- that is what makes rule un-application explode."
   > (L-M3-02)
4. **Widen coverage by adding another anchored right-hand side, never by dropping the
   anchor.** The corpus needed rules to fire across clitic boundaries as well as
   word-internal ones and added a second boundary-anchored right-hand side (L-M2-07);
   the *unanchored* right-hand side added at the same time is what caused the
   slowdown and was removed (M3 ops 3, 10-11).
5. **Scope a rule that should not be fully general.** The corpus took a general rule
   and reworked it into two scoped right-hand sides, gated by a dedicated inflection
   class and a rule feature, so that a lexical subset behaves differently (L-M7-03).
   Prefer this over duplicating the rule.
6. **Use exact per-segment environments when the members are not feature-separable.**
   The purpose-built natural class in the corpus was abandoned for four exact
   per-segment right-hand sides once feature comparison showed the members were
   indistinguishable (L-M7-03).
7. **Measure parse time before and after.** Ron treated it as a first-class metric:
   > "the parsing speed slowed down considerably after that last set of fixes. For
   > example [a long verb form] takes 9.6 seconds to parse ... Total parse time for all
   > 438 words was 4 minutes even." (D-M3-02)
   Record total corpus parse time and worst-case single-word time on every rule
   change.
8. **Delete the allomorphs the rule now derives.** The corpus pruned 25 redundant
   allomorphs after the global rules landed (M1 op 35) and later pruned rule-derivable
   clitic alternates (L-M3-05) -- leaving them produces duplicate parses.
9. **Do not remove the last remaining alternative of a required collection.**
   > `report.Warning("%s: '#' is its ONLY RHS -- not touching it")` (D-M7-06)
   Guard and warn instead.
10. **Plan first, mutate second**, removing indices in descending order (D-M7-03).
11. **Verify by read-back with concrete context casts**, checking inputs, outputs, and
    both contexts of every rule, and asserting zero malformed rules (M1 op 32).
12. **Re-check the FLEx application settings.** Whether phonological rules apply across
    clitics is a FLEx setting outside the data -- Ron restored the project specifically
    to flip it (D-M3-03). A rule that looks correct and does not fire may be gated
    there.

## Linguistic Decisions Required

- **Which alternations are rules and which are stored allomorphs.** The test in the
  corpus is generality: does the alternation hold across the lexicon given the right
  environment, or is it a property of particular lexemes? Per-lexeme irregularity was
  kept as a stored compound/oblique form rather than rule-ified (L-M6-07).
- **Where the rule's domain ends.** Word-internal only, or across clitic boundaries
  too (L-M2-07)? Is it fully general, or gated to a lexical class (L-M7-03)?
- **Whether the trigger segment survives the rule** (deletion vs replacement vs
  insertion).
- **Rule ordering / stratum.** The corpus checked compound-rule strata (M6 op 29) but
  never states an ordering policy for phonological rules.

The corpus's four-plus rules and their conditioning are in
[`reference/malayalam-morphophonology.md`](../reference/malayalam-morphophonology.md).
All are hypotheses; none is native-speaker verified.

## QC / Exit Criteria

- Every rule reads back with correct input, output, left context and right context.
- Zero malformed rules.
- **Every right-hand side is boundary-anchored** (or its lack of anchoring is an
  explicit, measured decision).
- Total corpus parse time and worst-case word parse time recorded, and not
  significantly worse than the pre-change baseline.
- Every allomorph the rules now derive has been deleted.
- Regression check: previously-parsing forms still parse (D-M3-01).
- No rule has had its only right-hand side removed.

## Common Failure Modes

- **Unanchored right context causing catastrophic parse-time blowup** (D-M3-02,
  L-M3-02). The defining failure of this stage.
- **Null reference when wiring a multi-element context** before its members are
  constructed (M1 op 28); orphan factory objects mutated before being owned (M2 §6).
- **Casting rejections** on rule and context properties (C-M3-03, C-M7-03).
- **Redundant stored allomorphs surviving the rule**, producing duplicate parses
  (L-M3-05).
- **Removing a rule's only right-hand side** (D-M7-06).
- **A rule that cannot fire because of a FLEx application setting**, not a data
  problem (D-M3-03).
- **Assuming a feature-based class is a usable environment** when its members are not
  feature-separable (L-M7-03).

## Automation Notes

**Automatable now:** rule creation, read-back verification, malformed-rule counting,
and anchored/unanchored classification.

**Human required for:** the rule-vs-allomorph call, domain decisions, and rule
ordering.

**Missing tooling (requirements):**
- **An unanchored-context lint.** Static: "rule R has a right-hand side whose context
  is a bare natural class with no boundary marker." This is a one-line check that
  would have prevented a 4-minute corpus parse time.
- **Parse-time instrumentation as a first-class metric**: total corpus time and
  per-word worst case, recorded per run and diffed against the previous run. Ron did
  this by stopwatch.
- **`rule_derives(rule, input_form) -> output_form`** -- apply a single rule to a
  string, in isolation, without a full parse. The corpus had no way to test a rule
  except by parsing.
- **A redundancy report**: stored allomorphs that a global rule already derives.
- Rule construction with context wiring handled (no orphan/ownership ordering for the
  caller to get wrong).
- Surfacing the FLEx "apply rules to clitics" setting through the MCP so a data-level
  diagnosis is not chasing an application-level cause (D-M3-03).

## Provenance

- M1 ops 28-32 (2026-09-11 11:37-11:41); D-M1-07; L-M1-01, L-M1-02, L-M1-03; M1 §5
  "Global phonological rules + feature-based natural classes"; M1 op 35 (redundant
  allomorph pruning).
- M2 op 9 (2026-09-11 14:31); L-M2-07; M2 §6 (context/ownership ordering).
- M3 ops 1-3, 10-11 (2026-09-11 14:59-16:06); **D-M3-02, D-M3-03**; L-M3-02, L-M3-05;
  C-M3-03.
- M6 ops 29, 34 (2026-09-14 16:49, 09-15 06:54); L-M6-10.
- M7 ops 21-35 (2026-09-15 09:52-10:35); D-M7-06; L-M7-02, L-M7-03; C-M7-03.
- **Merge seam:** Matthew may use metathesis or other rule types the corpus only
  enumerated (M6 L-M6-10 lists the available rule and context types).

## Open Questions

- No rule-ordering / stratum policy is stated anywhere in the corpus. Q-16.
- The content of the exhaustive phonological-rule dump at the end of M6 is not
  recoverable from the logs (L-M6-10, M6 §7). Q-17.
- What the acceptable parse-time budget actually is. Ron reacted to 9.6s/word and
  4min/438 words as unacceptable, but no target was set. Q-18.
</content>
</invoke>
