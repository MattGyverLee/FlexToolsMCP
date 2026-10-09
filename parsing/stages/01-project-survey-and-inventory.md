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
  *Status 2026-10-09: partial -- `POS.Find` and `PossibilityLists.FindItem` now recurse,
  and a None argument raises before any write and rolls back; variant `FindType` recurses
  one level only and the generic list wrappers are flat, so still guard against None.*
- **JSON-serializing interop objects** (C-M5-03).
- **Assuming a relational property is non-null** before iterating it (C-M7-02).
- **Polymorphic property access without a narrowing cast** -- pervasive across the whole
  corpus (C-M1-01, C-M3-03, C-M4-01/03, C-M6-04, C-M7-03, C-M8-01/02/03/05).
- **Project locked by another process** -- an environmental flake, not a logic bug;
  retry (C-M3-05, C-M5-02). Distinguish it in triage.
- **Project locked by the MCP's own parse worker.** On 09-23 and 09-24, after
  `try_word` / `parse_text`, the idle parse worker kept the lock, and the rejection
  named only a python PID. The agent identified it (`...parse.worker_main --project
  Claude-Swahili`) but auto mode denied it `Stop-Process`, and no release tool existed
  yet; Matthew killed workers by hand four times on 09-24. Cancelling a completed run
  does nothing (T-S8-04, T-S8-12, T-S9-05). The P0 Matthew ordered that afternoon
  (D-S9-09) became the fix, partly on his design: "the parser works off of a cached copy
  of the grammar" (D-S9-10).
  *Status 2026-10-09: fixed -- an idle worker drops the lock and `flextools_parse_release`
  exists since #223/#225 (09-24 15:41, 2.13.0); `project_locked` names this server's
  worker with `next_steps` since #315 (09-30). Keep "release, don't retry" as a
  fallback.*
- **"Shared mode" is not "FLEx is open".** On 09-24/25 the MCP's advisory said "FLEx has
  this project open" whenever project sharing was enabled (`projectSharing="true"`), and
  the agent repeated it to Matthew while FLEx was closed (C-S10-07); another agent blamed
  shared mode for what was a stale parse worker (C-S9-07). On 09-30 a lock holder was
  FLEx Send/Receive (T-S11-08). Identify the actual holder before acting on the advisory.
  *Status 2026-10-09: wording fixed (`SHARING_ENABLED_ADVISORY`, on main).*
- **Peer writes lost at teardown.** Bulk writes made while FieldWorks held the project
  ran as a "non-master peer" and the last one failed with `FP_ConflictingSaveError`
  (C-S8-03, C-S7-01: on 09-13 "the FLEx UI saved underneath me"). Treat any `[SHARED]`
  write as provisional until a reopen confirms it. A fresh session reads the on-disk
  file, not the shared commit log, so a verifier in a new session could not see objects
  just written and tried to recreate them; only the conflict error stopped duplicate
  slots (C-S7-13). Existence-check inside the writing script, and re-read after any
  conflict before retrying.
  *Status 2026-10-09: partial -- a conflicting save fails loudly (flexicon 4.6.0) and
  schema changes are refused while FLEx is open (FlexToolsMCP 2.15.0), but value writes
  are not gated and there is no write lease; close FLEx for bulk writes.*
- **In-op read-back mistaken for persistence.** A rule disable read back "now
  disabled=True" inside the op and was gone on every reopen (C-S9-02, T-S9-06). After a
  teardown or commit warning, verify with a separate read-only reopen.
  *Status 2026-10-09: partial -- use `PhonRules.SetDisabled` (flexicon 4.12.0) rather
  than a raw cast, and the teardown mutex loop is fixed (#302, 2.15.0); persistence
  across a reopen is still unproven, so keep the reopen check.*
- **Counting the wrong thing.** Wordform objects instead of occurrences (every
  "frequency" = 1, C-S11-02); approvals classified by agent display name (25,627
  "human" approvals that were really 0, C-S9-03).
- **Info-message truncation.** Large inventories get capped (M8 op 12: 320 truncated to
  100). Write big inventories to a **file**, not `report.Info`, or pass
  `max_info_messages=0` to `run_module` (the cap is flagged in `summary.info_truncated`).

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
  *Status 2026-10-09: open (T-25) -- inventory recipes (`pos-inventory`,
  `feature-system-inventory`, `affix-catalog`) cover parts.*
- A **diff** primitive: snapshot the grammar now, diff against a stored snapshot.
  This is what would have resolved C-M2-06 in seconds.
  *Status 2026-10-09: open for data; `flextools_parse_diff` (2.13.0) diffs parse results
  only.*
- Recursive possibility-list resolution as a first-class helper (POS, variant types,
  inflection classes) so C-M6-02 cannot recur.
  *Status 2026-10-09: partial -- `POS.Find` and `PossibilityLists.FindItem` recurse;
  variant `FindType` (one level) and generic list wrappers do not.*
- Overflow-safe output: automatic spill of large report payloads to a file.
  *Status 2026-10-09: partial -- `max_info_messages=0` lifts the 100-line cap; no
  automatic spill to a file (T-42).*

## Second-Operator Evidence (Swahili)

*Matthew's Swahili practice (project Claude-Swahili), from shards S1-S11 in the [evidence index](../evidence/directive-index.md). S1-S5 come from one machine's logs (2026-05-21..09-11) and S6-S11 from the other's (09-12..09-30), which ran a pre-2.13.0 FlexToolsMCP main checkout. Those logs keep little or no tool output, so S6-S11 were re-checked (2026-10-09) against the Claude Code transcripts behind them, which hold the parse results, real counts and Matthew's verbatim words (mid-turn messages included) that the logs lost; tooling defects carry their current fix status. Sessions run by other clients (local models, a non-Claude agent, an unidentified non-Claude client on 09-30) count only as failure-mode evidence. Labels: **CONFIRMS** / **ADDS** / **CONTRADICTS** Ron's practice above; **REVISES** marks an S6-S11 finding that corrects an S1-S5 claim.*

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
  *Status 2026-10-09: partial -- a stale GUID now raises `FP_ParameterError` from
  `project.Object()` (flexicon#262), but there is no manifest executor; an OutOfMemory /
  NullReference on open is still reported raw (still open).*
- **ADDS a failure mode: a silent None reads as data** (C-S3-03). A noun count of 0 came
  from an accessor returning None, and "looked like a real answer". Sanity-check every
  zero in a survey against a second route.
  *Status 2026-10-09: partial -- flexicon#232 (4.4.0) and many sibling silent-None bugs
  are fixed, but None is still a legal "unset" answer, so the second-route check stays.*
- **REVISES the reading of stored "unparsed" counts** (D-S3-02, D-S2-06 -> L-S8-01,
  L-S10-01, L-S11-01). A count of wordforms with no parser analyses measures the last
  filing, not the grammar. On 09-23 the top three "unparsed" words parsed under
  `try_word`, and 14 of 15 queue words were already in the lexicon (L-S8-02). On 09-24
  5 of 20, then 9 of 10, then 4 of 5 queue words already parsed and only needed filing
  (T-S9-14). On 09-25 one all-texts refile with no grammar change cut "unparsed" from
  14,096 to 9,260. On 09-30 all ten top "unparsed" words parsed because the 09-25 Stage 1
  batch had fixed them and filing was deferred to a stage that never ran (V-S11-04).
  Read every S1-S5
  unparsed figure as "not parsed since the last filing". See
  [Stage 11](11-parse-and-repair-loop.md) and [Stage 12](12-real-corpus-stress-test.md).
- **ADDS: fix the definition before counting** (T-S10-09, T-S9-11, D-S11-02). Three
  definitions of "unparsed" gave 14,096, 9,066 and 0 on one day, and the denominator
  drifted (27,708 wordforms vs 26,725 occurring in texts). On 09-24 the count ran 14,038
  -> 14,006 -> 13,927 (in texts) and then "rose" to 14,105 only because that query
  dropped the in-texts filter (T-S9-11). Use one query: occurring
  wordforms, ranked by occurrence count, with no parser-approved analysis from a
  current run.
  *Status 2026-10-09: partial -- `flextools_parse_text` (all_texts, 2.13.0) gives live
  type-level counts (`NumZeroParses`) in occurrence order; the `parser-coverage` recipe
  still reads stored ParserCount, and there is no token-weighted figure.*
- **CONFIRMS C-S3-03 (sanity-check every count), with new cases** (C-S9-03, C-S11-02,
  C-S11-03). Approvals counted by display name, "frequency" counted as objects, and a
  "top 10" sorted alphabetically (numerals first) each looked like an answer.
- **ADDS: one writer per project; close FieldWorks before a bulk write** (C-S8-03,
  D-S8-04, D-S8-05, C-S7-01, C-S7-12, C-S10-06, D-S7-10). Writes as a non-master peer
  were lost. The 09-13 overnight per-POS write agents ran **sequentially**, by the
  orchestrator's choice (transcript; the logs suggested parallel): their save conflicts
  came from the FLEx UI and from a second Claude session writing the same project
  01:04-01:31, and the one overwritten template description was a later run of the same
  agent, which restored it. The MCP holds one global session, so MCP subagents must run
  one at a time anyway (D-S7-10). A second writer also likely explains a stale read on
  09-13 20:08 (C-S7-12), and a second client wrote concurrently on 09-25. The recovery
  that worked:
  read-only probe of persisted state, confirm FLEx is closed, re-apply, spot-check, then
  a negative check (C-S8-03 was a local-model session; the recovery pattern still
  holds). This argues for Q-02 being answered "provisional, or block".
  *Status 2026-10-09: partial -- conflicts now fail loudly (`FP_ConflictingSaveError`)
  and schema changes are refused while FLEx is open (2.15.0); one-writer-per-project is
  not enforced (T-67, still open).*
- **ADDS: parallel read-only survey agents, tagged** (D-S6-12, D-S10-03, T-S6-07,
  T-S10-08). Read-only per-POS or per-batch subagents are cheap and safe (41 ops in 6
  minutes, D-S6-12). Both fan-outs were Matthew's request ("Use subagents to work
  through each part of speech", 09-12; "spin up some /lex-linguist and /lex-parse
  teams", 09-25); the AI chose to keep the 09-12 four read-only because "concurrent
  writes into a live shared-mode project is asking for trouble". Both times the logs
  filed every subagent under one request or session, so give each agent or batch its
  own tag.
  *Status 2026-10-09: partial -- `user_request` is tracked per session since FlexToolsMCP
  2.15.0 (#318); there is still no agent or batch tag.*
- **ADDS: survey the design record** (D-S7-02, C-S7-02). Template Description fields
  carried design reasons ("DO NOT merge ..."). On 09-13 two sessions changed documented
  templates without reading them. The 01:36 change answered Matthew's own questions and
  was checked by his FLEx parse within minutes; the 20:56 session, which ran no parse,
  made TAM2 optional and called a documented RelSuf anchor "almost certainly not
  intended". Include the descriptions in the pre-state.
- **ADDS a re-entry trigger: any failed or partly failed write** (C-S6-01, C-S9-04,
  C-S8-05, C-S11-05, T-S11-10). A failed non-undoable write left an orphan entry with a
  NULL lexeme form in the work project; a 12-change op failed half-way; on 09-20 a first
  write failed partway and left Isa and Ee with a gloss but no POS or MSA. On 09-30 a
  run that raised had already committed 9 bare entries (malaka, el, kumu, gizo, is, hara,
  en, ghadha, bu): the runner's `finally` closes, and so saves, the project even when the
  script raises, and the error response then dropped the script's messages, so the
  failure looked like a no-op. Re-survey before the next write: entries created today,
  NULL or empty lexeme forms, entries with no senses.
  *Status 2026-10-09: partial -- each flexicon operation rolls back on failure (flexicon
  4.4.0, FlexToolsMCP 2.13.0), `with project.UndoableOperation(...)` makes a whole
  script atomic, and #347 keeps the messages on error; outside such a block, writes made
  before a raise still commit, so keep the re-survey.*

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
