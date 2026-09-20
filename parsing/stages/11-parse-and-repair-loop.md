# Stage 11 -- Parse and Repair Loop

[Back to overview](../00-overview.md) | [Prev: Stage 10](10-paradigm-text-construction.md) | [Next: Stage 12](12-real-corpus-stress-test.md)

## Purpose

Run the grammar against the test texts, triage what it gets wrong in **both**
directions -- under-generation (forms that do not parse) and over-generation (forms
that parse too many ways, or parse that should not) -- fix, and regression-check.

This is the heart of the process. It is not a verification step at the end; it is the
loop the rest of the stages serve.

> "The goal is to be able to use the FLEx Parser to parse the paradigm words."
> (D-M2-04)

> "use the parsing capability we solved in the session named 'HermitCrab command line
> parsing' and parse all the words in the pronoun paradigm text" (D-M5-06)

> "iterate to see how good you can get it." (D-M6-01)

**Note on how this stage is written.** In the corpus, parsing was invoked out of band:
either through the FLEx GUI parser, or through a HermitCrab command-line capability
solved in a separate session, with the failure list exchanged outside the tool
(M5 §7 item 4). FLExToolsMCP is gaining parsing tooling based on that HermitCrab CLI
solution. **This stage is therefore written as it should work with in-MCP parsing**,
and the Automation Notes double as the requirements list for that tooling.

## Entry Criteria

- [Stage 10](10-paradigm-text-construction.md) complete: at least one test text
  exists whose intended forms are known.
- The grammar compiles / the parser runs at all.
- A baseline: which wordforms currently parse, how many analyses each has, and the
  parse time.

## Inputs

- The test text(s) and the intended surface form for every cell.
- The current grammar (lexicon + templates + classes + environments + rules).
- The previous run's results, for regression comparison.

## Procedure

1. **Parse the whole text and capture the result per wordform**: number of analyses,
   and for each analysis the morpheme breakdown (which entry, which allomorph, which
   slot). Also capture **total parse time and worst-case per-word time**
   (D-M3-02) -- see [Stage 08](08-phonological-rules.md).
2. **Partition the results into four buckets.**
   - **A. Zero analyses** -- under-generation. The primary failure bucket.
   - **B. Exactly one analysis** -- nominally correct; still check the breakdown is the
     *intended* one, not an accidental alternative path.
   - **C. Multiple analyses** -- split further in step 4.
   - **D. Parsed but should not have** -- over-generation. Only findable by inspecting
     breakdowns or by deliberately testing illicit forms.
3. **Triage bucket A systematically, not one form at a time.**
   > "more words not parsing, mainly nouns. [a specific form] isn't parsing. is that
   > the plural. check it out and others that didn't parse" (D-M2-07)
   A user-reported form is a **seed for a sweep**, not a one-off fix. Enumerate all
   zero-analysis wordforms, group them (by text, by suffix, by stem-final class), and
   look for the shared cause. The corpus's standard diagnostic sequence:
   1. list zero-analysis wordforms, grouped;
   2. dump every relevant affix entry's alternates and process-rule inputs/outputs;
   3. dump the morpheme breakdowns of the *working* near-neighbours;
   4. dump the global phonological rules and natural-class membership;
   5. compare a working form against a near-identical failing one, field by field
      (M2 §5, M6 op 31);
   6. count how often each stored allomorph is used across all analyses, to find the
      ones that are never usable (M1 op 41).
   The last two are the highest-yield moves in the whole corpus.
4. **Triage bucket C by morpheme signature.**
   > "104 words have more than 1 parse. [X], for example seems to have two identical
   > parses. Others like [Y] have ambiguous parses one with IMP and one with PAST.
   > That's ok if those are true ambiguities in the language. Review and see why we are
   > getting duplicate parses." (D-M3-04)
   **Group multi-analysis wordforms by morpheme signature.** Analyses with the *same*
   signature are duplicates and are defects. Analyses with *different* signatures are
   genuine ambiguity and must be preserved (L-M3-06). The known duplicate sources:
   - an alternate allomorph that is a verbatim clone of its own entry's lexeme form;
   - a stored allomorph that a global phonological rule independently derives;
   - a form reachable both as a separate entry and as an allomorph of another entry
     (L-M3-05, M1 op 35).
5. **Triage bucket D by reasoning about what the constraints permit.** Over-generation
   is invisible in a parse report of attested forms; you find it by asking what the
   model permits that the language does not. Ron found the corpus's deepest bug this
   way, unprompted by any failure:
   > "the downside of this, I think is that a non-past stem of a verb could get married
   > with a NMLZ suffix or any past suffix and be seen as valid since the inflection
   > class on the verb applies to all allomorphs." (D-M8-05)
   Also check for an elsewhere/lexeme form attaching where it should not (D-M3-06).
6. **Fix at the right level.** Route the finding to the stage that owns it:
   missing conditioning set -> [04](04-natural-classes.md); missing entry or
   missing derived data -> [06](06-stem-and-affix-population.md); wrong construct or
   wrong restriction -> [07](07-allomorphy-modeling.md); rule too narrow, too wide, or
   unanchored -> [08](08-phonological-rules.md); clitic/compound
   -> [09](09-compounding-and-clitics.md).
7. **Rebuild cleanly rather than patching incrementally** when a set of rules has
   drifted. The corpus deleted all the affix-process rules on seven suffixes and
   rebuilt them as an ordered, mutually exclusive set rather than patching each
   (M2 op 11) -- this is what made them reviewable as a single design.
8. **Regression-check every fix.**
   > "Fix it, but verify the others that are working will still parse." (D-M3-01)
   Compare the full bucket partition against the previous run, not just the target
   forms. A fix that moves a form from A to B while moving three others from B to A is
   a net loss.
9. **Re-measure parse time** (D-M3-02).
10. **Iterate.** Ron's authorization for this is explicit: *"iterate to see how good
    you can get it"* (D-M6-01). The loop terminates when bucket A is empty, bucket C
    contains only genuine ambiguity, and no known over-generation remains.

## Linguistic Decisions Required

- **Is this multi-parse a genuine ambiguity or a defect?** The single most frequent
  linguistic judgement in this stage (D-M3-04, L-M3-06). Requires knowing whether the
  homophony is real in the language -- which, for a language the analyst does not
  speak, is exactly where a native speaker is needed.
- **Is this form actually attested?** A failing form may be a bad test case (L-M5-02).
- **Should the model permit this?** Bucket D is pure linguistic judgement.
- **Is this over-generation harmful?** Some over-generation is tolerable in a parsing
  lexicon; unconstrained over-generation destroys parse precision and inflates parse
  time.

## QC / Exit Criteria

- Zero-analysis count is zero on the target text (or every remaining failure has a
  recorded reason).
- Every multi-analysis wordform is classified as duplicate (fixed) or genuine
  ambiguity (accepted, with the ambiguity recorded).
- Bucket B breakdowns spot-checked: the parse is via the *intended* morphemes.
- Known over-generation enumerated and either fixed or accepted with a reason.
- No allomorph has a usage count of zero across all analyses without a reason
  (M1 op 41).
- Parse time within budget; not regressed versus the previous run.
- Regression: the previous run's successes are all still successes.

## Common Failure Modes

- **Fixing the reported form instead of the class.** D-M2-07's discipline exists
  because the reported form is one instance of a systematic gap.
- **Treating all multi-parses as bugs** and destroying genuine ambiguity (D-M3-04).
- **Fixing under-generation into over-generation.** The corpus's PAST-allomorph cycle
  went unconstrained -> over-narrow (broke a sibling class) -> widened, in three steps
  over eight minutes (D-M5-14, D-M5-15, C-M5-06).
- **Fixing over-generation into under-generation.** The mirror: a class-based
  restriction blocked derived stems that inherit their root's class (D-M4-01,
  L-M4-01).
- **A fix that tanks parse time** (D-M3-02).
- **Diagnosing at the data level a problem that is at the application level** -- a
  FLEx setting gated whether rules applied to clitics (D-M3-03).
- **Losing the failure list.** In the corpus the parse results lived outside the tool,
  so they are not recoverable from the logs (M5 §7). Persist them.
- **Not verifying the last fix.** The corpus's final action has no follow-up
  spot-check (M8 §9).

## Automation Notes

**This is the stage FLExToolsMCP's new parsing tooling exists to serve.** Everything
below is a requirement.

**Automatable now (partially):** enumerating wordforms and their analysis counts,
dumping morpheme breakdowns, counting allomorph usage across analyses, comparing a
working entry against a failing one, and all the structural dumps. The corpus did all
of this in hand-written snippets, repeatedly.

**Human required for:** the ambiguity judgement and the "should the model permit this"
judgement.

**Missing tooling (requirements for the in-MCP parsing capability):**
1. **`parse_text(text) -> per-wordform results`** in-band: analysis count, and per
   analysis the full morpheme breakdown (entry, allomorph, slot, MSA), plus timing.
   No out-of-band exchange. This closes M5 §7 item 4.
2. **`parse_forms([surface_forms])`** -- parse an ad hoc list without creating a text,
   for quick hypothesis testing.
3. **`parse_diff(previous_run, current_run)`** -- the regression check of D-M3-01 as a
   first-class operation: what newly fails, what newly passes, what changed analysis
   count.
4. **Automatic bucket partition** (zero / one / duplicate-signature / distinct-signature
   multi), with multi-analysis grouping by morpheme signature -- mechanizing D-M3-04's
   distinction.
5. **`explain_parse_failure(surface_form)`** -- the highest-value missing tool in the
   entire spec. Given a form that should parse and does not, report how far the parser
   got: which stem allomorph matched, which suffix was attempted, which environment or
   inflection-class restriction rejected it, which rule did or did not apply. Every
   diagnostic operation in M1, M2, M3, M5 and M8 is a hand-rolled partial version of
   this.
6. **`allomorph_usage_report()`** -- usage count per stored allomorph across all
   analyses; zero-usage allomorphs are dead weight or a bug (M1 op 41).
7. **Over-generation probing**: given a paradigm, generate the forms the grammar
   *permits* and diff against the attested cells. Bucket D is currently invisible
   without this.
8. **Parse-run persistence**: store each run's results so runs can be diffed and so
   the failure list is not lost.
9. **Parse timing surfaced per run and per word**, with a diff against the previous
   run (D-M3-02).
10. **Failure-to-stage routing hints**: classify a failure by the kind of object that
    blocked it, so step 6 above can be suggested rather than reasoned out each time.

## Provenance

- M1 ops 7, 39-45 (2026-09-10 18:48; 09-11 12:36-12:47) -- simulated parse, failure
  triage, allomorph usage audit, root cause; M1 §5 "Verify-by-simulated-parse".
- M2 ops 6-14 (2026-09-11 14:11-14:36); **D-M2-04, D-M2-07**; M2 §5 "Parser-failure
  diagnosis".
- M3 ops 1, 12-14, 18 (2026-09-11 14:59-19:29); **D-M3-01, D-M3-02, D-M3-04**;
  L-M3-05, L-M3-06; D-M3-03.
- M4 ops 1-2, 8 (2026-09-12) -- parse defects driving construct changes; L-M4-03.
- M5 ops 40-41, 52-53, 63 (2026-09-14 10:37-13:50); **D-M5-06**, D-M5-12; M5 §5
  stage 7 "HermitCrab parse-driven QC loop"; M5 §7 item 4.
- M6 op 1 and throughout; **D-M6-01** ("iterate to see how good you can get it");
  ops 29-34 diagnosis.
- M7 §9 (converged practice: verification-after-mutation is standard).
- M8 ops 7-25; **D-M8-05** (over-generation found by reasoning, not by a failure
  report); M8 §9.
- **Merge seam:** Matthew's parse-triage practice, and whether he uses the FLEx GUI
  parser, HermitCrab CLI, or the new in-MCP tooling. His bucket definitions and
  acceptance thresholds should be captured alongside these.

## Open Questions

- What the acceptance threshold is. The corpus never states one; "as good as you can
  get it" (D-M6-01) is the only guidance. Q-23.
- Whether the corpus ever reached 100% on any text is not confirmed in the logs
  (M1 §7, M5 §7). Q-24.
- Over-generation was never systematically measured, only reasoned about. Q-25.
</content>
</invoke>
