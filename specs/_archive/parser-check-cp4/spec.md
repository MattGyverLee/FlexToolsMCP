# Feature Specification: parser-check CP4 -- in-process write: ParseFiler, the write ladder, and the first mutation

**Feature Branch**: `feat/parser-check-cp4` (proposed; not created by this command)

**Created**: 2026-09-23

**Status**: Draft -- `lex-domain` gate pass 1 run 2026-09-23; two blocking findings corrected in place (D-1, D-2 below). Clarified 2026-09-23 (three questions resolved); ready for planning

**Input**: User description: "create a spec to resolve https://github.com/MattGyverLee/FlexToolsMCP/issues/165"

**Source document**: GitHub issue #165 (the durable definition of CP4; self-contained by design)
**Parent spec**: [`../parser-check/SPEC.md`](../parser-check/SPEC.md) -- sections 5.2, 9.3.3, 9.3.4,
12.2, 12.3, 12.4, 12.6, 12.7, 14, 15 (CP4 row), 16 (live + concurrency rows). If pruned, recover with
`git show e5afbfd:specs/parser-check/SPEC.md`.
**Predecessors**: CP1, CP2, CP2a-bridge, CP2b (landed at `e5afbfd`); CP3
([`../parser-check-cp3/spec.md`](../parser-check-cp3/spec.md)) -- landed on `main` (merge `822ec10`,
lint follow-up `a672510`). The issue's entry gate ("CP3 landed first") is satisfied.
**Successors blocked by this**: #166, #167.

---

## Summary

Every checkpoint so far has been read-only. The linguist can now ask the parser what it makes of a
word, a text or a whole project, and see how a grammar edit changed the answer. **CP4 is the first
checkpoint that writes.** It lets the linguist tell the assistant "file these results into my
project", which is what FLEx's own *Parse Words in Text* menu does: parser-generated analyses are
created or re-approved, and stale ones are cleared out.

That is exactly the operation that can destroy work, permanently. FLEx's filer resets the
parser's opinion on every existing analysis of a word, then **deletes** every analysis that
neither the parser nor a human currently vouches for. The deletion cannot be undone. Run against a
half-edited grammar, it removes the analyses that grammar used to produce; run against a grammar
that silently lost entries on load, it does the same with no error anywhere. CP4 therefore ships
the write and its guard rails as one unit: a preview that says, in concrete numbers from the
user's own project, what may be deleted; a confirmation a human must give; a backup attempted
first, whose absence is shouted rather than buried; and a gate that refuses to file at all when the grammar did not load cleanly.

---

## Clarifications

### Session 2026-09-23

- Q: Must a completed read-only parse of the same scope exist before filing, and how does a user get
  past a new-load-error refusal? → A: A prior read-only run is **optional**. When one exists, it is
  the baseline. Running a fresh read-only parse of the same scope is the **only** way to accept new
  load errors (or a drop in eligible forms): they then become pre-existing and are warned about and
  counted. There is no override argument. A first-ever filing run has no baseline, so every load
  error counts as pre-existing. (Resolves former Q1; FR-021, FR-022, FR-039.)
- Q: When FLEx has the project open with sharing enabled, should CP4 file as a shared-mode peer?
  → A: **Allow, with an advisory**, as `run_module` does. The advisory tells the user to make sure
  FLEx's own parser is not running on the project, because the MCP cannot see whether it is. The
  risk of two concurrent filers rests with the user, and the advisory says so. Exclusive holds are
  still refused. (Resolves former Q2; FR-030.)
- Q: What happens to results whose parse ended in an error (timeout, exception)? → A: It depends on
  the mode. **Try-a-word modes never file anything**, errored or not. **Filing runs file errored
  results exactly as FLEx does.** Skipping them would be inconsistent, because a word that failed
  will fail again on the next parse. The projection and the run record account for them. (Resolves
  former Q3; FR-017.)
- Q: Constitution Principle I makes the pre-write backup best-effort and says it "MUST NOT raise".
  Issue #165 makes it mandatory for filing. Which wins? → A: **Keep best-effort** (the
  constitution). Filing attempts the backup exactly as `run_module` does and proceeds if the backup
  cannot be made. The plan states the expected backup outcome before confirmation, and a run without
  a backup carries a prominent no-recovery-point warning. **This departs from issue #165's
  definition of done** ("Mandatory pre-write backup ...") and from parent 12.4 ("Backup is mandatory
  here"). Both need updating to match. (FR-007, FR-009, SC-004.)
  **Why a backup cannot be required** (maintainer, 2026-09-23): a local `.fwdata` backup is useful
  only for a non-shared project. It cannot revert a project that takes part in Send/Receive. There,
  the recovery for a badly broken copy is to **not** Send/Receive it, delete the local copy and
  re-download it from the repository. A required backup would refuse filing on exactly the projects
  where it would not be the recovery path anyway. Separately, backup copies MUST NEVER be written
  inside the project folder. Anything placed there can be picked up by Mercurial on the next
  Send/Receive and balloon the project's repository (FR-042).

### Domain-gate corrections (2026-09-23, `lex-domain` pass 1)

- **D-1 -- load errors do not see every shrink.** `HCLoader.IsValidLexEntryForm`
  (`FieldWorks/Src/LexText/ParserCore/HCLoader.cs:579-589`) and `IsValidRuleForm` (`:536-569`)
  exclude a form with an empty or abstract vernacular text **without calling the error logger**.
  An entry whose forms all fail this check never reaches the grammar, and it leaves no line in the
  load-error file. A gate that only compares logged errors would pass the exact "half-edited
  grammar" case this checkpoint exists for. Corrected: FR-039 adds an eligibility-count comparison
  alongside the load-error diff, and US3 now tests the silent path as well as the logged one.
- **D-2 -- filing overwrites human disapprovals.** `ParseFiler.SetUnsuccessfulParseEvals`
  (`ParseFiler.cs:310-311`) sets the user agent to `approves` on every in-use analysis
  unconditionally, including one a human had marked incorrect. The parent spec's 12.2 sentence
  "filing can never overwrite or revoke a human's opinion" is **false** for this case. Corrected:
  FR-040, FR-041, a new edge case, and a correction to feed back into the parent spec.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what filing would do before anything is written (Priority: P1)

A linguist asks the assistant to file the parser's results for a text or genre. Nothing is written.
The response is a mutation plan built from the linguist's own project: how many words would be
filed, how many analyses may be created, how many of those duplicate an existing gloss-only record,
how many existing analyses **may be deleted**, and which ones by wordform. It states the grammar's
load-error standing (clean, pre-existing errors counted, or refused) and whether a backup is
expected to be taken. It ends by saying the same request must be resubmitted with explicit confirmation.

**Why this priority**: The preview is the only point where a human sees what they are agreeing
to. A confirmation that shows abstract warnings instead of real numbers trains people to click
through, which is how a non-undoable delete stops being read.

**Independent Test**: Against a project with known parser-created, never-reviewed analyses (some
used in a text, some not), submit a filing request without confirmation. Verify the project file
is byte-identical before and after, and the projected deletion set contains exactly the unused,
unreviewed ones and none of the in-text ones.

**Acceptance Scenarios**:

1. **Given** a session with writing enabled and a project never parsed live, **When** the linguist
   requests filing without confirmation, **Then** the response is `confirmation_required`, it says
   "may delete 0 analyses", and the project is unchanged.
2. **Given** a project where 12 parser-created analyses carry no human opinion and 4 of them appear
   in a text segment, **When** filing is previewed, **Then** at most 8 analyses are projected as
   deletable, and none of the 4 in-text ones are among them.
3. **Given** an analysis whose only link to a text is through one of its glosses, **When** filing is
   previewed, **Then** that analysis is treated as in use and is not projected as deletable.
4. **Given** a project with substantial gloss-only work, **When** filing is previewed, **Then** the
   plan states how many projected creations duplicate an existing gloss-only record rather than
   completing it.
5. **Given** a session with writing disabled, **When** filing is requested, **Then** it is refused
   before any preview is built, and nothing is parsed.

---

### User Story 2 - File confirmed results, backed up first whenever possible (Priority: P1)

The linguist has read the plan, and the plan said whether a backup is expected to succeed. They
confirm. Before a run starts, and while the linguist is still there, the system tries to back up the
project, exactly as `run_module` does. If the backup cannot be taken, filing still proceeds, per the
constitution's best-effort rule. The response then carries a loud warning that no recovery point
exists for a non-undoable write. Only after the backup attempt finishes does the run begin and a run
identifier come back. The run parses each word and files the result exactly as FLEx's own filer does, so the new
analyses carry the parser's honest provenance. At the end, the linguist gets a report of what was
created, re-approved, duplicated, deleted and skipped, with each deleted analysis recorded well
enough to identify it later.

**Why this priority**: This is the feature. Without it CP4 delivers nothing. Filing cannot be
undone, so the backup is the only recovery path. That is why its expected outcome is shown before
the human confirms, and its absence is shouted rather than buried.

**Independent Test**: On a disposable copy of a project, confirm a filing run for one text. Verify
a new backup exists and is dated before the first modified object, that the created analyses are
attributed to the parser agent, and that the report's deletion list matches the analyses actually
missing afterwards.

**Acceptance Scenarios**:

1. **Given** a confirmed filing request, **When** the backup succeeds, **Then** a run identifier is
   returned only after the backup is complete, and the response names the backup's location.
2. **Given** too little free disk space for a backup, **When** filing is previewed, **Then** the plan
   states that no backup is expected. **When** the request is then confirmed, **Then** filing
   proceeds, and the response carries a prominent warning that no backup was taken for a
   non-undoable write, with the reason.
3. **Given** a session configured to skip pre-write backups, **When** filing is previewed and
   confirmed, **Then** the plan and the result both state that no backup will be or was taken
   because of that setting.
4. **Given** a filing run in progress, **When** a word's parse result refers to an object that was
   deleted after parsing began, **Then** that result is skipped rather than filed, and the report
   counts the skip.
5. **Given** a filing run that finishes, **When** the report is read, **Then** it lists, per wordform,
   the analyses deleted, with enough of each one's content to recognise it, captured before the
   deletion happened.
6. **Given** a completed filing run, **When** the same scope is filed again with an unchanged
   grammar, **Then** words whose results did not change are left untouched and reported as
   unchanged.
7. **Given** a filing run is cancelled part way, **When** the report is read, **Then** it states
   exactly which words were filed before cancellation, and that those changes cannot be undone
   except by restoring the backup.

---

### User Story 3 - Refuse to file against a grammar that did not load cleanly (Priority: P1)

The linguist edits a rule, and the edit breaks some lexical entries so that they fail to load.
FLEx's grammar loader says nothing to its caller; those entries simply disappear from the parser's
view. Filing now would delete every analysis those entries used to license. CP4 compares the load
errors from this load against the errors its own earlier run recorded for the same scope. New errors
mean "your edit broke the grammar", and filing is refused, with the new errors named. Errors that
were already there last time are warned about and counted in the plan, but do not block. A grammar
that does not load at all is always refused.

**Why this priority**: This is the worst realistic failure of the feature: data loss with no error
anywhere in the chain. A blunt "any load error blocks" rule would make filing permanently unusable
on projects with long-standing benign errors, which would push people toward a bypass.

**Independent Test**: Parse a scope read-only (so a baseline is recorded). Then break the grammar
two ways, one at a time: (a) give one entry an allomorph shape that the loader rejects and logs;
(b) empty one entry's only lexeme form, which the loader drops **without logging anything**. For
each, request filing and verify it is refused with the right signal and the baseline's origin, and
that nothing was written. Case (b) is the one a load-error diff alone would miss (D-1).

**Acceptance Scenarios**:

1. **Given** a grammar whose parser cannot be built after loading, **When** filing is requested,
   **Then** it is refused with `grammar_load_unclean` / `morpher_null`, with no override.
2. **Given** a prior read-only run of this scope recorded 3 load errors and this load has 5,
   **When** filing is previewed, **Then** it is refused with `new_load_errors`, reporting
   `new_error_count` 2, `baseline_error_count` 3, and a `baseline_source` naming the prior run.
3. **Given** a first-ever run for this project and scope with 3 load errors, **When** filing is
   previewed, **Then** all 3 are reported as pre-existing, counted in the plan, and do not block,
   and the baseline source is reported as `absent`.
4. **Given** the grammar was clean at preview and an edit introduces a new load error before the
   job begins filing, **When** the job loads the grammar, **Then** the run ends refused with
   nothing filed, and it does not stop to ask anyone anything.
5. **Given** FLEx's own load-error file was rewritten by an unrelated FLEx session, **When** the
   gate runs, **Then** that file's earlier contents play no part in the comparison.
6. **Given** a baseline run, then an edit that empties an entry's only lexeme form (no load error is
   logged), **When** filing is previewed, **Then** it is refused because fewer forms are eligible to
   reach the grammar than in the baseline, and the missing entries are named.

---

### User Story 4 - Only one filing job per project, without freezing the lexicon (Priority: P2)

While a filing job runs on a project, a second filing request for the same project is refused with
the running job's identifier, when it started, and how far it has got, so the assistant can point
the linguist at it instead of starting another. Nothing else the MCP does is blocked by the job
merely existing: read-only parses, single-word tries and reading prior runs keep working.

**Why this priority**: Two writers to the parser's opinions is the one genuinely incoherent case.
But a feature that froze everything else for the hours a corpus parse takes would be worse than no
feature.

**Independent Test**: Start a filing run on a large scope, immediately submit a second filing
request for the same project, and try a single word while the first runs. Verify the second is
refused with `parser_filing_in_progress` and full detail, and the single-word try answers without
waiting for the run to finish.

**Acceptance Scenarios**:

1. **Given** a filing job running on project P, **When** a second filing request for P arrives,
   **Then** it is refused with `parser_filing_in_progress` carrying `run_id`, `started_at`,
   `words_completed` and `hint`, and no preview or backup is attempted.
2. **Given** a filing job running on project P, **When** a filing request for project Q arrives,
   **Then** it is not refused on P's account.
3. **Given** a filing job running on project P, **When** a single-word try or a read-only batch is
   submitted for P, **Then** it proceeds.
4. **Given** a filing job that ended (success, refusal, cancellation or crash), **When** a new
   filing request arrives, **Then** it is not refused as in progress.

---

### User Story 5 - Prove the write against a real project (Priority: P2)

Before CP4 is called done, the write is exercised against a real FieldWorks project, with evidence
kept. Three behaviours that no source reading can settle are observed directly: what happens when an
analysis a text still points at is deleted; whether an in-text analysis really survives a filing
pass that a naive "no human opinion" rule would have condemned; and whether a project that has never
run the HermitCrab parser from FLEx has the parser agent that filing needs.

**Why this priority**: Required by the project's own rules for any write path, and not waivable.
It is P2 only because it verifies stories 1-4 rather than delivering new capability.

**Independent Test**: Run the live suite with live verification forced on and confirm an evidence
artifact exists for each named case, with before and after state.

**Acceptance Scenarios**:

1. **Given** a live project with an analysis referenced by a segment, **When** that analysis is
   deleted through the generic deletion path, **Then** the evidence records where the segment's
   reference ends up.
2. **Given** a live project with an unreviewed parser analysis that is in use in a text and that
   the new parse no longer produces, **When** a filing pass runs, **Then** the analysis still exists
   afterwards, now carrying a user approval, and the evidence shows it would have been in a
   bare-no-opinion projection.
3. **Given** a live project whose active parser is HermitCrab and which has never run the parser
   from FLEx, **When** its agents are inspected read-only, **Then** the evidence records whether the
   HermitCrab parser agent exists, and the finding is written back to the parent spec's
   open-question register.
4. **Given** a live filing run, **When** its projected deletions are compared with what was actually
   deleted, **Then** every actual deletion was in the projection.

---

### User Story 6 - Know exactly what a filing run did, afterwards (Priority: P3)

Days later, the linguist asks what that filing run changed. The run's record answers: what was
projected, what was confirmed, where the backup is, what was created, re-approved, duplicated,
deleted and skipped (and why), and how many analyses gained a user approval they never gave,
because they were in use in a text.

**Why this priority**: Accountability for a non-undoable action. The run record already exists
(CP3); this adds the filing section.

**Independent Test**: After a filing run, read it back through the existing run-reading tools and
verify every count above is present and agrees with the project.

**Acceptance Scenarios**:

1. **Given** a completed filing run, **When** its record is read, **Then** it shows projected
   deletions next to actual deletions.
2. **Given** a filing run that wrote user approvals on in-text analyses, **When** its record is read,
   **Then** the count is shown and worded as recorded-for-anything-in-use, never as the user having
   reviewed or affirmed them.

---

### Edge Cases

- **Second run after the first.** A project never parsed live cannot lose anything on its first
  filing run. Risk arrives with the second. The projection must reflect this, not warn in the
  abstract.
- **Analysis in use only through a gloss.** It is shielded, so it must not be projected as
  deletable.
- **Human disapproved analysis.** It is never deleted by filing, and it must not appear in the
  deletion projection. But if it is in use in a text, filing **overwrites the human's disapproval
  with an approval** (D-2). That must be projected and reported separately.
- **Word that now fails to parse** (zero analyses, no error). Every unshielded, unreviewed analysis
  of that word is deleted. This is the grammar-shrink path and the reason the projection is per
  wordform.
- **Parse result with an error** (timeout, exception). In a filing run it is filed exactly as FLEx
  files it. The parser's opinion is cleared, and every unshielded, unreviewed analysis of that word
  is deleted, even though the error says nothing about the grammar. That is why the projection's
  upper bound covers every word in scope, and why the run record counts errored words separately
  (FR-017).
- **Unchanged result.** FLEx skips a wordform whose stored checksum matches the new result. That
  word must be reported as unchanged, not as filed.
- **Project-wide side effect.** Each filed word causes the filer to remove every parser-sourced
  problem annotation in the project. This must be disclosed in the plan, even though no current
  code path creates them.
- **Object deleted mid-run.** The per-result liveness check catches deletion of a referenced object,
  not a changed rule that leaves the objects alive. The report must not claim more than that.
- **Filer unable to start its write.** The filer declines to run when a write is already in progress
  in the project. A headless caller must treat that as a failure to file that word, never as success
  or silent loss. This deliberately differs from FLEx, whose idle queue retries the update on every
  idle cycle until it succeeds. The report must say the word was not filed, not that it was
  deferred.
- **Project opened for writing saves on open.** A read-only open has been observed to rewrite the
  project file. The backup must be attempted before the project is opened for writing, not after.
- **Grammar edited between preview and confirmation.** The confirmed call must re-check, not trust
  the preview.
- **Plan changed between preview and confirmation** (for example, more deletable analyses). The
  confirmed call must not file against a plan the human never saw.
- **HermitCrab agent missing.** Refuse with `parser_agent_missing` at preview, never an unhandled
  lookup failure.
- **FLEx open on the project.** Exclusive: refused, as `run_module` does today. Shared: filing
  proceeds as a non-master peer, with an advisory that FLEx's own parser must not be running. The
  MCP cannot detect FLEx's parser, so two filers on one project remain possible, and that is
  disclosed rather than prevented.
- **Crash mid-run.** The words filed before the crash stay filed. The run record shows how far it
  got and points at the backup, or repeats the no-backup warning if none was taken.
- **Assistant asserts confirmation on the first call.** There is no way to reach filing without a
  preview first, and no argument or setting that skips the confirmation rung.

---

## Requirements *(mandatory)*

### Functional Requirements

**The write ladder (US1, US2; parent 12.4)**

- **FR-001**: The batch parse tool MUST accept an argument that requests filing (`apply`). Its
  absence MUST keep today's read-only behaviour exactly. The tool's capability annotation MUST NOT
  change (CP3 FR-025). The description's first line MUST stop saying filing is unreachable.
- **FR-002**: A filing request MUST pass the same four rungs as `run_module`, in `run_module`'s order:
  session writing enabled; `require_write_confirmation`; the existing project-access / lock gate;
  pre-write backup. The rungs MUST reuse `run_module`'s mechanisms, not copies of them.
- **FR-003**: Every rung MUST complete before a run identifier is issued. No path may exist by which
  a running job requests consent, backup or any other human decision.
- **FR-004**: No argument, configuration key or environment variable introduced by this feature may
  skip or pre-answer the confirmation rung. `require_write_confirmation` MUST default on.
- **FR-005**: An unconfirmed filing request MUST return `confirmation_required` with the mutation
  plan (FR-010) and MUST NOT write, back up, or open the project for writing.
- **FR-006**: A confirmed filing request MUST be bound to the plan it confirms. If the re-computed
  plan differs from the previewed one in scope or in any projected count, the system MUST return
  `confirmation_required` again with the new plan instead of filing.
- **FR-007**: The pre-write backup MUST be attempted through `run_module`'s mechanism and is
  best-effort (constitution Principle I): a backup failure MUST NOT raise or refuse the run
  (clarified 2026-09-23). The mutation plan MUST state the backup's expected outcome: will be taken;
  not expected, with the reason (for example insufficient disk space); or disabled by configuration.
  The human therefore confirms knowing whether a recovery point will exist.
- **FR-042**: No backup, run record, pre-deletion capture or other artifact produced by filing may be
  written inside the project's folder or any folder under it. They MUST live under the MCP's own
  data directory, as the existing backup and run-record roots already do. A copy inside the project
  folder can be committed by Send/Receive's Mercurial repository and balloon it.
- **FR-043**: When the project takes part in Send/Receive, the no-backup warning (FR-009) and the
  mutation plan MUST name the recovery route. That route is not restoring the local backup: do not
  Send/Receive the broken copy, delete it, and re-download the project. A local backup, where one
  exists, MUST be described as a convenience for that machine and not as a way to revert the shared
  project. How Send/Receive participation is detected is left to the plan.
- **FR-008**: The backup MUST be attempted before the project is opened for writing, and before the
  first filing run per (session, project). A backup taken earlier in the session by `run_module`
  MUST NOT satisfy this.
- **FR-009**: The response issuing the run identifier MUST name the backup's location. When no backup
  was taken, the response MUST instead carry a prominent warning. The warning MUST give the reason
  and state that filing cannot be undone and that no recovery point exists. The same warning MUST
  appear in the run record.

**The mutation plan and deletion projection (US1; parent 12.2, 9.3.3)**

- **FR-010**: The mutation plan MUST state: words in scope; the grammar's load-error standing (FR-020
  to FR-023); the deletion projection; the duplicate disclosure; the backup's expected outcome (FR-007); and
  the project-wide removal of parser problem annotations.
- **FR-011**: The deletion projection MUST be built on the conjunction: no user opinion **and** not
  in use in any text segment, either directly or through any of its glosses. It MUST NOT be built on
  "no user opinion" alone.
- **FR-012**: The projection MUST exclude human-disapproved analyses.
- **FR-013**: The projection MUST be computed from the project's actual state, per wordform, and MUST
  show a concrete number, including zero, never only an abstract warning.
- **FR-014**: The projection MUST be an upper bound on what filing can delete: no analysis may be
  deleted by the run that was not in the confirmed projection.
- **FR-015**: The projection MUST reuse CP3's segment-occurrence join and project-state probe (CP3
  FR-004, FR-043), not rebuild them.
- **FR-040**: The plan MUST separately project the human-disapproved analyses that are in use in a
  text, because filing will overwrite each of those disapprovals with an approval (D-2). This count
  MUST NOT be folded into the tacit-approval population.
- **FR-016**: The plan MUST disclose how many projected creations would duplicate an existing
  gloss-only analysis rather than complete it (parent 9.3.3). Merging is out of scope.

**Filing (US2; parent 5.2, 12.6)**

- **FR-017**: In a filing run, results that carry a parse error (timeout, exception) MUST be filed
  exactly as FLEx files them, for consistency with the FLEx menu and with the next parse. The plan
  MUST state that a word which errors loses its unshielded, unreviewed analyses. The run record MUST
  count errored words and the deletions they caused, separately from successful ones. Try-a-word
  modes MUST NOT file any result, errored or not (clarified 2026-09-23).
- **FR-018**: Filing MUST go through FieldWorks' own filer, with the HermitCrab parser agent as the
  filer's agent, so filed analyses carry honest parser provenance. The filer's deferred wordform
  update MUST be driven synchronously, through a real stand-in for the idle queue, never a null.
- **FR-019**: Each result MUST be checked for object liveness immediately before it is filed; a
  result that fails MUST be skipped and counted. When the filer declines to run a queued update
  because a write is already in progress, that word MUST be reported as not filed. (FLEx would
  retry; the headless path does not, and says so.)

**The refuse-to-file gate (US3; parent 12.3)**

- **FR-020**: If the parser cannot be built after the grammar loads, filing MUST be refused with
  `grammar_load_unclean` / `morpher_null`, with no override.
- **FR-021**: If this load has load errors that the MCP's own baseline for this project and scope
  does not, filing MUST be refused with `grammar_load_unclean` / `new_load_errors`, naming the new
  errors. The refusal's hint MUST name the only way past it: run a read-only parse of the same scope,
  which re-baselines. No argument, setting or flag may override it (clarified 2026-09-23).
- **FR-022**: Load errors present in the baseline MUST be warned about and counted in the plan, and
  MUST NOT block. With no baseline, every load error MUST be treated as pre-existing and the
  baseline source reported as `absent`.
- **FR-023**: The baseline MUST be the load-error set recorded by the MCP's own runs (CP3 FR-023),
  keyed to the scope fingerprint. FLEx's load-error file MUST NOT be used as a prior state.
- **FR-024**: The gate MUST be evaluated at preview, at the confirmed call, and again on the job's
  own grammar load before the first word is filed. A refusal at job time MUST end the run with
  nothing filed and MUST NOT pause or ask.
- **FR-039**: In addition to the load-error diff, the gate MUST compare the number of lexical forms
  eligible to reach the grammar against the baseline, using the loader's own eligibility rules
  (stem or clitic allomorph, not abstract, non-empty vernacular form; the rule-form equivalent for
  affixes). A drop MUST refuse filing, name the entries no longer eligible, and use the same
  re-baseline escape as FR-021. This closes the silent-exclusion path the load-error file cannot see (D-1). The
  refusal's signal value is an additive extension of `grammar_load_unclean`'s `signal` enum, named
  in the plan.

**Preflight refusals and concurrency (US4; parent 12.6, 12.7)**

- **FR-025**: The HermitCrab agent MUST be probed before any preview is built. If it is absent,
  filing MUST be refused with `parser_agent_missing`, never an unhandled lookup failure.
- **FR-026**: While a filing job runs on a project, a second filing request for that project MUST be
  refused with `parser_filing_in_progress`, carrying `run_id`, `started_at`, `words_completed` and
  `hint`, before any preview, backup or parse.
- **FR-027**: A filing job MUST NOT take a project-wide claim that blocks the MCP's run-reading
  tools (`parse_status`, `parse_log`, `parse_diff`) for that project. On a project with **sharing
  enabled**, it MUST NOT block read-only parses or single-word tries either. On a project with
  sharing **off**, read-only parses and single-word tries MUST be refused with
  `parser_filing_in_progress` while the job runs, and the refusal MUST say that they wait for the
  run. The filing job is that project's only opener: a read-only open takes the project lock, and
  a second writable open then fails (L-0, `evidence/l0-coexistence.json`). *Amended 2026-09-24 by
  the maintainer after L-0.*
- **FR-028**: The in-progress refusal MUST clear when the job reaches any terminal state, including a
  crash of the process that ran it.
- **FR-029**: The read-only tools (single-word try, read-only batch) MUST continue to open the
  project read-only. The standing boundary tests MUST stay green.
- **FR-030**: When FLEx has the project open in shared mode, filing MUST proceed as a non-master
  peer, reusing `run_module`'s shared-mode handling and its backup caveat for peers. Both the
  mutation plan and the result MUST carry a shared-mode advisory. It MUST state that FLEx's own
  parser must not be running on this project, that the MCP cannot detect whether it is, and that
  concurrent filing by both is not prevented. When FLEx holds the project exclusively, filing MUST
  be refused exactly as `run_module` refuses (clarified 2026-09-23).

**Durability and reporting (US2, US6)**

- **FR-031**: Before an analysis is deleted, the run record MUST capture enough of it (wordform,
  morph bundles, glosses, evaluations) to recognise and manually reconstruct it.
- **FR-032**: The run record MUST carry: the confirmed plan, the backup location, and actual counts of
  created, re-approved, duplicated, deleted, unchanged and skipped (by reason), plus projected
  deletions next to actual ones.
- **FR-033**: The run record MUST count analyses that gained a user approval during filing because
  they were in use, and MUST word it as recorded-for-anything-in-use. It MUST NOT label any analysis
  as tacit, unreviewed or auto-approved (parent 9.3.4; CP3 FR-042).
- **FR-041**: The run record MUST list, separately from FR-033's count, every analysis whose human
  disapproval was overwritten with an approval, capturing the prior evaluation first. The
  correction to parent 12.2 ("filing can never overwrite or revoke a human's opinion") MUST be
  recorded back into the parent spec.
- **FR-034**: Filed changes MUST be persisted to the project before the run reports success.
  Cancellation MUST stop at a word boundary, persist what was filed, and report it as filed and not
  undoable except by restoring the backup.

**Contract (parent 14)**

- **FR-035**: `parser_filing_in_progress` and `grammar_load_unclean` MUST be added to the tool contract additively (staying on `tool-responses/1.0`), with detail
  fields in the parent spec's order, and a CHANGELOG entry under "Tool contract".

**Verification (US5)**

- **FR-036**: Live verification with `FLEXLIBS_REQUIRE_LIVE=1` MUST produce a before/after evidence
  artifact for: the `MoveConcAnnotationsToWordform` edge case; the auto-approval survival (an in-text
  analysis survives a pass that a bare-no-opinion projection would have condemned); the HermitCrab
  agent lazy-creation question (parent 17.10); projection versus actual deletions; and refuse-to-file
  on a deliberately broken grammar load.
- **FR-037**: Live runs MUST use a disposable copy of a project, never a working project in place.
- **FR-038**: CP1 deferred re-probing the installed engine for public grammar-health checkers to
  CP4 (parent 9.5.3). The re-probe MUST run against the installed engine version and its finding
  MUST be recorded. It MUST NOT be assumed to be unchanged.

### Key Entities

- **Filing request**: a batch parse request with filing asked for. Carries scope, the
  confirmation flag, and the identity of the plan it confirms.
- **Mutation plan**: the preview. Contains words in scope, load-error standing, deletion projection,
  duplicate count, backup intent and disclosed side effects. Identified so a confirmation can be
  bound to it.
- **Deletion projection**: per wordform, the analyses that satisfy the conjunction (no user
  opinion, not in use by any segment directly or through a gloss, not human-disapproved). This is an
  upper bound on actual deletions.
- **Load-error baseline**: the load-error set from the MCP's own most recent run for a project and
  scope fingerprint, with its source (`this_run`, `prior_run:<run_id>`, `absent`).
- **Filing run**: a CP3 run with a filing section. Holds the in-progress claim for its project while
  it is not terminal. Records backup location, per-word outcome, and pre-deletion captures.
- **Pre-deletion capture**: a record of an analysis about to be deleted: wordform, morph bundles,
  glosses and evaluations.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of tested paths, no project write occurs before a human-visible preview and an
  explicit confirmation. The project file is byte-identical across every unconfirmed request.
- **SC-002**: In live verification, 100% of analyses actually deleted by a filing run appear in that
  run's confirmed projection, and no in-text analysis appears in any projection.
- **SC-003**: On a project never parsed live, the preview projects exactly 0 deletions.
- **SC-004**: In 100% of filing runs, the plan's stated backup outcome matches what happened. Every
  run that proceeded without a backup carries the no-recovery-point warning in its response and its
  record.
- **SC-005**: A deliberately broken grammar load is refused before any word is filed, in every
  tested variant (cannot build, new errors at preview, new errors after confirmation, and an
  entry dropped silently with no logged error).
- **SC-011**: Every human disapproval that a filing run overwrites is projected in its plan and
  listed in its record, in 100% of live cases.
- **SC-006**: A second filing request against a busy project is refused in under 1 second, with all
  four detail fields present.
- **SC-007**: While a filing run is active on a project with sharing enabled, a single-word try on
  the same project answers without waiting for the run to finish. On a project with sharing off,
  the try is refused at once with `parser_filing_in_progress`, whose hint says reads wait for the
  run. *Amended with FR-027, 2026-09-24.*
- **SC-008**: Zero configuration keys, arguments or environment variables in the shipped build can
  bypass confirmation for filing. This is verified by a test that enumerates the tool
  schema and configuration keys.
- **SC-009**: Each of the five live cases in FR-036 has a before/after evidence artifact.
- **SC-010**: The existing test suite and the read-only boundary tests remain green.

---

## Assumptions

- **Filing parses fresh.** A confirmed filing request runs a new batch through CP3's runner and files
  each result as it is produced. It does not replay a previously stored read-only run, because the
  filer needs live parse results and the per-result liveness check (12.6) only makes sense at
  filing time. Consequence: the preview's deletion figure is an upper bound ("may delete up to N"),
  not a prediction. A prior read-only run of the same scope MAY be used to say how many of those the
  parser is expected to produce again, labelled as an estimate.
- **Rung order follows `run_module`.** The issue lists backup before the lock gate. `run_module`
  probes access before backing up, so it never backs up a project FLEx holds exclusively. This spec
  keeps `run_module`'s order, which satisfies the issue's requirement that all rungs complete before
  a run identifier exists.
- **"Pre-existing load errors are benign"** is a working hypothesis (parent 12.3), not a proven fact.
  The plan states it that way.
- **If the HermitCrab agent is missing**, CP4 refuses. It does not create the agent. Whether FLEx
  creates it lazily is what the live check answers. If it does, a follow-up may downgrade the refusal
  to a warning with a remedy.
- **Backups** reuse the existing backup location (`~/.flextoolsmcp/backups/<project>/<timestamp>/`,
  outside every project folder), retention and naming. Run records already live under
  `~/.flextoolsmcp` as well. FR-042 makes that placement a requirement rather than an accident.
- **No liblcm checkout is present** in this environment (`C:\Github\liblcm` is absent, although the
  CLAUDE.md sibling table names it). `MoveConcAnnotationsToWordform`'s implementation was not read,
  which is why its behaviour is left to live verification (FR-036).
- **Only the HermitCrab engine files.** The engine gate from CP1/CP3 still applies.

## Out of Scope

- Completing a gloss-only analysis with parser morphology (the merge; parent 17.6). Disclosed, not
  built.
- The sandbox spine (CP5), contract polish, telemetry and user docs beyond the contract rows (CP6).
- Unattended or scheduled filing, and any confirmation bypass.
- Detecting or coordinating with FLEx's own background parser.
- Undo of a filing run, beyond restoring the backup (non-shared projects) or discarding and
  re-downloading the copy (Send/Receive projects).
- Any automation of the Send/Receive recovery route. It is named to the user, never performed.

## Verbatim Constraints

- Tool: `flextools_parse_text`; filing argument `apply` (issue text: `apply=true`); resubmission flag
  `confirmed=True`; first-call code `confirmation_required`.
- Rungs: session `write_enabled`, `require_write_confirmation`, `perform_pre_write_backup`,
  `needs_lock`.
- Error codes and fields, in this order:
  - `parser_filing_in_progress`: `run_id`, `started_at`, `words_completed`, `hint`
  - `grammar_load_unclean`: `signal` (`morpher_null` \| `new_load_errors`), `new_error_count`,
    `baseline_error_count`, `baseline_source` (`this_run` \| `prior_run:<run_id>` \| `absent`),
    `log_path`
  - `parser_agent_missing` (existing, unchanged)
- Live gate: `FLEXLIBS_REQUIRE_LIVE=1`.
- Named edge case: `MoveConcAnnotationsToWordform`.
- Contract version stays `tool-responses/1.0`.
