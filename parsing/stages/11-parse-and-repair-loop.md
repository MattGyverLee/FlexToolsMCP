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

**Note on how this stage is written.** In Ron's corpus, parsing was invoked out of band:
either through the FLEx GUI parser, or through a HermitCrab command-line capability
solved in a separate session, with the failure list exchanged outside the tool
(M5 §7 item 4). **This stage is written as it should work with in-MCP parsing.**
That tooling now exists: `flextools_try_word` (one word, three levels),
`flextools_parse_text` (batch parse of a word list or corpus scope, with two-step
filing of parser results into the project), `parse_status` / `parse_log` (async
handles and persisted run records, including traces), `parse_diff` (run-to-run
regression), `parse_sandbox` (parse an exported copy of the grammar without touching
the project), `parse_release` (drop the parse worker's project lock) and
`grammar_health` (static scan for path-multiplying grammar properties). Matthew's
Swahili work from 2026-09-23 onward (S8-S11) used them on a real corpus; the
Automation Notes below record which requirements they met and which are still open.

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

0. **Confirm the failure live before repairing it.** Stored analysis state (a
   wordform's parser analyses, `ParserCount`) records the last parse run, not what the
   current grammar does. Parse the candidates now (`try_word` for a handful,
   `parse_text` for a queue) and drop the ones that parse. In the Swahili corpus 9 of
   the top 10 "unparsed" words parsed on first try (D-S10-01), one refile with no
   grammar change cleared 4,836 wordforms (L-S10-01), and one day spent about four
   hours repairing ten words that all parsed (C-S11-06, L-S11-01).
1. **Parse the whole text and capture the result per wordform**: number of analyses,
   and for each analysis the morpheme breakdown (which entry, which allomorph, which
   slot). Also capture **total parse time and worst-case per-word time**
   (D-M3-02) -- see [Stage 08](08-phonological-rules.md).
2. **Partition the results into four buckets.**
   - **A. Zero analyses** -- under-generation. The primary failure bucket.
   - **B. Exactly one analysis** -- nominally correct; still check the breakdown is the
     *intended* one, not an accidental alternative path. "Parsed" is not "correct":
     a high analysis count on a short word (10-13 on a two-syllable noun, L-S10-05)
     is an over-generation signal, not a success.
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
   Before adding lexicon for a failing word that already has an entry, check whether
   its POS, **or any ancestor POS**, owns a template with an obligatory slot that the
   word cannot fill. Parse rate of whole-word stem entries grouped by POS is a cheap
   screen: a POS far below the others has a template problem, not a lexicon problem
   (L-S9-01, L-S9-02, L-S9-03 -- about 3,000 tokens unblocked without one new entry).
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
   a net loss. Use a recorded run and `parse_diff`, not a remembered count
   (T-S9-03: "fixed 3, broken 0, unchanged 17").
   Close every batch explicitly: test -> diff -> file the parser results for the
   touched wordforms (including case variants) -> re-list the queue. Words that were
   test-parsed but never filed stay at the top of the queue (C-S9-05, D-S10-10).
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
- Every word fixed in a test parse has had its parser results filed, and the queue
  has been re-listed from the filed state (C-S9-05).

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
- **Repairing words that already parse**, because the work list came from stale
  stored analyses (C-S11-06, L-S8-01). See step 0.
- **Many changes in one write.** A 12-change operation failed half-way; the next
  parse could not be attributed to any one change (C-S9-04). One kind of change per
  write, parse-check between.
- **Parsing from inside a script instead of with the parse tools.** Parser calls in
  `run_module` were blocked as writes or returned unreadable traces; the dedicated
  tools answered the same question in two minutes (T-S11-01, T-S11-02).

## Automation Notes

**This is the stage FLExToolsMCP's parsing tooling exists to serve.** The list below
began as Ron's requirements; it now records, per item, what shipped and how it
behaved in Matthew's Swahili runs (S7-S11, FlexToolsMCP 2.12.0 logs, 2026-09-13 ..
09-30). Requirement ids are in [MERGE-NOTES §4](../MERGE-NOTES.md).

**Automatable now:** live parsing of single words and word lists, filing parser
results, run-to-run diffs, sandboxed grammar edits, and parse traces with rejection
histograms -- plus everything Ron's corpus did in hand-written snippets (wordform
enumeration, breakdown dumps, allomorph usage counts, working-vs-failing comparison,
structural dumps).

**Human required for:** the ambiguity judgement, the "should the model permit this"
judgement, and the decision to **file** parser results into the project (D-S10-04:
filing withheld even with write mode on; C-S10-02: a 26,725-word filing
self-confirmed 21 s after its preview).

**How the tooling arrived.** S1-S6 had no parse tool in the loop: the FLEx GUI parser
at the keyboard (S1-S5), then an agent exporting TSVs to build its own offline
template simulator (T-S6-02). On 09-13 the main session found it could load
`HCParser` inside `run_module` and drove HermitCrab by hand for probe lists, a
24-form baseline and an 858-wordform before/after (T-S7-01). That is the origin of
the dedicated tools. Four subagents the same night never found it and deferred
changes as "cannot be verified without running the parser" -- the loop must be
reachable by whoever writes (D-S7-02).

**Requirement status (in-MCP parsing):**
1. **In-band `parse_text` with per-analysis breakdown** (T-01). *Partly met.*
   `parse_text` exists and works on word lists and corpus scopes (20-word queues,
   a 1,783-word baseline). It returns counts (`NumZeroParses`, `TotalAnalyses`), not
   the per-analysis morpheme breakdown; agents read stored WfiAnalysis bundles instead,
   which may be stale (T-S10-03, T-S11-03). A request for "full parse results with
   morphological decomposition" was never met (D-S11-04).
2. **Ad hoc list parsing** (T-06). *Met* by `try_word` (one word) and `parse_text`
   on a word list. Most calls exceed the grace window and return a handle to poll
   (5-40 s per word on this grammar, T-S10-02); that worked once agents polled.
3. **`parse_diff`** (T-03). *Met, underused.* It gave decisive regression verdicts
   ("fixed 3, broken 0"; sandbox "no_change", T-S9-03), but a grammar-wide stage
   planned its regression as manual re-parses instead (T-S10-07).
4. **Automatic bucket partition** (T-04). *Missing.* Over-generation shows up in filed
   analyses (Misri 10, mwana 13, L-S10-05) and nothing groups them by signature.
5. **`explain_parse_failure`** (T-02). *Partly met* by the `try_word` ladder:
   `plain` says only *that* a word failed; `restricted` tests a stated decomposition
   (`hypothesis_held`) quickly; `explain` writes a full trace, and `parse_log`
   section=trace summarises it as a rejection histogram with the first failing rule
   (T-S11-01, L-S11-03). Gaps: the reason lives in the trace, not the response
   (T-S9-01); `restricted` needs exact headwords with homograph numbers and morph
   markers (`mi-1`, `*aka`) and offers no candidates (T-S8-02, T-S9-02, T-S10-01);
   for a word that parses, `explain` gives counts but no breakdown (T-S11-03).
6. **Allomorph usage report** (T-19). *Missing.* Hand-rolled six times in one session
   (T-S6-06); a never-selected allomorph was the key signal there (L-S6-01).
7. **Over-generation probing** (T-22). *Missing.* The manual substitute was paradigm
   texts plus "No Parse" texts of forms that must fail (D-S7-08); string-concatenation
   generators produced non-words (C-S7-05).
8. **Parse-run persistence** (T-05). *Met with defects.* Runs persist by id under
   `parse-runs/` from 09-24. `parse_log` could not find `try_word` runs that
   `parse_status` had just reported (T-S10-04); traces were later pruned (T-S9-01);
   the operation log truncates output at 1-2 KB (T-43).
9. **Parse timing** (T-07). *Partly met.* Per-word time is visible through polling and
   `grammar_health` reports the representation-variant product (1.8e10 here,
   T-S10-02); there is no per-run timing diff. Size regression sets to parse time
   (about 6 s/word, D-S10-05).
10. **Failure-to-stage routing hints.** *Partly met:* trace rejection types
    (`inflFeats`, `noTemplatesApplied`, `partialParse`, `requiredInflType`, `pos`)
    point at the blocking object type (L-S11-02, L-S11-03). No routing to a stage.

**Added by the Swahili runs:**
11. **Filing.** `parse_text` with apply: preview ("may delete up to N analyses"),
    then confirm with a plan id, a backup per filing, parser-agent evaluations only
    (T-S9-04, T-S10-06). Worked; one failure gave no reason (C-S9-05).
12. **Sandbox for rule changes** (T-32 in spirit). `parse_sandbox` let a rule edit be
    baselined, edited and diffed without touching the project (T-S9-08). On 09-25 it
    crashed on a missing packaged script while `flextools_health` reported it ready
    (T-S10-05). No XML-edit helper and no write-back path.
13. **Lock hygiene.** A finished parse worker keeps the project lock; writes then fail
    `project_locked` with only a python PID named. `parse_release` exists but was
    never suggested and never called (T-S8-04, T-S9-05). Loop order: parse ->
    `parse_release` -> write.
14. **Parser calls inside `run_module`** are classed as writes and the fix offered is
    a write guard, not "use `flextools_try_word`" (T-S11-02).

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md); S1-S5 and S6-S11 are the logs of two machines and together cover the project. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an earlier S1-S5 claim. S6-S7 logs keep no tool output, and S8 (09-23) onward keep truncated output. Sessions run by other clients (local models in OpenCode, an unidentified weaker client in S10) are cited only as failure-mode evidence.*

**Parser used -- it changed over the project:**
- **S1-S5 (to 09-11):** the FLEx GUI parser, run by Matthew at the keyboard. Results
  reached the MCP only as stored analyses ("analysis state is static until FLEx
  reparse", D-S2-06). The gaps of 14-60 minutes between operations match reparse
  breaks (inferred).
- **S6 (09-12):** still no parse tool in the loop; read-only subagents exported TSVs
  to simulate templates offline (T-S6-02), and no reparse of the motivating word is
  logged after about eight grammar writes (C-S6-05).
- **S7 (09-13):** HermitCrab driven by hand inside `run_module` (`HCParser.ParseWord`)
  for probe lists, a 24-form baseline and an 858-wordform before/after (T-S7-01).
  Results are not in the log.
- **S8-S11 (09-23 .. 09-30):** the in-MCP tools -- `try_word`, `parse_text` with
  filing, `parse_diff`, `parse_sandbox`, `grammar_health`. Results are in the log.

- **ADDS a layer the spec lacks: analysis approval and word glosses** (D-S4-02,
  D-S5-06; [README 4.14](../README.md)).
  - In bucket B/D, **reject** each wrong analysis by GUID with a linguistic reason
    ("v prefix on num stem (num has no slots)"). Then trace it to the entry that
    licensed it and fix that entry (D-S4-03: six malformed affix entries).
  - Repair glosses in three stages:
    1. Pick the analysis whose morph signature matches, link each morph's sense, set the
       word gloss, approve it, and point the text token at it.
    2. Hand-build analyses only for forms with no correct parse.
    3. Delete competing analyses that no other text references.
  - Exit check: **no wordform left with zero live analyses** after rejections.
- **ADDS: an approval policy** (C-S2-01). Never record a heuristic judgement
  ("fewest morphemes wins") as a *Human* approval. Never disapprove genuine
  ambiguity -- H5 applies to approvals too.
- **ADDS: a slot-usage census as a decisive test** (D-S4-04). Count how often each slot
  is used across every analysis in the project. "ClassPrefix appears in ZERO analyses
  project-wide" localised a whole class of failures in one operation. This is the
  slot-level twin of M1 op 41's allomorph count.
- **ADDS a mechanical bucket-D check** (L-S4-01). Compare the feature names on zero (and
  other) affixes with those on the stems.
  - An affix whose features share no feature name with any stem never clashes, so it
    attaches everywhere.
  - An affix value that no stem carries (class 16) has no legitimate use.
  - This is a concrete, automatable case of T-22.
- **ADDS: re-check stored analyses after any template change** (D-S5-03). Group the
  stored analyses by slot sequence and list the shapes the current grammar forbids
  (Obj without TAM). Old parser output goes stale. Also: never conclude "the parser
  ignores X" from analyses that predate the last reparse (C-S2-05).
- **ADDS: a one-variable experiment for the human to reparse** (D-S4-09). Change only
  `*sungura` (bound to free) and leave `*fisi` untouched as a control. It is cheaper
  and more decisive than a fix-everything pass.
- **ADDS a duplicate source to step 4** (L-S4-03): duplicate lexical entries or senses
  with identical grammatical info (three `mu` object markers; `ambia`/`ambi`). Group
  multi-analyses by entry+sense+grammatical info, not by gloss string.
- **ADDS a template check for bucket D** (D-S5-01). A two-subject parse means the
  template is not blocking something it should -- look for an affix sitting in two
  slots that co-occur ([row 30](../reference/flex-modeling-decisions.md)).
- **Failure modes:**
  - Comparing post-reparse counts with a hardcoded baseline ("was 116") instead of a
    recorded run (C-S4-04).
  - Hand-built analyses with no reparse logged afterwards (C-S5-04).

*S6-S11 (this machine, 2026-09-12 .. 09-30):*

- **REVISES the S1-S5 reading of "zero analyses"** (D-S2-06, D-S3-02, C-S2-05 ->
  L-S8-01, V-S8-01, L-S10-01, V-S10-01, L-S11-01). Stored zero-analysis counts were
  mostly stale: the top three "unparsed" words parsed under `try_word` on 09-23, 9 of
  the top 10 on 09-25, all 10 on 09-30, and an all-texts refile with no grammar change
  moved 14,096 -> 9,260. Hence procedure step 0. A cheaper bucket: checksum 0 with no
  analyses means never parsed against this grammar, not failed (L-S6-05).
- **ADDS a two-fork triage order** (D-S6-01, D-S6-02). Segment one high-frequency
  failure by hand and look each morph up over lexeme forms **and** allomorphs. If all
  exist, walk the grammar: templates and slots; each affix's slot assignment and
  slotless affix senses; slot usage; allomorph usage; environments, natural classes,
  rules.
- **ADDS: check the template before blaming the lexicon** (L-S9-01, L-S9-02,
  L-S9-03, V-S9-06). Free words failed because their POS or an ancestor POS owned a
  template with obligatory slots. Fixes were structural: move a subcategory to the top
  level, give it its own minimal template, or make a template-less POS for invariant
  words. Morph type is part of this: a free pronoun typed as bound stem fails
  (D-S9-03).
- **CONFIRMS step 3's allomorph-usage count** (L-S6-01, L-S9-07). An object-marker
  allomorph that no analysis ever selected exposed a swapped lexeme/alternate
  arrangement; an environment written as a natural class (`/ _ [V]`) blocked a
  regular form until narrowed to the attested vowels. V-S9-05 also settles C-S2-05:
  alternate forms *are* matched by the parser.
- **CONFIRMS bucket B/D: parsed is not correct** (L-S10-05, V-S10-07, L-S11-02).
  Null-prefix stacking gives 8-13 analyses on short nouns; `try_word` "parsed: true"
  hides it. Inspect the analyses of any word above a small count.
- **CONFIRMS step 8 (regression), with Matthew's mechanics** (D-S7-06, T-S9-03,
  D-S10-05). Structural changes were staged: prototype on a hand-marked subset,
  revert when unmarked items broke, classify the population from evidence, write in
  batches against a fixed parse baseline and diff, then convert atomically with a
  probe list and full-corpus before/after. The 09-25 baseline was the top frequent
  *parsed* words plus words containing the targeted segments.
- **ADDS: measure blast radius before touching a shared rule, and prefer the
  narrowest fix** (L-S9-06, L-S10-02). Count stored analyses that depend on the rule
  (7 of 3,312; ny 572, vy 383 ...), then block the one bad case (an exception feature)
  rather than rewrite the rule. Test rule edits in a sandbox: baseline -> edit ->
  rerun -> `parse_diff` (T-S9-08).
- **ADDS: filing is the loop's closing step and a separate gate** (C-S9-05, D-S10-10,
  D-S10-04, C-S10-02). File only wordforms containing touched morphemes, case variants
  included. Matthew withheld filing explicitly in a grammar-wide stage even with write
  mode on.
- **ADDS the `try_word` ladder** (T-S9-01): `plain` for yes/no, `restricted` with an
  explicit hypothesis (fast, decisive), `explain` last. Summarise the trace's reason
  into the conversation; the log does not keep it.
- **CONFIRMS P3/P6 by a counter-example** (C-S9-04): one 12-change write failed
  half-way and its parse result could not be attributed. Also verify persistence by
  reopening, not by reading back inside the op: a rule disable read back "True" in
  the op and never persisted (C-S9-02).
- **CONTRADICTS Ron's acceptance test in practice, not in principle** (C-S6-05,
  D-S7-02, C-S7-07). Four subagents wrote grammar blind because they lacked the
  parser; a "must survive" probe set contained AI-invented, likely non-word passives.
  Probe sets must be attested or labelled.
- **Approval layer, updated** (V-S9-01, V-S10-10, C-S9-03). By 09-24 Matthew had
  removed every human approval; from then on analyses entered the project only as
  parser-filed results. Count evaluations by agent identity, not display name (a first
  count misread 25,627 parser approvals as human). Whether the approval bullets above
  still describe the loop is open (README 4.14, Q-41).
- **Failure modes (other clients, and one run whose client is not recorded):**
  - regex affix stripping with no parser call, proposing "497 new stems" (C-S8-04,
    a local model);
  - a heuristic segmenter creating entries, allomorphs and *approved* analyses in one
    pass, leaving 424 duplicate allomorphs (C-S7-04);
  - on 09-30, four improvised "top 10" queues (invented words, object counts,
    unsorted, alphabetical), a "monomorphemic" verdict from a string match, and bare
    entries for syllable fragments (`el`, `is`, `ghadha`), probably committed
    (C-S11-01 .. C-S11-05);
  - the same error resubmitted 16 times in 11 minutes (C-S11-07). Two identical
    failures should stop the loop.

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
- S6-S11 (Swahili, this machine, 2026-09-12 .. 09-30): **D-S6-01, D-S6-02**, L-S6-05,
  C-S6-05; **T-S7-01**, D-S7-06, C-S7-04; **L-S8-01**, T-S8-04; **L-S9-01..03**,
  C-S9-02, C-S9-04, C-S9-05, T-S9-01, T-S9-03, T-S9-08; **L-S10-01**, L-S10-02,
  L-S10-05, D-S10-04, D-S10-05; **C-S11-06**, T-S11-01..03.
- **Merge seam:** Merged with S1-S11 (both machines) -- see Second-Operator Evidence above. Matthew moved from the GUI parser to the in-MCP tools during the project. Acceptance threshold still unstated (Q-23); Phase 0 used a static parse-readiness proxy, and the S9-S11 loop used "top-N frequency queue is empty" instead.
  *(Original seam: Matthew's parse-triage practice, and whether he uses the FLEx GUI parser, HermitCrab CLI, or the new in-MCP tooling. His bucket definitions and acceptance thresholds should be captured alongside these.)*

## Open Questions

- What the acceptance threshold is. The corpus never states one; "as good as you can
  get it" (D-M6-01) is the only guidance. Q-23.
- Whether the corpus ever reached 100% on any text is not confirmed in the logs
  (M1 §7, M5 §7). Q-24.
- Over-generation was never systematically measured, only reasoned about. Q-25.
