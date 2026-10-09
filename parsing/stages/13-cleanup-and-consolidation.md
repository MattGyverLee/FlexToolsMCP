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
16. **Snapshot the original values to a file before any bulk field rewrite, and
    re-derive every pass from the snapshot** (second operator, D-S8-03). A lossy
    808-row transform went wrong four times and still converged, because no pass read
    the already-mutated field.
17. **After any failed write run, check the database, not the error message**
    (C-S6-01, C-S11-05, T-S11-10). A failed run may have written already: sweep for
    entries created today, entries with a null or empty lexeme form, and entries with no
    senses.
    *Status 2026-10-09: each flexicon operation rolls back on its own failure
    (per-operation units of work, FlexToolsMCP #144, 2026-09-18, released 2.13.0), and
    a whole script is atomic inside `with project.UndoableOperation(...)`. But a script
    that raises outside such a block still commits every earlier write: the runner's
    `finally` closes, and so saves, the project. That is how the 09-30 junk entries
    landed, after 2.13.0. Since #347 the error response keeps the script's messages, so
    the "Created ..." lines are visible; the commit-on-error behaviour remains. Keep the
    sweep.*
18. **Prove a duplicate guard with an idempotency rerun that expects zero writes**
    (D-S10-09), and key the guard on form plus POS, not form plus gloss alone: a too-broad
    key silently skipped a noun because a verb shared its form and gloss (C-S10-04).

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
  *Status 2026-10-09: partly fixed (T-08) -- per-operation rollback (flexicon 4.4.0;
  FlexToolsMCP #144, released 2.13.0) and script-level atomicity on request with
  `with project.UndoableOperation(...)`. A script that raises outside that block still
  commits its earlier writes (T-S11-10), and there is no session-level transaction.*
- **Factory-seeded duplicate child nodes** left behind after building objects, found
  only by comparing against a known-good sibling (M7 ops 19-20).
- **Leaving both conventions in place** because the reconciliation was deferred
  (L-M6-01 -- still open).
- **"Consolidating" objects that are duplicated on purpose** (C-S6-02, L-S6-04,
  D-S6-08). An AI pass merged two slot objects that existed to give one slot different
  optionality in different templates; it passed validation and was reverted a minute
  later on Matthew's word. His objection was typed while the merge was running, so it
  reached the AI only after the write had landed. Read the object's recorded design
  reason before merging; write the reason into the object's Description so the next
  pass finds it (D-S6-09). The better idiom is one MSA in two slots (as `TAM`/`TAM2`
  already were); only `Subj`/`Subj2` had two MSAs and 14 duplicate senses, the real
  artifact.
- **A write script that writes first and verifies after**, so a bug in the
  verification makes a committed run look failed (C-S11-05).

## Automation Notes

**Automatable now:** the plan/mutate split, referrer counting, content backup,
duplicate detection, zero-usage detection, deletion logging, and post-hoc count
verification.

**Human required for:** the redundancy judgements and the convention reconciliation.

**Missing tooling (requirements):**
- **A transactional / rollback-capable write mode.** The non-undoable session-scoped
  atomicity is the single biggest risk in this stage and is flagged in three separate
  shards. Everything else here is a mitigation for its absence.
  *Status 2026-10-09: partly shipped (T-08) -- per-operation rollback by default
  (flexicon 4.4.0 `OpenProject(undoable=True)`; FlexToolsMCP 2.13.0 runs writes that
  way) and whole-script atomicity with `with project.UndoableOperation(...)`. Still
  missing: rollback of a raising script's earlier writes when it does not use that
  block (the runner saves on close, T-S11-10), and a session-level transaction.*
- **`redundancy_report()`** -- rule-derivable allomorphs, lexeme-form clones,
  zero-usage allomorphs, duplicate possibility items, orphaned contexts and
  environments, and classes with zero referrers, in one pass.
  *Status 2026-10-09: partial (T-20) -- audit recipes `overpowered-allomorphs`,
  `prune-citation-forms-matching-lexeme`, `find-overpowered-affixes`; no single report.*
- **`convention_audit()`** -- for a named phenomenon, report how many entries use
  representation A, how many use B, and how many use both (mechanizing L-M6-01's
  count into a standing check).
  *Status 2026-10-09: still open (T-21).*
- **A guarded bulk-delete primitive** that requires an explicit target list or a
  predicate *plus* a category filter, refuses senseful items by default, backs up
  content automatically, writes a log, and can be replayed in reverse (C-M7-01,
  D-M5-10, D-M7-02).
  *Status 2026-10-09: partial (T-09) -- write runs take an automatic pre-write backup
  and need explicit confirmation; recipe `delete-variant-entries-by-type` skips
  senseful entries. No general primitive, per-item log or reverse replay.*
- **Referrer-aware deletion**: refuse to delete a referenced object and name the
  referrers.
  *Status 2026-10-09: partial -- recipe `form-usage-before-edit` lists the analyses
  that use an entry's forms; no flexicon referrer API (T-10) and no dangling-analysis
  sweep (T-53).*

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 and S6-S11 cover the logs of both machines. S6-S7 logs keep no tool output; S8 from 09-23 and S9-S11 do (truncated). The Claude Code transcripts behind S6-S11 supply the missing output, numbers and Matthew's own words where they exist (checked 2026-10-09). Sessions by other clients (local models, an unidentified weaker client) are failure-mode evidence only. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

- **ADDS: disable before delete** (D-S4-08, C-S4-01).
  1. Hide the entry from the parser: set `IsAbstract` on its lexeme form and every
     allomorph. (D-S4-08 used `DoNotUseForParsing`; that flag has no parser effect
     and is refused at preflight since FlexToolsMCP 2.13.0.)
  2. Check that no root was left unparseable and that no curated entry was caught.
  3. List every disabled entry with the analyses that reference it.
  4. Delete only on explicit authorization, skipping any entry that carries content
     (citation form, etymology, pronunciation, references, definition, examples).
  The disable step is what made a faulty valency heuristic cheap to undo one minute
  later. Note that the S4 flag hid nothing from the parser, so step 2 checked nothing
  then; it still worked as a reversible "to delete" marker.
- **ADDS: tiered cleanup driven by a manifest** (D-S5-05). One GUID-keyed JSON manifest
  (action, order, target), run in tiers:
  1. additive;
  2. non-destructive edits;
  3. deletes, re-checking references live just before each one;
  4. a sweep for dangling analyses;
  5. merges that move senses to the survivor;
  6. only then, tagging the survivors.
  Order: **classify, then clean, then tag.** Rows whose target has already gone are
  counted, not errors.
  *Status 2026-10-09: still open (T-56) -- no manifest executor. A stale GUID now
  raises `FP_ParameterError` from `project.Object()` (flexicon#262), so catch it and
  count "already absent".*
- **ADDS: check references across the whole owned subtree** (C-S5-01). A reference check
  on the entry alone missed analyses pointing at its allomorph/MSA/sense (`bali` left a
  dangling analysis on *alikubali*). Check the subtree, or always run the dangling
  sweep.
  *Status 2026-10-09: partial (T-53) -- recipe `form-usage-before-edit` matches
  analyses through the allomorph's owning entry; no dangling-analysis sweep yet.*
- **ADDS: a merge must repoint references, not delete them** (C-S4-03). The merges here
  deleted the analyses that referenced the losing entry, and lost their approvals.
  *Status 2026-10-09: the wrapper existed all along (T-54) --
  `project.LexEntry.MergeObject(survivor, victim)` (flexicon since 2025-12-05), LCM's
  native merge, which updates back-references. Use it instead of delete-and-recreate;
  that approvals survive is unverified, so re-read them after.*
- **ADDS: decomposition audits** (D-S2-05):
  - stems still carrying a class prefix;
  - a prefix that disagrees with its stem's class;
  - compounds found as substring pairs;
  - TAM or extensions baked into verb stems.
- **ADDS: feature-matrix pruning** (D-S3-09; see
  [Stage 03](03-phonological-features.md)).
- **ADDS: reusable QA modules** (D-S5-09). The citation==lexeme check became a
  read-only FlexTools module. Caveat: for verbs the citation form carries the class
  information (`ku`+stem(+V), D-S5-04), so do not apply it to verbs blindly.
- **Failure mode: unguarded whole-lexicon delete for a "clean rebuild"** (C-S1-02).

*S6-S11:*

- **CONFIRMS the session-atomicity hazard, with an orphan** (C-S6-01, T-S6-04). An API
  probe in the work project (`ReplaceMoForm`, which expects a freshly created form)
  failed mid-transaction with no rollback, leaving an entry with a null lexeme form. It
  was found by a date-created plus null-lexeme sweep and deleted (Procedure 17). Probe
  API semantics in a test project, never the work project. Count deltas catch such
  debris: "+5 rather than +4" entries exposed both the orphan and a doubled hyphen
  (`--ye`) from passing a hyphenated form to `Create` (C-S6-07, L-S6-03).
  *Status 2026-10-09: the no-rollback cause (that checkout's `undoable=False` write
  sessions) is gone since #144 (released 2.13.0); undocumented LCM members such as
  `ReplaceMoForm` still need probing in a test project.*
- **ADDS: reference integrity as the cleanup QC** (L-S6-02, D-S6-06, D-S7-03). Before
  and after each structural write: count morph bundles, non-null morph references and
  distinct referenced GUIDs; fail on any loss. Swapping lexeme and allomorph by moving
  owned objects passed this check on 20 entries, 3,526 references identical before and
  after (see [Stage 07](07-allomorphy-modeling.md)). In the overnight 09-13 runs the
  bundle count grew (3,526 -> 4,205) with zero GUIDs lost: FLEx was parsing alongside,
  so assert "nothing removed", not "count unchanged".
- **ADDS: a native merge exists** (T-S7-05, L-S7-19). Matthew, after running the FLEx
  parser: "merge the 2 mu entries, then merge the 2 senses", choosing which sense to
  keep. `ILexEntry.MergeObject` merged the duplicate object-marker entry into `m-3`, and
  FLEx collapsed the two MSAs into one. Parse ambiguity follows MSAs, not senses: five
  `mu` entries gave one candidate per MSA, so count MSAs when merging homographs.
  Whether the merge repoints analyses (the C-S4-03 gap) is not shown; check before
  relying on it. The wrapper is `project.LexEntry.MergeObject(survivor, victim)`
  (available before S4; S7 used the raw call).
- **ADDS: clean up after structural conversions** (V-S7-01). Once the verb extensions
  became derivational, their now-empty template slots were removed from every verb
  template.
- **ADDS: bulk-run debris** (C-S7-04, C-S11-05).
  - A heuristic write run that created entries, allomorphs and approvals in one pass
    crashed on a wrapper type error and left 424 duplicate allomorphs, which a
    follow-up op deleted.
  - On 09-30 an unidentified client (not Claude Code) committed 9 bare entries for
    syllable fragments: *malaka, el, kumu, gizo, is, hara, en, ghadha, bu* (morph type
    stem, one empty sense, `DateCreated` 2026-10-01 00:54:10Z; `fu`, `hu`, `zi`, `ma`,
    `a` already existed). It had first invented "[el-fu] [is-hara]" splits that no tool
    returned (C-S11-08), then created the "missing morphemes" to match. The script
    raised, but the runner's `finally` saved the project anyway, and the error response
    dropped its "Created ..." messages, so nobody noticed (T-S11-10). The entries are
    still in the project and had not been sent by Send/Receive as of the check; delete
    the 9 entries with a GUID guard before the next S/R (pre-junk backup
    `20260930T200325Z`). The day's log triage turned the task into a shipped recipe,
    `ensure-morpheme-entries` (PR #337), and a local recipe still stores the junk script
    (T-S11-11): review the recipe (require POS, gloss and morph type) and drop the local
    one.
- **ADDS: guarded single deletes** (C-S10-01). Matthew: "remove *mwaka, file the
  parses." The duplicate bound stem was deleted only after a reference check (0
  analyses, no complex-form links) and a GUID plus headword guard that aborts on
  mismatch.
- **ADDS: keep the analysis layer apart from the lexicon** (D-S8-14, C-S8-06, D-S9-04,
  L-S8-06; tool output). Before deleting stored analyses, split human from parser
  analyses and count text references, then show the list and wait for the go-ahead.
  "Bundle without a sense" is normal for parser output (21,834 of 24,796, none
  referenced by a text), so that completeness test applies only to human analyses. A
  bad analysis is deleted as an analysis; the entry it points to is not junk by
  implication. Two lapses, both against Matthew's actual words:
  - 09-23: he asked to "identify and remove all incomplete user analyses"; the agent
    promised "only delete after you confirm", then sent the 18-analysis delete
    confirmed 20 s later without showing him the list. Only the parse-worker lock
    stopped it. 14 of the 18 lacked only the last verb-extension suffix, a lexicon gap;
    the agent itself advised linking them rather than deleting.
  - 09-24: "the human analyses are junk" approved deleting *yeye*'s one analysis; the
    agent widened it to a project-wide sweep until Matthew's mid-turn "i didn't mean the
    definition was junk, the analysis was bad". One approved deletion is not a licence
    for a sweep.
- **CORRECTS: `DoNotUseForParsing` suppressed nothing** (D-S7-04, V-S7-02, D-S8-12,
  C-S8-07, D-S10-14). Set on 33 entries by 09-20: the cl.16 null prefix, a duplicate
  quantifier stem, shadow whole-word possessives and losing homographs. A FieldWorks
  source check that Matthew ordered on 09-25 showed neither HermitCrab nor XAmple reads
  the flag; they skip only forms marked `IsAbstract`. So the cl.16 null prefix was never
  suppressed (V-S7-02 is refuted), which is why its analyses were still present on 09-24
  (V-S9-03). Matthew's ruling: "treat it as deprecated and redirect the MCP to use
  `isAbstract` on any lexeme form or allomorph we want to hide"; he opened LT-22810 so
  FLEx may honour the flag later. Migrating the 33 entries changes parser output; it was
  asked three times on 09-25 and never answered.
  *Status 2026-10-09: refused at preflight since FlexToolsMCP 2.13.0
  (`deprecated_member`, PR #259; weekly upstream watch). Migrate each entry to
  `IsAbstract` on its lexeme form and every allomorph (recipe `hide-entry-from-parser`;
  an entry drops out only when all its forms are abstract) and confirm with a
  `flextools_parse_diff`.*
- **ADDS: wastebasket POS review** (D-S6-11; S7 Swahili content). Particle and similar
  catch-all categories were reviewed and recategorised on 09-13: Particle 70 -> 33,
  Adverb 8 -> 20, new Interrogative (12), Copula (11) and Interjection (3); *mbali*
  became an Adverb. A recurring cleanup item.
- **ADDS: lexicon data-quality backlog** (L-S7-13). The 09-13 valency review found the
  hand tags "(tr)"/"(intr)" in glosses unreliable (causatives glossed "(intr)"), plus
  likely segmentation artefacts and glosses of the wrong category. Such findings go on a
  list for a human, not into a bulk rewrite.
- **Open: glide formation modelled twice** (S6 Conflicts 4): a global rule and stored
  glide allomorphs on 10 prefixes, with 35 more relying on the rule (L-S7-18). By
  S9-S10 the rule, not the allomorphs, was the defect (see
  [Stage 08](08-phonological-rules.md)): disabling it fixed 54 words in the sandbox and
  broke 3 because `vi-2` lacks a `vy` allomorph (L-S9-09). "Delete what the rules
  derive" can run in the other direction: delete or restrict the rule, after adding the
  allomorphs it was silently supplying.

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
- S6-S11: C-S6-01, C-S6-02, C-S6-07, L-S6-02, L-S6-03, L-S6-04, D-S6-06, D-S6-08,
  D-S6-09, D-S6-11, T-S6-04; D-S7-03, D-S7-04, C-S7-04, T-S7-05, L-S7-13, L-S7-18,
  L-S7-19, V-S7-01, V-S7-02; D-S8-03, D-S8-12, D-S8-14, C-S8-06, C-S8-07, L-S8-06;
  D-S9-04, L-S9-09, V-S9-03; C-S10-01, C-S10-04, D-S10-09, D-S10-14; C-S11-05,
  C-S11-08, T-S11-10, T-S11-11. Checked against the Claude Code transcripts and a
  read-only check of the live project file (09-30 entries).
- **Merge seam:** Merged from S1-S11 (both machines). Cadence (Q-27): still opportunistic; in S6-S11 cleanup is triggered by failed writes and structural conversions rather than scheduled. Open: the 33 `DoNotUseForParsing` entries (to migrate to `IsAbstract`; the flag never affected the parser and is refused since FlexToolsMCP 2.13.0), the 9 confirmed 09-30 junk entries, and the `ensure-morpheme-entries` recipe built from that run.
  *(Original seam: Matthew's cleanup cadence and his tolerance for redundancy.)*

## Open Questions

- The oblique allomorph-vs-variant-entry duplication was counted and never resolved
  (L-M6-01). Q-04.
- Whether every verb "that needs it" was converted in the final bulk pass (M8 §7).
  Q-14.
- Whether the abandoned "Enclitic onset" class was deleted or merely orphaned
  (M7 §7). Q-08.
- No cadence is stated for when cleanup should run. Q-27.
