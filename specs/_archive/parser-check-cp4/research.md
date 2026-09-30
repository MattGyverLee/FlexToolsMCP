# Research: parser-check CP4 -- the first write

**Date**: 2026-09-23 · **Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md)

This is the Phase 0 output. Every entry was checked against source in this checkout:
`FieldWorks/Src/LexText/ParserCore`, `FieldWorks/Src/Common/FwUtils`, the installed
`flexicon` in `.venv`, and `src/flextoolsmcp`. Where the spec or the parent spec says
something that the source contradicts, the entry says so plainly.

Entry format: **Decision** / **Rationale** / **Alternatives considered**.

---

## R-01 -- CP3's deletion projection is not an upper bound. CP4 must not reuse its predicate

**Finding.** `signals/projections.py:50` `_is_deletion_candidate` uses three
conjuncts: `not is_human_record(record)`, then user `noopinion`, then `in_segment is
False`. `is_human_record` (`signals/oracle.py:220`) returns True for any analysis that
the parser never evaluated.

FLEx's filer uses a different predicate. `ParseFiler.UpdateWordforms`
(`ParseFiler.cs:226-227`) resets the parser's opinion to `noopinion` on **every**
analysis in `AnalysesOC`. `SetUnsuccessfulParseEvals` (`:312-315`) then deletes any
analysis that still has parser `noopinion` and user `noopinion`. It does not care who
created the analysis. So an analysis a person made, never evaluated and never used in a
text **is deleted by FLEx, but is not counted by CP3's projection**. If CP4 reused CP3's
predicate, FR-014 (the projection is an upper bound) would be false.

- **Decision.** CP4's projection uses exactly the two conjuncts FR-011 names:
  - user opinion is `noopinion`, **and**
  - the analysis is not referenced by any segment, directly or through a gloss.

  It is a new function beside CP3's, `filing/projection.py:deletion_upper_bound`. CP3's
  informational projection is left alone. It stays CP3's report, and its docstring gains
  one line saying it is **not** the filing bound. The segment join itself is still
  CP3's `oracle.segment_occurrence`, so FR-015 is met. Only the predicate differs.
- **Rationale.** FR-011 already states the right predicate. The trap is the natural
  reading of FR-015 ("reuse CP3's projection"): what must be reused is the join and the
  probe, not CP3's candidate filter.
- **Alternatives considered.** *Fix CP3's predicate in place.* Rejected: CP3's number
  answers a different question (which parser-made records a pass could drop), and that
  output shipped. *Drop the parser-created conjunct from CP3.* Rejected for the same
  reason.
- **Test consequence.** `test_filing_projection.py` gets a fixture with a human-made,
  unevaluated, unused analysis. CP3's predicate returns 0 for it; the filing bound must
  return 1.

## R-02 -- The upper bound is enforced per word at filing time, not just previewed

**Finding.** There are three ways the bound computed at preview could be too small by
the time a word is filed:
- CP3's join is cached for the worker's whole life (`worker_main.py:1208`), so it can be
  out of date by the time of the preview.
- The join walks `Texts.GetAll()` segments only (`:1230`). The filer uses
  `wordform.OccurrencesBag` (`ParseFiler.cs:305`).
- The lexicon moves during an hours-long job, which is normal practice (parent 12.6).

- **Decision.** Immediately before each `ProcessParse`, the filing worker works out the
  filer's own would-delete set for that word. It uses the filer's exact predicate on the
  live objects:
  - it is an existing analysis;
  - no analysis in the new result `MatchesIWfiAnalysis` it (a public method on
    `ParseAnalysis`);
  - user `noopinion`;
  - not in any `seg.AnalysesRS` of `wordform.OccurrencesBag`, directly or through a
    gloss.

  For an errored result, "matched" is empty. If any member of that set is **not** in the
  confirmed projection, the word is skipped with reason `outside_projection` and
  nothing is filed for it. The same pass writes the pre-deletion captures (FR-031) and
  the disapproval-overwrite captures (FR-041).
- **Rationale.** This turns FR-014 from a hope into a guarantee the code enforces. SC-002
  ("100% of actual deletions were in the projection") then holds by construction, and
  live verification confirms it rather than being the only evidence for it. It also
  gives FR-031 its capture point for free, because the capture has to happen at exactly
  this moment anyway.
- **Alternatives considered.** *Trust the preview.* Rejected for the three reasons in
  the finding. *Refuse the whole run on any divergence.* Rejected: the lexicon
  legitimately moves under a long job, and a run-wide stale verdict is the thing parent
  12.6 rejects.
- **Preview join freshness.** The preview builds a **fresh** join
  (`segment_occurrence(self._iter_segments())`) and does not use the cached one. The
  runtime check uses `OccurrencesBag`, the filer's own source. Where they disagree, the
  preview over-projects, which is the safe direction.

## R-03 -- Driving the filer headlessly: a real, paused `IdleQueue`, pumped by hand

**Finding.**
- The constructor is `ParseFiler(LcmCache, PropertyTable, Action<TaskReport>, IdleQueue,
  ICmAgent)` (`ParseFiler.cs:96`).
- `UpdateWordforms` is **private**. `ProcessParse` only enqueues the work, then calls
  `m_idleQueue.Add(Low, UpdateWordforms)`, which replaces any existing entry
  (`update=true`).
- `IdleQueue` (`FwUtils/IdleQueue.cs:145`) is a concrete `ICollection<IdleQueueTask>`.
  `IsPaused = true` unhooks it from `Application.Idle`. `IdleQueueTask.Delegate` and
  `.Parameter` are public.
- FieldWorks' own tests (`ParserCoreTests/ParseFilerProcessingTests.cs:97-102, 143-144`)
  drive it exactly this way.
- `TaskReport`'s constructor calls the handler straight away (`TaskReport.cs:37-42`), so
  the handler must not be null.

- **Decision.**
  - Build a real `IdleQueue { IsPaused = true }`.
  - Pass a no-op `Action[TaskReport]` and `propertyTable=None`. A null property table
    makes `CheckParserUpdatesAnalyses` default to true (`:193`).
  - Pass the HermitCrab agent resolved by GUID.
  - After each `ProcessParse`, pump the queue with no unit of work open. Snapshot it with
    `list(q)`, then for each task call `q.Remove(task)` and `ok = task.Delegate(task.Parameter)`.
  - `ok == False` means `CanStartUow` was false (`:165-166`). That word is reported
    `not_filed` / `filer_declined` (FR-019).
- **Decision (declined work must not leak).** A declined batch stays in the filer's
  private `m_workQueue`, and the next `ProcessParse` would file it silently. To prevent
  that, **the filer is constructed once per word** and dropped after its pump. The
  queue and filer are cheap. The grammar lives in the parser, not the filer.
- **Rationale.** This meets FR-018's "a real stand-in, never a null" and parent 5.2's
  implementation note. A literal `null` only works because a `Debug.Assert` is compiled
  out of release builds. Rebuilding the filer per word makes a decline a property of
  that word alone.
- **Alternatives considered.**
  - *Reflect on the private `UpdateWordforms`.* Rejected: it binds to a non-public member
    the capability probe cannot sensibly cover.
  - *One filer, re-pump on the next word.* Rejected: the declined word would be filed
    later, out of order, and outside its own liveness check.
  - *Subclass `IdleQueue`.* Rejected: `Application_Idle` is private and non-virtual,
    and pausing already gives full control.
- **Capability probe.** Parent 5.4 lists `ParseFiler.ProcessParse(...)` as spine-2
  surface. CP4 adds these members to the reflective check:
  - `ParseFiler..ctor(5)` and `ProcessParse(IWfiWordform, ParserPriority, ParseResult,
    bool)`;
  - `IdleQueue..ctor()`, `IsPaused`, `Remove(IdleQueueTask)` and `GetEnumerator`;
  - `ParseAnalysis.MatchesIWfiAnalysis`.

  If any is missing, filing is `unavailable` with `parser_core_missing` /
  `incompatible_surface`, an existing code. Bind positionally (parent 5.4).

## R-04 -- The raw `ParseResult`: flexicon's facade already returns it

**Finding.** `flexicon/code/Parser/ParserOperations.py:447` `ParseWord` returns
`handle.ParseWord(word)`. That is the parser's own .NET `ParseResult`, carrying live
`IMoForm`/`IMoMorphSynAnalysis` references. It is exactly what
`ParseFiler.ProcessParse` takes. `HCParser.ParseWord` returns **null** when the morpher
is null (`HCParser.cs:89-90`), and the facade passes that null through.

- **Decision.** The filing worker gets its parser through `project.Parser` (the facade),
  just as the read worker does. It does not construct `HCParser` itself.
  - A `None` result is `grammar_load_unclean` / `morpher_null` (FR-020).
  - After a grammar load, a bare probe parse (`ParseWord` on the first word in scope)
    that returns `None` refuses before anything is filed.
- **Rationale.** This keeps parser construction in one place and keeps `test_cp1_boundary.py`'s
  allowlist unchanged. The facade's lazy-import and capability guarantees (parent 5.4)
  then cover the write spine too.
- **Alternatives considered.** *`HCParser(cache)` in MCP code.* Rejected: it would be a
  second construction site and a boundary-test allowlist change for no gain.

## R-05 -- The facade silently reloads a stale grammar before every parse

**Finding.** `ParseWord`'s docstring: "a stale grammar is reloaded first." The user may
edit the grammar while an hours-long filing job runs, and that is normal practice. If the
gate were checked only before the first word (FR-024's literal wording), a mid-run reload
could bring in new load errors and then file against them. That is exactly the deletion
case US3 exists to prevent.

- **Decision.** Before each word, the filing worker calls `project.Parser.IsUpToDate()`.
  If the grammar is stale, it reloads explicitly (`Reload()`) and **re-runs the whole
  gate**: morpher null, the load-error diff and the eligibility count. Any of these
  refusals ends the run at that word boundary:
  - it is recorded as `refused_midrun` with the signal;
  - the words filed so far are persisted and reported as filed (FR-034);
  - nothing is asked (FR-024).
- **Rationale.** FR-024 requires the gate "on the job's own grammar load". A mid-run
  reload **is** one of the job's own grammar loads. The spec named the first one because
  it did not know about the facade's auto-reload.
- **Open, live (R-13 Q3).** Do the filer's own writes (new `WfiAnalysis` objects) mark the
  grammar stale? That depends on which classes `ParserModelChangeListener` watches. If they
  do, this rule means a reload per word, which is catastrophic for throughput but safe.
  The live question is scheduled in Phase 1. The fallback, if they do, is to compare a
  grammar-object change stamp rather than use `IsUpToDate`.

## R-06 -- FLEx's lowercase side-filing is not reproduced

**Finding.** `ParserWorker.ParseAndUpdateWordform` (`ParserWorker.cs:164-181`) also files
the **lowercase** form through `ProcessParse(ITsString, ...)`. That path
`FindOrCreateWordform`s it, and a wordform created that way is outside the confirmed
scope. That is ParserWorker behaviour, not filer behaviour. It would reach into wordforms
whose analyses were never projected.

- **Decision.** CP4 files only the in-scope `IWfiWordform` overload. The plan and the run
  record each carry one line disclosing the divergence: "FLEx's menu also files the
  lowercase form of a capitalised word; this run does not."
- **Rationale.** FR-014's bound is per in-scope wordform. Following FLEx here would
  delete outside the projection, and R-02's guard would then have to skip exactly those
  words.
- **Alternatives considered.** *Reproduce it and add lowercase wordforms to the
  projection.* Rejected for CP4: it widens scope past what the user named. It can be a
  follow-up if parity turns out to matter.

## R-07 -- The write ladder is inline and must be extracted, not copied

**Finding.** None of `run_module`'s rungs is a reusable function. Confirmation, the
access gate and backup are written inline at `handlers/execution.py:~4480-4710` (at `2aedb1d`), inside
`handle_run_module`'s `try:`. The leaves *are* reusable:
- `probe_project_access` and `build_access_remedy` (`project_access.py:374`, `:290`);
- `perform_pre_write_backup` (`backup.py:70`);
- `session_state.was_backed_up` and `record_backup`;
- `error_response`.

- **Decision.** Extract rungs d-f (confirmation, access gate, backup) into
  `server/write_ladder.py`:
  - `probe_write_access(project) -> AccessDecision`: the refusal or advisory for
    `open_exclusive`, `held_by_other`, `open_shared` and `stale_lock`;
  - `backup_intent(project, *, session_key) -> BackupIntent`: the backup outcome,
    predicted and never performed;
  - `take_backup(project, *, session_key, peer) -> BackupOutcome`.

  `handle_run_module` is refactored to call them with **no behaviour change**, proven by
  the existing ladder tests. The serialisation rung (`get_project_write_lock`) stays with
  each caller.
- **Rationale.** FR-002 says "reuse, not copies". Constitution Principle VI says parallel
  copies of a safety path are forbidden. The refactor carries risk, so it is its own
  phase, and the green-before and green-after ladder suite is its exit condition.
- **Why the lock stays out.** `get_project_write_lock` is an in-process asyncio lock.
  Holding it for an hours-long job would block `run_module` writes on that project for
  hours. Filing does not need it, because filing's writes run in its own worker process,
  and that is covered by R-09.
- **Alternatives considered.**
  - *Call `handle_run_module` internally.* Rejected: its rungs take cert/cud inputs that
    exist only for Python scripts.
  - *Copy the block.* Forbidden by FR-002.

## R-08 -- Confirmation for filing is unconditional, and bound to a plan identifier

**Finding.**
- `require_write_confirmation` is a config key (`config.py:78`, default True).
  `flextools_manage_config` (`handlers/admin.py:687-757`) can set it to false, with no
  guard.
- `confirmed` is a bare boolean the caller asserts. Nothing checks that a confirmed call
  matches any preview (there is no token anywhere in `src`).

So, as shipped, SC-008 ("zero keys, args or env vars can bypass confirmation for
filing") would fail on day one, and so would the edge case "assistant asserts
confirmation on the first call".

- **Decision.**
  - **Filing always requires confirmation.** Filing reads `require_write_confirmation`
    only to report it, and never lets it lower the rung. A `false` value is disclosed in
    the plan: "confirmation is required for filing regardless of this setting". FR-004's
    "MUST default on" is met, and exceeded, for filing.
  - **Plan binding (FR-006).** The preview issues `plan_id`, which is sha256 over the
    canonical plan: scope fingerprint key, words in scope, each projected count, the
    per-wordform projected analysis-GUID sets, the gate standing, the backup outcome and
    the shared-mode verdict. It is held in session state, in
    `filing_plans[(project, scope_key)]`.

    A confirmed call must carry `confirmed=True` **and** a `plan_id` equal to one this
    session issued. The handler then recomputes the plan. If the recomputed id differs,
    or no plan was issued, the answer is `confirmation_required` again with the new plan
    and a new `plan_id`.

    There is therefore no request shape that reaches filing without a preview in the same
    session.
- **Rationale.** A confirmation that is not bound to what was shown is the audited hole
  parent 12.4 describes. `plan_id` is additive to the verbatim `confirmed=True`, not a
  replacement for it.
- **Honest limit (stated in the plan and the contract).** This proves a preview was
  **issued and unchanged**. It does not prove a human **read** it. Nothing in a stdio
  tool can prove that. It is a safety property, not a security boundary (constitution I).
- **Alternatives considered.**
  - *Honour `require_write_confirmation=false` for filing.* Rejected: SC-008.
  - *Time-limited plans.* Rejected as unnecessary: recomputation already catches a stale
    plan, and expiry would add a way to fail for no safety gain.

## R-09 -- The filing worker is its own process role, opened for writing. Read tools keep theirs

**Finding.**
- `WorkerPool` (`worker_client.py:719`) keys workers by (project, role). The roles are
  `SHARED_ROLE` and `MEASUREMENT_ROLE`.
- The read worker opens with the literal `writeEnabled=False` (`worker_main.py:714-730`).
  `test_parse_no_project_writes.py:102` asserts that literal for every `OpenProject` in
  `parse/`, `signals/` and `handlers/parse.py`.

- **Decision.**
  - Add a `FILING_ROLE`. Its entry module is a **new package** `server/filing/`,
    outside the scanned read-only set, and it is the only place `writeEnabled=True`
    appears. The read-only worker, its message set and its standing tests stay
    byte-for-byte as they are (FR-029).
  - The filing worker imports read-only helpers from `parse/` (scope, fingerprint, the
    segment join), never the other way round.
  - When the filing run ends, the shared read worker for that project is **recycled**.
    Its cache predates the filing, and a read-only diff against it would be stale.
- **Rationale.** Keeping the write spine in a separate package makes FR-029 a structural
  fact that the existing tests keep proving, not something re-audited in every review.
  It also gives FR-027 for free: reads go to a different process.
- **Alternatives considered.**
  - *A write mode inside `worker_main.py`.* Rejected: it breaks the standing no-writes
    test, or forces an allowlist inside the one file the test exists to protect.
  - *Route reads through the filing worker while it runs.* Rejected: that is a writable
    open serving read tools, the opposite of FR-029.

## R-10 -- Two processes on one project: the live question the plan cannot answer from source

**Finding.**
- During a filing run, the read worker (read-only open) and the filing worker (writable
  open) both hold the same project.
- For a **shared** project, LCM's shared XML backend and commit log are designed for this.
- For a **non-shared** project, it is unverified. Nothing in this checkout shows whether
  a writable open writes `<P>.fwdata.lock`, whether a later read-only open honours it,
  or whether the read worker's release can write the file.
- Memory note `parse-worker-saves-xample-project`: the "read-only" worker **was observed
  rewriting `Sena 3.fwdata`** (only `DateModified` changed) on the engine-refusal path,
  not yet root-caused. A whole-file rewrite by the read worker after the filing worker
  has saved would **silently revert the filing**.

- **Decision.** This is a **Phase 1 blocking live question** (quickstart L-0), answered
  on a disposable copy before any filing code is merged. There is a mandated safe default
  until it is answered:
  - Before a filing job starts on a **non-shared** project, the handler **releases** the
    shared read worker for that project.
  - While the job runs, read requests for that project (try-a-word, read-only batch) are
    **refused** with the existing `parser_filing_in_progress` refusal.
  - Shared projects are not restricted.
- **This conflicts with FR-027 / SC-007 for non-shared projects**, and the plan says so
  rather than absorbing it. There are two outcomes:
  - If L-0 shows that read-only coexistence is safe (no save on release, no lock
    conflict), the safe default is dropped and FR-027 holds everywhere. That is the
    expected result on HermitCrab projects, which the memory note says were not saved.
  - If it is not safe, the restriction stays for non-shared projects, and the spec needs a
    maintainer amendment to FR-027. That is a `needs_human` stop, not a silent downgrade.
- **Also in scope of L-0: the root cause of the XAmple-path save**, because it is the
  same mechanism. Fixing it may be what makes coexistence safe.
- **Upstream #147 (`106a2ff`)** now calls `RefreshFromDisk` before `CloseProject` on
  `run_module` write runs, so that a foreign save during a run does not leave a stale
  cache to be committed over it. That is the same hazard, seen from the writer's side.
  The filing worker reuses it at teardown. L-0 must check whether it is enough for the
  **reader** side too, when the read worker releases after the filing worker has saved.
- **`run_module` during filing.** If the filing worker's writable open produces a lock
  file held by a Python PID, `probe_project_access` returns `held_by_other`, and
  `run_module`'s writes to that project are refused naturally. L-0 confirms which case
  applies. If no lock is written, the handler refuses `run_module` writes on a project
  with an active filing claim through the same access decision (R-07's `probe_write_access`
  gains a filing-claim check).

- **Outcome (L-0, run live 2026-09-24; `evidence/l0-coexistence.json`): coexistence FAILS
  on a non-shared project.**
  - The read worker's read-only open writes `<P>.fwdata.lock` with its own interpreter's
    PID (`ProcessName: python`).
  - A second process's `OpenProject(writeEnabled=True)` then raises `FP_FileLockedError`
    ("This project is in use by another program"). The same open succeeds once the read
    worker is released.
  - The two cannot hold the project at once. So the release before the writable open is
    **required, not interim**: it is now unconditional on non-shared projects.
    `READS_REFUSED_ON_NON_SHARED_DURING_FILING` stays `True`, because a read during the run
    could not open the project anyway.
  - **FR-027 / SC-007 cannot hold on non-shared projects. This is a `needs_human` stop:
    the maintainer must amend FR-027.** Shared projects are unaffected.
  - The filing worker's own lock (a Python PID) makes `probe_project_access` answer
    `held_by_other`, so `run_module` writes during filing are refused naturally. That was
    the first case of the `run_module` bullet above.
  - The read worker's release did **not** rewrite the file after the filing worker saved
    (sha256 and mtime unchanged). The filed analysis is read back by a fresh worker.
  - On the XAmple engine-refusal path, the memory-noted save was **not reproduced** (the
    sha256 and mtime of a `Sena 3` scratch copy are unchanged). Its cause lies on a path
    that gets past the engine gate.
  - The run found four defects that only a live run could show; all four are fixed and
    listed in the evidence file. One changed this decision: the access gate refused the
    server's **own** read worker's lock as `held_by_other`. The handler now recognises that
    lock (the worker reports its own PID in `ready`), releases the worker, and probes
    again.

## R-11 -- The in-progress claim: an in-process registry, swept on startup

- **Decision.**
  - `filing/claims.py`: a per-project map in the server process of `run_id`, `started_at`
    and a live `words_completed` counter read from the runner handle.
  - It is checked as the **first** statement after project resolution, before engine,
    scope, preview, backup or parse (FR-026). That keeps it under a second (SC-006),
    because nothing heavy runs first.
  - The claim is released in the runner's terminal-state transition, in a `finally`.
  - **Crash of the worker process**: the runner already marks the run `failed/crashed`,
    which releases the claim.
  - **Crash of the server process**: the registry is gone with it. On startup, a sweep
    marks any run whose `meta.json` shows a non-terminal filing stage as `crashed` and
    writes the record's no-backup or backup pointer again (FR-028; edge case "Crash
    mid-run"). This follows the existing `test_startup_lock_sweep.py` pattern.
  - The claim is **not** a project lock. It blocks only filing requests, plus, under
    R-10's interim default, reads on non-shared projects.
- **Rationale.** FR-027 forbids a project-wide claim. `test_parse_no_edit_blocking.py`'s
  forbidden names (`get_project_write_lock`, `check_project_locked`, `locking`, ...)
  stay absent from `parse/`, `signals/` and `handlers/parse.py`.
- **Alternatives considered.**
  - *A lock file on disk.* Rejected: it survives crashes, which is exactly the wrong
    direction for FR-028, and it pollutes the projects directory.
  - *Reuse `get_project_write_lock`.* Rejected: see R-07.

## R-12 -- The refuse-to-file gate: baseline lookup, eligibility count, and the new signal

**Findings.**
- CP3 **records** a baseline (`worker_main.py:1270`, stored at `runner.py:796-806` into
  `RunMeta.load_error_baseline` with `scope_fingerprint_key`). There is **no lookup**.
- `HCLoader.IsValidLexEntryForm` (`HCLoader.cs:579-589`) and `IsValidRuleForm`
  (`:536-569`) are **private instance** methods, and the rule-form one depends on
  `IsValidEnvironment`. They cannot be called by reflection without an `HCLoader`
  instance mid-load.

**Decisions.**
- **Baseline lookup.** `filing/gate.py:find_baseline(project, scope_key)` looks through
  `record.list_run_ids()` for the newest run with that project and
  `scope_fingerprint_key` and `load_error_baseline.captured == True`. Newest means by
  `created_at`, not by name: CP3's R-03 class.
  - Filing runs count as baseline sources too. A read-only run of the scope is the
    documented escape.
  - `baseline_source` is `prior_run:<run_id>`, or `absent`. `this_run` is used only for
    the job-time re-check against the confirmed call's own preview load.
- **Comparison.** Errors are compared as a multiset of canonicalised `<LoadError>` entries,
  with `Hvo` already dropped by CP3. "New" means present now and not in the baseline.
  Errors in the baseline but not now are reported as resolved and do not block.
- **Eligibility count (FR-039, D-1).**
  - A port of the two predicates in `filing/eligibility.py`. An entry is eligible if it
    has at least one `IsValidLexEntryForm` form, or `HasValidRuleForm` holds. Circumfixes
    need both a valid prefix and a valid suffix alternate.
  - Environment-dependent affix validity (infix positions, bracketed affix forms) is
    treated as eligible **when the shape is valid**. An environment failure *is* logged by
    the loader (`InvalidEnvironment`), so the load-error diff catches it. That keeps the
    port to the parts the logger cannot see, which are D-1's parts exactly.
  - The baseline stores the eligible-entry GUID set. CP3's baseline object gains one
    additive key, `eligible_entries: [guid, ...]`, and CP3's artifact contract is amended
    additively.
  - A drop means baseline GUIDs are absent now. It refuses with a new signal and names
    the missing entries.
- **Parity proof.** A **live** test compares the port's eligible count to the entry count
  of the grammar HermitCrab actually loaded, read in the live test only through the
  loaded `Language`. A mismatch fails the live suite. The port is a copy of C# logic, and
  this is how it is kept honest (Principle VI).
- **New signal value: `eligible_forms_dropped`** (FR-039: "named in the plan"), an
  additive extension of `grammar_load_unclean.signal`.
- **Detail fields.** The parent's five fields are kept in the parent's order. Four
  additive fields are **appended after** `log_path`: `new_errors`, `dropped_entries`,
  `baseline_eligible_count` and `eligible_count`. Appending keeps parent 14's order a
  prefix, and FR-021 needs `new_errors` to name the errors. See `contracts/tools.md`.
- **Alternatives considered.**
  - *Reflect on the loaded `Language` for the count in production.* Rejected: it cannot
    name the dropped entries (FR-039), and it binds a private field.
  - *Compare FLEx's `HCLoadErrors.xml` directly.* Forbidden by FR-023.

## R-13 -- The live questions, and what each blocks

| # | Question | Blocks | Safe default until answered |
|---|---|---|---|
| Q0 | Two-process coexistence on a non-shared project (R-10), plus the root cause of the read-worker save | FR-027 on non-shared projects | Release the read worker; refuse reads for that project during filing |
| Q1 | `MoveConcAnnotationsToWordform` edge case (FR-036). The filer never calls it (it is only in `UserAnalysisRemover.cs:121` and `MorphologyListener.cs:625`). The live question is where a segment reference ends up when an analysis it points at is deleted **through the generic `Delete()` path** the filer uses | nothing; evidence only | none needed: R-02 means filing never deletes an in-use analysis, and the filer shields them anyway |
| Q2 | HermitCrab agent lazy creation (parent 17.10). `ParserWorker.cs:71` expects the agent to exist, and nothing in FieldWorks creates it lazily | a later downgrade of the refusal to a warning | refuse with `parser_agent_missing` (spec assumption) |
| Q3 | Do the filer's writes mark the grammar stale (R-05)? | throughput only | re-gate on every reload, which is safe but possibly slow |
| Q4 | FR-038: re-probe the installed engine for public grammar-health checkers | nothing; a recorded finding | none |
| Q5 | Does `ParseResult.GetHashCode()` in our worker match the checksums FLEx stored? It is built from `string.GetHashCode` (`ParseResult.cs:62-69`), which is stable on .NET Framework but can differ by bitness | the accuracy of the "unchanged" count | a mismatch only causes an idempotent re-file. US2 AS-6 is tested on MCP-filed checksums, re-filed by the MCP |

**Agent lookup.** `parser_probe.probe_hc_agent` (`parser_probe.py:810`) reads
`LangProject.DefaultParserAgent`. The filer needs the agent **by GUID**
(`CmAgentTags.kguidAgentHermitCrabParser`), as `ParserWorker.cs:71` does. Two decisions
follow:
- Filing's preflight calls the existing probe (FR-025).
- The filing worker then resolves by GUID and treats a `KeyNotFoundException` there as
  `parser_agent_missing` / `lookup_failed`.

The probe finally gets its first production caller, which it has lacked since CP1.

## R-14 -- Send/Receive participation, and where filing artifacts live

**Finding.** Nothing in `src` detects Send/Receive. The backup root is
`~/.flextoolsmcp/backups` (`backup.py:47`) and the record root is
`~/.flextoolsmcp/parse-runs` (`record.py:130`), which can be overridden by
`FLEXTOOLSMCP_PARSE_RECORD_DIR`. Both are outside every project folder.

- **Decision (detection).** A project takes part in Send/Receive when `<projects>/<P>/.hg`
  is a directory. Chorus keeps the Mercurial repository there. The result is reported as
  `send_receive: true | false | unknown`. `unknown` (the projects directory cannot be
  resolved) is treated as `true` for the wording, because naming the discard-and-
  re-download route costs nothing when it turns out not to apply.
- **Decision (FR-042 enforcement).** `filing/paths.py:assert_outside_project(path,
  project_dir)` resolves both paths and refuses to write any filing artifact whose real
  path is inside the project directory. `FLEXTOOLSMCP_PARSE_RECORD_DIR` pointing inside a
  project folder is therefore refused at filing time, not at CP3 read time. A test sets
  that variable to a project subfolder and asserts a refusal.
- **Decision (wording, FR-043).** For S/R projects, the plan and the no-backup warning
  name the route: do not Send/Receive, delete the local copy, re-download. A local backup,
  where one exists, is described as "a convenience for this machine, not a way to revert
  the shared project."
- **Alternatives considered.** *Read `.hg/hgrc` for a remote.* Rejected: it adds nothing
  to the wording decision and reads a file the MCP has no other reason to touch.

## R-15 -- The four ladder inputs `run_module` has and filing does not

| `run_module` input | Filing equivalent | Decision |
|---|---|---|
| per-call `write_enabled` (overrides the session) | none | **Session only.** `ParseTextInput` gains no `write_enabled`. US1 AS-5 asks for a refusal when the session has writing disabled, and a per-call override would make that meaningless |
| `compute_is_mutating_script(cert, cud)` | always mutating | `apply=True` **is** the mutating declaration |
| `build_writeability_payload(code, ...)` | the mutation plan | `filing/plan.py:build_plan`, a different payload behind the same `confirmation_required` code |
| per-call `backup_before_write` | none | **Config only.** The config opt-out is honoured and disclosed (US2 AS-3). No per-call knob is added, so the plan's stated outcome cannot be changed between preview and confirm |

## R-16 -- Tests that CP4 changes deliberately, and why each change is not a weakening

| Test | Today | CP4 change | Why it is not a weakening |
|---|---|---|---|
| `test_parse_text_handler.py:265` schema is exactly N fields, filing arg absent | asserts absence | assert the exact new set: `apply`, `confirmed`, `plan_id` added | still an exact-set assertion |
| `test_parse_text_handler.py:295` first line says "not yet reachable" | asserts that phrase | asserts the new first line (FR-001) | still pinned |
| `test_parse_text_handler.py:211` `filing == FILING_NOT_REACHABLE` | read-only runs | read-only runs now carry `filing: "not_requested"` | still pinned |
| `test_parse_no_project_writes.py:171` filing unreachable from every stage | no inbound edge | FILING reachable **only** on a run created with `filing=True`; unreachable for every read-only run | the read-only claim is kept, per run |
| `test_parse_no_project_writes.py` (scan set) | `parse/`, `signals/`, `handlers/parse.py` | **unchanged scan set**; `filing/` is scanned by a new *inverse* test that pins where writes may occur | read spine untouched |
| `test_parse_no_edit_blocking.py:130` forbidden names | three modules | unchanged, and extended to `filing/claims.py` | the claim is not a lock, and the test proves it |
