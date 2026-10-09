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
   *Status 2026-10-09: partial -- inflection classes are wrapped from flexicon 4.12.0
   (creating one with `InflectionClassCreate(name, pos=...)` is fixed on flexicon main,
   not yet released, flexicon#631); a rule's required/excluded rule features can be
   read (`PhonRules.GetRequiredRuleFeatures`) but not written, so that step is still
   raw LCM.*
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
13. **Measure a rule's blast radius before changing it** (second operator, L-S9-06,
    L-S10-02, C-S7-15). Count the stored analyses that depend on each of the rule's
    outputs (7 of 3,312; ny 572, vy 383), and the words in the rule's context, before
    disabling, narrowing or excepting it. This is P8 applied to rules. Count affix
    homographs too: the stored-analysis count said only *vyangu*, *vyombo* and *vyote*
    needed the glide rule because "the class 8 prefix already has a *vy-* allomorph",
    but the subject prefix `vi-2` has none, and the sandbox showed *vyombo* and
    *vyanzo* break without the rule (L-S9-09). The same count works in reverse: an AI
    dropped its own right-context glide fix before writing it, because it would have
    broken 29 stems that need the glide (C-S7-15).
14. **Test a rule change off-project first** (T-S9-08): parse a baseline set (a regex
    over wordforms for the rule's context, plus top-N frequent words), edit, re-parse,
    diff. A `no_change` diff on the targeted set means the edit missed. Done this way on
    09-24 with `flextools_parse_sandbox`: narrowing the glide rule changed none of 181
    targeted words; disabling it moved a 2,139-word set from 1,517 to 1,568 parsed (54
    fixed, 3 broken, 16 changed). Carry such a result into the next chat: the next
    morning's fix ignored it (C-S10-08).
15. **Verify a rule edit by reopening the project, not by an in-op read-back**
    (C-S9-02). A rule disable read back as done inside the op never persisted ("I set it
    four times; it takes effect inside each run but never reaches disk"); the agent then
    stopped and asked, which is right. In the same session the verification parses ran
    on a stale parse worker that had loaded the project before the edits (C-S9-01,
    C-S9-07), so "fresh" means a fresh open **and** a fresh parse worker. Disable a rule
    with `project.PhonRules.SetDisabled(rule, True)` (flexicon 4.12.0, flexicon#572),
    not the raw cast path of T-S9-07.
    *Status 2026-10-09: partial -- the wrapper is transactional, the teardown
    AbandonedMutexException handling is partly fixed (FlexToolsMCP #302: mutex
    recovered, `writes_committed` reported), and the idle parse worker now drops its
    lock, with `flextools_parse_release` to end it (#223/#225, 2.13.0). No one has proved
    a disable persists across a reopen and no reopen-verify exists (T-71). Keep the
    reopen check.*
16. **Read boundary markers from the project's phoneme set** (D-S7-15). An AI dump
    printed `#` for every boundary and misread a rule until Matthew corrected it: "+ is
    the marker for morph boundary in FLEx".

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
[`reference/example-agglutinative-suffixing.md`](../reference/example-agglutinative-suffixing.md).
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
- Every rule edit confirmed by a fresh project open, and its targeted-set diff
  finished and recorded (C-S9-02, T-S9-08).

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
- **A "general" rule that is really morpheme-specific**: the glide rule applied to a
  prefix the language exempts (`mi-`) and blocked a frequent noun for months (V-S9-07,
  L-S10-02, L-S10-09). Which part was at fault is not established: narrowing the left
  context of one right-hand side, then both, left *miaka* unparsed; only removing the
  whole rule fixed it. Check every right-hand side, and test the change, rather than
  trusting a reading of the rule.
- **A rule edit that does not persist** although the op reported success (C-S9-02).
  *Status 2026-10-09: partial -- mitigated by `PhonRules.SetDisabled` (4.12.0) and
  #302; cause never pinned down, persistence across reopen unproven.*
- **A stale parse worker** verifying an edit against the grammar it loaded before the
  edit (C-S9-01, C-S9-07). The agent blamed shared mode first; the edits were on disk.
  *Status 2026-10-09: the idle worker drops its lock and `flextools_parse_release`
  exists since 09-24 (#223/#225); end the worker before re-verifying.*

## Automation Notes

**Automatable now:** rule creation, read-back verification, malformed-rule counting,
and anchored/unanchored classification.

**Human required for:** the rule-vs-allomorph call, domain decisions, and rule
ordering.

**Missing tooling (requirements):**
- **An unanchored-context lint.** Static: "rule R has a right-hand side whose context
  is a bare natural class with no boundary marker." This is a one-line check that
  would have prevented a 4-minute corpus parse time.
  *Status 2026-10-09: still open (T-12) -- `flextools_grammar_health`'s nearest checks
  are `unbounded-quantifier` and `epenthesis-empty-struc-desc`.*
- **Parse-time instrumentation as a first-class metric**: total corpus time and
  per-word worst case, recorded per run and diffed against the previous run. Ron did
  this by stopwatch.
  *Status 2026-10-09: partial -- `flextools_parse_text` records `parse_time_ms` per
  word and `try_word bound_seconds` gives a bounded measurement (FlexToolsMCP 2.13.0);
  `flextools_parse_diff` does not compare timing (T-07).*
- **`rule_derives(rule, input_form) -> output_form`** -- apply a single rule to a
  string, in isolation, without a full parse. The corpus had no way to test a rule
  except by parsing.
  *Status 2026-10-09: partial -- `flextools_parse_sandbox` (2.13.0) parses whole words
  against an edited copy of the grammar without touching the project; no single-rule
  application (T-32).*
- **A redundancy report**: stored allomorphs that a global rule already derives.
  *Status 2026-10-09: partial -- audit recipes `overpowered-allomorphs` and
  `find-overpowered-affixes`; nothing checks rule derivability (T-20).*
- Rule construction with context wiring handled (no orphan/ownership ordering for the
  caller to get wrong).
  *Status 2026-10-09: shipped for one RHS -- `PhonRules.WireRule(..., left_context=,
  right_context=)` wires multi-element and NC/boundary contexts, `PhonRules.MakeConstraint`
  covers alpha features; adding a second RHS has no wrapper.*
- Surfacing the FLEx "apply rules to clitics" setting through the MCP so a data-level
  diagnosis is not chasing an application-level cause (D-M3-03).
  *Status 2026-10-09: still open (T-41).*
- Wrappers to disable or narrow a rule and to create rule / exception features; the
  second operator needed raw LCM, failed casts and several retries for each
  (T-S9-07, C-S10-05).
  *Status 2026-10-09, per part: disable shipped in flexicon 4.12.0
  (`PhonRules.SetDisabled`, flexicon#572); narrow partial (`PhonRules.WireRule` sets
  contexts; `SetLeftContext` refuses by design, no RHS input-POS setter); exception
  feature create fixed on flexicon main, not yet released (after 4.12.0)
  (`InflectionFeatures.ExceptionFeatureCreate/Find/GetAll`, flexicon#631); tagging
  stem MSAs shipped in 4.12.0 (`MSA.AddExceptionFeature`, flexicon#574); rule features
  still open -- readers only (`PhonRules.GetRequiredRuleFeatures/GetExcludedRuleFeatures`),
  no creator and no writer for ReqRuleFeats/ExclRuleFeats.*
- A working rule sandbox: `parse_sandbox` worked on 09-24 (a finished 2,139-word A/B
  run, T-S9-08) but crashed on 09-25 on a missing packaged script while health
  reported it ready (T-S10-05; possibly after that day's editable reinstall, T-S10-12,
  unproven). See the tooling list in MERGE-NOTES section 4.
  *Status 2026-10-09: the crash is fixed -- the script is package data since 06f90a8
  (09-24), and an unreadable script returns `sandbox_unavailable` (#322, PR #361,
  2026-10-04). Still open, no issue filed: `flextools_health` reports the sandbox
  `ready` without checking `hcparse.ps1`.*

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 and S6-S11 cover the logs of both machines. S6-S7 logs keep no tool output; S8 from 09-23 and S9-S11 do (truncated). The Claude Code transcripts behind S6-S11 supply the missing output, numbers and Matthew's own words where they exist (checked 2026-10-09). Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

- **ADDS an LCM fact** (L-S2-01): each member of a `PhSequenceContext` is a reference,
  so it must first be **owned by `PhPhonData.ContextsOS`**. Otherwise you get "Object
  has not been initialized".
- **ADDS: alpha-feature place assimilation for an archiphoneme** (D-S1-03): `N̲`
  becomes a consonant agreeing in place / _ + C, with `[-archi]` surface classes for
  the output.
- **CONFIRMS boundary anchoring, from the opposite starting point** (C-S1-07, D-S2-03).
  The first rules had no boundary and, in one case, no context at all. They were
  rewritten to fire only across "+" ("a+i -> e", "i -> y / _ + V"). The second project
  arrived at Ron's L-M3-02 independently.
- **CONTRADICTS P1 ordering: rules written before any stem existed** (S1). The rules
  were created hours before they were wired up, and the wiring failed until the
  underlying LCM rule object was used (C-S1-08). One output-class change was never
  tested. A rule nobody parses against is unverified.
- **ADDS: test words in the docstring** (D-S2-03). Every narrowed context names the
  words it was narrowed for.

*S6-S11:*

- **ADDS: the rule-vs-allomorph sentence** (D-S6-07, L-S7-08). Matthew first floated
  the concord shapes as "more broadly ... phonological rules", then narrowed it:
  "phonological rules are for very broad phenomena, but allomorphs and affix process
  rules are for morphophonemics specific to an affix." Language-wide N-place
  assimilation stays a rule; affix-specific shapes are allomorphs. CONFIRMS Ron's
  generality test (L-M6-07).
- **ADDS: the 09-13 glide repair was parser-checked by Matthew** (L-S7-06, V-S7-05,
  V-S7-12, L-S7-17, L-S7-18). The rule glided root-final vowels too (*atamuua* ->
  *atamuwa*; 150 verb roots end in `u` or `i`). Offered "add left context to the rule"
  or "disable rules, list allomorphs instead" (35 prefix edits), Matthew chose the
  first: the RHSs became `[C] __ + [Vnh]` and `# [C] __ + [Vnh]`. He then ran the FLEx
  parser himself: "atamuua looks good", and *kuwa* lost its spurious *ku-u-a* reading.
  The AI's 09-12 claim that the glide rule only duplicated stored allomorphs was wrong:
  10 prefixes carry the glided form, 35 depend on the rule. Residue: eight CV roots
  (*ju, tu, ku, chu, vu, li, zi, ti*) still mis-glide; the AI then said FLEx has no
  per-morpheme rule exception, which the 09-25 exception feature disproved.
- **REVISES D-S2-03** ("rules fire only across +") (L-S9-06, V-S9-07; tool output).
  The glide rule also produced *myaka* from `#mi+aka`, so *miaka* (214 tokens) failed
  to parse until 09-25; the 09-13 consonant left context did not stop it. Narrowing it
  further to exclude `m`, in one right-hand side and then both, changed nothing in the
  sandbox; why is unexplained. Disabling the rule fixed 54 words and broke 3 (T-S9-08).
  The 09-25 linguist spec judges gliding morpheme-conditioned (`vi-` -> `vy`, `mi-`
  stays) and wrong as one rule in both directions (it yields *kwona*, misses *mwili*),
  so by Matthew's own sentence it belongs in allomorphs (L-S10-09). Matthew approved
  that redesign among 11 options on 09-25 (D-S10-16); it was never executed.
- **ADDS: lexical exception feature to block a rule** (L-S10-02, L-S10-07, C-S10-08).
  The fix that landed was an exception feature excluded on both right-hand sides and set
  on three stems; *miaka*, *mianzo*, *myema*, *vyakula* then parsed. It was only
  spot-checked ("I didn't reparse the whole corpus"), and the chat that made it never
  saw the previous night's sandbox recommendation (disable the rule, add `vy / _ V` to
  `vi-2`). Open: the conditioning is the cl.4 prefix, not the stems, so tagging stems
  does not scale. The prefix route looks closed in HermitCrab: by a source read
  (untested), a stem's `ProdRestrictRC` becomes an exception, but an affix's
  `FromProdRestrictRC` becomes a *required* feature.
  *Status 2026-10-09: the feature was created through raw LCM after five attempts
  (C-S10-05); creation is fixed on flexicon main, not yet released
  (`InflectionFeatures.ExceptionFeatureCreate`, flexicon#631). Stem tagging is
  `project.MSA.AddExceptionFeature` (4.12.0). Exception features on an affix MSA
  (`side="from"/"to"`) are fixed on flexicon main, not yet released (flexicon#630); in
  4.12.0 those calls silently do nothing on affixes.*
- **ADDS: blast radius, sandbox, reopen** (Procedure 13-15 above; L-S9-06, T-S9-08,
  C-S9-02). The sandbox A/B regression did finish (23:54, after the log ends), and its
  result was then lost between chats; the rule disable never persisted. The lesson: a
  rule change is not done until a fresh open, a fresh worker and a finished diff say
  so, and the diff is carried into the decision.
  *Status 2026-10-09: the lesson stands. Disable is now `PhonRules.SetDisabled`
  (flexicon 4.12.0); persistence across reopen is unproven (mitigations: #302). The
  sandbox's warm worker between runs is still open (FlexToolsMCP #242).*
- **CONFIRMS P1 / [README 4.9](../README.md) the hard way.** The S1 glide rule, written
  before any stem existed (C-S1-08), was still breaking class-4 nouns four months later
  (V-S9-07). Rules must be built and tested against stems.
- **CONFIRMS parse time as a first-class cost** (D-S10-05, T-S10-02). At about 3.2 s
  per word a 1,783-word baseline needs about 95 minutes; both 09-25 baseline runs died
  at word 173 when the MCP server restarted, and the agent stopped. `grammar_health`
  reports a phoneme representation-variant product of 1.8e10. Size baselines to parse
  time and run them in chunks.
- **Open: glide modelled twice** (S6 Conflicts 4). Ten prefixes carry stored glide
  allomorphs and 35 rely on the rule; `vi-2` relies on it without saying so. Whether to
  delete the rule (and add the missing allomorphs) is a
  [Stage 13](13-cleanup-and-consolidation.md) "delete what the rules derive" question,
  in the opposite direction; the sandbox result above is the evidence to start from.

## Provenance

- M1 ops 28-32 (2026-09-11 11:37-11:41); D-M1-07; L-M1-01, L-M1-02, L-M1-03; M1 §5
  "Global phonological rules + feature-based natural classes"; M1 op 35 (redundant
  allomorph pruning).
- M2 op 9 (2026-09-11 14:31); L-M2-07; M2 §6 (context/ownership ordering).
- M3 ops 1-3, 10-11 (2026-09-11 14:59-16:06); **D-M3-02, D-M3-03**; L-M3-02, L-M3-05;
  C-M3-03.
- M6 ops 29, 34 (2026-09-14 16:49, 09-15 06:54); L-M6-10.
- M7 ops 21-35 (2026-09-15 09:52-10:35); D-M7-06; L-M7-02, L-M7-03; C-M7-03.
- S6-S11: D-S6-07; L-S7-06, L-S7-08, L-S7-17, L-S7-18, D-S7-15, C-S7-15, V-S7-05,
  V-S7-12; L-S9-06, L-S9-09, C-S9-01, C-S9-02, C-S9-07, T-S9-07, T-S9-08, V-S9-07;
  L-S10-02, L-S10-07, L-S10-09, D-S10-05, D-S10-16, C-S10-05, C-S10-08, T-S10-02,
  T-S10-05, T-S10-12. Results and attributions checked against the Claude Code
  transcripts.
- **Merge seam:** Merged from S1-S11 (both machines). No rule-ordering policy appears in Matthew's logs either (Q-16 stays open). Open: how to stop glide formation on `mi-` -- the stem exception feature now in place, disabling the rule plus a `vy` allomorph on `vi-2` (sandbox-tested, 54 fixed / 3 broken), or morpheme-specific allomorphs (linguist spec, approved, not executed). *Status 2026-10-09: an affix-MSA exception feature gets a wrapper once flexicon#630 is released, but HermitCrab appears to read it as a requirement, not an exception (L-S10-07, untested), so the prefix option is probably not viable.*
  *(Original seam: Matthew may use metathesis or other rule types the corpus only enumerated (M6 L-M6-10 lists the available rule and context types).)*

## Open Questions

- No rule-ordering / stratum policy is stated anywhere in the corpus. Q-16.
- The content of the exhaustive phonological-rule dump at the end of M6 is not
  recoverable from the logs (L-M6-10, M6 §7). Q-17.
- What the acceptable parse-time budget actually is. Ron reacted to 9.6s/word and
  4min/438 words as unacceptable, but no target was set. Q-18.
