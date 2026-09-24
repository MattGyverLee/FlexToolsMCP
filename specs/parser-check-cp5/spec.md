# Feature Specification: parser-check CP5 -- the sandbox spine: hardened hcparse.ps1, flextools_parse_sandbox, corpus assertions

**Feature Branch**: `feat/parser-check-cp5`

**Created**: 2026-09-24

**Status**: Draft -- `lex-domain` gate cycle 1 run 2026-09-24: APPROVED, no blocking findings (two wording fixes applied). Three questions deferred to clarify (Q1-Q3, each with an adopted default)

**Input**: User description: "create a spec to resolve https://github.com/MattGyverLee/FlexToolsMCP/issues/166"

**Source document**: GitHub issue #166 (the durable definition of CP5; self-contained by design)
**Parent spec**: [`../parser-check/SPEC.md`](../parser-check/SPEC.md) -- sections 1.1, 1.2, 2 (S3, S4, S6),
4, 5.3, 5.5, 6.2, 7, 10, 10.1, 10.2, 11, 12.5, 13, 14, 15 (CP5 row), 16. If pruned, recover with
`git show e5afbfd:specs/parser-check/SPEC.md`.
**Predecessors**: CP1-CP4 on `main` (CP4 merge `b8c5df6`). The issue says the sandbox spine is
independent of the write spine; #165 is a sequencing dependency, not a code dependency.
**Successor**: #167 (CP6 -- contract codes, CHANGELOG, telemetry, user docs).

**Source-verified against** (2026-09-24):
- `sillsdev/machine` at `b77b2337` (cloned at `C:\Github\machine`),
  `src/SIL.Machine.Morphology.HermitCrab.Tool/` -- `Program.cs`, `ParseCommand.cs`, `TestCommand.cs`,
  `StatsCommand.cs`, `MorphInfo.cs`, `Extensions.cs`, and the `.csproj` (at tags `v3.7.0`, `v3.8.0` and `v3.9.4`).
- `fieldworks` `Src/GenerateHCConfig/Program.cs` and `ConsoleLogger.cs`.
- The installed FieldWorks 9.3.11 (`SIL.Machine.Morphology.HermitCrab.dll` 3.8.2) and this machine's
  .NET installation (runtime 8.0.23 only, no SDK).

---

## Summary

The first four checkpoints ask the parser about the grammar **as it is in the project**. CP5 adds
the third spine: a **rehearsal space**. The linguist, or the assistant on their behalf, exports the
project's grammar to a HermitCrab configuration file, and optionally copies it into a named sandbox
and edits it ("tighten the left environment on this rule"). They then run words, or a whole corpus
of expected parses, against that file with the stand-alone `hc` tool. Nothing in this spine can
reach the live project. The copy, the export and the parse all happen on files the MCP made, and
`hc` reads only its three file arguments. That is what makes speculative edits safe (parent 1.2:
"Tweaking an exported grammar to test a theory IS safer than changing the whole database").

The spine's risks are disk and subprocess, not the lexicon. The maintainer's `hcparse.ps1` already
works, and CP5 hardens it (H1-H12) instead of replacing it. Four of those changes alter behaviour:

- **H1 -- find `hc` where it is actually installed.**
- **H4 -- stop trusting exit codes that are always 0.**
- **H6 -- always delete the project copy.** Today every run leaks a full copy into `%TEMP%`.
- **H10 -- keep the cache's config apart from the user's hand-edited one.**

Reading the tool sources turned up six facts the issue does not state. Each is written into this spec as a requirement:

1. **`hc` often cannot be installed or run as the issue describes.** Installing a dotnet global tool
   needs a .NET **SDK**, and `hc` 3.8 and later target **.NET 10**. A typical FLEx machine, including
   this one, has neither: it has only the .NET 8 runtime. "Found on disk" and "able to run" are
   separate states, and the health check must tell them apart (FR-004, FR-007).
2. **Passing words by file does not remove quoting problems.** `hc` splits each script line on spaces,
   and it treats `'` and `"` as quote toggles. A word that contains an apostrophe, which many
   orthographies use for a glottal stop, is split in two, the command is rejected, and no counter
   moves. Nothing reports the loss. Words must be quoted to suit `hc`'s splitter, and a word no quoting can
   express must be reported, never dropped (FR-013).
3. **Expected-parse strings in `test` have a broken escape.** A backslash-escaped `|` or `:` makes the
   splitter either loop forever or silently truncate the expectation. An assertion whose form or gloss
   contains a delimiter must be refused before it is sent (FR-027).
4. **`GenerateHCConfig` reports grammar load errors but still writes a configuration.** The
   configuration it writes omits the objects that failed. Its exit code is 0 both on success and when
   it prints its help text, and it is 1 for the three failures it anticipates. Any other failure
   crashes it. Success is judged from its output, not its exit code (FR-008, FR-009).
5. **The sandbox's engine may be a different HermitCrab version from FLEx's own.** FieldWorks 9.3.11
   bundles HermitCrab 3.8.2. The `hc` a user installs may be older or newer, so results are labelled
   with both versions (FR-005, Q3).
6. **A killed `hc` run loses buffered output.** Results written to the output file are buffered, and
   a timeout kill discards them. Partial results must survive a timeout (FR-020).

---

## Clarifications

### Session 2026-09-24

- Q: What should `parser_tool_missing`'s `install_hint` say for `hc`? → A: The literal command
  `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool` comes first, unchanged. It is
  followed by one sentence naming the prerequisites: a .NET SDK to install the tool, and the .NET 10
  runtime to run `hc` 3.8 and later. No version is pinned. (Resolves former Q1; FR-007.)

**Still open (deferred at specify):**

Deferred to `/speckit.clarify`. Each question has an adopted default, and the spec is written to
that default.

- **Q2 -- where do corpus expectations come from?** **Default:** from a **baseline run**. Running a
  corpus with no expectations against the project's current grammar records every parse `hc`
  produces, as an assertion file the user owns and may edit. Expectations derived from human-approved
  analyses in the project are out of scope for CP5 (see Out of Scope). [NEEDS CLARIFICATION: is
  seeding from a baseline run enough for CP5, or must CP5 also derive expectations from the
  project's fully linked, human-approved analyses?]
- **Q3 -- what if `hc`'s HermitCrab version differs from the one FieldWorks bundles?**
  **Default:** warn and label; never refuse. This follows the no-version-floor precedent (parent S8
  and 10.2: versions are reported, never compared to a floor). [NEEDS CLARIFICATION: is a
  version-skew warning enough, or should an `hc` older than FieldWorks' HermitCrab be refused?]

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find out whether the sandbox can run, and what to install if it cannot (Priority: P1)

A linguist asks the assistant to test a grammar change safely. Before anything runs, the health
check reports whether the sandbox spine is ready. If it is not, it names the missing piece:
`hc` absent, `hc` present but unable to start, or `GenerateHCConfig.exe` absent. The message tells
the user what to install, in words that work on their machine. When the spine is ready, the health
check's guidance starts naming the sandbox tool.

**Why this priority**: every other story depends on it, and on today's typical FLEx machine the
answer is "not ready". Getting that message right is the first value CP5 delivers.

**Independent Test**: run the health check on three machines or fixtures: no `hc`; an `hc` that
exists but cannot start for lack of a runtime; a working `hc`. Each gets the right status, component
detail and hint.

**Acceptance Scenarios**:

1. **Given** no `hc` on the machine, **When** health runs, **Then** `parser.sandbox.status` is
   `unavailable`, the `hc` component reads not found, and the guidance names the install command.
   The guidance never names `flextools_parse_sandbox`.
2. **Given** `hc` is installed in the default dotnet tools folder, but that folder is not on the
   server process's PATH (installed after the server started), **When** health runs, **Then** `hc` is
   still found.
3. **Given** an `hc` that exists but whose required runtime is missing, **When** health runs,
   **Then** the sandbox is `unavailable`, and the reason names the missing runtime rather than
   reporting `hc` as absent.
4. **Given** a working `hc` and `GenerateHCConfig.exe`, **When** health runs, **Then**
   `parser.sandbox.status: ready`. Both tool versions are reported, and so is FieldWorks' bundled
   HermitCrab version.
5. **Given** a caller invokes `flextools_parse_sandbox` while `hc` is missing, **When** the call runs,
   **Then** it is refused with `parser_tool_missing` (component `hc`), whose `install_hint` begins with
   the literal install command and then names the SDK and .NET 10 prerequisites. No project copy is made.

---

### User Story 2 - Parse words against the project's exported grammar, safely (Priority: P1)

The linguist asks "what does the sandbox make of these words?". The MCP makes a minimal copy of the
project outside every project folder, generates a HermitCrab configuration from the copy (reusing a
cached one when nothing has changed), and runs the words through `hc`. It returns a summary on the
fast path, or a run identifier for a long list. The copy is deleted whatever happens. The results
are stored as a normal run record, readable through the existing log, status and diff tools, and are
labelled as the sandbox's results, not the project's.

**Why this priority**: this is the spine itself, the hardened `hcparse.ps1` behind a tool.
Everything else builds on it.

**Independent Test**: parse a small word list that includes non-Latin words, a word with an
apostrophe and a word with a known failure. Check that the per-word results are correct, that the
live project folder is byte-identical afterwards, and that no copy remains in the temporary area.

**Acceptance Scenarios**:

1. **Given** an HC project with a working sandbox, **When** the user parses three words, **Then**
   each word gets its own result: parsed with N analyses, not parsed, or error with a reason. The
   run summary's counts match the per-word results.
2. **Given** a word list in a non-Latin script, **When** it is parsed, **Then** no word reports "invalid
   segment at position 1" because of encoding. This is the section-4 regression, as a standing test.
3. **Given** a word containing `'`, **When** it is parsed, **Then** it is parsed as one word. A word
   containing both `'` and `"` is reported as "cannot be expressed to hc", never silently dropped.
4. **Given** any run, **When** it ends in success, failure, timeout or cancellation, **Then** the
   project copy no longer exists, and the live project's files are unchanged.
5. **Given** the project's grammar has not changed since the last run, **When** the user parses again,
   **Then** the cached configuration is reused and generation does not run a second time.
6. **Given** the project is on XAmple, **When** the tool is called, **Then** it is refused with
   `parser_engine_mismatch` before any copy is made.
7. **Given** FLEx holds the project open, exclusively or shared, **When** the tool is called,
   **Then** the run still proceeds from a copy. When sharing is on, the result carries
   `staleness: "shared_mode_unverifiable"` and its note.

---

### User Story 3 - Rehearse a grammar edit in a named sandbox (Priority: P1)

The linguist wants to try a theory without touching the project. The assistant creates a named
sandbox from the project's current exported grammar and gets its file path. The user or assistant
edits the XML with ordinary file tools. The assistant then parses words or runs the corpus against
the sandbox and compares the result with a baseline run of the project's grammar. The sandbox is
theirs: no cache refresh, grammar change or pruning ever overwrites, invalidates or deletes it.

**Why this priority**: this is the reason the spine exists. It is the "rehearse" rung of the
confidence gradient.

**Independent Test**: create a sandbox, edit one environment, run the same words against the
project's config and against the sandbox, and diff the two runs. Then change the project's grammar
and refresh the cache. The sandbox file must be byte-identical.

**Acceptance Scenarios**:

1. **Given** a project, **When** the user creates sandbox `tighten-env`, **Then** a user-owned copy of
   the current exported configuration exists at a stated path outside every project folder,
   together with a note of which grammar state it came from.
2. **Given** an existing sandbox with that name, **When** creation is requested again, **Then** it
   is refused. The existing file is never overwritten.
3. **Given** an edited sandbox, **When** words are run against it, **Then** the run is recorded as a
   sandbox run of that named config and is diffable against a run of the project's config.
4. **Given** the project's grammar changed after the sandbox was made, **When** the sandbox is used,
   **Then** the result carries an advisory that the sandbox predates the project's current grammar.
   The sandbox is used exactly as it is.
5. **Given** a hand edit that breaks the XML, **When** the sandbox is run, **Then** the run fails with
   `hc`'s own load-error message, and nothing is reported as a parse result.

---

### User Story 4 - Run corpus assertions and learn which words regressed and which just became ambiguous (Priority: P2)

The linguist keeps a corpus of words with their expected parses. Running it against a
configuration reports each assertion as one of: **pass**; **regression** (an expected parse is
missing, including "no longer parses"); **new ambiguity** (every expected parse is still there, plus
extra ones); **changed** (both at once); or **error**. The corpus is seeded from a baseline run so
the linguist never hand-types expectations in `hc`'s format.

**Why this priority**: it turns a one-off check into a repeatable test, and it separates the two kinds
of failure that `hc`'s pass/fail line lumps together. It needs Stories 2 and 3 in place first.

**Independent Test**: seed a corpus from a baseline run. Break one rule so a word loses its only
parse. Loosen another so a word gains a second parse. Run the corpus. Exactly one assertion is a
regression and one is a new ambiguity, and each names the missing or extra parse.

**Acceptance Scenarios**:

1. **Given** no corpus, **When** the user seeds one from a completed baseline run, **Then** a
   user-owned assertion file holds every word from that run with the parses it produced. A word that
   produced no parse is recorded as an expectation of "no parse".
2. **Given** a corpus, **When** it is run and a word's only expected parse is gone, **Then** that
   assertion is a `regression` and lists the missing parse.
3. **Given** a word keeps its expected parse and gains another, **When** the corpus runs,
   **Then** the assertion is `new_ambiguity`, lists the extra parse, and is **not** counted as a
   pass.
4. **Given** a corpus run, **When** it completes, **Then** its totals come from `hc`'s test counters,
   not its parse counters. The totals agree with the per-assertion classifications, or the run
   reports the disagreement.
5. **Given** an assertion whose form or gloss contains `|`, `:` or `\`, **When** the corpus runs,
   **Then** that assertion is reported as not expressible, and the rest of the corpus still runs.

---

### User Story 5 - Diagnose a sandbox run afterwards (Priority: P2)

After a sandbox run the linguist or assistant can read what happened. The existing log tool now
fills the three sections it reserved for this spine: configuration generation (including grammar
load errors), `hc`'s console output, and `hc`'s result output. A run that timed out, was cancelled
or failed still reports how far it got.

**Why this priority**: CP3 reserved these sections as "filled by CP5". Until CP5 fills them they
answer "not applicable", which is untrue for a sandbox run.

**Independent Test**: produce four sandbox runs: one that succeeds, one whose generation logged load
errors, one that timed out, and one against a broken sandbox. Read each section of each run. Every
section is either real content or a typed not-applicable answer. None is empty.

**Acceptance Scenarios**:

1. **Given** a sandbox run, **When** the log is read for `config_generation`, **Then** it shows the
   generator's captured output, with load errors itemised and counted.
2. **Given** an in-process run, **When** a sandbox section is requested, **Then** the existing typed
   not-applicable response is returned, unchanged.
3. **Given** a sandbox run that timed out after 40 of 100 words, **When** its status is read,
   **Then** it names 40 completed words and the word in flight, and the 40 results are readable.
4. **Given** a sandbox run and an in-process run of the same words, **When** they are diffed,
   **Then** the diff runs, and it says plainly that it is comparing two engines and grammar sources.

---

### User Story 6 - Keep disk use bounded (Priority: P3)

Long-running use of the sandbox does not fill the disk. Copies are always deleted. Cached
configurations are pruned. Runs obey the existing retention. A run that would not have room for its
copy is refused before copying.

**Why this priority**: this closes the confirmed leak, but it is housekeeping behind the stories
that deliver value.

**Independent Test**: run 30 sandbox runs, including killed ones. Afterwards no project copies
remain, at most three cached configurations per project remain, and run retention holds.

**Acceptance Scenarios**:

1. **Given** too little free space for twice the files to be copied, **When** a run is requested,
   **Then** it is refused before any copy, naming the space needed and the space free.
2. **Given** the server process is killed mid-run, **When** it next runs a sandbox job, **Then**
   any copy left by an MCP sandbox run is removed.

---

### Edge Cases

- **`hc` on disk but not on PATH.** A fresh install puts `hc` in the default dotnet tools folder,
  but a server started earlier has an older PATH. Discovery checks that folder directly.
- **`hc` present but unable to start.** Discovery must actually run it, not just find the file.
- **The detected `hc` is not HermitCrab's `hc`.** Some other program named `hc` on PATH must not be
  reported as the HermitCrab tool. Discovery confirms its identity from its own help output.
- **A slow or hanging `dotnet tool list -g`.** It is already bounded at 5 seconds (existing
  `timeout` signal). Where no SDK is installed it cannot list tools at all, and that must not read as
  "not installed" when a direct path check finds `hc`.
- **Word forms.**
  - A word containing whitespace, `'`, `"`, or both quotes.
  - A word beginning with `-`, which `hc`'s option parser may read as an option (unverified; see
    FR-013).
  - A duplicate word.
  - A word that differs only in Unicode normalisation.
  - An empty list.
- **Grammar load errors during generation.** The configuration is written without the failed
  objects. This is the sandbox's version of "the grammar silently shrank". It is warned about with
  counts, never hidden, and never a refusal, because nothing is written.
- **`GenerateHCConfig` output conditions.**
  - Exit 0 with its help text, no configuration written.
  - Exit 1 with "The FieldWorks project is currently open in another application", because a lock
    marker was copied.
  - Exit 1 with "created with an older version of FLEx", because the project needs migration.
  - A crash with no message.
- **A copied lock marker.** Copying the project folder whole also copies its `.fwdata.lock`, which
  makes `GenerateHCConfig` report the copy as locked. The copy must leave it out.
- **Project folder size.** A Send/Receive project folder holds a Mercurial history, and linked media
  can be gigabytes. Copying the whole folder is wasteful, and the free-space check would refuse
  runs needlessly.
- **Copying mid-save.** FLEx may be saving `.fwdata` while it is copied. A copy that fails to load is
  reported as a generation failure, never as a grammar problem.
- **Shared-mode staleness.** With sharing on, `.fwdata` may not hold a peer's latest grammar edits
  (parent 7.3). The cache key cannot notice this.
- **A runaway word.** One word never finishes. The run timeout kills the process tree. Results
  already produced survive, and the word in flight is named.
- **Cancellation mid-word.** The process tree is killed. The cancelled state keeps the results
  produced so far.
- **Output that cannot be read unambiguously.** `hc` prints a parse as two space-padded columns
  (forms and glosses). A form or gloss containing a space can make the columns ambiguous. Such a
  parse is flagged as not reliably readable, never guessed.
- **An empty morph.** A morph whose form and gloss are both empty is omitted from `hc`'s printed
  parse.
- **An empty gloss.** A morph with no gloss prints as `?`.
- **An unexpected error from `hc`.** An exception other than an invalid segment may leave no
  per-word line. The word is reported as an error with no result, never as "not parsed".
- **Sandbox names.** A name that is empty, reserved, or contains path separators or `..` is refused.
- **Two sandbox jobs on one project.** Two jobs run concurrently on separate copies. A shared cache
  entry is built at most once at a time.
- **A write completes during a sandbox job.** The job keeps its already-generated configuration. The
  cache entry is invalidated for later jobs.

---

## Requirements *(mandatory)*

### Functional Requirements

**Tool discovery and health (H1)**

- **FR-001**: Discovery MUST locate `hc` from these sources, and MUST record which one succeeded:
  1. the `HC_TOOL_PATH` override;
  2. PATH;
  3. the default dotnet global-tools folder under the user profile, checked directly;
  4. the dotnet global-tool listing.

  The script MUST never assume `%LOCALAPPDATA%\HermitCrabTool\hc.dll`.
- **FR-002**: The script MUST NOT hard-code the FieldWorks folder. It MUST receive the paths to `hc`
  and `GenerateHCConfig.exe` from the MCP's existing resolution.
- **FR-003**: Discovery MUST confirm that a found `hc` is the HermitCrab tool. It does this by running
  it under a short bound and recognising its own usage text. Anything else counts as not found.
- **FR-004**: Health MUST tell apart "`hc` not found" from "`hc` found but cannot start". It MUST
  report the second as `unavailable` with a reason naming the missing runtime. Both cases MUST use
  the existing two-state status.
- **FR-005**: Health MUST report three versions: the `hc` tool, FieldWorks' bundled HermitCrab
  library, and `GenerateHCConfig`. Every sandbox run MUST record the same three. A difference
  between the two HermitCrab versions MUST produce a version-skew warning. It MUST NOT produce a
  refusal (Q3).
- **FR-006**: When the sandbox spine is `ready`, the health guidance MUST be allowed to name
  `flextools_parse_sandbox`. When it is `unavailable`, the guidance MUST never name it. This
  replaces the current "never named" rule.
- **FR-007**: The sandbox tool MUST refuse with `parser_tool_missing` before any copy is made when
  either component is missing or cannot start. Its fields, in order, are `component`,
  `expected_path`, `install_hint`. For `hc`, the `install_hint` MUST begin with
  `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool`, unchanged. It MUST then add one
  sentence naming the two prerequisites: a .NET SDK to install the tool, and the .NET 10 runtime to
  run `hc` 3.8 and later. The command MUST NOT pin a version (Clarified 2026-09-24).

**Configuration generation (H5, H6, H7, S6)**

- **FR-008**: Generation MUST run against a copy of the project that holds only what the generator
  needs. The copy MUST leave out the project's lock marker, its version-control history, and
  linked media and backup folders. The copy MUST live outside every FieldWorks project folder.
- **FR-009**: The generator's full output MUST be captured to the run's `generate-config.log`. It
  MUST NOT be discarded. Generation MUST count as successful only when the generator exits 0, the
  configuration file exists and is non-empty, and the output contains the generator's
  "Writing completed." line. Anything else MUST fail as `parser_config_failed`, with its fields in
  order: `exit_code`, `stderr_tail`, `log_path`, `run_id`.
- **FR-010**: Grammar load errors that the generator reports while still writing a configuration
  MUST be itemised and counted in the run record and summary, as a warning that the exported grammar
  may lack those objects. They MUST NOT be a refusal.
- **FR-011**: The copied project MUST be deleted when the run ends, on every path: success, failure,
  timeout, cancellation and exception. Before its first sandbox job, a server MUST remove copies left
  behind by MCP sandbox runs that died. A regression test MUST prove no copy remains after each
  terminal path.
- **FR-012**: Before copying, the run MUST check that free space at the copy's destination is at
  least twice the size of the files to be copied. If it is not, the run MUST be refused before any
  copy is made, stating the space needed and the space free.

**Running `hc` (H2, H4, H8, H9, H11)**

- **FR-013**: Words MUST reach `hc` only through a script file, never on a command line.
  - The script MUST be written as UTF-8 without a BOM.
  - Each word MUST be quoted so that `hc`'s line splitter yields exactly that word.
  - A word that no quoting can express, such as one containing both quote characters, MUST get a
    per-word "not expressible" result and MUST NOT be sent.
  - Whether a word beginning with `-` reaches `hc` intact MUST be verified live, and handled the
    same way if it does not.
- **FR-014**: Word lists MUST be read as UTF-8 and MUST be split on `[,\s]+` where a list arrives as
  one string. These existing behaviours MUST be preserved verbatim (H11).
- **FR-015**: Word lists MUST be de-duplicated after NFC normalisation, ordered by descending
  occurrence count where counts are known and then alphabetically, and cut to `limit` after
  ordering. The run MUST record whether the limit cut the list.
- **FR-016**: Outcomes MUST be decided from `hc`'s per-word output and its counter line, never from
  its exit code. Exit code -1 MUST be reported as a failure to start: usually a configuration
  load failure, reported with `hc`'s load-error message. It can also be an argument error, which a
  correct script never triggers.
- **FR-017**: A parse run MUST read the parse counters (`stats -p`). A corpus run MUST read the test
  counters (`stats -t`). When the counters disagree with the per-word results, the run MUST report
  the disagreement and MUST NOT silently prefer either.
- **FR-018**: Every word sent MUST produce exactly one result. The possible results are: parsed with
  its analyses, not parsed, invalid segment (with position), not expressible, error without output,
  and not reached. A word that was sent but produced no output MUST NOT be reported as "not parsed".
- **FR-019**: A parse whose printed columns cannot be read unambiguously MUST be flagged as such, with
  the raw text kept. It MUST NOT be guessed.
- **FR-020**: Each `hc` call MUST run under a timeout (`-TimeoutSeconds`). On timeout the whole
  process tree MUST be killed. The run MUST end in the existing `parser_timeout` state, with
  `timeout_seconds`, `words_completed`, `run_id`, `hint`. Every result produced before the kill MUST
  be preserved, and the word in flight MUST be named.
- **FR-021**: Everything the script prints to the console MUST be ASCII-only. Non-ASCII data MUST
  travel only in UTF-8 files.

**The script itself (H3, H12)**

- **FR-022**: The hardened script MUST ship inside the package as `hcparse.ps1`. It MUST be run as
  `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`, and never through string
  evaluation.
- **FR-023**: The script MUST write a machine-readable `run.json` giving its inputs, exit codes,
  timings and per-word results. The MCP MUST fold that file into the existing run record. It MUST NOT
  scrape the script's console prose.
- **FR-024**: The script MUST declare `$script:HCPARSE_VERSION`. That value MUST be bumped on every
  change in behaviour, and it MUST be part of the cache key.

**Three lifecycles (H6, H10; parent 7.1)**

- **FR-025**: The design MUST keep three artifacts under distinct names, and each MUST have its own
  lifecycle:
  - **the project copy**: always deleted (FR-011);
  - **the cached configuration**: managed, invalidatable, pruned to 3 per project, least recently
    used first. It is keyed on the `.fwdata` path, size and modification time, on the generator's
    path, size and modification time, and on `$script:HCPARSE_VERSION`;
  - **a user-owned sandbox configuration**: kept until the user removes it. No cache operation may
    ever overwrite, invalidate or delete it.
- **FR-026**: The cache MUST be invalidated for a project whenever a write run against that project
  completes. That includes `run_module` writes and CP4 filing runs. The script's `-ConfigOut` MUST
  target only the cache. No code path may point it at a sandbox path.

**Sandboxes and corpus assertions**

- **FR-027**: Before any expected parse is sent, it MUST be checked. An assertion whose form or gloss
  contains `|`, `:`, `\`, a quote character or whitespace MUST be reported as not expressible, and
  MUST NOT be sent. The rest of the corpus MUST still run.
- **FR-028**: A user MUST be able to create a named sandbox from the project's current exported
  configuration. The result MUST return its path and record where it came from (cache key and time).
  Creating over an existing name MUST be refused. Names MUST be validated so that they cannot leave
  the sandbox area.
- **FR-029**: A run against a sandbox that predates the project's current grammar MUST carry an
  advisory saying so. It MUST NOT alter the sandbox.
- **FR-030**: A user MUST be able to seed a corpus assertion file from a completed sandbox run. The
  file records every word with the exact parses the run produced, and "no parse" for words that
  produced none (Q2). The file MUST be user-owned under the same lifecycle as a sandbox.
- **FR-031**: Each assertion MUST be classified from `hc`'s expected-parse and actual-parse sections,
  not from its pass/fail line:
  - `pass`: every expected parse appeared and nothing else did;
  - `regression`: at least one expected parse is missing, and nothing unexpected appeared;
  - `new_ambiguity`: every expected parse appeared, plus unexpected ones;
  - `changed`: expected parses are missing and unexpected ones appeared;
  - `error`: invalid segment, not expressible, timeout or no output.
- **FR-032**: The classifications MUST map onto the existing diff buckets. Expected-but-missing maps
  to `broken`, and unexpected maps to `changed`. `new_ambiguity` MUST NOT be counted as a pass or as
  unchanged.
- **FR-033**: When a word is expected to produce no parse and now parses, the assertion MUST be
  classified `new_ambiguity`. It MUST be labelled as "now parses". The word MUST NOT be called fixed.

**The tool and the existing parse surface**

- **FR-034**: `flextools_parse_sandbox` MUST be registered as read-only with respect to the live
  database. The first line of its description MUST state the spine. The description MUST say that
  the tool works on an exported copy, never touches the live project, and welcomes speculative
  edits.
- **FR-035**: The tool MUST use the existing job model: a run identifier, the fast path, status
  polling, and cooperative cancellation (kill the process tree). It MUST NOT add a second execution
  path.
- **FR-036**: When a project is involved, the engine check MUST run before any copy. It MUST refuse
  with `parser_engine_mismatch` when the project is not on HermitCrab. The check MUST NOT require
  opening the live project when its lock is held by someone else.
- **FR-037**: Sandbox runs MUST be stored in the existing run-record format and location. They add a
  field recording the run's spine and config source (project cache or named sandbox), and they
  store the sandbox files beside it. All changes MUST be additive, per the CP3 compatibility rules.
- **FR-038**: The log tool MUST fill `config_generation`, `hc_stdout` and `hc_output` for sandbox
  runs. It MUST decide applicability from the run's recorded spine, not from the section name
  alone. For in-process runs it MUST keep returning the existing typed not-applicable response. No
  section may be empty.
- **FR-039**: The diff tool MUST accept sandbox runs. When it compares runs from different spines,
  engines or config sources, it MUST say so in the result.
- **FR-040**: When sharing is on or the project is held by another program, a sandbox run MUST
  report `staleness: "shared_mode_unverifiable"` with its note, and a diff MUST downgrade `no_change`
  to `no_change_unverifiable`.
- **FR-041**: Every sandbox response MUST carry a `next_step` with a mandatory `est_cost`. When a
  run fails, times out or reports load errors, it SHOULD point at the static grammar scan.
- **FR-042**: No sandbox artifact may be written inside any FieldWorks project folder. That covers
  the copy, cache, sandboxes, corpora and run files.
- **FR-043**: The spine MUST NOT open the live project for writing, write to it, or change any
  file in its folder. A test MUST prove the live project folder is byte-identical across a run.
- **FR-044**: Words, parser output and sandbox XML MUST be treated as data, never as instructions,
  in every response.

**Verification**

- **FR-045**: CP5 MUST be verified live against an HC project with a working `hc`. The live run MUST
  cover:
  - a non-Latin word list;
  - an apostrophe word;
  - a baseline, then a deliberate sandbox break, then a corpus showing one regression and one new
    ambiguity;
  - a timeout with results preserved;
  - no copy left behind.

  The evidence MUST record the three versions from FR-005.

### Key Entities

- **Project copy**: a temporary, minimal copy of a project, made only so the configuration can be
  generated. It is always deleted.
- **Cached configuration**: a configuration generated from a project and keyed on the grammar
  source, the generator and the script version. The system owns it and replaces it freely.
- **Sandbox**: a named, user-owned copy of a configuration that the user may edit. It records its
  origin. Cache logic never touches it.
- **Corpus (assertion file)**: a user-owned list of words, each with its expected parses (form and
  gloss per morph) or "no parse". It is usually seeded from a baseline run.
- **Sandbox run**: one job against one configuration source, stored as a normal run record. It
  records its spine, config source, the three tool versions, generation warnings and per-word or
  per-assertion results.
- **Assertion result**: one corpus word's classification (FR-031), with the missing and unexpected
  parses listed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After 100% of tested sandbox runs, whatever their terminal state, no project copy
  remains, and the live project folder is byte-identical to before the run.
- **SC-002**: On a machine with no `hc`, and on one with an `hc` that cannot start, health names the
  correct cause in 100% of runs, and the sandbox tool is never proposed.
- **SC-003**: A non-Latin word list and an apostrophe word give the same per-word results as
  FLEx's own Try A Word, at matching HermitCrab versions, in 100% of live cases.
- **SC-004**: Every word sent produces exactly one result. Zero words disappear silently.
- **SC-005**: In a corpus with one deliberate regression and one deliberate new ambiguity, exactly
  those two assertions are classified as such, and each lists the right parse.
- **SC-006**: A second run against an unchanged grammar skips generation, and in the maintainer's
  test it runs at least twice as fast as a cold run.
- **SC-007**: No cache operation changes a sandbox or corpus file. Their bytes are identical across
  cache refresh, invalidation and pruning.
- **SC-008**: A run that times out preserves 100% of the results produced before the kill, and names
  the word in flight.
- **SC-009**: The three sandbox log sections return real content for 100% of sandbox runs, and never
  return an empty section.
- **SC-010**: The existing test suite, the read-only boundary tests and the error-model field-order
  tests remain green.

## Assumptions

- **The run-record format is CP3's, not the parent's old listing.** CP3's artifact contract corrected
  the parent's listing (`run.json`, `hc-output.txt`, and so on). `run.json` survives only as the
  script's hand-off file, which the MCP folds into the record (FR-023).
- **The bundled script is canonical.** The contributed root-level `hcparse.ps1` is replaced by the
  packaged, hardened copy. Its history stays in git, and its section-4 lessons are carried forward
  verbatim (FR-014).
- **Sandbox and corpus files live under `~/.flextoolsmcp`,** beside the existing run records, cache
  and backups. They are never under a project folder.
- **The engine check reads the copy.** Reading `ActiveParser` from the copied project avoids opening
  the live project. On non-shared projects, a live open takes the lock, and FLEx may hold it.
  `ActiveParser` is not an element of its own in the `.fwdata` file. It sits inside the XML text of
  the `MoMorphData` object's `ParserParameters` string. It can therefore be read from a copy in two
  steps, or by opening the copy through LCM; planning chooses. An absent or unreadable value counts
  as XAmple, so the check fails safe (CP2 domain review).
- **Console output survives a kill; file output does not.** `hc` writes results to its console
  writer, which flushes as it goes, unless an output file is given; that file's writer does not
  flush until closed. This is why FR-020 needs partial results to come from the console stream or
  be flushed often (domain review, cycle 1).
- **`hc` is run without its continue-on-load-error flag.** A configuration `hc` cannot fully load
  fails loudly with `hc`'s own message (US3 scenario 5). The generator's load errors happen earlier
  and are handled by FR-010.
- **No full-folder copy.** Which files the generator needs, such as the `.fwdata` and the
  writing-system store, is decided in planning and verified live. The free-space check measures what
  is actually copied.
- **Engine versions:** FieldWorks 9.3.11 bundles HermitCrab 3.8.2. `hc` 3.8.x needs .NET 10, and
  3.7.x runs on .NET 8. Both facts come from the installed files and the tool's project history.
- **`GenerateHCConfig` initialises the SLDR at start-up.** Whether that needs network access is
  unverified. If it hangs offline, the generation timeout covers it.
- **The engine check follows the existing preflight.** It is `check_active_parser`, and its refusal
  shape is `ParserEngineMismatchDetail`.

## Out of Scope

- Filing anything from a sandbox run. This is semantically impossible (parent 1.1), and no path to
  it may exist.
- Editing grammar XML for the user, or suggesting rule edits (parent 18). CP5 gives the path, and the
  user or assistant edits the file with ordinary tools.
- Deriving corpus expectations from the project's human-approved analyses (Q2 default). This is
  deferred.
- Installing `hc`, the .NET SDK or a runtime on the user's behalf. CP5 names these, never performs
  them.
- XAmple, and anything other than Windows.
- Contract-catalog prose, CHANGELOG, telemetry and user documentation beyond the contract rows. These
  belong to CP6 (#167).

## Verbatim Constraints

- Tool: `flextools_parse_sandbox`.
- Script: `hcparse.ps1`; version constant `$script:HCPARSE_VERSION`; parameters `-TimeoutSeconds`,
  `-ConfigOut`; generator log `generate-config.log`; hand-off file `run.json`.
- Invocation: `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File`.
- Health: `parser.sandbox.status: ready` / `unavailable`; components `hc`, `GenerateHCConfig.exe`.
- Install hint: `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool`.
- Override: `HC_TOOL_PATH` (existing).
- `hc` commands: `parse`, `test`, `stats -p`, `stats -t`; test output sections `Expected parses:` and
  `Actual parses:`.
- Error codes and fields, in this order:
  - `parser_tool_missing`: `component`, `expected_path`, `install_hint` (existing)
  - `parser_config_failed`: `exit_code`, `stderr_tail`, `log_path`, `run_id` (new)
  - `parser_timeout`: `timeout_seconds`, `words_completed`, `run_id`, `hint` (existing)
  - `parser_engine_mismatch` (existing, unchanged)
- Log sections: `config_generation`, `hc_stdout`, `hc_output`.
- Staleness: `shared_mode_unverifiable`; diff verdict `no_change_unverifiable`.
- The leak location named in the issue: `%TEMP%`.
- Contract version stays `tool-responses/1.0`.
