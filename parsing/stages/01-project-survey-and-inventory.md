# Stage 01 -- Project Survey and Inventory

[Back to overview](../00-overview.md) | [Next: Stage 02](02-phoneme-inventory.md)

## Purpose

Establish the *actual* current state of the FLEx project before any write, and keep
re-establishing it whenever anything outside your control could have changed it. Every
later stage's preconditions are read here.

This stage is not optional and it is not once-per-project. It runs at session start, and
again after any project restore, any gap in the session, any GUI edit by the human, and
any `[SHARED]` / concurrent-holder warning.

## Entry Criteria

- A FLEx project exists and can be opened.
- Write is **disabled** for this stage.

## Inputs

- The project itself (the only trustworthy source of state).
- Any source-of-truth data modules or JSON plans from prior sessions, for diffing.
- The previous session's end-state notes, treated as a *hypothesis* to be checked, not
  as fact.

## Procedure

1. **Run everything read-only.** An explicit "don't modify anything" constraint persists
   across the whole investigative session even when stated once at the start (D-M4-04:
   *"Don't modify anything just answer the question."*).
2. **Writing systems.** Enumerate them and resolve handles via the sanctioned helper,
   not raw ServiceLocator iteration (C-M4-02). Record vernacular, any transliteration
   WS, and the analysis WS. Use integer handles as dict keys -- WS objects are not
   JSON-serializable (C-M5-03).
3. **POS tree.** Walk it **recursively**, including sub-possibilities. Record name,
   abbreviation and catalog id per node (M5 op 43). The same recursive-walk idiom is
   needed for every `CmPossibility` list in the project (C-M6-02).
4. **Inflection templates and slots.** Per POS: templates, ordered slots, per-slot
   optionality, and which affix entries fill each slot. Note which slots are *shared*
   across POS via a parent category -- a shared slot is a cross-category coupling you
   must respect (M5 op 34: the Case slot owned by Nominal and shared by
   Noun/Demonstrative/Pronoun).
5. **Entry inventory.** Count entries by POS and by morph type. Dump lexeme form,
   transliteration, morph type, gloss and POS to a scratch JSON for dedup
   (M5 ops 2-4). Coerce every .NET interop object to a plain string/int first
   (C-M5-03).
6. **Phonological data.** Phoneme count and codes; natural classes with their type
   (segment-based vs feature-based) and membership; phonological features and values;
   environments with their `StringRepresentation`; phonological rules with inputs,
   outputs and contexts; compound rules; inflection classes; stem names; variant types.
7. **Texts.** Titles, paragraph counts, and (if relevant) per-wordform analysis counts.
   Stored parser analyses record the last parser filing, not what the current grammar
   does, so state when the texts were last refiled and the exact query behind every
   "unparsed" count (L-S8-01, L-S10-01, T-S10-09).
8. **Diff against the canonical source of truth.** If a source-of-truth data module or
   JSON plan exists, re-derive expected counts from it rather than hardcoding a
   snapshot literal -- hardcoded baselines drift and produce phantom regressions
   (C-M2-06).
9. **Record anomalies rather than acting on them.** Anything that differs from the
   expected pre-state is a finding for this stage, not a fix.
10. **For a gap-analysis run**, build the candidate list from *real failures* (parse or
    gloss failures on a real text), normalize both sides of every string comparison,
    and report PRESENT/MISSING (D-M8-01, D-M8-02, D-M8-04). Deliberately over-generate
    the candidate list: it costs nothing to look, and the dump is what reveals which
    existing entries need a new *sense* rather than a new *entry* (L-G1-04).

## Linguistic Decisions Required

Essentially none -- this stage is deliberately decision-free. The one judgement call:

- Whether an unexpected structure is **legitimate prior work** (a human GUI edit, a
  restore) or **damage**. Ron's restore of the project to fix an unrelated FLEx setting
  (D-M3-03) and his hand-restructuring of the Pronoun category under Nominal (D-M5-02)
  are both legitimate. Treat state deltas as information, not error, until proven
  otherwise.

## QC / Exit Criteria

- A written pre-state record exists covering: WS, POS tree, templates/slots, entry
  counts by POS and morph type, phonemes, features, natural classes, environments,
  phonological rules, compound rules, inflection classes, stem names, variant types,
  texts.
- Every count you intend to assert later has been **derived from the live database**,
  not copied from a previous session.
- All anomalies are listed with a classification: expected / human-made / unexplained.
- Zero writes occurred.

## Common Failure Modes

- **Hardcoded baseline counts.** M2's verification found "POS Verb slot count 3
  (expected 1)" and "total entries 76 != 74" and never resolved whether this was
  concurrent GUI editing, a stale baseline, or leakage from another session (C-M2-06).
  Re-derive, don't hardcode.
- **Naive string comparison.** LCM stores vernacular text decomposed; a NFC literal
  will silently fail to match (D-M8-02, C-M2-03). Normalize **both** sides.
- **Shallow possibility-list search.** "Oblique" was a sub-possibility of "Irregularly
  Inflected Form"; a flat search returned `None`, which was then passed to `.Add()` and
  crashed mid-write, leaving half-built entries (C-M6-02).
- **JSON-serializing interop objects** (C-M5-03).
- **Assuming a relational property is non-null** before iterating it (C-M7-02).
- **Polymorphic property access without a narrowing cast** -- pervasive across the whole
  corpus (C-M1-01, C-M3-03, C-M4-01/03, C-M6-04, C-M7-03, C-M8-01/02/03/05).
- **Project locked by another process** -- an environmental flake, not a logic bug;
  retry (C-M3-05, C-M5-02). Distinguish it in triage.
- **Project locked by the MCP's own parse worker.** After `try_word` / `parse_text`, an
  idle parse worker can still hold the lock, and the rejection names only a python PID.
  Release it (`flextools_parse_release`) rather than retrying; cancelling a completed
  run does nothing (T-S8-04, T-S9-05).
- **Peer writes lost at teardown.** Bulk writes made while FieldWorks held the project
  ran as a "non-master peer" and the last one failed with `FP_ConflictingSaveError`
  (C-S8-03, C-S7-01). Treat any `[SHARED]` write as provisional until a reopen confirms
  it.
- **In-op read-back mistaken for persistence.** A rule disable read back "now
  disabled=True" inside the op and was gone on every reopen (C-S9-02, T-S9-06). After a
  teardown or commit warning, verify with a separate read-only reopen.
- **Counting the wrong thing.** Wordform objects instead of occurrences (every
  "frequency" = 1, C-S11-02); approvals classified by agent display name (25,627
  "human" approvals that were really 0, C-S9-03).
- **Info-message truncation.** Large inventories get capped (M8 op 12: 320 truncated to
  100). Write big inventories to a **file**, not `report.Info`.

## Automation Notes

**Already automatable (FLExTools / flexicon / MCP):** all of it. This stage is pure
read. Use `bare_snippet` with write disabled.

**MCP tooling that helps today:** `flextools_health`, `flextools_list_projects`,
`flextools_get_object_api`, `flextools_resolve_property` (use it *proactively* before
touching any `OC`/`RC`/`OA`/`RA` property -- C-M6-04), `flextools_resolve_type`.

**Human still required for:** deciding whether an anomaly is damage.

**Missing tooling (requirements):**
- A single `survey_project` / grammar-snapshot call returning the whole pre-state
  structure in one response, instead of ten hand-written probes per session. Every
  shard opens by re-writing essentially the same survey code.
- A **diff** primitive: snapshot the grammar now, diff against a stored snapshot.
  This is what would have resolved C-M2-06 in seconds.
- Recursive possibility-list resolution as a first-class helper (POS, variant types,
  inflection classes) so C-M6-02 cannot recur.
- Overflow-safe output: automatic spill of large report payloads to a file.

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 come from one machine's logs (2026-05-21..09-11) and S6-S11 from the other's (09-12..09-30); both machines' Swahili logs are now ingested. Logs before 09-23 keep no tool output, so their results are partly inferred; later logs keep truncated output. Sessions run by other clients (local models, a non-Claude agent, an unidentified weaker client) count only as failure-mode evidence. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

- **ADDS: survey against a written target, not just an inventory** (D-S3-03). The
  August re-entry first wrote down what a finished entry looks like (four fields:
  bound-stem lexeme form, singular citation form, noun class, gloss), then bucketed
  every noun against it: 832/1,024 parse-ready, 134 "bound but featureless -> zero
  parses", 0 orphaned, 58 free stems. The orphaned bucket is kept as a standing
  regression alarm ("any rise above 0 ... silent zero-parse defect").
- **ADDS: Phase 0 baseline with stop conditions** (D-S3-04). Before any work: lock file,
  version match, and a *grammar-before-lexicon* gate -- check that the class-prefix
  allomorph pairs exist, because "No amount of stem work will make anything parse"
  without them. Record each count's exact query so a later phase can repeat it. "Do not
  claim a parser baseline you did not actually obtain."
- **ADDS: adopt the project's existing convention** (L-S3-02). The target moved from
  "bound root" to "bound stem (the lexicon's existing convention)" once the survey
  showed what the lexicon actually used.
- **ADDS: harvest recipes from a reference project** (D-S3-08) -- probe a mature project
  of a related language (here Sena 3, also Bantu) for confirmed-good structures before
  inventing them.
- **CONFIRMS C-M2-06 (re-survey after outside change)** (C-S5-02, C-S5-05). A GUID
  manifest went stale between sessions; a project held open elsewhere refused to open
  for writing (OutOfMemory, then NullReference) and the write was never confirmed.
- **ADDS a failure mode: a silent None reads as data** (C-S3-03). A noun count of 0 came
  from an accessor returning None, and "looked like a real answer". Sanity-check every
  zero in a survey against a second route.
- **REVISES the reading of stored "unparsed" counts** (D-S3-02, D-S2-06 -> L-S8-01,
  L-S10-01, L-S11-01). A count of wordforms with no parser analyses measures the last
  filing, not the grammar. On 09-23 the top three "unparsed" words parsed under
  `try_word`. On 09-25 one all-texts refile with no grammar change cut "unparsed" from
  14,096 to 9,260. On 09-30 all ten top "unparsed" words parsed. Read every S1-S5
  unparsed figure as "not parsed since the last filing". See
  [Stage 11](11-parse-and-repair-loop.md) and [Stage 12](12-real-corpus-stress-test.md).
- **ADDS: fix the definition before counting** (T-S10-09, T-S9-11, D-S11-02). Three
  definitions of "unparsed" gave 14,096, 9,066 and 0 on one day, and the denominator
  drifted (27,708 wordforms vs 26,725 occurring in texts). Use one query: occurring
  wordforms, ranked by occurrence count, with no parser-approved analysis from a
  current run.
- **CONFIRMS C-S3-03 (sanity-check every count), with new cases** (C-S9-03, C-S11-02,
  C-S11-03). Approvals counted by display name, "frequency" counted as objects, and a
  "top 10" sorted alphabetically (numerals first) each looked like an answer.
- **ADDS: one writer per project; close FieldWorks before a bulk write** (C-S8-03,
  D-S8-04, D-S8-05, C-S7-01, C-S10-06). Writes as a non-master peer were lost; parallel
  per-POS writers lost commits and overwrote each other's template descriptions; a
  second client wrote to the same project concurrently. The recovery that worked:
  read-only probe of persisted state, confirm FLEx is closed, re-apply, spot-check, then
  a negative check (C-S8-03 was a local-model session; the recovery pattern still
  holds). This argues for Q-02 being answered "provisional, or block".
- **ADDS: parallel read-only survey agents, tagged** (D-S6-12, D-S10-03, T-S6-07,
  T-S10-08). Read-only per-POS or per-batch subagents are cheap and safe (41 ops in 6
  minutes, D-S6-12). Both times the logs filed every subagent under one request or
  session, so give each agent or batch its own tag.
- **ADDS: survey the design record** (D-S7-02, C-S7-02). Template Description fields
  carried design reasons ("DO NOT merge ..."). Two same-day reversals of documented
  decisions came from sessions that never read them. Include them in the pre-state.
- **ADDS a re-entry trigger: any failed or partly failed write** (C-S6-01, C-S9-04,
  C-S11-05). A failed non-undoable write left an orphan entry with a NULL lexeme form in
  the work project; a 12-change op failed half-way; a run that crashed in its
  verification code had already created entries. Re-survey before the next write:
  entries created today, NULL or empty lexeme forms, entries with no senses.

## Provenance

- M1 ops 3, 11, 12, 29, 31 (2026-09-10 16:14 .. 09-11 11:39) -- inspect/audit operations.
- M2 §5 "Recon before write" (2026-09-10 19:45 onward); C-M2-06 (2026-09-10 20:46).
- M3 §5 "Diagnostic snippet (read-only survey)" and "Environment/session restart";
  D-M3-03 (2026-09-11 16:05); C-M3-05.
- M4 §5 "Read-only diagnostic investigation"; D-M4-04 (2026-09-14 12:19).
- M5 §5 stage 1 "Survey / inventory" (2026-09-13 22:37); ops 1-8, 24-25, 43, 57;
  C-M5-03.
- M6 §5 stage 1 "Survey stage" (2026-09-14 16:01); C-M6-02, C-M6-04.
- M7 §5 "Cheap-first read-only reconnaissance" (2026-09-15 08:04); D-M7-01; C-M7-02/03.
- M8 §5 "Gap-analysis audit" (2026-09-15 14:02); D-M8-01/02/04; C-M8-01/02/03/05.
- G1 §5 "Candidate Dump (step 1)" (2026-09-04 22:39) and L-G1-04 -- language-independent
  per G1 §9.
- **Merge seam:** Merged from S1-S11 (both machines) -- see Second-Operator Evidence above. Remaining: whether Matthew surveys greenfield projects the same way; neither operator persists a survey snapshot (Q-01).
  *(Original seam: Matthew's survey practice may differ in scope or in what he records.)*

## Open Questions

- Should the pre-state record be a committed artifact per session (a grammar snapshot
  file) rather than transient log output? The corpus never persisted one, and paid for
  it repeatedly. See [open-questions.md](../open-questions.md) Q-01.
- How should a `[SHARED]` non-master-peer write be treated -- proceed (as the corpus
  always did) or block? Unresolved. Q-02. The Swahili evidence (C-S7-01, C-S8-03) shows
  peer writes being lost, which argues against "proceed".
